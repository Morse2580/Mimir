# claude.md - Cost Tracking & Kill Switch

YOU ARE implementing **€1,500 BUDGET ENFORCEMENT** with automatic kill switch.

## 🚨 BUDGET CRITICAL - NEVER VIOLATE  

**YOU MUST ENFORCE:**
- €1,500 hard monthly cap (cannot exceed)
- 95% kill switch threshold (€1,425)
- Pre-flight cost check before EVERY Parallel.ai call
- Real-time spend tracking with Redis
- Kill switch activation <1 second

**YOU MUST NEVER:**
- Allow API calls without cost check
- Let monthly spend exceed €1,500  
- Modify kill switch threshold without approval
- Allow cost tracking accuracy <0.001 EUR
- Skip cost recording after API calls

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def calculate_api_cost(
    api_type: str, 
    processor: str,
    request_size: int = 0
) -> float:
    """Cost calculation. MUST be deterministic."""

def should_activate_kill_switch(
    current_spend: float,
    proposed_cost: float, 
    monthly_cap: float,
    threshold_percent: float
) -> bool:
    """Kill switch logic. MUST be pure function."""

def calculate_budget_utilization(
    current_spend: float,
    monthly_cap: float
) -> float:
    """Budget percentage. MUST be accurate."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def check_budget_before_call(
    api_type: str,
    processor: str,
    tenant: str
) -> bool:
    """Pre-flight check. Block if over budget."""

async def record_api_cost(
    api_type: str,
    cost_eur: float,
    tenant: str,
    use_case: str
) -> CostEntry:
    """Record cost. Update Redis totals."""
```

## 💰 COST MATRIX (EXACT VALUES)

**API PRICING (EUR):**
- `search_base`: €0.001
- `search_pro`: €0.005  
- `task_base`: €0.010
- `task_core`: €0.020
- `task_pro`: €0.050

**BUDGET THRESHOLDS:**
- 50% (€750): Email warning
- 80% (€1,200): Teams alert + daily monitoring  
- 90% (€1,350): Management escalation
- 95% (€1,425): KILL SWITCH ACTIVATED

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- Cost calculations for all 5 API types
- Kill switch at exactly 95% threshold
- Budget utilization accuracy to 0.001 EUR
- Redis state consistency under load
- Recovery after monthly reset

**KILL SWITCH SCENARIOS:**
- Current €1,400 + €50 call = BLOCK (would exceed 95%)
- Current €1,400 + €5 call = ALLOW (stays under 95%)
- Kill switch activation alerts within 5 seconds
- Manual override requires C-level approval

## 🎯 PERFORMANCE REQUIREMENTS

**Cost Check:** <10ms (Redis lookup)
**Cost Recording:** <50ms (DB insert + Redis update)  
**Kill Switch Activation:** <1 second
**Budget Calculation:** <5ms (pure computation)

## 📋 FILE STRUCTURE (MANDATORY)

```
cost/
├── claude.md           # This file
├── core.py            # Pure cost calculation + kill switch logic  
├── shell.py           # Redis operations + database + alerts
├── contracts.py       # SpendLimits, CostEntry types
├── events.py          # BudgetThresholdExceeded, KillSwitchActivated
└── tests/
    ├── test_core.py   # Cost calculations, kill switch logic
    └── test_shell.py  # Redis integration, alert testing
```

**SUCCESS CRITERIA:**
- [ ] €1,500 monthly cap enforced 
- [ ] 95% kill switch functional
- [ ] All API cost calculations correct
- [ ] Performance targets met
- [ ] Integration with PII boundary works