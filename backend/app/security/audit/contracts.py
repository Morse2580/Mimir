from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from ..auth.contracts import Principal, Resource, Permission


class AuditEventType(Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    SECRET_ACCESS = "secret_access"
    SECRET_ROTATION = "secret_rotation"
    WEBHOOK_VALIDATION = "webhook_validation"
    PRIVILEGED_OPERATION = "privileged_operation"
    DATA_ACCESS = "data_access"
    CONFIGURATION_CHANGE = "configuration_change"
    EMERGENCY_ACTION = "emergency_action"
    COMPLIANCE_EVENT = "compliance_event"


class AuditSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuditOutcome(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


@dataclass(frozen=True)
class AuditContext:
    session_id: Optional[str]
    client_ip: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    api_endpoint: Optional[str]
    correlation_id: Optional[str]
    additional_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    principal: Optional[Principal]
    resource: Optional[Resource]
    permission: Optional[Permission]
    outcome: AuditOutcome
    severity: AuditSeverity
    message: str
    context: AuditContext
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_privileged(self) -> bool:
        return (
            self.severity in {AuditSeverity.HIGH, AuditSeverity.CRITICAL} or
            self.event_type in {
                AuditEventType.SECRET_ROTATION,
                AuditEventType.PRIVILEGED_OPERATION,
                AuditEventType.CONFIGURATION_CHANGE,
                AuditEventType.EMERGENCY_ACTION
            }
        )
    
    @property
    def requires_investigation(self) -> bool:
        return (
            self.outcome in {AuditOutcome.FAILURE, AuditOutcome.ERROR} and
            self.severity in {AuditSeverity.HIGH, AuditSeverity.CRITICAL}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "principal": {
                "user_id": self.principal.user_id,
                "username": self.principal.username,
                "roles": [r.value for r in self.principal.roles]
            } if self.principal else None,
            "resource": self.resource.value if self.resource else None,
            "permission": self.permission.value if self.permission else None,
            "outcome": self.outcome.value,
            "severity": self.severity.value,
            "message": self.message,
            "context": {
                "session_id": self.context.session_id,
                "client_ip": self.context.client_ip,
                "user_agent": self.context.user_agent,
                "request_id": self.context.request_id,
                "api_endpoint": self.context.api_endpoint,
                "correlation_id": self.context.correlation_id,
                **self.context.additional_metadata
            },
            "details": self.details
        }


@dataclass(frozen=True)
class AuditQuery:
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    event_types: Optional[List[AuditEventType]] = None
    user_ids: Optional[List[str]] = None
    outcomes: Optional[List[AuditOutcome]] = None
    severities: Optional[List[AuditSeverity]] = None
    resources: Optional[List[Resource]] = None
    client_ips: Optional[List[str]] = None
    limit: int = 1000
    offset: int = 0


@dataclass(frozen=True)
class AuditStatistics:
    total_events: int
    events_by_type: Dict[str, int]
    events_by_outcome: Dict[str, int]
    events_by_severity: Dict[str, int]
    events_by_user: Dict[str, int]
    failed_authentications: int
    privileged_operations: int
    security_incidents: int
    time_range: tuple[datetime, datetime]


@dataclass(frozen=True)
class RetentionPolicy:
    retention_days: int
    archive_after_days: Optional[int]
    compress_after_days: Optional[int]
    purge_pii_after_days: Optional[int]
    
    @property
    def should_archive(self) -> bool:
        return self.archive_after_days is not None
    
    @property
    def should_compress(self) -> bool:
        return self.compress_after_days is not None


@dataclass(frozen=True)
class ComplianceRule:
    rule_id: str
    name: str
    description: str
    event_types: List[AuditEventType]
    required_fields: List[str]
    retention_days: int
    real_time_alerts: bool
    
    def matches_event(self, event: AuditEvent) -> bool:
        return event.event_type in self.event_types


class AuditError(Exception):
    pass


class AuditStorageError(AuditError):
    pass


class AuditQueryError(AuditError):
    pass


class RetentionPolicyViolationError(AuditError):
    pass