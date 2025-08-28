"""Domain events for incident classification."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from .contracts import Severity, DeadlineCalculation


@dataclass(frozen=True)
class IncidentClassified:
    """Event: Incident has been classified according to DORA rules."""

    incident_id: str
    severity: Severity
    anchor_timestamp: datetime
    anchor_source: str
    classification_reasons: tuple[str, ...]
    classified_at: datetime
    requires_notification: bool
    notification_deadline_hours: Optional[int]


@dataclass(frozen=True)
class DeadlineScheduled:
    """Event: DORA notification deadlines have been scheduled."""

    incident_id: str
    deadlines: DeadlineCalculation
    scheduled_at: datetime
    dst_transitions_handled: tuple[str, ...]


@dataclass(frozen=True)
class DSTTransitionHandled:
    """Event: DST transition was handled during deadline calculation."""

    incident_id: str
    transition_type: str  # "spring_forward" or "fall_back"
    anchor_time: datetime
    adjusted_time: datetime
    handled_at: datetime


@dataclass(frozen=True)
class InvalidClockAnchor:
    """Event: Invalid timestamp was detected and corrected."""

    incident_id: str
    invalid_timestamp: datetime
    error_type: str
    suggested_correction: Optional[datetime]
    detected_at: datetime
