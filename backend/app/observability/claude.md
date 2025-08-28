# claude.md - Observability & Metrics

YOU ARE implementing **COMPREHENSIVE OBSERVABILITY** for the Belgian RegOps Platform.

## 🎯 OBSERVABILITY MISSION

**YOU MUST PROVIDE:**
- Business metrics: parallel.calls, digest.tierA.count, clock.deadline.miss, ledger.verify.ok
- Security metrics: pii.violations=0, budget.utilization, circuit.breaker.state  
- Performance SLOs: PII detection <50ms, Cost checking <10ms, OneGate export <30min
- Real-time dashboards for business, performance, and security monitoring
- Alerting for budget >95%, PII violations, deadline misses

**YOU MUST NEVER:**
- Skip metrics collection on critical operations
- Allow metrics collection to break core functionality
- Record PII in metrics or traces
- Exceed 5ms overhead for metrics collection
- Allow metric names to conflict across modules

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def create_metric(
    name: str,
    value: float, 
    labels: dict[str, str],
    metric_type: str,
    timestamp: Optional[datetime] = None
) -> Metric:
    """Create standardized metric. MUST be deterministic."""

def validate_metric_name(name: str) -> bool:
    """Validate metric name follows conventions."""

def calculate_slo_compliance(
    target: float,
    actual: float, 
    tolerance: float
) -> float:
    """Calculate SLO compliance percentage."""

def should_trigger_alert(
    metric: Metric,
    threshold: float,
    operator: str
) -> bool:
    """Determine if metric triggers alert."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def record_metric(
    name: str,
    value: float,
    labels: dict[str, str] = None
) -> None:
    """Record metric to storage."""

async def emit_alert(
    metric_name: str,
    severity: str,
    message: str
) -> None:
    """Emit alert via configured channels."""

async def get_slo_status(
    slo_name: str,
    time_window: timedelta
) -> SLOStatus:
    """Get current SLO compliance status."""
```

## 📊 REQUIRED METRICS

**BUSINESS METRICS:**
- `parallel.calls.total` (counter) - Total Parallel.ai API calls
- `parallel.calls.duration_ms` (histogram) - API call latency
- `digest.tier_a.count` (gauge) - Tier A regulatory items found  
- `digest.completion.time` (gauge) - Daily digest completion time (CET)
- `clock.deadline.miss.total` (counter) - Deadline misses by type
- `ledger.verify.status` (gauge) - Evidence ledger verification status

**SECURITY METRICS:**
- `pii.violations.total` (counter) - PII boundary violations (MUST=0)
- `pii.detection.duration_ms` (histogram) - PII detection latency
- `budget.utilization.percent` (gauge) - Monthly budget utilization
- `budget.spend.eur` (gauge) - Current monthly spend
- `circuit.breaker.state` (gauge) - Circuit breaker status (0=closed, 1=open)
- `circuit.breaker.failures.total` (counter) - Circuit breaker failures

**PERFORMANCE METRICS:**
- `cost.check.duration_ms` (histogram) - Cost checking latency
- `onegate.export.duration_ms` (histogram) - OneGate export time
- `xml.validation.duration_ms` (histogram) - XSD validation time
- `classification.duration_ms` (histogram) - Incident classification time

## 🚨 CRITICAL SLOs

**SLO-01: OneGate Export Performance**
- Target: p95 < 30 minutes
- Alert: p95 > 25 minutes (warning), p95 > 35 minutes (critical)

**SLO-02: Daily Digest Completion**
- Target: Complete by 09:00 CET daily
- Alert: Not completed by 09:30 CET

**SLO-03: Parallel.ai Error Rate**
- Target: <2% error rate over 15 minutes
- Alert: >2% opens circuit breaker

**SLO-04: Security Violations**
- Target: 0 PII violations
- Alert: Any PII violation (immediate)

**SLO-05: Performance Targets**
- PII detection: <50ms
- Cost checking: <10ms
- Alert: p95 exceeds target

## 📋 FILE STRUCTURE (MANDATORY)

```
observability/
├── claude.md           # This file
├── core.py            # Pure metric functions + SLO calculations
├── shell.py           # Storage, alerts, OpenTelemetry integration
├── contracts.py       # Metric, SLOStatus, AlertRule types
├── events.py          # MetricRecorded, AlertTriggered, SLOViolated
├── integration.py     # OpenTelemetry setup + Azure App Insights
└── tests/
    ├── test_core.py   # Pure function tests
    ├── test_shell.py  # Integration tests with mocks
    └── test_slo.py    # SLO calculation tests
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- All business metrics collection points
- SLO compliance calculation accuracy
- Alert threshold triggering logic
- OpenTelemetry span creation
- Performance overhead <5ms per metric

**DASHBOARD VALIDATION:**
- Business overview shows all required metrics
- Performance SLOs update in real-time
- Security monitoring shows zero PII violations
- Alerting rules fire at correct thresholds

## 🎯 PERFORMANCE REQUIREMENTS

**Metric Recording:** <5ms overhead per metric
**SLO Calculation:** <10ms for any time window
**Alert Evaluation:** <5ms per metric
**Dashboard Update:** <100ms end-to-end

**SUCCESS CRITERIA:**
- [ ] All required metrics implemented
- [ ] SLOs tracked and alerted on
- [ ] Dashboards functional
- [ ] <5ms observability overhead
- [ ] Integration with existing modules works