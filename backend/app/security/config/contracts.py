from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List, Union
from ..vault.contracts import SecretType


class ConfigSource(Enum):
    ENVIRONMENT = "environment"
    KEY_VAULT = "key_vault"
    RUNTIME = "runtime"
    DEFAULT = "default"


class ConfigSensitivity(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


@dataclass(frozen=True)
class ConfigValue:
    key: str
    value: Any
    source: ConfigSource
    sensitivity: ConfigSensitivity
    last_updated: datetime
    expires_at: Optional[datetime] = None
    description: Optional[str] = None
    
    @property
    def is_sensitive(self) -> bool:
        return self.sensitivity in {ConfigSensitivity.CONFIDENTIAL, ConfigSensitivity.SECRET}
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def masked_value(self) -> Any:
        if not self.is_sensitive:
            return self.value
        
        if isinstance(self.value, str):
            if len(self.value) <= 8:
                return "*" * len(self.value)
            return self.value[:4] + "*" * (len(self.value) - 8) + self.value[-4:]
        
        return "***MASKED***"


@dataclass(frozen=True)
class ConfigSchema:
    key: str
    required: bool
    default_value: Optional[Any]
    sensitivity: ConfigSensitivity
    secret_type: Optional[SecretType]
    description: str
    validation_pattern: Optional[str] = None
    allowed_values: Optional[List[Any]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    
    def validate_value(self, value: Any) -> bool:
        if value is None and self.required:
            return False
        
        if value is None and not self.required:
            return True
        
        if self.allowed_values and value not in self.allowed_values:
            return False
        
        if isinstance(value, str):
            if self.min_length and len(value) < self.min_length:
                return False
            if self.max_length and len(value) > self.max_length:
                return False
            
            if self.validation_pattern:
                import re
                return bool(re.match(self.validation_pattern, value))
        
        return True


@dataclass(frozen=True)
class EnvironmentConfig:
    environment: str
    azure_tenant_id: str
    azure_key_vault_url: str
    azure_client_id: str
    use_managed_identity: bool = True
    debug_mode: bool = False
    
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() in {"development", "dev", "local"}


class ConfigError(Exception):
    pass


class ConfigValidationError(ConfigError):
    def __init__(self, key: str, message: str):
        self.key = key
        self.message = message
        super().__init__(f"Configuration validation error for '{key}': {message}")


class SecretNotConfiguredError(ConfigError):
    pass


class ConfigSourceUnavailableError(ConfigError):
    pass