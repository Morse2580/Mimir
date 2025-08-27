# claude.md - Parallel.ai Task API Integration

YOU ARE implementing **SECURE** Parallel.ai Task API integration with PII protection and cost controls.

## 🚨 TASK API CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Run `assert_parallel_safe()` before EVERY API call
- Check budget with cost controller before API calls
- Limit output schema to ≤8 fields (avoid complex schemas)
- Keep request size <15,000 characters
- Use circuit breaker for all external calls
- Record actual API costs after successful calls

**YOU MUST NEVER:**
- Send PII to Parallel.ai (emails, names, IDs, phone numbers)
- Skip cost pre-flight checks
- Exceed schema complexity limits
- Bypass circuit breaker protection
- Send requests without authentication headers

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def validate_task_schema(schema: dict) -> tuple[bool, list[str]]:
    """Validate task schema complexity. MUST be deterministic."""

def calculate_task_cost(processor: str, estimated_complexity: str) -> float:
    """Calculate expected API cost. MUST be deterministic."""

def sanitize_task_input(data: dict) -> dict:
    """Remove potential PII from task input. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def execute_task(
    task_spec: dict,
    processor: str = "core",
    tenant: str = "default"
) -> TaskResult:
    """Execute Parallel.ai task with full protection."""

async def submit_task_with_protection(
    objective: str,
    input_data: dict,
    output_schema: dict
) -> TaskResponse:
    """Protected task submission with cost/PII checks."""
```

## 🔧 TASK API CONFIGURATION

**ALLOWED PROCESSORS:**
- `base` - €0.010 per call (simple tasks)
- `core` - €0.020 per call (standard complexity)  
- `pro` - €0.050 per call (complex analysis)

**SCHEMA LIMITS:**
- Max 8 output fields
- Max 15,000 characters total request size
- No nested objects >3 levels deep
- Primitive types preferred (string, number, boolean)

**REQUEST STRUCTURE:**
```python
{
    "objective": "Clean, specific task description",
    "input_data": {}, # PII-safe input only
    "output_schema": {
        "field1": "string",
        "field2": "number", 
        "field3": "boolean"
        # Max 8 fields total
    },
    "processor": "core" # base|core|pro
}
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST:**
- Schema validation rejects >8 fields
- PII detection blocks personal data
- Cost calculation matches processor rates
- Circuit breaker activates on failures
- Request size limits enforced

**PII INJECTION SCENARIOS:**
```python
# These MUST be blocked
{
    "objective": "Analyze customer feedback", 
    "input_data": {
        "feedback": "Contact john.doe@company.com for issues"  # EMAIL - BLOCKED
    }
}

{
    "objective": "Process support ticket",
    "input_data": {
        "customer_id": "12345",  # ID - BLOCKED
        "phone": "+32 2 123 4567"  # PHONE - BLOCKED  
    }
}
```

## 📋 ERROR HANDLING

**API ERROR RESPONSES:**
- 401 Unauthorized → Check API key configuration
- 429 Rate Limited → Activate circuit breaker, use exponential backoff
- 400 Bad Request → Log schema validation error, don't retry
- 500 Internal Error → Circuit breaker, fallback to RSS

**TIMEOUT HANDLING:**
- Request timeout: 30 seconds
- Retry attempts: 2 with exponential backoff
- Circuit breaker: Open after 3 consecutive failures

## 🎯 PERFORMANCE REQUIREMENTS

**Task Execution:** <60 seconds for standard tasks
**Schema Validation:** <10ms per request
**PII Detection:** <50ms per request  
**Cost Pre-flight:** <10ms per request

## 📋 FILE STRUCTURE (MANDATORY)

```
parallel/task/
├── claude.md           # This file
├── core.py            # Pure schema validation + cost calculation
├── shell.py           # API calls + circuit breaker integration
├── contracts.py       # TaskResult, TaskResponse types  
├── events.py          # TaskExecuted, TaskFailed events
└── tests/
    ├── test_core.py   # Schema validation, PII sanitization
    └── test_shell.py  # API integration, circuit breaker tests
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- `parallel/common/` - PII boundary and circuit breaker
- `cost/` - Budget checking and cost recording
- Redis - Circuit breaker state persistence
- PostgreSQL - Task execution audit trail

**EMITS EVENTS:**
- `TaskExecuted(task_id, processor, cost, duration)`
- `TaskFailed(task_id, error_type, retry_count)`
- `SchemaViolationDetected(task_id, violations)`

**SUCCESS CRITERIA:**
- [ ] All PII injection attempts blocked
- [ ] Schema complexity limits enforced
- [ ] Cost tracking accurate to 0.001 EUR
- [ ] Circuit breaker functional
- [ ] Integration with other modules works