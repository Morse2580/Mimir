from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Set, Dict, Any, Optional, List


class Role(Enum):
    ANALYST = "analyst"
    LEGAL_REVIEWER = "legal_reviewer"
    ADMIN = "admin"
    SYSTEM = "system"


class Permission(Enum):
    # Incident Management
    VIEW_INCIDENTS = "view_incidents"
    CREATE_INCIDENTS = "create_incidents"
    UPDATE_INCIDENTS = "update_incidents"
    DELETE_INCIDENTS = "delete_incidents"
    CLASSIFY_INCIDENTS = "classify_incidents"
    
    # Compliance Reviews
    VIEW_REVIEWS = "view_reviews"
    CREATE_REVIEWS = "create_reviews"
    APPROVE_REVIEWS = "approve_reviews"
    REJECT_REVIEWS = "reject_reviews"
    
    # Evidence Management
    VIEW_EVIDENCE = "view_evidence"
    CREATE_EVIDENCE = "create_evidence"
    VERIFY_EVIDENCE = "verify_evidence"
    DELETE_EVIDENCE = "delete_evidence"
    
    # Regulatory Monitoring
    VIEW_SOURCES = "view_sources"
    MANAGE_SOURCES = "manage_sources"
    TRIGGER_SNAPSHOTS = "trigger_snapshots"
    
    # System Administration
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_SECRETS = "manage_secrets"
    SYSTEM_CONFIG = "system_config"
    
    # Cost Management
    VIEW_COSTS = "view_costs"
    SET_BUDGETS = "set_budgets"
    EMERGENCY_STOP = "emergency_stop"
    
    # Parallel.ai Integration
    USE_PARALLEL_SEARCH = "use_parallel_search"
    USE_PARALLEL_TASK = "use_parallel_task"
    MANAGE_PARALLEL_CONFIG = "manage_parallel_config"


class Resource(Enum):
    INCIDENT = "incident"
    REVIEW = "review"
    EVIDENCE = "evidence"
    SOURCE = "source"
    USER = "user"
    AUDIT_LOG = "audit_log"
    SECRET = "secret"
    SYSTEM = "system"
    COST = "cost"
    PARALLEL = "parallel"


@dataclass(frozen=True)
class RBACMatrix:
    role_permissions: Dict[Role, Set[Permission]]
    permission_resources: Dict[Permission, Set[Resource]]
    
    def get_role_permissions(self, role: Role) -> Set[Permission]:
        return self.role_permissions.get(role, set())
    
    def get_permission_resources(self, permission: Permission) -> Set[Resource]:
        return self.permission_resources.get(permission, set())
    
    def has_permission(self, role: Role, permission: Permission) -> bool:
        return permission in self.get_role_permissions(role)
    
    def can_access_resource(
        self,
        role: Role,
        permission: Permission,
        resource: Resource
    ) -> bool:
        if not self.has_permission(role, permission):
            return False
        
        allowed_resources = self.get_permission_resources(permission)
        return resource in allowed_resources


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    email: str
    roles: Set[Role]
    groups: Set[str]
    session_id: Optional[str]
    authenticated_at: datetime
    expires_at: Optional[datetime]
    client_ip: Optional[str]
    user_agent: Optional[str]
    
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        now = datetime.now(timezone.utc)
        return now > self.expires_at
    
    @property
    def is_privileged(self) -> bool:
        privileged_roles = {Role.ADMIN, Role.SYSTEM}
        return bool(self.roles & privileged_roles)
    
    def has_role(self, role: Role) -> bool:
        return role in self.roles
    
    def has_any_role(self, roles: Set[Role]) -> bool:
        return bool(self.roles & roles)


@dataclass(frozen=True)
class AuthorizationContext:
    principal: Principal
    resource: Resource
    resource_id: Optional[str]
    operation: Permission
    request_metadata: Dict[str, Any]
    
    @property
    def is_self_access(self) -> bool:
        if self.resource != Resource.USER:
            return False
        return self.resource_id == self.principal.user_id


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    principal: Principal
    permission: Permission
    resource: Resource
    reason: str
    evaluated_at: datetime
    
    @property
    def denied(self) -> bool:
        return not self.allowed


@dataclass(frozen=True)
class SessionConfig:
    max_session_duration_minutes: int = 480  # 8 hours
    max_idle_duration_minutes: int = 60      # 1 hour
    require_mfa_for_privileged: bool = True
    enforce_ip_restrictions: bool = True
    allowed_ip_ranges: List[str] = None


class AuthenticationError(Exception):
    pass


class AuthorizationError(Exception):
    def __init__(self, message: str, principal: Principal, permission: Permission):
        self.principal = principal
        self.permission = permission
        super().__init__(message)


class SessionExpiredError(AuthenticationError):
    pass


class InsufficientPrivilegesError(AuthorizationError):
    pass


class ResourceAccessDeniedError(AuthorizationError):
    pass