"""Pure functions for DORA incident classification and DST-aware deadline calculation."""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, Tuple
from .contracts import (
    Severity,
    DeadlineCalculation,
    ClockValidationResult,
    Success,
    Failure,
    Result,
)

# Brussels timezone for all calculations
BRUSSELS_TZ = ZoneInfo("Europe/Brussels")

# DORA deadline configuration per severity
DORA_DEADLINES = {
    Severity.CRITICAL: {"initial_hours": 1, "intermediate_hours": 24, "final_days": 14},
    Severity.MAJOR: {"initial_hours": 4, "intermediate_hours": 72, "final_days": 14},
    Severity.SIGNIFICANT: {
        "initial_hours": 24,
        "intermediate_hours": None,
        "final_days": 14,
    },
    Severity.MINOR: {"initial_hours": 24, "intermediate_hours": None, "final_days": 14},
}


def classify_incident_severity(
    clients_affected: int, downtime_minutes: int, services_critical: tuple[str, ...]
) -> Severity:
    """
    DORA Article 18 classification. MUST be deterministic.

    Classification Rules:
    - MAJOR: downtime_minutes >= 60 AND services_critical >= 1 OR
             clients_affected >= 1000 OR
             "payment" IN services AND downtime_minutes >= 30
    - SIGNIFICANT: 100 <= clients_affected < 1000 OR
                   15 <= downtime_minutes < 60 AND services_critical >= 1
    - MINOR/NO_REPORT: Everything else
    """
    # Major incident criteria
    if (
        (downtime_minutes >= 60 and len(services_critical) >= 1)
        or (clients_affected >= 1000)
        or ("payment" in services_critical and downtime_minutes >= 30)
    ):
        return Severity.MAJOR

    # Significant incident criteria
    if (100 <= clients_affected < 1000) or (
        15 <= downtime_minutes < 60 and len(services_critical) >= 1
    ):
        return Severity.SIGNIFICANT

    # Minor incidents still need reporting per DORA
    if clients_affected > 0 or downtime_minutes > 0:
        return Severity.MINOR

    # No reporting required
    return Severity.NO_REPORT


def determine_anchor_timestamp(
    detected_at: Optional[datetime],
    confirmed_at: Optional[datetime],
    occurred_at: Optional[datetime],
) -> Result[Tuple[datetime, str], str]:
    """
    Fallback chain for timestamp anchor. MUST be deterministic.
    Priority: detected_at → confirmed_at → occurred_at
    """
    if detected_at is not None:
        return Success((detected_at, "detected_at"))

    if confirmed_at is not None:
        return Success((confirmed_at, "confirmed_at"))

    if occurred_at is not None:
        return Success((occurred_at, "occurred_at"))

    return Failure("No valid timestamp provided for incident")


def validate_clock_anchor(
    timestamp: datetime, timezone: ZoneInfo = BRUSSELS_TZ
) -> ClockValidationResult:
    """Validate timestamp is valid clock anchor. MUST be pure."""
    if timestamp.tzinfo is None:
        return ClockValidationResult(
            valid=False,
            timestamp=timestamp,
            error_type="naive_datetime",
            error_message="Timestamp must be timezone-aware",
            suggested_time=timestamp.replace(tzinfo=timezone),
        )

    # Check for DST gap (spring forward)
    if _is_dst_gap_time(timestamp, timezone):
        return ClockValidationResult(
            valid=False,
            timestamp=timestamp,
            error_type="dst_gap",
            error_message="Timestamp falls in DST spring forward gap (02:00-03:00 doesn't exist)",
            suggested_time=_suggest_valid_time_from_gap(timestamp, timezone),
        )

    # Valid timestamp
    return ClockValidationResult(valid=True, timestamp=timestamp)


def calculate_deadlines(
    anchor: datetime, severity: Severity, tz: ZoneInfo = BRUSSELS_TZ
) -> Result[DeadlineCalculation, str]:
    """DST-aware deadlines. MUST handle all transitions."""

    # Validate anchor timestamp
    validation = validate_clock_anchor(anchor, tz)
    if not validation.valid:
        return Failure(f"Invalid anchor timestamp: {validation.error_message}")

    if severity == Severity.NO_REPORT:
        return Failure("No deadlines calculated for NO_REPORT severity")

    # Get deadline configuration
    deadline_config = DORA_DEADLINES.get(severity)
    if not deadline_config:
        return Failure(f"No deadline configuration for severity: {severity}")

    # Convert anchor to Brussels time if needed
    anchor_brussels = anchor.astimezone(tz) if anchor.tzinfo != tz else anchor
    anchor_utc = anchor.astimezone(timezone.utc)

    # Track DST transitions handled
    dst_transitions_handled = []

    # Calculate initial notification deadline
    initial_hours = deadline_config["initial_hours"]
    initial_deadline, initial_dst = _add_hours_with_dst(
        anchor_brussels, initial_hours, tz
    )
    dst_transitions_handled.extend(initial_dst)

    # Calculate intermediate report deadline (if applicable)
    intermediate_deadline = None
    if deadline_config["intermediate_hours"] is not None:
        intermediate_deadline, intermediate_dst = _add_hours_with_dst(
            anchor_brussels, deadline_config["intermediate_hours"], tz
        )
        dst_transitions_handled.extend(intermediate_dst)

    # Calculate final report deadline
    final_days = deadline_config["final_days"]
    final_deadline, final_dst = _add_days_with_dst(anchor_brussels, final_days, tz)
    dst_transitions_handled.extend(final_dst)

    # NBB notification (same as initial for pilot)
    nbb_deadline = (
        initial_deadline if severity in [Severity.MAJOR, Severity.CRITICAL] else None
    )

    return Success(
        DeadlineCalculation(
            incident_id="",  # Will be set by caller
            severity=severity,
            anchor_time_utc=anchor_utc,
            anchor_time_brussels=anchor_brussels,
            initial_notification=initial_deadline.astimezone(timezone.utc),
            intermediate_report=(
                intermediate_deadline.astimezone(timezone.utc)
                if intermediate_deadline
                else None
            ),
            final_report=final_deadline.astimezone(timezone.utc),
            nbb_notification=(
                nbb_deadline.astimezone(timezone.utc) if nbb_deadline else None
            ),
            dst_transitions_handled=tuple(dst_transitions_handled),
            calculation_confidence=1.0,
            timezone_used=str(tz),
        )
    )


def _is_dst_gap_time(dt: datetime, tz: ZoneInfo) -> bool:
    """Check if datetime falls in DST gap (non-existent time)."""
    # For ZoneInfo, check if this is specifically the spring forward gap
    return _is_spring_forward_gap(dt, tz)


def _is_spring_forward_gap(dt: datetime, tz: ZoneInfo) -> bool:
    """Check specifically for spring forward gap."""
    # Get the year from the datetime
    year = dt.year

    # Find the last Sunday in March (EU DST rule)
    march_last_sunday = _get_last_sunday_of_march(year)

    # Check if this is the DST transition day and time is in 02:00-03:00 range
    return (
        dt.month == 3
        and dt.day == march_last_sunday
        and dt.hour == 2  # This hour doesn't exist during spring forward
    )


def _get_last_sunday_of_march(year: int) -> int:
    """Get the day number of the last Sunday in March."""
    # March 31st
    march_31 = datetime(year, 3, 31)

    # Find the last Sunday by going back from March 31
    days_back = march_31.weekday() + 1  # Monday is 0, Sunday is 6
    if days_back == 7:
        days_back = 0

    last_sunday = march_31 - timedelta(days=days_back)
    return last_sunday.day


def _get_last_sunday_of_october(year: int) -> int:
    """Get the day number of the last Sunday in October."""
    # October 31st
    october_31 = datetime(year, 10, 31)

    # Find the last Sunday by going back from October 31
    days_back = october_31.weekday() + 1  # Monday is 0, Sunday is 6
    if days_back == 7:
        days_back = 0

    last_sunday = october_31 - timedelta(days=days_back)
    return last_sunday.day


def _suggest_valid_time_from_gap(dt: datetime, tz: ZoneInfo) -> datetime:
    """Suggest a valid time when given time is in DST gap."""
    # If it's 2:XX during spring forward, suggest 3:XX
    if dt.hour == 2:
        suggested = dt.replace(hour=3)
        return suggested.replace(tzinfo=tz)

    return dt


def _add_hours_with_dst(
    start: datetime, hours: int, tz: ZoneInfo
) -> Tuple[datetime, list[str]]:
    """Add hours to datetime handling DST transitions."""
    dst_transitions = []

    # Convert to UTC, add hours, then back to local timezone
    # This properly handles DST transitions
    start_utc = start.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(hours=hours)
    end_time = end_utc.astimezone(tz)

    # Check if we crossed a DST boundary by comparing offsets
    start_offset = start.utcoffset()
    end_offset = end_time.utcoffset()

    if start_offset != end_offset:
        if end_offset > start_offset:
            dst_transitions.append("spring_forward")
        else:
            dst_transitions.append("fall_back")

    return end_time, dst_transitions


def _add_days_with_dst(
    start: datetime, days: int, tz: ZoneInfo
) -> Tuple[datetime, list[str]]:
    """Add days to datetime handling DST transitions."""
    dst_transitions = []

    # Add days
    end_time = start + timedelta(days=days)

    # Check for DST transitions in the range
    current = start
    for day in range(days):
        next_day = current + timedelta(days=1)

        current_offset = current.utcoffset()
        next_offset = next_day.utcoffset()

        if current_offset != next_offset:
            if next_offset > current_offset:
                dst_transitions.append(f"spring_forward_day_{day + 1}")
            else:
                dst_transitions.append(f"fall_back_day_{day + 1}")

        current = next_day

    return end_time, dst_transitions
