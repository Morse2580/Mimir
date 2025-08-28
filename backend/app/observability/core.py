"""
Observability Core - Pure Functions Only
NEVER include I/O operations in this module.

This module provides deterministic functions for metric calculations,
SLO compliance, and alert threshold evaluation for the Belgian RegOps platform.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .contracts import (
    Alert,
    AlertOperator,
    AlertRule,
    Failure,
    Metric,
    MetricType,
    MetricValidationError,
    PerformanceTarget,
    Result,
    SLODefinition,
    SLOStatus,
    Severity,
    Success,
)


# Standard metric naming conventions
METRIC_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
RESERVED_LABEL_NAMES = {"__name__", "__value__", "__timestamp__"}


def create_metric(
    name: str,
    value: float,
    labels: Optional[Dict[str, str]] = None,
    metric_type: MetricType = MetricType.GAUGE,
    timestamp: Optional[datetime] = None,
    unit: Optional[str] = None,
) -> Result[Metric, MetricValidationError]:
    """
    Create a standardized metric with validation.
    MUST be deterministic - same inputs produce same outputs.

    Args:
        name: Metric name following RegOps conventions
        value: Numeric value (must be finite)
        labels: Optional key-value labels
        metric_type: Type of metric (counter, gauge, histogram)
        timestamp: Optional timestamp (defaults to None for shell layer)
        unit: Optional unit description

    Returns:
        Result containing validated Metric or validation error
    """
    # Validate metric name
    if not name or not isinstance(name, str):
        return Failure(MetricValidationError("name", "Metric name must be non-empty string"))
    
    if not METRIC_NAME_PATTERN.match(name):
        return Failure(
            MetricValidationError(
                "name", 
                "Metric name must follow pattern: lowercase, underscores, dots for namespaces",
                name
            )
        )

    # Validate value
    if not isinstance(value, (int, float)):
        return Failure(MetricValidationError("value", "Metric value must be numeric"))
    
    if not (-float('inf') < value < float('inf')):
        return Failure(MetricValidationError("value", "Metric value must be finite"))

    # Validate labels
    clean_labels = labels or {}
    if not isinstance(clean_labels, dict):
        return Failure(MetricValidationError("labels", "Labels must be a dictionary"))
    
    for label_name in clean_labels:
        if label_name in RESERVED_LABEL_NAMES:
            return Failure(
                MetricValidationError(
                    "labels",
                    f"Label name '{label_name}' is reserved",
                    label_name
                )
            )

    # Use provided timestamp or None (shell layer will set)
    final_timestamp = timestamp or datetime.now(timezone.utc)

    return Success(
        Metric(
            name=name,
            value=float(value),
            labels=clean_labels,
            metric_type=metric_type,
            timestamp=final_timestamp,
            unit=unit,
        )
    )


def calculate_slo_compliance(
    target: float,
    actual: float,
    operator: AlertOperator,
) -> float:
    """
    Calculate SLO compliance as percentage (0.0 to 100.0).
    MUST be deterministic - same inputs produce same result.

    Args:
        target: Target value for the SLO
        actual: Actual measured value
        operator: Comparison operator (GT, LT, etc.)

    Returns:
        Compliance percentage (0.0-100.0)
    """
    if target == 0 and operator in [AlertOperator.LT, AlertOperator.LTE]:
        # Special case: target is 0 and we want less than
        return 100.0 if actual == 0 else 0.0
    
    if target == 0:
        # Avoid division by zero for other operators
        return 100.0 if actual == target else 0.0

    if operator == AlertOperator.LT:
        # actual should be < target
        compliance = max(0.0, min(100.0, (target - actual) / target * 100.0))
    elif operator == AlertOperator.LTE:
        # actual should be <= target  
        compliance = 100.0 if actual <= target else max(0.0, (target - actual) / target * 100.0)
    elif operator == AlertOperator.GT:
        # actual should be > target
        compliance = max(0.0, min(100.0, (actual - target) / target * 100.0))
    elif operator == AlertOperator.GTE:
        # actual should be >= target
        compliance = 100.0 if actual >= target else max(0.0, (actual - target) / target * 100.0)
    elif operator == AlertOperator.EQ:
        # actual should equal target (with small tolerance)
        tolerance = abs(target * 0.01)  # 1% tolerance
        compliance = 100.0 if abs(actual - target) <= tolerance else 0.0
    else:
        compliance = 0.0

    return round(compliance, 2)


def should_trigger_alert(
    metric_value: float,
    threshold: float,
    operator: AlertOperator,
) -> bool:
    """
    Determine if a metric value should trigger an alert.
    MUST be pure function - no side effects.

    Args:
        metric_value: Current metric value
        threshold: Alert threshold value
        operator: Comparison operator

    Returns:
        True if alert should be triggered, False otherwise
    """
    if operator == AlertOperator.GT:
        return metric_value > threshold
    elif operator == AlertOperator.GTE:
        return metric_value >= threshold
    elif operator == AlertOperator.LT:
        return metric_value < threshold
    elif operator == AlertOperator.LTE:
        return metric_value <= threshold
    elif operator == AlertOperator.EQ:
        # Use small tolerance for float comparison
        tolerance = abs(threshold * 0.001) if threshold != 0 else 0.001
        return abs(metric_value - threshold) <= tolerance
    else:
        return False


def validate_metric_name(name: str) -> bool:
    """
    Validate metric name follows RegOps conventions.
    MUST be deterministic.

    Args:
        name: Metric name to validate

    Returns:
        True if valid, False otherwise
    """
    if not name or not isinstance(name, str):
        return False
    
    return bool(METRIC_NAME_PATTERN.match(name))


def calculate_budget_alert_severity(utilization_percent: float) -> Severity:
    """
    Calculate alert severity based on budget utilization.
    Aligns with cost module thresholds.

    Args:
        utilization_percent: Budget utilization (0.0-100.0+)

    Returns:
        Appropriate alert severity
    """
    if utilization_percent >= 95.0:  # Kill switch threshold
        return Severity.CRITICAL
    elif utilization_percent >= 90.0:  # Escalation threshold
        return Severity.CRITICAL
    elif utilization_percent >= 80.0:  # Alert threshold
        return Severity.WARNING
    elif utilization_percent >= 50.0:  # Warning threshold
        return Severity.WARNING
    else:
        return Severity.INFO


def calculate_performance_score(
    actual_duration_ms: float,
    target_duration_ms: float,
) -> float:
    """
    Calculate performance score (0.0-1.0) based on actual vs target.
    Higher score is better performance.

    Args:
        actual_duration_ms: Actual operation duration in milliseconds
        target_duration_ms: Target duration in milliseconds

    Returns:
        Performance score from 0.0 (poor) to 1.0 (excellent)
    """
    if target_duration_ms <= 0:
        return 0.0
    
    if actual_duration_ms <= 0:
        return 1.0
    
    # Score decreases as actual exceeds target
    ratio = target_duration_ms / actual_duration_ms
    return min(1.0, max(0.0, ratio))


def get_business_metric_targets() -> Dict[str, float]:
    """
    Get target values for business metrics.
    MUST be deterministic and match requirements.

    Returns:
        Dictionary mapping metric names to target values
    """
    return {
        "digest.tier_a.count": 5.0,  # Minimum 5 Tier A items per digest
        "digest.completion.hour": 9.0,  # Must complete by 09:00 CET
        "parallel.calls.error_rate": 2.0,  # <2% error rate
        "ledger.verify.success_rate": 100.0,  # 100% verification success
        "clock.deadline.miss.rate": 0.0,  # 0% deadline misses
    }


def get_performance_targets() -> List[PerformanceTarget]:
    """
    Get all performance SLO targets as defined in requirements.
    MUST match claude.md specifications.

    Returns:
        List of PerformanceTarget definitions
    """
    return [
        PerformanceTarget(
            operation="pii_detection",
            target_ms=50,
            percentile=95,
            description="PII detection must complete under 50ms p95"
        ),
        PerformanceTarget(
            operation="cost_checking", 
            target_ms=10,
            percentile=95,
            description="Cost checking must complete under 10ms p95"
        ),
        PerformanceTarget(
            operation="onegate_export",
            target_ms=30 * 60 * 1000,  # 30 minutes in ms
            percentile=95, 
            description="OneGate export must complete under 30 minutes p95"
        ),
        PerformanceTarget(
            operation="xml_validation",
            target_ms=1000,  # 1 second
            percentile=95,
            description="XSD validation must complete under 1 second p95"
        ),
        PerformanceTarget(
            operation="incident_classification",
            target_ms=500,  # 500ms
            percentile=95,
            description="Incident classification must complete under 500ms p95"
        ),
    ]


def create_standard_alert_rules() -> List[AlertRule]:
    """
    Create standard alert rules for RegOps platform.
    MUST include all critical alerts from requirements.

    Returns:
        List of configured AlertRule instances
    """
    return [
        # Security alerts - CRITICAL
        AlertRule(
            metric_name="pii.violations.total",
            threshold=0.0,
            operator=AlertOperator.GT,
            severity=Severity.CRITICAL,
            message_template="PII violation detected! Count: {value}. Immediate investigation required.",
        ),
        AlertRule(
            metric_name="budget.utilization.percent",
            threshold=95.0,
            operator=AlertOperator.GTE,
            severity=Severity.CRITICAL,
            message_template="Budget kill switch activated! Utilization: {value}%. All Parallel.ai calls blocked.",
        ),
        AlertRule(
            metric_name="circuit.breaker.state",
            threshold=1.0,
            operator=AlertOperator.EQ,
            severity=Severity.CRITICAL,
            message_template="Circuit breaker opened! State: {value}. External API calls failing.",
        ),
        
        # Business alerts
        AlertRule(
            metric_name="digest.completion.hour",
            threshold=9.5,  # 09:30 CET
            operator=AlertOperator.GT,
            severity=Severity.CRITICAL,
            message_template="Daily digest not completed by 09:30 CET! Current time: {value}",
        ),
        AlertRule(
            metric_name="clock.deadline.miss.total",
            threshold=0.0,
            operator=AlertOperator.GT,
            severity=Severity.WARNING,
            message_template="Deadline missed! Total misses: {value}",
        ),
        
        # Performance alerts
        AlertRule(
            metric_name="pii.detection.duration_ms",
            threshold=50.0,
            operator=AlertOperator.GT,
            severity=Severity.WARNING,
            message_template="PII detection slow! Duration: {value}ms (target: <50ms p95)",
        ),
        AlertRule(
            metric_name="cost.check.duration_ms", 
            threshold=10.0,
            operator=AlertOperator.GT,
            severity=Severity.WARNING,
            message_template="Cost checking slow! Duration: {value}ms (target: <10ms p95)",
        ),
        AlertRule(
            metric_name="onegate.export.duration_ms",
            threshold=30 * 60 * 1000,  # 30 minutes
            operator=AlertOperator.GT,
            severity=Severity.CRITICAL,
            message_template="OneGate export timeout! Duration: {value}ms (target: <30 minutes)",
        ),
    ]


def is_metric_name_reserved(name: str) -> bool:
    """
    Check if metric name conflicts with reserved names.

    Args:
        name: Metric name to check

    Returns:
        True if name is reserved, False if available
    """
    reserved_prefixes = [
        "system.",
        "process.", 
        "http.server.",
        "http.client.",
        "db.",
        "cache.",
    ]
    
    return any(name.startswith(prefix) for prefix in reserved_prefixes)