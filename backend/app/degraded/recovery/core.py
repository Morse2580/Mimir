"""
Background Recovery Detection - Core Functions

Pure functions for recovery detection, health assessment, and plan management.
"""

import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional

from .contracts import (
    HealthCheckResult,
    RecoveryStatus,
    RecoveryStep,
    RecoveryPlan,
    RecoveryConfig,
    ServiceRecoveryMetrics,
    AutoRecoveryStatus,
    RecoveryTrigger,
    HealthCheckType
)


def assess_service_health(
    recent_results: List[HealthCheckResult],
    success_threshold: int = 3
) -> bool:
    """
    Assess if service is healthy based on recent check results.
    
    Args:
        recent_results: Recent health check results, ordered by timestamp
        success_threshold: Number of consecutive successes needed
        
    Returns:
        True if service is considered healthy
        
    MUST be deterministic.
    """
    if len(recent_results) < success_threshold:
        return False
        
    # Check most recent results
    recent_checks = sorted(recent_results, key=lambda x: x.timestamp, reverse=True)
    consecutive_successes = 0
    
    for result in recent_checks:
        if result.is_healthy:
            consecutive_successes += 1
            if consecutive_successes >= success_threshold:
                return True
        else:
            break  # Reset counter on failure
            
    return False


def calculate_recovery_confidence(
    health_results: List[HealthCheckResult],
    required_confirmations: int = 3,
    time_window_minutes: int = 5
) -> float:
    """
    Calculate confidence level for service recovery (0.0 to 1.0).
    
    Args:
        health_results: Health check results to analyze
        required_confirmations: Number of confirmations needed
        time_window_minutes: Time window to consider for recent results
        
    Returns:
        Confidence score from 0.0 (no confidence) to 1.0 (high confidence)
        
    MUST be deterministic.
    """
    if not health_results:
        return 0.0
        
    # Filter to recent results only
    cutoff_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)
    recent_results = [r for r in health_results if r.timestamp >= cutoff_time]
    
    if not recent_results:
        return 0.0
        
    # Calculate success rate
    successful_checks = sum(1 for r in recent_results if r.is_healthy)
    success_rate = successful_checks / len(recent_results)
    
    # Calculate consecutive successes
    sorted_results = sorted(recent_results, key=lambda x: x.timestamp, reverse=True)
    consecutive_successes = 0
    for result in sorted_results:
        if result.is_healthy:
            consecutive_successes += 1
        else:
            break
            
    # Base confidence on success rate and consecutive successes
    confidence = success_rate * 0.7  # 70% weight on overall success rate
    
    # Bonus for consecutive successes
    consecutive_bonus = min(1.0, consecutive_successes / required_confirmations) * 0.3
    confidence += consecutive_bonus
    
    # Penalty for response time issues
    slow_responses = sum(1 for r in recent_results 
                        if r.response_time_ms and r.response_time_ms > 5000)
    if slow_responses > 0:
        response_penalty = (slow_responses / len(recent_results)) * 0.2
        confidence = max(0.0, confidence - response_penalty)
        
    return min(1.0, max(0.0, confidence))


def determine_recovery_readiness(
    service_name: str,
    health_results: List[HealthCheckResult],
    config: RecoveryConfig
) -> Tuple[bool, float, str]:
    """
    Determine if service is ready for recovery from degraded mode.
    
    Args:
        service_name: Name of service to assess
        health_results: Recent health check results
        config: Recovery configuration
        
    Returns:
        Tuple of (is_ready, confidence_score, reason)
        
    MUST be deterministic.
    """
    if not health_results:
        return False, 0.0, "No health check data available"
        
    # Check if service appears healthy
    is_healthy = assess_service_health(
        health_results, 
        config.recovery_confirmation_checks
    )
    
    if not is_healthy:
        return False, 0.0, "Service health checks still failing"
        
    # Calculate recovery confidence
    confidence = calculate_recovery_confidence(
        health_results,
        config.recovery_confirmation_checks
    )
    
    # Require minimum confidence threshold
    min_confidence = 0.8
    if confidence < min_confidence:
        return False, confidence, f"Recovery confidence too low ({confidence:.2%} < {min_confidence:.2%})"
        
    # Check response time consistency
    recent_results = sorted(health_results, key=lambda x: x.timestamp, reverse=True)[:5]
    response_times = [r.response_time_ms for r in recent_results if r.response_time_ms]
    
    if response_times:
        avg_response_time = sum(response_times) / len(response_times)
        if avg_response_time > 3000:  # 3 seconds threshold
            return False, confidence, f"Response times still elevated ({avg_response_time:.0f}ms)"
            
    return True, confidence, "Service ready for recovery"


def create_recovery_plan(
    service_name: str,
    recovery_type: str = "standard"
) -> RecoveryPlan:
    """
    Create recovery plan for service restoration.
    
    Args:
        service_name: Name of service to recover
        recovery_type: Type of recovery plan to create
        
    Returns:
        RecoveryPlan with appropriate steps
        
    MUST be deterministic.
    """
    plan_id = generate_plan_id(service_name, recovery_type)
    
    if recovery_type == "parallel_ai":
        steps = [
            RecoveryStep(
                step_id="verify_health",
                name="Verify Service Health",
                description="Confirm Parallel.ai API is responding correctly",
                status=RecoveryStatus.NOT_STARTED,
                estimated_duration_seconds=30
            ),
            RecoveryStep(
                step_id="test_requests",
                name="Test API Requests",
                description="Execute test requests to verify functionality",
                status=RecoveryStatus.NOT_STARTED,
                estimated_duration_seconds=60,
                depends_on=["verify_health"]
            ),
            RecoveryStep(
                step_id="gradual_transition",
                name="Gradual Traffic Transition",
                description="Gradually shift traffic from fallbacks to primary service",
                status=RecoveryStatus.NOT_STARTED,
                estimated_duration_seconds=180,
                depends_on=["test_requests"]
            ),
            RecoveryStep(
                step_id="deactivate_fallbacks",
                name="Deactivate Fallback Systems",
                description="Safely deactivate RSS and cache fallbacks",
                status=RecoveryStatus.NOT_STARTED,
                estimated_duration_seconds=30,
                depends_on=["gradual_transition"]
            )
        ]
        total_duration = 300
        
    else:  # Standard recovery
        steps = [
            RecoveryStep(
                step_id="health_verification",
                name="Health Verification",
                description="Verify service health and stability",
                status=RecoveryStatus.NOT_STARTED,
                estimated_duration_seconds=60
            ),
            RecoveryStep(
                step_id="restore_traffic",
                name="Restore Traffic",
                description="Restore normal traffic routing",
                status=RecoveryStatus.NOT_STARTED,
                estimated_duration_seconds=120,
                depends_on=["health_verification"]
            ),
            RecoveryStep(
                step_id="cleanup",
                name="Cleanup",
                description="Clean up degraded mode artifacts",
                status=RecoveryStatus.NOT_STARTED,
                estimated_duration_seconds=60,
                depends_on=["restore_traffic"]
            )
        ]
        total_duration = 240
    
    return RecoveryPlan(
        plan_id=plan_id,
        service_name=service_name,
        steps=steps,
        overall_status=RecoveryStatus.NOT_STARTED,
        created_at=datetime.utcnow(),
        estimated_total_duration_seconds=total_duration,
        automatic_execution=True
    )


def generate_plan_id(service_name: str, recovery_type: str) -> str:
    """
    Generate deterministic plan ID for recovery plan.
    
    Args:
        service_name: Name of service
        recovery_type: Type of recovery
        
    Returns:
        Unique plan ID string
        
    MUST be deterministic.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_string = f"{service_name}_{recovery_type}_{timestamp}"
    hash_digest = hashlib.sha256(base_string.encode()).hexdigest()[:8]
    return f"recovery_{service_name}_{hash_digest}"


def calculate_step_readiness(
    step: RecoveryStep,
    completed_steps: List[str]
) -> bool:
    """
    Determine if recovery step is ready to execute based on dependencies.
    
    Args:
        step: Recovery step to check
        completed_steps: List of completed step IDs
        
    Returns:
        True if step is ready to execute
        
    MUST be deterministic.
    """
    if step.status != RecoveryStatus.NOT_STARTED:
        return False
        
    # Check if all dependencies are completed
    for dependency in step.depends_on:
        if dependency not in completed_steps:
            return False
            
    return True


def update_plan_progress(
    plan: RecoveryPlan,
    step_updates: Dict[str, RecoveryStep]
) -> RecoveryPlan:
    """
    Update recovery plan with step progress.
    
    Args:
        plan: Current recovery plan
        step_updates: Dictionary of step updates keyed by step_id
        
    Returns:
        Updated recovery plan
        
    MUST be deterministic.
    """
    updated_steps = []
    completed_count = 0
    failed_count = 0
    in_progress_count = 0
    
    for step in plan.steps:
        if step.step_id in step_updates:
            updated_step = step_updates[step.step_id]
            updated_steps.append(updated_step)
            
            if updated_step.status == RecoveryStatus.COMPLETED:
                completed_count += 1
            elif updated_step.status == RecoveryStatus.FAILED:
                failed_count += 1
            elif updated_step.status == RecoveryStatus.IN_PROGRESS:
                in_progress_count += 1
        else:
            updated_steps.append(step)
            
            if step.status == RecoveryStatus.COMPLETED:
                completed_count += 1
            elif step.status == RecoveryStatus.FAILED:
                failed_count += 1
            elif step.status == RecoveryStatus.IN_PROGRESS:
                in_progress_count += 1
    
    # Determine overall status
    overall_status = plan.overall_status
    if failed_count > 0:
        overall_status = RecoveryStatus.FAILED
    elif completed_count == len(updated_steps):
        overall_status = RecoveryStatus.COMPLETED
    elif in_progress_count > 0 or completed_count > 0:
        overall_status = RecoveryStatus.IN_PROGRESS
        
    # Update completion time if completed
    completed_at = plan.completed_at
    if overall_status == RecoveryStatus.COMPLETED and not completed_at:
        completed_at = datetime.utcnow()
        
    return RecoveryPlan(
        plan_id=plan.plan_id,
        service_name=plan.service_name,
        steps=updated_steps,
        overall_status=overall_status,
        created_at=plan.created_at,
        started_at=plan.started_at,
        completed_at=completed_at,
        estimated_total_duration_seconds=plan.estimated_total_duration_seconds,
        automatic_execution=plan.automatic_execution
    )


def calculate_recovery_metrics(
    service_name: str,
    recovery_history: List[RecoveryPlan],
    current_uptime_seconds: int,
    health_check_results: List[HealthCheckResult]
) -> ServiceRecoveryMetrics:
    """
    Calculate recovery metrics for service.
    
    Args:
        service_name: Name of service
        recovery_history: List of past recovery plans
        current_uptime_seconds: Current uptime in seconds
        health_check_results: Recent health check results
        
    Returns:
        ServiceRecoveryMetrics summary
        
    MUST be deterministic.
    """
    total_attempts = len(recovery_history)
    successful_recoveries = sum(1 for plan in recovery_history 
                              if plan.overall_status == RecoveryStatus.COMPLETED)
    failed_recoveries = sum(1 for plan in recovery_history
                          if plan.overall_status == RecoveryStatus.FAILED)
    
    # Calculate average recovery time
    completed_recoveries = [plan for plan in recovery_history 
                          if plan.overall_status == RecoveryStatus.COMPLETED
                          and plan.started_at and plan.completed_at]
    
    if completed_recoveries:
        recovery_times = [
            (plan.completed_at - plan.started_at).total_seconds()
            for plan in completed_recoveries
        ]
        average_recovery_time = sum(recovery_times) / len(recovery_times)
    else:
        average_recovery_time = 0.0
        
    # Find last recovery time
    last_recovery_time = None
    if recovery_history:
        last_recovery = max(recovery_history, key=lambda x: x.created_at)
        if last_recovery.completed_at:
            last_recovery_time = last_recovery.completed_at
            
    # Calculate health check success rate
    if health_check_results:
        successful_checks = sum(1 for result in health_check_results if result.is_healthy)
        health_success_rate = successful_checks / len(health_check_results)
    else:
        health_success_rate = 0.0
    
    return ServiceRecoveryMetrics(
        service_name=service_name,
        total_recovery_attempts=total_attempts,
        successful_recoveries=successful_recoveries,
        failed_recoveries=failed_recoveries,
        average_recovery_time_seconds=average_recovery_time,
        last_recovery_time=last_recovery_time,
        current_uptime_seconds=current_uptime_seconds,
        health_check_success_rate=health_success_rate
    )


def should_trigger_recovery(
    health_results: List[HealthCheckResult],
    degraded_mode_active: bool,
    config: RecoveryConfig
) -> Tuple[bool, str]:
    """
    Determine if automatic recovery should be triggered.
    
    Args:
        health_results: Recent health check results
        degraded_mode_active: Whether degraded mode is currently active
        config: Recovery configuration
        
    Returns:
        Tuple of (should_trigger, reason)
        
    MUST be deterministic.
    """
    if not degraded_mode_active:
        return False, "System not in degraded mode"
        
    if not config.automatic_recovery_enabled:
        return False, "Automatic recovery disabled"
        
    if not health_results:
        return False, "No health check data available"
        
    # Check if service is healthy
    is_ready, confidence, reason = determine_recovery_readiness(
        "service", health_results, config
    )
    
    if not is_ready:
        return False, f"Service not ready: {reason}"
        
    return True, f"Service ready for recovery (confidence: {confidence:.1%})"