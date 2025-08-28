from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from .contracts import (
    SecretMetadata, SecretType, RotationStatus,
    RotationPolicy, SecretExpiredError
)


def calculate_rotation_status(
    created_at: datetime,
    rotation_days: int,
    warning_days: int,
    current_time: Optional[datetime] = None
) -> RotationStatus:
    now = current_time or datetime.now(timezone.utc)
    expires_at = created_at + timedelta(days=rotation_days)
    warning_at = expires_at - timedelta(days=warning_days)
    
    if now >= expires_at:
        return RotationStatus.EXPIRED
    elif now >= warning_at:
        return RotationStatus.PENDING_ROTATION
    else:
        return RotationStatus.CURRENT


def validate_secret_expiry(
    metadata: SecretMetadata,
    current_time: Optional[datetime] = None
) -> bool:
    now = current_time or datetime.now(timezone.utc)
    
    if metadata.rotation_status == RotationStatus.EXPIRED:
        raise SecretExpiredError(
            f"Secret {metadata.name} expired at {metadata.expires_at}"
        )
    
    if now >= metadata.expires_at:
        raise SecretExpiredError(
            f"Secret {metadata.name} expired at {metadata.expires_at}"
        )
    
    return True


def get_secrets_requiring_rotation(
    secrets: List[SecretMetadata],
    policies: Dict[SecretType, RotationPolicy],
    current_time: Optional[datetime] = None
) -> List[SecretMetadata]:
    now = current_time or datetime.now(timezone.utc)
    requiring_rotation = []
    
    for secret in secrets:
        policy = policies.get(secret.secret_type)
        if not policy or not policy.auto_rotate:
            continue
            
        status = calculate_rotation_status(
            secret.created_at,
            policy.rotation_days,
            policy.warning_days,
            now
        )
        
        if status in (RotationStatus.PENDING_ROTATION, RotationStatus.EXPIRED):
            requiring_rotation.append(secret)
    
    return requiring_rotation


def generate_secret_name(
    base_name: str,
    secret_type: SecretType,
    environment: str,
    version: Optional[str] = None
) -> str:
    components = [environment.lower(), secret_type.value, base_name]
    
    if version:
        components.append(version)
    
    return "-".join(components)


def parse_secret_name(name: str) -> Dict[str, str]:
    parts = name.split("-")
    
    if len(parts) < 3:
        return {"raw": name}
    
    result = {
        "environment": parts[0],
        "secret_type": parts[1],
        "base_name": "-".join(parts[2:-1]) if len(parts) > 3 else parts[2]
    }
    
    if len(parts) > 3 and parts[-1].isdigit():
        result["version"] = parts[-1]
    
    return result


def validate_secret_access(
    secret_type: SecretType,
    allowed_types: Set[SecretType]
) -> bool:
    return secret_type in allowed_types


def calculate_cache_key(
    secret_name: str,
    environment: str
) -> str:
    return f"{environment}:{secret_name}"


def is_cache_expired(
    cached_at: datetime,
    ttl_seconds: int,
    current_time: Optional[datetime] = None
) -> bool:
    now = current_time or datetime.now(timezone.utc)
    expiry = cached_at + timedelta(seconds=ttl_seconds)
    return now >= expiry