import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
import redis
from .contracts import (
    VaultConfig, SecretMetadata, SecretValue, SecretType,
    RotationStatus, RotationPolicy, SecretNotFoundError,
    VaultAccessDeniedError, VaultError
)
from .core import (
    validate_secret_expiry, calculate_rotation_status,
    generate_secret_name, calculate_cache_key, is_cache_expired
)


logger = logging.getLogger(__name__)


class KeyVaultService:
    def __init__(
        self,
        config: VaultConfig,
        redis_client: Optional[redis.Redis] = None
    ):
        self.config = config
        self.redis_client = redis_client
        self._client: Optional[SecretClient] = None
        self._cache: Dict[str, tuple[SecretValue, datetime]] = {}
        
    def _get_client(self) -> SecretClient:
        if not self._client:
            if self.config.use_managed_identity:
                credential = ManagedIdentityCredential(
                    client_id=self.config.client_id
                )
            else:
                credential = DefaultAzureCredential(
                    exclude_managed_identity_credential=False,
                    tenant_id=self.config.tenant_id
                )
            
            self._client = SecretClient(
                vault_url=self.config.vault_url,
                credential=credential
            )
        
        return self._client
    
    async def get_secret(
        self,
        secret_name: str,
        use_cache: bool = True
    ) -> SecretValue:
        cache_key = calculate_cache_key(secret_name, self.config.environment)
        
        if use_cache:
            cached = await self._get_cached_secret(cache_key)
            if cached:
                return cached
        
        try:
            client = self._get_client()
            secret = await asyncio.get_event_loop().run_in_executor(
                None, client.get_secret, secret_name
            )
            
            metadata = SecretMetadata(
                name=secret.name,
                version=secret.properties.version,
                secret_type=self._parse_secret_type(secret.properties.tags),
                created_at=secret.properties.created_on or datetime.now(timezone.utc),
                expires_at=secret.properties.expires_on or 
                    datetime.now(timezone.utc).replace(year=9999),
                rotation_status=RotationStatus.CURRENT,
                tags=secret.properties.tags or {}
            )
            
            validate_secret_expiry(metadata)
            
            secret_value = SecretValue(
                value=secret.value,
                metadata=metadata
            )
            
            if use_cache:
                await self._cache_secret(cache_key, secret_value)
            
            logger.info(
                f"Retrieved secret {secret_name} from Key Vault",
                extra={"secret_name": secret_name, "version": metadata.version}
            )
            
            return secret_value
            
        except ResourceNotFoundError:
            raise SecretNotFoundError(f"Secret {secret_name} not found in Key Vault")
        except HttpResponseError as e:
            if e.status_code == 403:
                raise VaultAccessDeniedError(f"Access denied to secret {secret_name}")
            raise VaultError(f"Failed to retrieve secret: {str(e)}")
    
    async def set_secret(
        self,
        secret_name: str,
        secret_value: str,
        secret_type: SecretType,
        tags: Optional[Dict[str, str]] = None
    ) -> SecretMetadata:
        try:
            client = self._get_client()
            
            all_tags = {
                "secret_type": secret_type.value,
                "environment": self.config.environment,
                "created_by": "mimir-security",
                **(tags or {})
            }
            
            secret = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.set_secret(
                    secret_name,
                    secret_value,
                    tags=all_tags,
                    content_type="text/plain"
                )
            )
            
            metadata = SecretMetadata(
                name=secret.name,
                version=secret.properties.version,
                secret_type=secret_type,
                created_at=secret.properties.created_on,
                expires_at=secret.properties.expires_on or 
                    datetime.now(timezone.utc).replace(year=9999),
                rotation_status=RotationStatus.CURRENT,
                tags=all_tags
            )
            
            await self._invalidate_cache(secret_name)
            
            logger.info(
                f"Created/updated secret {secret_name} in Key Vault",
                extra={"secret_name": secret_name, "version": metadata.version}
            )
            
            return metadata
            
        except HttpResponseError as e:
            if e.status_code == 403:
                raise VaultAccessDeniedError(f"Access denied to create secret {secret_name}")
            raise VaultError(f"Failed to set secret: {str(e)}")
    
    async def list_secrets(
        self,
        secret_type: Optional[SecretType] = None
    ) -> List[SecretMetadata]:
        try:
            client = self._get_client()
            secrets = []
            
            secret_properties = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(client.list_properties_of_secrets())
            )
            
            for props in secret_properties:
                if props.tags:
                    prop_type = self._parse_secret_type(props.tags)
                    if secret_type and prop_type != secret_type:
                        continue
                    
                    metadata = SecretMetadata(
                        name=props.name,
                        version=props.version,
                        secret_type=prop_type,
                        created_at=props.created_on or datetime.now(timezone.utc),
                        expires_at=props.expires_on or 
                            datetime.now(timezone.utc).replace(year=9999),
                        rotation_status=RotationStatus.CURRENT,
                        tags=props.tags
                    )
                    secrets.append(metadata)
            
            return secrets
            
        except HttpResponseError as e:
            if e.status_code == 403:
                raise VaultAccessDeniedError("Access denied to list secrets")
            raise VaultError(f"Failed to list secrets: {str(e)}")
    
    async def rotate_secret(
        self,
        secret_name: str,
        new_value: str,
        keep_versions: int = 3
    ) -> SecretMetadata:
        current = await self.get_secret(secret_name, use_cache=False)
        
        new_tags = {
            **current.metadata.tags,
            "rotated_from": current.metadata.version,
            "rotated_at": datetime.now(timezone.utc).isoformat()
        }
        
        new_metadata = await self.set_secret(
            secret_name,
            new_value,
            current.metadata.secret_type,
            new_tags
        )
        
        await self._cleanup_old_versions(secret_name, keep_versions)
        
        logger.info(
            f"Rotated secret {secret_name}",
            extra={
                "secret_name": secret_name,
                "old_version": current.metadata.version,
                "new_version": new_metadata.version
            }
        )
        
        return new_metadata
    
    async def _get_cached_secret(self, cache_key: str) -> Optional[SecretValue]:
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    data = json.loads(cached_data)
                    cached_at = datetime.fromisoformat(data["cached_at"])
                    
                    if not is_cache_expired(cached_at, self.config.cache_ttl_seconds):
                        metadata = SecretMetadata(**data["metadata"])
                        return SecretValue(value=data["value"], metadata=metadata)
            except Exception as e:
                logger.warning(f"Failed to retrieve from Redis cache: {e}")
        
        if cache_key in self._cache:
            secret_value, cached_at = self._cache[cache_key]
            if not is_cache_expired(cached_at, self.config.cache_ttl_seconds):
                return secret_value
        
        return None
    
    async def _cache_secret(self, cache_key: str, secret_value: SecretValue):
        cached_at = datetime.now(timezone.utc)
        
        self._cache[cache_key] = (secret_value, cached_at)
        
        if self.redis_client:
            try:
                cache_data = {
                    "value": secret_value.value,
                    "metadata": {
                        "name": secret_value.metadata.name,
                        "version": secret_value.metadata.version,
                        "secret_type": secret_value.metadata.secret_type.value,
                        "created_at": secret_value.metadata.created_at.isoformat(),
                        "expires_at": secret_value.metadata.expires_at.isoformat(),
                        "rotation_status": secret_value.metadata.rotation_status.value,
                        "tags": secret_value.metadata.tags
                    },
                    "cached_at": cached_at.isoformat()
                }
                
                self.redis_client.setex(
                    cache_key,
                    self.config.cache_ttl_seconds,
                    json.dumps(cache_data)
                )
            except Exception as e:
                logger.warning(f"Failed to cache in Redis: {e}")
    
    async def _invalidate_cache(self, secret_name: str):
        cache_key = calculate_cache_key(secret_name, self.config.environment)
        
        if cache_key in self._cache:
            del self._cache[cache_key]
        
        if self.redis_client:
            try:
                self.redis_client.delete(cache_key)
            except Exception as e:
                logger.warning(f"Failed to invalidate Redis cache: {e}")
    
    async def _cleanup_old_versions(self, secret_name: str, keep_versions: int):
        try:
            client = self._get_client()
            versions = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(client.list_properties_of_secret_versions(secret_name))
            )
            
            versions.sort(key=lambda v: v.created_on, reverse=True)
            
            for version in versions[keep_versions:]:
                if not version.enabled:
                    continue
                    
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda v=version: client.update_secret_properties(
                        secret_name,
                        version=v.version,
                        enabled=False
                    )
                )
                
                logger.info(
                    f"Disabled old version of secret {secret_name}",
                    extra={"secret_name": secret_name, "version": version.version}
                )
                
        except Exception as e:
            logger.warning(f"Failed to cleanup old versions: {e}")
    
    def _parse_secret_type(self, tags: Dict[str, str]) -> SecretType:
        type_str = tags.get("secret_type", "api_key")
        try:
            return SecretType(type_str)
        except ValueError:
            return SecretType.API_KEY