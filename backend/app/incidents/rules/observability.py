"""
Observability integration for Incidents Rules module.
Collects metrics for DORA incident classification, deadline calculation, and DST handling.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from ...observability.contracts import MetricType
from ...observability.core import create_metric
from ...observability.integration import get_tracer, TrackedOperation
from ...observability.shell import record_metric
from .contracts import Severity, DeadlineCalculation

logger = logging.getLogger(__name__)

# Get tracer for this module
tracer = get_tracer("regops.incidents.rules")


class IncidentsObservabilityCollector:
    """
    Collects observability metrics for the incidents rules module.
    Integrates with DORA classification and deadline calculation.
    """

    def __init__(self, storage=None):
        self.storage = storage

    async def track_incident_classification(
        self,
        incident_id: str,
        duration_ms: float,
        severity: Severity,
        clients_affected: int,
        downtime_minutes: int,
        services_critical: List[str],
        anchor_source: str,
        classification_reasons: List[str],
        requires_notification: bool,
    ) -> None:
        """
        Track incident classification metrics.

        Args:
            incident_id: Incident identifier
            duration_ms: Time taken for classification (<10ms target)
            severity: Classified severity level
            clients_affected: Number of clients affected
            downtime_minutes: Duration of downtime
            services_critical: List of critical services affected
            anchor_source: Source of anchor timestamp
            classification_reasons: Reasons for classification
            requires_notification: Whether notification is required
        """
        try:
            labels = {
                "severity": severity.value,
                "anchor_source": anchor_source,
                "requires_notification": str(requires_notification).lower(),
            }

            # Record classification duration (SLO: <10ms)
            await self._record_metric(
                name="incidents.classification.duration_ms",
                value=duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record incident severity distribution
            await self._record_metric(
                name="incidents.classified.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record DORA classification metrics by severity
            severity_counter_labels = {"severity": severity.value}
            await self._record_metric(
                name="dora.incidents.by_severity.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=severity_counter_labels,
            )

            # Record business impact metrics
            await self._record_metric(
                name="incidents.clients_affected",
                value=clients_affected,
                metric_type=MetricType.HISTOGRAM,
                labels={"severity": severity.value},
            )

            await self._record_metric(
                name="incidents.downtime_minutes",
                value=downtime_minutes,
                metric_type=MetricType.HISTOGRAM,
                labels={"severity": severity.value},
            )

            # Record critical services count
            await self._record_metric(
                name="incidents.critical_services_affected",
                value=len(services_critical),
                metric_type=MetricType.HISTOGRAM,
                labels={"severity": severity.value},
            )

            # Track notifications required (business metric)
            if requires_notification:
                await self._record_metric(
                    name="dora.notifications.required.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels={"severity": severity.value},
                )

        except Exception as e:
            logger.error(f"Failed to track incident classification metrics: {e}")

    async def track_deadline_calculation(
        self,
        incident_id: str,
        duration_ms: float,
        severity: Severity,
        anchor_time: datetime,
        dst_transitions_handled: List[str],
        calculation_confidence: float,
        timezone_used: str,
    ) -> None:
        """
        Track deadline calculation metrics.

        Args:
            incident_id: Incident identifier
            duration_ms: Time taken for calculation (<50ms target)
            severity: Incident severity
            anchor_time: Anchor timestamp used
            dst_transitions_handled: List of DST transitions handled
            calculation_confidence: Confidence in calculation (0.0-1.0)
            timezone_used: Timezone used for calculations
        """
        try:
            labels = {
                "severity": severity.value,
                "timezone": timezone_used,
                "dst_transitions": str(len(dst_transitions_handled)),
            }

            # Record deadline calculation duration (SLO: <50ms)
            await self._record_metric(
                name="incidents.deadline_calculation.duration_ms",
                value=duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record deadline calculations completed
            await self._record_metric(
                name="incidents.deadlines.calculated.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record calculation confidence
            await self._record_metric(
                name="incidents.deadline_calculation.confidence",
                value=calculation_confidence,
                metric_type=MetricType.HISTOGRAM,
                labels={"severity": severity.value},
            )

            # Track DST handling (critical for compliance)
            if dst_transitions_handled:
                await self._record_metric(
                    name="incidents.dst_transitions.handled.total",
                    value=len(dst_transitions_handled),
                    metric_type=MetricType.COUNTER,
                    labels={"timezone": timezone_used},
                )

                # Track specific DST transition types
                for transition in dst_transitions_handled:
                    transition_type = transition.split("_")[0] if "_" in transition else transition
                    await self._record_metric(
                        name="incidents.dst_transitions.by_type.total",
                        value=1.0,
                        metric_type=MetricType.COUNTER,
                        labels={"type": transition_type, "timezone": timezone_used},
                    )

        except Exception as e:
            logger.error(f"Failed to track deadline calculation metrics: {e}")

    async def track_clock_validation(
        self,
        incident_id: str,
        validation_duration_ms: float,
        is_valid: bool,
        error_type: Optional[str] = None,
        anchor_source: str = "unknown",
    ) -> None:
        """
        Track clock anchor validation metrics.

        Args:
            incident_id: Incident identifier
            validation_duration_ms: Time taken for validation
            is_valid: Whether the clock anchor is valid
            error_type: Type of validation error if any
            anchor_source: Source of the timestamp
        """
        try:
            labels = {
                "valid": str(is_valid).lower(),
                "anchor_source": anchor_source,
            }

            if error_type:
                labels["error_type"] = error_type

            # Record clock validation duration
            await self._record_metric(
                name="incidents.clock_validation.duration_ms",
                value=validation_duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record validation results
            await self._record_metric(
                name="incidents.clock_validations.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Track clock validation failures (critical compliance metric)
            if not is_valid:
                await self._record_metric(
                    name="incidents.clock_validation.failures.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels={"error_type": error_type or "unknown", "anchor_source": anchor_source},
                )

        except Exception as e:
            logger.error(f"Failed to track clock validation metrics: {e}")

    async def track_deadline_miss(
        self,
        incident_id: str,
        deadline_type: str,  # "initial", "intermediate", "final", "nbb"
        severity: Severity,
        deadline_time: datetime,
        missed_by_minutes: float,
        notification_sent: bool = False,
    ) -> None:
        """
        Track deadline miss events (critical compliance metric).

        Args:
            incident_id: Incident identifier
            deadline_type: Type of deadline missed
            severity: Incident severity
            deadline_time: Original deadline time
            missed_by_minutes: How many minutes the deadline was missed by
            notification_sent: Whether notification was eventually sent
        """
        try:
            labels = {
                "deadline_type": deadline_type,
                "severity": severity.value,
                "notification_sent": str(notification_sent).lower(),
            }

            # Record deadline miss (critical business metric)
            await self._record_metric(
                name="clock.deadline.miss.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record how much the deadline was missed by
            await self._record_metric(
                name="clock.deadline.miss.minutes",
                value=missed_by_minutes,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track DORA compliance violations
            await self._record_metric(
                name="dora.compliance.violations.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels={"violation_type": "deadline_miss", "severity": severity.value},
            )

        except Exception as e:
            logger.error(f"Failed to track deadline miss metrics: {e}")

    async def track_notification_scheduling(
        self,
        incident_id: str,
        notification_type: str,
        severity: Severity,
        deadline: datetime,
        scheduling_duration_ms: float,
        success: bool,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Track notification scheduling metrics.

        Args:
            incident_id: Incident identifier
            notification_type: Type of notification ("initial", "intermediate", "final", "nbb")
            severity: Incident severity
            deadline: Notification deadline
            scheduling_duration_ms: Time taken to schedule
            success: Whether scheduling succeeded
            error_message: Error message if scheduling failed
        """
        try:
            labels = {
                "notification_type": notification_type,
                "severity": severity.value,
                "success": str(success).lower(),
            }

            # Record notification scheduling attempts
            await self._record_metric(
                name="incidents.notifications.scheduled.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record scheduling duration
            await self._record_metric(
                name="incidents.notification_scheduling.duration_ms",
                value=scheduling_duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track failures
            if not success:
                await self._record_metric(
                    name="incidents.notification_scheduling.failures.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels={**labels, "error": error_message or "unknown"},
                )

        except Exception as e:
            logger.error(f"Failed to track notification scheduling metrics: {e}")

    async def track_classification_accuracy(
        self,
        incident_id: str,
        predicted_severity: Severity,
        actual_severity: Optional[Severity] = None,
        confidence_score: float = 1.0,
    ) -> None:
        """
        Track classification accuracy metrics (for ML/validation purposes).

        Args:
            incident_id: Incident identifier
            predicted_severity: Severity predicted by algorithm
            actual_severity: Actual severity (if available from audit)
            confidence_score: Confidence in prediction (0.0-1.0)
        """
        try:
            labels = {"predicted_severity": predicted_severity.value}

            if actual_severity:
                labels["actual_severity"] = actual_severity.value
                is_correct = predicted_severity == actual_severity
                labels["correct"] = str(is_correct).lower()

                # Record accuracy
                await self._record_metric(
                    name="incidents.classification.accuracy",
                    value=1.0 if is_correct else 0.0,
                    metric_type=MetricType.GAUGE,
                    labels=labels,
                )

            # Record confidence scores
            await self._record_metric(
                name="incidents.classification.confidence",
                value=confidence_score,
                metric_type=MetricType.HISTOGRAM,
                labels={"predicted_severity": predicted_severity.value},
            )

        except Exception as e:
            logger.error(f"Failed to track classification accuracy metrics: {e}")

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


# Instrumented wrapper for incident classification
class InstrumentedIncidentClassifier:
    """
    Wrapper around incident classification that tracks metrics.
    """

    def __init__(self, collector: Optional[IncidentsObservabilityCollector] = None):
        self.collector = collector

    async def classify_and_persist_with_metrics(self, incident_id: str):
        """
        Classify incident and persist with comprehensive metrics tracking.
        """
        from .shell import classify_and_persist
        from .core import classify_incident_severity, determine_anchor_timestamp, calculate_deadlines

        start_time = datetime.utcnow()

        with TrackedOperation("incident_classification", tracer) as span:
            span.add_attribute("incident_id", incident_id)

            try:
                # Load incident data for metrics
                from .shell import _load_incident_data
                incident_data = await _load_incident_data(incident_id)
                
                if not hasattr(incident_data, 'value'):
                    raise Exception("Failed to load incident data")
                
                incident = incident_data.value

                # Track clock validation
                clock_start = datetime.utcnow()
                anchor_result = determine_anchor_timestamp(
                    incident.detected_at, incident.confirmed_at, incident.occurred_at
                )
                clock_duration = (datetime.utcnow() - clock_start).total_seconds() * 1000

                if self.collector:
                    await self.collector.track_clock_validation(
                        incident_id=incident_id,
                        validation_duration_ms=clock_duration,
                        is_valid=not isinstance(anchor_result, Exception),
                        error_type=None if not isinstance(anchor_result, Exception) else "missing_timestamps",
                        anchor_source="detected_at" if incident.detected_at else "confirmed_at" if incident.confirmed_at else "occurred_at",
                    )

                # Perform actual classification
                classification_start = datetime.utcnow()
                result = await classify_and_persist(incident_id)
                classification_duration = (datetime.utcnow() - classification_start).total_seconds() * 1000

                if hasattr(result, 'value'):
                    classification_result = result.value
                    
                    # Track classification metrics
                    if self.collector:
                        await self.collector.track_incident_classification(
                            incident_id=incident_id,
                            duration_ms=classification_duration,
                            severity=classification_result.severity,
                            clients_affected=incident.clients_affected,
                            downtime_minutes=incident.downtime_minutes,
                            services_critical=list(incident.services_critical),
                            anchor_source=classification_result.anchor_source,
                            classification_reasons=list(classification_result.classification_reasons),
                            requires_notification=classification_result.requires_notification,
                        )

                        # Track deadline calculation if deadlines were calculated
                        if classification_result.deadlines:
                            await self.collector.track_deadline_calculation(
                                incident_id=incident_id,
                                duration_ms=classification_duration,  # Approximation
                                severity=classification_result.severity,
                                anchor_time=classification_result.anchor_timestamp,
                                dst_transitions_handled=list(classification_result.deadlines.dst_transitions_handled),
                                calculation_confidence=classification_result.deadlines.calculation_confidence,
                                timezone_used=classification_result.deadlines.timezone_used,
                            )

                    span.add_attribute("severity", classification_result.severity.value)
                    span.add_attribute("requires_notification", classification_result.requires_notification)
                    span.add_attribute("clients_affected", incident.clients_affected)
                    span.add_attribute("downtime_minutes", incident.downtime_minutes)

                total_duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                span.add_attribute("total_duration_ms", total_duration)

                return result

            except Exception as e:
                total_duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                span.add_attribute("error", str(e))
                span.add_attribute("total_duration_ms", total_duration)
                raise


# Global collector instance
_global_collector: Optional[IncidentsObservabilityCollector] = None


def initialize_incidents_observability(storage=None) -> IncidentsObservabilityCollector:
    """Initialize global incidents observability collector."""
    global _global_collector
    _global_collector = IncidentsObservabilityCollector(storage)
    return _global_collector


def get_global_collector() -> Optional[IncidentsObservabilityCollector]:
    """Get the global incidents observability collector."""
    return _global_collector