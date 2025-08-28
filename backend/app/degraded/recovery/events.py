"""
Background Recovery Detection - Domain Events

Events emitted by the recovery system for monitoring and observability.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from .contracts import HealthCheckType, RecoveryStatus


@dataclass(frozen=True)
class ServiceHealthCheckStarted:
    """
    Event emitted when service health check begins.
    
    Used for tracking health check operations and timing.
    """
    
    event_id: str
    timestamp: datetime
    service_name: str
    check_type: HealthCheckType
    timeout_seconds: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ServiceHealthCheckCompleted:
    """
    Event emitted when service health check completes.
    
    Critical for recovery decision making and service monitoring.
    """
    
    event_id: str
    timestamp: datetime
    service_name: str
    check_type: HealthCheckType
    is_healthy: bool
    response_time_ms: Optional[int] = None
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class AutoRecoveryTriggered:
    """
    Event emitted when automatic recovery is triggered.
    
    Important for auditing automatic system decisions.
    """
    
    event_id: str
    timestamp: datetime
    service_name: str
    trigger_reason: str
    health_check_confidence: float
    degraded_duration_seconds: Optional[int] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RecoveryPlanCreated:
    """
    Event emitted when recovery plan is created.
    
    Tracks the start of recovery processes.
    """
    
    event_id: str
    timestamp: datetime
    plan_id: str
    service_name: str
    recovery_type: str
    estimated_duration_seconds: int
    automatic_execution: bool
    step_count: int = 0
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RecoveryStepStarted:
    """
    Event emitted when individual recovery step begins.
    
    Provides granular tracking of recovery progress.
    """
    
    event_id: str
    timestamp: datetime
    plan_id: str
    step_id: str
    step_name: str
    estimated_duration_seconds: int
    dependencies_completed: int = 0
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RecoveryStepCompleted:
    """
    Event emitted when recovery step completes.
    
    Tracks progress and timing of recovery steps.
    """
    
    event_id: str
    timestamp: datetime
    plan_id: str
    step_id: str
    step_name: str
    step_status: RecoveryStatus
    actual_duration_seconds: int
    error_message: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RecoveryPlanCompleted:
    """
    Event emitted when entire recovery plan completes.
    
    Marks completion of recovery process with summary metrics.
    """
    
    event_id: str
    timestamp: datetime
    plan_id: str
    service_name: str
    overall_status: RecoveryStatus
    total_duration_seconds: int
    successful_steps: int
    failed_steps: int = 0
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ServiceRecovered:
    """
    Event emitted when service is confirmed to be fully recovered.
    
    Final confirmation that service has returned to normal operation.
    """
    
    event_id: str
    timestamp: datetime
    service_name: str
    recovery_plan_id: str
    total_downtime_seconds: int
    recovery_method: str  # "automatic", "manual", "assisted"
    fallbacks_deactivated: list[str]
    health_confirmation_checks: int
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Set default empty list for fallbacks."""
        if not hasattr(self, 'fallbacks_deactivated') or self.fallbacks_deactivated is None:
            object.__setattr__(self, 'fallbacks_deactivated', [])


@dataclass(frozen=True)
class RecoveryAttemptFailed:
    """
    Event emitted when recovery attempt fails.
    
    Important for understanding recovery failures and improving processes.
    """
    
    event_id: str
    timestamp: datetime
    service_name: str
    recovery_plan_id: str
    failure_reason: str
    failed_at_step: Optional[str] = None
    retry_scheduled: bool = False
    next_retry_time: Optional[datetime] = None
    manual_intervention_required: bool = False
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class FallbackSystemDeactivated:
    """
    Event emitted when fallback system is deactivated after recovery.
    
    Tracks transition from degraded mode back to normal operations.
    """
    
    event_id: str
    timestamp: datetime
    fallback_system: str
    service_name: str
    deactivation_reason: str
    operations_handled_during_degraded: int
    fallback_duration_seconds: int
    graceful_shutdown: bool = True
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RecoveryConfidenceUpdated:
    """
    Event emitted when recovery confidence level changes significantly.
    
    Helps track recovery readiness and decision making.
    """
    
    event_id: str
    timestamp: datetime
    service_name: str
    previous_confidence: float
    current_confidence: float
    confidence_trend: str  # "improving", "declining", "stable"
    health_checks_analyzed: int
    trigger_threshold: float
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate confidence values."""
        if not (0.0 <= self.previous_confidence <= 1.0):
            raise ValueError("Previous confidence must be between 0.0 and 1.0")
        if not (0.0 <= self.current_confidence <= 1.0):
            raise ValueError("Current confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class ManualRecoveryRequested:
    """
    Event emitted when manual recovery is requested by user.
    
    Tracks manual interventions in the recovery process.
    """
    
    event_id: str
    timestamp: datetime
    service_name: str
    requested_by_user: str
    recovery_type: str
    override_automatic_checks: bool = False
    reason: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class RecoveryHealthMetrics:
    """
    Event emitted periodically with recovery system health metrics.
    
    Provides overall system health for monitoring dashboards.
    """
    
    event_id: str
    timestamp: datetime
    total_services_monitored: int
    healthy_services: int
    degraded_services: int
    failed_services: int
    active_recovery_plans: int
    successful_recoveries_24h: int
    failed_recoveries_24h: int
    average_recovery_time_minutes: float
    automatic_recovery_rate: float  # Percentage of recoveries that were automatic
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate metrics."""
        if self.automatic_recovery_rate < 0 or self.automatic_recovery_rate > 1:
            raise ValueError("Automatic recovery rate must be between 0 and 1")


@dataclass(frozen=True)
class DegradedModeExitInitiated:
    """
    Event emitted when system begins transitioning out of degraded mode.
    
    Marks the start of the process to return to normal operations.
    """
    
    event_id: str
    timestamp: datetime
    trigger_service: str
    exit_strategy: str  # "gradual", "immediate", "manual"
    services_to_recover: list[str]
    estimated_transition_time_seconds: int
    fallback_systems_to_deactivate: list[str]
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Set default empty lists."""
        if not hasattr(self, 'services_to_recover') or self.services_to_recover is None:
            object.__setattr__(self, 'services_to_recover', [])
        if not hasattr(self, 'fallback_systems_to_deactivate') or self.fallback_systems_to_deactivate is None:
            object.__setattr__(self, 'fallback_systems_to_deactivate', [])