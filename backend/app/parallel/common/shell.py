"""
PII Boundary Guard - I/O Operations

This module contains all I/O operations for the PII boundary guard,
including Redis state management, event publishing, and the critical
assert_parallel_safe function.
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Callable
import asyncio
import logging

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from .core import contains_pii, should_open_circuit, calculate_risk_score
from .contracts import (
    PIIBoundaryViolation,
    CircuitBreakerState,
    CircuitBreakerStatus,
    CircuitBreakerConfig,
    PIIViolationType,
    ParallelCallRequest,
    ParallelCallResponse
)
from .events import (
    PIIViolationDetected,
    CircuitBreakerOpened,
    CircuitBreakerClosed,
    CircuitBreakerHalfOpen,
    PIIBoundaryBypass,
    ParallelCallCompleted,
    ParallelCallFailed
)

logger = logging.getLogger(__name__)


class PIIBoundaryError(Exception):
    """Raised when PII is detected in data bound for external APIs."""
    
    def __init__(self, violation: PIIBoundaryViolation):
        self.violation = violation
        super().__init__(f"PII detected: {violation.violation_type.value}")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and calls are blocked."""
    
    def __init__(self, service_name: str, next_attempt_time: Optional[datetime] = None):
        self.service_name = service_name
        self.next_attempt_time = next_attempt_time
        super().__init__(f"Circuit breaker open for {service_name}")


class PIIBoundaryGuard:
    """
    PII Boundary Guard implementation with Redis-based circuit breaker.
    
    This class provides the critical assert_parallel_safe function and
    circuit breaker functionality for protecting against PII leaks
    and service failures.
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        config: Optional[CircuitBreakerConfig] = None,
        event_publisher: Optional[Callable] = None
    ):
        self.redis = redis_client
        self.config = config or CircuitBreakerConfig()
        self.event_publisher = event_publisher or self._default_event_publisher
    
    async def assert_parallel_safe(self, data: Dict[str, Any], context: Optional[str] = None) -> None:
        """
        Validate that data is safe to send to Parallel.ai.
        
        This is the CRITICAL SECURITY FUNCTION that must be called
        before ANY data is sent to external APIs.
        
        Args:
            data: Dictionary containing the payload to validate
            context: Optional context about where this data originated
            
        Raises:
            PIIBoundaryError: If PII is detected in the data
            ValueError: If data is invalid or too large
        """
        if not data:
            return
        
        # Check payload size limit (15k chars as per requirements)
        try:
            payload_str = json.dumps(data, ensure_ascii=False)
        except (ValueError, TypeError) as e:
            # Handle circular references and other JSON serialization issues
            raise ValueError(f"Invalid payload structure: {str(e)}")
            
        if len(payload_str) > 15000:
            raise ValueError(f"Payload too large: {len(payload_str)} chars (limit: 15000)")
        
        # Extract text for PII analysis
        text_content = self._extract_all_text(data)
        
        # Perform PII detection
        has_pii, pii_matches = contains_pii(text_content)
        
        if has_pii:
            # Calculate risk score
            risk_score = calculate_risk_score(data)
            
            # Create violation object
            violation = PIIBoundaryViolation(
                violation_type=PIIViolationType(pii_matches[0].pattern_type),
                detected_patterns=[match.matched_text for match in pii_matches[:5]],  # Limit to 5 patterns
                risk_score=risk_score,
                payload_size=len(payload_str),
                timestamp=datetime.utcnow(),
                context=context
            )
            
            # Emit violation event
            event = PIIViolationDetected(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                violation_type=violation.violation_type,
                detected_patterns=violation.detected_patterns,
                risk_score=violation.risk_score,
                payload_size=violation.payload_size,
                source_endpoint=context or "unknown",
                context={"full_patterns": len(pii_matches)}
            )
            
            try:
                await self.event_publisher(event)
            except Exception as e:
                # Log the event publishing failure but don't let it prevent PII blocking
                logger.warning(f"Failed to publish PII violation event: {e}")
                # Continue to raise PIIBoundaryError regardless
            
            # Always block PII - no exceptions
            raise PIIBoundaryError(violation)
    
    async def circuit_breaker_call(
        self, 
        func: Callable,
        service_name: str = "parallel_ai",
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            service_name: Name of the service for circuit breaker state
            *args, **kwargs: Arguments to pass to the function
            
        Returns:
            Result of the function call
            
        Raises:
            CircuitBreakerOpenError: If circuit breaker is open
        """
        # Check circuit breaker state
        status = await self.get_circuit_status(service_name)
        
        if status.state == CircuitBreakerState.OPEN:
            if status.next_attempt_time and datetime.utcnow() < status.next_attempt_time:
                raise CircuitBreakerOpenError(service_name, status.next_attempt_time)
            else:
                # Move to half-open state
                await self._set_circuit_state(service_name, CircuitBreakerState.HALF_OPEN)
        
        try:
            # Execute the function
            start_time = datetime.utcnow()
            result = await func(*args, **kwargs)
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Success - update circuit breaker state
            await self._record_success(service_name)
            
            # Emit success event
            cost_euros = 0.0
            if hasattr(result, 'cost_euros'):
                cost_euros = getattr(result, 'cost_euros', 0.0)
            elif isinstance(result, dict) and 'cost_euros' in result:
                cost_euros = result.get('cost_euros', 0.0)
            
            if cost_euros > 0 or service_name.startswith('parallel'):  # Always emit for parallel calls
                event = ParallelCallCompleted(
                    event_id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    endpoint=service_name,
                    response_time_ms=int(execution_time),
                    cost_euros=cost_euros,
                    payload_size_bytes=len(json.dumps(args[0]) if args else "{}"),
                    response_size_bytes=len(str(result))
                )
                await self.event_publisher(event)
            
            return result
            
        except Exception as e:
            # Failure - update circuit breaker state
            await self._record_failure(service_name, str(e))
            
            # Emit failure event
            event = ParallelCallFailed(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                endpoint=service_name,
                error_type=type(e).__name__,
                error_message=str(e),
                status_code=getattr(e, 'status_code', None)
            )
            await self.event_publisher(event)
            
            # Check if we should open circuit
            status = await self.get_circuit_status(service_name)
            if should_open_circuit(status.failure_count, self.config.failure_threshold):
                await self._open_circuit(service_name)
            
            raise
    
    async def get_circuit_status(self, service_name: str) -> CircuitBreakerStatus:
        """Get current circuit breaker status for a service."""
        if not self.redis:
            # Default to closed state if no Redis
            return CircuitBreakerStatus(
                state=CircuitBreakerState.CLOSED,
                failure_count=0,
                last_failure_time=None,
                next_attempt_time=None,
                total_requests=0,
                successful_requests=0,
                failed_requests=0
            )
        
        key_prefix = f"{self.config.redis_key_prefix}:{service_name}"
        
        try:
            # Get all circuit breaker data in one transaction
            pipe = self.redis.pipeline()
            pipe.get(f"{key_prefix}:state")
            pipe.get(f"{key_prefix}:failure_count")
            pipe.get(f"{key_prefix}:last_failure_time")
            pipe.get(f"{key_prefix}:next_attempt_time")
            pipe.get(f"{key_prefix}:total_requests")
            pipe.get(f"{key_prefix}:successful_requests")
            pipe.get(f"{key_prefix}:failed_requests")
            
            results = await pipe.execute()
        except Exception as e:
            # Redis connection failed - fail safe to closed state
            logger.warning(f"Redis connection failed for circuit breaker: {e}")
            return CircuitBreakerStatus(
                state=CircuitBreakerState.CLOSED,
                failure_count=0,
                last_failure_time=None,
                next_attempt_time=None,
                total_requests=0,
                successful_requests=0,
                failed_requests=0
            )
        
        state_str = results[0] or "closed"
        state = CircuitBreakerState(state_str.decode() if isinstance(state_str, bytes) else state_str)
        
        return CircuitBreakerStatus(
            state=state,
            failure_count=int(results[1] or 0),
            last_failure_time=self._parse_datetime(results[2]),
            next_attempt_time=self._parse_datetime(results[3]),
            total_requests=int(results[4] or 0),
            successful_requests=int(results[5] or 0),
            failed_requests=int(results[6] or 0)
        )
    
    async def reset_circuit_breaker(self, service_name: str) -> None:
        """Manually reset circuit breaker to closed state."""
        if not self.redis:
            return
        
        key_prefix = f"{self.config.redis_key_prefix}:{service_name}"
        
        pipe = self.redis.pipeline()
        pipe.set(f"{key_prefix}:state", CircuitBreakerState.CLOSED.value)
        pipe.delete(f"{key_prefix}:failure_count")
        pipe.delete(f"{key_prefix}:last_failure_time")
        pipe.delete(f"{key_prefix}:next_attempt_time")
        await pipe.execute()
        
        # Emit reset event
        event = CircuitBreakerClosed(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            service_name=service_name,
            downtime_duration_seconds=0,
            recovery_attempts=0,
            context={"manual_reset": True}
        )
        await self.event_publisher(event)
    
    def _extract_all_text(self, data: Any, max_depth: int = 3) -> str:
        """Extract all text content from data structure for PII analysis."""
        if max_depth <= 0:
            return ""
        
        text_parts = []
        
        if isinstance(data, str):
            text_parts.append(data)
        elif isinstance(data, dict):
            for key, value in data.items():
                text_parts.append(str(key))
                text_parts.append(self._extract_all_text(value, max_depth - 1))
        elif isinstance(data, (list, tuple)):
            for item in data:
                text_parts.append(self._extract_all_text(item, max_depth - 1))
        else:
            text_parts.append(str(data))
        
        return " ".join(text_parts)
    
    async def _record_success(self, service_name: str) -> None:
        """Record successful call and update circuit breaker state."""
        if not self.redis:
            return
        
        try:
            key_prefix = f"{self.config.redis_key_prefix}:{service_name}"
            
            pipe = self.redis.pipeline()
            pipe.set(f"{key_prefix}:state", CircuitBreakerState.CLOSED.value)
            pipe.delete(f"{key_prefix}:failure_count")
            pipe.delete(f"{key_prefix}:last_failure_time")
            pipe.delete(f"{key_prefix}:next_attempt_time")
            pipe.incr(f"{key_prefix}:total_requests")
            pipe.incr(f"{key_prefix}:successful_requests")
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to record circuit breaker success: {e}")
            # Continue silently - circuit breaker degrades gracefully
    
    async def _record_failure(self, service_name: str, error_message: str) -> None:
        """Record failed call and update circuit breaker state."""
        if not self.redis:
            return
        
        try:
            key_prefix = f"{self.config.redis_key_prefix}:{service_name}"
            now = datetime.utcnow().isoformat()
            
            pipe = self.redis.pipeline()
            pipe.incr(f"{key_prefix}:failure_count")
            pipe.set(f"{key_prefix}:last_failure_time", now)
            pipe.incr(f"{key_prefix}:total_requests")
            pipe.incr(f"{key_prefix}:failed_requests")
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to record circuit breaker failure: {e}")
            # Continue silently - circuit breaker degrades gracefully
    
    async def _open_circuit(self, service_name: str) -> None:
        """Open circuit breaker and set recovery time."""
        if not self.redis:
            return
        
        key_prefix = f"{self.config.redis_key_prefix}:{service_name}"
        next_attempt = datetime.utcnow() + timedelta(seconds=self.config.recovery_timeout_seconds)
        
        pipe = self.redis.pipeline()
        pipe.set(f"{key_prefix}:state", CircuitBreakerState.OPEN.value)
        pipe.set(f"{key_prefix}:next_attempt_time", next_attempt.isoformat())
        await pipe.execute()
        
        # Get current status for event
        status = await self.get_circuit_status(service_name)
        
        # Emit circuit opened event
        event = CircuitBreakerOpened(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            service_name=service_name,
            failure_count=status.failure_count,
            failure_threshold=self.config.failure_threshold,
            recovery_time=next_attempt
        )
        await self.event_publisher(event)
    
    async def _set_circuit_state(self, service_name: str, state: CircuitBreakerState) -> None:
        """Set circuit breaker state."""
        if not self.redis:
            return
        
        key_prefix = f"{self.config.redis_key_prefix}:{service_name}"
        await self.redis.set(f"{key_prefix}:state", state.value)
        
        if state == CircuitBreakerState.HALF_OPEN:
            event = CircuitBreakerHalfOpen(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                service_name=service_name,
                test_requests_allowed=self.config.half_open_max_calls
            )
            await self.event_publisher(event)
    
    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from Redis value."""
        if not value:
            return None
        
        try:
            date_str = value.decode() if isinstance(value, bytes) else str(value)
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
    
    async def _default_event_publisher(self, event) -> None:
        """Default event publisher that logs events."""
        logger.info(f"PII Boundary Event: {type(event).__name__} - {event}")


# Global instance for easy access
_global_guard: Optional[PIIBoundaryGuard] = None


async def assert_parallel_safe(data: Dict[str, Any], context: Optional[str] = None) -> None:
    """
    Global function to validate data is safe for Parallel.ai.
    
    This is the CRITICAL SECURITY FUNCTION that must be called
    before ANY data is sent to external APIs.
    
    Args:
        data: Dictionary containing the payload to validate
        context: Optional context about where this data originated
        
    Raises:
        PIIBoundaryError: If PII is detected in the data
        ValueError: If data is invalid or too large
    """
    global _global_guard
    
    if _global_guard is None:
        _global_guard = PIIBoundaryGuard()
    
    await _global_guard.assert_parallel_safe(data, context)


def initialize_pii_guard(
    redis_client: Optional[redis.Redis] = None,
    config: Optional[CircuitBreakerConfig] = None,
    event_publisher: Optional[Callable] = None
) -> PIIBoundaryGuard:
    """Initialize the global PII boundary guard."""
    global _global_guard
    _global_guard = PIIBoundaryGuard(redis_client, config, event_publisher)
    return _global_guard