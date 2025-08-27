# claude.md - Cost Tracking Module

## Module Purpose
**€1,500 monthly spend control** with automatic kill switch for Parallel.ai API usage. Provides real-time cost tracking, budget alerts, and detailed spend analytics.

## Core Contracts

```python
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class APIProcessor(Enum):
    SEARCH_BASE = "search_base"      # €0.001 per call
    SEARCH_PRO = "search_pro"        # €0.005 per call
    TASK_BASE = "task_base"          # €0.010 per call
    TASK_CORE = "task_core"          # €0.020 per call
    TASK_PRO = "task_pro"            # €0.050 per call

class SpendCategory(Enum):
    REGULATORY_MONITORING = "regulatory_monitoring"
    INCIDENT_CLASSIFICATION = "incident_classification"
    OBLIGATION_MAPPING = "obligation_mapping"
    EVIDENCE_COLLECTION = "evidence_collection"
    DIGEST_GENERATION = "digest_generation"

@dataclass(frozen=True)
class SpendLimits:
    """Immutable spend configuration."""
    monthly_cap_eur: float = 1500.0
    daily_alert_threshold_eur: float = 100.0
    kill_switch_percent: float = 95.0  # 95% of monthly cap
    warning_thresholds: tuple[float, ...] = (50.0, 80.0, 90.0)

@dataclass(frozen=True)
class CostEntry:
    """Immutable cost tracking record."""
    id: str
    timestamp: datetime
    api_type: str
    processor: APIProcessor
    cost_eur: float
    tenant: str
    use_case: SpendCategory
    request_metadata: dict
    month_running_total: float

class CostController(Protocol):
    """Core contract for cost management."""
    
    def check_budget_before_call(
        self,
        api_type: str,
        processor: APIProcessor,
        tenant: str,
        use_case: SpendCategory
    ) -> bool:
        """Check if API call allowed within budget."""
        ...
        
    def record_api_cost(
        self,
        api_type: str,
        processor: APIProcessor,
        cost_eur: float,
        tenant: str,
        use_case: SpendCategory,
        metadata: dict
    ) -> CostEntry:
        """Record actual API cost after call."""
        ...
```

## Functional Core (Pure Logic)

### Cost Calculation
```python
def calculate_api_cost(
    api_type: str,
    processor: APIProcessor,
    request_size_chars: int = 0
) -> float:
    """Pure function: calculate cost for API call.
    
    Cost matrix:
    - search_base: €0.001
    - search_pro: €0.005  
    - task_base: €0.010
    - task_core: €0.020
    - task_pro: €0.050
    """
    
def is_over_budget(
    current_spend: float,
    additional_cost: float,
    monthly_limit: float,
    threshold_percent: float
) -> bool:
    """Pure function: check if spend would exceed threshold."""
    
def calculate_budget_utilization(
    current_spend: float,
    monthly_limit: float
) -> float:
    """Pure function: calculate budget utilization percentage."""
```

### Spend Analytics
```python
def calculate_daily_average(
    monthly_spend: float,
    days_elapsed: int
) -> float:
    """Pure function: calculate daily average spend."""
    
def project_monthly_spend(
    current_spend: float,
    days_elapsed: int,
    days_in_month: int
) -> float:
    """Pure function: project month-end spend."""
    
def categorize_spend_by_use_case(
    cost_entries: list[CostEntry]
) -> dict[SpendCategory, float]:
    """Pure function: aggregate spend by category."""
```

## Imperative Shell (I/O Operations)

### Budget Enforcement
- Pre-flight budget checks
- Kill switch activation
- Circuit breaker integration
- Real-time spend tracking with Redis

### Persistence
- Cost entries to PostgreSQL
- Running totals in Redis cache
- Monthly/daily aggregates
- Historical spend patterns

### Alerting
- Teams/email budget warnings
- Critical alerts for kill switch
- Daily spend summaries
- Monthly budget reports

### Reporting
- Weekly cost breakdowns
- Tenant usage analysis
- Use case efficiency metrics
- Budget variance reports

## Cost Control Matrix

### API Pricing (EUR)
```python
COST_MATRIX = {
    ("search", "base"): 0.001,
    ("search", "pro"): 0.005,
    ("task", "base"): 0.010,
    ("task", "core"): 0.020,
    ("task", "pro"): 0.050
}
```

### Budget Thresholds
- **50% Warning**: Email notification to ops team
- **80% Alert**: Teams notification + daily monitoring
- **90% Critical**: Escalation to management
- **95% Kill Switch**: Automatic API blocking

### Kill Switch Logic
```python
def should_activate_kill_switch(
    current_spend: float,
    proposed_cost: float,
    monthly_cap: float,
    kill_switch_percent: float
) -> bool:
    """Pure function: decide if kill switch should activate."""
    total_after_call = current_spend + proposed_cost
    threshold = monthly_cap * (kill_switch_percent / 100)
    return total_after_call > threshold
```

## Test Strategy

### Budget Logic Testing
```python
def test_budget_calculations():
    """Test pure budget calculation functions."""
    assert calculate_api_cost("search", APIProcessor.SEARCH_BASE) == 0.001
    assert calculate_api_cost("task", APIProcessor.TASK_PRO) == 0.050
    
    assert is_over_budget(1400.0, 100.0, 1500.0, 95.0) == True  # Would hit 100%
    assert is_over_budget(1300.0, 100.0, 1500.0, 95.0) == False # 93.3% OK

def test_spend_projection():
    """Test spend projection logic."""
    # After 10 days, spent €500, project month-end
    projection = project_monthly_spend(500.0, 10, 30)
    assert projection == 1500.0  # €50/day * 30 days
```

### Kill Switch Testing
```python
def test_kill_switch_activation():
    """Test kill switch trigger conditions."""
    current_spend = 1400.0  # €1,400 already spent
    monthly_cap = 1500.0
    kill_switch_percent = 95.0  # €1,425 threshold
    
    # Small call - should pass
    assert not should_activate_kill_switch(1400.0, 5.0, 1500.0, 95.0)
    
    # Large call - should trigger kill switch
    assert should_activate_kill_switch(1400.0, 50.0, 1500.0, 95.0)
```

### Integration Testing
```python
@pytest.mark.integration
async def test_cost_tracking_workflow():
    """Test end-to-end cost tracking."""
    # Pre-flight check
    allowed = await cost_controller.check_budget_before_call(
        "search", 
        APIProcessor.SEARCH_PRO,
        "tenant_001",
        SpendCategory.REGULATORY_MONITORING
    )
    assert allowed == True
    
    # Record actual cost
    entry = await cost_controller.record_api_cost(
        "search",
        APIProcessor.SEARCH_PRO, 
        0.005,
        "tenant_001",
        SpendCategory.REGULATORY_MONITORING,
        {"query": "DORA requirements", "results": 15}
    )
    
    assert entry.cost_eur == 0.005
    assert entry.use_case == SpendCategory.REGULATORY_MONITORING
```

## Monitoring & Alerting

### Real-time Metrics
- Current month spend (Redis counter)
- Daily spend rate
- Budget utilization percentage
- Kill switch proximity

### Alert Conditions
```python
# Warning Alerts (Email)
if budget_utilization >= 0.50:
    send_budget_warning_email()

# Critical Alerts (Teams + Email)  
if budget_utilization >= 0.80:
    send_budget_critical_alert()

# Kill Switch Alert (Immediate)
if kill_switch_activated:
    send_kill_switch_alert()
    disable_parallel_api_calls()
```

### Reporting Schedule
- **Daily**: Spend summary (if >€20/day)
- **Weekly**: Detailed breakdown by use case
- **Monthly**: Full budget analysis + projections
- **Ad-hoc**: Kill switch activation reports

## Performance Requirements

### Response Times
- Budget check: <10ms (Redis lookup)
- Cost recording: <50ms (DB insert + cache update)
- Daily aggregation: <5 seconds
- Report generation: <30 seconds

### Accuracy Requirements
- Cost tracking: Exact to 0.001 EUR
- Running totals: Eventually consistent (5s max lag)
- Kill switch: Immediate activation (<1s)

## Module Dependencies

### READ Operations
- Current month spend from Redis
- Historical cost data from PostgreSQL
- API pricing matrix from config
- Tenant/use case mappings

### WRITE Operations
- Cost entries to PostgreSQL
- Running totals to Redis
- Alert notifications to Teams/email
- Kill switch state to circuit breaker

### EMIT Events
- `BudgetThresholdExceeded(threshold_percent, current_spend)`
- `KillSwitchActivated(trigger_cost, total_spend)`
- `CostRecorded(api_type, cost, use_case, tenant)`
- `MonthlyBudgetReset(new_month, previous_spend)`

## Weekly Report Format

```markdown
# Weekly Cost Report
**Period**: 2024-03-11 to 2024-03-17
**Total Spend**: €127.45 / €1,500.00 (8.5%)
**Daily Average**: €18.21
**Monthly Projection**: €547.64

## By Use Case
| Category | Calls | Cost (€) | % of Total |
|----------|-------|----------|------------|
| Regulatory Monitoring | 1,247 | €67.32 | 52.8% |
| Incident Classification | 89 | €31.15 | 24.4% |
| Obligation Mapping | 156 | €18.73 | 14.7% |
| Evidence Collection | 234 | €7.89 | 6.2% |
| Digest Generation | 45 | €2.36 | 1.9% |

## By API Type
| API | Processor | Calls | Cost (€) |
|-----|-----------|-------|----------|
| Search | Pro | 1,456 | €7.28 |
| Search | Base | 234 | €0.23 |
| Task | Core | 67 | €1.34 |

**Status**: ✅ Well within budget
**Next Threshold**: 50% warning at €750.00
```

This module ensures **strict budget compliance** with **automatic protection** against cost overruns.