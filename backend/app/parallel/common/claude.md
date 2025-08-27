# claude.md - Parallel Common Module

## Module Purpose
**Security boundary enforcement** for all Parallel.ai interactions. Prevents PII leakage through technical controls and provides circuit breaker protection.

## Core Contracts

```python
from typing import Protocol, Dict, Any
from dataclasses import dataclass
from enum import Enum

class PIIBoundaryViolation(Exception):
    """Raised when PII detected in outbound data."""
    pass

class ParallelDataGuard(Protocol):
    """Core contract for PII boundary enforcement."""
    
    def assert_parallel_safe(self, data: Dict[str, Any]) -> None:
        """Validates data contains no PII. Raises PIIBoundaryViolation if unsafe."""
        ...
        
    def sanitize_query(self, query: str) -> str:
        """Removes potential PII patterns from query strings."""
        ...

class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Failed, rejecting calls  
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker(Protocol):
    """Protects against external service failures."""
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit protection."""
        ...
        
    def get_state(self) -> CircuitBreakerState:
        """Current breaker state."""
        ...
```

## Functional Core (Pure Logic)

### PII Detection
```python
def contains_pii(text: str) -> tuple[bool, list[str]]:
    """Pure function: detect PII patterns in text.
    
    Returns:
        (has_pii, violation_types)
    """
    # Implementation: regex patterns for emails, IDs, etc.
    
def calculate_risk_score(data: Dict[str, Any]) -> float:
    """Pure function: calculate PII risk score (0.0-1.0)."""
    
def should_block(risk_score: float, threshold: float = 0.3) -> bool:
    """Pure function: decision to block based on risk."""
```

### Circuit Logic
```python  
def should_open_circuit(
    failure_count: int, 
    threshold: int,
    last_failure: Optional[datetime]
) -> bool:
    """Pure function: decide if circuit should open."""
    
def can_attempt_reset(
    last_failure: datetime,
    recovery_timeout: int  
) -> bool:
    """Pure function: decide if reset attempt allowed."""
```

## Imperative Shell (I/O Operations)

### Audit Logging
- Log all PII violations with context
- Record circuit breaker state changes
- Emit security alerts for violations

### External Dependencies
- Redis for circuit breaker state persistence
- Azure Key Vault for audit signing
- Teams/email for critical alerts

### Fallback Coordination  
- RSS feed fetching when Parallel unavailable
- Cache coordination for degraded mode
- Metric collection for monitoring

## Security Properties

### PII Patterns Blocked
- Email addresses (regex: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`)
- Account numbers (patterns: IBAN, credit card, etc.)
- Phone numbers (international formats)
- Personal names (common name lists)
- IP addresses and system identifiers

### Circuit Breaker Behavior
- **Threshold**: 3 consecutive failures
- **Recovery Time**: 10 minutes  
- **Half-Open Test**: Single request to test recovery
- **Alert Threshold**: Circuit opens → immediate ops alert

## Test Strategy

### Unit Tests (Pure Functions)
```python
def test_pii_detection():
    assert contains_pii("Contact john.doe@company.com") == (True, ["email"])
    assert contains_pii("DORA requirements Belgium") == (False, [])

def test_circuit_logic():
    assert should_open_circuit(3, 3, datetime.utcnow()) == True
    assert should_open_circuit(2, 3, datetime.utcnow()) == False
```

### Integration Tests (Shell)
- Mock Parallel API failures
- Verify circuit breaker persistence
- Test alert notifications
- Validate audit logging

### Attack Simulation
- 5 PII injection vectors
- Bypass attempts (encoding, obfuscation)
- Performance under attack load

## Module Dependencies

### READ Operations
- Configuration (thresholds, patterns)
- Circuit breaker state from Redis
- Alert channel configurations

### WRITE Operations  
- Audit logs to evidence chain
- Circuit state to Redis
- Security alerts to Teams/email

### EMIT Events
- `PIIViolationDetected`
- `CircuitBreakerOpened`
- `CircuitBreakerRecovered`
- `FallbackModeActivated`

## Error Handling

### PII Violations
- Block request immediately
- Log full context (sanitized)
- Return clear error message
- Increment violation counter

### Circuit Failures
- Automatic fallback to RSS
- Graceful degradation
- User-visible service status
- Ops alerting with runbooks

## Performance Characteristics

### PII Scanning
- Target: <50ms per request
- Memory: O(1) for pattern matching
- CPU: Regex compilation cached

### Circuit Breaker
- State check: <5ms
- Redis roundtrip: <10ms
- Fallback activation: <100ms

This module is the **first line of defense** for data protection and service reliability.