"""
Operation Queueing System - Type Definitions and Contracts

Defines types for queueing operations during degraded mode and replaying them during recovery.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Protocol
from enum import Enum
from datetime import datetime


class OperationStatus(Enum):
    """Status of queued operation."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class OperationType(Enum):
    """Types of operations that can be queued."""
    PARALLEL_SEARCH = "parallel_search"
    PARALLEL_TASK = "parallel_task"
    REGULATORY_SCAN = "regulatory_scan"
    OBLIGATION_MAPPING = "obligation_mapping"
    INCIDENT_CLASSIFICATION = "incident_classification"
    DIGEST_GENERATION = "digest_generation"
    CUSTOM = "custom"


class QueuePriority(Enum):
    """Priority levels for queued operations."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
    CRITICAL = 5


@dataclass(frozen=True)
class QueuedOperation:
    """Represents an operation queued for later execution."""
    
    operation_id: str
    operation_type: OperationType
    priority: QueuePriority
    queued_at: datetime
    expires_at: Optional[datetime]
    
    # Operation parameters
    endpoint: str
    payload: Dict[str, Any]
    headers: Optional[Dict[str, str]] = None
    timeout_seconds: int = 30
    
    # Retry configuration
    max_retries: int = 3
    retry_count: int = 0
    retry_delay_seconds: int = 60
    
    # Status tracking
    status: OperationStatus = OperationStatus.QUEUED
    queued_by_user: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    # Result tracking
    result: Optional[Any] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    

@dataclass(frozen=True)
class QueueConfig:
    """Configuration for operation queue behavior."""
    
    max_queue_size: int = 10000
    default_ttl_hours: int = 24
    max_retry_attempts: int = 3
    retry_exponential_backoff: bool = True
    max_retry_delay_seconds: int = 3600  # 1 hour
    
    # Priority settings
    priority_queue_enabled: bool = True
    high_priority_threshold: int = 100  # Max high priority items
    
    # Batch processing
    batch_size: int = 50
    batch_timeout_seconds: int = 300  # 5 minutes
    
    # Storage settings
    persistent_storage: bool = True
    compression_enabled: bool = True


@dataclass(frozen=True)
class QueueMetrics:
    """Metrics for queue performance and status."""
    
    total_operations: int
    queued_operations: int
    in_progress_operations: int
    completed_operations: int
    failed_operations: int
    expired_operations: int
    
    operations_by_type: Dict[OperationType, int]
    operations_by_priority: Dict[QueuePriority, int]
    
    average_queue_time_seconds: float
    average_execution_time_seconds: float
    success_rate: float
    
    oldest_queued_operation: Optional[datetime]
    queue_size_bytes: int
    

@dataclass(frozen=True)
class BatchExecutionRequest:
    """Request to execute a batch of queued operations."""
    
    batch_id: str
    operations: List[QueuedOperation]
    requested_at: datetime
    priority_override: Optional[QueuePriority] = None
    timeout_override_seconds: Optional[int] = None
    

@dataclass(frozen=True)
class BatchExecutionResult:
    """Result of batch operation execution."""
    
    batch_id: str
    executed_at: datetime
    total_operations: int
    successful_operations: int
    failed_operations: int
    execution_time_seconds: int
    
    operation_results: Dict[str, Any]  # operation_id -> result
    errors: Dict[str, str]  # operation_id -> error_message
    

class OperationQueue(Protocol):
    """Protocol for operation queue implementations."""
    
    async def enqueue(self, operation: QueuedOperation) -> bool:
        """Add operation to queue."""
        ...
        
    async def dequeue(
        self, 
        limit: int = 1,
        operation_types: Optional[List[OperationType]] = None
    ) -> List[QueuedOperation]:
        """Get operations from queue for execution."""
        ...
        
    async def get_status(self, operation_id: str) -> Optional[QueuedOperation]:
        """Get status of queued operation."""
        ...
        
    async def cancel(self, operation_id: str) -> bool:
        """Cancel queued operation."""
        ...
        
    async def get_metrics(self) -> QueueMetrics:
        """Get queue performance metrics."""
        ...


class OperationExecutor(Protocol):
    """Protocol for executing queued operations."""
    
    async def execute(self, operation: QueuedOperation) -> Any:
        """Execute queued operation."""
        ...
        
    async def execute_batch(
        self, 
        operations: List[QueuedOperation]
    ) -> BatchExecutionResult:
        """Execute batch of operations."""
        ...
        
    def can_execute(self, operation_type: OperationType) -> bool:
        """Check if executor can handle operation type."""
        ...


@dataclass(frozen=True)
class QueueReplayConfig:
    """Configuration for queue replay during recovery."""
    
    replay_enabled: bool = True
    replay_batch_size: int = 25
    replay_delay_seconds: int = 1  # Delay between batches
    
    # Filtering
    max_age_hours: int = 24  # Don't replay operations older than this
    priority_threshold: QueuePriority = QueuePriority.NORMAL
    
    # Safety limits
    max_operations_per_replay: int = 1000
    timeout_per_batch_seconds: int = 300
    

@dataclass(frozen=True)
class ReplaySession:
    """Information about a queue replay session."""
    
    session_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    
    total_operations_selected: int
    operations_executed: int
    operations_succeeded: int
    operations_failed: int
    operations_skipped: int
    
    replay_config: QueueReplayConfig
    trigger_reason: str  # "service_recovery", "manual", "scheduled"
    
    
@dataclass(frozen=True)
class OperationDependency:
    """Represents dependency between queued operations."""
    
    dependent_operation_id: str
    depends_on_operation_id: str
    dependency_type: str  # "prerequisite", "blocking", "ordering"
    created_at: datetime