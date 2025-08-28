import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any
from .contracts import (
    AuditEvent, AuditEventType, AuditSeverity, AuditOutcome, AuditContext,
    AuditQuery, AuditStatistics, RetentionPolicy, ComplianceRule
)
from ..auth.contracts import Principal, Resource, Permission


def create_audit_event(
    event_type: AuditEventType,
    outcome: AuditOutcome,
    message: str,
    principal: Optional[Principal] = None,
    resource: Optional[Resource] = None,
    permission: Optional[Permission] = None,
    context: Optional[AuditContext] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: Optional[AuditSeverity] = None
) -> AuditEvent:
    event_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    
    if severity is None:
        severity = determine_severity(event_type, outcome, principal)
    
    if context is None:
        context = AuditContext(
            session_id=None,
            client_ip=None,
            user_agent=None,
            request_id=None,
            api_endpoint=None,
            correlation_id=None
        )
    
    return AuditEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        principal=principal,
        resource=resource,
        permission=permission,
        outcome=outcome,
        severity=severity,
        message=message,
        context=context,
        details=details or {}
    )


def determine_severity(
    event_type: AuditEventType,
    outcome: AuditOutcome,
    principal: Optional[Principal] = None
) -> AuditSeverity:
    base_severities = {
        AuditEventType.AUTHENTICATION: AuditSeverity.MEDIUM,
        AuditEventType.AUTHORIZATION: AuditSeverity.LOW,
        AuditEventType.SECRET_ACCESS: AuditSeverity.HIGH,
        AuditEventType.SECRET_ROTATION: AuditSeverity.HIGH,
        AuditEventType.WEBHOOK_VALIDATION: AuditSeverity.MEDIUM,
        AuditEventType.PRIVILEGED_OPERATION: AuditSeverity.HIGH,
        AuditEventType.DATA_ACCESS: AuditSeverity.MEDIUM,
        AuditEventType.CONFIGURATION_CHANGE: AuditSeverity.HIGH,
        AuditEventType.EMERGENCY_ACTION: AuditSeverity.CRITICAL,
        AuditEventType.COMPLIANCE_EVENT: AuditSeverity.MEDIUM
    }
    
    base_severity = base_severities.get(event_type, AuditSeverity.MEDIUM)
    
    if outcome in {AuditOutcome.FAILURE, AuditOutcome.ERROR}:
        if base_severity == AuditSeverity.LOW:
            return AuditSeverity.MEDIUM
        elif base_severity == AuditSeverity.MEDIUM:
            return AuditSeverity.HIGH
        elif base_severity == AuditSeverity.HIGH:
            return AuditSeverity.CRITICAL
    
    if principal and principal.is_privileged:
        if base_severity == AuditSeverity.LOW:
            return AuditSeverity.MEDIUM
        elif base_severity == AuditSeverity.MEDIUM:
            return AuditSeverity.HIGH
    
    return base_severity


def sanitize_audit_data(data: Dict[str, Any]) -> Dict[str, Any]:
    sensitive_patterns = {
        'password', 'secret', 'token', 'key', 'auth', 'credential',
        'private', 'signature', 'hash', 'bearer', 'authorization'
    }
    
    pii_patterns = {
        'email', 'phone', 'ssn', 'national_id', 'iban', 'credit_card',
        'passport', 'license', 'vat_number', 'ip_address'
    }
    
    def sanitize_value(key: str, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: sanitize_value(k, v) for k, v in value.items()}
        elif isinstance(value, list):
            return [sanitize_value(key, item) for item in value]
        elif isinstance(value, str):
            key_lower = key.lower()
            
            if any(pattern in key_lower for pattern in sensitive_patterns):
                return "***REDACTED***"
            
            if any(pattern in key_lower for pattern in pii_patterns):
                return _mask_pii_value(key_lower, value)
            
            if len(value) > 10000:  # Truncate very long values
                return value[:10000] + "...[truncated]"
        
        return value
    
    return {k: sanitize_value(k, v) for k, v in data.items()}


def _mask_pii_value(key: str, value: str) -> str:
    if 'email' in key and '@' in value:
        parts = value.split('@')
        if len(parts) == 2:
            username, domain = parts
            masked_username = username[:2] + '*' * (len(username) - 2)
            return f"{masked_username}@{domain}"
    
    elif 'phone' in key:
        return '*' * (len(value) - 4) + value[-4:]
    
    elif 'ip' in key or 'address' in key:
        parts = value.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.***.***.***"
    
    if len(value) > 4:
        return value[:2] + '*' * (len(value) - 4) + value[-2:]
    else:
        return '*' * len(value)


def calculate_audit_hash(event: AuditEvent) -> str:
    hash_data = f"{event.event_id}{event.timestamp.isoformat()}{event.message}"
    if event.principal:
        hash_data += event.principal.user_id
    if event.resource:
        hash_data += event.resource.value
    
    return hashlib.sha256(hash_data.encode()).hexdigest()


def validate_audit_integrity(
    events: List[AuditEvent],
    expected_hashes: List[str]
) -> bool:
    if len(events) != len(expected_hashes):
        return False
    
    for event, expected_hash in zip(events, expected_hashes):
        calculated_hash = calculate_audit_hash(event)
        if calculated_hash != expected_hash:
            return False
    
    return True


def create_dora_compliance_rules() -> List[ComplianceRule]:
    return [
        ComplianceRule(
            rule_id="dora-ict-incidents",
            name="DORA ICT Incident Reporting",
            description="Track all ICT incidents for DORA compliance",
            event_types=[
                AuditEventType.EMERGENCY_ACTION,
                AuditEventType.CONFIGURATION_CHANGE,
                AuditEventType.PRIVILEGED_OPERATION
            ],
            required_fields=[
                "timestamp", "event_type", "principal", "outcome", "message"
            ],
            retention_days=2555,  # 7 years
            real_time_alerts=True
        ),
        
        ComplianceRule(
            rule_id="dora-access-controls",
            name="DORA Access Control Monitoring",
            description="Monitor access to critical ICT systems",
            event_types=[
                AuditEventType.AUTHENTICATION,
                AuditEventType.AUTHORIZATION,
                AuditEventType.SECRET_ACCESS
            ],
            required_fields=[
                "timestamp", "principal", "resource", "outcome"
            ],
            retention_days=1825,  # 5 years
            real_time_alerts=False
        ),
        
        ComplianceRule(
            rule_id="dora-third-party-risk",
            name="DORA Third-Party Risk Management",
            description="Track third-party service interactions",
            event_types=[
                AuditEventType.WEBHOOK_VALIDATION,
                AuditEventType.DATA_ACCESS
            ],
            required_fields=[
                "timestamp", "event_type", "context", "outcome"
            ],
            retention_days=2555,  # 7 years
            real_time_alerts=True
        )
    ]


def create_retention_policies() -> Dict[AuditEventType, RetentionPolicy]:
    return {
        AuditEventType.AUTHENTICATION: RetentionPolicy(
            retention_days=1825,  # 5 years
            archive_after_days=365,
            compress_after_days=90,
            purge_pii_after_days=2555  # 7 years (DORA requirement)
        ),
        
        AuditEventType.SECRET_ACCESS: RetentionPolicy(
            retention_days=2555,  # 7 years
            archive_after_days=730,
            compress_after_days=180,
            purge_pii_after_days=None  # Never purge for security events
        ),
        
        AuditEventType.PRIVILEGED_OPERATION: RetentionPolicy(
            retention_days=2555,  # 7 years
            archive_after_days=1095,
            compress_after_days=365,
            purge_pii_after_days=None
        ),
        
        AuditEventType.EMERGENCY_ACTION: RetentionPolicy(
            retention_days=3650,  # 10 years
            archive_after_days=1825,
            compress_after_days=730,
            purge_pii_after_days=None
        ),
        
        AuditEventType.COMPLIANCE_EVENT: RetentionPolicy(
            retention_days=2555,  # 7 years (DORA requirement)
            archive_after_days=1095,
            compress_after_days=730,
            purge_pii_after_days=2555
        )
    }


def filter_events_by_query(
    events: List[AuditEvent],
    query: AuditQuery
) -> List[AuditEvent]:
    filtered = events
    
    if query.start_date:
        filtered = [e for e in filtered if e.timestamp >= query.start_date]
    
    if query.end_date:
        filtered = [e for e in filtered if e.timestamp <= query.end_date]
    
    if query.event_types:
        filtered = [e for e in filtered if e.event_type in query.event_types]
    
    if query.user_ids and any(e.principal for e in filtered):
        filtered = [
            e for e in filtered 
            if e.principal and e.principal.user_id in query.user_ids
        ]
    
    if query.outcomes:
        filtered = [e for e in filtered if e.outcome in query.outcomes]
    
    if query.severities:
        filtered = [e for e in filtered if e.severity in query.severities]
    
    if query.resources:
        filtered = [e for e in filtered if e.resource in query.resources]
    
    if query.client_ips:
        filtered = [
            e for e in filtered
            if e.context.client_ip in query.client_ips
        ]
    
    sorted_events = sorted(filtered, key=lambda e: e.timestamp, reverse=True)
    
    return sorted_events[query.offset:query.offset + query.limit]


def calculate_audit_statistics(
    events: List[AuditEvent],
    time_range: Optional[tuple[datetime, datetime]] = None
) -> AuditStatistics:
    if not events:
        return AuditStatistics(
            total_events=0,
            events_by_type={},
            events_by_outcome={},
            events_by_severity={},
            events_by_user={},
            failed_authentications=0,
            privileged_operations=0,
            security_incidents=0,
            time_range=time_range or (datetime.now(timezone.utc), datetime.now(timezone.utc))
        )
    
    if not time_range:
        start_time = min(e.timestamp for e in events)
        end_time = max(e.timestamp for e in events)
        time_range = (start_time, end_time)
    
    events_by_type = {}
    events_by_outcome = {}
    events_by_severity = {}
    events_by_user = {}
    
    failed_authentications = 0
    privileged_operations = 0
    security_incidents = 0
    
    for event in events:
        events_by_type[event.event_type.value] = events_by_type.get(event.event_type.value, 0) + 1
        events_by_outcome[event.outcome.value] = events_by_outcome.get(event.outcome.value, 0) + 1
        events_by_severity[event.severity.value] = events_by_severity.get(event.severity.value, 0) + 1
        
        if event.principal:
            user_key = event.principal.user_id
            events_by_user[user_key] = events_by_user.get(user_key, 0) + 1
        
        if (event.event_type == AuditEventType.AUTHENTICATION and 
            event.outcome in {AuditOutcome.FAILURE, AuditOutcome.DENIED}):
            failed_authentications += 1
        
        if event.is_privileged:
            privileged_operations += 1
        
        if event.requires_investigation:
            security_incidents += 1
    
    return AuditStatistics(
        total_events=len(events),
        events_by_type=events_by_type,
        events_by_outcome=events_by_outcome,
        events_by_severity=events_by_severity,
        events_by_user=events_by_user,
        failed_authentications=failed_authentications,
        privileged_operations=privileged_operations,
        security_incidents=security_incidents,
        time_range=time_range
    )


def detect_anomalous_patterns(events: List[AuditEvent]) -> List[Dict[str, Any]]:
    anomalies = []
    
    failed_auth_attempts = {}
    for event in events:
        if (event.event_type == AuditEventType.AUTHENTICATION and
            event.outcome in {AuditOutcome.FAILURE, AuditOutcome.DENIED}):
            
            client_ip = event.context.client_ip or "unknown"
            failed_auth_attempts[client_ip] = failed_auth_attempts.get(client_ip, 0) + 1
    
    for ip, count in failed_auth_attempts.items():
        if count >= 10:  # Threshold for suspicious activity
            anomalies.append({
                "type": "multiple_failed_auth",
                "source_ip": ip,
                "count": count,
                "severity": "high" if count >= 50 else "medium"
            })
    
    privileged_after_hours = []
    for event in events:
        if event.is_privileged and event.timestamp.hour < 6 or event.timestamp.hour > 22:
            privileged_after_hours.append(event)
    
    if len(privileged_after_hours) > 0:
        anomalies.append({
            "type": "after_hours_privileged_access",
            "count": len(privileged_after_hours),
            "events": [e.event_id for e in privileged_after_hours[:5]],
            "severity": "medium"
        })
    
    return anomalies


def should_expire_event(
    event: AuditEvent,
    retention_policy: RetentionPolicy,
    current_time: Optional[datetime] = None
) -> bool:
    now = current_time or datetime.now(timezone.utc)
    retention_cutoff = now - timedelta(days=retention_policy.retention_days)
    
    return event.timestamp < retention_cutoff