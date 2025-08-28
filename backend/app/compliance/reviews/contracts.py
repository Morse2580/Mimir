"""
Compliance Reviews Module - Type Definitions and Contracts

Immutable data structures for lawyer review workflow with audit trail support.
"""

from typing import Protocol, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import uuid


class ReviewStatus(Enum):
    """Review lifecycle states."""

    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    STALE = "stale"  # Mapping changed since review started


class ReviewPriority(Enum):
    """Review priority levels with SLA implications."""

    URGENT = "urgent"  # <4 hours response
    HIGH = "high"  # <24 hours response
    NORMAL = "normal"  # <72 hours response
    LOW = "low"  # <1 week response


class AuditAction(Enum):
    """Types of auditable actions in review workflow."""

    REVIEW_SUBMITTED = "review_submitted"
    REVIEW_ASSIGNED = "review_assigned"
    REVIEW_STARTED = "review_started"
    DECISION_RECORDED = "decision_recorded"
    MAPPING_MARKED_STALE = "mapping_marked_stale"
    REVIEW_REASSIGNED = "review_reassigned"


@dataclass(frozen=True)
class Reviewer:
    """Immutable reviewer information."""

    id: str
    email: str
    role: str  # "Senior Legal Counsel", "Compliance Officer", etc.
    certifications: Tuple[str, ...]
    workload_capacity: int  # Max concurrent reviews


@dataclass(frozen=True)
class ReviewRequest:
    """Immutable review request with version tracking."""

    id: str
    mapping_id: str
    mapping_version_hash: str
    priority: ReviewPriority
    submitted_at: datetime
    submitted_by: str
    evidence_urls: Tuple[str, ...]
    rationale: str

    @classmethod
    def create(
        cls,
        mapping_id: str,
        mapping_version_hash: str,
        priority: ReviewPriority,
        submitted_by: str,
        evidence_urls: Tuple[str, ...],
        rationale: str,
    ) -> "ReviewRequest":
        """Factory method for creating review requests."""
        return cls(
            id=f"req_{uuid.uuid4().hex[:12]}",
            mapping_id=mapping_id,
            mapping_version_hash=mapping_version_hash,
            priority=priority,
            submitted_at=datetime.utcnow(),
            submitted_by=submitted_by,
            evidence_urls=evidence_urls,
            rationale=rationale,
        )


@dataclass(frozen=True)
class ReviewDecision:
    """Immutable review decision with full audit information."""

    request_id: str
    reviewer_id: str
    reviewer_email: str
    reviewer_role: str
    decision: ReviewStatus
    comments: str
    evidence_reviewed: Tuple[str, ...]
    reviewed_at: datetime
    review_duration_minutes: int
    version_verified: bool


@dataclass(frozen=True)
class AuditTrailEntry:
    """Immutable audit trail entry for compliance tracking."""

    id: str
    timestamp: datetime
    action_type: AuditAction
    actor: str
    evidence_ref: str
    context_data: Dict[str, Any]

    @classmethod
    def create(
        cls,
        action_type: AuditAction,
        actor: str,
        evidence_ref: str,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> "AuditTrailEntry":
        """Factory method for creating audit trail entries."""
        return cls(
            id=f"audit_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.utcnow(),
            action_type=action_type,
            actor=actor,
            evidence_ref=evidence_ref,
            context_data=context_data or {},
        )


@dataclass(frozen=True)
class ChainVerificationResult:
    """Result of hash chain integrity verification."""

    valid: bool
    total_entries: int
    verified_entries: int
    broken_at_sequence: Optional[int] = None
    expected_hash: Optional[str] = None
    actual_hash: Optional[str] = None
    verification_timestamp: datetime = datetime.utcnow()


@dataclass(frozen=True)
class ReviewAuditReport:
    """Audit report for review activities."""

    report_id: str
    generated_at: datetime
    generated_by: str
    date_range: Tuple[datetime, datetime]
    total_reviews: int
    reviews_by_status: Dict[ReviewStatus, int]
    avg_review_duration_minutes: float
    sla_breach_count: int
    reviewers_activity: Dict[str, Dict[str, Any]]


class ReviewWorkflow(Protocol):
    """Core contract for review process operations."""

    def submit_for_review(
        self,
        mapping_id: str,
        priority: ReviewPriority,
        rationale: str,
        evidence_urls: Tuple[str, ...],
    ) -> ReviewRequest:
        """Submit mapping for lawyer review with audit trail."""
        ...

    def record_decision(
        self,
        request_id: str,
        reviewer: Reviewer,
        decision: ReviewStatus,
        comments: str,
        evidence_checked: Tuple[str, ...],
    ) -> ReviewDecision:
        """Record review decision with immutable audit trail."""
        ...

    def verify_chain_integrity(
        self, entries: Tuple[AuditTrailEntry, ...]
    ) -> ChainVerificationResult:
        """Verify audit trail integrity for compliance."""
        ...


class ReviewAuditTrail(Protocol):
    """Contract for audit trail operations."""

    def append_audit_entry(
        self,
        action_type: AuditAction,
        actor: str,
        evidence_ref: str,
        context_data: Optional[Dict[str, Any]] = None,
    ) -> AuditTrailEntry:
        """Append entry to immutable audit trail."""
        ...

    def export_audit_report(
        self, start_date: datetime, end_date: datetime, requester: str
    ) -> ReviewAuditReport:
        """Export audit report for regulatory compliance."""
        ...
