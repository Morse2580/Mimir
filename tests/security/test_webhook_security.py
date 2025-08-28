import pytest
import time
import hmac
import hashlib
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from backend.app.security.webhooks.contracts import (
    WebhookConfig, WebhookHeaders, WebhookSource, WebhookStatus,
    InvalidSignatureError, TimestampInvalidError, ReplayDetectedError,
    PayloadTooLargeError, RateLimitExceededError
)
from backend.app.security.webhooks.core import (
    generate_hmac_signature, verify_hmac_signature, validate_timestamp,
    create_replay_entry, is_suspicious_payload
)
from backend.app.security.webhooks.shell import WebhookValidator, WebhookSecurityService


class TestWebhookCore:
    def test_generate_hmac_signature(self):
        payload = b"test payload"
        secret = "test-secret-key"
        
        signature = generate_hmac_signature(payload, secret)
        
        expected = hmac.new(
            secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        assert signature == f"sha256={expected}"

    def test_verify_hmac_signature_valid(self):
        payload = b"test payload"
        secret = "test-secret-key"
        
        signature = generate_hmac_signature(payload, secret)
        
        assert verify_hmac_signature(payload, signature, secret) is True

    def test_verify_hmac_signature_invalid(self):
        payload = b"test payload"
        secret = "test-secret-key"
        wrong_signature = "sha256=wrong_signature"
        
        assert verify_hmac_signature(payload, wrong_signature, secret) is False

    def test_verify_hmac_signature_timing_attack_resistant(self):
        payload = b"test payload"
        secret = "test-secret-key"
        
        correct_signature = generate_hmac_signature(payload, secret)
        wrong_signature = "sha256=" + "a" * 64  # Same length, wrong content
        
        # Both operations should take similar time (timing attack resistance)
        start = time.time()
        result1 = verify_hmac_signature(payload, correct_signature, secret)
        time1 = time.time() - start
        
        start = time.time()
        result2 = verify_hmac_signature(payload, wrong_signature, secret)
        time2 = time.time() - start
        
        assert result1 is True
        assert result2 is False
        # Time difference should be minimal (timing attack resistance)
        assert abs(time1 - time2) < 0.001  # Less than 1ms difference

    def test_validate_timestamp_valid(self):
        current_time = datetime.now(timezone.utc)
        timestamp = str(int(current_time.timestamp()))
        
        assert validate_timestamp(timestamp, 300, current_time) is True

    def test_validate_timestamp_expired(self):
        current_time = datetime.now(timezone.utc)
        old_timestamp = str(int(current_time.timestamp()) - 400)  # 400 seconds ago
        
        assert validate_timestamp(old_timestamp, 300, current_time) is False

    def test_validate_timestamp_future(self):
        current_time = datetime.now(timezone.utc)
        future_timestamp = str(int(current_time.timestamp()) + 400)  # 400 seconds in future
        
        assert validate_timestamp(future_timestamp, 300, current_time) is False

    def test_create_replay_entry(self):
        payload = b"test payload"
        signature = "test-signature"
        timestamp = "1234567890"
        source_ip = "192.168.1.1"
        
        entry = create_replay_entry(payload, signature, timestamp, source_ip)
        
        assert entry.signature == signature
        assert entry.source_ip == source_ip
        assert len(entry.request_id) == 16  # Should be 16 character hash

    def test_is_suspicious_payload_normal(self):
        normal_payload = {"event": "test", "data": {"key": "value"}}
        
        assert is_suspicious_payload(normal_payload) is False

    def test_is_suspicious_payload_suspicious(self):
        suspicious_payloads = [
            {"script": "<script>alert('xss')</script>"},
            {"code": "eval(malicious_code)"},
            {"nested": {"very": {"deep": {"nesting": {"structure": {"a": "b"}}}}}},
            {"large_array": ["item"] * 2000}
        ]
        
        for payload in suspicious_payloads:
            assert is_suspicious_payload(payload) is True


class TestWebhookValidator:
    @pytest.fixture
    def webhook_config(self):
        return WebhookConfig(
            source=WebhookSource.PARALLEL_AI,
            secret_key="test-secret-key-12345",
            timestamp_tolerance_seconds=300,
            max_payload_size=1048576,
            rate_limit_per_minute=60
        )

    @pytest.fixture
    def mock_redis(self):
        redis_mock = Mock()
        redis_mock.exists.return_value = False
        redis_mock.setex.return_value = True
        redis_mock.pipeline.return_value.__enter__.return_value.execute.return_value = [1]
        return redis_mock

    @pytest.fixture
    def validator(self, webhook_config, mock_redis):
        return WebhookValidator(webhook_config, mock_redis)

    def create_valid_webhook(self, payload: bytes, secret: str):
        timestamp = str(int(time.time()))
        signature = generate_hmac_signature(payload, secret)
        
        headers = WebhookHeaders(
            signature=signature,
            timestamp=timestamp,
            content_type="application/json",
            content_length=len(payload),
            user_agent="test-agent",
            source_ip="192.168.1.1"
        )
        
        return headers

    @pytest.mark.asyncio
    async def test_validate_webhook_success(self, validator):
        payload = b'{"event": "test", "data": {"key": "value"}}'
        headers = self.create_valid_webhook(payload, validator.config.secret_key)
        
        result = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.VERIFIED
        assert result.is_valid is True
        assert result.payload is not None
        assert result.payload.parsed_data["event"] == "test"

    @pytest.mark.asyncio
    async def test_validate_webhook_invalid_signature(self, validator):
        payload = b'{"event": "test"}'
        headers = WebhookHeaders(
            signature="sha256=invalid_signature",
            timestamp=str(int(time.time())),
            content_type="application/json",
            content_length=len(payload),
            user_agent="test-agent",
            source_ip="192.168.1.1"
        )
        
        result = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.INVALID_SIGNATURE
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_webhook_expired_timestamp(self, validator):
        payload = b'{"event": "test"}'
        old_timestamp = str(int(time.time()) - 400)  # 400 seconds ago
        signature = generate_hmac_signature(payload, validator.config.secret_key)
        
        headers = WebhookHeaders(
            signature=signature,
            timestamp=old_timestamp,
            content_type="application/json",
            content_length=len(payload),
            user_agent="test-agent",
            source_ip="192.168.1.1"
        )
        
        result = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.TIMESTAMP_INVALID
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_webhook_payload_too_large(self, validator):
        large_payload = b"x" * (validator.config.max_payload_size + 1)
        headers = self.create_valid_webhook(large_payload, validator.config.secret_key)
        
        result = await validator.validate_webhook(
            large_payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.PAYLOAD_TOO_LARGE
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_webhook_rate_limited(self, validator):
        payload = b'{"event": "test"}'
        headers = self.create_valid_webhook(payload, validator.config.secret_key)
        
        # Mock Redis to return rate limit exceeded
        validator.redis_client.pipeline.return_value.__enter__.return_value.execute.return_value = [61]
        
        result = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.RATE_LIMITED
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_webhook_replay_detected(self, validator):
        payload = b'{"event": "test"}'
        headers = self.create_valid_webhook(payload, validator.config.secret_key)
        
        # Mock Redis to indicate replay exists
        validator.redis_client.exists.return_value = True
        
        result = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.REPLAY_DETECTED
        assert result.is_valid is False

    @pytest.mark.asyncio
    async def test_validate_webhook_suspicious_content(self, validator):
        suspicious_payload = b'{"script": "<script>alert(\'xss\')</script>"}'
        headers = self.create_valid_webhook(suspicious_payload, validator.config.secret_key)
        
        result = await validator.validate_webhook(
            suspicious_payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.INVALID_SIGNATURE
        assert result.is_valid is False


class TestWebhookSecurityService:
    @pytest.fixture
    def security_service(self):
        mock_redis = Mock()
        mock_redis.exists.return_value = False
        return WebhookSecurityService(mock_redis)

    def test_register_source(self, security_service):
        config = WebhookConfig(
            source=WebhookSource.PARALLEL_AI,
            secret_key="test-key"
        )
        
        security_service.register_source(WebhookSource.PARALLEL_AI, config)
        
        assert WebhookSource.PARALLEL_AI in security_service._validators

    @pytest.mark.asyncio
    async def test_validate_webhook_unknown_source(self, security_service):
        result = await security_service.validate_webhook(
            WebhookSource.PARALLEL_AI,
            b"test payload",
            {"X-Signature": "test"}
        )
        
        assert result.status == WebhookStatus.INVALID_SIGNATURE
        assert "Unknown webhook source" in result.error_message

    @pytest.mark.asyncio
    async def test_validate_webhook_with_registered_source(self, security_service):
        config = WebhookConfig(
            source=WebhookSource.PARALLEL_AI,
            secret_key="test-secret-key"
        )
        security_service.register_source(WebhookSource.PARALLEL_AI, config)
        
        payload = b'{"test": "data"}'
        timestamp = str(int(time.time()))
        signature = generate_hmac_signature(payload, "test-secret-key")
        
        headers = {
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "Content-Type": "application/json"
        }
        
        result = await security_service.validate_webhook(
            WebhookSource.PARALLEL_AI,
            payload,
            headers
        )
        
        assert result.status == WebhookStatus.VERIFIED

    def test_get_security_metrics(self, security_service):
        config1 = WebhookConfig(source=WebhookSource.PARALLEL_AI, secret_key="key1")
        config2 = WebhookConfig(source=WebhookSource.NBB_ONEGATE, secret_key="key2")
        
        security_service.register_source(WebhookSource.PARALLEL_AI, config1)
        security_service.register_source(WebhookSource.NBB_ONEGATE, config2)
        
        metrics = security_service.get_security_metrics()
        
        assert metrics["registered_sources"] == 2
        assert WebhookSource.PARALLEL_AI.value in metrics["sources"]
        assert WebhookSource.NBB_ONEGATE.value in metrics["sources"]


class TestWebhookSecurityAttacks:
    """Test webhook validation against common security attacks."""
    
    def test_timing_attack_resistance(self):
        payload = b"test payload"
        secret = "correct-secret"
        
        correct_signature = generate_hmac_signature(payload, secret)
        
        # Test multiple wrong signatures of same length
        wrong_signatures = [
            "sha256=" + "a" * 64,
            "sha256=" + "b" * 64, 
            "sha256=" + "f" * 64
        ]
        
        times = []
        for sig in wrong_signatures:
            start = time.time()
            verify_hmac_signature(payload, sig, secret)
            times.append(time.time() - start)
        
        # All wrong signatures should take similar time
        max_time = max(times)
        min_time = min(times)
        assert (max_time - min_time) < 0.001  # Less than 1ms variance

    @pytest.mark.asyncio
    async def test_replay_attack_prevention(self):
        config = WebhookConfig(
            source=WebhookSource.PARALLEL_AI,
            secret_key="test-key",
            replay_cache_ttl=300
        )
        
        mock_redis = Mock()
        mock_redis.exists.return_value = False
        mock_redis.setex.return_value = True
        
        validator = WebhookValidator(config, mock_redis)
        
        payload = b'{"event": "test"}'
        headers = WebhookHeaders(
            signature=generate_hmac_signature(payload, config.secret_key),
            timestamp=str(int(time.time())),
            content_type="application/json",
            content_length=len(payload),
            user_agent="test-agent",
            source_ip="192.168.1.1"
        )
        
        # First request should succeed
        result1 = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        assert result1.status == WebhookStatus.VERIFIED
        
        # Mock Redis to simulate replay detection
        mock_redis.exists.return_value = True
        
        # Second identical request should be blocked
        result2 = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        assert result2.status == WebhookStatus.REPLAY_DETECTED

    def test_xss_payload_detection(self):
        malicious_payloads = [
            {"message": "<script>alert('xss')</script>"},
            {"data": "<img src=x onerror=alert('xss')>"},
            {"content": "javascript:alert('xss')"},
            {"eval": "eval(document.cookie)"}
        ]
        
        for payload in malicious_payloads:
            assert is_suspicious_payload(payload) is True

    def test_injection_payload_detection(self):
        injection_payloads = [
            {"query": "'; DROP TABLE users; --"},
            {"command": "$(rm -rf /)"},
            {"code": "__import__('os').system('rm -rf /')"},
            {"exec": "exec('malicious_code')"}
        ]
        
        for payload in injection_payloads:
            assert is_suspicious_payload(payload) is True

    @pytest.mark.asyncio
    async def test_dos_protection_large_payload(self):
        config = WebhookConfig(
            source=WebhookSource.PARALLEL_AI,
            secret_key="test-key",
            max_payload_size=1024  # 1KB limit
        )
        
        validator = WebhookValidator(config)
        
        # Create payload larger than limit
        large_payload = b"x" * 2048  # 2KB
        headers = WebhookHeaders(
            signature=generate_hmac_signature(large_payload, config.secret_key),
            timestamp=str(int(time.time())),
            content_type="application/json",
            content_length=len(large_payload),
            user_agent="test-agent",
            source_ip="192.168.1.1"
        )
        
        result = await validator.validate_webhook(
            large_payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.PAYLOAD_TOO_LARGE

    @pytest.mark.asyncio
    async def test_dos_protection_rate_limiting(self):
        config = WebhookConfig(
            source=WebhookSource.PARALLEL_AI,
            secret_key="test-key",
            rate_limit_per_minute=5
        )
        
        mock_redis = Mock()
        validator = WebhookValidator(config, mock_redis)
        
        # Simulate multiple requests from same IP
        payload = b'{"test": "data"}'
        headers = WebhookHeaders(
            signature=generate_hmac_signature(payload, config.secret_key),
            timestamp=str(int(time.time())),
            content_type="application/json", 
            content_length=len(payload),
            user_agent="test-agent",
            source_ip="192.168.1.1"
        )
        
        # Mock Redis to return high request count
        mock_redis.pipeline.return_value.__enter__.return_value.execute.return_value = [6]  # Over limit
        
        result = await validator.validate_webhook(
            payload, headers, WebhookSource.PARALLEL_AI
        )
        
        assert result.status == WebhookStatus.RATE_LIMITED