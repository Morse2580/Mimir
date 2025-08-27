# claude.md - Incident Rules Module

## Module Purpose
**Deterministic incident classification** per DORA Article 18 with DST-aware deadline calculations. Ensures consistent regulatory compliance across all incident reports.

## Core Contracts

```python
from typing import Protocol
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class Severity(Enum):
    MAJOR = "major"
    SIGNIFICANT = "significant" 
    MINOR = "minor"
    NO_REPORT = "no_report"

@dataclass(frozen=True)
class IncidentInput:
    """Immutable incident data for classification."""
    clients_affected: int
    downtime_minutes: int
    services_critical: tuple[str, ...]
    detected_at: datetime
    confirmed_at: Optional[datetime] = None
    occurred_at: Optional[datetime] = None

@dataclass(frozen=True)
class ClassificationResult:
    """Deterministic classification output."""
    severity: Severity
    criteria_matched: tuple[str, ...]
    anchor_timestamp: datetime
    anchor_source: str  # "detected_at", "confirmed_at", "occurred_at"
    confidence: float  # Always 1.0 for deterministic rules
    
@dataclass(frozen=True)
class DeadlineCalculation:
    """DST-aware deadline results."""
    initial_utc: datetime
    intermediate_utc: Optional[datetime]
    final_utc: Optional[datetime]
    display_timezone: str
    dst_transitions_handled: tuple[str, ...]

class IncidentClassifier(Protocol):
    """Core contract for incident classification."""
    
    def classify(self, incident: IncidentInput) -> ClassificationResult:
        """Pure function - deterministic classification."""
        ...
        
    def calculate_deadlines(
        self, 
        severity: Severity, 
        anchor: datetime
    ) -> DeadlineCalculation:
        """Pure function - DST-aware deadline calculation."""
        ...
```

## Functional Core (Pure Logic)

### Classification Rules (DORA Article 18)
```python
def is_major_incident(
    clients_affected: int,
    downtime_minutes: int, 
    services_critical: tuple[str, ...]
) -> bool:
    """Pure function: DORA major incident criteria.
    
    Major if ANY of:
    - downtime_minutes >= 60 AND services_critical >= 1
    - clients_affected >= 1000
    - services contains "payment" AND downtime_minutes >= 30
    """
    
def is_significant_incident(
    clients_affected: int,
    downtime_minutes: int,
    services_critical: tuple[str, ...]  
) -> bool:
    """Pure function: DORA significant incident criteria.
    
    Significant if ANY of:
    - 100 <= clients_affected < 1000
    - 15 <= downtime_minutes < 60 AND services_critical >= 1
    """

def determine_anchor_timestamp(
    detected_at: datetime,
    confirmed_at: Optional[datetime],
    occurred_at: Optional[datetime]
) -> tuple[datetime, str]:
    """Pure function: select best timestamp with fallback chain.
    
    Priority: detected_at > confirmed_at > occurred_at
    """
```

### Clock & DST Logic
```python
def calculate_deadline(
    anchor: datetime,
    hours_offset: int,
    timezone_name: str = "Europe/Brussels"
) -> tuple[datetime, list[str]]:
    """Pure function: deadline with DST transition detection.
    
    Returns:
        (deadline_utc, dst_transitions_crossed)
    """
    
def detect_dst_transition(
    start: datetime,
    end: datetime, 
    timezone_name: str
) -> list[str]:
    """Pure function: detect DST transitions in time range."""
    
def is_business_hours(dt: datetime, timezone_name: str) -> bool:
    """Pure function: check if datetime falls in business hours."""
```

## Imperative Shell (I/O Operations)

### Data Loading
- Load incident from database
- Fetch classification rules configuration
- Read timezone configuration

### Persistence
- Save classification result with audit trail
- Update incident status
- Store deadline calculations

### Event Publishing
- `IncidentClassified` event
- `DeadlineCalculated` event  
- `ClassificationRuleApplied` event

### External Integration
- OneGate XML generation trigger
- Regulatory notification scheduling
- Stakeholder alert coordination

## DORA Compliance Rules

### Major Incident Thresholds
```yaml
major_incident:
  criteria:
    - name: "critical_downtime"
      condition: "downtime_minutes >= 60 AND critical_services >= 1"
      
    - name: "mass_impact" 
      condition: "clients_affected >= 1000"
      
    - name: "payment_disruption"
      condition: "'payment' IN services AND downtime_minutes >= 30"
      
  notification_deadlines:
    initial: "4 hours from anchor"
    intermediate: "72 hours from anchor" 
    final: "30 days from anchor"
```

### Significant Incident Thresholds  
```yaml
significant_incident:
  criteria:
    - name: "moderate_impact"
      condition: "100 <= clients_affected < 1000"
      
    - name: "service_disruption"
      condition: "15 <= downtime_minutes < 60 AND critical_services >= 1"
      
  notification_deadlines:
    initial: "24 hours from anchor"
    final: "30 days from anchor"
```

## Test Strategy

### Deterministic Testing
```python
def test_classification_deterministic():
    """Same input MUST produce same output."""
    input_data = IncidentInput(
        clients_affected=5000,
        downtime_minutes=120, 
        services_critical=("payment", "trading"),
        detected_at=datetime(2024, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
    )
    
    result1 = classifier.classify(input_data)
    result2 = classifier.classify(input_data)
    
    assert result1 == result2
    assert result1.severity == Severity.MAJOR
    assert result1.confidence == 1.0
```

### DST Boundary Testing
```python
@pytest.mark.parametrize(
    "anchor_time,expected_transitions",
    [
        # Spring forward: lose 1 hour
        (datetime(2024, 3, 31, 1, 30), ["spring_forward_2024_03_31"]),
        
        # Fall back: gain 1 hour  
        (datetime(2024, 10, 27, 2, 30), ["fall_back_2024_10_27"]),
        
        # Normal time
        (datetime(2024, 6, 15, 14, 0), []),
    ]
)
def test_dst_transitions(anchor_time, expected_transitions):
    """Verify DST handling across all scenarios."""
```

### Classification Matrix Testing
- Test all combinations of thresholds
- Edge cases (exactly at boundaries) 
- Missing timestamp fallbacks
- Invalid input handling

## Invariants & Properties

### Classification Invariants
- **Deterministic**: Same input → same output
- **Complete**: Every incident gets classified
- **Monotonic**: More severe criteria → higher severity
- **Consistent**: Classification rules align with DORA

### Deadline Properties  
- **Future**: All deadlines after anchor timestamp
- **Ordered**: initial < intermediate < final
- **Timezone**: Display timezone always Europe/Brussels
- **DST-Safe**: Handles spring forward/fall back correctly

## Module Dependencies

### READ Operations
- Incident data from database
- Classification rules from YAML config
- Timezone data from system/pytz

### WRITE Operations
- Classification results to audit table
- Deadline schedules to notification system
- Metrics to monitoring system

### EMIT Events
- `IncidentClassified(incident_id, severity, criteria)`
- `DeadlineScheduled(incident_id, deadline_type, when)`  
- `DSTransitionDetected(incident_id, transitions)`

## Error Handling

### Invalid Input
- Missing required fields → validation error
- Invalid timestamp formats → parsing error  
- Negative values → domain error

### DST Edge Cases
- Non-existent times (spring forward) → use next valid time
- Ambiguous times (fall back) → use first occurrence
- Invalid timezone → fallback to UTC with warning

## Performance Requirements

### Classification Speed
- Target: <10ms per incident
- Memory: O(1) - no complex data structures
- CPU: Simple arithmetic operations

### Deadline Calculation
- Target: <50ms per incident (DST calculations)
- Pytz timezone lookups cached
- DST transition table precomputed

This module ensures **100% consistent** and **audit-defensible** incident classification.