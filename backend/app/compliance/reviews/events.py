"""
Compliance Reviews Module - Domain Events

Domain events for lawyer review workflow and audit trail operations.
All events are immutable and contain complete context for downstream processing.
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .contracts import ReviewStatus, ReviewPriority


class EventType(Enum):
    """Types of domain events emitted by review workflow."""
    REVIEW_REQUESTED = "review_requested"
    REVIEW_ASSIGNED = "review_assigned"
    REVIEW_STARTED = "review_started"
    DECISION_RECORDED = "decision_recorded"
    MAPPING_MARKED_STALE = "mapping_marked_stale"
    SLA_BREACHED = "sla_breached"
    AUDIT_TRAIL_VIOLATION = "audit_trail_violation"
    CHAIN_INTEGRITY_VERIFIED = "chain_integrity_verified"


@dataclass(frozen=True)
class ReviewRequested:
    """Event: Review has been submitted for lawyer approval."""
    request_id: str
    mapping_id: str
    mapping_version_hash: str
    priority: ReviewPriority
    submitted_by: str
    evidence_urls: Tuple[str, ...]
    rationale: str
    submitted_at: datetime
    expected_sla_deadline: datetime
    
    event_type: EventType = EventType.REVIEW_REQUESTED
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class ReviewAssigned:
    """Event: Review has been assigned to a lawyer."""
    request_id: str
    reviewer_id: str
    reviewer_email: str
    assigned_by: str
    assigned_at: datetime
    reviewer_current_workload: int
    priority: ReviewPriority
    
    event_type: EventType = EventType.REVIEW_ASSIGNED
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class ReviewStarted:
    """Event: Lawyer has started reviewing the mapping."""
    request_id: str
    reviewer_id: str
    started_at: datetime
    evidence_urls_accessed: Tuple[str, ...]
    
    event_type: EventType = EventType.REVIEW_STARTED
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class DecisionRecorded:
    """Event: Review decision has been recorded with audit trail."""
    request_id: str
    decision: ReviewStatus
    reviewer_id: str
    reviewer_email: str
    decision_comments: str
    evidence_reviewed: Tuple[str, ...]
    reviewed_at: datetime
    review_duration_minutes: int
    version_verified: bool
    audit_entry_id: str
    chain_hash: str
    
    event_type: EventType = EventType.DECISION_RECORDED
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class MappingMarkedStale:
    """Event: Mapping was modified during review, marking review stale."""
    request_id: str
    mapping_id: str
    original_version_hash: str
    current_version_hash: str
    detected_at: datetime
    detected_by: str
    review_status_before: ReviewStatus
    
    event_type: EventType = EventType.MAPPING_MARKED_STALE
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class ReviewSLABreached:
    """Event: Review has exceeded its SLA deadline."""
    request_id: str
    priority: ReviewPriority
    submitted_at: datetime
    sla_deadline: datetime
    hours_overdue: float
    reviewer_id: Optional[str]
    current_status: ReviewStatus
    
    event_type: EventType = EventType.SLA_BREACHED
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class AuditTrailViolation:
    """Event: Audit trail integrity violation detected."""
    violation_type: str  # "hash_mismatch", "missing_entry", "timestamp_anomaly"
    affected_entry_id: str
    expected_value: str
    actual_value: str
    detected_at: datetime
    detection_context: Dict[str, Any]
    severity: str  # "critical", "high", "medium"
    
    event_type: EventType = EventType.AUDIT_TRAIL_VIOLATION
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True)
class ChainIntegrityVerified:
    """Event: Audit trail chain integrity successfully verified."""
    verification_id: str
    total_entries_verified: int
    verification_started_at: datetime
    verification_completed_at: datetime
    hash_chain_valid: bool
    last_entry_hash: str
    verification_triggered_by: str
    
    event_type: EventType = EventType.CHAIN_INTEGRITY_VERIFIED
    event_id: str = ""
    event_timestamp: datetime = datetime.utcnow()
    
    def __post_init__(self):
        if not self.event_id:
            import uuid
            object.__setattr__(self, 'event_id', f"evt_{uuid.uuid4().hex[:12]}")


# Event aggregates for batch processing
@dataclass(frozen=True)
class ReviewWorkflowEvents:
    """Aggregate of all events for a review workflow session."""
    review_requested: Optional[ReviewRequested] = None
    review_assigned: Optional[ReviewAssigned] = None
    review_started: Optional[ReviewStarted] = None
    decision_recorded: Optional[DecisionRecorded] = None
    mapping_marked_stale: Optional[MappingMarkedStale] = None
    sla_breached: Optional[ReviewSLABreached] = None
    
    def all_events(self) -> Tuple[Any, ...]:
        """Get all non-None events in chronological order."""
        events = []
        for event in [
            self.review_requested,
            self.review_assigned,
            self.review_started,
            self.decision_recorded,
            self.mapping_marked_stale,
            self.sla_breached
        ]:
            if event is not None:
                events.append(event)
        
        # Sort by event timestamp
        return tuple(sorted(events, key=lambda e: e.event_timestamp))


@dataclass(frozen=True) 
class AuditIntegrityEvents:
    """Aggregate of audit trail integrity events."""
    violations: Tuple[AuditTrailViolation, ...] = ()
    verifications: Tuple[ChainIntegrityVerified, ...] = ()
    
    def has_critical_violations(self) -> bool:
        """Check if any critical audit violations occurred."""
        return any(v.severity == "critical" for v in self.violations)
    
    def latest_verification(self) -> Optional[ChainIntegrityVerified]:
        """Get the most recent chain integrity verification."""
        if not self.verifications:
            return None
        return max(self.verifications, key=lambda v: v.verification_completed_at)