import pytest
from datetime import datetime, timezone, timedelta
from backend.app.security.auth.contracts import (
    Role, Permission, Resource, Principal, AuthorizationContext,
    AuthorizationResult, SessionConfig, AuthenticationError,
    AuthorizationError, InsufficientPrivilegesError
)
from backend.app.security.auth.core import (
    create_rbac_matrix, check_authorization, validate_session_timeout,
    is_privileged_operation, get_minimum_role_for_permission
)
from backend.app.security.auth.shell import AuthorizationService


class TestRBACMatrix:
    def test_create_rbac_matrix(self):
        matrix = create_rbac_matrix()
        
        # Test that all roles have some permissions
        assert len(matrix.get_role_permissions(Role.ANALYST)) > 0
        assert len(matrix.get_role_permissions(Role.LEGAL_REVIEWER)) > 0
        assert len(matrix.get_role_permissions(Role.ADMIN)) > 0
        assert len(matrix.get_role_permissions(Role.SYSTEM)) > 0

    def test_analyst_permissions(self):
        matrix = create_rbac_matrix()
        analyst_perms = matrix.get_role_permissions(Role.ANALYST)
        
        # Analysts can view and create incidents
        assert Permission.VIEW_INCIDENTS in analyst_perms
        assert Permission.CREATE_INCIDENTS in analyst_perms
        assert Permission.CLASSIFY_INCIDENTS in analyst_perms
        
        # But cannot delete incidents or manage users
        assert Permission.DELETE_INCIDENTS not in analyst_perms
        assert Permission.MANAGE_USERS not in analyst_perms

    def test_legal_reviewer_permissions(self):
        matrix = create_rbac_matrix()
        legal_perms = matrix.get_role_permissions(Role.LEGAL_REVIEWER)
        
        # Legal reviewers can approve/reject reviews
        assert Permission.APPROVE_REVIEWS in legal_perms
        assert Permission.REJECT_REVIEWS in legal_perms
        assert Permission.VERIFY_EVIDENCE in legal_perms
        
        # But cannot manage system configuration
        assert Permission.SYSTEM_CONFIG not in legal_perms
        assert Permission.MANAGE_SECRETS not in legal_perms

    def test_admin_permissions(self):
        matrix = create_rbac_matrix()
        admin_perms = matrix.get_role_permissions(Role.ADMIN)
        
        # Admins have all permissions
        assert Permission.MANAGE_USERS in admin_perms
        assert Permission.MANAGE_SECRETS in admin_perms
        assert Permission.SYSTEM_CONFIG in admin_perms
        assert Permission.EMERGENCY_STOP in admin_perms

    def test_system_permissions(self):
        matrix = create_rbac_matrix()
        system_perms = matrix.get_role_permissions(Role.SYSTEM)
        
        # System role has operational permissions
        assert Permission.CREATE_INCIDENTS in system_perms
        assert Permission.MANAGE_SOURCES in system_perms
        assert Permission.USE_PARALLEL_SEARCH in system_perms
        
        # But not user management
        assert Permission.MANAGE_USERS not in system_perms

    def test_permission_resource_mapping(self):
        matrix = create_rbac_matrix()
        
        # Test that permissions map to correct resources
        incident_resources = matrix.get_permission_resources(Permission.VIEW_INCIDENTS)
        assert Resource.INCIDENT in incident_resources
        
        user_resources = matrix.get_permission_resources(Permission.MANAGE_USERS)
        assert Resource.USER in user_resources
        
        secret_resources = matrix.get_permission_resources(Permission.MANAGE_SECRETS)
        assert Resource.SECRET in secret_resources


class TestAuthorizationCore:
    @pytest.fixture
    def analyst_principal(self):
        return Principal(
            user_id="analyst-001",
            username="analyst",
            email="analyst@company.com",
            roles={Role.ANALYST},
            groups={"analysts"},
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            client_ip="192.168.1.100",
            user_agent="Test-Agent/1.0"
        )

    @pytest.fixture
    def admin_principal(self):
        return Principal(
            user_id="admin-001",
            username="admin",
            email="admin@company.com", 
            roles={Role.ADMIN},
            groups={"admins"},
            session_id="admin-session-456",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
            client_ip="192.168.1.10",
            user_agent="Admin-Client/2.0"
        )

    def test_check_authorization_success(self, analyst_principal):
        matrix = create_rbac_matrix()
        context = AuthorizationContext(
            principal=analyst_principal,
            resource=Resource.INCIDENT,
            resource_id="inc-123",
            operation=Permission.VIEW_INCIDENTS,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        assert result.allowed is True
        assert result.principal == analyst_principal
        assert result.permission == Permission.VIEW_INCIDENTS

    def test_check_authorization_insufficient_role(self, analyst_principal):
        matrix = create_rbac_matrix()
        context = AuthorizationContext(
            principal=analyst_principal,
            resource=Resource.USER,
            resource_id="user-456",
            operation=Permission.MANAGE_USERS,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        assert result.allowed is False
        assert "do not have permission" in result.reason

    def test_check_authorization_expired_session(self, analyst_principal):
        matrix = create_rbac_matrix()
        
        # Create expired principal
        expired_principal = Principal(
            user_id=analyst_principal.user_id,
            username=analyst_principal.username,
            email=analyst_principal.email,
            roles=analyst_principal.roles,
            groups=analyst_principal.groups,
            session_id=analyst_principal.session_id,
            authenticated_at=analyst_principal.authenticated_at,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
            client_ip=analyst_principal.client_ip,
            user_agent=analyst_principal.user_agent
        )
        
        context = AuthorizationContext(
            principal=expired_principal,
            resource=Resource.INCIDENT,
            resource_id="inc-123",
            operation=Permission.VIEW_INCIDENTS,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        assert result.allowed is False
        assert "Session expired" in result.reason

    def test_check_authorization_wrong_resource(self, analyst_principal):
        matrix = create_rbac_matrix()
        context = AuthorizationContext(
            principal=analyst_principal,
            resource=Resource.SECRET,  # Wrong resource for this permission
            resource_id="secret-123",
            operation=Permission.VIEW_INCIDENTS,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        assert result.allowed is False
        assert "does not allow access to resource" in result.reason

    def test_privileged_operation_check(self, admin_principal):
        matrix = create_rbac_matrix()
        context = AuthorizationContext(
            principal=admin_principal,
            resource=Resource.SYSTEM,
            resource_id=None,
            operation=Permission.EMERGENCY_STOP,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        assert result.allowed is True

    def test_privileged_operation_denied(self, analyst_principal):
        matrix = create_rbac_matrix()
        context = AuthorizationContext(
            principal=analyst_principal,
            resource=Resource.SYSTEM,
            resource_id=None,
            operation=Permission.EMERGENCY_STOP,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        assert result.allowed is False


class TestSessionValidation:
    def test_validate_session_timeout_valid(self):
        config = SessionConfig(max_session_duration_minutes=60)
        principal = Principal(
            user_id="user-001",
            username="user",
            email="user@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc) - timedelta(minutes=30),  # 30 min ago
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        assert validate_session_timeout(principal, config) is True

    def test_validate_session_timeout_expired(self):
        config = SessionConfig(max_session_duration_minutes=60)
        principal = Principal(
            user_id="user-001",
            username="user",
            email="user@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc) - timedelta(minutes=90),  # 90 min ago
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),  # Expired
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        assert validate_session_timeout(principal, config) is False

    def test_validate_session_timeout_max_duration_exceeded(self):
        config = SessionConfig(max_session_duration_minutes=60)
        current_time = datetime.now(timezone.utc)
        
        principal = Principal(
            user_id="user-001",
            username="user", 
            email="user@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="session-123",
            authenticated_at=current_time - timedelta(minutes=90),  # 90 min ago
            expires_at=current_time + timedelta(minutes=30),  # Still valid expiry
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        assert validate_session_timeout(principal, config, current_time) is False


class TestAuthorizationService:
    @pytest.fixture
    def auth_service(self):
        return AuthorizationService()

    @pytest.fixture
    def legal_reviewer(self):
        return Principal(
            user_id="legal-001",
            username="legal_reviewer",
            email="legal@company.com",
            roles={Role.LEGAL_REVIEWER},
            groups={"legal"},
            session_id="legal-session",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            client_ip="192.168.1.50",
            user_agent="Legal-Client/1.0"
        )

    def test_authorize_success(self, auth_service, legal_reviewer):
        result = auth_service.authorize(
            legal_reviewer,
            Permission.APPROVE_REVIEWS,
            Resource.REVIEW,
            "review-123"
        )
        
        assert result.allowed is True

    def test_authorize_insufficient_privileges(self, auth_service, legal_reviewer):
        with pytest.raises(InsufficientPrivilegesError):
            auth_service.authorize(
                legal_reviewer,
                Permission.MANAGE_USERS,
                Resource.USER,
                "user-456"
            )

    def test_has_permission_true(self, auth_service, legal_reviewer):
        has_perm = auth_service.has_permission(
            legal_reviewer,
            Permission.VERIFY_EVIDENCE,
            Resource.EVIDENCE
        )
        
        assert has_perm is True

    def test_has_permission_false(self, auth_service, legal_reviewer):
        has_perm = auth_service.has_permission(
            legal_reviewer,
            Permission.SYSTEM_CONFIG,
            Resource.SYSTEM
        )
        
        assert has_perm is False

    def test_get_user_permissions(self, auth_service, legal_reviewer):
        permissions = auth_service.get_user_permissions(legal_reviewer)
        
        assert Permission.APPROVE_REVIEWS in permissions
        assert Permission.REJECT_REVIEWS in permissions
        assert Permission.VERIFY_EVIDENCE in permissions
        assert Permission.MANAGE_USERS not in permissions

    def test_validate_role_assignment_valid(self, auth_service):
        admin_principal = Principal(
            user_id="admin-001",
            username="admin",
            email="admin@company.com",
            roles={Role.ADMIN},
            groups=set(),
            session_id="admin-session",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
            client_ip="192.168.1.1",
            user_agent="Admin-Client"
        )
        
        # Admin can assign analyst role
        can_assign = auth_service.validate_role_assignment(
            admin_principal,
            {Role.ANALYST}
        )
        
        assert can_assign is True

    def test_validate_role_assignment_invalid(self, auth_service, legal_reviewer):
        # Legal reviewer cannot assign any roles
        can_assign = auth_service.validate_role_assignment(
            legal_reviewer,
            {Role.ANALYST}
        )
        
        assert can_assign is False


class TestPrivilegedOperations:
    def test_is_privileged_operation_true(self):
        privileged_ops = [
            Permission.DELETE_INCIDENTS,
            Permission.DELETE_EVIDENCE,
            Permission.MANAGE_USERS,
            Permission.MANAGE_SECRETS,
            Permission.SYSTEM_CONFIG,
            Permission.EMERGENCY_STOP
        ]
        
        for op in privileged_ops:
            assert is_privileged_operation(op) is True

    def test_is_privileged_operation_false(self):
        regular_ops = [
            Permission.VIEW_INCIDENTS,
            Permission.CREATE_INCIDENTS,
            Permission.VIEW_REVIEWS,
            Permission.USE_PARALLEL_SEARCH
        ]
        
        for op in regular_ops:
            assert is_privileged_operation(op) is False

    def test_get_minimum_role_for_permission(self):
        # Test that correct minimum roles are returned
        assert get_minimum_role_for_permission(Permission.VIEW_INCIDENTS) == Role.ANALYST
        assert get_minimum_role_for_permission(Permission.APPROVE_REVIEWS) == Role.LEGAL_REVIEWER
        assert get_minimum_role_for_permission(Permission.MANAGE_USERS) == Role.ADMIN
        assert get_minimum_role_for_permission(Permission.CREATE_INCIDENTS) == Role.ANALYST


class TestRBACSecurityTests:
    """Test RBAC system against common security vulnerabilities."""
    
    def test_privilege_escalation_protection(self):
        matrix = create_rbac_matrix()
        
        # Create analyst trying to access admin function
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
        
        context = AuthorizationContext(
            principal=analyst,
            resource=Resource.USER,
            resource_id="admin-user",
            operation=Permission.MANAGE_USERS,
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        # Should be denied - no privilege escalation
        assert result.allowed is False

    def test_session_fixation_protection(self):
        auth_service = AuthorizationService()
        
        # Test that expired sessions are rejected
        expired_principal = Principal(
            user_id="user-001",
            username="user",
            email="user@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="old-session",
            authenticated_at=datetime.now(timezone.utc) - timedelta(hours=10),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        with pytest.raises(AuthenticationError):
            auth_service.authorize(
                expired_principal,
                Permission.VIEW_INCIDENTS,
                Resource.INCIDENT
            )

    def test_cross_resource_access_protection(self):
        matrix = create_rbac_matrix()
        
        principal = Principal(
            user_id="user-001",
            username="user",
            email="user@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        # Try to use incident permission on user resource
        context = AuthorizationContext(
            principal=principal,
            resource=Resource.USER,  # Wrong resource
            resource_id="user-123",
            operation=Permission.VIEW_INCIDENTS,  # Incident permission
            request_metadata={}
        )
        
        result = check_authorization(matrix, context)
        
        assert result.allowed is False
        assert "does not allow access to resource" in result.reason

    def test_role_tampering_protection(self):
        """Test that roles cannot be modified after principal creation."""
        
        principal = Principal(
            user_id="user-001",
            username="user",
            email="user@company.com",
            roles={Role.ANALYST},
            groups=set(),
            session_id="session-123",
            authenticated_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=8),
            client_ip="192.168.1.1",
            user_agent="Test-Agent"
        )
        
        # Principal should be frozen/immutable
        with pytest.raises((AttributeError, TypeError)):
            principal.roles.add(Role.ADMIN)

    def test_authorization_bypass_protection(self):
        """Test that authorization cannot be bypassed with malformed input."""
        
        matrix = create_rbac_matrix()
        
        # Try with None principal
        context = AuthorizationContext(
            principal=None,
            resource=Resource.INCIDENT,
            resource_id="inc-123",
            operation=Permission.VIEW_INCIDENTS,
            request_metadata={}
        )
        
        with pytest.raises(AttributeError):
            check_authorization(matrix, context)