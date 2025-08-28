from datetime import datetime, timezone, timedelta
from typing import Set, Dict, Optional
from .contracts import (
    Role, Permission, Resource, RBACMatrix, Principal,
    AuthorizationContext, AuthorizationResult, SessionConfig
)


def create_rbac_matrix() -> RBACMatrix:
    role_permissions = {
        Role.ANALYST: {
            Permission.VIEW_INCIDENTS,
            Permission.CREATE_INCIDENTS,
            Permission.UPDATE_INCIDENTS,
            Permission.CLASSIFY_INCIDENTS,
            Permission.VIEW_REVIEWS,
            Permission.CREATE_REVIEWS,
            Permission.VIEW_EVIDENCE,
            Permission.CREATE_EVIDENCE,
            Permission.VIEW_SOURCES,
            Permission.USE_PARALLEL_SEARCH,
            Permission.USE_PARALLEL_TASK,
            Permission.VIEW_COSTS
        },
        
        Role.LEGAL_REVIEWER: {
            Permission.VIEW_INCIDENTS,
            Permission.VIEW_REVIEWS,
            Permission.CREATE_REVIEWS,
            Permission.APPROVE_REVIEWS,
            Permission.REJECT_REVIEWS,
            Permission.VIEW_EVIDENCE,
            Permission.CREATE_EVIDENCE,
            Permission.VERIFY_EVIDENCE,
            Permission.VIEW_SOURCES,
            Permission.USE_PARALLEL_SEARCH,
            Permission.VIEW_COSTS
        },
        
        Role.ADMIN: {
            Permission.VIEW_INCIDENTS,
            Permission.CREATE_INCIDENTS,
            Permission.UPDATE_INCIDENTS,
            Permission.DELETE_INCIDENTS,
            Permission.CLASSIFY_INCIDENTS,
            Permission.VIEW_REVIEWS,
            Permission.CREATE_REVIEWS,
            Permission.APPROVE_REVIEWS,
            Permission.REJECT_REVIEWS,
            Permission.VIEW_EVIDENCE,
            Permission.CREATE_EVIDENCE,
            Permission.VERIFY_EVIDENCE,
            Permission.DELETE_EVIDENCE,
            Permission.VIEW_SOURCES,
            Permission.MANAGE_SOURCES,
            Permission.TRIGGER_SNAPSHOTS,
            Permission.MANAGE_USERS,
            Permission.MANAGE_ROLES,
            Permission.VIEW_AUDIT_LOGS,
            Permission.MANAGE_SECRETS,
            Permission.SYSTEM_CONFIG,
            Permission.VIEW_COSTS,
            Permission.SET_BUDGETS,
            Permission.EMERGENCY_STOP,
            Permission.USE_PARALLEL_SEARCH,
            Permission.USE_PARALLEL_TASK,
            Permission.MANAGE_PARALLEL_CONFIG
        },
        
        Role.SYSTEM: {
            Permission.VIEW_INCIDENTS,
            Permission.CREATE_INCIDENTS,
            Permission.UPDATE_INCIDENTS,
            Permission.CLASSIFY_INCIDENTS,
            Permission.VIEW_REVIEWS,
            Permission.CREATE_REVIEWS,
            Permission.VIEW_EVIDENCE,
            Permission.CREATE_EVIDENCE,
            Permission.VERIFY_EVIDENCE,
            Permission.VIEW_SOURCES,
            Permission.MANAGE_SOURCES,
            Permission.TRIGGER_SNAPSHOTS,
            Permission.MANAGE_SECRETS,
            Permission.VIEW_COSTS,
            Permission.USE_PARALLEL_SEARCH,
            Permission.USE_PARALLEL_TASK
        }
    }
    
    permission_resources = {
        Permission.VIEW_INCIDENTS: {Resource.INCIDENT},
        Permission.CREATE_INCIDENTS: {Resource.INCIDENT},
        Permission.UPDATE_INCIDENTS: {Resource.INCIDENT},
        Permission.DELETE_INCIDENTS: {Resource.INCIDENT},
        Permission.CLASSIFY_INCIDENTS: {Resource.INCIDENT},
        
        Permission.VIEW_REVIEWS: {Resource.REVIEW},
        Permission.CREATE_REVIEWS: {Resource.REVIEW},
        Permission.APPROVE_REVIEWS: {Resource.REVIEW},
        Permission.REJECT_REVIEWS: {Resource.REVIEW},
        
        Permission.VIEW_EVIDENCE: {Resource.EVIDENCE},
        Permission.CREATE_EVIDENCE: {Resource.EVIDENCE},
        Permission.VERIFY_EVIDENCE: {Resource.EVIDENCE},
        Permission.DELETE_EVIDENCE: {Resource.EVIDENCE},
        
        Permission.VIEW_SOURCES: {Resource.SOURCE},
        Permission.MANAGE_SOURCES: {Resource.SOURCE},
        Permission.TRIGGER_SNAPSHOTS: {Resource.SOURCE},
        
        Permission.MANAGE_USERS: {Resource.USER},
        Permission.MANAGE_ROLES: {Resource.USER},
        Permission.VIEW_AUDIT_LOGS: {Resource.AUDIT_LOG},
        Permission.MANAGE_SECRETS: {Resource.SECRET},
        Permission.SYSTEM_CONFIG: {Resource.SYSTEM},
        
        Permission.VIEW_COSTS: {Resource.COST},
        Permission.SET_BUDGETS: {Resource.COST},
        Permission.EMERGENCY_STOP: {Resource.COST, Resource.SYSTEM},
        
        Permission.USE_PARALLEL_SEARCH: {Resource.PARALLEL},
        Permission.USE_PARALLEL_TASK: {Resource.PARALLEL},
        Permission.MANAGE_PARALLEL_CONFIG: {Resource.PARALLEL, Resource.SYSTEM}
    }
    
    return RBACMatrix(role_permissions, permission_resources)


def check_authorization(
    matrix: RBACMatrix,
    context: AuthorizationContext
) -> AuthorizationResult:
    principal = context.principal
    permission = context.operation
    resource = context.resource
    evaluated_at = datetime.now(timezone.utc)
    
    if principal.is_expired:
        return AuthorizationResult(
            allowed=False,
            principal=principal,
            permission=permission,
            resource=resource,
            reason="Session expired",
            evaluated_at=evaluated_at
        )
    
    allowed_roles = {role for role in Role if matrix.has_permission(role, permission)}
    user_roles = principal.roles
    
    if not (user_roles & allowed_roles):
        return AuthorizationResult(
            allowed=False,
            principal=principal,
            permission=permission,
            resource=resource,
            reason=f"User roles {[r.value for r in user_roles]} do not have permission {permission.value}",
            evaluated_at=evaluated_at
        )
    
    user_role = next(iter(user_roles & allowed_roles))
    
    if not matrix.can_access_resource(user_role, permission, resource):
        return AuthorizationResult(
            allowed=False,
            principal=principal,
            permission=permission,
            resource=resource,
            reason=f"Permission {permission.value} does not allow access to resource {resource.value}",
            evaluated_at=evaluated_at
        )
    
    if _requires_additional_checks(permission, context):
        additional_result = _perform_additional_checks(permission, context)
        if not additional_result.allowed:
            return additional_result
    
    return AuthorizationResult(
        allowed=True,
        principal=principal,
        permission=permission,
        resource=resource,
        reason="Authorization granted",
        evaluated_at=evaluated_at
    )


def create_session_config(environment: str = "production") -> SessionConfig:
    if environment == "development":
        return SessionConfig(
            max_session_duration_minutes=60,
            max_idle_duration_minutes=30,
            require_mfa_for_privileged=False,
            enforce_ip_restrictions=False
        )
    
    return SessionConfig(
        max_session_duration_minutes=480,
        max_idle_duration_minutes=60,
        require_mfa_for_privileged=True,
        enforce_ip_restrictions=True,
        allowed_ip_ranges=["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
    )


def validate_session_timeout(
    principal: Principal,
    config: SessionConfig,
    current_time: Optional[datetime] = None
) -> bool:
    now = current_time or datetime.now(timezone.utc)
    
    if principal.expires_at and now > principal.expires_at:
        return False
    
    max_session_age = timedelta(minutes=config.max_session_duration_minutes)
    if now - principal.authenticated_at > max_session_age:
        return False
    
    return True


def calculate_session_expiry(
    config: SessionConfig,
    authenticated_at: Optional[datetime] = None
) -> datetime:
    start_time = authenticated_at or datetime.now(timezone.utc)
    return start_time + timedelta(minutes=config.max_session_duration_minutes)


def is_privileged_operation(permission: Permission) -> bool:
    privileged_permissions = {
        Permission.DELETE_INCIDENTS,
        Permission.DELETE_EVIDENCE,
        Permission.MANAGE_USERS,
        Permission.MANAGE_ROLES,
        Permission.MANAGE_SECRETS,
        Permission.SYSTEM_CONFIG,
        Permission.SET_BUDGETS,
        Permission.EMERGENCY_STOP,
        Permission.MANAGE_PARALLEL_CONFIG
    }
    
    return permission in privileged_permissions


def get_minimum_role_for_permission(permission: Permission) -> Optional[Role]:
    role_hierarchy = [Role.ANALYST, Role.LEGAL_REVIEWER, Role.ADMIN, Role.SYSTEM]
    
    matrix = create_rbac_matrix()
    
    for role in role_hierarchy:
        if matrix.has_permission(role, permission):
            return role
    
    return None


def validate_role_elevation(
    current_roles: Set[Role],
    target_roles: Set[Role]
) -> bool:
    role_levels = {
        Role.ANALYST: 1,
        Role.LEGAL_REVIEWER: 2,
        Role.ADMIN: 3,
        Role.SYSTEM: 4
    }
    
    current_max = max(role_levels.get(role, 0) for role in current_roles)
    target_max = max(role_levels.get(role, 0) for role in target_roles)
    
    return target_max <= current_max


def _requires_additional_checks(
    permission: Permission,
    context: AuthorizationContext
) -> bool:
    return (
        is_privileged_operation(permission) or
        context.is_self_access or
        permission in {Permission.MANAGE_SECRETS, Permission.EMERGENCY_STOP}
    )


def _perform_additional_checks(
    permission: Permission,
    context: AuthorizationContext
) -> AuthorizationResult:
    principal = context.principal
    evaluated_at = datetime.now(timezone.utc)
    
    if is_privileged_operation(permission) and not principal.is_privileged:
        return AuthorizationResult(
            allowed=False,
            principal=principal,
            permission=permission,
            resource=context.resource,
            reason="Privileged operation requires privileged role",
            evaluated_at=evaluated_at
        )
    
    if permission == Permission.MANAGE_SECRETS and Role.SYSTEM not in principal.roles:
        if Role.ADMIN not in principal.roles:
            return AuthorizationResult(
                allowed=False,
                principal=principal,
                permission=permission,
                resource=context.resource,
                reason="Secret management requires ADMIN or SYSTEM role",
                evaluated_at=evaluated_at
            )
    
    if permission == Permission.EMERGENCY_STOP:
        if not (Role.ADMIN in principal.roles or Role.SYSTEM in principal.roles):
            return AuthorizationResult(
                allowed=False,
                principal=principal,
                permission=permission,
                resource=context.resource,
                reason="Emergency stop requires ADMIN or SYSTEM role",
                evaluated_at=evaluated_at
            )
    
    return AuthorizationResult(
        allowed=True,
        principal=principal,
        permission=permission,
        resource=context.resource,
        reason="Additional checks passed",
        evaluated_at=evaluated_at
    )