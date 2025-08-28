"""
Observability integration for Parallel Common module.
Collects metrics for PII detection, circuit breaker, and API calls.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from ...observability.contracts import MetricType
from ...observability.core import create_metric
from ...observability.integration import get_tracer, TrackedOperation
from ...observability.shell import record_metric

logger = logging.getLogger(__name__)

# Get tracer for this module
tracer = get_tracer("regops.parallel.common")


class ParallelObservabilityCollector:
    """
    Collects observability metrics for the parallel common module.
    Integrates with existing PII boundary guard and circuit breaker.
    """

    def __init__(self, storage=None):
        self.storage = storage

    async def track_pii_detection(
        self,
        duration_ms: float,
        has_pii: bool,
        payload_size: int,
        pattern_count: int = 0,
        context: Optional[str] = None,
    ) -> None:
        """
        Track PII detection metrics.

        Args:
            duration_ms: Time taken for PII detection
            has_pii: Whether PII was detected
            payload_size: Size of payload in bytes
            pattern_count: Number of PII patterns found
            context: Optional context (module, operation, etc.)
        """
        try:
            labels = {
                "has_pii": str(has_pii).lower(),
                "context": context or "unknown",
            }

            # Record PII detection duration
            await self._record_metric(
                name="pii.detection.duration_ms",
                value=duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record PII violations (critical security metric)
            if has_pii:
                await self._record_metric(
                    name="pii.violations.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels=labels,
                )

                # Record pattern count for violated payloads
                await self._record_metric(
                    name="pii.patterns.detected",
                    value=pattern_count,
                    metric_type=MetricType.GAUGE,
                    labels=labels,
                )

            # Record payload size metrics
            await self._record_metric(
                name="pii.payload.size_bytes",
                value=payload_size,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record successful PII checks
            await self._record_metric(
                name="pii.checks.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels={**labels, "status": "completed"},
            )

        except Exception as e:
            logger.error(f"Failed to track PII detection metrics: {e}")

    async def track_circuit_breaker_state(
        self,
        service_name: str,
        state: str,  # "closed", "open", "half_open"
        failure_count: int = 0,
        success_rate: float = 0.0,
    ) -> None:
        """
        Track circuit breaker state changes.

        Args:
            service_name: Name of the service
            state: Current circuit breaker state
            failure_count: Current failure count
            success_rate: Current success rate (0.0-1.0)
        """
        try:
            labels = {"service": service_name, "state": state}

            # Map state to numeric value for gauge
            state_values = {"closed": 0, "open": 1, "half_open": 2}
            state_value = state_values.get(state, 0)

            await self._record_metric(
                name="circuit.breaker.state",
                value=state_value,
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

            # Record failure count
            await self._record_metric(
                name="circuit.breaker.failures.total",
                value=failure_count,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record success rate
            await self._record_metric(
                name="circuit.breaker.success_rate",
                value=success_rate,
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

        except Exception as e:
            logger.error(f"Failed to track circuit breaker metrics: {e}")

    async def track_parallel_api_call(
        self,
        endpoint: str,
        duration_ms: float,
        success: bool,
        cost_euros: float = 0.0,
        payload_size_bytes: int = 0,
        response_size_bytes: int = 0,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Track Parallel.ai API call metrics.

        Args:
            endpoint: API endpoint called
            duration_ms: Call duration in milliseconds  
            success: Whether the call succeeded
            cost_euros: Cost of the API call in euros
            payload_size_bytes: Size of request payload
            response_size_bytes: Size of response
            error_type: Type of error if call failed
        """
        try:
            labels = {
                "endpoint": endpoint,
                "status": "success" if success else "failure",
            }

            if error_type:
                labels["error_type"] = error_type

            # Record total API calls
            await self._record_metric(
                name="parallel.calls.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record call duration
            await self._record_metric(
                name="parallel.calls.duration_ms",
                value=duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record API costs (critical budget metric)
            if cost_euros > 0:
                await self._record_metric(
                    name="parallel.costs.eur",
                    value=cost_euros,
                    metric_type=MetricType.COUNTER,
                    labels=labels,
                )

            # Record payload and response sizes
            if payload_size_bytes > 0:
                await self._record_metric(
                    name="parallel.payload.size_bytes",
                    value=payload_size_bytes,
                    metric_type=MetricType.HISTOGRAM,
                    labels=labels,
                )

            if response_size_bytes > 0:
                await self._record_metric(
                    name="parallel.response.size_bytes",
                    value=response_size_bytes,
                    metric_type=MetricType.HISTOGRAM,
                    labels=labels,
                )

            # Calculate and record error rate
            if not success:
                await self._record_metric(
                    name="parallel.errors.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels=labels,
                )

        except Exception as e:
            logger.error(f"Failed to track Parallel API call metrics: {e}")

    async def _record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Internal method to record metrics."""
        if self.storage:
            # Use injected storage
            await record_metric(
                name=name,
                value=value,
                labels=labels,
                metric_type=metric_type,
                storage=self.storage,
            )
        else:
            # Log metric for now (would integrate with global storage)
            logger.info(
                f"Metric: {name}={value} {metric_type.value} {labels or {}}"
            )


# Instrumented wrapper for assert_parallel_safe
async def instrumented_assert_parallel_safe(
    data: Dict,
    context: Optional[str] = None,
    collector: Optional[ParallelObservabilityCollector] = None,
) -> None:
    """
    Instrumented version of assert_parallel_safe that tracks metrics.
    
    Args:
        data: Data payload to validate
        context: Optional context
        collector: Optional metrics collector
    """
    from .core import contains_pii
    from .shell import assert_parallel_safe
    
    start_time = datetime.utcnow()
    payload_size = len(str(data))
    
    with TrackedOperation("pii_boundary_check", tracer) as span:
        span.add_attribute("payload_size", payload_size)
        span.add_attribute("context", context or "unknown")
        
        try:
            # First do PII detection for metrics
            text_content = str(data)  # Simplified extraction
            has_pii, pii_matches = contains_pii(text_content)
            
            # Calculate duration
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Track metrics
            if collector:
                await collector.track_pii_detection(
                    duration_ms=duration_ms,
                    has_pii=has_pii,
                    payload_size=payload_size,
                    pattern_count=len(pii_matches),
                    context=context,
                )
            
            # Call actual validation (will raise if PII detected)
            await assert_parallel_safe(data, context)
            
            span.add_attribute("pii_detected", has_pii)
            span.add_attribute("pattern_count", len(pii_matches))
            
        except Exception as e:
            span.add_attribute("error", str(e))
            
            # Still track metrics for failed checks
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if collector:
                await collector.track_pii_detection(
                    duration_ms=duration_ms,
                    has_pii=True,  # Assume PII if validation failed
                    payload_size=payload_size,
                    pattern_count=1,  # At least one pattern detected
                    context=context,
                )
            
            raise


# Instrumented circuit breaker wrapper
class InstrumentedCircuitBreaker:
    """
    Wrapper around circuit breaker that tracks metrics.
    """

    def __init__(self, guard, collector: Optional[ParallelObservabilityCollector] = None):
        self.guard = guard
        self.collector = collector

    async def execute_with_metrics(
        self,
        func,
        service_name: str = "parallel_ai",
        endpoint: str = "unknown",
        *args,
        **kwargs,
    ):
        """
        Execute function with circuit breaker and metrics tracking.
        
        Args:
            func: Function to execute
            service_name: Service name for circuit breaker
            endpoint: API endpoint for metrics
            *args, **kwargs: Function arguments
        """
        start_time = datetime.utcnow()
        
        with TrackedOperation(f"parallel_api_call_{endpoint}", tracer) as span:
            span.add_attribute("service", service_name)
            span.add_attribute("endpoint", endpoint)
            
            try:
                # Get circuit breaker status before call
                status = await self.guard.get_circuit_status(service_name)
                
                # Track circuit breaker state
                if self.collector:
                    await self.collector.track_circuit_breaker_state(
                        service_name=service_name,
                        state=status.state.value,
                        failure_count=status.failure_count,
                        success_rate=status.successful_requests / max(status.total_requests, 1),
                    )
                
                # Execute with circuit breaker
                result = await self.guard.circuit_breaker_call(
                    func, service_name, *args, **kwargs
                )
                
                # Calculate duration and cost
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                cost_euros = getattr(result, "cost_euros", 0.0) or result.get("cost_euros", 0.0) if isinstance(result, dict) else 0.0
                
                # Track successful API call
                if self.collector:
                    await self.collector.track_parallel_api_call(
                        endpoint=endpoint,
                        duration_ms=duration_ms,
                        success=True,
                        cost_euros=cost_euros,
                        payload_size_bytes=len(str(args[0]) if args else "{}"),
                        response_size_bytes=len(str(result)),
                    )
                
                span.add_attribute("success", True)
                span.add_attribute("duration_ms", duration_ms)
                span.add_attribute("cost_euros", cost_euros)
                
                return result
                
            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                error_type = type(e).__name__
                
                # Track failed API call
                if self.collector:
                    await self.collector.track_parallel_api_call(
                        endpoint=endpoint,
                        duration_ms=duration_ms,
                        success=False,
                        error_type=error_type,
                        payload_size_bytes=len(str(args[0]) if args else "{}"),
                    )
                
                span.add_attribute("success", False)
                span.add_attribute("error_type", error_type)
                span.add_attribute("duration_ms", duration_ms)
                
                raise


# Global collector instance
_global_collector: Optional[ParallelObservabilityCollector] = None


def initialize_parallel_observability(storage=None) -> ParallelObservabilityCollector:
    """Initialize global parallel observability collector."""
    global _global_collector
    _global_collector = ParallelObservabilityCollector(storage)
    return _global_collector


def get_global_collector() -> Optional[ParallelObservabilityCollector]:
    """Get the global parallel observability collector."""
    return _global_collector