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
import logging

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from .core import (
    contains_pii, 
    should_open_circuit, 
    calculate_risk_score,
    should_activate_degraded_mode,
    calculate_service_health_score,
    estimate_recovery_time,
    calculate_degraded_coverage_estimate
)
from .contracts import (
    PIIBoundaryViolation,
    CircuitBreakerState,
    CircuitBreakerStatus,
    CircuitBreakerConfig,
    PIIViolationType,
    DegradedModeStatus,
    DegradedModeConfig,
    ServiceHealthStatus
)
from .events import (
    PIIViolationDetected,
    CircuitBreakerOpened,
    CircuitBreakerClosed,
    CircuitBreakerHalfOpen,
    ParallelCallCompleted,
    ParallelCallFailed,
    DegradedModeActivated,
    DegradedModeDeactivated,
    ServiceHealthCheckCompleted,
    FallbackSystemActivated,
    RecoveryAttemptStarted,
    RecoveryAttemptCompleted
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
        degraded_config: Optional[DegradedModeConfig] = None,
        event_publisher: Optional[Callable] = None,
    ):
        self.redis = redis_client
        self.config = config or CircuitBreakerConfig()
        self.degraded_config = degraded_config or DegradedModeConfig()
        self.event_publisher = event_publisher or self._default_event_publisher

    async def assert_parallel_safe(
        self, data: Dict[str, Any], context: Optional[str] = None
    ) -> None:
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
            raise ValueError(
                f"Payload too large: {len(payload_str)} chars (limit: 15000)"
            )

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
                detected_patterns=[
                    match.matched_text for match in pii_matches[:5]
                ],  # Limit to 5 patterns
                risk_score=risk_score,
                payload_size=len(payload_str),
                timestamp=datetime.utcnow(),
                context=context,
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
                context={"full_patterns": len(pii_matches)},
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
        self, func: Callable, service_name: str = "parallel_ai", *args, **kwargs
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
            if (
                status.next_attempt_time
                and datetime.utcnow() < status.next_attempt_time
            ):
                raise CircuitBreakerOpenError(service_name, status.next_attempt_time)
            else:
                # Move to half-open state
                await self._set_circuit_state(
                    service_name, CircuitBreakerState.HALF_OPEN
                )

        try:
            # Execute the function
            start_time = datetime.utcnow()
            result = await func(*args, **kwargs)
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Success - update circuit breaker state
            await self._record_success(service_name)

            # Emit success event
            cost_euros = 0.0
            if hasattr(result, "cost_euros"):
                cost_euros = getattr(result, "cost_euros", 0.0)
            elif isinstance(result, dict) and "cost_euros" in result:
                cost_euros = result.get("cost_euros", 0.0)

            if cost_euros > 0 or service_name.startswith(
                "parallel"
            ):  # Always emit for parallel calls
                event = ParallelCallCompleted(
                    event_id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    endpoint=service_name,
                    response_time_ms=int(execution_time),
                    cost_euros=cost_euros,
                    payload_size_bytes=len(json.dumps(args[0]) if args else "{}"),
                    response_size_bytes=len(str(result)),
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
                status_code=getattr(e, "status_code", None),
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
                failed_requests=0,
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
                failed_requests=0,
            )

        state_str = results[0] or "closed"
        state = CircuitBreakerState(
            state_str.decode() if isinstance(state_str, bytes) else state_str
        )

        return CircuitBreakerStatus(
            state=state,
            failure_count=int(results[1] or 0),
            last_failure_time=self._parse_datetime(results[2]),
            next_attempt_time=self._parse_datetime(results[3]),
            total_requests=int(results[4] or 0),
            successful_requests=int(results[5] or 0),
            failed_requests=int(results[6] or 0),
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
            context={"manual_reset": True},
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
        next_attempt = datetime.utcnow() + timedelta(
            seconds=self.config.recovery_timeout_seconds
        )

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
            recovery_time=next_attempt,
        )
        await self.event_publisher(event)

    async def _set_circuit_state(
        self, service_name: str, state: CircuitBreakerState
    ) -> None:
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
                test_requests_allowed=self.config.half_open_max_calls,
            )
            await self.event_publisher(event)

    def _parse_datetime(self, value) -> Optional[datetime]:
        """Parse datetime from Redis value."""
        if not value:
            return None

        try:
            date_str = value.decode() if isinstance(value, bytes) else str(value)
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    async def get_degraded_mode_status(self) -> DegradedModeStatus:
        """Get current degraded mode status."""
        if not self.redis:
            return DegradedModeStatus(
                active=False,
                activated_at=None,
                trigger_reason="",
                active_fallbacks=[],
                estimated_coverage_percentage=1.0,
                recovery_detection_active=False
            )
            
        try:
            key_prefix = f"{self.config.redis_key_prefix}:degraded_mode"
            
            pipe = self.redis.pipeline()
            pipe.get(f"{key_prefix}:active")
            pipe.get(f"{key_prefix}:activated_at")
            pipe.get(f"{key_prefix}:trigger_reason")
            pipe.get(f"{key_prefix}:active_fallbacks")
            pipe.get(f"{key_prefix}:coverage_percentage")
            
            results = await pipe.execute()
            
            active = bool(results[0])
            activated_at_str = results[1]
            trigger_reason = results[2] or ""
            fallbacks_str = results[3] or "[]"
            coverage = float(results[4] or 1.0)
            
            activated_at = None
            if activated_at_str:
                try:
                    activated_at = datetime.fromisoformat(activated_at_str.decode() if isinstance(activated_at_str, bytes) else activated_at_str)
                except ValueError:
                    pass
                    
            import json
            active_fallbacks = json.loads(fallbacks_str.decode() if isinstance(fallbacks_str, bytes) else fallbacks_str)
            
            return DegradedModeStatus(
                active=active,
                activated_at=activated_at,
                trigger_reason=trigger_reason.decode() if isinstance(trigger_reason, bytes) else trigger_reason,
                active_fallbacks=active_fallbacks,
                estimated_coverage_percentage=coverage,
                recovery_detection_active=True  # Always active when Redis available
            )
            
        except Exception as e:
            logger.warning(f"Failed to get degraded mode status: {e}")
            return DegradedModeStatus(
                active=False,
                activated_at=None,
                trigger_reason="",
                active_fallbacks=[],
                estimated_coverage_percentage=1.0,
                recovery_detection_active=False
            )
    
    async def activate_degraded_mode(
        self,
        trigger_service: str,
        trigger_reason: str,
        active_fallbacks: List[str]
    ) -> None:
        """Activate degraded mode with specified fallback systems."""
        current_time = datetime.utcnow()
        coverage = calculate_degraded_coverage_estimate(active_fallbacks)
        
        if self.redis:
            try:
                key_prefix = f"{self.config.redis_key_prefix}:degraded_mode"
                
                pipe = self.redis.pipeline()
                pipe.set(f"{key_prefix}:active", True)
                pipe.set(f"{key_prefix}:activated_at", current_time.isoformat())
                pipe.set(f"{key_prefix}:trigger_reason", trigger_reason)
                pipe.set(f"{key_prefix}:coverage_percentage", coverage)
                
                import json
                pipe.set(f"{key_prefix}:active_fallbacks", json.dumps(active_fallbacks))
                
                await pipe.execute()
                
            except Exception as e:
                logger.error(f"Failed to store degraded mode status: {e}")
        
        # Emit degraded mode activation event
        event = DegradedModeActivated(
            event_id=str(uuid.uuid4()),
            timestamp=current_time,
            trigger_service=trigger_service,
            trigger_reason=trigger_reason,
            activated_fallbacks=active_fallbacks,
            estimated_coverage_percentage=coverage,
            expected_recovery_time=estimate_recovery_time(
                3, current_time, current_time  # Assume circuit opened
            )
        )
        await self.event_publisher(event)
        
        # Activate each fallback system
        for fallback in active_fallbacks:
            fallback_event = FallbackSystemActivated(
                event_id=str(uuid.uuid4()),
                timestamp=current_time,
                fallback_system=fallback,
                activation_reason=trigger_reason,
                estimated_coverage=coverage,
                expected_performance_impact=0.3  # 30% performance impact
            )
            await self.event_publisher(fallback_event)
        
        logger.info(f"Degraded mode activated: {trigger_reason} (coverage: {coverage:.1%})")
    
    async def deactivate_degraded_mode(
        self,
        recovery_trigger: str = "automatic_recovery",
        operations_count: int = 0
    ) -> None:
        """Deactivate degraded mode and return to normal operations."""
        current_time = datetime.utcnow()
        
        # Get current status for event
        status = await self.get_degraded_mode_status()
        
        if self.redis:
            try:
                key_prefix = f"{self.config.redis_key_prefix}:degraded_mode"
                
                pipe = self.redis.pipeline()
                pipe.delete(f"{key_prefix}:active")
                pipe.delete(f"{key_prefix}:activated_at")
                pipe.delete(f"{key_prefix}:trigger_reason")
                pipe.delete(f"{key_prefix}:active_fallbacks")
                pipe.delete(f"{key_prefix}:coverage_percentage")
                
                await pipe.execute()
                
            except Exception as e:
                logger.error(f"Failed to clear degraded mode status: {e}")
        
        # Calculate degraded duration
        degraded_duration = 0
        if status.activated_at:
            degraded_duration = int((current_time - status.activated_at).total_seconds())
        
        # Emit deactivation event
        event = DegradedModeDeactivated(
            event_id=str(uuid.uuid4()),
            timestamp=current_time,
            degraded_duration_seconds=degraded_duration,
            recovery_trigger=recovery_trigger,
            operations_during_degraded=operations_count,
            successful_recovery=True
        )
        await self.event_publisher(event)
        
        logger.info(f"Degraded mode deactivated after {degraded_duration}s")
    
    async def check_service_health(
        self,
        service_name: str,
        health_check_func: Optional[Callable] = None
    ) -> ServiceHealthStatus:
        """Check health of external service."""
        current_time = datetime.utcnow()
        
        if not health_check_func:
            # Default health check - just check circuit breaker status
            circuit_status = await self.get_circuit_status(service_name)
            is_healthy = circuit_status.state == CircuitBreakerState.CLOSED
            
            health_score = calculate_service_health_score(
                circuit_status.successful_requests,
                circuit_status.failed_requests,
                1000  # Assume 1s response time if no data
            )
            
            status = ServiceHealthStatus(
                service_name=service_name,
                is_healthy=is_healthy,
                last_check_time=current_time,
                response_time_ms=None,
                consecutive_failures=circuit_status.failure_count,
                consecutive_successes=max(0, circuit_status.successful_requests - circuit_status.failed_requests),
                health_score=health_score
            )
            
        else:
            # Use custom health check function
            try:
                start_time = current_time
                health_result = await health_check_func()
                response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                status = ServiceHealthStatus(
                    service_name=service_name,
                    is_healthy=health_result.get('healthy', False),
                    last_check_time=current_time,
                    response_time_ms=response_time,
                    error_message=health_result.get('error'),
                    health_score=health_result.get('score', 0.0)
                )
                
            except Exception as e:
                status = ServiceHealthStatus(
                    service_name=service_name,
                    is_healthy=False,
                    last_check_time=current_time,
                    response_time_ms=None,
                    error_message=str(e),
                    consecutive_failures=1,
                    health_score=0.0
                )
        
        # Emit health check event
        health_event = ServiceHealthCheckCompleted(
            event_id=str(uuid.uuid4()),
            timestamp=current_time,
            service_name=service_name,
            health_check_passed=status.is_healthy,
            response_time_ms=status.response_time_ms,
            health_score=status.health_score,
            consecutive_successes=status.consecutive_successes,
            consecutive_failures=status.consecutive_failures
        )
        await self.event_publisher(health_event)
        
        return status

    async def _default_event_publisher(self, event) -> None:
        """Default event publisher that logs events."""
        logger.info(f"PII Boundary Event: {type(event).__name__} - {event}")


# Global instance for easy access
_global_guard: Optional[PIIBoundaryGuard] = None


async def assert_parallel_safe(
    data: Dict[str, Any], context: Optional[str] = None
) -> None:
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
    event_publisher: Optional[Callable] = None,
) -> PIIBoundaryGuard:
    """Initialize the global PII boundary guard."""
    global _global_guard
    _global_guard = PIIBoundaryGuard(redis_client, config, event_publisher)
    return _global_guard
