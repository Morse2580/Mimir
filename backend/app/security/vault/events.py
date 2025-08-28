from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
from .contracts import SecretType, RotationStatus


@dataclass(frozen=True)
class SecretAccessedEvent:
    secret_name: str
    secret_type: SecretType
    user_id: Optional[str]
    client_ip: Optional[str]
    accessed_at: datetime
    cache_hit: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": "secret_accessed",
            "secret_name": self.secret_name,
            "secret_type": self.secret_type.value,
            "user_id": self.user_id,
            "client_ip": self.client_ip,
            "accessed_at": self.accessed_at.isoformat(),
            "cache_hit": self.cache_hit
        }


@dataclass(frozen=True)
class SecretCreatedEvent:
    secret_name: str
    secret_type: SecretType
    version: str
    created_by: Optional[str]
    created_at: datetime
    tags: Dict[str, str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": "secret_created",
            "secret_name": self.secret_name,
            "secret_type": self.secret_type.value,
            "version": self.version,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "tags": self.tags
        }


@dataclass(frozen=True)
class SecretRotatedEvent:
    secret_name: str
    secret_type: SecretType
    old_version: str
    new_version: str
    rotated_by: Optional[str]
    rotated_at: datetime
    reason: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": "secret_rotated",
            "secret_name": self.secret_name,
            "secret_type": self.secret_type.value,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "rotated_by": self.rotated_by,
            "rotated_at": self.rotated_at.isoformat(),
            "reason": self.reason
        }


@dataclass(frozen=True)
class SecretExpiredEvent:
    secret_name: str
    secret_type: SecretType
    expired_at: datetime
    last_accessed: Optional[datetime]
    requires_rotation: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": "secret_expired",
            "secret_name": self.secret_name,
            "secret_type": self.secret_type.value,
            "expired_at": self.expired_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "requires_rotation": self.requires_rotation
        }


@dataclass(frozen=True)
class VaultAccessDeniedEvent:
    secret_name: str
    operation: str
    user_id: Optional[str]
    client_ip: Optional[str]
    denied_at: datetime
    reason: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": "vault_access_denied",
            "secret_name": self.secret_name,
            "operation": self.operation,
            "user_id": self.user_id,
            "client_ip": self.client_ip,
            "denied_at": self.denied_at.isoformat(),
            "reason": self.reason
        }