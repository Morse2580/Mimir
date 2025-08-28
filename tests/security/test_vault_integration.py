import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from backend.app.security.vault.contracts import (
    VaultConfig, SecretType, RotationStatus, SecretNotFoundError,
    VaultAccessDeniedError, SecretExpiredError
)
from backend.app.security.vault.core import (
    calculate_rotation_status, validate_secret_expiry,
    generate_secret_name, is_cache_expired
)
from backend.app.security.vault.shell import KeyVaultService


class TestVaultCore:
    def test_calculate_rotation_status_current(self):
        created_at = datetime.now(timezone.utc)
        rotation_days = 90
        warning_days = 7
        
        status = calculate_rotation_status(created_at, rotation_days, warning_days)
        
        assert status == RotationStatus.CURRENT

    def test_calculate_rotation_status_pending(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=85)
        rotation_days = 90
        warning_days = 7
        
        status = calculate_rotation_status(created_at, rotation_days, warning_days)
        
        assert status == RotationStatus.PENDING_ROTATION

    def test_calculate_rotation_status_expired(self):
        created_at = datetime.now(timezone.utc) - timedelta(days=95)
        rotation_days = 90
        warning_days = 7
        
        status = calculate_rotation_status(created_at, rotation_days, warning_days)
        
        assert status == RotationStatus.EXPIRED

    def test_validate_secret_expiry_valid(self):
        from backend.app.security.vault.contracts import SecretMetadata
        
        metadata = SecretMetadata(
            name="test-secret",
            version="1",
            secret_type=SecretType.API_KEY,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            rotation_status=RotationStatus.CURRENT,
            tags={}
        )
        
        assert validate_secret_expiry(metadata) is True

    def test_validate_secret_expiry_expired(self):
        from backend.app.security.vault.contracts import SecretMetadata
        
        metadata = SecretMetadata(
            name="test-secret",
            version="1",
            secret_type=SecretType.API_KEY,
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
            rotation_status=RotationStatus.EXPIRED,
            tags={}
        )
        
        with pytest.raises(SecretExpiredError):
            validate_secret_expiry(metadata)

    def test_generate_secret_name(self):
        name = generate_secret_name("api-key", SecretType.API_KEY, "production", "v1")
        
        assert name == "production-api_key-api-key-v1"

    def test_is_cache_expired_true(self):
        cached_at = datetime.now(timezone.utc) - timedelta(seconds=600)
        ttl_seconds = 300
        
        assert is_cache_expired(cached_at, ttl_seconds) is True

    def test_is_cache_expired_false(self):
        cached_at = datetime.now(timezone.utc) - timedelta(seconds=100)
        ttl_seconds = 300
        
        assert is_cache_expired(cached_at, ttl_seconds) is False


class TestKeyVaultService:
    @pytest.fixture
    def vault_config(self):
        return VaultConfig(
            vault_url="https://test-vault.vault.azure.net/",
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            environment="test",
            use_managed_identity=False
        )

    @pytest.fixture
    def mock_redis(self):
        redis_mock = Mock()
        redis_mock.get.return_value = None
        redis_mock.setex.return_value = True
        redis_mock.delete.return_value = True
        return redis_mock

    @pytest.fixture
    def vault_service(self, vault_config, mock_redis):
        return KeyVaultService(vault_config, mock_redis)

    @pytest.mark.asyncio
    async def test_get_secret_success(self, vault_service):
        with patch.object(vault_service, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_secret = Mock()
            mock_secret.name = "test-secret"
            mock_secret.value = "secret-value"
            mock_secret.properties.version = "1"
            mock_secret.properties.created_on = datetime.now(timezone.utc)
            mock_secret.properties.expires_on = None
            mock_secret.properties.tags = {"secret_type": "api_key"}
            
            mock_client.get_secret.return_value = mock_secret
            mock_get_client.return_value = mock_client
            
            secret = await vault_service.get_secret("test-secret")
            
            assert secret.value == "secret-value"
            assert secret.metadata.name == "test-secret"
            assert secret.metadata.secret_type == SecretType.API_KEY

    @pytest.mark.asyncio
    async def test_get_secret_not_found(self, vault_service):
        from azure.core.exceptions import ResourceNotFoundError
        
        with patch.object(vault_service, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_client.get_secret.side_effect = ResourceNotFoundError("Not found")
            mock_get_client.return_value = mock_client
            
            with pytest.raises(SecretNotFoundError):
                await vault_service.get_secret("nonexistent-secret")

    @pytest.mark.asyncio
    async def test_get_secret_access_denied(self, vault_service):
        from azure.core.exceptions import HttpResponseError
        
        with patch.object(vault_service, '_get_client') as mock_get_client:
            mock_client = Mock()
            http_error = HttpResponseError("Access denied")
            http_error.status_code = 403
            mock_client.get_secret.side_effect = http_error
            mock_get_client.return_value = mock_client
            
            with pytest.raises(VaultAccessDeniedError):
                await vault_service.get_secret("secret")

    @pytest.mark.asyncio
    async def test_set_secret_success(self, vault_service):
        with patch.object(vault_service, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_secret = Mock()
            mock_secret.name = "new-secret"
            mock_secret.properties.version = "1"
            mock_secret.properties.created_on = datetime.now(timezone.utc)
            mock_secret.properties.expires_on = None
            
            mock_client.set_secret.return_value = mock_secret
            mock_get_client.return_value = mock_client
            
            with patch.object(vault_service, '_invalidate_cache') as mock_invalidate:
                metadata = await vault_service.set_secret(
                    "new-secret",
                    "new-value",
                    SecretType.API_KEY
                )
                
                assert metadata.name == "new-secret"
                assert metadata.version == "1"
                mock_invalidate.assert_called_once_with("new-secret")

    @pytest.mark.asyncio
    async def test_rotate_secret_success(self, vault_service):
        with patch.object(vault_service, 'get_secret') as mock_get_secret, \
             patch.object(vault_service, 'set_secret') as mock_set_secret, \
             patch.object(vault_service, '_cleanup_old_versions') as mock_cleanup:
            
            from backend.app.security.vault.contracts import SecretValue, SecretMetadata
            
            current_metadata = SecretMetadata(
                name="test-secret",
                version="1",
                secret_type=SecretType.API_KEY,
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                rotation_status=RotationStatus.CURRENT,
                tags={"previous": "value"}
            )
            
            current_secret = SecretValue(
                value="old-value",
                metadata=current_metadata
            )
            
            new_metadata = SecretMetadata(
                name="test-secret",
                version="2", 
                secret_type=SecretType.API_KEY,
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                rotation_status=RotationStatus.CURRENT,
                tags={"rotated_from": "1"}
            )
            
            mock_get_secret.return_value = current_secret
            mock_set_secret.return_value = new_metadata
            
            result = await vault_service.rotate_secret("test-secret", "new-value")
            
            assert result.name == "test-secret"
            assert result.version == "2"
            mock_cleanup.assert_called_once_with("test-secret", 3)

    @pytest.mark.asyncio
    async def test_cache_functionality(self, vault_service):
        # Test that cache is used on second call
        with patch.object(vault_service, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_secret = Mock()
            mock_secret.name = "cached-secret"
            mock_secret.value = "cached-value"
            mock_secret.properties.version = "1"
            mock_secret.properties.created_on = datetime.now(timezone.utc)
            mock_secret.properties.expires_on = None
            mock_secret.properties.tags = {"secret_type": "api_key"}
            
            mock_client.get_secret.return_value = mock_secret
            mock_get_client.return_value = mock_client
            
            # First call - should hit vault
            secret1 = await vault_service.get_secret("cached-secret")
            
            # Second call - should use cache
            secret2 = await vault_service.get_secret("cached-secret")
            
            assert secret1.value == secret2.value
            # Client should only be called once due to caching
            mock_client.get_secret.assert_called_once()


class TestVaultSecurity:
    @pytest.mark.asyncio
    async def test_pii_not_logged_in_vault_operations(self, caplog):
        config = VaultConfig(
            vault_url="https://test-vault.vault.azure.net/",
            tenant_id="test-tenant-id", 
            client_id="test-client-id"
        )
        
        vault_service = KeyVaultService(config)
        
        with patch.object(vault_service, '_get_client') as mock_get_client:
            mock_client = Mock()
            http_error = HttpResponseError("Access denied")
            http_error.status_code = 403
            mock_client.get_secret.side_effect = http_error
            mock_get_client.return_value = mock_client
            
            with pytest.raises(VaultAccessDeniedError):
                await vault_service.get_secret("user-email-john.doe@company.com")
            
            # Check that PII is not in logs
            for record in caplog.records:
                assert "john.doe@company.com" not in record.message
                assert "@company.com" not in record.message

    def test_secret_value_repr_masks_value(self):
        from backend.app.security.vault.contracts import SecretValue, SecretMetadata
        
        metadata = SecretMetadata(
            name="test-secret",
            version="1",
            secret_type=SecretType.API_KEY,
            created_at=datetime.now(timezone.utc),
            expires_at=None,
            rotation_status=RotationStatus.CURRENT,
            tags={}
        )
        
        secret = SecretValue(value="super-secret-value", metadata=metadata)
        
        repr_str = repr(secret)
        assert "super-secret-value" not in repr_str
        assert "***" in repr_str

    @pytest.mark.asyncio
    async def test_vault_client_credential_security(self):
        config = VaultConfig(
            vault_url="https://test-vault.vault.azure.net/",
            tenant_id="tenant-id",
            client_id="client-id",
            use_managed_identity=True
        )
        
        vault_service = KeyVaultService(config)
        
        # Test that managed identity is preferred over client secrets
        with patch('backend.app.security.vault.shell.ManagedIdentityCredential') as mock_managed_cred, \
             patch('backend.app.security.vault.shell.DefaultAzureCredential') as mock_default_cred:
            
            vault_service._get_client()
            
            # Should use managed identity when configured
            mock_managed_cred.assert_called_once_with(client_id="client-id")
            mock_default_cred.assert_not_called()

    @pytest.mark.asyncio
    async def test_secret_cache_encryption_at_rest(self, vault_service):
        # Test that cached secrets are properly protected
        sensitive_value = "very-sensitive-api-key-12345"
        
        with patch.object(vault_service, '_get_client') as mock_get_client:
            mock_client = Mock()
            mock_secret = Mock()
            mock_secret.name = "api-key"
            mock_secret.value = sensitive_value
            mock_secret.properties.version = "1"
            mock_secret.properties.created_on = datetime.now(timezone.utc)
            mock_secret.properties.expires_on = None
            mock_secret.properties.tags = {"secret_type": "api_key"}
            
            mock_client.get_secret.return_value = mock_secret
            mock_get_client.return_value = mock_client
            
            await vault_service.get_secret("api-key")
            
            # Verify Redis operations don't log sensitive data
            vault_service.redis_client.setex.assert_called()
            call_args = vault_service.redis_client.setex.call_args
            
            # The actual secret value should not appear in call arguments when logged
            assert sensitive_value not in str(call_args)