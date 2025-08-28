from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from .contracts import (
    ConfigSchema, ConfigSensitivity, EnvironmentConfig,
    ConfigValidationError, SecretNotConfiguredError
)
from ..vault.contracts import SecretType


def create_config_schema() -> Dict[str, ConfigSchema]:
    return {
        # Environment Configuration
        "ENVIRONMENT": ConfigSchema(
            key="ENVIRONMENT",
            required=True,
            default_value="development",
            sensitivity=ConfigSensitivity.PUBLIC,
            secret_type=None,
            description="Application environment (development, staging, production)",
            allowed_values=["development", "staging", "production"]
        ),
        
        # Azure Configuration
        "AZURE_TENANT_ID": ConfigSchema(
            key="AZURE_TENANT_ID",
            required=True,
            default_value=None,
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Azure AD tenant ID for authentication"
        ),
        
        "AZURE_CLIENT_ID": ConfigSchema(
            key="AZURE_CLIENT_ID",
            required=True,
            default_value=None,
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Azure AD application client ID"
        ),
        
        "AZURE_KEY_VAULT_URL": ConfigSchema(
            key="AZURE_KEY_VAULT_URL",
            required=True,
            default_value=None,
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Azure Key Vault URL for secrets management",
            validation_pattern=r"^https://.*\.vault\.azure\.net/?$"
        ),
        
        # Database Configuration
        "DATABASE_HOST": ConfigSchema(
            key="DATABASE_HOST",
            required=True,
            default_value="localhost",
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Database server hostname or IP address"
        ),
        
        "DATABASE_NAME": ConfigSchema(
            key="DATABASE_NAME",
            required=True,
            default_value="mimir_regops",
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Database name"
        ),
        
        "DATABASE_USER": ConfigSchema(
            key="DATABASE_USER",
            required=True,
            default_value="postgres",
            sensitivity=ConfigSensitivity.CONFIDENTIAL,
            secret_type=None,
            description="Database username"
        ),
        
        "DATABASE_PASSWORD": ConfigSchema(
            key="DATABASE_PASSWORD",
            required=True,
            default_value=None,
            sensitivity=ConfigSensitivity.SECRET,
            secret_type=SecretType.DATABASE_PASSWORD,
            description="Database password",
            min_length=12
        ),
        
        # Redis Configuration
        "REDIS_URL": ConfigSchema(
            key="REDIS_URL",
            required=True,
            default_value="redis://localhost:6379/0",
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Redis connection URL"
        ),
        
        # Parallel.ai Configuration
        "PARALLEL_API_KEY": ConfigSchema(
            key="PARALLEL_API_KEY",
            required=True,
            default_value=None,
            sensitivity=ConfigSensitivity.SECRET,
            secret_type=SecretType.API_KEY,
            description="Parallel.ai API key for research and analysis",
            min_length=32
        ),
        
        "PARALLEL_BASE_URL": ConfigSchema(
            key="PARALLEL_BASE_URL",
            required=True,
            default_value="https://api.parallel.ai/v1",
            sensitivity=ConfigSensitivity.PUBLIC,
            secret_type=None,
            description="Parallel.ai API base URL"
        ),
        
        # JWT Configuration
        "JWT_SECRET_KEY": ConfigSchema(
            key="JWT_SECRET_KEY",
            required=True,
            default_value=None,
            sensitivity=ConfigSensitivity.SECRET,
            secret_type=SecretType.SIGNING_KEY,
            description="Secret key for JWT token signing",
            min_length=32
        ),
        
        # Webhook Configuration
        "WEBHOOK_SECRET": ConfigSchema(
            key="WEBHOOK_SECRET",
            required=True,
            default_value=None,
            sensitivity=ConfigSensitivity.SECRET,
            secret_type=SecretType.WEBHOOK_SECRET,
            description="Secret for webhook signature validation",
            min_length=32
        ),
        
        # Cost Management
        "COST_BUDGET_LIMIT": ConfigSchema(
            key="COST_BUDGET_LIMIT",
            required=True,
            default_value=1500.0,
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Monthly budget limit in EUR for external API calls"
        ),
        
        # Application Configuration
        "LOG_LEVEL": ConfigSchema(
            key="LOG_LEVEL",
            required=False,
            default_value="INFO",
            sensitivity=ConfigSensitivity.PUBLIC,
            secret_type=None,
            description="Application log level",
            allowed_values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        ),
        
        "MAX_REQUEST_SIZE": ConfigSchema(
            key="MAX_REQUEST_SIZE",
            required=False,
            default_value=16777216,  # 16MB
            sensitivity=ConfigSensitivity.PUBLIC,
            secret_type=None,
            description="Maximum request size in bytes"
        ),
        
        "SESSION_TIMEOUT_MINUTES": ConfigSchema(
            key="SESSION_TIMEOUT_MINUTES",
            required=False,
            default_value=480,  # 8 hours
            sensitivity=ConfigSensitivity.PUBLIC,
            secret_type=None,
            description="User session timeout in minutes"
        ),
        
        # Security Configuration
        "ENABLE_AUDIT_LOGGING": ConfigSchema(
            key="ENABLE_AUDIT_LOGGING",
            required=False,
            default_value=True,
            sensitivity=ConfigSensitivity.PUBLIC,
            secret_type=None,
            description="Enable comprehensive audit logging"
        ),
        
        "REQUIRE_MFA": ConfigSchema(
            key="REQUIRE_MFA",
            required=False,
            default_value=True,
            sensitivity=ConfigSensitivity.INTERNAL,
            secret_type=None,
            description="Require multi-factor authentication for privileged operations"
        ),
        
        "IP_WHITELIST": ConfigSchema(
            key="IP_WHITELIST",
            required=False,
            default_value=None,
            sensitivity=ConfigSensitivity.CONFIDENTIAL,
            secret_type=None,
            description="Comma-separated list of allowed IP addresses/ranges"
        )
    }


def validate_environment_config(env_config: EnvironmentConfig) -> List[str]:
    errors = []
    
    if not env_config.environment:
        errors.append("Environment name is required")
    
    if not env_config.azure_tenant_id:
        errors.append("Azure tenant ID is required")
    
    if not env_config.azure_key_vault_url:
        errors.append("Azure Key Vault URL is required")
    elif not env_config.azure_key_vault_url.startswith("https://"):
        errors.append("Azure Key Vault URL must use HTTPS")
    elif not ".vault.azure.net" in env_config.azure_key_vault_url:
        errors.append("Azure Key Vault URL must be a valid Azure Key Vault endpoint")
    
    if not env_config.azure_client_id:
        errors.append("Azure client ID is required")
    
    if env_config.is_production and env_config.debug_mode:
        errors.append("Debug mode must be disabled in production environment")
    
    return errors


def create_production_defaults() -> Dict[str, Any]:
    return {
        "ENVIRONMENT": "production",
        "LOG_LEVEL": "INFO",
        "REQUIRE_MFA": True,
        "ENABLE_AUDIT_LOGGING": True,
        "SESSION_TIMEOUT_MINUTES": 240,  # 4 hours in production
        "MAX_REQUEST_SIZE": 8388608,  # 8MB in production
        "COST_BUDGET_LIMIT": 1500.0
    }


def create_development_defaults() -> Dict[str, Any]:
    return {
        "ENVIRONMENT": "development", 
        "LOG_LEVEL": "DEBUG",
        "REQUIRE_MFA": False,
        "ENABLE_AUDIT_LOGGING": True,
        "SESSION_TIMEOUT_MINUTES": 480,  # 8 hours in development
        "MAX_REQUEST_SIZE": 16777216,  # 16MB in development
        "COST_BUDGET_LIMIT": 100.0,  # Lower budget for dev
        "DATABASE_HOST": "localhost",
        "DATABASE_NAME": "mimir_regops_dev",
        "REDIS_URL": "redis://localhost:6379/1"
    }


def get_required_secrets() -> List[str]:
    schema = create_config_schema()
    
    return [
        key for key, config in schema.items()
        if config.sensitivity == ConfigSensitivity.SECRET and config.required
    ]


def get_key_vault_secret_mapping() -> Dict[str, str]:
    return {
        "DATABASE_PASSWORD": "prod-database-password-mimir-regops",
        "PARALLEL_API_KEY": "prod-api-key-parallel-ai", 
        "JWT_SECRET_KEY": "prod-signing-key-jwt-auth",
        "WEBHOOK_SECRET": "prod-webhook-secret-validation"
    }


def validate_config_value(schema: ConfigSchema, value: Any) -> bool:
    return schema.validate_value(value)


def mask_sensitive_config(config: Dict[str, Any]) -> Dict[str, Any]:
    schema = create_config_schema()
    masked = {}
    
    for key, value in config.items():
        config_schema = schema.get(key)
        
        if config_schema and config_schema.is_sensitive:
            if isinstance(value, str) and len(value) > 8:
                masked[key] = value[:4] + "*" * (len(value) - 8) + value[-4:]
            elif isinstance(value, str):
                masked[key] = "*" * len(value)
            else:
                masked[key] = "***MASKED***"
        else:
            masked[key] = value
    
    return masked


def get_config_dependencies() -> Dict[str, List[str]]:
    return {
        "database": ["DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD"],
        "redis": ["REDIS_URL"],
        "azure": ["AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_KEY_VAULT_URL"],
        "parallel": ["PARALLEL_API_KEY", "PARALLEL_BASE_URL"],
        "security": ["JWT_SECRET_KEY", "WEBHOOK_SECRET"],
        "audit": ["ENABLE_AUDIT_LOGGING"]
    }


def detect_missing_critical_config(config: Dict[str, Any]) -> List[str]:
    critical_keys = [
        "ENVIRONMENT",
        "AZURE_KEY_VAULT_URL",
        "DATABASE_PASSWORD",
        "JWT_SECRET_KEY"
    ]
    
    missing = []
    for key in critical_keys:
        if key not in config or config[key] is None or config[key] == "":
            missing.append(key)
    
    return missing


def create_config_validation_report(
    config: Dict[str, Any]
) -> Dict[str, Any]:
    schema = create_config_schema()
    report = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "missing_optional": [],
        "insecure_defaults": [],
        "summary": {}
    }
    
    total_configs = len(schema)
    configured_count = 0
    secret_count = 0
    valid_count = 0
    
    for key, config_schema in schema.items():
        value = config.get(key)
        
        if value is not None:
            configured_count += 1
            
            if config_schema.sensitivity == ConfigSensitivity.SECRET:
                secret_count += 1
            
            if validate_config_value(config_schema, value):
                valid_count += 1
            else:
                report["valid"] = False
                report["errors"].append(f"Invalid value for {key}")
        
        elif config_schema.required:
            report["valid"] = False
            report["errors"].append(f"Required configuration {key} is missing")
        else:
            report["missing_optional"].append(key)
        
        if value == config_schema.default_value and config_schema.is_sensitive:
            report["warnings"].append(f"Using default value for sensitive config {key}")
    
    environment = config.get("ENVIRONMENT", "unknown").lower()
    if environment == "production":
        dev_configs = ["DEBUG", "DEVELOPMENT", "TEST"]
        for dev_config in dev_configs:
            if config.get(dev_config, False):
                report["insecure_defaults"].append(f"Development setting {dev_config} enabled in production")
    
    report["summary"] = {
        "total_configs": total_configs,
        "configured_count": configured_count,
        "valid_count": valid_count,
        "secret_count": secret_count,
        "completion_rate": configured_count / total_configs,
        "validation_rate": valid_count / configured_count if configured_count > 0 else 0
    }
    
    return report