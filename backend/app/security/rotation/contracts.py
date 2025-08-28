from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Callable, Awaitable
from ..vault.contracts import SecretType, SecretMetadata


class RotationTrigger(Enum):
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    COMPROMISE_DETECTED = "compromise_detected"
    POLICY_CHANGE = "policy_change"
    EMERGENCY = "emergency"


class RotationStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class RotationPolicy:
    secret_type: SecretType
    rotation_interval_days: int
    warning_days: int
    auto_rotate: bool
    max_retries: int
    rollback_on_failure: bool
    validation_required: bool
    notification_channels: List[str]
    
    @property
    def is_critical(self) -> bool:
        return self.secret_type in {
            SecretType.SIGNING_KEY,
            SecretType.ENCRYPTION_KEY,
            SecretType.DATABASE_PASSWORD
        }


@dataclass(frozen=True)
class RotationRequest:
    secret_name: str
    secret_type: SecretType
    trigger: RotationTrigger
    requested_by: str
    requested_at: datetime
    reason: str
    metadata: Dict[str, Any]
    
    @property
    def is_emergency(self) -> bool:
        return self.trigger == RotationTrigger.EMERGENCY


@dataclass(frozen=True)
class RotationJob:
    job_id: str
    request: RotationRequest
    policy: RotationPolicy
    status: RotationStatus
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    error_message: Optional[str]
    retry_count: int
    old_version: Optional[str]
    new_version: Optional[str]
    rollback_version: Optional[str]
    validation_results: Dict[str, bool]
    
    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def is_complete(self) -> bool:
        return self.status in {
            RotationStatus.COMPLETED,
            RotationStatus.FAILED,
            RotationStatus.ROLLED_BACK
        }


@dataclass(frozen=True)
class RotationResult:
    job: RotationJob
    success: bool
    old_secret: Optional[SecretMetadata]
    new_secret: Optional[SecretMetadata]
    validation_passed: bool
    error_details: Optional[str]


@dataclass(frozen=True)
class RotationSchedule:
    secret_name: str
    secret_type: SecretType
    next_rotation: datetime
    policy: RotationPolicy
    last_rotation: Optional[datetime]
    rotation_history: List[str]  # Job IDs
    
    @property
    def is_overdue(self) -> bool:
        now = datetime.utcnow()
        return now > self.next_rotation
    
    @property
    def days_until_rotation(self) -> int:
        now = datetime.utcnow()
        delta = self.next_rotation - now
        return max(0, delta.days)


class RotationError(Exception):
    def __init__(self, message: str, job_id: Optional[str] = None):
        self.job_id = job_id
        super().__init__(message)


class SecretGenerationError(RotationError):
    pass


class ValidationFailedError(RotationError):
    pass


class RollbackError(RotationError):
    pass


# Type alias for secret generator functions
SecretGenerator = Callable[[SecretType, Dict[str, Any]], Awaitable[str]]

# Type alias for secret validator functions  
SecretValidator = Callable[[str, SecretType, Dict[str, Any]], Awaitable[bool]]