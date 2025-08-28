import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from .contracts import (
    RotationPolicy, RotationSchedule, RotationJob, RotationRequest,
    RotationStatus, RotationTrigger
)
from ..vault.contracts import SecretType


def create_default_rotation_policies() -> Dict[SecretType, RotationPolicy]:
    return {
        SecretType.API_KEY: RotationPolicy(
            secret_type=SecretType.API_KEY,
            rotation_interval_days=90,
            warning_days=7,
            auto_rotate=True,
            max_retries=3,
            rollback_on_failure=True,
            validation_required=True,
            notification_channels=["security@company.com"]
        ),
        
        SecretType.SIGNING_KEY: RotationPolicy(
            secret_type=SecretType.SIGNING_KEY,
            rotation_interval_days=180,
            warning_days=14,
            auto_rotate=False,  # Requires manual approval
            max_retries=1,
            rollback_on_failure=True,
            validation_required=True,
            notification_channels=["security@company.com", "admin@company.com"]
        ),
        
        SecretType.DATABASE_PASSWORD: RotationPolicy(
            secret_type=SecretType.DATABASE_PASSWORD,
            rotation_interval_days=60,
            warning_days=7,
            auto_rotate=True,
            max_retries=2,
            rollback_on_failure=True,
            validation_required=True,
            notification_channels=["security@company.com", "devops@company.com"]
        ),
        
        SecretType.WEBHOOK_SECRET: RotationPolicy(
            secret_type=SecretType.WEBHOOK_SECRET,
            rotation_interval_days=90,
            warning_days=7,
            auto_rotate=True,
            max_retries=3,
            rollback_on_failure=True,
            validation_required=True,
            notification_channels=["security@company.com"]
        ),
        
        SecretType.ENCRYPTION_KEY: RotationPolicy(
            secret_type=SecretType.ENCRYPTION_KEY,
            rotation_interval_days=365,
            warning_days=30,
            auto_rotate=False,
            max_retries=1,
            rollback_on_failure=True,
            validation_required=True,
            notification_channels=["security@company.com", "admin@company.com"]
        )
    }


def calculate_next_rotation_date(
    policy: RotationPolicy,
    last_rotation: Optional[datetime] = None
) -> datetime:
    base_date = last_rotation or datetime.now(timezone.utc)
    return base_date + timedelta(days=policy.rotation_interval_days)


def calculate_warning_date(
    next_rotation: datetime,
    warning_days: int
) -> datetime:
    return next_rotation - timedelta(days=warning_days)


def should_rotate_secret(
    schedule: RotationSchedule,
    current_time: Optional[datetime] = None
) -> bool:
    now = current_time or datetime.now(timezone.utc)
    
    if schedule.is_overdue:
        return True
    
    warning_date = calculate_warning_date(
        schedule.next_rotation,
        schedule.policy.warning_days
    )
    
    return now >= warning_date and schedule.policy.auto_rotate


def generate_job_id(request: RotationRequest) -> str:
    timestamp = request.requested_at.strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"rot-{request.secret_type.value}-{timestamp}-{random_suffix}"


def generate_secret_value(secret_type: SecretType, length: int = 32) -> str:
    if secret_type == SecretType.API_KEY:
        return generate_api_key(length)
    elif secret_type == SecretType.WEBHOOK_SECRET:
        return generate_webhook_secret(length)
    elif secret_type == SecretType.DATABASE_PASSWORD:
        return generate_database_password()
    elif secret_type == SecretType.SIGNING_KEY:
        return generate_rsa_private_key()
    elif secret_type == SecretType.ENCRYPTION_KEY:
        return generate_encryption_key(length)
    else:
        return generate_api_key(length)


def generate_api_key(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_webhook_secret(length: int = 64) -> str:
    return secrets.token_urlsafe(length)


def generate_database_password(length: int = 24) -> str:
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%^&*"
    
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(special)
    ]
    
    all_chars = lowercase + uppercase + digits + special
    for _ in range(length - 4):
        password.append(secrets.choice(all_chars))
    
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def generate_rsa_private_key() -> str:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    return pem.decode('utf-8')


def generate_encryption_key(length: int = 32) -> str:
    return secrets.token_hex(length)


def validate_secret_strength(secret_value: str, secret_type: SecretType) -> bool:
    if not secret_value:
        return False
    
    min_lengths = {
        SecretType.API_KEY: 24,
        SecretType.WEBHOOK_SECRET: 32,
        SecretType.DATABASE_PASSWORD: 12,
        SecretType.ENCRYPTION_KEY: 32
    }
    
    min_length = min_lengths.get(secret_type, 16)
    if len(secret_value) < min_length:
        return False
    
    if secret_type == SecretType.DATABASE_PASSWORD:
        return validate_password_complexity(secret_value)
    elif secret_type == SecretType.SIGNING_KEY:
        return validate_rsa_key(secret_value)
    
    return True


def validate_password_complexity(password: str) -> bool:
    if len(password) < 12:
        return False
    
    has_lower = any(c.islower() for c in password)
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    return all([has_lower, has_upper, has_digit, has_special])


def validate_rsa_key(key_pem: str) -> bool:
    try:
        from cryptography.hazmat.primitives import serialization
        
        serialization.load_pem_private_key(
            key_pem.encode('utf-8'),
            password=None
        )
        return True
    except Exception:
        return False


def get_secrets_due_for_rotation(
    schedules: List[RotationSchedule],
    current_time: Optional[datetime] = None
) -> List[RotationSchedule]:
    now = current_time or datetime.now(timezone.utc)
    
    return [
        schedule for schedule in schedules
        if should_rotate_secret(schedule, now)
    ]


def get_emergency_rotation_priority(secret_type: SecretType) -> int:
    priorities = {
        SecretType.ENCRYPTION_KEY: 1,
        SecretType.SIGNING_KEY: 2,
        SecretType.DATABASE_PASSWORD: 3,
        SecretType.API_KEY: 4,
        SecretType.WEBHOOK_SECRET: 5
    }
    
    return priorities.get(secret_type, 10)


def should_notify_rotation_warning(
    schedule: RotationSchedule,
    current_time: Optional[datetime] = None
) -> bool:
    now = current_time or datetime.now(timezone.utc)
    warning_date = calculate_warning_date(
        schedule.next_rotation,
        schedule.policy.warning_days
    )
    
    return now >= warning_date and now < schedule.next_rotation


def calculate_rotation_impact(
    secret_type: SecretType,
    dependent_services: List[str]
) -> Dict[str, any]:
    risk_levels = {
        SecretType.DATABASE_PASSWORD: "high",
        SecretType.SIGNING_KEY: "high", 
        SecretType.ENCRYPTION_KEY: "critical",
        SecretType.API_KEY: "medium",
        SecretType.WEBHOOK_SECRET: "low"
    }
    
    downtime_estimates = {
        SecretType.DATABASE_PASSWORD: {"min": 5, "max": 30},
        SecretType.SIGNING_KEY: {"min": 10, "max": 60},
        SecretType.ENCRYPTION_KEY: {"min": 30, "max": 120},
        SecretType.API_KEY: {"min": 1, "max": 10},
        SecretType.WEBHOOK_SECRET: {"min": 1, "max": 5}
    }
    
    return {
        "risk_level": risk_levels.get(secret_type, "medium"),
        "affected_services": dependent_services,
        "estimated_downtime_minutes": downtime_estimates.get(secret_type, {"min": 1, "max": 10}),
        "requires_coordination": secret_type in {
            SecretType.DATABASE_PASSWORD,
            SecretType.SIGNING_KEY,
            SecretType.ENCRYPTION_KEY
        }
    }