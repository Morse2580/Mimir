# claude.md - Incident Clock Matrix

YOU ARE implementing **DST-aware deadline calculation** with Brussels timezone handling and audit-grade clock transitions.

## 🎯 MODULE PURPOSE
Calculate precise incident reporting deadlines across DST transitions. Handle Brussels timezone complexity for Belgian regulators (NBB, FSMA). Ensure audit-grade accuracy for regulatory compliance.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Use Brussels timezone (Europe/Brussels) for all calculations
- Handle DST spring-forward and fall-back transitions correctly
- Store both UTC and local timestamps for audit trail
- Test all 32 DST transition scenarios
- Validate clock anchors before deadline calculations

**YOU MUST NEVER:**
- Use system timezone or naive datetime objects
- Skip DST transition validation
- Allow deadline calculations without timezone context
- Trust user-provided timestamps without validation
- Calculate deadlines during DST transition gaps (02:00-03:00 spring forward)

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def calculate_reporting_deadlines(
    incident_detected_at: datetime,
    incident_severity: Severity,
    timezone: tzinfo.BaseTzInfo
) -> ReportingDeadlines:
    """Calculate all reporting deadlines for incident. MUST be deterministic."""

def handle_dst_transition(
    anchor_time: datetime,
    duration_hours: int,
    timezone: tzinfo.BaseTzInfo
) -> datetime:
    """Handle DST transitions in deadline calculation. MUST be pure."""

def validate_clock_anchor(
    timestamp: datetime,
    timezone: tzinfo.BaseTzInfo
) -> ClockValidationResult:
    """Validate timestamp is valid clock anchor. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def get_current_brussels_time() -> datetime:
    """Get current Brussels time with timezone info."""

async def store_deadline_calculation(
    incident_id: str,
    deadlines: ReportingDeadlines,
    calculation_audit: DeadlineAudit
) -> None:
    """Store deadline calculation with full audit trail."""
```

## 🕐 DST TRANSITION HANDLING

**Brussels Timezone Rules:**
```python
BRUSSELS_TZ = ZoneInfo("Europe/Brussels")

# DST Transition Dates (calculated annually)
DST_TRANSITIONS_2024 = {
    "spring_forward": datetime(2024, 3, 31, 2, 0, tzinfo=BRUSSELS_TZ),  # 02:00 → 03:00
    "fall_back": datetime(2024, 10, 27, 3, 0, tzinfo=BRUSSELS_TZ)       # 03:00 → 02:00
}

def is_dst_transition_gap(dt: datetime) -> bool:
    """Check if datetime falls in DST gap (non-existent time)."""
    # Spring forward gap: 02:00-03:00 doesn't exist
    return (
        dt.month == 3 and 
        dt.day == get_last_sunday_of_march(dt.year) and
        dt.hour == 2  # This hour doesn't exist
    )

def is_dst_transition_overlap(dt: datetime) -> bool:
    """Check if datetime falls in DST overlap (ambiguous time)."""
    # Fall back overlap: 02:00-03:00 happens twice
    return (
        dt.month == 10 and
        dt.day == get_last_sunday_of_october(dt.year) and
        2 <= dt.hour < 3  # This hour exists twice
    )
```

**Clock Matrix Scenarios:**
```python
DST_TEST_SCENARIOS = [
    # Spring Forward Scenarios
    ("spring_before", datetime(2024, 3, 31, 1, 30, tzinfo=BRUSSELS_TZ)),
    ("spring_gap", datetime(2024, 3, 31, 2, 30, tzinfo=BRUSSELS_TZ)),     # Invalid!
    ("spring_after", datetime(2024, 3, 31, 3, 30, tzinfo=BRUSSELS_TZ)),
    
    # Fall Back Scenarios  
    ("fall_before", datetime(2024, 10, 27, 1, 30, tzinfo=BRUSSELS_TZ)),
    ("fall_first", datetime(2024, 10, 27, 2, 30, tzinfo=BRUSSELS_TZ, fold=0)),
    ("fall_second", datetime(2024, 10, 27, 2, 30, tzinfo=BRUSSELS_TZ, fold=1)),
    ("fall_after", datetime(2024, 10, 27, 3, 30, tzinfo=BRUSSELS_TZ)),
    
    # Cross-midnight Weekend
    ("weekend_before", datetime(2024, 3, 30, 23, 30, tzinfo=BRUSSELS_TZ)),
    ("weekend_after", datetime(2024, 3, 31, 4, 30, tzinfo=BRUSSELS_TZ)),
]
```

## 📊 REPORTING DEADLINES

**DORA Reporting Timelines:**
```python
@dataclass(frozen=True)
class ReportingDeadlines:
    """All incident reporting deadlines."""
    incident_id: str
    severity: Severity
    anchor_time_utc: datetime
    anchor_time_brussels: datetime
    
    # DORA Article 19 deadlines
    initial_notification: datetime  # 1-4 hours based on severity
    intermediate_report: Optional[datetime]  # 72 hours for major
    final_report: datetime  # 14 days
    
    # NBB OneGate deadlines
    nbb_notification: Optional[datetime]  # If applicable
    
    # Audit metadata
    dst_transitions_handled: list[str]
    calculation_confidence: float
    timezone_used: str

DORA_DEADLINES = {
    Severity.CRITICAL: {
        "initial_hours": 1,
        "intermediate_hours": 24,
        "final_days": 14
    },
    Severity.MAJOR: {
        "initial_hours": 4, 
        "intermediate_hours": 72,
        "final_days": 14
    },
    Severity.MINOR: {
        "initial_hours": 24,
        "intermediate_hours": None,
        "final_days": 14
    }
}
```

## 🧪 MANDATORY TESTS

**ALL 32 DST SCENARIOS MUST PASS:**

**Spring Forward Tests:**
```python
@pytest.mark.parametrize("anchor_time,expected_initial,scenario", [
    # Normal case before DST
    (datetime(2024, 3, 31, 1, 30, tzinfo=BRUSSELS_TZ),
     datetime(2024, 3, 31, 5, 30, tzinfo=timezone.utc), "before_dst"),
    
    # Case spanning DST transition (1:30 + 4h = 6:30 Brussels, but only 5:30 UTC)
    (datetime(2024, 3, 31, 1, 30, tzinfo=BRUSSELS_TZ),
     datetime(2024, 3, 31, 5, 30, tzinfo=timezone.utc), "spans_spring_forward"),
     
    # Case after DST transition
    (datetime(2024, 3, 31, 4, 0, tzinfo=BRUSSELS_TZ),
     datetime(2024, 3, 31, 6, 0, tzinfo=timezone.utc), "after_dst")
])
def test_spring_forward_deadlines(anchor_time, expected_initial, scenario):
    """Test deadline calculation across spring DST transition."""
    deadlines = calculate_reporting_deadlines(
        anchor_time, 
        Severity.MAJOR, 
        BRUSSELS_TZ
    )
    
    assert deadlines.initial_notification == expected_initial
    assert scenario in deadlines.dst_transitions_handled
    assert deadlines.calculation_confidence == 1.0  # Must be deterministic
```

**Fall Back Tests:**
```python
def test_fall_back_ambiguous_time():
    """Test handling of ambiguous times during fall-back."""
    # First occurrence of 02:30 (before fall-back)
    anchor_first = datetime(2024, 10, 27, 2, 30, tzinfo=BRUSSELS_TZ, fold=0)
    deadlines_first = calculate_reporting_deadlines(anchor_first, Severity.MAJOR, BRUSSELS_TZ)
    
    # Second occurrence of 02:30 (after fall-back) 
    anchor_second = datetime(2024, 10, 27, 2, 30, tzinfo=BRUSSELS_TZ, fold=1)
    deadlines_second = calculate_reporting_deadlines(anchor_second, Severity.MAJOR, BRUSSELS_TZ)
    
    # Should produce different UTC times
    assert deadlines_first.initial_notification != deadlines_second.initial_notification
    assert abs((deadlines_first.initial_notification - deadlines_second.initial_notification).total_seconds()) == 3600
```

**Invalid Clock Tests:**
```python
def test_dst_gap_handling():
    """Test handling of non-existent times during spring forward."""
    # 02:30 on DST transition day doesn't exist
    invalid_time = datetime(2024, 3, 31, 2, 30, tzinfo=BRUSSELS_TZ)
    
    validation = validate_clock_anchor(invalid_time, BRUSSELS_TZ)
    assert validation.valid == False
    assert validation.error_type == "dst_gap"
    assert validation.suggested_time is not None  # Should suggest 03:30
```

## 🎯 PERFORMANCE REQUIREMENTS

**Deadline Calculation:** <10ms per incident
**DST Validation:** <5ms per timestamp
**Clock Matrix Test:** All 32 scenarios <1 second total
**Timezone Lookup:** <1ms per timezone operation

## 📋 FILE STRUCTURE (MANDATORY)

```
incidents/clocks/
├── claude.md           # This file
├── core.py            # Pure deadline calculation + DST handling
├── shell.py           # Current time fetching + audit storage
├── contracts.py       # ReportingDeadlines, ClockValidationResult types
├── events.py          # DeadlineCalculated, DSTTransitionHandled events
├── dst_matrix.py      # All 32 DST test scenarios
└── tests/
    ├── test_core.py   # All DST scenarios, deadline calculations
    └── test_shell.py  # Time fetching, audit trail storage
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- Python `zoneinfo` - Brussels timezone data
- NTP time sync - Accurate time source
- PostgreSQL - Deadline audit storage

**EMITS EVENTS:**
- `DeadlineCalculated(incident_id, deadlines, dst_handled, confidence)`
- `DSTTransitionHandled(transition_type, anchor_time, adjusted_time)`
- `InvalidClockAnchor(timestamp, error_type, suggested_correction)`

**CONSUMED BY:**
- `incidents/rules/` - Uses deadlines for incident classification
- Notification service - Schedules deadline reminders
- OneGate export - Uses deadlines for reporting compliance

## 📅 DST TRANSITION CALENDAR

**2024 Transitions:**
```python
DST_2024 = {
    "spring_forward": {
        "date": "2024-03-31",
        "time": "02:00 → 03:00",
        "gap": "02:00-03:00 doesn't exist",
        "utc_offset_change": "UTC+1 → UTC+2"
    },
    "fall_back": {
        "date": "2024-10-27", 
        "time": "03:00 → 02:00",
        "overlap": "02:00-03:00 happens twice",
        "utc_offset_change": "UTC+2 → UTC+1"
    }
}
```

**Weekly DST Preparedness Check:**
```python
async def weekly_dst_preparedness() -> DSTReadinessReport:
    """Weekly check for upcoming DST transitions."""
    next_transition = get_next_dst_transition(datetime.utcnow())
    
    if next_transition and next_transition < datetime.utcnow() + timedelta(days=7):
        return DSTReadinessReport(
            transition_approaching=True,
            transition_date=next_transition,
            test_scenarios_ready=True,
            system_clock_synced=await verify_ntp_sync()
        )
```

**SUCCESS CRITERIA:**
- [ ] All 32 DST scenarios pass with 100% accuracy
- [ ] Brussels timezone handling works across all transitions
- [ ] Invalid clock anchors properly detected and handled
- [ ] Deadline calculations deterministic and audit-grade
- [ ] Both UTC and Brussels times stored for compliance