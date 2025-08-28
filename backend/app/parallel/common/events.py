"""
PII Boundary Guard - Domain Events

This module defines domain events emitted by the PII boundary guard
when violations are detected or circuit breaker state changes.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
from .contracts import PIIViolationType, CircuitBreakerState


@dataclass(frozen=True)
class PIIViolationDetected:
    """
    Event emitted when PII is detected in data bound for external APIs.
    
    This is a critical security event that should trigger alerts
    and be logged in the audit trail.
    """
    event_id: str
    timestamp: datetime
    violation_type: PIIViolationType
    detected_patterns: List[str]
    risk_score: float
    payload_size: int
    source_endpoint: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate event data on creation."""
        if self.risk_score < 0.0 or self.risk_score > 1.0:
            raise ValueError("Risk score must be between 0.0 and 1.0")
        if self.payload_size < 0:
            raise ValueError("Payload size cannot be negative")


@dataclass(frozen=True)
class CircuitBreakerOpened:
    """
    Event emitted when circuit breaker opens due to failures.
    
    Indicates that external API calls are being blocked and
    the system has entered degraded mode.
    """
    event_id: str
    timestamp: datetime
    service_name: str
    failure_count: int
    failure_threshold: int
    last_error: Optional[str] = None
    recovery_time: Optional[datetime] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CircuitBreakerClosed:
    """
    Event emitted when circuit breaker closes after recovery.
    
    Indicates that the service has recovered and external API
    calls are functioning normally again.
    """
    event_id: str
    timestamp: datetime
    service_name: str
    downtime_duration_seconds: int
    recovery_attempts: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CircuitBreakerHalfOpen:
    """
    Event emitted when circuit breaker enters half-open state.
    
    Indicates that the system is testing if the external service
    has recovered by allowing limited requests through.
    """
    event_id: str
    timestamp: datetime
    service_name: str
    test_requests_allowed: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class PIIBoundaryBypass:
    """
    Event emitted when there's an attempt to bypass PII boundary checks.
    
    This is a critical security event that indicates potential
    malicious activity or system compromise.
    """
    event_id: str
    timestamp: datetime
    attempted_bypass_method: str
    source_ip: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    stack_trace: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class CostLimitApproached:
    """
    Event emitted when Parallel.ai API costs approach the monthly limit.
    
    This allows for proactive cost management and prevents
    unexpected service shutdowns.
    """
    event_id: str
    timestamp: datetime
    current_cost_euros: float
    monthly_limit_euros: float
    percentage_used: float
    estimated_days_remaining: int
    context: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate cost data on creation."""
        if self.current_cost_euros < 0:
            raise ValueError("Current cost cannot be negative")
        if self.monthly_limit_euros <= 0:
            raise ValueError("Monthly limit must be positive")
        if self.percentage_used < 0 or self.percentage_used > 100:
            raise ValueError("Percentage used must be between 0 and 100")


@dataclass(frozen=True)
class ParallelCallCompleted:
    """
    Event emitted when a Parallel.ai API call completes successfully.
    
    Used for tracking usage metrics and cost monitoring.
    """
    event_id: str
    timestamp: datetime
    endpoint: str
    response_time_ms: int
    cost_euros: float
    payload_size_bytes: int
    response_size_bytes: int
    context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ParallelCallFailed:
    """
    Event emitted when a Parallel.ai API call fails.
    
    Used for circuit breaker logic and error monitoring.
    """
    event_id: str
    timestamp: datetime
    endpoint: str
    error_type: str
    error_message: str
    status_code: Optional[int] = None
    retry_count: int = 0
    will_retry: bool = False
    context: Optional[Dict[str, Any]] = None