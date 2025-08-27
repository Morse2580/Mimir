# claude.md - DORA Incident Classification  

YOU ARE implementing **DETERMINISTIC** incident classification per DORA Article 18.

## 🚨 REGULATORY CRITICAL - NEVER VIOLATE

**YOU MUST ENSURE:**
- Same incident input = EXACTLY same classification output
- All 32 DST/timezone scenarios work correctly  
- Classification logic matches DORA Article 18 requirements
- Anchor timestamp fallback chain works: detected_at → confirmed_at → occurred_at

**YOU MUST NEVER:**
- Use non-deterministic functions in classification
- Skip DST transition handling
- Allow timezone ambiguity in deadlines
- Change classification after audit trail created

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def classify_incident_severity(
    clients_affected: int,
    downtime_minutes: int, 
    services_critical: tuple[str, ...]
) -> Severity:
    """DORA classification. MUST be deterministic."""

def calculate_deadlines(
    anchor: datetime,
    severity: Severity,
    timezone: str = "Europe/Brussels"  
) -> DeadlineCalculation:
    """DST-aware deadlines. MUST handle all transitions."""

def determine_anchor_timestamp(
    detected_at: Optional[datetime],
    confirmed_at: Optional[datetime],
    occurred_at: Optional[datetime]
) -> tuple[datetime, str]:
    """Fallback chain. MUST be deterministic."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def classify_and_persist(incident_id: str) -> ClassificationResult:
    """Load, classify, persist, emit events."""

async def schedule_notifications(
    incident_id: str,
    deadlines: DeadlineCalculation
) -> None:
    """Schedule DORA notification deadlines."""
```

## 📏 DORA CLASSIFICATION RULES

**MAJOR INCIDENT (4-hour notification):**
- `downtime_minutes >= 60 AND services_critical >= 1` OR
- `clients_affected >= 1000` OR  
- `"payment" IN services AND downtime_minutes >= 30`

**SIGNIFICANT INCIDENT (24-hour notification):**
- `100 <= clients_affected < 1000` OR
- `15 <= downtime_minutes < 60 AND services_critical >= 1`

**MINOR/NO_REPORT:**
- Everything else

## 🧪 MANDATORY TESTS

**YOU MUST TEST ALL 32 DST SCENARIOS:**
- 3 timezones × 3 anchor types × 2 DST states × 2 weekend states = 36 total
- Spring forward (lose 1 hour): March 31, 2024 at 1:30 AM
- Fall back (gain 1 hour): October 27, 2024 at 2:30 AM  
- Normal time periods without DST transitions
- Business hours vs weekend handling

**CLASSIFICATION EDGE CASES:**
- Exactly at thresholds (1000 clients, 60 minutes)
- Missing timestamp scenarios
- Multiple criteria matching
- Invalid input handling

## 🎯 PERFORMANCE REQUIREMENTS

**Classification:** <10ms (pure computation)
**Deadline Calculation:** <50ms (DST lookups)
**Database Operations:** <100ms  
**Event Publishing:** <10ms

## 📋 FILE STRUCTURE (MANDATORY)

```
incidents/rules/
├── claude.md           # This file  
├── core.py            # Pure classification + deadline logic
├── shell.py           # Database + notification scheduling  
├── contracts.py       # Severity, ClassificationResult types
├── events.py          # IncidentClassified, DeadlineScheduled
├── rules.yaml         # DORA thresholds and criteria
└── tests/
    ├── test_core.py   # 32 DST scenarios, classification matrix
    └── test_shell.py  # Database integration, event emission
```

**SUCCESS CRITERIA:**
- [ ] All DORA classification rules implemented correctly
- [ ] 32 DST scenarios pass
- [ ] Deterministic behavior verified  
- [ ] Performance targets met
- [ ] Integration with OneGate export works