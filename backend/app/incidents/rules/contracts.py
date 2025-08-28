"""Contracts for DORA incident classification."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Generic, TypeVar, Union

T = TypeVar('T')
E = TypeVar('E')

@dataclass(frozen=True)
class Success(Generic[T]):
    """Success result with value."""
    value: T

@dataclass(frozen=True) 
class Failure(Generic[E]):
    """Failure result with error."""
    error: E

Result = Union[Success[T], Failure[E]]

class Severity(Enum):
    """DORA incident severity levels."""
    CRITICAL = "critical"
    MAJOR = "major" 
    SIGNIFICANT = "significant"
    MINOR = "minor"
    NO_REPORT = "no_report"

@dataclass(frozen=True)
class IncidentInput:
    """Input data for incident classification."""
    incident_id: str
    clients_affected: int
    downtime_minutes: int
    services_critical: tuple[str, ...]
    detected_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    occurred_at: Optional[datetime]
    reputational_impact: Optional[str] = None
    data_losses: Optional[bool] = None
    economic_impact_eur: Optional[float] = None
    geographical_spread: Optional[str] = None

@dataclass(frozen=True)
class ClassificationResult:
    """Result of incident classification."""
    incident_id: str
    severity: Severity
    anchor_timestamp: datetime
    anchor_source: str
    classification_reasons: tuple[str, ...]
    deadlines: DeadlineCalculation
    requires_notification: bool
    notification_deadline_hours: Optional[int]
    
@dataclass(frozen=True)
class DeadlineCalculation:
    """DST-aware deadline calculation results."""
    incident_id: str
    severity: Severity
    anchor_time_utc: datetime
    anchor_time_brussels: datetime
    
    # DORA Article 19 deadlines
    initial_notification: datetime
    intermediate_report: Optional[datetime]
    final_report: datetime
    
    # NBB OneGate deadlines
    nbb_notification: Optional[datetime]
    
    # Audit metadata
    dst_transitions_handled: tuple[str, ...]
    calculation_confidence: float
    timezone_used: str

@dataclass(frozen=True)
class ClockValidationResult:
    """Result of clock anchor validation."""
    valid: bool
    timestamp: datetime
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    suggested_time: Optional[datetime] = None