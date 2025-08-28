import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import redis
from azure.storage.blob import BlobServiceClient
from .contracts import (
    AuditEvent, AuditEventType, AuditOutcome, AuditQuery, AuditStatistics,
    RetentionPolicy, ComplianceRule, AuditError, AuditStorageError
)
from .core import (
    create_audit_event, sanitize_audit_data, calculate_audit_hash,
    create_dora_compliance_rules, create_retention_policies,
    filter_events_by_query, calculate_audit_statistics, detect_anomalous_patterns
)


logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(
        self,
        redis_client: redis.Redis,
        blob_service: Optional[BlobServiceClient] = None,
        container_name: str = "audit-logs"
    ):
        self.redis_client = redis_client
        self.blob_service = blob_service
        self.container_name = container_name
        self.compliance_rules = create_dora_compliance_rules()
        self.retention_policies = create_retention_policies()
        
        if self.blob_service:
            self._ensure_container_exists()
    
    async def log_event(
        self,
        event_type: AuditEventType,
        outcome: AuditOutcome,
        message: str,
        **kwargs
    ) -> str:
        try:
            event = create_audit_event(
                event_type=event_type,
                outcome=outcome,
                message=message,
                **kwargs
            )
            
            sanitized_details = sanitize_audit_data(event.details)
            sanitized_event = AuditEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                timestamp=event.timestamp,
                principal=event.principal,
                resource=event.resource,
                permission=event.permission,
                outcome=event.outcome,
                severity=event.severity,
                message=event.message,
                context=event.context,
                details=sanitized_details
            )
            
            await self._store_event(sanitized_event)
            
            await self._check_compliance_rules(sanitized_event)
            
            logger.info(
                f"Audit event logged: {event_type.value}",
                extra={
                    "event_id": sanitized_event.event_id,
                    "event_type": event_type.value,
                    "outcome": outcome.value,
                    "severity": sanitized_event.severity.value,
                    "user_id": sanitized_event.principal.user_id if sanitized_event.principal else None
                }
            )
            
            return sanitized_event.event_id
            
        except Exception as e:
            logger.error(f"Failed to log audit event: {str(e)}", exc_info=True)
            raise AuditError(f"Failed to log audit event: {str(e)}")
    
    async def query_events(self, query: AuditQuery) -> List[AuditEvent]:
        try:
            events = await self._retrieve_events(query)
            
            return filter_events_by_query(events, query)
            
        except Exception as e:
            logger.error(f"Failed to query audit events: {str(e)}", exc_info=True)
            raise AuditError(f"Failed to query audit events: {str(e)}")
    
    async def get_statistics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> AuditStatistics:
        try:
            query = AuditQuery(
                start_date=start_date,
                end_date=end_date,
                limit=10000
            )
            
            events = await self.query_events(query)
            
            time_range = None
            if start_date and end_date:
                time_range = (start_date, end_date)
            
            return calculate_audit_statistics(events, time_range)
            
        except Exception as e:
            logger.error(f"Failed to calculate audit statistics: {str(e)}", exc_info=True)
            raise AuditError(f"Failed to calculate audit statistics: {str(e)}")
    
    async def detect_anomalies(
        self,
        hours_back: int = 24
    ) -> List[Dict[str, Any]]:
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time.replace(hour=end_time.hour - hours_back)
            
            query = AuditQuery(
                start_date=start_time,
                end_date=end_time,
                limit=50000
            )
            
            events = await self.query_events(query)
            
            return detect_anomalous_patterns(events)
            
        except Exception as e:
            logger.error(f"Failed to detect anomalies: {str(e)}", exc_info=True)
            return []
    
    async def verify_integrity(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> bool:
        try:
            query = AuditQuery(start_date=start_date, end_date=end_date, limit=100000)
            events = await self.query_events(query)
            
            stored_hashes = await self._retrieve_hashes(start_date, end_date)
            expected_hashes = [calculate_audit_hash(event) for event in events]
            
            return stored_hashes == expected_hashes
            
        except Exception as e:
            logger.error(f"Failed to verify audit integrity: {str(e)}", exc_info=True)
            return False
    
    async def archive_old_events(self, days_old: int = 365) -> int:
        try:
            cutoff_date = datetime.now(timezone.utc).replace(day=cutoff_date.day - days_old)
            
            query = AuditQuery(
                end_date=cutoff_date,
                limit=100000
            )
            
            events_to_archive = await self.query_events(query)
            
            if not events_to_archive:
                return 0
            
            archived_count = await self._archive_to_blob_storage(events_to_archive)
            
            await self._remove_archived_events(events_to_archive)
            
            logger.info(
                f"Archived {archived_count} audit events older than {days_old} days",
                extra={"archived_count": archived_count, "cutoff_date": cutoff_date.isoformat()}
            )
            
            return archived_count
            
        except Exception as e:
            logger.error(f"Failed to archive old events: {str(e)}", exc_info=True)
            raise AuditStorageError(f"Failed to archive old events: {str(e)}")
    
    async def _store_event(self, event: AuditEvent):
        try:
            event_data = event.to_dict()
            event_hash = calculate_audit_hash(event)
            
            pipeline = self.redis_client.pipeline()
            
            event_key = f"audit:event:{event.event_id}"
            pipeline.setex(event_key, 86400 * 30, json.dumps(event_data))  # 30 days in Redis
            
            index_key = f"audit:by_date:{event.timestamp.strftime('%Y-%m-%d')}"
            pipeline.sadd(index_key, event.event_id)
            pipeline.expire(index_key, 86400 * 35)  # Keep index slightly longer
            
            if event.principal:
                user_index_key = f"audit:by_user:{event.principal.user_id}"
                pipeline.sadd(user_index_key, event.event_id)
                pipeline.expire(user_index_key, 86400 * 30)
            
            type_index_key = f"audit:by_type:{event.event_type.value}"
            pipeline.sadd(type_index_key, event.event_id)
            pipeline.expire(type_index_key, 86400 * 30)
            
            hash_key = f"audit:hash:{event.event_id}"
            pipeline.setex(hash_key, 86400 * 30, event_hash)
            
            pipeline.execute()
            
            if self.blob_service:
                await self._store_in_blob_storage(event, event_hash)
                
        except redis.RedisError as e:
            raise AuditStorageError(f"Failed to store event in Redis: {str(e)}")
        except Exception as e:
            raise AuditStorageError(f"Failed to store audit event: {str(e)}")
    
    async def _store_in_blob_storage(self, event: AuditEvent, event_hash: str):
        try:
            blob_name = f"{event.timestamp.strftime('%Y/%m/%d')}/{event.event_id}.json"
            
            blob_data = {
                **event.to_dict(),
                "integrity_hash": event_hash,
                "stored_at": datetime.now(timezone.utc).isoformat()
            }
            
            blob_client = self.blob_service.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            await asyncio.get_event_loop().run_in_executor(
                None,
                blob_client.upload_blob,
                json.dumps(blob_data, indent=2),
                True  # Overwrite
            )
            
        except Exception as e:
            logger.warning(f"Failed to store event in blob storage: {str(e)}")
    
    async def _retrieve_events(self, query: AuditQuery) -> List[AuditEvent]:
        events = []
        
        try:
            if query.start_date and query.end_date:
                current_date = query.start_date.date()
                end_date = query.end_date.date()
                
                while current_date <= end_date:
                    date_key = f"audit:by_date:{current_date.strftime('%Y-%m-%d')}"
                    event_ids = self.redis_client.smembers(date_key)
                    
                    for event_id in event_ids:
                        if isinstance(event_id, bytes):
                            event_id = event_id.decode('utf-8')
                        
                        event = await self._load_event(event_id)
                        if event:
                            events.append(event)
                    
                    current_date = current_date.replace(day=current_date.day + 1)
            
            else:
                pattern = "audit:event:*"
                keys = self.redis_client.keys(pattern)
                
                for key in keys[:query.limit]:
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    
                    event_id = key.split(':')[-1]
                    event = await self._load_event(event_id)
                    if event:
                        events.append(event)
        
        except redis.RedisError as e:
            logger.error(f"Redis error while retrieving events: {str(e)}")
        
        return events
    
    async def _load_event(self, event_id: str) -> Optional[AuditEvent]:
        try:
            event_key = f"audit:event:{event_id}"
            event_data = self.redis_client.get(event_key)
            
            if not event_data:
                return None
            
            data = json.loads(event_data)
            
            return self._deserialize_event(data)
            
        except Exception as e:
            logger.warning(f"Failed to load event {event_id}: {str(e)}")
            return None
    
    def _deserialize_event(self, data: Dict[str, Any]) -> AuditEvent:
        from ..auth.contracts import Principal, Resource, Permission, Role
        from .contracts import AuditContext
        
        principal = None
        if data.get("principal"):
            p_data = data["principal"]
            principal = Principal(
                user_id=p_data["user_id"],
                username=p_data["username"],
                email=p_data.get("email", ""),
                roles={Role(r) for r in p_data.get("roles", [])},
                groups=set(p_data.get("groups", [])),
                session_id=p_data.get("session_id"),
                authenticated_at=datetime.fromisoformat(p_data.get("authenticated_at", "2024-01-01T00:00:00+00:00")),
                expires_at=datetime.fromisoformat(p_data["expires_at"]) if p_data.get("expires_at") else None,
                client_ip=p_data.get("client_ip"),
                user_agent=p_data.get("user_agent")
            )
        
        context_data = data.get("context", {})
        context = AuditContext(
            session_id=context_data.get("session_id"),
            client_ip=context_data.get("client_ip"),
            user_agent=context_data.get("user_agent"),
            request_id=context_data.get("request_id"),
            api_endpoint=context_data.get("api_endpoint"),
            correlation_id=context_data.get("correlation_id"),
            additional_metadata={k: v for k, v in context_data.items() if k not in {
                'session_id', 'client_ip', 'user_agent', 'request_id', 'api_endpoint', 'correlation_id'
            }}
        )
        
        return AuditEvent(
            event_id=data["event_id"],
            event_type=AuditEventType(data["event_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            principal=principal,
            resource=Resource(data["resource"]) if data.get("resource") else None,
            permission=Permission(data["permission"]) if data.get("permission") else None,
            outcome=AuditOutcome(data["outcome"]),
            severity=data["severity"],  # This will need proper deserialization
            message=data["message"],
            context=context,
            details=data.get("details", {})
        )
    
    async def _check_compliance_rules(self, event: AuditEvent):
        try:
            for rule in self.compliance_rules:
                if rule.matches_event(event):
                    if rule.real_time_alerts and event.severity.value in ['high', 'critical']:
                        await self._send_compliance_alert(event, rule)
                    
                    compliance_key = f"compliance:{rule.rule_id}:{event.timestamp.strftime('%Y-%m')}"
                    self.redis_client.sadd(compliance_key, event.event_id)
                    self.redis_client.expire(compliance_key, 86400 * 31)
                    
        except Exception as e:
            logger.error(f"Failed to check compliance rules: {str(e)}")
    
    async def _send_compliance_alert(self, event: AuditEvent, rule: ComplianceRule):
        alert_data = {
            "rule_id": rule.rule_id,
            "rule_name": rule.name,
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "timestamp": event.timestamp.isoformat(),
            "message": event.message
        }
        
        alert_key = f"compliance:alerts:{rule.rule_id}"
        self.redis_client.lpush(alert_key, json.dumps(alert_data))
        self.redis_client.ltrim(alert_key, 0, 999)  # Keep last 1000 alerts
        
        logger.warning(
            f"Compliance alert triggered: {rule.name}",
            extra=alert_data
        )
    
    async def _retrieve_hashes(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[str]:
        hashes = []
        
        current_date = start_date.date()
        end_date_val = end_date.date()
        
        while current_date <= end_date_val:
            date_key = f"audit:by_date:{current_date.strftime('%Y-%m-%d')}"
            event_ids = self.redis_client.smembers(date_key)
            
            for event_id in event_ids:
                if isinstance(event_id, bytes):
                    event_id = event_id.decode('utf-8')
                
                hash_key = f"audit:hash:{event_id}"
                event_hash = self.redis_client.get(hash_key)
                
                if event_hash:
                    if isinstance(event_hash, bytes):
                        event_hash = event_hash.decode('utf-8')
                    hashes.append(event_hash)
            
            current_date = current_date.replace(day=current_date.day + 1)
        
        return sorted(hashes)
    
    def _ensure_container_exists(self):
        try:
            container_client = self.blob_service.get_container_client(self.container_name)
            if not container_client.exists():
                container_client.create_container()
                logger.info(f"Created audit log container: {self.container_name}")
        except Exception as e:
            logger.warning(f"Failed to ensure container exists: {str(e)}")
    
    async def _archive_to_blob_storage(self, events: List[AuditEvent]) -> int:
        if not self.blob_service:
            return 0
        
        archived_count = 0
        
        try:
            for event in events:
                blob_name = f"archive/{event.timestamp.strftime('%Y/%m/%d')}/{event.event_id}.json"
                
                blob_data = {
                    **event.to_dict(),
                    "archived_at": datetime.now(timezone.utc).isoformat(),
                    "integrity_hash": calculate_audit_hash(event)
                }
                
                blob_client = self.blob_service.get_blob_client(
                    container=self.container_name,
                    blob=blob_name
                )
                
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    blob_client.upload_blob,
                    json.dumps(blob_data, indent=2),
                    True
                )
                
                archived_count += 1
                
        except Exception as e:
            logger.error(f"Failed to archive events to blob storage: {str(e)}")
        
        return archived_count
    
    async def _remove_archived_events(self, events: List[AuditEvent]):
        try:
            pipeline = self.redis_client.pipeline()
            
            for event in events:
                event_key = f"audit:event:{event.event_id}"
                hash_key = f"audit:hash:{event.event_id}"
                
                pipeline.delete(event_key)
                pipeline.delete(hash_key)
                
                date_key = f"audit:by_date:{event.timestamp.strftime('%Y-%m-%d')}"
                pipeline.srem(date_key, event.event_id)
                
                if event.principal:
                    user_key = f"audit:by_user:{event.principal.user_id}"
                    pipeline.srem(user_key, event.event_id)
                
                type_key = f"audit:by_type:{event.event_type.value}"
                pipeline.srem(type_key, event.event_id)
            
            pipeline.execute()
            
        except redis.RedisError as e:
            logger.error(f"Failed to remove archived events from Redis: {str(e)}")
            raise AuditStorageError(f"Failed to remove archived events: {str(e)}")