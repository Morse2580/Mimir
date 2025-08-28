"""
Test the observability core module - pure functions only.
Tests metric creation, SLO calculations, and alert threshold logic.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from ..contracts import (
    AlertOperator,
    Failure,
    MetricType,
    MetricValidationError,
    PerformanceTarget,
    Severity,
    Success,
)
from ..core import (
    calculate_budget_alert_severity,
    calculate_performance_score,
    calculate_slo_compliance,
    create_metric,
    create_standard_alert_rules,
    get_business_metric_targets,
    get_performance_targets,
    is_metric_name_reserved,
    should_trigger_alert,
    validate_metric_name,
)


class TestMetricCreation:
    """Test metric creation and validation."""

    def test_create_valid_metric(self):
        """Test creating a valid metric."""
        result = create_metric(
            name="test.metric.count",
            value=42.5,
            labels={"service": "regops", "env": "test"},
            metric_type=MetricType.GAUGE,
        )
        
        assert isinstance(result, Success)
        metric = result.value
        assert metric.name == "test.metric.count"
        assert metric.value == 42.5
        assert metric.labels == {"service": "regops", "env": "test"}
        assert metric.metric_type == MetricType.GAUGE

    def test_create_metric_with_invalid_name(self):
        """Test creating metric with invalid name."""
        invalid_names = [
            "",  # Empty
            "Invalid-Name",  # Contains dash
            "UPPERCASE",  # Uppercase
            "123numbers",  # Starts with number
            "special@chars",  # Special characters
        ]
        
        for invalid_name in invalid_names:
            result = create_metric(name=invalid_name, value=1.0)
            assert isinstance(result, Failure)
            assert result.error.field == "name"

    def test_create_metric_with_invalid_value(self):
        """Test creating metric with invalid value."""
        invalid_values = [float('inf'), float('-inf'), float('nan'), "not_a_number"]
        
        for invalid_value in invalid_values:
            result = create_metric(name="test.metric", value=invalid_value)
            if invalid_value == "not_a_number":
                assert isinstance(result, Failure)
                assert result.error.field == "value"
            else:
                assert isinstance(result, Failure)
                assert result.error.field == "value"

    def test_create_metric_with_reserved_labels(self):
        """Test creating metric with reserved label names."""
        reserved_labels = ["__name__", "__value__", "__timestamp__"]
        
        for reserved_label in reserved_labels:
            result = create_metric(
                name="test.metric",
                value=1.0,
                labels={reserved_label: "should_fail"}
            )
            assert isinstance(result, Failure)
            assert result.error.field == "labels"
            assert reserved_label in result.error.message


class TestMetricNameValidation:
    """Test metric name validation logic."""

    def test_valid_metric_names(self):
        """Test valid metric names."""
        valid_names = [
            "simple",
            "with_underscores", 
            "with.dots.namespace",
            "complex.namespace.with_underscores.count",
            "a",  # Single character
            "parallel.calls.total",
            "pii.violations.count",
            "budget.utilization.percent",
        ]
        
        for name in valid_names:
            assert validate_metric_name(name), f"Expected {name} to be valid"

    def test_invalid_metric_names(self):
        """Test invalid metric names."""
        invalid_names = [
            "",  # Empty
            "Invalid-Name",  # Contains dash  
            "UPPERCASE",  # Uppercase
            "123numbers",  # Starts with number
            "special@chars",  # Special characters
            "end.",  # Ends with dot
            ".start",  # Starts with dot
            "double..dots",  # Double dots
        ]
        
        for name in invalid_names:
            assert not validate_metric_name(name), f"Expected {name} to be invalid"

    def test_reserved_metric_names(self):
        """Test reserved metric name detection."""
        reserved_names = [
            "system.cpu.usage",
            "process.memory.rss", 
            "http.server.requests",
            "http.client.duration",
            "db.query.time",
            "cache.hits",
        ]
        
        for name in reserved_names:
            assert is_metric_name_reserved(name), f"Expected {name} to be reserved"

    def test_allowed_metric_names(self):
        """Test allowed (non-reserved) metric names."""
        allowed_names = [
            "parallel.calls.total",
            "pii.violations.count",
            "budget.utilization.percent",
            "digest.tier_a.count",
            "clock.deadline.miss",
            "ledger.verify.status",
        ]
        
        for name in allowed_names:
            assert not is_metric_name_reserved(name), f"Expected {name} to be allowed"


class TestSLOCalculations:
    """Test SLO compliance calculations."""

    def test_calculate_slo_compliance_less_than(self):
        """Test SLO compliance for less than operator."""
        # Good case: actual < target
        compliance = calculate_slo_compliance(100.0, 50.0, AlertOperator.LT)
        assert compliance == 50.0
        
        # Bad case: actual > target
        compliance = calculate_slo_compliance(100.0, 150.0, AlertOperator.LT)
        assert compliance == 0.0
        
        # Edge case: actual == target
        compliance = calculate_slo_compliance(100.0, 100.0, AlertOperator.LT)
        assert compliance == 0.0

    def test_calculate_slo_compliance_greater_than(self):
        """Test SLO compliance for greater than operator."""
        # Good case: actual > target
        compliance = calculate_slo_compliance(100.0, 150.0, AlertOperator.GT)
        assert compliance == 50.0
        
        # Bad case: actual < target  
        compliance = calculate_slo_compliance(100.0, 50.0, AlertOperator.GT)
        assert compliance == 0.0

    def test_calculate_slo_compliance_equals(self):
        """Test SLO compliance for equals operator."""
        # Perfect match
        compliance = calculate_slo_compliance(100.0, 100.0, AlertOperator.EQ)
        assert compliance == 100.0
        
        # Within tolerance (1%)
        compliance = calculate_slo_compliance(100.0, 100.5, AlertOperator.EQ)
        assert compliance == 100.0
        
        # Outside tolerance
        compliance = calculate_slo_compliance(100.0, 102.0, AlertOperator.EQ)
        assert compliance == 0.0

    def test_calculate_slo_compliance_zero_target(self):
        """Test SLO compliance with zero target."""
        # Zero target with LT operator
        compliance = calculate_slo_compliance(0.0, 0.0, AlertOperator.LT)
        assert compliance == 100.0
        
        compliance = calculate_slo_compliance(0.0, 1.0, AlertOperator.LT)
        assert compliance == 0.0


class TestAlertThresholds:
    """Test alert threshold evaluation."""

    def test_should_trigger_alert_greater_than(self):
        """Test GT alert triggering."""
        assert should_trigger_alert(150.0, 100.0, AlertOperator.GT)
        assert not should_trigger_alert(50.0, 100.0, AlertOperator.GT)
        assert not should_trigger_alert(100.0, 100.0, AlertOperator.GT)

    def test_should_trigger_alert_less_than(self):
        """Test LT alert triggering."""
        assert should_trigger_alert(50.0, 100.0, AlertOperator.LT)
        assert not should_trigger_alert(150.0, 100.0, AlertOperator.LT)
        assert not should_trigger_alert(100.0, 100.0, AlertOperator.LT)

    def test_should_trigger_alert_equals(self):
        """Test EQ alert triggering."""
        assert should_trigger_alert(100.0, 100.0, AlertOperator.EQ)
        assert should_trigger_alert(100.05, 100.0, AlertOperator.EQ)  # Within tolerance
        assert not should_trigger_alert(102.0, 100.0, AlertOperator.EQ)  # Outside tolerance

    def test_should_trigger_alert_with_floats(self):
        """Test alert triggering with floating point values."""
        # Test precision handling
        assert should_trigger_alert(95.001, 95.0, AlertOperator.GT)
        assert not should_trigger_alert(94.999, 95.0, AlertOperator.GT)


class TestBudgetAlertSeverity:
    """Test budget alert severity calculation."""

    def test_calculate_budget_alert_severity(self):
        """Test budget alert severity mapping."""
        # Normal range
        assert calculate_budget_alert_severity(25.0) == Severity.INFO
        
        # Warning range (50-80%)
        assert calculate_budget_alert_severity(60.0) == Severity.WARNING
        
        # Alert range (80-90%)
        assert calculate_budget_alert_severity(85.0) == Severity.WARNING
        
        # Escalation range (90-95%)
        assert calculate_budget_alert_severity(92.0) == Severity.CRITICAL
        
        # Kill switch range (95%+)
        assert calculate_budget_alert_severity(97.0) == Severity.CRITICAL
        
        # Over budget
        assert calculate_budget_alert_severity(105.0) == Severity.CRITICAL

    def test_calculate_budget_alert_severity_edge_cases(self):
        """Test budget alert severity edge cases."""
        # Exact thresholds
        assert calculate_budget_alert_severity(50.0) == Severity.WARNING
        assert calculate_budget_alert_severity(80.0) == Severity.WARNING
        assert calculate_budget_alert_severity(90.0) == Severity.CRITICAL
        assert calculate_budget_alert_severity(95.0) == Severity.CRITICAL


class TestPerformanceScoring:
    """Test performance score calculations."""

    def test_calculate_performance_score(self):
        """Test performance score calculation."""
        # Perfect performance (actual == target)
        score = calculate_performance_score(100.0, 100.0)
        assert score == 1.0
        
        # Better than target
        score = calculate_performance_score(50.0, 100.0)
        assert score == 1.0  # Capped at 1.0
        
        # Worse than target
        score = calculate_performance_score(200.0, 100.0)
        assert score == 0.5
        
        # Much worse than target
        score = calculate_performance_score(1000.0, 100.0)
        assert score == 0.1

    def test_calculate_performance_score_edge_cases(self):
        """Test performance score edge cases."""
        # Zero target
        score = calculate_performance_score(100.0, 0.0)
        assert score == 0.0
        
        # Zero actual
        score = calculate_performance_score(0.0, 100.0)
        assert score == 1.0
        
        # Negative values handled gracefully
        score = calculate_performance_score(-100.0, 100.0)
        assert score >= 0.0


class TestBusinessMetrics:
    """Test business metric configuration."""

    def test_get_business_metric_targets(self):
        """Test business metric targets are properly defined."""
        targets = get_business_metric_targets()
        
        # Required metrics
        required_metrics = [
            "digest.tier_a.count",
            "digest.completion.hour", 
            "parallel.calls.error_rate",
            "ledger.verify.success_rate",
            "clock.deadline.miss.rate",
        ]
        
        for metric in required_metrics:
            assert metric in targets
            assert isinstance(targets[metric], (int, float))
            assert targets[metric] >= 0

    def test_get_performance_targets(self):
        """Test performance targets are properly defined."""
        targets = get_performance_targets()
        
        assert len(targets) > 0
        
        required_operations = [
            "pii_detection",
            "cost_checking", 
            "onegate_export",
            "xml_validation",
            "incident_classification",
        ]
        
        operation_names = [t.operation for t in targets]
        for operation in required_operations:
            assert operation in operation_names
        
        # Validate target structure
        for target in targets:
            assert isinstance(target, PerformanceTarget)
            assert target.target_ms > 0
            assert target.percentile in [50, 90, 95, 99]
            assert target.description
            assert target.operation

    def test_performance_targets_match_requirements(self):
        """Test performance targets match claude.md requirements."""
        targets = get_performance_targets()
        target_map = {t.operation: t for t in targets}
        
        # Specific requirements from claude.md
        assert target_map["pii_detection"].target_ms == 50
        assert target_map["cost_checking"].target_ms == 10
        assert target_map["onegate_export"].target_ms == 30 * 60 * 1000  # 30 minutes


class TestStandardAlertRules:
    """Test standard alert rule configuration."""

    def test_create_standard_alert_rules(self):
        """Test standard alert rules are properly configured."""
        rules = create_standard_alert_rules()
        
        assert len(rules) > 0
        
        # Critical security rules
        pii_rule = next((r for r in rules if "pii.violations" in r.metric_name), None)
        assert pii_rule is not None
        assert pii_rule.severity == Severity.CRITICAL
        assert pii_rule.threshold == 0.0
        assert pii_rule.operator == AlertOperator.GT
        
        # Budget kill switch rule
        budget_rule = next((r for r in rules if "budget.utilization" in r.metric_name), None)
        assert budget_rule is not None
        assert budget_rule.severity == Severity.CRITICAL
        assert budget_rule.threshold == 95.0
        
        # Performance rules
        performance_rules = [r for r in rules if "duration_ms" in r.metric_name]
        assert len(performance_rules) > 0

    def test_alert_rules_have_required_fields(self):
        """Test all alert rules have required fields."""
        rules = create_standard_alert_rules()
        
        for rule in rules:
            assert rule.metric_name
            assert rule.threshold is not None
            assert rule.operator in AlertOperator
            assert rule.severity in Severity
            assert rule.message_template
            assert "{value}" in rule.message_template  # Must include placeholder


# Integration test for the complete flow
class TestMetricFlow:
    """Test complete metric creation and evaluation flow."""

    def test_complete_metric_workflow(self):
        """Test creating metric and evaluating alerts."""
        # Create a metric
        result = create_metric(
            name="pii.violations.total",
            value=1.0,  # Should trigger alert
            labels={"module": "parallel"},
            metric_type=MetricType.COUNTER,
        )
        
        assert isinstance(result, Success)
        metric = result.value
        
        # Check if it would trigger alerts
        rules = create_standard_alert_rules()
        pii_rule = next((r for r in rules if "pii.violations" in r.metric_name), None)
        
        assert pii_rule is not None
        should_alert = should_trigger_alert(
            metric.value,
            pii_rule.threshold,
            pii_rule.operator,
        )
        
        assert should_alert  # PII violation should always alert

    def test_performance_metric_workflow(self):
        """Test performance metric creation and SLO evaluation."""
        # Create a performance metric that exceeds target
        result = create_metric(
            name="pii.detection.duration_ms",
            value=75.0,  # Exceeds 50ms target
            labels={"operation": "pii_detection"},
            metric_type=MetricType.HISTOGRAM,
        )
        
        assert isinstance(result, Success)
        metric = result.value
        
        # Check performance score
        targets = get_performance_targets()
        pii_target = next((t for t in targets if t.operation == "pii_detection"), None)
        
        assert pii_target is not None
        score = calculate_performance_score(metric.value, pii_target.target_ms)
        assert score < 1.0  # Should be degraded performance