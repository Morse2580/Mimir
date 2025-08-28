"""
Operation Queueing System - Core Functions

Pure functions for queue management, operation prioritization, and replay logic.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from .contracts import (
    QueuedOperation,
    OperationType,
    OperationStatus,
    QueuePriority,
    QueueConfig,
    QueueMetrics,
    BatchExecutionResult,
    QueueReplayConfig,
    ReplaySession,
    OperationDependency
)


def calculate_operation_priority_score(
    operation: QueuedOperation,
    current_time: datetime,
    degraded_mode_active: bool = True
) -> float:
    """
    Calculate priority score for operation scheduling (higher = more urgent).
    
    Args:
        operation: Queued operation to score
        current_time: Current timestamp
        degraded_mode_active: Whether system is in degraded mode
        
    Returns:
        Priority score for scheduling
        
    MUST be deterministic.
    """
    base_score = operation.priority.value * 100  # Base priority (100-500)
    
    # Age factor - older operations get higher priority
    age_hours = (current_time - operation.queued_at).total_seconds() / 3600
    age_bonus = min(200, age_hours * 10)  # Up to 200 points for age
    
    # Expiration urgency
    expiration_bonus = 0
    if operation.expires_at:
        time_to_expiry = (operation.expires_at - current_time).total_seconds() / 3600
        if time_to_expiry < 1:  # Less than 1 hour to expiry
            expiration_bonus = 300  # High urgency
        elif time_to_expiry < 6:  # Less than 6 hours
            expiration_bonus = 100
        elif time_to_expiry < 24:  # Less than 24 hours
            expiration_bonus = 50
            
    # Operation type importance during degraded mode
    type_bonus = 0
    if degraded_mode_active:
        critical_types = {
            OperationType.PARALLEL_SEARCH: 50,
            OperationType.PARALLEL_TASK: 75,
            OperationType.REGULATORY_SCAN: 25,
            OperationType.INCIDENT_CLASSIFICATION: 100,
            OperationType.DIGEST_GENERATION: 30
        }
        type_bonus = critical_types.get(operation.operation_type, 10)
    
    # Retry penalty - operations that have failed before get lower priority
    retry_penalty = operation.retry_count * 25
    
    total_score = base_score + age_bonus + expiration_bonus + type_bonus - retry_penalty
    return max(0, total_score)


def sort_operations_by_priority(
    operations: List[QueuedOperation],
    current_time: datetime,
    degraded_mode_active: bool = True
) -> List[QueuedOperation]:
    """
    Sort operations by calculated priority score.
    
    Args:
        operations: List of operations to sort
        current_time: Current timestamp
        degraded_mode_active: Whether in degraded mode
        
    Returns:
        Operations sorted by priority (highest first)
        
    MUST be deterministic.
    """
    if not operations:
        return []
        
    # Calculate priority scores
    scored_operations = []
    for op in operations:
        score = calculate_operation_priority_score(op, current_time, degraded_mode_active)
        scored_operations.append((score, op))
        
    # Sort by score (highest first), then by queue time (older first)
    scored_operations.sort(
        key=lambda x: (x[0], -x[1].queued_at.timestamp()),
        reverse=True
    )
    
    return [op for score, op in scored_operations]


def filter_executable_operations(
    operations: List[QueuedOperation],
    current_time: datetime,
    max_age_hours: int = 24,
    exclude_statuses: List[OperationStatus] = None
) -> List[QueuedOperation]:
    """
    Filter operations that are ready for execution.
    
    Args:
        operations: Operations to filter
        current_time: Current timestamp
        max_age_hours: Maximum age for operations
        exclude_statuses: Statuses to exclude
        
    Returns:
        Filtered list of executable operations
        
    MUST be deterministic.
    """
    if exclude_statuses is None:
        exclude_statuses = [
            OperationStatus.COMPLETED,
            OperationStatus.CANCELLED,
            OperationStatus.EXPIRED,
            OperationStatus.IN_PROGRESS
        ]
    
    executable = []
    cutoff_time = current_time - timedelta(hours=max_age_hours)
    
    for op in operations:
        # Skip excluded statuses
        if op.status in exclude_statuses:
            continue
            
        # Skip expired operations
        if op.expires_at and current_time >= op.expires_at:
            continue
            
        # Skip operations that are too old
        if op.queued_at < cutoff_time:
            continue
            
        executable.append(op)
    
    return executable


def create_execution_batches(
    operations: List[QueuedOperation],
    batch_size: int = 50,
    group_by_type: bool = True
) -> List[List[QueuedOperation]]:
    """
    Create execution batches from operations list.
    
    Args:
        operations: Operations to batch
        batch_size: Maximum operations per batch
        group_by_type: Whether to group operations by type
        
    Returns:
        List of operation batches
        
    MUST be deterministic.
    """
    if not operations:
        return []
        
    if not group_by_type:
        # Simple batching by size
        batches = []
        for i in range(0, len(operations), batch_size):
            batch = operations[i:i + batch_size]
            batches.append(batch)
        return batches
    
    # Group by operation type first
    type_groups = {}
    for op in operations:
        op_type = op.operation_type
        if op_type not in type_groups:
            type_groups[op_type] = []
        type_groups[op_type].append(op)
    
    # Create batches within each type group
    batches = []
    for op_type, ops in type_groups.items():
        for i in range(0, len(ops), batch_size):
            batch = ops[i:i + batch_size]
            batches.append(batch)
    
    return batches


def calculate_retry_delay(
    operation: QueuedOperation,
    exponential_backoff: bool = True,
    base_delay_seconds: int = 60,
    max_delay_seconds: int = 3600
) -> int:
    """
    Calculate delay before retrying failed operation.
    
    Args:
        operation: Operation that failed
        exponential_backoff: Whether to use exponential backoff
        base_delay_seconds: Base delay for first retry
        max_delay_seconds: Maximum delay allowed
        
    Returns:
        Delay in seconds before retry
        
    MUST be deterministic.
    """
    if not exponential_backoff:
        return min(operation.retry_delay_seconds, max_delay_seconds)
    
    # Exponential backoff: base * 2^retry_count
    delay = base_delay_seconds * (2 ** operation.retry_count)
    return min(delay, max_delay_seconds)


def should_retry_operation(
    operation: QueuedOperation,
    error_message: str,
    current_time: datetime
) -> Tuple[bool, str]:
    """
    Determine if failed operation should be retried.
    
    Args:
        operation: Operation that failed
        error_message: Error message from failure
        current_time: Current timestamp
        
    Returns:
        Tuple of (should_retry, reason)
        
    MUST be deterministic.
    """
    if operation.retry_count >= operation.max_retries:
        return False, f"Maximum retries exceeded ({operation.max_retries})"
        
    if operation.expires_at and current_time >= operation.expires_at:
        return False, "Operation expired"
    
    # Check for non-retryable errors
    non_retryable_errors = [
        "pii boundary violation",
        "invalid payload format",
        "authentication failed",
        "operation cancelled",
        "malformed request"
    ]
    
    error_lower = error_message.lower()
    for non_retryable in non_retryable_errors:
        if non_retryable in error_lower:
            return False, f"Non-retryable error: {non_retryable}"
    
    # Retryable network/service errors
    retryable_errors = [
        "connection timeout",
        "connection refused", 
        "service unavailable",
        "circuit breaker open",
        "rate limit exceeded",
        "temporary failure"
    ]
    
    for retryable in retryable_errors:
        if retryable in error_lower:
            return True, f"Retryable error: {retryable}"
    
    # Default to retry for most errors
    return True, "General failure - retry allowed"


def update_operation_status(
    operation: QueuedOperation,
    new_status: OperationStatus,
    current_time: datetime,
    result: Any = None,
    error_message: str = None
) -> QueuedOperation:
    """
    Create updated operation with new status.
    
    Args:
        operation: Original operation
        new_status: New status to set
        current_time: Current timestamp
        result: Operation result if successful
        error_message: Error message if failed
        
    Returns:
        Updated operation
        
    MUST be deterministic.
    """
    started_at = operation.started_at
    completed_at = operation.completed_at
    retry_count = operation.retry_count
    
    if new_status == OperationStatus.IN_PROGRESS and not started_at:
        started_at = current_time
    elif new_status in [OperationStatus.COMPLETED, OperationStatus.FAILED]:
        if not completed_at:
            completed_at = current_time
        if new_status == OperationStatus.FAILED:
            retry_count += 1
    
    return QueuedOperation(
        operation_id=operation.operation_id,
        operation_type=operation.operation_type,
        priority=operation.priority,
        queued_at=operation.queued_at,
        expires_at=operation.expires_at,
        endpoint=operation.endpoint,
        payload=operation.payload,
        headers=operation.headers,
        timeout_seconds=operation.timeout_seconds,
        max_retries=operation.max_retries,
        retry_count=retry_count,
        retry_delay_seconds=operation.retry_delay_seconds,
        status=new_status,
        queued_by_user=operation.queued_by_user,
        context=operation.context,
        result=result,
        error_message=error_message,
        started_at=started_at,
        completed_at=completed_at
    )


def calculate_queue_metrics(
    operations: List[QueuedOperation],
    current_time: datetime
) -> QueueMetrics:
    """
    Calculate comprehensive queue metrics.
    
    Args:
        operations: All operations in queue
        current_time: Current timestamp
        
    Returns:
        QueueMetrics summary
        
    MUST be deterministic.
    """
    if not operations:
        return QueueMetrics(
            total_operations=0,
            queued_operations=0,
            in_progress_operations=0,
            completed_operations=0,
            failed_operations=0,
            expired_operations=0,
            operations_by_type={},
            operations_by_priority={},
            average_queue_time_seconds=0.0,
            average_execution_time_seconds=0.0,
            success_rate=0.0,
            oldest_queued_operation=None,
            queue_size_bytes=0
        )
    
    # Count operations by status
    status_counts = {}
    for status in OperationStatus:
        status_counts[status] = 0
        
    for op in operations:
        status_counts[op.status] += 1
    
    # Count by type
    type_counts = {}
    for op_type in OperationType:
        type_counts[op_type] = 0
        
    for op in operations:
        type_counts[op.operation_type] += 1
    
    # Count by priority
    priority_counts = {}
    for priority in QueuePriority:
        priority_counts[priority] = 0
        
    for op in operations:
        priority_counts[op.priority] += 1
    
    # Calculate timing metrics
    queue_times = []
    execution_times = []
    
    for op in operations:
        if op.started_at:
            queue_time = (op.started_at - op.queued_at).total_seconds()
            queue_times.append(queue_time)
            
        if op.started_at and op.completed_at:
            execution_time = (op.completed_at - op.started_at).total_seconds()
            execution_times.append(execution_time)
    
    avg_queue_time = sum(queue_times) / len(queue_times) if queue_times else 0.0
    avg_execution_time = sum(execution_times) / len(execution_times) if execution_times else 0.0
    
    # Success rate
    completed = status_counts[OperationStatus.COMPLETED]
    failed = status_counts[OperationStatus.FAILED]
    total_finished = completed + failed
    success_rate = completed / total_finished if total_finished > 0 else 0.0
    
    # Find oldest queued operation
    queued_ops = [op for op in operations if op.status == OperationStatus.QUEUED]
    oldest_queued = None
    if queued_ops:
        oldest_queued = min(queued_ops, key=lambda x: x.queued_at).queued_at
    
    # Estimate queue size in bytes
    queue_size = 0
    for op in operations:
        op_size = len(json.dumps({
            'operation_id': op.operation_id,
            'payload': op.payload,
            'headers': op.headers or {},
            'context': op.context or {}
        }, default=str))
        queue_size += op_size
    
    return QueueMetrics(
        total_operations=len(operations),
        queued_operations=status_counts[OperationStatus.QUEUED],
        in_progress_operations=status_counts[OperationStatus.IN_PROGRESS],
        completed_operations=status_counts[OperationStatus.COMPLETED],
        failed_operations=status_counts[OperationStatus.FAILED],
        expired_operations=status_counts[OperationStatus.EXPIRED],
        operations_by_type=type_counts,
        operations_by_priority=priority_counts,
        average_queue_time_seconds=avg_queue_time,
        average_execution_time_seconds=avg_execution_time,
        success_rate=success_rate,
        oldest_queued_operation=oldest_queued,
        queue_size_bytes=queue_size
    )


def generate_operation_id(
    operation_type: OperationType,
    endpoint: str,
    payload_hash: str,
    timestamp: datetime
) -> str:
    """
    Generate deterministic operation ID.
    
    Args:
        operation_type: Type of operation
        endpoint: Target endpoint
        payload_hash: Hash of payload
        timestamp: Queue timestamp
        
    Returns:
        Unique operation ID
        
    MUST be deterministic.
    """
    components = [
        operation_type.value,
        endpoint,
        payload_hash,
        timestamp.isoformat()
    ]
    
    combined = "|".join(components)
    hash_digest = hashlib.sha256(combined.encode()).hexdigest()[:12]
    
    return f"{operation_type.value}_{hash_digest}"


def calculate_payload_hash(payload: Dict[str, Any]) -> str:
    """
    Calculate deterministic hash of operation payload.
    
    Args:
        payload: Operation payload to hash
        
    Returns:
        SHA-256 hash of payload
        
    MUST be deterministic.
    """
    # Sort keys for deterministic serialization
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload_json.encode()).hexdigest()[:16]


def resolve_operation_dependencies(
    operations: List[QueuedOperation],
    dependencies: List[OperationDependency]
) -> List[QueuedOperation]:
    """
    Resolve operation dependencies and return executable operations.
    
    Args:
        operations: List of operations
        dependencies: List of operation dependencies
        
    Returns:
        Operations that can be executed (dependencies satisfied)
        
    MUST be deterministic.
    """
    if not dependencies:
        return operations
        
    # Build dependency map
    dependency_map = {}
    for dep in dependencies:
        dependent_id = dep.dependent_operation_id
        if dependent_id not in dependency_map:
            dependency_map[dependent_id] = []
        dependency_map[dependent_id].append(dep.depends_on_operation_id)
    
    # Find completed operations
    completed_ops = {op.operation_id for op in operations 
                    if op.status == OperationStatus.COMPLETED}
    
    # Filter operations that have all dependencies satisfied
    executable = []
    for op in operations:
        if op.status != OperationStatus.QUEUED:
            continue
            
        op_dependencies = dependency_map.get(op.operation_id, [])
        
        # Check if all dependencies are completed
        dependencies_satisfied = all(
            dep_id in completed_ops for dep_id in op_dependencies
        )
        
        if dependencies_satisfied:
            executable.append(op)
    
    return executable