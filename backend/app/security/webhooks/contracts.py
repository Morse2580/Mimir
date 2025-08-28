from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional


class WebhookStatus(Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    INVALID_SIGNATURE = "invalid_signature"
    TIMESTAMP_INVALID = "timestamp_invalid"
    REPLAY_DETECTED = "replay_detected"
    RATE_LIMITED = "rate_limited"
    PAYLOAD_TOO_LARGE = "payload_too_large"


class WebhookSource(Enum):
    PARALLEL_AI = "parallel_ai"
    NBB_ONEGATE = "nbb_onegate"
    AZURE_KEYVAULT = "azure_keyvault"
    INTERNAL = "internal"


@dataclass(frozen=True)
class WebhookConfig:
    source: WebhookSource
    secret_key: str
    algorithm: str = "sha256"
    timestamp_tolerance_seconds: int = 300  # 5 minutes
    max_payload_size: int = 1048576  # 1MB
    replay_cache_ttl: int = 900  # 15 minutes
    rate_limit_per_minute: int = 60


@dataclass(frozen=True)
class WebhookHeaders:
    signature: Optional[str]
    timestamp: Optional[str]
    content_type: Optional[str]
    content_length: Optional[int]
    user_agent: Optional[str]
    source_ip: Optional[str]
    
    @classmethod
    def from_dict(cls, headers: Dict[str, str]) -> 'WebhookHeaders':
        return cls(
            signature=headers.get("X-Signature") or headers.get("X-Hub-Signature-256"),
            timestamp=headers.get("X-Timestamp") or headers.get("X-Hub-Timestamp"),
            content_type=headers.get("Content-Type"),
            content_length=int(headers.get("Content-Length", 0)),
            user_agent=headers.get("User-Agent"),
            source_ip=headers.get("X-Forwarded-For") or headers.get("X-Real-IP")
        )


@dataclass(frozen=True)
class WebhookPayload:
    raw_body: bytes
    parsed_data: Dict[str, Any]
    headers: WebhookHeaders
    received_at: datetime
    
    @property
    def size(self) -> int:
        return len(self.raw_body)


@dataclass(frozen=True)
class WebhookValidationResult:
    status: WebhookStatus
    payload: Optional[WebhookPayload]
    error_message: Optional[str]
    validation_time_ms: int
    source: WebhookSource
    
    @property
    def is_valid(self) -> bool:
        return self.status == WebhookStatus.VERIFIED
    
    @property
    def should_process(self) -> bool:
        return self.status in (WebhookStatus.VERIFIED, WebhookStatus.PENDING)


@dataclass(frozen=True)
class ReplayEntry:
    request_id: str
    signature: str
    timestamp: datetime
    source_ip: Optional[str]
    
    def cache_key(self) -> str:
        return f"webhook:replay:{self.request_id}:{self.signature}"


class WebhookValidationError(Exception):
    def __init__(self, status: WebhookStatus, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


class InvalidSignatureError(WebhookValidationError):
    def __init__(self, message: str = "Invalid webhook signature"):
        super().__init__(WebhookStatus.INVALID_SIGNATURE, message)


class TimestampInvalidError(WebhookValidationError):
    def __init__(self, message: str = "Webhook timestamp invalid or expired"):
        super().__init__(WebhookStatus.TIMESTAMP_INVALID, message)


class ReplayDetectedError(WebhookValidationError):
    def __init__(self, message: str = "Webhook replay detected"):
        super().__init__(WebhookStatus.REPLAY_DETECTED, message)


class PayloadTooLargeError(WebhookValidationError):
    def __init__(self, message: str = "Webhook payload exceeds size limit"):
        super().__init__(WebhookStatus.PAYLOAD_TOO_LARGE, message)


class RateLimitExceededError(WebhookValidationError):
    def __init__(self, message: str = "Webhook rate limit exceeded"):
        super().__init__(WebhookStatus.RATE_LIMITED, message)