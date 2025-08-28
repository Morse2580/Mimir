"""
Observability integration for Cost module.
Collects metrics for budget utilization, cost checking, and kill switch status.
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from ..observability.contracts import MetricType
from ..observability.core import create_metric
from ..observability.integration import get_tracer, TrackedOperation
from ..observability.shell import record_metric

logger = logging.getLogger(__name__)

# Get tracer for this module
tracer = get_tracer("regops.cost")


class CostObservabilityCollector:
    """
    Collects observability metrics for the cost tracking module.
    Integrates with existing cost tracker and budget management.
    """

    def __init__(self, storage=None):
        self.storage = storage

    async def track_cost_check(
        self,
        duration_ms: float,
        allowed: bool,
        api_type: str,
        processor: str,
        tenant: str,
        current_spend_eur: Decimal,
        proposed_cost_eur: Decimal,
        utilization_percent: Decimal,
    ) -> None:
        """
        Track cost checking metrics.

        Args:
            duration_ms: Time taken for cost check (<10ms target)
            allowed: Whether the API call was allowed
            api_type: Type of API ("search" or "task")
            processor: Processor type ("base", "pro", "core")
            tenant: Tenant identifier
            current_spend_eur: Current monthly spend
            proposed_cost_eur: Cost of proposed API call
            utilization_percent: Budget utilization percentage
        """
        try:
            labels = {
                "api_type": api_type,
                "processor": processor,
                "tenant": tenant,
                "allowed": str(allowed).lower(),
            }

            # Record cost checking duration (SLO: <10ms)
            await self._record_metric(
                name="cost.check.duration_ms",
                value=float(duration_ms),
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record budget utilization (critical business metric)
            await self._record_metric(
                name="budget.utilization.percent",
                value=float(utilization_percent),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Record current monthly spend
            await self._record_metric(
                name="budget.spend.eur",
                value=float(current_spend_eur),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Record cost check attempts
            await self._record_metric(
                name="cost.checks.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record blocked requests if not allowed
            if not allowed:
                await self._record_metric(
                    name="cost.checks.blocked.total",
                    value=1.0,
                    metric_type=MetricType.COUNTER,
                    labels=labels,
                )

        except Exception as e:
            logger.error(f"Failed to track cost check metrics: {e}")

    async def track_cost_recording(
        self,
        duration_ms: float,
        api_type: str,
        processor: str,
        cost_eur: Decimal,
        tenant: str,
        use_case: str,
        new_total_spend: Decimal,
        utilization_percent: Decimal,
    ) -> None:
        """
        Track cost recording metrics.

        Args:
            duration_ms: Time taken to record cost (<50ms target)
            api_type: Type of API
            processor: Processor type
            cost_eur: Cost recorded in euros
            tenant: Tenant identifier
            use_case: Use case description
            new_total_spend: New total monthly spend
            utilization_percent: Updated budget utilization
        """
        try:
            labels = {
                "api_type": api_type,
                "processor": processor,
                "tenant": tenant,
                "use_case": use_case,
            }

            # Record cost recording duration (SLO: <50ms)
            await self._record_metric(
                name="cost.recording.duration_ms",
                value=float(duration_ms),
                metric_type=MetricType.HISTOGRAM,
                labels=labels,
            )

            # Record API costs by type and processor
            await self._record_metric(
                name="api.costs.eur",
                value=float(cost_eur),
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Update budget utilization
            await self._record_metric(
                name="budget.utilization.percent",
                value=float(utilization_percent),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Update total spend
            await self._record_metric(
                name="budget.spend.eur",
                value=float(new_total_spend),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Record successful cost recording
            await self._record_metric(
                name="cost.recordings.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

        except Exception as e:
            logger.error(f"Failed to track cost recording metrics: {e}")

    async def track_kill_switch_activation(
        self,
        tenant: str,
        current_spend_eur: Decimal,
        proposed_cost_eur: Decimal,
        utilization_percent: Decimal,
        threshold_percent: Decimal,
    ) -> None:
        """
        Track kill switch activation event.

        Args:
            tenant: Tenant identifier
            current_spend_eur: Current monthly spend
            proposed_cost_eur: Proposed cost that triggered kill switch
            utilization_percent: Current utilization percentage
            threshold_percent: Kill switch threshold (95%)
        """
        try:
            labels = {"tenant": tenant, "trigger": "automatic"}

            # Record kill switch activation
            await self._record_metric(
                name="budget.kill_switch.activations.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record kill switch state (critical security metric)
            await self._record_metric(
                name="budget.kill_switch.active",
                value=1.0,  # 1 = active, 0 = inactive
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Record spend at activation
            await self._record_metric(
                name="budget.kill_switch.spend_at_activation.eur",
                value=float(current_spend_eur),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Record utilization at activation
            await self._record_metric(
                name="budget.kill_switch.utilization_at_activation.percent",
                value=float(utilization_percent),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

        except Exception as e:
            logger.error(f"Failed to track kill switch activation metrics: {e}")

    async def track_kill_switch_override(
        self,
        tenant: str,
        overridden_by: str,
        approval_level: str,
        current_spend_eur: Decimal,
    ) -> None:
        """
        Track kill switch override event.

        Args:
            tenant: Tenant identifier
            overridden_by: User who overrode the kill switch
            approval_level: Level of approval ("c_level", "emergency")
            current_spend_eur: Current spend when overridden
        """
        try:
            labels = {
                "tenant": tenant,
                "overridden_by": overridden_by,
                "approval_level": approval_level,
            }

            # Record kill switch override
            await self._record_metric(
                name="budget.kill_switch.overrides.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record kill switch state as inactive
            await self._record_metric(
                name="budget.kill_switch.active",
                value=0.0,  # 0 = inactive
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Record spend at override
            await self._record_metric(
                name="budget.kill_switch.spend_at_override.eur",
                value=float(current_spend_eur),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

        except Exception as e:
            logger.error(f"Failed to track kill switch override metrics: {e}")

    async def track_budget_threshold_crossing(
        self,
        tenant: str,
        threshold_percent: Decimal,
        current_spend_eur: Decimal,
        utilization_percent: Decimal,
        previous_status: str,
        new_status: str,
    ) -> None:
        """
        Track budget threshold crossing events.

        Args:
            tenant: Tenant identifier
            threshold_percent: Threshold that was crossed
            current_spend_eur: Current monthly spend
            utilization_percent: Current utilization percentage
            previous_status: Previous budget status
            new_status: New budget status
        """
        try:
            labels = {
                "tenant": tenant,
                "threshold_percent": str(float(threshold_percent)),
                "previous_status": previous_status,
                "new_status": new_status,
            }

            # Record threshold crossing
            await self._record_metric(
                name="budget.thresholds.crossed.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record current budget status
            status_values = {
                "normal": 0,
                "warning": 1,
                "alert": 2,
                "escalation": 3,
                "kill_switch": 4,
            }
            status_value = status_values.get(new_status, 0)

            await self._record_metric(
                name="budget.status",
                value=float(status_value),
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant, "status": new_status},
            )

        except Exception as e:
            logger.error(f"Failed to track budget threshold crossing metrics: {e}")

    async def track_monthly_budget_reset(
        self,
        tenant: str,
        previous_spend_eur: Decimal,
        reset_month: str,
    ) -> None:
        """
        Track monthly budget reset event.

        Args:
            tenant: Tenant identifier
            previous_spend_eur: Previous month's total spend
            reset_month: Month being reset (YYYY-MM format)
        """
        try:
            labels = {
                "tenant": tenant,
                "month": reset_month,
            }

            # Record budget reset
            await self._record_metric(
                name="budget.resets.total",
                value=1.0,
                metric_type=MetricType.COUNTER,
                labels=labels,
            )

            # Record previous month's final spend
            await self._record_metric(
                name="budget.previous_month.final_spend.eur",
                value=float(previous_spend_eur),
                metric_type=MetricType.GAUGE,
                labels=labels,
            )

            # Reset current metrics to zero
            await self._record_metric(
                name="budget.spend.eur",
                value=0.0,
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            await self._record_metric(
                name="budget.utilization.percent",
                value=0.0,
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

            # Reset kill switch state
            await self._record_metric(
                name="budget.kill_switch.active",
                value=0.0,
                metric_type=MetricType.GAUGE,
                labels={"tenant": tenant},
            )

        except Exception as e:
            logger.error(f"Failed to track budget reset metrics: {e}")

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


# Instrumented wrapper for cost tracking operations
class InstrumentedCostTracker:
    """
    Wrapper around CostTracker that tracks metrics.
    """

    def __init__(self, cost_tracker, collector: Optional[CostObservabilityCollector] = None):
        self.cost_tracker = cost_tracker
        self.collector = collector

    async def check_budget_before_call_with_metrics(
        self,
        api_type: str,
        processor: str,
        tenant: str,
        use_case: str = "default",
    ):
        """
        Pre-flight budget check with metrics tracking.
        """
        start_time = datetime.utcnow()

        with TrackedOperation("cost_check", tracer) as span:
            span.add_attribute("api_type", api_type)
            span.add_attribute("processor", processor)
            span.add_attribute("tenant", tenant)

            try:
                result = await self.cost_tracker.check_budget_before_call(
                    api_type, processor, tenant, use_case
                )

                # Calculate duration
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

                # Track metrics
                if self.collector:
                    await self.collector.track_cost_check(
                        duration_ms=duration_ms,
                        allowed=result.allowed,
                        api_type=api_type,
                        processor=processor,
                        tenant=tenant,
                        current_spend_eur=result.current_spend_eur,
                        proposed_cost_eur=result.proposed_cost_eur,
                        utilization_percent=result.utilization_after_percent,
                    )

                span.add_attribute("allowed", result.allowed)
                span.add_attribute("duration_ms", duration_ms)
                span.add_attribute("utilization_percent", float(result.utilization_after_percent))

                return result

            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                span.add_attribute("error", str(e))
                span.add_attribute("duration_ms", duration_ms)
                raise

    async def record_api_cost_with_metrics(
        self,
        api_type: str,
        processor: str,
        tenant: str,
        use_case: str,
        request_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """
        Record API cost with metrics tracking.
        """
        start_time = datetime.utcnow()

        with TrackedOperation("cost_recording", tracer) as span:
            span.add_attribute("api_type", api_type)
            span.add_attribute("processor", processor)
            span.add_attribute("tenant", tenant)

            try:
                result = await self.cost_tracker.record_api_cost(
                    api_type, processor, tenant, use_case, request_id, metadata
                )

                # Calculate duration
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

                # Get updated budget state
                budget_state = await self.cost_tracker.get_budget_state(tenant)

                # Track metrics
                if self.collector:
                    await self.collector.track_cost_recording(
                        duration_ms=duration_ms,
                        api_type=api_type,
                        processor=processor,
                        cost_eur=result.cost_eur,
                        tenant=tenant,
                        use_case=use_case,
                        new_total_spend=budget_state.current_spend_eur,
                        utilization_percent=budget_state.utilization_percent,
                    )

                span.add_attribute("cost_eur", float(result.cost_eur))
                span.add_attribute("duration_ms", duration_ms)
                span.add_attribute("utilization_percent", float(budget_state.utilization_percent))

                return result

            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                span.add_attribute("error", str(e))
                span.add_attribute("duration_ms", duration_ms)
                raise


# Global collector instance
_global_collector: Optional[CostObservabilityCollector] = None


def initialize_cost_observability(storage=None) -> CostObservabilityCollector:
    """Initialize global cost observability collector."""
    global _global_collector
    _global_collector = CostObservabilityCollector(storage)
    return _global_collector


def get_global_collector() -> Optional[CostObservabilityCollector]:
    """Get the global cost observability collector."""
    return _global_collector