import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from .contracts import (
    WebhookConfig, WebhookHeaders, WebhookPayload, WebhookStatus,
    ReplayEntry, InvalidSignatureError, TimestampInvalidError,
    PayloadTooLargeError
)


def generate_hmac_signature(
    payload: bytes,
    secret_key: str,
    algorithm: str = "sha256"
) -> str:
    key = secret_key.encode('utf-8')
    signature = hmac.new(key, payload, getattr(hashlib, algorithm)).hexdigest()
    return f"{algorithm}={signature}"


def verify_hmac_signature(
    payload: bytes,
    signature: str,
    secret_key: str,
    algorithm: str = "sha256"
) -> bool:
    if not signature or not secret_key:
        return False
    
    expected_signature = generate_hmac_signature(payload, secret_key, algorithm)
    
    return hmac.compare_digest(signature, expected_signature)


def extract_signature_components(signature: str) -> tuple[str, str]:
    if "=" not in signature:
        return "sha256", signature
    
    parts = signature.split("=", 1)
    if len(parts) != 2:
        return "sha256", signature
    
    algorithm, hash_value = parts
    return algorithm, hash_value


def validate_timestamp(
    timestamp_str: Optional[str],
    tolerance_seconds: int,
    current_time: Optional[datetime] = None
) -> bool:
    if not timestamp_str:
        return False
    
    try:
        timestamp = int(timestamp_str)
        webhook_time = datetime.fromtimestamp(timestamp, timezone.utc)
    except (ValueError, OSError):
        return False
    
    now = current_time or datetime.now(timezone.utc)
    time_diff = abs((now - webhook_time).total_seconds())
    
    return time_diff <= tolerance_seconds


def validate_payload_size(payload_size: int, max_size: int) -> bool:
    return payload_size <= max_size


def generate_request_id(
    payload: bytes,
    timestamp: str,
    source_ip: Optional[str] = None
) -> str:
    components = [payload, timestamp.encode('utf-8')]
    
    if source_ip:
        components.append(source_ip.encode('utf-8'))
    
    combined = b'|'.join(components)
    return hashlib.sha256(combined).hexdigest()[:16]


def create_replay_entry(
    payload: bytes,
    signature: str,
    timestamp: str,
    source_ip: Optional[str] = None
) -> ReplayEntry:
    request_id = generate_request_id(payload, timestamp, source_ip)
    
    try:
        timestamp_dt = datetime.fromtimestamp(int(timestamp), timezone.utc)
    except (ValueError, OSError):
        timestamp_dt = datetime.now(timezone.utc)
    
    return ReplayEntry(
        request_id=request_id,
        signature=signature,
        timestamp=timestamp_dt,
        source_ip=source_ip
    )


def calculate_rate_limit_key(
    source_ip: Optional[str],
    user_agent: Optional[str]
) -> str:
    components = []
    
    if source_ip:
        components.append(source_ip)
    if user_agent:
        components.append(user_agent)
    
    if not components:
        components.append("unknown")
    
    key_data = "|".join(components)
    return f"webhook:rate:{hashlib.md5(key_data.encode()).hexdigest()}"


def validate_content_type(content_type: Optional[str]) -> bool:
    if not content_type:
        return True  # Allow requests without content type
    
    allowed_types = [
        "application/json",
        "application/x-www-form-urlencoded",
        "text/plain"
    ]
    
    content_type_lower = content_type.lower()
    return any(ct in content_type_lower for ct in allowed_types)


def sanitize_webhook_data(data: Dict[str, Any]) -> Dict[str, Any]:
    sensitive_keys = {
        "password", "secret", "key", "token", "auth",
        "credentials", "private", "api_key", "webhook_secret"
    }
    
    def sanitize_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(item) for item in value]
        elif isinstance(value, str) and len(value) > 100:
            return value[:100] + "...[truncated]"
        return value
    
    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = sanitize_value(value)
    
    return sanitized


def calculate_validation_metrics(
    start_time: float,
    payload_size: int,
    validation_steps: int
) -> Dict[str, Any]:
    end_time = time.time()
    duration_ms = int((end_time - start_time) * 1000)
    
    return {
        "duration_ms": duration_ms,
        "payload_size": payload_size,
        "validation_steps": validation_steps,
        "throughput_kbps": (payload_size / 1024) / max(duration_ms / 1000, 0.001)
    }


def is_suspicious_payload(payload: Dict[str, Any]) -> bool:
    suspicious_indicators = [
        lambda d: len(str(d)) > 100000,  # Very large payload
        lambda d: _has_deeply_nested_structure(d, max_depth=10),  # Deep nesting
        lambda d: _has_suspicious_patterns(d),  # Known attack patterns
        lambda d: _has_excessive_arrays(d, max_items=1000)  # Large arrays
    ]
    
    return any(indicator(payload) for indicator in suspicious_indicators)


def _has_deeply_nested_structure(obj: Any, max_depth: int, current_depth: int = 0) -> bool:
    if current_depth > max_depth:
        return True
    
    if isinstance(obj, dict):
        return any(
            _has_deeply_nested_structure(v, max_depth, current_depth + 1)
            for v in obj.values()
        )
    elif isinstance(obj, list):
        return any(
            _has_deeply_nested_structure(item, max_depth, current_depth + 1)
            for item in obj
        )
    
    return False


def _has_suspicious_patterns(obj: Any) -> bool:
    suspicious_patterns = [
        "javascript:", "<script", "eval(", "function(",
        "exec(", "__import__", "subprocess", "os.system"
    ]
    
    content = str(obj).lower()
    return any(pattern in content for pattern in suspicious_patterns)


def _has_excessive_arrays(obj: Any, max_items: int) -> bool:
    if isinstance(obj, list) and len(obj) > max_items:
        return True
    elif isinstance(obj, dict):
        return any(_has_excessive_arrays(v, max_items) for v in obj.values())
    
    return False