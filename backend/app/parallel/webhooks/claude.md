# claude.md - Parallel Webhooks Security

YOU ARE implementing **SECURE** webhook handling with mTLS, HMAC verification, and replay protection.

## 🎯 MODULE PURPOSE
Secure webhook endpoint for Parallel.ai Task API callbacks. Prevents replay attacks, validates signatures, and ensures only authentic Parallel requests are processed.

## 🚨 SECURITY CRITICAL - NEVER VIOLATE

**YOU MUST ALWAYS:**
- Verify HMAC signature on every webhook request
- Check timestamp freshness (≤5 minutes)
- Use replay protection with Redis nonce cache
- Validate mTLS client certificates when configured
- Log all webhook attempts for audit

**YOU MUST NEVER:**
- Process webhooks without signature verification
- Accept stale timestamps (>5 minutes old)
- Allow nonce replay attacks
- Skip audit logging of webhook events
- Return sensitive data in webhook responses

## ⚡ IMPLEMENTATION COMMANDS

**STEP 1: Write core.py (pure functions only)**
```python
def calculate_hmac_signature(
    payload: bytes,
    timestamp: str,
    nonce: str,
    secret: str
) -> str:
    """Calculate webhook HMAC signature. MUST be deterministic."""

def is_timestamp_fresh(
    timestamp_str: str,
    max_age_seconds: int = 300
) -> bool:
    """Check timestamp freshness. MUST be pure function."""

def validate_webhook_payload(
    payload: dict,
    required_fields: tuple[str, ...]
) -> tuple[bool, list[str]]:
    """Validate webhook payload structure. MUST be pure."""
```

**STEP 2: Write shell.py (I/O operations)**
```python
async def handle_webhook_request(
    body: bytes,
    headers: dict[str, str],
    client_cert: Optional[str] = None
) -> WebhookResponse:
    """Process webhook with full security validation."""

async def verify_and_process_webhook(
    webhook_event: dict
) -> None:
    """Verify webhook and trigger appropriate handlers."""
```

## 🔐 WEBHOOK SECURITY LAYERS

**Layer 1: mTLS (Optional)**
```python
def validate_client_certificate(cert: str) -> bool:
    """Validate mTLS client certificate against trusted CA."""
```

**Layer 2: HMAC Verification**
```python
# Required headers
REQUIRED_HEADERS = [
    "X-Parallel-Signature",
    "X-Parallel-Timestamp", 
    "X-Parallel-Nonce"
]

# HMAC calculation
message = body + timestamp.encode() + nonce.encode()
expected_sig = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
```

**Layer 3: Replay Protection**
```python
# Redis nonce cache
NONCE_KEY_PATTERN = "webhook_nonce:{nonce}"
NONCE_TTL_SECONDS = 300  # 5 minutes
```

**Layer 4: Timestamp Validation**
```python
MAX_WEBHOOK_AGE = 300  # 5 minutes
req_time = datetime.fromisoformat(timestamp)
age = abs((datetime.utcnow() - req_time).total_seconds())
```

## 🧪 MANDATORY TESTS

**YOU MUST TEST ALL SECURITY LAYERS:**

**HMAC Verification Tests:**
```python
def test_valid_webhook_signature():
    """Valid HMAC signature should pass verification."""
    
def test_invalid_webhook_signature():
    """Invalid HMAC signature should be rejected."""
    
def test_missing_signature_header():
    """Missing signature header should be rejected."""
```

**Replay Protection Tests:**
```python
def test_fresh_nonce_accepted():
    """Fresh nonce should be accepted once."""
    
def test_nonce_replay_blocked():
    """Duplicate nonce should be blocked."""
    
def test_nonce_expiry():
    """Expired nonce should be cleared from cache."""
```

**Timestamp Validation Tests:**
```python
def test_fresh_timestamp_accepted():
    """Fresh timestamp within 5 minutes should pass."""
    
def test_stale_timestamp_rejected():
    """Timestamp older than 5 minutes should be rejected."""
```

## 📋 WEBHOOK EVENT TYPES

**Task Completion Events:**
```python
{
    "type": "task_run.status",
    "data": {
        "id": "run_abc123",
        "status": "completed",
        "output": {...},
        "basis": {...}
    },
    "timestamp": "2024-03-15T14:30:00Z"
}
```

**Error Events:**
```python
{
    "type": "task_run.status", 
    "data": {
        "id": "run_abc123",
        "status": "failed",
        "error": "Task execution timeout"
    },
    "timestamp": "2024-03-15T14:30:00Z"
}
```

## 🎯 PERFORMANCE REQUIREMENTS

**HMAC Verification:** <10ms per request
**Redis Nonce Check:** <5ms per lookup
**Total Webhook Processing:** <100ms end-to-end
**Certificate Validation:** <20ms (if mTLS enabled)

## 📋 FILE STRUCTURE (MANDATORY)

```
parallel/webhooks/
├── claude.md           # This file
├── core.py            # Pure HMAC + timestamp validation
├── shell.py           # Webhook handling + Redis operations
├── contracts.py       # WebhookEvent, WebhookResponse types
├── events.py          # WebhookReceived, WebhookSecurityViolation events
├── replay_cache.py    # Redis nonce management
└── tests/
    ├── test_core.py   # HMAC, timestamp, payload validation
    └── test_shell.py  # Full webhook security integration
```

## 🔗 INTEGRATION POINTS

**DEPENDS ON:**
- Redis - Nonce replay cache
- Azure Key Vault - Webhook secret storage
- PostgreSQL - Webhook audit logging
- `parallel/common/` - Circuit breaker for downstream processing

**EMITS EVENTS:**
- `WebhookReceived(event_type, timestamp, verified)`
- `WebhookSecurityViolation(violation_type, source_ip, timestamp)`
- `TaskCompletionReceived(task_id, status, processing_time)`

## 🚨 SECURITY INCIDENT RESPONSE

**Replay Attack Detected:**
```python
logger.critical(f"REPLAY ATTACK detected: nonce={nonce}")
await send_security_alert("Webhook replay attack", {
    "nonce": nonce,
    "source_ip": request_ip,
    "timestamp": timestamp
})
```

**Invalid HMAC Signature:**
```python
logger.warning(f"Invalid webhook signature from {source_ip}")
await increment_security_metric("webhook.hmac.failures")
```

**SUCCESS CRITERIA:**
- [ ] All security layers functional
- [ ] Replay attacks blocked and logged
- [ ] HMAC verification working
- [ ] Performance targets met
- [ ] Integration with task processing works