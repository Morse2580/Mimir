"""
Background Recovery Detection - I/O Operations

Handles service health checking, recovery plan execution, and automatic recovery management.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable

try:
    import httpx
    import redis.asyncio as redis
except ImportError:
    httpx = None
    redis = None

from .contracts import (
    HealthCheckConfig,
    HealthCheckResult,
    HealthCheckType,
    RecoveryPlan,
    RecoveryStep,
    RecoveryStatus,
    RecoveryConfig,
    AutoRecoveryStatus,
    ServiceRecoveryMetrics,
    RecoveryTrigger
)
from .core import (
    assess_service_health,
    calculate_recovery_confidence,
    determine_recovery_readiness,
    create_recovery_plan,
    calculate_step_readiness,
    update_plan_progress,
    should_trigger_recovery
)
from .events import (
    ServiceHealthCheckStarted,
    ServiceHealthCheckCompleted,
    RecoveryPlanCreated,
    RecoveryStepStarted,
    RecoveryStepCompleted,
    RecoveryPlanCompleted,
    AutoRecoveryTriggered
)

logger = logging.getLogger(__name__)


class RecoveryManagerError(Exception):
    """Raised when recovery manager encounters errors."""
    pass


class BackgroundRecoveryManager:
    """
    Manages background service recovery detection and automatic recovery execution.
    
    Continuously monitors service health and automatically triggers recovery
    when services return to healthy state during degraded mode.
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        config: Optional[RecoveryConfig] = None,
        event_publisher: Optional[Callable] = None
    ):
        self.redis = redis_client
        self.http_client = http_client or httpx.AsyncClient(timeout=10.0)
        self.config = config or RecoveryConfig()
        self.event_publisher = event_publisher or self._default_event_publisher
        
        # Track running tasks
        self._monitoring_tasks: Dict[str, asyncio.Task] = {}
        self._recovery_tasks: Dict[str, asyncio.Task] = {}
        self._shutdown_requested = False
        
    async def start_monitoring(
        self,
        services: List[HealthCheckConfig]
    ) -> None:
        """Start background monitoring for specified services."""
        logger.info(f"Starting recovery monitoring for {len(services)} services")
        
        for service_config in services:
            if service_config.service_name not in self._monitoring_tasks:
                task = asyncio.create_task(
                    self._monitor_service_health(service_config),
                    name=f"monitor_{service_config.service_name}"
                )
                self._monitoring_tasks[service_config.service_name] = task
                
    async def stop_monitoring(self) -> None:
        """Stop all background monitoring tasks."""
        logger.info("Stopping recovery monitoring")
        self._shutdown_requested = True
        
        # Cancel monitoring tasks
        for service_name, task in self._monitoring_tasks.items():
            logger.debug(f"Cancelling monitoring for {service_name}")
            task.cancel()
            
        # Cancel recovery tasks
        for plan_id, task in self._recovery_tasks.items():
            logger.debug(f"Cancelling recovery {plan_id}")
            task.cancel()
            
        # Wait for tasks to complete
        all_tasks = list(self._monitoring_tasks.values()) + list(self._recovery_tasks.values())
        if all_tasks:
            await asyncio.gather(*all_tasks, return_exceptions=True)
            
        self._monitoring_tasks.clear()
        self._recovery_tasks.clear()
        
    async def check_service_health(
        self,
        config: HealthCheckConfig
    ) -> HealthCheckResult:
        """Perform single health check on service."""
        start_time = datetime.utcnow()
        
        # Emit health check started event
        started_event = ServiceHealthCheckStarted(
            event_id=str(uuid.uuid4()),
            timestamp=start_time,
            service_name=config.service_name,
            check_type=config.check_type,
            timeout_seconds=config.timeout_seconds
        )
        await self.event_publisher(started_event)
        
        try:
            if config.check_type == HealthCheckType.HTTP_PING:
                result = await self._http_health_check(config)
            elif config.check_type == HealthCheckType.API_CALL:
                result = await self._api_health_check(config)
            elif config.check_type == HealthCheckType.CIRCUIT_BREAKER:
                result = await self._circuit_breaker_health_check(config)
            else:
                result = await self._custom_health_check(config)
                
        except Exception as e:
            logger.warning(f"Health check failed for {config.service_name}: {e}")
            result = HealthCheckResult(
                service_name=config.service_name,
                check_type=config.check_type,
                timestamp=datetime.utcnow(),
                is_healthy=False,
                error_message=str(e)
            )
        
        # Emit health check completed event
        completed_event = ServiceHealthCheckCompleted(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            service_name=config.service_name,
            check_type=config.check_type,
            is_healthy=result.is_healthy,
            response_time_ms=result.response_time_ms,
            error_message=result.error_message
        )
        await self.event_publisher(completed_event)
        
        # Store result in Redis
        await self._store_health_result(result)
        
        return result
        
    async def trigger_recovery(
        self,
        service_name: str,
        recovery_type: str = "standard",
        manual: bool = False
    ) -> RecoveryPlan:
        """Trigger recovery process for service."""
        plan = create_recovery_plan(service_name, recovery_type)
        
        # Emit recovery plan created event
        created_event = RecoveryPlanCreated(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            plan_id=plan.plan_id,
            service_name=service_name,
            recovery_type=recovery_type,
            estimated_duration_seconds=plan.estimated_total_duration_seconds,
            automatic_execution=not manual
        )
        await self.event_publisher(created_event)
        
        # Start recovery execution
        if plan.plan_id not in self._recovery_tasks:
            task = asyncio.create_task(
                self._execute_recovery_plan(plan),
                name=f"recovery_{plan.plan_id}"
            )
            self._recovery_tasks[plan.plan_id] = task
            
        # Store plan in Redis
        await self._store_recovery_plan(plan)
        
        return plan
        
    async def get_auto_recovery_status(self) -> AutoRecoveryStatus:
        """Get current status of automatic recovery system."""
        if not self.redis:
            return AutoRecoveryStatus(
                enabled=self.config.automatic_recovery_enabled,
                active_recoveries=[],
                monitored_services=[],
                last_check_time=datetime.utcnow(),
                next_check_time=datetime.utcnow(),
                total_services_monitored=0,
                healthy_services=0,
                degraded_services=0,
                failed_services=0
            )
            
        try:
            # Get monitoring status from Redis
            pipe = self.redis.pipeline()
            pipe.smembers("recovery:monitored_services")
            pipe.smembers("recovery:active_recoveries")
            pipe.get("recovery:last_check_time")
            
            results = await pipe.execute()
            monitored_services = [s.decode() if isinstance(s, bytes) else s for s in results[0]]
            active_recoveries = [r.decode() if isinstance(r, bytes) else r for r in results[1]]
            last_check_str = results[2]
            
            last_check_time = datetime.utcnow()
            if last_check_str:
                try:
                    last_check_time = datetime.fromisoformat(
                        last_check_str.decode() if isinstance(last_check_str, bytes) else last_check_str
                    )
                except ValueError:
                    pass
                    
            # Count service health status
            healthy_count = 0
            degraded_count = 0
            failed_count = 0
            
            for service in monitored_services:
                recent_results = await self._get_recent_health_results(service, 5)
                if recent_results:
                    is_healthy = assess_service_health(recent_results)
                    if is_healthy:
                        healthy_count += 1
                    else:
                        confidence = calculate_recovery_confidence(recent_results)
                        if confidence > 0.3:
                            degraded_count += 1
                        else:
                            failed_count += 1
            
            next_check_time = last_check_time + timedelta(
                seconds=self.config.health_check_interval_seconds
            )
            
            return AutoRecoveryStatus(
                enabled=self.config.automatic_recovery_enabled,
                active_recoveries=active_recoveries,
                monitored_services=monitored_services,
                last_check_time=last_check_time,
                next_check_time=next_check_time,
                total_services_monitored=len(monitored_services),
                healthy_services=healthy_count,
                degraded_services=degraded_count,
                failed_services=failed_count
            )
            
        except Exception as e:
            logger.error(f"Failed to get auto recovery status: {e}")
            return AutoRecoveryStatus(
                enabled=False,
                active_recoveries=[],
                monitored_services=[],
                last_check_time=datetime.utcnow(),
                next_check_time=datetime.utcnow(),
                total_services_monitored=0,
                healthy_services=0,
                degraded_services=0,
                failed_services=0
            )
    
    async def _monitor_service_health(self, config: HealthCheckConfig) -> None:
        """Background task to monitor service health."""
        logger.info(f"Starting health monitoring for {config.service_name}")
        
        while not self._shutdown_requested:
            try:
                # Perform health check
                result = await self.check_service_health(config)
                
                # Check if recovery should be triggered
                if self.config.automatic_recovery_enabled:
                    await self._check_recovery_trigger(config.service_name, result)
                    
                # Wait for next check
                await asyncio.sleep(config.check_interval_seconds)
                
            except asyncio.CancelledError:
                logger.info(f"Health monitoring cancelled for {config.service_name}")
                break
            except Exception as e:
                logger.error(f"Error in health monitoring for {config.service_name}: {e}")
                await asyncio.sleep(config.check_interval_seconds)
                
    async def _check_recovery_trigger(
        self,
        service_name: str,
        latest_result: HealthCheckResult
    ) -> None:
        """Check if automatic recovery should be triggered."""
        # Get recent health results
        recent_results = await self._get_recent_health_results(service_name, 10)
        recent_results.append(latest_result)
        
        # Check if degraded mode is active
        degraded_mode_active = await self._is_degraded_mode_active()
        
        # Determine if recovery should be triggered
        should_trigger, reason = should_trigger_recovery(
            recent_results,
            degraded_mode_active,
            self.config
        )
        
        if should_trigger:
            logger.info(f"Auto-triggering recovery for {service_name}: {reason}")
            
            # Emit auto recovery triggered event
            trigger_event = AutoRecoveryTriggered(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                service_name=service_name,
                trigger_reason=reason,
                health_check_confidence=calculate_recovery_confidence(recent_results)
            )
            await self.event_publisher(trigger_event)
            
            # Trigger recovery
            await self.trigger_recovery(service_name, "parallel_ai", manual=False)
        
    async def _execute_recovery_plan(self, plan: RecoveryPlan) -> None:
        """Execute recovery plan steps."""
        logger.info(f"Executing recovery plan {plan.plan_id} for {plan.service_name}")
        
        try:
            # Mark plan as started
            plan = RecoveryPlan(
                plan_id=plan.plan_id,
                service_name=plan.service_name,
                steps=plan.steps,
                overall_status=RecoveryStatus.IN_PROGRESS,
                created_at=plan.created_at,
                started_at=datetime.utcnow(),
                completed_at=plan.completed_at,
                estimated_total_duration_seconds=plan.estimated_total_duration_seconds,
                automatic_execution=plan.automatic_execution
            )
            await self._store_recovery_plan(plan)
            
            completed_step_ids = []
            
            # Execute steps in dependency order
            while True:
                # Find ready steps
                ready_steps = []
                for step in plan.steps:
                    if calculate_step_readiness(step, completed_step_ids):
                        ready_steps.append(step)
                        
                if not ready_steps:
                    break  # No more steps to execute
                    
                # Execute ready steps
                for step in ready_steps:
                    await self._execute_recovery_step(step, plan)
                    completed_step_ids.append(step.step_id)
                    
            # Mark plan as completed
            plan = update_plan_progress(plan, {})
            
            # Emit completion event
            completed_event = RecoveryPlanCompleted(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                plan_id=plan.plan_id,
                service_name=plan.service_name,
                overall_status=plan.overall_status,
                total_duration_seconds=int((datetime.utcnow() - plan.started_at).total_seconds()) if plan.started_at else 0,
                successful_steps=len([s for s in plan.steps if s.status == RecoveryStatus.COMPLETED])
            )
            await self.event_publisher(completed_event)
            
            logger.info(f"Recovery plan {plan.plan_id} completed with status {plan.overall_status}")
            
        except Exception as e:
            logger.error(f"Recovery plan execution failed: {e}")
            # Mark plan as failed
            # Implementation would update plan status
            
        finally:
            # Clean up task reference
            if plan.plan_id in self._recovery_tasks:
                del self._recovery_tasks[plan.plan_id]
    
    async def _execute_recovery_step(
        self,
        step: RecoveryStep,
        plan: RecoveryPlan
    ) -> RecoveryStep:
        """Execute individual recovery step."""
        logger.info(f"Executing recovery step: {step.name}")
        
        # Emit step started event
        started_event = RecoveryStepStarted(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            plan_id=plan.plan_id,
            step_id=step.step_id,
            step_name=step.name,
            estimated_duration_seconds=step.estimated_duration_seconds
        )
        await self.event_publisher(started_event)
        
        start_time = datetime.utcnow()
        
        try:
            # Step implementation would go here
            # For now, simulate step execution
            await asyncio.sleep(min(step.estimated_duration_seconds / 10, 5))
            
            # Mark as completed
            completed_step = RecoveryStep(
                step_id=step.step_id,
                name=step.name,
                description=step.description,
                status=RecoveryStatus.COMPLETED,
                started_at=start_time,
                completed_at=datetime.utcnow(),
                estimated_duration_seconds=step.estimated_duration_seconds,
                depends_on=step.depends_on
            )
            
            # Emit step completed event
            completed_event = RecoveryStepCompleted(
                event_id=str(uuid.uuid4()),
                timestamp=datetime.utcnow(),
                plan_id=plan.plan_id,
                step_id=step.step_id,
                step_name=step.name,
                step_status=RecoveryStatus.COMPLETED,
                actual_duration_seconds=int((datetime.utcnow() - start_time).total_seconds())
            )
            await self.event_publisher(completed_event)
            
            return completed_step
            
        except Exception as e:
            logger.error(f"Recovery step failed: {step.name}: {e}")
            
            failed_step = RecoveryStep(
                step_id=step.step_id,
                name=step.name,
                description=step.description,
                status=RecoveryStatus.FAILED,
                started_at=start_time,
                completed_at=datetime.utcnow(),
                error_message=str(e),
                estimated_duration_seconds=step.estimated_duration_seconds,
                depends_on=step.depends_on
            )
            
            return failed_step
    
    async def _http_health_check(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Perform HTTP ping health check."""
        if not config.endpoint_url or not self.http_client:
            raise ValueError("HTTP health check requires endpoint URL and HTTP client")
            
        start_time = datetime.utcnow()
        
        try:
            response = await self.http_client.get(
                config.endpoint_url,
                timeout=config.timeout_seconds
            )
            
            response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            is_healthy = (
                response.status_code == config.expected_response_code and
                response_time <= config.expected_response_time_ms
            )
            
            return HealthCheckResult(
                service_name=config.service_name,
                check_type=config.check_type,
                timestamp=datetime.utcnow(),
                is_healthy=is_healthy,
                response_time_ms=response_time,
                status_code=response.status_code
            )
            
        except Exception as e:
            return HealthCheckResult(
                service_name=config.service_name,
                check_type=config.check_type,
                timestamp=datetime.utcnow(),
                is_healthy=False,
                error_message=str(e)
            )
    
    async def _api_health_check(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Perform API call health check."""
        # Implementation would make specific API call
        # For now, delegate to HTTP health check
        return await self._http_health_check(config)
    
    async def _circuit_breaker_health_check(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Check circuit breaker status for health assessment."""
        # Implementation would check circuit breaker state from Redis
        # For now, return healthy
        return HealthCheckResult(
            service_name=config.service_name,
            check_type=config.check_type,
            timestamp=datetime.utcnow(),
            is_healthy=True,
            response_time_ms=10
        )
    
    async def _custom_health_check(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Perform custom health check."""
        # Implementation would call custom function
        return HealthCheckResult(
            service_name=config.service_name,
            check_type=config.check_type,
            timestamp=datetime.utcnow(),
            is_healthy=True
        )
    
    async def _store_health_result(self, result: HealthCheckResult) -> None:
        """Store health check result in Redis."""
        if not self.redis:
            return
            
        try:
            key = f"health_results:{result.service_name}"
            
            # Store result with TTL
            result_data = {
                'timestamp': result.timestamp.isoformat(),
                'is_healthy': result.is_healthy,
                'response_time_ms': result.response_time_ms,
                'status_code': result.status_code,
                'error_message': result.error_message
            }
            
            import json
            await self.redis.lpush(key, json.dumps(result_data))
            await self.redis.ltrim(key, 0, 99)  # Keep last 100 results
            await self.redis.expire(key, 86400)  # 24 hour TTL
            
        except Exception as e:
            logger.warning(f"Failed to store health result: {e}")
    
    async def _get_recent_health_results(
        self,
        service_name: str,
        limit: int = 10
    ) -> List[HealthCheckResult]:
        """Get recent health results for service."""
        if not self.redis:
            return []
            
        try:
            key = f"health_results:{service_name}"
            results = await self.redis.lrange(key, 0, limit - 1)
            
            health_results = []
            import json
            
            for result_data in results:
                try:
                    data = json.loads(result_data)
                    result = HealthCheckResult(
                        service_name=service_name,
                        check_type=HealthCheckType.HTTP_PING,  # Default
                        timestamp=datetime.fromisoformat(data['timestamp']),
                        is_healthy=data['is_healthy'],
                        response_time_ms=data.get('response_time_ms'),
                        status_code=data.get('status_code'),
                        error_message=data.get('error_message')
                    )
                    health_results.append(result)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse health result: {e}")
                    continue
                    
            return health_results
            
        except Exception as e:
            logger.warning(f"Failed to get health results: {e}")
            return []
    
    async def _store_recovery_plan(self, plan: RecoveryPlan) -> None:
        """Store recovery plan in Redis."""
        # Implementation would serialize and store plan
        pass
    
    async def _is_degraded_mode_active(self) -> bool:
        """Check if system is currently in degraded mode."""
        if not self.redis:
            return False
            
        try:
            status = await self.redis.get("circuit_breaker:degraded_mode:active")
            return bool(status)
        except Exception:
            return False
    
    async def _default_event_publisher(self, event) -> None:
        """Default event publisher that logs events."""
        logger.info(f"Recovery Event: {type(event).__name__} - {event}")


# Global recovery manager instance
_global_recovery_manager: Optional[BackgroundRecoveryManager] = None


async def start_auto_recovery_monitoring(
    services: List[HealthCheckConfig],
    redis_client: Optional[redis.Redis] = None,
    config: Optional[RecoveryConfig] = None
) -> BackgroundRecoveryManager:
    """Start automatic recovery monitoring for services."""
    global _global_recovery_manager
    
    if _global_recovery_manager is None:
        _global_recovery_manager = BackgroundRecoveryManager(
            redis_client=redis_client,
            config=config
        )
    
    await _global_recovery_manager.start_monitoring(services)
    return _global_recovery_manager


def initialize_recovery_manager(
    redis_client: Optional[redis.Redis] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    config: Optional[RecoveryConfig] = None,
    event_publisher: Optional[Callable] = None
) -> BackgroundRecoveryManager:
    """Initialize the global recovery manager."""
    global _global_recovery_manager
    _global_recovery_manager = BackgroundRecoveryManager(
        redis_client, http_client, config, event_publisher
    )
    return _global_recovery_manager