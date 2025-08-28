"""
Observability integration for Compliance Reviews module.
Collects metrics for lawyer review workflow, SLA tracking, and audit trail integrity.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from ...observability.contracts import MetricType
from ...observability.core import create_metric
from ...observability.integration import get_tracer, TrackedOperation
from ...observability.shell import record_metric
from .contracts import ReviewStatus, ReviewPriority, ReviewRequest, ReviewDecision

logger = logging.getLogger(__name__)

# Get tracer for this module
tracer = get_tracer("regops.compliance.reviews")


class ComplianceObservabilityCollector:
    """
    Collects observability metrics for the compliance reviews module.
    Integrates with lawyer review workflow and audit trail operations.
    """

    def __init__(self, storage=None):
        self.storage = storage

    async def track_review_submission(
        self,
        mapping_id: str,
        priority: ReviewPriority,
        submitted_by: str,
        evidence_count: int,
        submission_duration_ms: float,
        auto_priority_assigned: bool = False,
    ) -> None:
        """
        Track review submission metrics.

        Args:
            mapping_id: Mapping identifier
            priority: Assigned priority level
            submitted_by: Who submitted the review
            evidence_count: Number of evidence URLs provided
            submission_duration_ms: Time taken to submit
            auto_priority_assigned: Whether priority was auto-assigned
        """
        try:
            labels = {
                "priority": priority.value,
                "submitted_by": submitted_by,
                "auto_priority": str(auto_priority_assigned).lower(),
            }

            # Record review submissions
            await self._record_metric(
                name="compliance.reviews.submitted.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Track submission duration
            await self._record_metric(
                name="compliance.review_submission.duration_ms",
                value=submission_duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track priority distribution
            await self._record_metric(
                name="compliance.reviews.by_priority.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels={"priority": priority.value},
            )

            # Track evidence provided
            await self._record_metric(
                name="compliance.reviews.evidence_count",
                value=evidence_count,
                metric_type=MetricType.HISTOGRAM,
                labels={"priority": priority.value},
            )

            # Track queue size by priority
            await self._record_metric(
                name="compliance.review_queue.pending",
                value=1.0,
                metric_type=MetricType.GAUGE,
                labels={"priority": priority.value},
            )

        except Exception as e:
            logger.error(f"Failed to track review submission metrics: {e}")

    async def track_review_assignment(
        self,
        request_id: str,
        reviewer_id: str,
        reviewer_workload: int,
        workload_capacity: int,
        assignment_duration_ms: float,
        auto_assigned: bool = True,
    ) -> None:
        """
        Track review assignment metrics.

        Args:
            request_id: Review request identifier
            reviewer_id: Assigned reviewer
            reviewer_workload: Current reviewer workload
            workload_capacity: Reviewer's capacity
            assignment_duration_ms: Time taken to assign
            auto_assigned: Whether assignment was automatic
        """
        try:
            labels = {
                "reviewer_id": reviewer_id,
                "auto_assigned": str(auto_assigned).lower(),
            }

            # Record assignments
            await self._record_metric(
                name="compliance.reviews.assigned.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Track assignment duration (should be <1 minute per SLA)
            await self._record_metric(
                name="compliance.review_assignment.duration_ms",
                value=assignment_duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track reviewer workload
            await self._record_metric(
                name="compliance.reviewer.workload",
                value=reviewer_workload,
                metric_type=MetricType.GAUGE,
                labels={"reviewer_id": reviewer_id},
            )

            # Track reviewer capacity utilization
            utilization = (reviewer_workload / workload_capacity) * 100
            await self._record_metric(
                name="compliance.reviewer.capacity_utilization.percent",
                value=utilization,
                metric_type=MetricType.GAUGE,
                labels={"reviewer_id": reviewer_id},
            )

        except Exception as e:
            logger.error(f"Failed to track review assignment metrics: {e}")

    async def track_review_completion(
        self,
        request_id: str,
        reviewer_id: str,
        decision: ReviewStatus,
        priority: ReviewPriority,
        review_duration_minutes: int,
        evidence_reviewed_count: int,
        sla_deadline: datetime,
        completion_time: datetime,
        is_stale: bool = False,
    ) -> None:
        """
        Track review completion metrics.

        Args:
            request_id: Review request identifier
            reviewer_id: Reviewer who completed the review
            decision: Review decision made
            priority: Original priority level
            review_duration_minutes: Time taken for review
            evidence_reviewed_count: Number of evidence items reviewed
            sla_deadline: SLA deadline for the review
            completion_time: When review was completed
            is_stale: Whether mapping became stale during review
        """
        try:
            # Calculate SLA compliance
            sla_breached = completion_time > sla_deadline
            sla_margin_minutes = (sla_deadline - completion_time).total_seconds() / 60

            labels = {
                "reviewer_id": reviewer_id,
                "decision": decision.value,
                "priority": priority.value,
                "sla_breached": str(sla_breached).lower(),
                "stale": str(is_stale).lower(),
            }

            # Record review completions
            await self._record_metric(
                name="compliance.reviews.completed.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Track review duration
            await self._record_metric(
                name="compliance.review.duration_minutes",
                value=review_duration_minutes,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track SLA performance (critical business metric)
            if sla_breached:
                await self._record_metric(
                    name="compliance.reviews.sla_breached.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels=labels,
                )

                # Track breach severity
                breach_hours = abs(sla_margin_minutes / 60)
                await self._record_metric(
                    name="compliance.review_sla_breach.hours",
                    value=breach_hours,
                    metric_type=MetricType.HISTOGRAM,
                    labels=labels,
                )

            # Track SLA margin
            await self._record_metric(
                name="compliance.review_sla_margin.minutes",
                value=sla_margin_minutes,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track evidence review coverage
            await self._record_metric(
                name="compliance.review.evidence_reviewed_count",
                value=evidence_reviewed_count,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track decision distribution
            await self._record_metric(
                name="compliance.reviews.by_decision.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels={"decision": decision.value, "priority": priority.value},
            )

            # Track stale reviews (version conflicts)
            if is_stale:
                await self._record_metric(
                    name="compliance.reviews.stale.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels={"priority": priority.value},
                )

            # Update queue size (decrease)
            await self._record_metric(
                name="compliance.review_queue.pending",
                value=-1.0,
                metric_type=MetricType.GAUGE,
                labels={"priority": priority.value},
            )

        except Exception as e:
            logger.error(f"Failed to track review completion metrics: {e}")

    async def track_audit_trail_operation(
        self,
        operation_type: str,  # "create", "verify", "export"
        duration_ms: float,
        entries_processed: int,
        success: bool,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Track audit trail operations.

        Args:
            operation_type: Type of audit operation
            duration_ms: Time taken for operation
            entries_processed: Number of audit entries processed
            success: Whether operation succeeded
            error_type: Type of error if operation failed
        """
        try:
            labels = {
                "operation": operation_type,
                "success": str(success).lower(),
            }

            if error_type:
                labels["error_type"] = error_type

            # Record audit operations
            await self._record_metric(
                name="compliance.audit_trail.operations.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Track operation duration
            await self._record_metric(
                name="compliance.audit_trail.operation_duration_ms",
                value=duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track entries processed
            await self._record_metric(
                name="compliance.audit_trail.entries_processed",
                value=entries_processed,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track failures
            if not success:
                await self._record_metric(
                    name="compliance.audit_trail.failures.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels=labels,
                )

        except Exception as e:
            logger.error(f"Failed to track audit trail metrics: {e}")

    async def track_hash_chain_verification(
        self,
        total_entries: int,
        verified_entries: int,
        verification_duration_ms: float,
        chain_intact: bool,
        broken_at_sequence: Optional[int] = None,
    ) -> None:
        """
        Track hash chain verification results.

        Args:
            total_entries: Total number of audit entries
            verified_entries: Number of entries successfully verified
            verification_duration_ms: Time taken for verification
            chain_intact: Whether the hash chain is intact
            broken_at_sequence: Sequence number where chain was broken (if any)
        """
        try:
            labels = {
                "chain_intact": str(chain_intact).lower(),
            }

            # Record verification attempts
            await self._record_metric(
                name="compliance.hash_chain.verifications.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Track verification duration
            await self._record_metric(
                name="compliance.hash_chain.verification_duration_ms",
                value=verification_duration_ms,
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Track verification rate
            verification_rate = (verified_entries / max(total_entries, 1)) * 100
            await self._record_metric(
                name="compliance.hash_chain.verification_rate.percent",
                value=verification_rate,
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

            # Track chain integrity (critical security metric)
            await self._record_metric(
                name="ledger.verify.ok",
                value=1.0 if chain_intact else 0.0,
                metric_type=MetricType.GAUGE,
                labels={},
            )

            # Track chain breaks
            if not chain_intact and broken_at_sequence is not None:
                await self._record_metric(
                    name="compliance.hash_chain.breaks.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels={"broken_at_sequence": str(broken_at_sequence)},
                )

        except Exception as e:
            logger.error(f"Failed to track hash chain verification metrics: {e}")

    async def track_reviewer_performance(
        self,
        reviewer_id: str,
        reviews_completed: int,
        avg_duration_minutes: float,
        sla_breach_rate: float,
        completion_rate: float,
        decision_distribution: Dict[str, int],
    ) -> None:
        """
        Track individual reviewer performance metrics.

        Args:
            reviewer_id: Reviewer identifier
            reviews_completed: Number of reviews completed
            avg_duration_minutes: Average review duration
            sla_breach_rate: Rate of SLA breaches (0.0-1.0)
            completion_rate: Review completion rate (0.0-1.0)
            decision_distribution: Distribution of decisions made
        """
        try:
            labels = {"reviewer_id": reviewer_id}

            # Track reviewer productivity
            await self._record_metric(
                name="compliance.reviewer.reviews_completed",
                value=reviews_completed,
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

            # Track average review time
            await self._record_metric(
                name="compliance.reviewer.avg_duration_minutes",
                value=avg_duration_minutes,
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

            # Track SLA performance
            await self._record_metric(
                name="compliance.reviewer.sla_breach_rate.percent",
                value=sla_breach_rate * 100,
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

            # Track completion rate
            await self._record_metric(
                name="compliance.reviewer.completion_rate.percent",
                value=completion_rate * 100,
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

            # Track decision patterns
            for decision, count in decision_distribution.items():
                await self._record_metric(
                    name="compliance.reviewer.decisions.total",
                    value=count,
                    metric_type=MetricType.GAUGE,
                    labels={**labels, "decision": decision},
                )

        except Exception as e:
            logger.error(f"Failed to track reviewer performance metrics: {e}")

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


# Instrumented wrapper for compliance review operations
class InstrumentedReviewWorkflow:
    """
    Wrapper around review workflow that tracks comprehensive metrics.
    """

    def __init__(self, workflow, collector: Optional[ComplianceObservabilityCollector] = None):
        self.workflow = workflow
        self.collector = collector

    async def submit_for_review_with_metrics(
        self,
        mapping_id: str,
        priority: ReviewPriority,
        rationale: str,
        submitted_by: str,
        evidence_urls: List[str],
    ):
        """
        Submit mapping for review with metrics tracking.
        """
        start_time = datetime.utcnow()

        with TrackedOperation("compliance_review_submission", tracer) as span:
            span.add_attribute("mapping_id", mapping_id)
            span.add_attribute("priority", priority.value)
            span.add_attribute("evidence_count", len(evidence_urls))

            try:
                result = await self.workflow.submit_for_review(
                    mapping_id, priority, rationale
                )

                # Calculate duration
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

                # Track metrics
                if self.collector:
                    await self.collector.track_review_submission(
                        mapping_id=mapping_id,
                        priority=priority,
                        submitted_by=submitted_by,
                        evidence_count=len(evidence_urls),
                        submission_duration_ms=duration_ms,
                        auto_priority_assigned=False,  # Assuming explicit priority
                    )

                span.add_attribute("success", True)
                span.add_attribute("duration_ms", duration_ms)

                return result

            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                span.add_attribute("error", str(e))
                span.add_attribute("duration_ms", duration_ms)
                raise

    async def record_decision_with_metrics(
        self,
        request_id: str,
        reviewer_id: str,
        decision: ReviewStatus,
        comments: str,
        evidence_checked: List[str],
        original_request: ReviewRequest,
    ):
        """
        Record review decision with comprehensive metrics tracking.
        """
        start_time = datetime.utcnow()

        with TrackedOperation("compliance_review_decision", tracer) as span:
            span.add_attribute("request_id", request_id)
            span.add_attribute("reviewer_id", reviewer_id)
            span.add_attribute("decision", decision.value)

            try:
                result = await self.workflow.record_decision(
                    request_id, reviewer_id, decision, comments, evidence_checked
                )

                # Calculate metrics
                completion_time = datetime.utcnow()
                duration_ms = (completion_time - start_time).total_seconds() * 1000
                review_duration_minutes = (completion_time - original_request.submitted_at).total_seconds() / 60

                # Calculate SLA deadline
                from .core import calculate_sla_deadline
                sla_deadline = calculate_sla_deadline(original_request.submitted_at, original_request.priority)

                # Track metrics
                if self.collector:
                    await self.collector.track_review_completion(
                        request_id=request_id,
                        reviewer_id=reviewer_id,
                        decision=decision,
                        priority=original_request.priority,
                        review_duration_minutes=int(review_duration_minutes),
                        evidence_reviewed_count=len(evidence_checked),
                        sla_deadline=sla_deadline,
                        completion_time=completion_time,
                        is_stale=decision == ReviewStatus.STALE,
                    )

                span.add_attribute("success", True)
                span.add_attribute("duration_ms", duration_ms)
                span.add_attribute("review_duration_minutes", review_duration_minutes)

                return result

            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                span.add_attribute("error", str(e))
                span.add_attribute("duration_ms", duration_ms)
                raise


# Global collector instance
_global_collector: Optional[ComplianceObservabilityCollector] = None


def initialize_compliance_observability(storage=None) -> ComplianceObservabilityCollector:
    """Initialize global compliance observability collector."""
    global _global_collector
    _global_collector = ComplianceObservabilityCollector(storage)
    return _global_collector


def get_global_collector() -> Optional[ComplianceObservabilityCollector]:
    """Get the global compliance observability collector."""
    return _global_collector