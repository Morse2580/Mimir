"""
Background Recovery Detection - Type Definitions and Contracts

Defines types for monitoring service recovery and automatic mode switching.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Protocol
from enum import Enum
from datetime import datetime


class RecoveryStatus(Enum):
    """Status of service recovery process."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HealthCheckType(Enum):
    """Types of health checks available."""
    HTTP_PING = "http_ping"
    API_CALL = "api_call"
    CIRCUIT_BREAKER = "circuit_breaker"
    CUSTOM = "custom"


@dataclass(frozen=True)
class HealthCheckConfig:
    """Configuration for a service health check."""
    
    service_name: str
    check_type: HealthCheckType
    endpoint_url: Optional[str] = None
    timeout_seconds: int = 10
    expected_response_code: int = 200
    expected_response_time_ms: int = 2000
    check_interval_seconds: int = 30
    failure_threshold: int = 3
    success_threshold: int = 2
    custom_check_function: Optional[str] = None  # Function name for custom checks


@dataclass(frozen=True)
class HealthCheckResult:
    """Result of a service health check."""
    
    service_name: str
    check_type: HealthCheckType
    timestamp: datetime
    is_healthy: bool
    response_time_ms: Optional[int] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RecoveryStep:
    """Individual step in service recovery process."""
    
    step_id: str
    name: str
    description: str
    status: RecoveryStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    estimated_duration_seconds: int = 60
    depends_on: List[str] = None  # Step IDs this step depends on
    
    def __post_init__(self):
        """Set default empty list for dependencies."""
        if self.depends_on is None:
            object.__setattr__(self, 'depends_on', [])


@dataclass(frozen=True)
class RecoveryPlan:
    """Complete recovery plan for restoring services."""
    
    plan_id: str
    service_name: str
    steps: List[RecoveryStep]
    overall_status: RecoveryStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_total_duration_seconds: int = 300
    automatic_execution: bool = True
    

@dataclass(frozen=True)
class RecoveryConfig:
    """Configuration for recovery detection behavior."""
    
    health_check_interval_seconds: int = 30
    recovery_confirmation_checks: int = 3  # Consecutive checks needed to confirm recovery
    max_recovery_attempts: int = 5
    recovery_timeout_minutes: int = 30
    automatic_recovery_enabled: bool = True
    fallback_deactivation_delay_seconds: int = 60  # Wait before deactivating fallbacks
    parallel_health_checks: bool = True
    

@dataclass(frozen=True)
class ServiceRecoveryMetrics:
    """Metrics for service recovery performance."""
    
    service_name: str
    total_recovery_attempts: int
    successful_recoveries: int
    failed_recoveries: int
    average_recovery_time_seconds: float
    last_recovery_time: Optional[datetime]
    current_uptime_seconds: int
    health_check_success_rate: float
    

class HealthChecker(Protocol):
    """Protocol for service health checking implementations."""
    
    async def check_health(self, config: HealthCheckConfig) -> HealthCheckResult:
        """Perform health check on service."""
        ...
        
    async def batch_health_check(
        self, 
        configs: List[HealthCheckConfig]
    ) -> List[HealthCheckResult]:
        """Perform health checks on multiple services."""
        ...


class RecoveryExecutor(Protocol):
    """Protocol for recovery plan execution."""
    
    async def execute_plan(self, plan: RecoveryPlan) -> RecoveryPlan:
        """Execute recovery plan."""
        ...
        
    async def execute_step(
        self, 
        step: RecoveryStep, 
        context: Dict[str, Any]
    ) -> RecoveryStep:
        """Execute individual recovery step."""
        ...
        
    async def cancel_recovery(self, plan_id: str) -> bool:
        """Cancel ongoing recovery."""
        ...


@dataclass(frozen=True)
class RecoveryTrigger:
    """Trigger condition for starting recovery."""
    
    trigger_id: str
    service_name: str
    trigger_type: str  # "health_check", "manual", "timeout"
    condition_met: bool
    triggered_at: datetime
    trigger_data: Dict[str, Any]
    

@dataclass(frozen=True)
class AutoRecoveryStatus:
    """Current status of automatic recovery system."""
    
    enabled: bool
    active_recoveries: List[str]  # Plan IDs
    monitored_services: List[str]
    last_check_time: datetime
    next_check_time: datetime
    total_services_monitored: int
    healthy_services: int
    degraded_services: int
    failed_services: int