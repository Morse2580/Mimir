import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from celery import Celery
import redis
from ..vault.shell import KeyVaultService
from ..vault.contracts import SecretType
from .contracts import (
    RotationRequest, RotationJob, RotationResult, RotationSchedule,
    RotationPolicy, RotationStatus, RotationTrigger, RotationError,
    SecretGenerationError, ValidationFailedError, RollbackError
)
from .core import (
    create_default_rotation_policies, calculate_next_rotation_date,
    generate_job_id, generate_secret_value, validate_secret_strength,
    get_secrets_due_for_rotation, get_emergency_rotation_priority
)


logger = logging.getLogger(__name__)


class SecretRotationService:
    def __init__(
        self,
        vault_service: KeyVaultService,
        redis_client: redis.Redis,
        celery_app: Optional[Celery] = None
    ):
        self.vault_service = vault_service
        self.redis_client = redis_client
        self.celery_app = celery_app
        self.policies = create_default_rotation_policies()
        
    async def schedule_rotation(
        self,
        secret_name: str,
        secret_type: SecretType,
        trigger: RotationTrigger,
        requested_by: str,
        reason: str = "Scheduled rotation",
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        request = RotationRequest(
            secret_name=secret_name,
            secret_type=secret_type,
            trigger=trigger,
            requested_by=requested_by,
            requested_at=datetime.now(timezone.utc),
            reason=reason,
            metadata=metadata or {}
        )
        
        policy = self.policies.get(secret_type)
        if not policy:
            raise RotationError(f"No rotation policy found for secret type {secret_type}")
        
        job_id = generate_job_id(request)
        
        job = RotationJob(
            job_id=job_id,
            request=request,
            policy=policy,
            status=RotationStatus.PENDING,
            started_at=None,
            completed_at=None,
            error_message=None,
            retry_count=0,
            old_version=None,
            new_version=None,
            rollback_version=None,
            validation_results={}
        )
        
        await self._save_job(job)
        
        if request.is_emergency:
            await self._execute_rotation_immediately(job)
        elif self.celery_app:
            self.celery_app.send_task('rotate_secret', args=[job_id])
        else:
            asyncio.create_task(self._execute_rotation(job_id))
        
        logger.info(
            f"Scheduled rotation for secret {secret_name}",
            extra={
                "job_id": job_id,
                "secret_name": secret_name,
                "secret_type": secret_type.value,
                "trigger": trigger.value,
                "requested_by": requested_by
            }
        )
        
        return job_id
    
    async def rotate_secret(self, job_id: str) -> RotationResult:
        job = await self._load_job(job_id)
        if not job:
            raise RotationError(f"Job {job_id} not found")
        
        return await self._execute_rotation(job_id)
    
    async def get_rotation_schedule(self, secret_name: str) -> Optional[RotationSchedule]:
        cache_key = f"rotation:schedule:{secret_name}"
        
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                import json
                data = json.loads(cached_data)
                return self._deserialize_schedule(data)
        except Exception as e:
            logger.warning(f"Failed to load schedule from cache: {e}")
        
        return None
    
    async def get_secrets_due_for_rotation(self) -> List[RotationSchedule]:
        all_schedules = await self._load_all_schedules()
        return get_secrets_due_for_rotation(all_schedules)
    
    async def get_rotation_status(self, job_id: str) -> Optional[RotationJob]:
        return await self._load_job(job_id)
    
    async def cancel_rotation(self, job_id: str, reason: str = "User cancelled") -> bool:
        job = await self._load_job(job_id)
        if not job:
            return False
        
        if job.status not in {RotationStatus.PENDING, RotationStatus.IN_PROGRESS}:
            return False
        
        updated_job = RotationJob(
            job_id=job.job_id,
            request=job.request,
            policy=job.policy,
            status=RotationStatus.FAILED,
            started_at=job.started_at,
            completed_at=datetime.now(timezone.utc),
            error_message=f"Cancelled: {reason}",
            retry_count=job.retry_count,
            old_version=job.old_version,
            new_version=job.new_version,
            rollback_version=job.rollback_version,
            validation_results=job.validation_results
        )
        
        await self._save_job(updated_job)
        
        logger.info(
            f"Cancelled rotation job {job_id}",
            extra={"job_id": job_id, "reason": reason}
        )
        
        return True
    
    async def _execute_rotation(self, job_id: str) -> RotationResult:
        job = await self._load_job(job_id)
        if not job:
            raise RotationError(f"Job {job_id} not found")
        
        max_retries = job.policy.max_retries
        
        for attempt in range(max_retries + 1):
            try:
                updated_job = RotationJob(
                    job_id=job.job_id,
                    request=job.request,
                    policy=job.policy,
                    status=RotationStatus.IN_PROGRESS,
                    started_at=datetime.now(timezone.utc),
                    completed_at=None,
                    error_message=None,
                    retry_count=attempt,
                    old_version=job.old_version,
                    new_version=job.new_version,
                    rollback_version=job.rollback_version,
                    validation_results=job.validation_results
                )
                
                await self._save_job(updated_job)
                
                result = await self._perform_rotation(updated_job)
                
                if result.success:
                    await self._update_rotation_schedule(job.request.secret_name, job.request.secret_type)
                    return result
                
                job = updated_job
                
            except Exception as e:
                logger.warning(
                    f"Rotation attempt {attempt + 1} failed for job {job_id}: {str(e)}"
                )
                
                if attempt == max_retries:
                    return await self._handle_rotation_failure(job, str(e))
                
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return await self._handle_rotation_failure(job, "Max retries exceeded")
    
    async def _execute_rotation_immediately(self, job: RotationJob):
        try:
            await self._execute_rotation(job.job_id)
        except Exception as e:
            logger.error(f"Emergency rotation failed: {str(e)}", exc_info=True)
    
    async def _perform_rotation(self, job: RotationJob) -> RotationResult:
        secret_name = job.request.secret_name
        secret_type = job.request.secret_type
        
        try:
            current_secret = await self.vault_service.get_secret(secret_name, use_cache=False)
            old_version = current_secret.metadata.version
        except Exception:
            current_secret = None
            old_version = None
        
        new_value = generate_secret_value(secret_type)
        
        if not validate_secret_strength(new_value, secret_type):
            raise SecretGenerationError(f"Generated secret failed strength validation")
        
        if job.policy.validation_required:
            validation_passed = await self._validate_new_secret(new_value, secret_type)
            if not validation_passed:
                raise ValidationFailedError("New secret failed validation")
        
        try:
            new_metadata = await self.vault_service.set_secret(
                secret_name,
                new_value,
                secret_type,
                tags={
                    "rotation_job_id": job.job_id,
                    "rotation_trigger": job.request.trigger.value,
                    "rotated_by": job.request.requested_by,
                    "previous_version": old_version or "none"
                }
            )
            
            completed_job = RotationJob(
                job_id=job.job_id,
                request=job.request,
                policy=job.policy,
                status=RotationStatus.COMPLETED,
                started_at=job.started_at,
                completed_at=datetime.now(timezone.utc),
                error_message=None,
                retry_count=job.retry_count,
                old_version=old_version,
                new_version=new_metadata.version,
                rollback_version=old_version,
                validation_results={"strength": True, "custom": True}
            )
            
            await self._save_job(completed_job)
            
            logger.info(
                f"Successfully rotated secret {secret_name}",
                extra={
                    "job_id": job.job_id,
                    "secret_name": secret_name,
                    "old_version": old_version,
                    "new_version": new_metadata.version
                }
            )
            
            return RotationResult(
                job=completed_job,
                success=True,
                old_secret=current_secret.metadata if current_secret else None,
                new_secret=new_metadata,
                validation_passed=True,
                error_details=None
            )
            
        except Exception as e:
            if job.policy.rollback_on_failure and current_secret:
                await self._attempt_rollback(job, current_secret.value)
            
            raise RotationError(f"Failed to update secret in vault: {str(e)}")
    
    async def _validate_new_secret(self, secret_value: str, secret_type: SecretType) -> bool:
        if secret_type == SecretType.API_KEY:
            return len(secret_value) >= 24 and secret_value.isalnum()
        
        elif secret_type == SecretType.DATABASE_PASSWORD:
            return validate_secret_strength(secret_value, secret_type)
        
        elif secret_type == SecretType.WEBHOOK_SECRET:
            return len(secret_value) >= 32
        
        return True
    
    async def _attempt_rollback(self, job: RotationJob, old_value: str):
        try:
            await self.vault_service.set_secret(
                job.request.secret_name,
                old_value,
                job.request.secret_type,
                tags={
                    "rollback_job_id": job.job_id,
                    "rollback_reason": "Rotation failed"
                }
            )
            
            logger.info(f"Successfully rolled back secret {job.request.secret_name}")
            
        except Exception as e:
            logger.error(f"Rollback failed for job {job.job_id}: {str(e)}")
            raise RollbackError(f"Rollback failed: {str(e)}", job.job_id)
    
    async def _handle_rotation_failure(self, job: RotationJob, error_message: str) -> RotationResult:
        failed_job = RotationJob(
            job_id=job.job_id,
            request=job.request,
            policy=job.policy,
            status=RotationStatus.FAILED,
            started_at=job.started_at,
            completed_at=datetime.now(timezone.utc),
            error_message=error_message,
            retry_count=job.retry_count,
            old_version=job.old_version,
            new_version=job.new_version,
            rollback_version=job.rollback_version,
            validation_results=job.validation_results
        )
        
        await self._save_job(failed_job)
        
        logger.error(
            f"Rotation failed for job {job.job_id}",
            extra={
                "job_id": job.job_id,
                "secret_name": job.request.secret_name,
                "error": error_message,
                "retry_count": job.retry_count
            }
        )
        
        return RotationResult(
            job=failed_job,
            success=False,
            old_secret=None,
            new_secret=None,
            validation_passed=False,
            error_details=error_message
        )
    
    async def _save_job(self, job: RotationJob):
        import json
        
        job_data = {
            "job_id": job.job_id,
            "request": {
                "secret_name": job.request.secret_name,
                "secret_type": job.request.secret_type.value,
                "trigger": job.request.trigger.value,
                "requested_by": job.request.requested_by,
                "requested_at": job.request.requested_at.isoformat(),
                "reason": job.request.reason,
                "metadata": job.request.metadata
            },
            "policy": {
                "secret_type": job.policy.secret_type.value,
                "rotation_interval_days": job.policy.rotation_interval_days,
                "warning_days": job.policy.warning_days,
                "auto_rotate": job.policy.auto_rotate,
                "max_retries": job.policy.max_retries,
                "rollback_on_failure": job.policy.rollback_on_failure,
                "validation_required": job.policy.validation_required,
                "notification_channels": job.policy.notification_channels
            },
            "status": job.status.value,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "error_message": job.error_message,
            "retry_count": job.retry_count,
            "old_version": job.old_version,
            "new_version": job.new_version,
            "rollback_version": job.rollback_version,
            "validation_results": job.validation_results
        }
        
        cache_key = f"rotation:job:{job.job_id}"
        self.redis_client.setex(cache_key, 86400 * 30, json.dumps(job_data))  # 30 days
    
    async def _load_job(self, job_id: str) -> Optional[RotationJob]:
        import json
        
        cache_key = f"rotation:job:{job_id}"
        
        try:
            cached_data = self.redis_client.get(cache_key)
            if not cached_data:
                return None
            
            data = json.loads(cached_data)
            return self._deserialize_job(data)
            
        except Exception as e:
            logger.warning(f"Failed to load job {job_id}: {e}")
            return None
    
    async def _update_rotation_schedule(self, secret_name: str, secret_type: SecretType):
        policy = self.policies.get(secret_type)
        if not policy:
            return
        
        next_rotation = calculate_next_rotation_date(policy)
        
        schedule = RotationSchedule(
            secret_name=secret_name,
            secret_type=secret_type,
            next_rotation=next_rotation,
            policy=policy,
            last_rotation=datetime.now(timezone.utc),
            rotation_history=[]
        )
        
        await self._save_schedule(schedule)
    
    async def _save_schedule(self, schedule: RotationSchedule):
        import json
        
        schedule_data = {
            "secret_name": schedule.secret_name,
            "secret_type": schedule.secret_type.value,
            "next_rotation": schedule.next_rotation.isoformat(),
            "last_rotation": schedule.last_rotation.isoformat() if schedule.last_rotation else None,
            "rotation_history": schedule.rotation_history,
            "policy": {
                "secret_type": schedule.policy.secret_type.value,
                "rotation_interval_days": schedule.policy.rotation_interval_days,
                "warning_days": schedule.policy.warning_days,
                "auto_rotate": schedule.policy.auto_rotate,
                "max_retries": schedule.policy.max_retries,
                "rollback_on_failure": schedule.policy.rollback_on_failure,
                "validation_required": schedule.policy.validation_required,
                "notification_channels": schedule.policy.notification_channels
            }
        }
        
        cache_key = f"rotation:schedule:{schedule.secret_name}"
        self.redis_client.setex(cache_key, 86400 * 7, json.dumps(schedule_data))  # 7 days
    
    async def _load_all_schedules(self) -> List[RotationSchedule]:
        pattern = "rotation:schedule:*"
        keys = self.redis_client.keys(pattern)
        
        schedules = []
        for key in keys:
            try:
                data = self.redis_client.get(key)
                if data:
                    import json
                    schedule_data = json.loads(data)
                    schedule = self._deserialize_schedule(schedule_data)
                    schedules.append(schedule)
            except Exception as e:
                logger.warning(f"Failed to load schedule from key {key}: {e}")
        
        return schedules
    
    def _deserialize_job(self, data: Dict[str, Any]) -> RotationJob:
        from .contracts import RotationPolicy, RotationRequest
        
        request_data = data["request"]
        policy_data = data["policy"]
        
        request = RotationRequest(
            secret_name=request_data["secret_name"],
            secret_type=SecretType(request_data["secret_type"]),
            trigger=RotationTrigger(request_data["trigger"]),
            requested_by=request_data["requested_by"],
            requested_at=datetime.fromisoformat(request_data["requested_at"]),
            reason=request_data["reason"],
            metadata=request_data["metadata"]
        )
        
        policy = RotationPolicy(
            secret_type=SecretType(policy_data["secret_type"]),
            rotation_interval_days=policy_data["rotation_interval_days"],
            warning_days=policy_data["warning_days"],
            auto_rotate=policy_data["auto_rotate"],
            max_retries=policy_data["max_retries"],
            rollback_on_failure=policy_data["rollback_on_failure"],
            validation_required=policy_data["validation_required"],
            notification_channels=policy_data["notification_channels"]
        )
        
        return RotationJob(
            job_id=data["job_id"],
            request=request,
            policy=policy,
            status=RotationStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data["started_at"] else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data["completed_at"] else None,
            error_message=data["error_message"],
            retry_count=data["retry_count"],
            old_version=data["old_version"],
            new_version=data["new_version"],
            rollback_version=data["rollback_version"],
            validation_results=data["validation_results"]
        )
    
    def _deserialize_schedule(self, data: Dict[str, Any]) -> RotationSchedule:
        from .contracts import RotationPolicy
        
        policy_data = data["policy"]
        
        policy = RotationPolicy(
            secret_type=SecretType(policy_data["secret_type"]),
            rotation_interval_days=policy_data["rotation_interval_days"],
            warning_days=policy_data["warning_days"],
            auto_rotate=policy_data["auto_rotate"],
            max_retries=policy_data["max_retries"],
            rollback_on_failure=policy_data["rollback_on_failure"],
            validation_required=policy_data["validation_required"],
            notification_channels=policy_data["notification_channels"]
        )
        
        return RotationSchedule(
            secret_name=data["secret_name"],
            secret_type=SecretType(data["secret_type"]),
            next_rotation=datetime.fromisoformat(data["next_rotation"]),
            policy=policy,
            last_rotation=datetime.fromisoformat(data["last_rotation"]) if data["last_rotation"] else None,
            rotation_history=data["rotation_history"]
        )