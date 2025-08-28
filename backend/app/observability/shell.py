"""
Observability Shell - I/O Operations Only
ALL I/O operations for observability: Redis, database, alerts, external APIs.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
import redis.asyncio as redis
from opentelemetry import metrics, trace

from .contracts import (
    Alert,
    AlertOperator,
    AlertRule,
    DashboardConfig,
    Failure,
    Metric,
    MetricType,
    PerformanceTarget,
    Result,
    SLODefinition,
    SLOStatus,
    Severity,
    Success,
)
from .core import (
    calculate_slo_compliance,
    create_standard_alert_rules,
    get_performance_targets,
    should_trigger_alert,
)
from .events import (
    AlertTriggered,
    DashboardUpdateRequired,
    MetricCollectionFailed,
    MetricRecorded,
    PerformanceThresholdExceeded,
    SecurityMetricViolation,
    SLOViolated,
)

logger = logging.getLogger(__name__)

# OpenTelemetry setup
meter = metrics.get_meter("regops.observability")
tracer = trace.get_tracer("regops.observability")

# Global metrics
metric_recording_duration = meter.create_histogram(
    "observability.recording.duration_ms",
    description="Time taken to record a metric",
    unit="milliseconds",
)

alert_evaluation_duration = meter.create_histogram(
    "observability.alert_evaluation.duration_ms", 
    description="Time taken to evaluate alert rules",
    unit="milliseconds",
)


class ObservabilityStorage:
    """
    Storage operations for observability data.
    Uses Redis for real-time metrics and PostgreSQL for historical data.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        database_url: str,
        tenant: Optional[str] = None,
    ):
        self.redis = redis_client
        self.database_url = database_url
        self.tenant = tenant or "default"
        self.alert_rules: List[AlertRule] = []

    async def initialize(self) -> None:
        """Initialize storage and load alert rules."""
        self.alert_rules = create_standard_alert_rules()
        await self._load_custom_alert_rules()

    async def record_metric(
        self,
        metric: Metric,
        emit_events: bool = True,
    ) -> Result[None, str]:
        """
        Record metric to Redis and emit events.
        
        Args:
            metric: Validated metric to record
            emit_events: Whether to emit MetricRecorded event
            
        Returns:
            Result indicating success or failure
        """
        start_time = datetime.utcnow()
        
        try:
            with tracer.start_as_current_span("record_metric") as span:
                span.set_attributes({
                    "metric.name": metric.name,
                    "metric.type": metric.metric_type.value,
                    "tenant": self.tenant,
                })

                # Store in Redis for real-time access
                redis_key = f"metrics:{self.tenant}:{metric.name}"
                metric_data = {
                    "value": metric.value,
                    "labels": metric.labels,
                    "timestamp": metric.timestamp.isoformat(),
                    "type": metric.metric_type.value,
                    "unit": metric.unit,
                }

                # Use Redis pipeline for atomic operations
                async with self.redis.pipeline() as pipe:
                    # Store current value
                    await pipe.hset(redis_key, mapping=metric_data)
                    
                    # Add to time series for historical data
                    ts_key = f"timeseries:{self.tenant}:{metric.name}"
                    await pipe.zadd(
                        ts_key,
                        {json.dumps(metric_data): metric.timestamp.timestamp()}
                    )
                    
                    # Expire time series after 7 days
                    await pipe.expire(ts_key, 7 * 24 * 3600)
                    
                    await pipe.execute()

                # Evaluate alerts
                await self._evaluate_alerts_for_metric(metric)

                # Emit event if requested
                if emit_events:
                    await self._emit_event(
                        MetricRecorded(
                            metric=metric,
                            recorded_at=datetime.utcnow(),
                            tenant=self.tenant,
                        )
                    )

                # Record observability metrics
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                metric_recording_duration.record(
                    duration_ms,
                    {"metric_name": metric.name, "tenant": self.tenant}
                )

                return Success(None)

        except Exception as e:
            logger.error(f"Failed to record metric {metric.name}: {e}", exc_info=True)
            
            await self._emit_event(
                MetricCollectionFailed(
                    metric_name=metric.name,
                    error_message=str(e),
                    failed_at=datetime.utcnow(),
                    retry_count=0,
                    tenant=self.tenant,
                )
            )
            
            return Failure(f"Failed to record metric: {e}")

    async def get_metric_value(
        self,
        metric_name: str,
        time_window: Optional[timedelta] = None,
    ) -> Result[Optional[float], str]:
        """
        Get current or aggregated metric value.
        
        Args:
            metric_name: Name of metric to retrieve
            time_window: Optional time window for aggregation
            
        Returns:
            Result containing metric value or error
        """
        try:
            if time_window is None:
                # Get current value
                redis_key = f"metrics:{self.tenant}:{metric_name}"
                value_str = await self.redis.hget(redis_key, "value")
                
                if value_str is None:
                    return Success(None)
                    
                return Success(float(value_str))
            else:
                # Get aggregated value over time window
                return await self._get_aggregated_metric(metric_name, time_window)
                
        except Exception as e:
            logger.error(f"Failed to get metric {metric_name}: {e}")
            return Failure(f"Failed to retrieve metric: {e}")

    async def get_slo_status(
        self,
        slo_definition: SLODefinition,
    ) -> Result[SLOStatus, str]:
        """
        Get current SLO compliance status.
        
        Args:
            slo_definition: SLO definition to evaluate
            
        Returns:
            Result containing SLO status or error
        """
        try:
            # Extract metric name from SLO (assuming it's in the definition)
            metric_result = await self.get_metric_value(
                slo_definition.name,
                slo_definition.time_window,
            )
            
            if isinstance(metric_result, Failure):
                return Failure(f"Failed to get SLO metric: {metric_result.error}")
            
            current_value = metric_result.value or 0.0
            
            # Calculate compliance
            compliance_percent = calculate_slo_compliance(
                slo_definition.target_value,
                current_value,
                slo_definition.operator,
            )
            
            is_violated = compliance_percent < 95.0  # 95% compliance threshold
            
            slo_status = SLOStatus(
                definition=slo_definition,
                current_value=current_value,
                compliance_percent=compliance_percent,
                is_violated=is_violated,
                last_evaluation=datetime.utcnow(),
            )
            
            # Emit violation event if needed
            if is_violated:
                await self._emit_event(
                    SLOViolated(
                        slo_status=slo_status,
                        violated_at=datetime.utcnow(),
                        compliance_percent=compliance_percent,
                        tenant=self.tenant,
                    )
                )
            
            return Success(slo_status)
            
        except Exception as e:
            logger.error(f"Failed to get SLO status for {slo_definition.name}: {e}")
            return Failure(f"Failed to evaluate SLO: {e}")

    async def emit_alert(
        self,
        alert: Alert,
        channels: Optional[List[str]] = None,
    ) -> Result[None, str]:
        """
        Emit alert via configured channels (Teams, email, etc.).
        
        Args:
            alert: Alert to emit
            channels: Optional list of channels to use
            
        Returns:
            Result indicating success or failure
        """
        try:
            # Default channels
            default_channels = ["redis", "log"]
            active_channels = channels or default_channels
            
            for channel in active_channels:
                if channel == "redis":
                    await self._emit_alert_to_redis(alert)
                elif channel == "log":
                    await self._emit_alert_to_log(alert)
                elif channel == "teams":
                    await self._emit_alert_to_teams(alert)
                elif channel == "email":
                    await self._emit_alert_to_email(alert)
            
            # Emit event
            await self._emit_event(
                AlertTriggered(
                    alert=alert,
                    triggered_at=datetime.utcnow(),
                    tenant=self.tenant,
                )
            )
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to emit alert: {e}", exc_info=True)
            return Failure(f"Failed to emit alert: {e}")

    async def _evaluate_alerts_for_metric(self, metric: Metric) -> None:
        """Evaluate all alert rules for the given metric."""
        start_time = datetime.utcnow()
        
        try:
            matching_rules = [
                rule for rule in self.alert_rules
                if rule.metric_name == metric.name
            ]
            
            for rule in matching_rules:
                should_alert = should_trigger_alert(
                    metric.value,
                    rule.threshold,
                    rule.operator,
                )
                
                if should_alert:
                    alert = Alert(
                        rule=rule,
                        current_value=metric.value,
                        message=rule.message_template.format(value=metric.value),
                        timestamp=datetime.utcnow(),
                        labels=metric.labels,
                    )
                    
                    await self.emit_alert(alert)
                    
                    # Check for security violations
                    if rule.severity == Severity.CRITICAL and "pii" in rule.metric_name.lower():
                        await self._emit_event(
                            SecurityMetricViolation(
                                metric_name=metric.name,
                                violation_type="pii_detected",
                                current_value=metric.value,
                                threshold=rule.threshold,
                                severity=rule.severity,
                                violated_at=datetime.utcnow(),
                                details={"alert_message": alert.message},
                                tenant=self.tenant,
                            )
                        )
            
            # Record evaluation performance
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            alert_evaluation_duration.record(
                duration_ms,
                {"metric_name": metric.name, "tenant": self.tenant}
            )
            
        except Exception as e:
            logger.error(f"Failed to evaluate alerts for {metric.name}: {e}")

    async def _get_aggregated_metric(
        self,
        metric_name: str,
        time_window: timedelta,
    ) -> Result[Optional[float], str]:
        """Get aggregated metric value over time window."""
        try:
            ts_key = f"timeseries:{self.tenant}:{metric_name}"
            now = datetime.utcnow()
            start_time = now - time_window
            
            # Get values in time window
            results = await self.redis.zrangebyscore(
                ts_key,
                start_time.timestamp(),
                now.timestamp(),
                withscores=True,
            )
            
            if not results:
                return Success(None)
            
            # Parse values and calculate average
            values = []
            for data_json, timestamp in results:
                try:
                    data = json.loads(data_json)
                    values.append(float(data["value"]))
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue
            
            if not values:
                return Success(None)
                
            # Return average for now (could be configurable)
            avg_value = sum(values) / len(values)
            return Success(avg_value)
            
        except Exception as e:
            return Failure(f"Failed to get aggregated metric: {e}")

    async def _load_custom_alert_rules(self) -> None:
        """Load custom alert rules from Redis."""
        try:
            rules_key = f"alert_rules:{self.tenant}"
            rules_data = await self.redis.get(rules_key)
            
            if rules_data:
                custom_rules = json.loads(rules_data)
                # Parse and add to alert_rules list
                # Implementation would depend on storage format
                pass
                
        except Exception as e:
            logger.warning(f"Failed to load custom alert rules: {e}")

    async def _emit_event(self, event) -> None:
        """Emit domain event (placeholder for event bus integration)."""
        # In a real implementation, this would publish to event bus
        logger.info(f"Event emitted: {type(event).__name__}")

    async def _emit_alert_to_redis(self, alert: Alert) -> None:
        """Store alert in Redis for dashboard consumption."""
        alert_key = f"alerts:{self.tenant}:{alert.timestamp.isoformat()}"
        alert_data = {
            "metric_name": alert.rule.metric_name,
            "severity": alert.rule.severity.value,
            "message": alert.message,
            "threshold": alert.rule.threshold,
            "current_value": alert.current_value,
            "timestamp": alert.timestamp.isoformat(),
            "labels": json.dumps(alert.labels),
        }
        
        await self.redis.hset(alert_key, mapping=alert_data)
        await self.redis.expire(alert_key, 7 * 24 * 3600)  # Expire after 7 days

    async def _emit_alert_to_log(self, alert: Alert) -> None:
        """Emit alert to application logs."""
        log_level = logging.CRITICAL if alert.rule.severity == Severity.CRITICAL else logging.WARNING
        logger.log(
            log_level,
            f"ALERT: {alert.rule.severity.value.upper()} - {alert.message} "
            f"(metric: {alert.rule.metric_name}, value: {alert.current_value})"
        )

    async def _emit_alert_to_teams(self, alert: Alert) -> None:
        """Emit alert to Microsoft Teams (placeholder)."""
        # Implementation would depend on Teams webhook setup
        logger.info(f"Teams alert: {alert.message}")

    async def _emit_alert_to_email(self, alert: Alert) -> None:
        """Emit alert via email (placeholder).""" 
        # Implementation would depend on email service setup
        logger.info(f"Email alert: {alert.message}")


class PerformanceTracker:
    """
    Performance tracking for SLO monitoring.
    """

    def __init__(self, storage: ObservabilityStorage):
        self.storage = storage
        self.targets = get_performance_targets()

    async def track_operation_duration(
        self,
        operation: str,
        duration_ms: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> Result[None, str]:
        """
        Track operation duration and check against targets.
        
        Args:
            operation: Operation name (must match PerformanceTarget)
            duration_ms: Duration in milliseconds
            labels: Optional additional labels
            
        Returns:
            Result indicating success or failure
        """
        try:
            # Find matching target
            target = next(
                (t for t in self.targets if t.operation == operation),
                None
            )
            
            if not target:
                logger.warning(f"No performance target defined for operation: {operation}")
                return Failure(f"No target defined for operation: {operation}")
            
            # Record metric
            metric_name = f"{operation}.duration_ms"
            from .core import create_metric
            
            metric_result = create_metric(
                name=metric_name,
                value=duration_ms,
                labels=labels or {},
                metric_type=MetricType.HISTOGRAM,
                timestamp=datetime.utcnow(),
                unit="milliseconds",
            )
            
            if isinstance(metric_result, Failure):
                return Failure(f"Failed to create performance metric: {metric_result.error}")
            
            await self.storage.record_metric(metric_result.value, emit_events=True)
            
            # Check if threshold exceeded
            if duration_ms > target.target_ms:
                await self.storage._emit_event(
                    PerformanceThresholdExceeded(
                        operation=operation,
                        actual_duration_ms=duration_ms,
                        target_duration_ms=target.target_ms,
                        percentile=target.percentile,
                        exceeded_at=datetime.utcnow(),
                        tenant=self.storage.tenant,
                    )
                )
            
            return Success(None)
            
        except Exception as e:
            logger.error(f"Failed to track performance for {operation}: {e}")
            return Failure(f"Failed to track performance: {e}")


# Convenience function for easy metric recording
async def record_metric(
    name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
    metric_type: MetricType = MetricType.GAUGE,
    storage: Optional[ObservabilityStorage] = None,
) -> Result[None, str]:
    """
    Convenience function to record a metric.
    
    Args:
        name: Metric name
        value: Metric value  
        labels: Optional labels
        metric_type: Type of metric
        storage: Optional storage instance (uses default if None)
        
    Returns:
        Result indicating success or failure
    """
    from .core import create_metric
    
    metric_result = create_metric(
        name=name,
        value=value,
        labels=labels or {},
        metric_type=metric_type,
        timestamp=datetime.utcnow(),
    )
    
    if isinstance(metric_result, Failure):
        return Failure(f"Invalid metric: {metric_result.error}")
    
    if storage is None:
        # Would need global storage instance in real implementation
        logger.warning("No storage instance provided for metric recording")
        return Failure("No storage instance available")
    
    return await storage.record_metric(metric_result.value)