import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from ..vault.shell import KeyVaultService
from ..vault.contracts import SecretType, SecretNotFoundError
from .contracts import (
    ConfigValue, ConfigSource, ConfigSensitivity, EnvironmentConfig,
    ConfigError, ConfigValidationError, SecretNotConfiguredError,
    ConfigSourceUnavailableError
)
from .core import (
    create_config_schema, validate_environment_config, get_required_secrets,
    get_key_vault_secret_mapping, create_production_defaults,
    create_development_defaults, detect_missing_critical_config,
    create_config_validation_report
)


logger = logging.getLogger(__name__)


class SecureConfigManager:
    def __init__(
        self,
        vault_service: Optional[KeyVaultService] = None,
        environment: Optional[str] = None
    ):
        self.vault_service = vault_service
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.schema = create_config_schema()
        self._config_cache: Dict[str, ConfigValue] = {}
        self._fallback_enabled = True
        
        self._initialize_environment_defaults()
    
    def _initialize_environment_defaults(self):
        if self.environment.lower() == "production":
            defaults = create_production_defaults()
        else:
            defaults = create_development_defaults()
        
        for key, value in defaults.items():
            if key not in self._config_cache:
                schema = self.schema.get(key)
                if schema:
                    self._config_cache[key] = ConfigValue(
                        key=key,
                        value=value,
                        source=ConfigSource.DEFAULT,
                        sensitivity=schema.sensitivity,
                        last_updated=datetime.now(timezone.utc),
                        description=schema.description
                    )
    
    async def initialize(self, env_config: EnvironmentConfig) -> bool:
        validation_errors = validate_environment_config(env_config)
        if validation_errors:
            logger.error(f"Environment configuration validation failed: {validation_errors}")
            return False
        
        try:
            await self._load_secrets_from_vault()
            
            await self._load_from_environment()
            
            missing_critical = detect_missing_critical_config(self.get_all_config())
            if missing_critical:
                logger.critical(f"Missing critical configuration: {missing_critical}")
                return False
            
            logger.info(
                "Secure configuration manager initialized successfully",
                extra={
                    "environment": self.environment,
                    "config_count": len(self._config_cache),
                    "secrets_loaded": len(await self._get_loaded_secrets())
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize configuration manager: {str(e)}", exc_info=True)
            return False
    
    async def get_config(self, key: str, default: Any = None) -> Any:
        if key in self._config_cache:
            config_value = self._config_cache[key]
            
            if config_value.is_expired:
                logger.warning(f"Configuration {key} has expired, attempting refresh")
                await self._refresh_config(key)
            
            return self._config_cache[key].value
        
        schema = self.schema.get(key)
        if not schema:
            logger.warning(f"Unknown configuration key: {key}")
            return default
        
        try:
            value = await self._fetch_config_value(key, schema)
            return value
        except ConfigError:
            if schema.default_value is not None:
                logger.info(f"Using default value for configuration {key}")
                return schema.default_value
            
            if default is not None:
                return default
            
            if schema.required:
                raise SecretNotConfiguredError(f"Required configuration {key} not found")
            
            return None
    
    async def get_database_url(self) -> str:
        host = await self.get_config("DATABASE_HOST")
        name = await self.get_config("DATABASE_NAME") 
        user = await self.get_config("DATABASE_USER")
        password = await self.get_config("DATABASE_PASSWORD")
        
        if not all([host, name, user, password]):
            raise ConfigError("Incomplete database configuration")
        
        return f"postgresql://{user}:{password}@{host}/{name}"
    
    async def get_redis_config(self) -> Dict[str, Any]:
        redis_url = await self.get_config("REDIS_URL")
        
        if not redis_url:
            raise ConfigError("Redis configuration not found")
        
        return {"url": redis_url}
    
    async def get_parallel_config(self) -> Dict[str, Any]:
        api_key = await self.get_config("PARALLEL_API_KEY")
        base_url = await self.get_config("PARALLEL_BASE_URL")
        
        if not api_key:
            raise ConfigError("Parallel.ai API key not configured")
        
        return {
            "api_key": api_key,
            "base_url": base_url,
            "budget_limit": await self.get_config("COST_BUDGET_LIMIT", 1500.0)
        }
    
    async def get_jwt_config(self) -> Dict[str, Any]:
        secret_key = await self.get_config("JWT_SECRET_KEY")
        
        if not secret_key:
            raise ConfigError("JWT secret key not configured")
        
        return {
            "secret_key": secret_key,
            "algorithm": "HS256",
            "issuer": "mimir-regops"
        }
    
    async def get_webhook_config(self) -> Dict[str, str]:
        webhook_secret = await self.get_config("WEBHOOK_SECRET")
        
        if not webhook_secret:
            raise ConfigError("Webhook secret not configured")
        
        return {"secret": webhook_secret}
    
    def get_all_config(self, include_secrets: bool = False) -> Dict[str, Any]:
        result = {}
        
        for key, config_value in self._config_cache.items():
            if config_value.is_sensitive and not include_secrets:
                result[key] = config_value.masked_value()
            else:
                result[key] = config_value.value
        
        return result
    
    async def validate_configuration(self) -> Dict[str, Any]:
        config_dict = {key: cv.value for key, cv in self._config_cache.items()}
        return create_config_validation_report(config_dict)
    
    async def refresh_secrets(self) -> bool:
        if not self.vault_service:
            logger.warning("Cannot refresh secrets: Vault service not available")
            return False
        
        try:
            await self._load_secrets_from_vault()
            logger.info("Successfully refreshed secrets from Key Vault")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh secrets: {str(e)}")
            return False
    
    async def _load_secrets_from_vault(self):
        if not self.vault_service:
            return
        
        secret_mapping = get_key_vault_secret_mapping()
        
        for config_key, vault_key in secret_mapping.items():
            try:
                secret_value = await self.vault_service.get_secret(vault_key)
                
                schema = self.schema.get(config_key)
                if not schema:
                    continue
                
                self._config_cache[config_key] = ConfigValue(
                    key=config_key,
                    value=secret_value.value,
                    source=ConfigSource.KEY_VAULT,
                    sensitivity=schema.sensitivity,
                    last_updated=datetime.now(timezone.utc),
                    expires_at=secret_value.metadata.expires_at,
                    description=schema.description
                )
                
                logger.debug(f"Loaded secret {config_key} from Key Vault")
                
            except SecretNotFoundError:
                logger.warning(f"Secret {vault_key} not found in Key Vault")
                
                if self._fallback_enabled:
                    env_value = os.getenv(config_key)
                    if env_value:
                        logger.warning(f"Using environment fallback for {config_key}")
                        schema = self.schema.get(config_key)
                        self._config_cache[config_key] = ConfigValue(
                            key=config_key,
                            value=env_value,
                            source=ConfigSource.ENVIRONMENT,
                            sensitivity=schema.sensitivity if schema else ConfigSensitivity.SECRET,
                            last_updated=datetime.now(timezone.utc),
                            description="Environment fallback"
                        )
            
            except Exception as e:
                logger.error(f"Failed to load secret {config_key}: {str(e)}")
    
    async def _load_from_environment(self):
        for key, schema in self.schema.items():
            if key in self._config_cache and self._config_cache[key].source == ConfigSource.KEY_VAULT:
                continue  # Secrets from Key Vault take precedence
            
            env_value = os.getenv(key)
            if env_value is not None:
                parsed_value = self._parse_env_value(env_value, schema)
                
                if not schema.validate_value(parsed_value):
                    logger.error(f"Invalid environment value for {key}")
                    continue
                
                self._config_cache[key] = ConfigValue(
                    key=key,
                    value=parsed_value,
                    source=ConfigSource.ENVIRONMENT,
                    sensitivity=schema.sensitivity,
                    last_updated=datetime.now(timezone.utc),
                    description=schema.description
                )
    
    def _parse_env_value(self, value: str, schema) -> Any:
        if isinstance(schema.default_value, bool):
            return value.lower() in {'true', '1', 'yes', 'on'}
        elif isinstance(schema.default_value, int):
            try:
                return int(value)
            except ValueError:
                return value
        elif isinstance(schema.default_value, float):
            try:
                return float(value)
            except ValueError:
                return value
        
        return value
    
    async def _fetch_config_value(self, key: str, schema) -> Any:
        if schema.sensitivity == ConfigSensitivity.SECRET and self.vault_service:
            try:
                secret_mapping = get_key_vault_secret_mapping()
                vault_key = secret_mapping.get(key)
                
                if vault_key:
                    secret_value = await self.vault_service.get_secret(vault_key)
                    
                    self._config_cache[key] = ConfigValue(
                        key=key,
                        value=secret_value.value,
                        source=ConfigSource.KEY_VAULT,
                        sensitivity=schema.sensitivity,
                        last_updated=datetime.now(timezone.utc),
                        expires_at=secret_value.metadata.expires_at,
                        description=schema.description
                    )
                    
                    return secret_value.value
                    
            except SecretNotFoundError:
                pass  # Fall through to environment check
        
        env_value = os.getenv(key)
        if env_value:
            parsed_value = self._parse_env_value(env_value, schema)
            
            if schema.validate_value(parsed_value):
                self._config_cache[key] = ConfigValue(
                    key=key,
                    value=parsed_value,
                    source=ConfigSource.ENVIRONMENT,
                    sensitivity=schema.sensitivity,
                    last_updated=datetime.now(timezone.utc),
                    description=schema.description
                )
                
                return parsed_value
        
        raise ConfigError(f"Configuration {key} not found in any source")
    
    async def _refresh_config(self, key: str):
        schema = self.schema.get(key)
        if not schema:
            return
        
        try:
            value = await self._fetch_config_value(key, schema)
            logger.info(f"Refreshed configuration {key}")
        except ConfigError:
            logger.warning(f"Failed to refresh configuration {key}")
    
    async def _get_loaded_secrets(self) -> List[str]:
        return [
            key for key, config_value in self._config_cache.items()
            if config_value.sensitivity == ConfigSensitivity.SECRET
        ]


async def create_secure_config_manager(
    vault_service: Optional[KeyVaultService] = None,
    environment: Optional[str] = None
) -> SecureConfigManager:
    config_manager = SecureConfigManager(vault_service, environment)
    
    env_config = EnvironmentConfig(
        environment=environment or os.getenv("ENVIRONMENT", "development"),
        azure_tenant_id=os.getenv("AZURE_TENANT_ID", ""),
        azure_key_vault_url=os.getenv("AZURE_KEY_VAULT_URL", ""),
        azure_client_id=os.getenv("AZURE_CLIENT_ID", ""),
        use_managed_identity=os.getenv("USE_MANAGED_IDENTITY", "true").lower() == "true"
    )
    
    success = await config_manager.initialize(env_config)
    if not success:
        raise ConfigError("Failed to initialize secure configuration manager")
    
    return config_manager


def disable_env_file_loading():
    env_vars_to_remove = [
        "DATABASE_PASSWORD",
        "PARALLEL_API_KEY", 
        "JWT_SECRET_KEY",
        "WEBHOOK_SECRET"
    ]
    
    for var in env_vars_to_remove:
        if var in os.environ:
            logger.warning(f"Removing sensitive environment variable {var} from memory")
            del os.environ[var]