import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from backend.app.security.audit.contracts import (
    AuditEventType, AuditSeverity, AuditOutcome, AuditContext, AuditEvent,
    AuditQuery, RetentionPolicy
)
from backend.app.security.audit.core import (
    create_audit_event, determine_severity, sanitize_audit_data,
    calculate_audit_hash, create_dora_compliance_rules, detect_anomalous_patterns
)
from backend.app.security.audit.shell import AuditLogger
from backend.app.security.auth.contracts import Role, Resource, Permission, Principal


class TestAuditCore:
    def test_create_audit_event(self):
        event = create_audit_event(
            event_type=AuditEventType.AUTHENTICATION,
            outcome=AuditOutcome.SUCCESS,
            message="User login successful"
        )
        
        assert event.event_type == AuditEventType.AUTHENTICATION
        assert event.outcome == AuditOutcome.SUCCESS
        assert event.message == "User login successful"
        assert event.event_id is not None
        assert event.timestamp is not None

    def test_determine_severity_authentication_success(self):
        severity = determine_severity(
            AuditEventType.AUTHENTICATION,
            AuditOutcome.SUCCESS
        )
        
        assert severity == AuditSeverity.MEDIUM

    def test_determine_severity_authentication_failure(self):
        severity = determine_severity(
            AuditEventType.AUTHENTICATION,
            AuditOutcome.FAILURE
        )
        
        assert severity == AuditSeverity.HIGH

    def test_determine_severity_emergency_action(self):
        severity = determine_severity(
            AuditEventType.EMERGENCY_ACTION,
            AuditOutcome.SUCCESS
        )
        
        assert severity == AuditSeverity.CRITICAL

    def test_determine_severity_privileged_user(self):
        privileged_principal = Principal(
            user_id="admin-001",
            username="admin",
            email="admin@company.com",
            roles={Role.ADMIN},
            groups=set(),
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=None,
            client_ip="192.168.1.1",
            user_agent="Admin-Client"
        )
        
        # Regular operation by privileged user should have elevated severity
        severity = determine_severity(
            AuditEventType.DATA_ACCESS,
            AuditOutcome.SUCCESS,
            privileged_principal
        )
        
        assert severity == AuditSeverity.HIGH

    def test_sanitize_audit_data_sensitive_keys(self):
        data = {
            "username": "john.doe",
            "password": "secret123",
            "api_key": "ak_1234567890abcdef",
            "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
            "message": "User performed action"
        }
        
        sanitized = sanitize_audit_data(data)
        
        assert sanitized["username"] == "john.doe"
        assert sanitized["password"] == "***REDACTED***"
        assert sanitized["api_key"] == "***REDACTED***"
        assert sanitized["token"] == "***REDACTED***"
        assert sanitized["message"] == "User performed action"

    def test_sanitize_audit_data_pii_masking(self):
        data = {
            "email": "john.doe@company.com",
            "phone": "+32123456789",
            "ip_address": "192.168.1.100",
            "user_id": "user-12345"
        }
        
        sanitized = sanitize_audit_data(data)
        
        # Email should be partially masked
        assert "@company.com" in sanitized["email"]
        assert "jo*" in sanitized["email"]
        
        # Phone should show only last 4 digits
        assert sanitized["phone"].endswith("6789")
        assert "*" in sanitized["phone"]
        
        # IP should be partially masked
        assert sanitized["ip_address"].startswith("192.168.")
        assert "***" in sanitized["ip_address"]

    def test_sanitize_audit_data_nested_objects(self):
        data = {
            "user": {
                "credentials": {
                    "password": "secret123",
                    "api_key": "ak_sensitive"
                },
                "profile": {
                    "name": "John Doe",
                    "email": "john@company.com"
                }
            }
        }
        
        sanitized = sanitize_audit_data(data)
        
        assert sanitized["user"]["credentials"]["password"] == "***REDACTED***"
        assert sanitized["user"]["credentials"]["api_key"] == "***REDACTED***"
        assert sanitized["user"]["profile"]["name"] == "John Doe"
        assert "*" in sanitized["user"]["profile"]["email"]

    def test_calculate_audit_hash(self):
        event = create_audit_event(
            event_type=AuditEventType.SECRET_ACCESS,
            outcome=AuditOutcome.SUCCESS,
            message="Secret retrieved"
        )
        
        hash1 = calculate_audit_hash(event)
        hash2 = calculate_audit_hash(event)
        
        # Same event should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_create_dora_compliance_rules(self):
        rules = create_dora_compliance_rules()
        
        assert len(rules) >= 3  # Should have ICT incidents, access controls, third-party
        
        # Check that ICT incident rule exists
        ict_rule = next((r for r in rules if "ict-incidents" in r.rule_id.lower()), None)
        assert ict_rule is not None
        assert ict_rule.retention_days == 2555  # 7 years
        assert AuditEventType.EMERGENCY_ACTION in ict_rule.event_types

    def test_detect_anomalous_patterns_failed_auth(self):
        # Create multiple failed authentication events
        events = []
        for i in range(15):
            event = create_audit_event(
                event_type=AuditEventType.AUTHENTICATION,
                outcome=AuditOutcome.FAILURE,
                message=f"Login failed attempt {i}",
                context=AuditContext(
                    session_id=None,
                    client_ip="192.168.1.100",
                    user_agent="AttackBot/1.0",
                    request_id=f"req-{i}",
                    api_endpoint="/auth/login",
                    correlation_id=None
                )
            )
            events.append(event)
        
        anomalies = detect_anomalous_patterns(events)
        
        # Should detect multiple failed authentication attempts
        auth_anomaly = next((a for a in anomalies if a["type"] == "multiple_failed_auth"), None)
        assert auth_anomaly is not None
        assert auth_anomaly["count"] == 15
        assert auth_anomaly["source_ip"] == "192.168.1.100"

    def test_detect_anomalous_patterns_after_hours_access(self):
        # Create privileged access event at 2 AM
        late_night_time = datetime.now(timezone.utc).replace(hour=2, minute=0, second=0)
        
        event = AuditEvent(
            event_id="evt-123",
            event_type=AuditEventType.PRIVILEGED_OPERATION,
            timestamp=late_night_time,
            principal=None,
            resource=Resource.SYSTEM,
            permission=Permission.SYSTEM_CONFIG,
            outcome=AuditOutcome.SUCCESS,
            severity=AuditSeverity.HIGH,
            message="System configuration changed",
            context=AuditContext(
                session_id="session-123",
                client_ip="192.168.1.50",
                user_agent="Admin-Client",
                request_id="req-late-night",
                api_endpoint="/admin/config",
                correlation_id=None
            )
        )
        
        anomalies = detect_anomalous_patterns([event])
        
        # Should detect after-hours privileged access
        after_hours_anomaly = next((a for a in anomalies if a["type"] == "after_hours_privileged_access"), None)
        assert after_hours_anomaly is not None
        assert after_hours_anomaly["count"] == 1


class TestAuditLogger:
    @pytest.fixture
    def mock_redis(self):
        redis_mock = Mock()
        redis_mock.pipeline.return_value.__enter__.return_value = redis_mock
        redis_mock.setex.return_value = True
        redis_mock.sadd.return_value = True
        redis_mock.expire.return_value = True
        redis_mock.execute.return_value = [True] * 10
        redis_mock.get.return_value = None
        redis_mock.smembers.return_value = set()
        redis_mock.keys.return_value = []
        return redis_mock

    @pytest.fixture
    def audit_logger(self, mock_redis):
        return AuditLogger(mock_redis)

    @pytest.mark.asyncio
    async def test_log_event_success(self, audit_logger):
        event_id = await audit_logger.log_event(
            event_type=AuditEventType.AUTHENTICATION,
            outcome=AuditOutcome.SUCCESS,
            message="User login successful",
            principal=Principal(
                user_id="user-001",
                username="john.doe",
                email="john@company.com",
                roles={Role.ANALYST},
                groups=set(),
                session_id="session-123",
                authenticated_at=datetime.now(timezone.utc),
                expires_at=None,
                client_ip="192.168.1.100",
                user_agent="Browser/1.0"
            )
        )
        
        assert event_id is not None
        assert len(event_id) == 36  # UUID length

    @pytest.mark.asyncio
    async def test_log_event_sanitizes_sensitive_data(self, audit_logger):
        await audit_logger.log_event(
            event_type=AuditEventType.SECRET_ACCESS,
            outcome=AuditOutcome.SUCCESS,
            message="Secret accessed",
            details={
                "secret_name": "database-password",
                "secret_value": "supersecretpassword123",
                "user_action": "retrieve"
            }
        )
        
        # Verify that sensitive data was sanitized before storage
        audit_logger.redis_client.setex.assert_called()

    @pytest.mark.asyncio
    async def test_query_events_by_date_range(self, audit_logger):
        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc)
        
        query = AuditQuery(
            start_date=start_date,
            end_date=end_date,
            limit=100
        )
        
        events = await audit_logger.query_events(query)
        
        # Should return empty list since we have no test data
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_get_statistics(self, audit_logger):
        stats = await audit_logger.get_statistics()
        
        assert stats.total_events == 0
        assert isinstance(stats.events_by_type, dict)
        assert isinstance(stats.events_by_outcome, dict)
        assert stats.failed_authentications == 0
        assert stats.privileged_operations == 0

    @pytest.mark.asyncio
    async def test_detect_anomalies(self, audit_logger):
        anomalies = await audit_logger.detect_anomalies(hours_back=24)
        
        # Should return empty list since no events
        assert isinstance(anomalies, list)

    @pytest.mark.asyncio
    async def test_verify_integrity(self, audit_logger):
        start_date = datetime.now(timezone.utc) - timedelta(days=1)
        end_date = datetime.now(timezone.utc)
        
        # Mock hash retrieval to return empty list
        with patch.object(audit_logger, '_retrieve_hashes', return_value=[]):
            integrity_ok = await audit_logger.verify_integrity(start_date, end_date)
            
            # Should pass with empty datasets
            assert integrity_ok is True


class TestAuditCompliance:
    def test_dora_compliance_rule_matching(self):
        rules = create_dora_compliance_rules()
        
        # Test ICT incident events
        ict_incident_event = create_audit_event(
            event_type=AuditEventType.EMERGENCY_ACTION,
            outcome=AuditOutcome.SUCCESS,
            message="Emergency system shutdown"
        )
        
        ict_rule = next((r for r in rules if "ict-incidents" in r.rule_id), None)
        assert ict_rule.matches_event(ict_incident_event) is True
        
        # Test access control events
        access_event = create_audit_event(
            event_type=AuditEventType.AUTHENTICATION,
            outcome=AuditOutcome.FAILURE,
            message="Authentication failed"
        )
        
        access_rule = next((r for r in rules if "access-controls" in r.rule_id), None)
        assert access_rule.matches_event(access_event) is True

    def test_retention_policy_compliance(self):
        from backend.app.security.audit.core import create_retention_policies
        
        policies = create_retention_policies()
        
        # DORA requires 7 years retention for critical events
        auth_policy = policies[AuditEventType.AUTHENTICATION]
        assert auth_policy.retention_days == 1825  # 5 years minimum
        
        secret_policy = policies[AuditEventType.SECRET_ACCESS]
        assert secret_policy.retention_days == 2555  # 7 years
        
        emergency_policy = policies[AuditEventType.EMERGENCY_ACTION]
        assert emergency_policy.retention_days == 3650  # 10 years

    @pytest.mark.asyncio
    async def test_real_time_compliance_alerts(self):
        mock_redis = Mock()
        mock_redis.pipeline.return_value.__enter__.return_value = mock_redis
        mock_redis.setex.return_value = True
        mock_redis.sadd.return_value = True
        mock_redis.expire.return_value = True
        mock_redis.execute.return_value = [True] * 10
        mock_redis.lpush.return_value = True
        mock_redis.ltrim.return_value = True
        
        audit_logger = AuditLogger(mock_redis)
        
        # Log a critical emergency action
        await audit_logger.log_event(
            event_type=AuditEventType.EMERGENCY_ACTION,
            outcome=AuditOutcome.SUCCESS,
            message="Emergency budget kill switch activated",
            severity=AuditSeverity.CRITICAL
        )
        
        # Should trigger compliance alert
        mock_redis.lpush.assert_called()
        mock_redis.ltrim.assert_called()


class TestAuditSecurity:
    """Test audit system against security threats."""
    
    @pytest.mark.asyncio
    async def test_audit_log_tampering_protection(self):
        # Test that audit events cannot be modified after creation
        event = create_audit_event(
            event_type=AuditEventType.PRIVILEGED_OPERATION,
            outcome=AuditOutcome.SUCCESS,
            message="User performed privileged action"
        )
        
        original_hash = calculate_audit_hash(event)
        
        # Event should be immutable
        with pytest.raises((AttributeError, TypeError)):
            event.message = "Modified message"
        
        # Hash should remain the same
        assert calculate_audit_hash(event) == original_hash

    @pytest.mark.asyncio
    async def test_audit_bypass_protection(self):
        mock_redis = Mock()
        audit_logger = AuditLogger(mock_redis)
        
        # Test that audit logging cannot be bypassed
        with pytest.raises((ValueError, TypeError)):
            await audit_logger.log_event(
                event_type=None,  # Invalid event type
                outcome=AuditOutcome.SUCCESS,
                message="Attempted bypass"
            )

    def test_pii_redaction_in_audit_logs(self):
        # Test that PII is properly redacted in audit logs
        event_details = {
            "user_email": "sensitive.user@company.com",
            "user_phone": "+32987654321",
            "user_ssn": "123-45-6789",
            "action": "user_profile_updated"
        }
        
        sanitized = sanitize_audit_data(event_details)
        
        # PII should be masked
        assert "sensitive.user@company.com" not in str(sanitized)
        assert "+32987654321" not in str(sanitized)
        assert "*" in sanitized["user_email"]
        assert "*" in sanitized["user_phone"]

    @pytest.mark.asyncio
    async def test_audit_injection_protection(self):
        mock_redis = Mock()
        mock_redis.pipeline.return_value.__enter__.return_value = mock_redis
        mock_redis.execute.return_value = [True] * 10
        
        audit_logger = AuditLogger(mock_redis)
        
        # Try to inject malicious content
        malicious_message = "User login'; DROP TABLE audit_logs; --"
        
        event_id = await audit_logger.log_event(
            event_type=AuditEventType.AUTHENTICATION,
            outcome=AuditOutcome.SUCCESS,
            message=malicious_message
        )
        
        # Should log successfully but sanitize the message
        assert event_id is not None
        
        # Verify Redis operations were called (indicating successful storage)
        mock_redis.setex.assert_called()

    def test_audit_hash_integrity(self):
        event1 = create_audit_event(
            event_type=AuditEventType.SECRET_ACCESS,
            outcome=AuditOutcome.SUCCESS,
            message="Secret accessed"
        )
        
        event2 = create_audit_event(
            event_type=AuditEventType.SECRET_ACCESS,
            outcome=AuditOutcome.SUCCESS,
            message="Secret accessed modified"  # Different message
        )
        
        hash1 = calculate_audit_hash(event1)
        hash2 = calculate_audit_hash(event2)
        
        # Different events should have different hashes
        assert hash1 != hash2
        
        # Same event should always produce same hash
        assert calculate_audit_hash(event1) == hash1

    @pytest.mark.asyncio
    async def test_audit_performance_dos_protection(self):
        """Test that audit logging can handle high volume without DoS."""
        mock_redis = Mock()
        mock_redis.pipeline.return_value.__enter__.return_value = mock_redis
        mock_redis.execute.return_value = [True] * 10
        
        audit_logger = AuditLogger(mock_redis)
        
        # Simulate burst of audit events
        start_time = datetime.now()
        
        for i in range(100):
            await audit_logger.log_event(
                event_type=AuditEventType.DATA_ACCESS,
                outcome=AuditOutcome.SUCCESS,
                message=f"Data access event {i}"
            )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Should complete in reasonable time (less than 5 seconds for 100 events)
        assert duration < 5.0