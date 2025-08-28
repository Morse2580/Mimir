"""
Observability domain events.
Events emitted by the observability module for other modules to consume.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from .contracts import Alert, Metric, SLOStatus, Severity


@dataclass(frozen=True)
class MetricRecorded:
    """
    Event emitted when a metric is successfully recorded.
    """
    metric: Metric
    recorded_at: datetime
    tenant: Optional[str] = None


@dataclass(frozen=True) 
class AlertTriggered:
    """
    Event emitted when an alert threshold is exceeded.
    """
    alert: Alert
    triggered_at: datetime
    tenant: Optional[str] = None


@dataclass(frozen=True)
class SLOViolated:
    """
    Event emitted when an SLO is violated.
    """
    slo_status: SLOStatus
    violated_at: datetime
    compliance_percent: float
    tenant: Optional[str] = None


@dataclass(frozen=True)
class PerformanceThresholdExceeded:
    """
    Event emitted when performance targets are exceeded.
    """
    operation: str
    actual_duration_ms: float
    target_duration_ms: float
    percentile: int
    exceeded_at: datetime
    tenant: Optional[str] = None


@dataclass(frozen=True)
class SecurityMetricViolation:
    """
    Event emitted for security-related metric violations.
    CRITICAL - requires immediate attention.
    """
    metric_name: str
    violation_type: str  # "pii_detected", "budget_exceeded", "circuit_open"
    current_value: float
    threshold: float
    severity: Severity
    violated_at: datetime
    details: Dict[str, str]
    tenant: Optional[str] = None


@dataclass(frozen=True)
class DashboardUpdateRequired:
    """
    Event emitted when dashboards need to be updated with new data.
    """
    dashboard_name: str
    metrics_updated: list[str]
    update_requested_at: datetime
    tenant: Optional[str] = None


@dataclass(frozen=True)
class MetricCollectionFailed:
    """
    Event emitted when metric collection fails.
    """
    metric_name: str
    error_message: str
    failed_at: datetime
    retry_count: int
    tenant: Optional[str] = None


@dataclass(frozen=True)
class BudgetThresholdCrossed:
    """
    Event emitted when budget utilization crosses defined thresholds.
    Integrates with cost module events.
    """
    current_utilization_percent: float
    threshold_percent: float
    threshold_type: str  # "warning", "alert", "escalation", "kill_switch"
    monthly_spend_eur: float
    crossed_at: datetime
    tenant: Optional[str] = None


@dataclass(frozen=True)
class CircuitBreakerStateChanged:
    """
    Event emitted when circuit breaker state changes.
    Integrates with parallel module events.
    """
    previous_state: str  # "closed", "open", "half_open"
    new_state: str
    failure_count: int
    changed_at: datetime
    service_name: str
    tenant: Optional[str] = None


@dataclass(frozen=True)
class DigestCompletionStatus:
    """
    Event emitted when daily digest completion is tracked.
    """
    completion_time_cet: datetime
    tier_a_count: int
    total_items: int
    target_time_cet: datetime
    is_on_time: bool
    completed_at: datetime
    tenant: Optional[str] = None