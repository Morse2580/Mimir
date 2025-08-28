"""
Compliance Reviews Module - Functional Core (Pure Logic)

Pure functions for lawyer review workflow, version control, and audit trail integrity.
All functions are deterministic and side-effect free.
"""

from typing import Dict, Any, List, Tuple, Union, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import hashlib

from .contracts import (
    ReviewStatus,
    ReviewPriority,
    ReviewRequest,
    ReviewDecision,
    AuditTrailEntry,
    AuditAction,
    ChainVerificationResult,
    Reviewer,
)


# Result type for pure error handling
@dataclass(frozen=True)
class Success:
    """Success result with value."""

    value: Any


@dataclass(frozen=True)
class Failure:
    """Failure result with error message."""

    error: str


Result = Union[Success, Failure]


def hash_mapping_content(mapping: Dict[str, Any]) -> str:
    """
    Pure function: create deterministic version hash for mapping content.

    Args:
        mapping: Mapping data with obligation_id, control_id, rationale, etc.

    Returns:
        SHA-256 hash of canonical mapping content
    """
    # Extract only version-relevant fields in canonical order
    content = {
        "obligation_id": mapping.get("obligation_id", ""),
        "control_id": mapping.get("control_id", ""),
        "mapping_rationale": mapping.get("mapping_rationale", ""),
        "evidence_urls": tuple(sorted(mapping.get("evidence_urls", []))),
        "confidence_score": mapping.get("confidence_score", 0.0),
    }

    # Create deterministic JSON representation
    content_json = json.dumps(content, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(content_json.encode("utf-8")).hexdigest()


def is_mapping_stale(original_hash: str, current_mapping: Dict[str, Any]) -> bool:
    """
    Pure function: check if mapping content changed since review started.

    Args:
        original_hash: Hash when review was submitted
        current_mapping: Current mapping data

    Returns:
        True if mapping has changed (review is stale)
    """
    current_hash = hash_mapping_content(current_mapping)
    return original_hash != current_hash


def calculate_review_duration(submitted_at: datetime, reviewed_at: datetime) -> int:
    """
    Pure function: calculate review duration in minutes.

    Args:
        submitted_at: When review was submitted
        reviewed_at: When review was completed

    Returns:
        Duration in minutes (always non-negative)
    """
    if reviewed_at < submitted_at:
        return 0

    duration_seconds = (reviewed_at - submitted_at).total_seconds()
    return max(0, int(duration_seconds / 60))


def determine_review_priority(
    obligation_severity: str,
    regulatory_deadline: Optional[datetime],
    control_criticality: str,
    current_time: Optional[datetime] = None,
) -> ReviewPriority:
    """
    Pure function: auto-determine review priority based on business rules.

    Args:
        obligation_severity: "critical", "high", "medium", "low"
        regulatory_deadline: Optional deadline for compliance
        control_criticality: "tier1", "tier2", "tier3"
        current_time: Current time (defaults to None for testing)

    Returns:
        Calculated review priority
    """
    # Urgent if critical obligation or deadline within 48 hours
    if obligation_severity == "critical":
        return ReviewPriority.URGENT

    if regulatory_deadline and current_time:
        hours_until_deadline = (
            regulatory_deadline - current_time
        ).total_seconds() / 3600
        if hours_until_deadline <= 48:
            return ReviewPriority.URGENT
        elif hours_until_deadline <= 168:  # 1 week
            return ReviewPriority.HIGH

    # High if high severity or tier1 control
    if obligation_severity == "high" or control_criticality == "tier1":
        return ReviewPriority.HIGH

    # Normal if medium severity or tier2 control
    if obligation_severity == "medium" or control_criticality == "tier2":
        return ReviewPriority.NORMAL

    # Default to low priority
    return ReviewPriority.LOW


def calculate_sla_deadline(
    submitted_at: datetime, priority: ReviewPriority
) -> datetime:
    """
    Pure function: calculate SLA deadline based on priority.

    Args:
        submitted_at: When review was submitted
        priority: Review priority level

    Returns:
        SLA deadline timestamp
    """
    sla_hours = {
        ReviewPriority.URGENT: 4,
        ReviewPriority.HIGH: 24,
        ReviewPriority.NORMAL: 72,
        ReviewPriority.LOW: 168,  # 1 week
    }

    hours = sla_hours[priority]
    return submitted_at + timedelta(hours=hours)


def is_sla_breached(
    submitted_at: datetime, priority: ReviewPriority, current_time: datetime
) -> bool:
    """
    Pure function: check if review SLA has been breached.

    Args:
        submitted_at: When review was submitted
        priority: Review priority level
        current_time: Current timestamp

    Returns:
        True if SLA deadline has passed
    """
    deadline = calculate_sla_deadline(submitted_at, priority)
    return current_time > deadline


def can_transition_status(from_status: ReviewStatus, to_status: ReviewStatus) -> bool:
    """
    Pure function: validate state machine transitions for review status.

    Args:
        from_status: Current review status
        to_status: Desired review status

    Returns:
        True if transition is valid
    """
    valid_transitions = {
        ReviewStatus.PENDING: {ReviewStatus.IN_REVIEW},
        ReviewStatus.IN_REVIEW: {
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED,
            ReviewStatus.NEEDS_REVISION,
            ReviewStatus.STALE,
        },
        ReviewStatus.NEEDS_REVISION: {ReviewStatus.PENDING},
        ReviewStatus.STALE: {ReviewStatus.PENDING},
        # Terminal states - no transitions allowed
        ReviewStatus.APPROVED: set(),
        ReviewStatus.REJECTED: set(),
    }

    return to_status in valid_transitions.get(from_status, set())


def calculate_evidence_hash(
    evidence_data: Dict[str, Any], previous_hash: str, timestamp: datetime, actor: str
) -> str:
    """
    Pure function: calculate evidence hash for audit chain integrity.

    Args:
        evidence_data: Evidence content to hash
        previous_hash: Hash of previous evidence entry
        timestamp: Evidence creation timestamp
        actor: Who created the evidence

    Returns:
        SHA-256 hash for chain integrity
    """
    # Create deterministic hash input
    hash_input = (
        previous_hash.encode("utf-8")
        + json.dumps(evidence_data, sort_keys=True, ensure_ascii=True).encode("utf-8")
        + timestamp.isoformat().encode("utf-8")
        + actor.encode("utf-8")
    )

    return hashlib.sha256(hash_input).hexdigest()


def verify_hash_chain(audit_entries: List[AuditTrailEntry]) -> ChainVerificationResult:
    """
    Pure function: verify integrity of audit trail hash chain.

    Args:
        audit_entries: List of audit trail entries to verify

    Returns:
        Verification result with details of any integrity issues
    """
    if not audit_entries:
        return ChainVerificationResult(valid=True, total_entries=0, verified_entries=0)

    # Sort by timestamp to ensure correct order
    sorted_entries = sorted(audit_entries, key=lambda x: x.timestamp)

    # Genesis entry should have empty previous hash
    expected_previous_hash = ""

    for i, entry in enumerate(sorted_entries):
        # Calculate expected hash for this entry
        expected_hash = calculate_evidence_hash(
            evidence_data=entry.context_data,
            previous_hash=expected_previous_hash,
            timestamp=entry.timestamp,
            actor=entry.actor,
        )

        # Check if stored hash matches calculated hash
        stored_hash = entry.context_data.get("chain_hash", "")

        if stored_hash != expected_hash:
            return ChainVerificationResult(
                valid=False,
                total_entries=len(sorted_entries),
                verified_entries=i,
                broken_at_sequence=i,
                expected_hash=expected_hash,
                actual_hash=stored_hash,
            )

        # Update for next iteration
        expected_previous_hash = expected_hash

    return ChainVerificationResult(
        valid=True,
        total_entries=len(sorted_entries),
        verified_entries=len(sorted_entries),
    )


def build_audit_trail_entry(
    action_type: AuditAction,
    actor: str,
    evidence_ref: str,
    timestamp: datetime,
    context_data: Optional[Dict[str, Any]] = None,
    previous_hash: str = "",
) -> AuditTrailEntry:
    """
    Pure function: build audit trail entry with hash chain integrity.

    Args:
        action_type: Type of audit action
        actor: Who performed the action
        evidence_ref: Reference to evidence created
        timestamp: When action occurred
        context_data: Additional context information
        previous_hash: Hash of previous audit entry

    Returns:
        Complete audit trail entry with integrity hash
    """
    # Prepare context data with chain hash
    full_context = context_data or {}

    # Calculate chain hash for this entry
    chain_hash = calculate_evidence_hash(
        evidence_data=full_context,
        previous_hash=previous_hash,
        timestamp=timestamp,
        actor=actor,
    )

    # Add chain hash to context
    full_context["chain_hash"] = chain_hash
    full_context["previous_hash"] = previous_hash

    return AuditTrailEntry.create(
        action_type=action_type,
        actor=actor,
        evidence_ref=evidence_ref,
        context_data=full_context,
    )


def validate_reviewer_capacity(reviewer: Reviewer, current_workload: int) -> Result:
    """
    Pure function: validate if reviewer can take additional review.

    Args:
        reviewer: Reviewer information
        current_workload: Current number of active reviews

    Returns:
        Success if capacity available, Failure otherwise
    """
    if current_workload >= reviewer.workload_capacity:
        return Failure(
            f"Reviewer {reviewer.id} at capacity ({current_workload}/{reviewer.workload_capacity})"
        )

    return Success(True)


def calculate_review_metrics(
    reviews: List[Tuple[ReviewRequest, Optional[ReviewDecision]]],
) -> Dict[str, Any]:
    """
    Pure function: calculate review performance metrics.

    Args:
        reviews: List of review requests with optional decisions

    Returns:
        Dictionary with calculated metrics
    """
    total_reviews = len(reviews)
    completed_reviews = [r for r in reviews if r[1] is not None]

    if not completed_reviews:
        return {
            "total_reviews": total_reviews,
            "completion_rate": 0.0,
            "avg_duration_minutes": 0.0,
            "sla_breach_rate": 0.0,
        }

    # Calculate average duration
    total_duration = sum(
        decision.review_duration_minutes for _, decision in completed_reviews
    )
    avg_duration = total_duration / len(completed_reviews)

    # Calculate SLA breach rate
    breached_count = 0
    for request, decision in completed_reviews:
        if decision and is_sla_breached(
            request.submitted_at, request.priority, decision.reviewed_at
        ):
            breached_count += 1

    sla_breach_rate = breached_count / len(completed_reviews)
    completion_rate = len(completed_reviews) / total_reviews

    return {
        "total_reviews": total_reviews,
        "completion_rate": completion_rate,
        "avg_duration_minutes": avg_duration,
        "sla_breach_rate": sla_breach_rate,
        "reviews_by_status": _count_by_status(completed_reviews),
    }


def _count_by_status(
    completed_reviews: List[Tuple[ReviewRequest, ReviewDecision]],
) -> Dict[str, int]:
    """Helper function to count reviews by status."""
    counts = {}
    for _, decision in completed_reviews:
        status = decision.decision.value
        counts[status] = counts.get(status, 0) + 1
    return counts
