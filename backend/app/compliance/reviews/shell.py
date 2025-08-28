"""
Compliance Reviews Module - Imperative Shell (I/O Operations)

All I/O operations for lawyer review workflow including database operations,
event publishing, notifications, and external integrations.
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import uuid

from .contracts import (
    ReviewRequest,
    ReviewDecision,
    ReviewStatus,
    ReviewPriority,
    Reviewer,
    AuditTrailEntry,
    AuditAction,
    ChainVerificationResult,
    ReviewAuditReport,
)
from .core import (
    hash_mapping_content,
    is_mapping_stale,
    calculate_review_duration,
    calculate_sla_deadline,
    is_sla_breached,
    can_transition_status,
    build_audit_trail_entry,
    verify_hash_chain,
    validate_reviewer_capacity,
    calculate_review_metrics,
)
from .events import (
    ReviewRequested,
    ReviewAssigned,
    ReviewStarted,
    DecisionRecorded,
    MappingMarkedStale,
    ReviewSLABreached,
    AuditTrailViolation,
    ChainIntegrityVerified,
)


class ReviewWorkflowService:
    """Service for managing lawyer review workflow with audit trails."""

    def __init__(self, db_session, event_publisher, notification_service):
        self.db = db_session
        self.events = event_publisher
        self.notifications = notification_service

    async def submit_for_review(
        self,
        mapping_id: str,
        priority: ReviewPriority,
        rationale: str,
        evidence_urls: Tuple[str, ...],
        submitted_by: str,
    ) -> ReviewRequest:
        """Submit mapping for lawyer review with audit trail."""

        # Get current mapping and calculate version hash
        current_mapping = await self._get_mapping(mapping_id)
        if not current_mapping:
            raise ValueError(f"Mapping {mapping_id} not found")

        version_hash = hash_mapping_content(current_mapping)

        # Create review request
        request = ReviewRequest.create(
            mapping_id=mapping_id,
            mapping_version_hash=version_hash,
            priority=priority,
            submitted_by=submitted_by,
            evidence_urls=evidence_urls,
            rationale=rationale,
        )

        # Store review request
        await self._store_review_request(request)

        # Create audit trail entry
        await self._append_audit_entry(
            AuditAction.REVIEW_SUBMITTED,
            submitted_by,
            request.id,
            {
                "mapping_id": mapping_id,
                "version_hash": version_hash,
                "priority": priority.value,
                "evidence_count": len(evidence_urls),
            },
        )

        # Publish event
        sla_deadline = calculate_sla_deadline(request.submitted_at, priority)
        event = ReviewRequested(
            request_id=request.id,
            mapping_id=mapping_id,
            mapping_version_hash=version_hash,
            priority=priority,
            submitted_by=submitted_by,
            evidence_urls=evidence_urls,
            rationale=rationale,
            submitted_at=request.submitted_at,
            expected_sla_deadline=sla_deadline,
        )
        await self.events.publish(event)

        # Attempt auto-assignment
        await self._attempt_auto_assignment(request)

        return request

    async def assign_reviewer(
        self, request_id: str, reviewer_id: str, assigned_by: str
    ) -> bool:
        """Assign review to specific lawyer."""

        # Get review request and reviewer
        request = await self._get_review_request(request_id)
        reviewer = await self._get_reviewer(reviewer_id)

        if not request or not reviewer:
            return False

        # Check reviewer capacity
        current_workload = await self._get_reviewer_workload(reviewer_id)
        capacity_result = validate_reviewer_capacity(reviewer, current_workload)

        if hasattr(capacity_result, "error"):
            return False

        # Update assignment
        await self._update_assignment(request_id, reviewer_id, assigned_by)

        # Create audit trail
        await self._append_audit_entry(
            AuditAction.REVIEW_ASSIGNED,
            assigned_by,
            request_id,
            {
                "reviewer_id": reviewer_id,
                "reviewer_email": reviewer.email,
                "workload_before": current_workload,
                "workload_after": current_workload + 1,
            },
        )

        # Publish event
        event = ReviewAssigned(
            request_id=request_id,
            reviewer_id=reviewer_id,
            reviewer_email=reviewer.email,
            assigned_by=assigned_by,
            assigned_at=datetime.utcnow(),
            reviewer_current_workload=current_workload + 1,
            priority=request.priority,
        )
        await self.events.publish(event)

        # Send notification
        await self._notify_reviewer_assigned(reviewer, request)

        return True

    async def start_review(
        self, request_id: str, reviewer_id: str, evidence_urls_accessed: Tuple[str, ...]
    ) -> bool:
        """Mark review as started by lawyer."""

        request = await self._get_review_request(request_id)
        if not request or request.id != request_id:
            return False

        # Update status to in_review
        success = await self._update_review_status(request_id, ReviewStatus.IN_REVIEW)
        if not success:
            return False

        # Create audit trail
        await self._append_audit_entry(
            AuditAction.REVIEW_STARTED,
            reviewer_id,
            request_id,
            {
                "started_at": datetime.utcnow().isoformat(),
                "evidence_accessed": list(evidence_urls_accessed),
            },
        )

        # Publish event
        event = ReviewStarted(
            request_id=request_id,
            reviewer_id=reviewer_id,
            started_at=datetime.utcnow(),
            evidence_urls_accessed=evidence_urls_accessed,
        )
        await self.events.publish(event)

        return True

    async def record_decision(
        self,
        request_id: str,
        reviewer: Reviewer,
        decision: ReviewStatus,
        comments: str,
        evidence_checked: Tuple[str, ...],
    ) -> ReviewDecision:
        """Record review decision with immutable audit trail."""

        # Get review request
        request = await self._get_review_request(request_id)
        if not request:
            raise ValueError(f"Review request {request_id} not found")

        # Validate state transition
        current_status = await self._get_current_status(request_id)
        if not can_transition_status(current_status, decision):
            raise ValueError(
                f"Invalid status transition from {current_status} to {decision}"
            )

        # Check for stale mapping
        current_mapping = await self._get_mapping(request.mapping_id)
        if is_mapping_stale(request.mapping_version_hash, current_mapping):
            # Mark as stale instead
            await self._mark_mapping_stale(request, current_mapping)
            raise ValueError(
                "Mapping has changed since review started - marked as stale"
            )

        # Calculate review duration
        reviewed_at = datetime.utcnow()
        duration_minutes = calculate_review_duration(request.submitted_at, reviewed_at)

        # Create decision record
        review_decision = ReviewDecision(
            request_id=request_id,
            reviewer_id=reviewer.id,
            reviewer_email=reviewer.email,
            reviewer_role=reviewer.role,
            decision=decision,
            comments=comments,
            evidence_reviewed=evidence_checked,
            reviewed_at=reviewed_at,
            review_duration_minutes=duration_minutes,
            version_verified=True,
        )

        # Store decision
        await self._store_review_decision(review_decision)
        await self._update_review_status(request_id, decision)

        # Create audit trail with hash chain
        audit_entry = await self._append_audit_entry(
            AuditAction.DECISION_RECORDED,
            reviewer.email,
            request_id,
            {
                "decision": decision.value,
                "comments": comments,
                "evidence_reviewed": list(evidence_checked),
                "duration_minutes": duration_minutes,
                "mapping_version_verified": True,
            },
        )

        # Publish event
        event = DecisionRecorded(
            request_id=request_id,
            decision=decision,
            reviewer_id=reviewer.id,
            reviewer_email=reviewer.email,
            decision_comments=comments,
            evidence_reviewed=evidence_checked,
            reviewed_at=reviewed_at,
            review_duration_minutes=duration_minutes,
            version_verified=True,
            audit_entry_id=audit_entry.id,
            chain_hash=audit_entry.context_data.get("chain_hash", ""),
        )
        await self.events.publish(event)

        # Send completion notification
        await self._notify_decision_recorded(request, review_decision)

        return review_decision

    async def check_sla_breaches(self) -> List[ReviewSLABreached]:
        """Check for SLA breaches and emit events."""

        active_reviews = await self._get_active_reviews()
        breached_events = []
        current_time = datetime.utcnow()

        for request, reviewer_id in active_reviews:
            if is_sla_breached(request.submitted_at, request.priority, current_time):
                # Calculate hours overdue
                deadline = calculate_sla_deadline(
                    request.submitted_at, request.priority
                )
                hours_overdue = (current_time - deadline).total_seconds() / 3600

                # Create breach event
                event = ReviewSLABreached(
                    request_id=request.id,
                    priority=request.priority,
                    submitted_at=request.submitted_at,
                    sla_deadline=deadline,
                    hours_overdue=hours_overdue,
                    reviewer_id=reviewer_id,
                    current_status=await self._get_current_status(request.id),
                )

                await self.events.publish(event)
                breached_events.append(event)

        return breached_events

    async def verify_audit_chain_integrity(self) -> ChainVerificationResult:
        """Verify complete audit trail integrity."""

        # Get all audit entries
        audit_entries = await self._get_all_audit_entries()

        # Verify hash chain
        verification_result = verify_hash_chain(audit_entries)

        # Create verification event
        event = ChainIntegrityVerified(
            verification_id=f"verify_{uuid.uuid4().hex[:8]}",
            total_entries_verified=verification_result.total_entries,
            verification_started_at=datetime.utcnow(),
            verification_completed_at=datetime.utcnow(),
            hash_chain_valid=verification_result.valid,
            last_entry_hash=(
                audit_entries[-1].context_data.get("chain_hash", "")
                if audit_entries
                else ""
            ),
            verification_triggered_by="system",
        )
        await self.events.publish(event)

        # If integrity violation detected, emit violation event
        if not verification_result.valid:
            violation_event = AuditTrailViolation(
                violation_type="hash_mismatch",
                affected_entry_id=f"entry_{verification_result.broken_at_sequence}",
                expected_value=verification_result.expected_hash or "",
                actual_value=verification_result.actual_hash or "",
                detected_at=datetime.utcnow(),
                detection_context={
                    "total_entries": verification_result.total_entries,
                    "verified_entries": verification_result.verified_entries,
                    "broken_sequence": verification_result.broken_at_sequence,
                },
                severity="critical",
            )
            await self.events.publish(violation_event)

        return verification_result

    async def export_audit_trail(
        self, start_date: datetime, end_date: datetime, requester: str
    ) -> ReviewAuditReport:
        """Export complete audit trail for regulatory review."""

        # Get audit entries in date range
        audit_entries = await self._get_audit_entries_by_date(start_date, end_date)
        reviews_data = await self._get_reviews_by_date(start_date, end_date)

        # Calculate metrics
        metrics = calculate_review_metrics(reviews_data)

        # Create audit report
        report = ReviewAuditReport(
            report_id=f"audit_{uuid.uuid4().hex[:8]}",
            generated_at=datetime.utcnow(),
            generated_by=requester,
            date_range=(start_date, end_date),
            total_reviews=metrics["total_reviews"],
            reviews_by_status={
                ReviewStatus(k): v for k, v in metrics["reviews_by_status"].items()
            },
            avg_review_duration_minutes=metrics["avg_duration_minutes"],
            sla_breach_count=int(metrics["total_reviews"] * metrics["sla_breach_rate"]),
            reviewers_activity=await self._get_reviewer_activity_stats(
                start_date, end_date
            ),
        )

        # Store export record
        await self._store_audit_export(report, audit_entries)

        return report

    # Private helper methods for database operations

    async def _get_mapping(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        """Get mapping data from database."""
        # Mock implementation - replace with actual DB query
        return {
            "mapping_id": mapping_id,
            "obligation_id": "DORA_ART_18",
            "control_id": "C001",
            "mapping_rationale": "Sample rationale",
            "evidence_urls": ["https://example.com/evidence"],
            "confidence_score": 0.95,
        }

    async def _store_review_request(self, request: ReviewRequest) -> None:
        """Store review request in database."""
        # Mock implementation
        pass

    async def _get_review_request(self, request_id: str) -> Optional[ReviewRequest]:
        """Get review request from database."""
        # Mock implementation
        return None

    async def _get_reviewer(self, reviewer_id: str) -> Optional[Reviewer]:
        """Get reviewer information."""
        # Mock implementation
        return None

    async def _get_reviewer_workload(self, reviewer_id: str) -> int:
        """Get current reviewer workload."""
        # Mock implementation
        return 0

    async def _update_assignment(
        self, request_id: str, reviewer_id: str, assigned_by: str
    ) -> None:
        """Update review assignment."""
        # Mock implementation
        pass

    async def _update_review_status(
        self, request_id: str, status: ReviewStatus
    ) -> bool:
        """Update review status."""
        # Mock implementation
        return True

    async def _get_current_status(self, request_id: str) -> ReviewStatus:
        """Get current review status."""
        # Mock implementation
        return ReviewStatus.PENDING

    async def _store_review_decision(self, decision: ReviewDecision) -> None:
        """Store review decision."""
        # Mock implementation
        pass

    async def _append_audit_entry(
        self,
        action_type: AuditAction,
        actor: str,
        evidence_ref: str,
        context_data: Dict[str, Any],
    ) -> AuditTrailEntry:
        """Append audit entry with hash chain integrity."""

        # Get previous hash from last entry
        previous_hash = await self._get_last_audit_hash()

        # Build audit entry with chain hash
        entry = build_audit_trail_entry(
            action_type=action_type,
            actor=actor,
            evidence_ref=evidence_ref,
            timestamp=datetime.utcnow(),
            context_data=context_data,
            previous_hash=previous_hash,
        )

        # Store in database
        await self._store_audit_entry(entry)

        return entry

    async def _get_last_audit_hash(self) -> str:
        """Get hash of last audit entry for chaining."""
        # Mock implementation
        return ""

    async def _store_audit_entry(self, entry: AuditTrailEntry) -> None:
        """Store audit entry in database."""
        # Mock implementation
        pass

    async def _get_all_audit_entries(self) -> List[AuditTrailEntry]:
        """Get all audit entries for integrity verification."""
        # Mock implementation
        return []

    async def _get_audit_entries_by_date(
        self, start_date: datetime, end_date: datetime
    ) -> List[AuditTrailEntry]:
        """Get audit entries within date range."""
        # Mock implementation
        return []

    async def _get_reviews_by_date(
        self, start_date: datetime, end_date: datetime
    ) -> List[Tuple[ReviewRequest, Optional[ReviewDecision]]]:
        """Get reviews within date range."""
        # Mock implementation
        return []

    async def _get_active_reviews(self) -> List[Tuple[ReviewRequest, Optional[str]]]:
        """Get active reviews for SLA checking."""
        # Mock implementation
        return []

    async def _mark_mapping_stale(
        self, request: ReviewRequest, current_mapping: Dict[str, Any]
    ) -> None:
        """Mark mapping as stale due to changes."""

        current_hash = hash_mapping_content(current_mapping)

        # Update status
        await self._update_review_status(request.id, ReviewStatus.STALE)

        # Create audit entry
        await self._append_audit_entry(
            AuditAction.MAPPING_MARKED_STALE,
            "system",
            request.id,
            {
                "original_hash": request.mapping_version_hash,
                "current_hash": current_hash,
                "mapping_id": request.mapping_id,
            },
        )

        # Publish event
        event = MappingMarkedStale(
            request_id=request.id,
            mapping_id=request.mapping_id,
            original_version_hash=request.mapping_version_hash,
            current_version_hash=current_hash,
            detected_at=datetime.utcnow(),
            detected_by="system",
            review_status_before=ReviewStatus.IN_REVIEW,
        )
        await self.events.publish(event)

    async def _attempt_auto_assignment(self, request: ReviewRequest) -> None:
        """Attempt to auto-assign review to available lawyer."""
        # Mock implementation
        pass

    async def _notify_reviewer_assigned(
        self, reviewer: Reviewer, request: ReviewRequest
    ) -> None:
        """Send notification to assigned reviewer."""
        # Mock implementation
        pass

    async def _notify_decision_recorded(
        self, request: ReviewRequest, decision: ReviewDecision
    ) -> None:
        """Send notification about recorded decision."""
        # Mock implementation
        pass

    async def _get_reviewer_activity_stats(
        self, start_date: datetime, end_date: datetime
    ) -> Dict[str, Dict[str, Any]]:
        """Get reviewer activity statistics."""
        # Mock implementation
        return {}

    async def _store_audit_export(
        self, report: ReviewAuditReport, entries: List[AuditTrailEntry]
    ) -> None:
        """Store audit export record."""
        # Mock implementation
        pass
