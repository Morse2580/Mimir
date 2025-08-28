from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class SecretType(Enum):
    API_KEY = "api_key"
    SIGNING_KEY = "signing_key"
    DATABASE_PASSWORD = "database_password"
    WEBHOOK_SECRET = "webhook_secret"
    ENCRYPTION_KEY = "encryption_key"


class RotationStatus(Enum):
    CURRENT = "current"
    PENDING_ROTATION = "pending_rotation"
    EXPIRED = "expired"
    ROTATED = "rotated"


@dataclass(frozen=True)
class SecretMetadata:
    name: str
    version: str
    secret_type: SecretType
    created_at: datetime
    expires_at: datetime
    rotation_status: RotationStatus
    tags: Dict[str, str]


@dataclass(frozen=True)
class SecretValue:
    value: str
    metadata: SecretMetadata
    
    def __repr__(self) -> str:
        return f"SecretValue(metadata={self.metadata}, value=***)"


@dataclass(frozen=True)
class RotationPolicy:
    secret_type: SecretType
    rotation_days: int = 90
    warning_days: int = 7
    auto_rotate: bool = True


@dataclass(frozen=True)
class VaultConfig:
    vault_url: str
    tenant_id: str
    client_id: str
    environment: str = "production"
    use_managed_identity: bool = True
    cache_ttl_seconds: int = 300


class VaultError(Exception):
    pass


class SecretNotFoundError(VaultError):
    pass


class SecretExpiredError(VaultError):
    pass


class VaultAccessDeniedError(VaultError):
    pass