import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from .contracts import (
    Role, Permission, Resource, Principal, AuthorizationContext,
    AuthorizationResult, SessionConfig, AuthenticationError,
    AuthorizationError, SessionExpiredError, InsufficientPrivilegesError
)
from .core import (
    create_rbac_matrix, check_authorization, validate_session_timeout,
    create_session_config
)


logger = logging.getLogger(__name__)
security = HTTPBearer()


class AuthorizationService:
    def __init__(self, session_config: Optional[SessionConfig] = None):
        self.rbac_matrix = create_rbac_matrix()
        self.session_config = session_config or create_session_config()
        
    def authorize(
        self,
        principal: Principal,
        permission: Permission,
        resource: Resource,
        resource_id: Optional[str] = None,
        request_metadata: Optional[Dict[str, Any]] = None
    ) -> AuthorizationResult:
        if not validate_session_timeout(principal, self.session_config):
            raise SessionExpiredError("Session has expired")
        
        context = AuthorizationContext(
            principal=principal,
            resource=resource,
            resource_id=resource_id,
            operation=permission,
            request_metadata=request_metadata or {}
        )
        
        result = check_authorization(self.rbac_matrix, context)
        
        if not result.allowed:
            logger.warning(
                f"Authorization denied for user {principal.user_id}",
                extra={
                    "user_id": principal.user_id,
                    "permission": permission.value,
                    "resource": resource.value,
                    "reason": result.reason,
                    "roles": [r.value for r in principal.roles]
                }
            )
            
            if "insufficient" in result.reason.lower():
                raise InsufficientPrivilegesError(result.reason, principal, permission)
            else:
                raise AuthorizationError(result.reason, principal, permission)
        
        logger.info(
            f"Authorization granted for user {principal.user_id}",
            extra={
                "user_id": principal.user_id,
                "permission": permission.value,
                "resource": resource.value,
                "roles": [r.value for r in principal.roles]
            }
        )
        
        return result
    
    def has_permission(
        self,
        principal: Principal,
        permission: Permission,
        resource: Resource
    ) -> bool:
        try:
            result = self.authorize(principal, permission, resource)
            return result.allowed
        except (AuthenticationError, AuthorizationError):
            return False
    
    def get_user_permissions(self, principal: Principal) -> Set[Permission]:
        all_permissions = set()
        
        for role in principal.roles:
            role_permissions = self.rbac_matrix.get_role_permissions(role)
            all_permissions.update(role_permissions)
        
        return all_permissions
    
    def validate_role_assignment(
        self,
        current_principal: Principal,
        target_roles: Set[Role]
    ) -> bool:
        if Role.ADMIN not in current_principal.roles:
            return False
        
        protected_roles = {Role.ADMIN, Role.SYSTEM}
        
        if target_roles & protected_roles and Role.SYSTEM not in current_principal.roles:
            return False
        
        return True


class JWTAuthService:
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        issuer: str = "mimir-regops"
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.issuer = issuer
    
    def decode_token(self, token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                issuer=self.issuer
            )
            return payload
            
        except jwt.ExpiredSignatureError:
            raise SessionExpiredError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationError(f"Invalid token: {str(e)}")
    
    def create_principal_from_token(self, token_payload: Dict[str, Any]) -> Principal:
        user_id = token_payload.get("sub")
        if not user_id:
            raise AuthenticationError("Token missing user ID")
        
        username = token_payload.get("preferred_username", user_id)
        email = token_payload.get("email", f"{user_id}@unknown.com")
        
        role_claims = token_payload.get("roles", [])
        groups = set(token_payload.get("groups", []))
        
        roles = set()
        for role_str in role_claims:
            try:
                role = Role(role_str.lower())
                roles.add(role)
            except ValueError:
                logger.warning(f"Unknown role in token: {role_str}")
        
        if not roles:
            roles.add(Role.ANALYST)  # Default role
        
        authenticated_at = datetime.fromtimestamp(
            token_payload.get("iat", 0),
            timezone.utc
        )
        
        expires_at = None
        if "exp" in token_payload:
            expires_at = datetime.fromtimestamp(
                token_payload["exp"],
                timezone.utc
            )
        
        return Principal(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles,
            groups=groups,
            session_id=token_payload.get("jti"),
            authenticated_at=authenticated_at,
            expires_at=expires_at,
            client_ip=None,  # Set by middleware
            user_agent=None  # Set by middleware
        )


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    jwt_service: JWTAuthService = Depends()
) -> Principal:
    try:
        token_payload = jwt_service.decode_token(credentials.credentials)
        principal = jwt_service.create_principal_from_token(token_payload)
        
        client_ip = (
            request.headers.get("X-Forwarded-For") or
            request.headers.get("X-Real-IP") or
            request.client.host
        )
        
        user_agent = request.headers.get("User-Agent")
        
        updated_principal = Principal(
            user_id=principal.user_id,
            username=principal.username,
            email=principal.email,
            roles=principal.roles,
            groups=principal.groups,
            session_id=principal.session_id,
            authenticated_at=principal.authenticated_at,
            expires_at=principal.expires_at,
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        return updated_principal
        
    except (AuthenticationError, AuthorizationError) as e:
        logger.warning(f"Authentication failed: {str(e)}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected authentication error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")


def require_permission(
    permission: Permission,
    resource: Resource,
    resource_id: Optional[str] = None
):
    def permission_check(
        principal: Principal = Depends(get_current_principal),
        auth_service: AuthorizationService = Depends()
    ):
        try:
            auth_service.authorize(
                principal=principal,
                permission=permission,
                resource=resource,
                resource_id=resource_id
            )
            return principal
            
        except AuthorizationError as e:
            logger.warning(f"Authorization failed: {str(e)}")
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected authorization error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Authorization check failed")
    
    return permission_check


def require_role(required_roles: Set[Role]):
    def role_check(
        principal: Principal = Depends(get_current_principal)
    ):
        if not principal.has_any_role(required_roles):
            required_role_names = [r.value for r in required_roles]
            user_role_names = [r.value for r in principal.roles]
            
            logger.warning(
                f"Role check failed for user {principal.user_id}",
                extra={
                    "user_id": principal.user_id,
                    "required_roles": required_role_names,
                    "user_roles": user_role_names
                }
            )
            
            raise HTTPException(
                status_code=403,
                detail=f"Required roles: {required_role_names}, user has: {user_role_names}"
            )
        
        return principal
    
    return role_check


class SecurityMiddleware:
    def __init__(self, auth_service: AuthorizationService):
        self.auth_service = auth_service
    
    async def log_security_event(
        self,
        event_type: str,
        principal: Optional[Principal],
        resource: Optional[Resource],
        details: Dict[str, Any]
    ):
        log_data = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": principal.user_id if principal else None,
            "resource": resource.value if resource else None,
            **details
        }
        
        logger.info(f"Security event: {event_type}", extra=log_data)