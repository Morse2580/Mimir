#!/usr/bin/env python3
"""
Security Test Validation Runner for Belgian RegOps Platform
Validates core security functionality without external dependencies
"""

import sys
import traceback
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

def test_vault_core_functions():
    """Test core vault functionality"""
    print("Testing Vault Core Functions...")
    try:
        from backend.app.security.vault.core import (
            calculate_rotation_status, generate_secret_name, is_cache_expired
        )
        from backend.app.security.vault.contracts import RotationStatus
        
        # Test rotation status calculation
        created_at = datetime.now(timezone.utc) - timedelta(days=85)
        status = calculate_rotation_status(created_at, 90, 7)
        assert status == RotationStatus.PENDING_ROTATION, f"Expected PENDING_ROTATION, got {status}"
        
        # Test secret name generation
        name = generate_secret_name("test-key", "api_key", "production")
        expected = "production-api_key-test-key"
        assert name == expected, f"Expected {expected}, got {name}"
        
        # Test cache expiry
        cached_at = datetime.now(timezone.utc) - timedelta(seconds=600)
        expired = is_cache_expired(cached_at, 300)
        assert expired is True, "Cache should be expired"
        
        print("✅ Vault Core Functions: PASSED")
        return True
    except Exception as e:
        print(f"❌ Vault Core Functions: FAILED - {str(e)}")
        traceback.print_exc()
        return False

def test_webhook_security():
    """Test webhook validation functionality"""
    print("Testing Webhook Security...")
    try:
        from backend.app.security.webhooks.core import (
            generate_hmac_signature, verify_hmac_signature, validate_timestamp
        )
        
        # Test HMAC signature generation and verification
        payload = b"test payload"
        secret = "test-secret-key"
        signature = generate_hmac_signature(payload, secret)
        
        # Verify correct signature
        valid = verify_hmac_signature(payload, signature, secret)
        assert valid is True, "Valid signature should verify"
        
        # Test invalid signature
        invalid = verify_hmac_signature(payload, "wrong-signature", secret)
        assert invalid is False, "Invalid signature should not verify"
        
        # Test timestamp validation
        current_time = datetime.now(timezone.utc)
        valid_timestamp = str(int(current_time.timestamp()))
        valid = validate_timestamp(valid_timestamp, 300, current_time)
        assert valid is True, "Valid timestamp should pass"
        
        # Test expired timestamp
        old_timestamp = str(int(current_time.timestamp()) - 400)
        expired = validate_timestamp(old_timestamp, 300, current_time)
        assert expired is False, "Expired timestamp should fail"
        
        print("✅ Webhook Security: PASSED")
        return True
    except Exception as e:
        print(f"❌ Webhook Security: FAILED - {str(e)}")
        traceback.print_exc()
        return False

def test_rbac_core():
    """Test RBAC matrix and authorization"""
    print("Testing RBAC Core...")
    try:
        from backend.app.security.auth.core import (
            create_rbac_matrix, is_privileged_operation
        )
        from backend.app.security.auth.contracts import (
            Role, Permission, Resource
        )
        
        # Test RBAC matrix creation
        matrix = create_rbac_matrix()
        
        # Test that analysts can view incidents
        analyst_perms = matrix.get_role_permissions(Role.ANALYST)
        assert Permission.VIEW_INCIDENTS in analyst_perms, "Analysts should be able to view incidents"
        
        # Test that analysts cannot manage users
        assert Permission.MANAGE_USERS not in analyst_perms, "Analysts should not manage users"
        
        # Test privileged operation detection
        assert is_privileged_operation(Permission.MANAGE_SECRETS) is True, "Secret management should be privileged"
        assert is_privileged_operation(Permission.VIEW_INCIDENTS) is False, "Viewing incidents should not be privileged"
        
        print("✅ RBAC Core: PASSED")
        return True
    except Exception as e:
        print(f"❌ RBAC Core: FAILED - {str(e)}")
        traceback.print_exc()
        return False

def test_audit_core():
    """Test audit logging functionality"""
    print("Testing Audit Core...")
    try:
        from backend.app.security.audit.core import (
            create_audit_event, sanitize_audit_data, create_dora_compliance_rules
        )
        from backend.app.security.audit.contracts import (
            AuditEventType, AuditOutcome, AuditSeverity
        )
        
        # Test audit event creation
        event = create_audit_event(
            AuditEventType.AUTHENTICATION,
            AuditOutcome.SUCCESS,
            "Test login"
        )
        assert event.event_type == AuditEventType.AUTHENTICATION
        assert event.outcome == AuditOutcome.SUCCESS
        assert event.message == "Test login"
        assert event.event_id is not None
        
        # Test PII sanitization
        data = {
            "username": "john.doe",
            "password": "secret123",
            "email": "john@company.com"
        }
        sanitized = sanitize_audit_data(data)
        assert sanitized["username"] == "john.doe"  # Not sensitive
        assert sanitized["password"] == "***REDACTED***"  # Sensitive
        assert "*" in sanitized["email"]  # PII masked
        
        # Test DORA compliance rules
        rules = create_dora_compliance_rules()
        assert len(rules) >= 3, "Should have at least 3 DORA compliance rules"
        
        print("✅ Audit Core: PASSED")
        return True
    except Exception as e:
        print(f"❌ Audit Core: FAILED - {str(e)}")
        traceback.print_exc()
        return False

def test_rotation_core():
    """Test secret rotation functionality"""
    print("Testing Secret Rotation Core...")
    try:
        from backend.app.security.rotation.core import (
            generate_secret_value, validate_secret_strength, 
            create_default_rotation_policies
        )
        from backend.app.security.vault.contracts import SecretType
        
        # Test secret generation
        api_key = generate_secret_value(SecretType.API_KEY, 32)
        assert len(api_key) == 32, f"API key should be 32 chars, got {len(api_key)}"
        assert api_key.isalnum(), "API key should be alphanumeric"
        
        # Test secret strength validation
        strong_secret = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
        assert validate_secret_strength(strong_secret, SecretType.API_KEY) is True
        
        weak_secret = "abc"
        assert validate_secret_strength(weak_secret, SecretType.API_KEY) is False
        
        # Test rotation policies
        policies = create_default_rotation_policies()
        assert SecretType.API_KEY in policies
        assert policies[SecretType.API_KEY].rotation_interval_days == 90
        
        print("✅ Secret Rotation Core: PASSED")
        return True
    except Exception as e:
        print(f"❌ Secret Rotation Core: FAILED - {str(e)}")
        traceback.print_exc()
        return False

def test_config_core():
    """Test configuration management"""
    print("Testing Config Core...")
    try:
        from backend.app.security.config.core import (
            create_config_schema, validate_config_value, 
            get_required_secrets, mask_sensitive_config
        )
        
        # Test schema creation
        schema = create_config_schema()
        assert "DATABASE_PASSWORD" in schema
        assert "PARALLEL_API_KEY" in schema
        
        # Test config validation
        db_schema = schema["DATABASE_PASSWORD"]
        assert validate_config_value(db_schema, "strongpassword123") is True
        assert validate_config_value(db_schema, "weak") is False  # Too short
        
        # Test required secrets identification
        required = get_required_secrets()
        assert "DATABASE_PASSWORD" in required
        assert "JWT_SECRET_KEY" in required
        
        # Test sensitive data masking
        config = {
            "DATABASE_PASSWORD": "supersecretpassword",
            "LOG_LEVEL": "INFO"
        }
        masked = mask_sensitive_config(config)
        assert "***" in masked["DATABASE_PASSWORD"]
        assert masked["LOG_LEVEL"] == "INFO"  # Non-sensitive unchanged
        
        print("✅ Config Core: PASSED")
        return True
    except Exception as e:
        print(f"❌ Config Core: FAILED - {str(e)}")
        traceback.print_exc()
        return False

def test_fail_closed_behavior():
    """Test fail-closed security behavior"""
    print("Testing Fail-Closed Behavior...")
    try:
        from backend.app.security.auth.core import check_authorization, create_rbac_matrix
        from backend.app.security.auth.contracts import (
            Principal, AuthorizationContext, Role, Permission, Resource
        )
        
        matrix = create_rbac_matrix()
        
        # Test expired session fails closed
        expired_principal = Principal(
            user_id="user-001",
            username="user",
            email="user@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc) - timedelta(hours=10),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        context = AuthorizationContext(
            principal=expired_principal,
            resource=Resource.INCIDENT,
            resource_id="inc-123",
            operation=Permission.VIEW_INCIDENTS,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        assert result.allowed is False, "Expired session should be denied"
        assert "expired" in result.reason.lower(), "Should indicate session expiry"
        
        # Test insufficient privileges fails closed
        analyst = Principal(
            user_id="analyst-001",
            username="analyst",
            email="analyst@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        admin_context = AuthorizationContext(
            principal=analyst,
            resource=Resource.USER,
            resource_id="admin-user",
            operation=Permission.MANAGE_USERS,  # Admin permission
            request_metadata={}
        )
        
        result = check_authorization(matrix, admin_context)
        assert result.allowed is False, "Insufficient privileges should be denied"
        
        print("✅ Fail-Closed Behavior: PASSED")
        return True
    except Exception as e:
        print(f"❌ Fail-Closed Behavior: FAILED - {str(e)}")
        traceback.print_exc()
        return False

def main():
    """Run all security validation tests"""
    print("🔒 Belgian RegOps Platform - Security Test Validation")
    print("=" * 60)
    print(f"Test run started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Add current directory to Python path
    sys.path.insert(0, '/Users/arinti-work/Documents/projs/regops-worktrees/security-hardening')
    
    test_functions = [
        test_vault_core_functions,
        test_webhook_security,
        test_rbac_core,
        test_audit_core,
        test_rotation_core,
        test_config_core,
        test_fail_closed_behavior
    ]
    
    results = []
    for test_func in test_functions:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ {test_func.__name__}: CRITICAL FAILURE - {str(e)}")
            results.append(False)
        print()
    
    print("=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    for i, (test_func, result) in enumerate(zip(test_functions, results), 1):
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{i:2d}. {test_func.__name__.replace('test_', '').replace('_', ' ').title()}: {status}")
    
    print()
    print(f"Overall Result: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL SECURITY TESTS PASSED - Production Ready!")
        return 0
    else:
        print("⚠️  SOME TESTS FAILED - Review failures before deployment")
        return 1

if __name__ == "__main__":
    sys.exit(main())