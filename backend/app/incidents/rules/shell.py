"""I/O operations for incident classification and deadline scheduling."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Any

from .core import (
    classify_incident_severity,
    determine_anchor_timestamp,
    calculate_deadlines,
    validate_clock_anchor,
    BRUSSELS_TZ,
)
from .contracts import (
    IncidentInput,
    ClassificationResult,
    DeadlineCalculation,
    Severity,
    Success,
    Failure,
    Result,
)
from .events import (
    IncidentClassified,
    DeadlineScheduled,
    DSTTransitionHandled,
    InvalidClockAnchor,
)


class IncidentClassificationError(Exception):
    """Exception for incident classification errors."""

    pass


class DeadlineSchedulingError(Exception):
    """Exception for deadline scheduling errors."""

    pass


async def classify_and_persist(incident_id: str) -> Result[ClassificationResult, str]:
    """
    Load incident data, classify according to DORA rules, persist results, and emit events.

    This is the main entry point for incident classification workflow.
    """
    try:
        # Step 1: Load incident data
        incident_data = await _load_incident_data(incident_id)
        if isinstance(incident_data, Failure):
            return incident_data

        incident = incident_data.value

        # Step 2: Determine anchor timestamp using fallback chain
        anchor_result = determine_anchor_timestamp(
            incident.detected_at, incident.confirmed_at, incident.occurred_at
        )

        if isinstance(anchor_result, Failure):
            await _emit_event(
                InvalidClockAnchor(
                    incident_id=incident_id,
                    invalid_timestamp=datetime.now(timezone.utc),
                    error_type="missing_timestamps",
                    suggested_correction=None,
                    detected_at=datetime.now(timezone.utc),
                )
            )
            return Failure(f"Invalid timestamps: {anchor_result.error}")

        anchor_timestamp, anchor_source = anchor_result.value

        # Step 3: Validate clock anchor
        validation = validate_clock_anchor(anchor_timestamp, BRUSSELS_TZ)
        if not validation.valid:
            await _emit_event(
                InvalidClockAnchor(
                    incident_id=incident_id,
                    invalid_timestamp=validation.timestamp,
                    error_type=validation.error_type,
                    suggested_correction=validation.suggested_time,
                    detected_at=datetime.now(timezone.utc),
                )
            )

            if validation.suggested_time:
                anchor_timestamp = validation.suggested_time
            else:
                return Failure(f"Invalid clock anchor: {validation.error_message}")

        # Step 4: Classify incident severity
        severity = classify_incident_severity(
            clients_affected=incident.clients_affected,
            downtime_minutes=incident.downtime_minutes,
            services_critical=incident.services_critical,
        )

        # Step 5: Calculate deadlines (if reporting required)
        deadlines = None
        if severity != Severity.NO_REPORT:
            deadline_result = calculate_deadlines(
                anchor_timestamp, severity, BRUSSELS_TZ
            )
            if isinstance(deadline_result, Failure):
                return Failure(f"Deadline calculation failed: {deadline_result.error}")

            deadlines = deadline_result.value
            deadlines = DeadlineCalculation(
                incident_id=incident_id,
                severity=deadlines.severity,
                anchor_time_utc=deadlines.anchor_time_utc,
                anchor_time_brussels=deadlines.anchor_time_brussels,
                initial_notification=deadlines.initial_notification,
                intermediate_report=deadlines.intermediate_report,
                final_report=deadlines.final_report,
                nbb_notification=deadlines.nbb_notification,
                dst_transitions_handled=deadlines.dst_transitions_handled,
                calculation_confidence=deadlines.calculation_confidence,
                timezone_used=deadlines.timezone_used,
            )

        # Step 6: Build classification result
        classification_reasons = _build_classification_reasons(incident, severity)
        requires_notification = severity in [
            Severity.CRITICAL,
            Severity.MAJOR,
            Severity.SIGNIFICANT,
        ]
        notification_hours = _get_notification_deadline_hours(severity)

        result = ClassificationResult(
            incident_id=incident_id,
            severity=severity,
            anchor_timestamp=anchor_timestamp,
            anchor_source=anchor_source,
            classification_reasons=classification_reasons,
            deadlines=deadlines,
            requires_notification=requires_notification,
            notification_deadline_hours=notification_hours,
        )

        # Step 7: Persist to database
        await _persist_classification(result)

        # Step 8: Emit domain events
        await _emit_incident_classified_event(result)

        if deadlines:
            await _emit_deadline_scheduled_event(deadlines)

            # Emit DST transition events if any were handled
            for transition in deadlines.dst_transitions_handled:
                await _emit_event(
                    DSTTransitionHandled(
                        incident_id=incident_id,
                        transition_type=transition,
                        anchor_time=anchor_timestamp,
                        adjusted_time=deadlines.initial_notification,
                        handled_at=datetime.now(timezone.utc),
                    )
                )

        return Success(result)

    except Exception as e:
        error_msg = f"Classification failed for incident {incident_id}: {str(e)}"
        await _log_error(error_msg, incident_id)
        return Failure(error_msg)


async def schedule_notifications(
    incident_id: str, deadlines: DeadlineCalculation
) -> Result[None, str]:
    """Schedule DORA notification deadlines using external notification service."""
    try:
        # Schedule initial notification
        if deadlines.initial_notification:
            await _schedule_notification(
                incident_id=incident_id,
                notification_type="initial",
                deadline=deadlines.initial_notification,
                severity=deadlines.severity,
            )

        # Schedule intermediate report (if applicable)
        if deadlines.intermediate_report:
            await _schedule_notification(
                incident_id=incident_id,
                notification_type="intermediate",
                deadline=deadlines.intermediate_report,
                severity=deadlines.severity,
            )

        # Schedule final report
        if deadlines.final_report:
            await _schedule_notification(
                incident_id=incident_id,
                notification_type="final",
                deadline=deadlines.final_report,
                severity=deadlines.severity,
            )

        # Schedule NBB notification (if applicable)
        if deadlines.nbb_notification:
            await _schedule_notification(
                incident_id=incident_id,
                notification_type="nbb",
                deadline=deadlines.nbb_notification,
                severity=deadlines.severity,
            )

        return Success(None)

    except Exception as e:
        error_msg = (
            f"Notification scheduling failed for incident {incident_id}: {str(e)}"
        )
        await _log_error(error_msg, incident_id)
        return Failure(error_msg)


async def get_current_brussels_time() -> datetime:
    """Get current Brussels time with timezone info."""
    return datetime.now(BRUSSELS_TZ)


# Private helper functions


async def _load_incident_data(incident_id: str) -> Result[IncidentInput, str]:
    """Load incident data from database."""
    # This would integrate with actual database
    # For now, return a mock for testing
    mock_incident = IncidentInput(
        incident_id=incident_id,
        clients_affected=500,
        downtime_minutes=45,
        services_critical=("trading",),
        detected_at=datetime.now(timezone.utc),
        confirmed_at=None,
        occurred_at=None,
    )
    return Success(mock_incident)


async def _persist_classification(result: ClassificationResult) -> None:
    """Persist classification result to database."""
    # This would integrate with actual database
    pass


async def _emit_incident_classified_event(result: ClassificationResult) -> None:
    """Emit IncidentClassified domain event."""
    event = IncidentClassified(
        incident_id=result.incident_id,
        severity=result.severity,
        anchor_timestamp=result.anchor_timestamp,
        anchor_source=result.anchor_source,
        classification_reasons=result.classification_reasons,
        classified_at=datetime.now(timezone.utc),
        requires_notification=result.requires_notification,
        notification_deadline_hours=result.notification_deadline_hours,
    )
    await _emit_event(event)


async def _emit_deadline_scheduled_event(deadlines: DeadlineCalculation) -> None:
    """Emit DeadlineScheduled domain event."""
    event = DeadlineScheduled(
        incident_id=deadlines.incident_id,
        deadlines=deadlines,
        scheduled_at=datetime.now(timezone.utc),
        dst_transitions_handled=deadlines.dst_transitions_handled,
    )
    await _emit_event(event)


async def _emit_event(event: Any) -> None:
    """Emit domain event to event bus."""
    # This would integrate with actual event bus (Redis, message queue, etc.)
    print(f"EVENT: {event}")


async def _schedule_notification(
    incident_id: str, notification_type: str, deadline: datetime, severity: Severity
) -> None:
    """Schedule a notification with external service."""
    # This would integrate with notification service (Celery, etc.)
    pass


async def _log_error(message: str, incident_id: str) -> None:
    """Log error with structured logging."""
    # This would integrate with structured logging
    print(f"ERROR: {message} [incident_id={incident_id}]")


def _build_classification_reasons(
    incident: IncidentInput, severity: Severity
) -> tuple[str, ...]:
    """Build human-readable classification reasons."""
    reasons = []

    if severity == Severity.MAJOR:
        if incident.downtime_minutes >= 60 and len(incident.services_critical) >= 1:
            reasons.append(
                f"Downtime {incident.downtime_minutes}min >= 60min with {len(incident.services_critical)} critical services"
            )

        if incident.clients_affected >= 1000:
            reasons.append(f"Clients affected {incident.clients_affected} >= 1000")

        if "payment" in incident.services_critical and incident.downtime_minutes >= 30:
            reasons.append(
                f"Payment service affected with {incident.downtime_minutes}min downtime >= 30min"
            )

    elif severity == Severity.SIGNIFICANT:
        if 100 <= incident.clients_affected < 1000:
            reasons.append(
                f"Clients affected {incident.clients_affected} in range 100-999"
            )

        if (
            15 <= incident.downtime_minutes < 60
            and len(incident.services_critical) >= 1
        ):
            reasons.append(
                f"Downtime {incident.downtime_minutes}min in range 15-59min with {len(incident.services_critical)} critical services"
            )

    elif severity == Severity.MINOR:
        reasons.append("Below significant thresholds but requires DORA reporting")

    elif severity == Severity.NO_REPORT:
        reasons.append("Below DORA reporting thresholds")

    return tuple(reasons)


def _get_notification_deadline_hours(severity: Severity) -> Optional[int]:
    """Get notification deadline hours for severity."""
    deadline_map = {
        Severity.CRITICAL: 1,
        Severity.MAJOR: 4,
        Severity.SIGNIFICANT: 24,
        Severity.MINOR: 24,
        Severity.NO_REPORT: None,
    }
    return deadline_map.get(severity)
