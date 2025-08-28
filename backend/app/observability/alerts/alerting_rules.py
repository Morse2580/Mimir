"""
Alerting rules configuration for Belgian RegOps Platform.
Defines all critical alerts with proper thresholds and escalation paths.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum

from ..contracts import AlertRule, AlertOperator, Severity


class AlertChannel(Enum):
    """Alert notification channels."""
    EMAIL = "email"
    TEAMS = "teams"
    PAGERDUTY = "pagerduty"
    SLACK = "slack"
    WEBHOOK = "webhook"


class EscalationLevel(Enum):
    """Alert escalation levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass(frozen=True)
class AlertConfig:
    """Complete alert configuration."""
    rule: AlertRule
    channels: List[AlertChannel]
    escalation_level: EscalationLevel
    runbook_url: Optional[str] = None
    auto_resolve: bool = True
    silence_duration_minutes: int = 60


def get_security_alert_rules() -> List[AlertConfig]:
    """
    Get all security-related alert rules.
    These are the most critical alerts that require immediate attention.
    """
    return [
        # PII Violations - CRITICAL (MUST = 0)
        AlertConfig(
            rule=AlertRule(
                metric_name="pii.violations.total",
                threshold=0.0,
                operator=AlertOperator.GT,
                severity=Severity.CRITICAL,
                message_template="🚨 CRITICAL: PII violation detected! Count: {value}. "
                               "All external API calls must be reviewed immediately. "
                               "This is a potential GDPR/data protection breach.",
            ),
            channels=[AlertChannel.PAGERDUTY, AlertChannel.TEAMS, AlertChannel.EMAIL],
            escalation_level=EscalationLevel.EMERGENCY,
            runbook_url="https://wiki.company.com/regops/pii-violation-response",
            auto_resolve=False,  # Requires manual investigation
            silence_duration_minutes=0,  # Cannot be silenced
        ),

        # Budget Kill Switch - CRITICAL
        AlertConfig(
            rule=AlertRule(
                metric_name="budget.utilization.percent",
                threshold=95.0,
                operator=AlertOperator.GTE,
                severity=Severity.CRITICAL,
                message_template="🔴 CRITICAL: Budget kill switch activated! "
                               "Utilization: {value}% (≥95%). "
                               "All Parallel.ai calls are now BLOCKED. "
                               "C-level approval required to override.",
            ),
            channels=[AlertChannel.PAGERDUTY, AlertChannel.TEAMS],
            escalation_level=EscalationLevel.CRITICAL,
            runbook_url="https://wiki.company.com/regops/kill-switch-response",
            auto_resolve=True,
            silence_duration_minutes=30,
        ),

        # Budget Warning Thresholds
        AlertConfig(
            rule=AlertRule(
                metric_name="budget.utilization.percent",
                threshold=90.0,
                operator=AlertOperator.GTE,
                severity=Severity.WARNING,
                message_template="⚠️ WARNING: Budget escalation threshold reached! "
                               "Utilization: {value}% (≥90%). "
                               "Management notification required. Kill switch at 95%.",
            ),
            channels=[AlertChannel.TEAMS, AlertChannel.EMAIL],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/budget-management",
            auto_resolve=True,
            silence_duration_minutes=120,
        ),

        # Circuit Breaker Open - CRITICAL
        AlertConfig(
            rule=AlertRule(
                metric_name="circuit.breaker.state",
                threshold=1.0,
                operator=AlertOperator.EQ,
                severity=Severity.CRITICAL,
                message_template="🔌 CRITICAL: Circuit breaker OPEN! State: {value}. "
                               "External API calls failing. "
                               "Platform in degraded mode. "
                               "Investigate Parallel.ai connectivity immediately.",
            ),
            channels=[AlertChannel.PAGERDUTY, AlertChannel.TEAMS],
            escalation_level=EscalationLevel.CRITICAL,
            runbook_url="https://wiki.company.com/regops/circuit-breaker-response",
            auto_resolve=True,
            silence_duration_minutes=15,
        ),

        # Evidence Ledger Integrity - CRITICAL
        AlertConfig(
            rule=AlertRule(
                metric_name="ledger.verify.ok",
                threshold=1.0,
                operator=AlertOperator.LT,
                severity=Severity.CRITICAL,
                message_template="🔐 CRITICAL: Evidence ledger integrity FAILURE! Status: {value}. "
                               "Hash chain broken. Audit trail compromised. "
                               "This affects regulatory compliance evidence. "
                               "Immediate forensic investigation required.",
            ),
            channels=[AlertChannel.PAGERDUTY, AlertChannel.TEAMS, AlertChannel.EMAIL],
            escalation_level=EscalationLevel.EMERGENCY,
            runbook_url="https://wiki.company.com/regops/ledger-integrity-response",
            auto_resolve=False,  # Requires manual verification
            silence_duration_minutes=0,  # Cannot be silenced
        ),
    ]


def get_business_alert_rules() -> List[AlertConfig]:
    """
    Get business-critical alert rules.
    These affect regulatory compliance and business operations.
    """
    return [
        # DORA Deadline Miss - CRITICAL
        AlertConfig(
            rule=AlertRule(
                metric_name="clock.deadline.miss.total",
                threshold=0.0,
                operator=AlertOperator.GT,
                severity=Severity.CRITICAL,
                message_template="📅 CRITICAL: DORA deadline MISSED! "
                               "Count: {value}. This is a regulatory compliance violation. "
                               "NBB/FSMA notification may be overdue. "
                               "Immediate compliance team notification required.",
            ),
            channels=[AlertChannel.PAGERDUTY, AlertChannel.TEAMS, AlertChannel.EMAIL],
            escalation_level=EscalationLevel.CRITICAL,
            runbook_url="https://wiki.company.com/regops/deadline-miss-response",
            auto_resolve=False,
            silence_duration_minutes=0,
        ),

        # Daily Digest Late - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="digest.completion.hour",
                threshold=9.5,  # 09:30 CET
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="🕘 WARNING: Daily digest completion DELAYED! "
                               "Completed at hour: {value} (target: ≤09:00 CET). "
                               "Regulatory monitoring may be impacted.",
            ),
            channels=[AlertChannel.TEAMS, AlertChannel.EMAIL],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/digest-monitoring",
            auto_resolve=True,
            silence_duration_minutes=360,  # 6 hours
        ),

        # Tier A Count Low - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="digest.tier_a.count",
                threshold=3.0,
                operator=AlertOperator.LT,
                severity=Severity.WARNING,
                message_template="📉 WARNING: Low Tier A regulatory items found! "
                               "Count: {value} (expected: ≥5). "
                               "May indicate monitoring issues or regulatory quiet period.",
            ),
            channels=[AlertChannel.TEAMS],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/tier-a-monitoring",
            auto_resolve=True,
            silence_duration_minutes=240,  # 4 hours
        ),

        # Compliance Review SLA Breach - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="compliance.reviews.sla_breached.total",
                threshold=0.0,
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="⏰ WARNING: Compliance review SLA breached! "
                               "Count: {value}. Legal team capacity may be exceeded. "
                               "Review queue management needed.",
            ),
            channels=[AlertChannel.TEAMS, AlertChannel.EMAIL],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/review-sla-management",
            auto_resolve=True,
            silence_duration_minutes=180,  # 3 hours
        ),
    ]


def get_performance_alert_rules() -> List[AlertConfig]:
    """
    Get performance-related alert rules.
    These monitor SLO compliance and system performance.
    """
    return [
        # PII Detection Slow - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="pii.detection.duration_ms",
                threshold=50.0,
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="🐌 WARNING: PII detection performance degraded! "
                               "p95 Duration: {value}ms (SLO: <50ms). "
                               "May impact API response times.",
            ),
            channels=[AlertChannel.TEAMS],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/performance-tuning",
            auto_resolve=True,
            silence_duration_minutes=60,
        ),

        # Cost Checking Slow - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="cost.check.duration_ms",
                threshold=10.0,
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="🐌 WARNING: Cost checking performance degraded! "
                               "p95 Duration: {value}ms (SLO: <10ms). "
                               "Budget checks taking too long.",
            ),
            channels=[AlertChannel.TEAMS],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/performance-tuning",
            auto_resolve=True,
            silence_duration_minutes=60,
        ),

        # OneGate Export Timeout - CRITICAL
        AlertConfig(
            rule=AlertRule(
                metric_name="onegate.export.duration_ms",
                threshold=30 * 60 * 1000,  # 30 minutes in milliseconds
                operator=AlertOperator.GT,
                severity=Severity.CRITICAL,
                message_template="⏱️ CRITICAL: OneGate export TIMEOUT! "
                               "Duration: {value}ms (SLO: <30 minutes). "
                               "NBB reporting may be delayed. "
                               "Investigate XML generation performance.",
            ),
            channels=[AlertChannel.PAGERDUTY, AlertChannel.TEAMS],
            escalation_level=EscalationLevel.CRITICAL,
            runbook_url="https://wiki.company.com/regops/onegate-troubleshooting",
            auto_resolve=True,
            silence_duration_minutes=30,
        ),

        # Parallel.ai Error Rate High - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="parallel.calls.error_rate",
                threshold=2.0,
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="📡 WARNING: Parallel.ai error rate elevated! "
                               "Error rate: {value}% (threshold: <2%). "
                               "Circuit breaker may open soon.",
            ),
            channels=[AlertChannel.TEAMS],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/parallel-ai-troubleshooting",
            auto_resolve=True,
            silence_duration_minutes=45,
        ),
    ]


def get_operational_alert_rules() -> List[AlertConfig]:
    """
    Get operational alert rules.
    These monitor system health and capacity.
    """
    return [
        # High Memory Usage - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="system.memory.usage_percent",
                threshold=85.0,
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="💾 WARNING: High memory usage! "
                               "Usage: {value}% (threshold: 85%). "
                               "System may need scaling or optimization.",
            ),
            channels=[AlertChannel.TEAMS],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/system-scaling",
            auto_resolve=True,
            silence_duration_minutes=120,
        ),

        # High CPU Usage - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="system.cpu.usage_percent",
                threshold=90.0,
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="🔥 WARNING: High CPU usage! "
                               "Usage: {value}% (threshold: 90%). "
                               "Performance may be impacted.",
            ),
            channels=[AlertChannel.TEAMS],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/system-scaling",
            auto_resolve=True,
            silence_duration_minutes=60,
        ),

        # Database Connection Issues - CRITICAL
        AlertConfig(
            rule=AlertRule(
                metric_name="database.connections.failed.total",
                threshold=0.0,
                operator=AlertOperator.GT,
                severity=Severity.CRITICAL,
                message_template="🗄️ CRITICAL: Database connection failures! "
                               "Failed connections: {value}. "
                               "Data persistence may be affected.",
            ),
            channels=[AlertChannel.PAGERDUTY, AlertChannel.TEAMS],
            escalation_level=EscalationLevel.CRITICAL,
            runbook_url="https://wiki.company.com/regops/database-troubleshooting",
            auto_resolve=True,
            silence_duration_minutes=15,
        ),

        # Redis Connection Issues - WARNING
        AlertConfig(
            rule=AlertRule(
                metric_name="redis.connections.failed.total",
                threshold=0.0,
                operator=AlertOperator.GT,
                severity=Severity.WARNING,
                message_template="🔴 WARNING: Redis connection failures! "
                               "Failed connections: {value}. "
                               "Caching and session management may be affected.",
            ),
            channels=[AlertChannel.TEAMS],
            escalation_level=EscalationLevel.WARNING,
            runbook_url="https://wiki.company.com/regops/redis-troubleshooting",
            auto_resolve=True,
            silence_duration_minutes=30,
        ),
    ]


def get_all_alert_rules() -> List[AlertConfig]:
    """Get all alert rules organized by category."""
    return (
        get_security_alert_rules() +
        get_business_alert_rules() +
        get_performance_alert_rules() +
        get_operational_alert_rules()
    )


def get_alert_rules_by_severity(severity: Severity) -> List[AlertConfig]:
    """Get alert rules filtered by severity level."""
    all_rules = get_all_alert_rules()
    return [rule for rule in all_rules if rule.rule.severity == severity]


def get_emergency_alert_rules() -> List[AlertConfig]:
    """Get only emergency-level alerts (cannot be silenced)."""
    all_rules = get_all_alert_rules()
    return [
        rule for rule in all_rules
        if rule.escalation_level == EscalationLevel.EMERGENCY
    ]


def get_alert_channels_for_rule(rule_name: str) -> List[AlertChannel]:
    """Get notification channels for a specific alert rule."""
    all_rules = get_all_alert_rules()
    for rule in all_rules:
        if rule.rule.metric_name == rule_name:
            return rule.channels
    return []


# Alert rule validation
def validate_alert_rule(rule: AlertConfig) -> List[str]:
    """
    Validate alert rule configuration.
    
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Check required fields
    if not rule.rule.metric_name:
        errors.append("Metric name is required")
    
    if rule.rule.threshold is None:
        errors.append("Threshold value is required")
    
    if not rule.rule.message_template:
        errors.append("Message template is required")
    
    # Check message template has placeholder
    if "{value}" not in rule.rule.message_template:
        errors.append("Message template must include {value} placeholder")
    
    # Check channels
    if not rule.channels:
        errors.append("At least one notification channel is required")
    
    # Check escalation consistency
    if (rule.escalation_level == EscalationLevel.EMERGENCY and 
        rule.rule.severity != Severity.CRITICAL):
        errors.append("Emergency escalation requires CRITICAL severity")
    
    # Check silence rules for critical alerts
    if (rule.escalation_level == EscalationLevel.EMERGENCY and 
        rule.silence_duration_minutes > 0):
        errors.append("Emergency alerts cannot be silenced")
    
    return errors


def export_prometheus_rules() -> str:
    """
    Export alert rules in Prometheus alert manager format.
    
    Returns:
        YAML string for Prometheus alert rules
    """
    all_rules = get_all_alert_rules()
    
    prometheus_rules = {
        "groups": [
            {
                "name": "regops_alerts",
                "rules": []
            }
        ]
    }
    
    for rule_config in all_rules:
        rule = rule_config.rule
        prom_rule = {
            "alert": rule.metric_name.replace(".", "_").upper(),
            "expr": f"{rule.metric_name} {rule.operator.value} {rule.threshold}",
            "for": "0s" if rule_config.escalation_level == EscalationLevel.EMERGENCY else "30s",
            "labels": {
                "severity": rule.severity.value,
                "escalation": rule_config.escalation_level.value,
                "team": "regops"
            },
            "annotations": {
                "summary": rule.message_template,
                "description": rule.message_template,
                "runbook_url": rule_config.runbook_url or ""
            }
        }
        
        prometheus_rules["groups"][0]["rules"].append(prom_rule)
    
    import yaml
    return yaml.dump(prometheus_rules, default_flow_style=False)


# Alert testing utilities
def simulate_alert_trigger(metric_name: str, value: float) -> List[AlertConfig]:
    """
    Simulate which alerts would trigger for given metric value.
    Useful for testing alert thresholds.
    """
    from ..core import should_trigger_alert
    
    triggered_alerts = []
    all_rules = get_all_alert_rules()
    
    for rule_config in all_rules:
        if rule_config.rule.metric_name == metric_name:
            if should_trigger_alert(value, rule_config.rule.threshold, rule_config.rule.operator):
                triggered_alerts.append(rule_config)
    
    return triggered_alerts