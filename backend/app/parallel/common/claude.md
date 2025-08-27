# claude.md - PII Boundary & Circuit Breaker

YOU ARE implementing the **FIRST LINE OF DEFENSE** against PII leaks and service failures.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST BLOCK ALL PII:**
- Emails: `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`
- Phone numbers: `(\+\d{1,3}[-.\s]?)?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}`
- Account numbers: IBAN, credit card patterns
- Personal names: Common first/last name lists
- IP addresses: `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`

**YOU MUST NEVER:**
- Allow any data to Parallel.ai without `assert_parallel_safe()` check
- Skip circuit breaker for external calls
- Let circuit breaker stay open >10 minutes
- Allow >5% false positives in PII detection

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def contains_pii(text: str) -> tuple[bool, list[str]]:
    """Detect PII patterns. MUST be deterministic."""

def should_open_circuit(failures: int, threshold: int) -> bool:  
    """Circuit breaker logic. MUST be pure function."""

def calculate_risk_score(data: dict) -> float:
    """Risk assessment 0.0-1.0. MUST be deterministic."""
```

**STEP 2: Write shell.py (I/O operations)**  
```python
async def assert_parallel_safe(data: dict) -> None:
    """Validate and block PII. Emit PIIViolationDetected event."""

async def circuit_breaker_call(func, *args) -> Any:
    """Execute with circuit protection. Use Redis for state."""
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST ALL 5 ATTACK VECTORS:**
1. Direct email injection: `"Contact support@company.com"`
2. Obfuscated patterns: `"Email: john dot doe at company dot com"`
3. Encoded data: Base64, URL encoding attempts
4. Context injection: `{"user": "john", "contact": "john@co.com"}`
5. Large payload with embedded PII

**CIRCUIT BREAKER SCENARIOS:**
- 3 consecutive failures → circuit opens
- Recovery after 10 minutes
- Fallback to RSS feeds
- State persistence in Redis

## 🎯 PERFORMANCE REQUIREMENTS

**PII Detection:** <50ms per request
**Circuit State Check:** <5ms  
**Redis Operations:** <10ms
**Fallback Activation:** <100ms

## 📋 FILE STRUCTURE (MANDATORY)

```
parallel/common/
├── claude.md           # This file
├── core.py            # Pure PII detection + circuit logic
├── shell.py           # Redis state + alerts + I/O
├── contracts.py       # PIIBoundaryViolation, CircuitBreakerState
├── events.py          # PIIViolationDetected, CircuitBreakerOpened
└── tests/
    ├── test_core.py   # 5 attack vectors, pure function tests
    └── test_shell.py  # Redis integration, alert tests
```

**SUCCESS CRITERIA:**
- [ ] All 5 PII attack vectors blocked
- [ ] Circuit breaker recovers from failures  
- [ ] <1% false positive rate
- [ ] Performance targets met
- [ ] Integration with cost tracking works