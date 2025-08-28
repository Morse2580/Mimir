"""
PII Boundary Guard - Type Definitions and Contracts

This module defines the types and interfaces used by the PII boundary guard.
"""

from dataclasses import dataclass
from typing import List, Optional, Protocol, Any
from enum import Enum
from datetime import datetime


class CircuitBreakerState(Enum):
    """Circuit breaker state enumeration."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    DEGRADED = "degraded"  # New state for degraded mode operations


class PIIViolationType(Enum):
    """Types of PII violations detected."""

    BELGIAN_RRN = "belgian_rrn"
    BELGIAN_VAT = "belgian_vat"
    IBAN = "iban"
    EMAIL = "email"
    PHONE = "phone"
    IP_ADDRESS = "ip_address"
    CREDIT_CARD = "credit_card"


@dataclass(frozen=True)
class PIIBoundaryViolation:
    """
    Represents a PII boundary violation.

    This is raised when PII is detected in data that would be sent
    to external APIs like Parallel.ai.
    """

    violation_type: PIIViolationType
    detected_patterns: List[str]
    risk_score: float
    payload_size: int
    timestamp: datetime
    context: Optional[str] = None


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 3
    recovery_timeout_seconds: int = 600  # 10 minutes
    half_open_max_calls: int = 5
    redis_key_prefix: str = "circuit_breaker"


@dataclass(frozen=True)
class CircuitBreakerStatus:
    """Current status of the circuit breaker."""

    state: CircuitBreakerState
    failure_count: int
    last_failure_time: Optional[datetime]
    next_attempt_time: Optional[datetime]
    total_requests: int
    successful_requests: int
    failed_requests: int
    degraded_mode_active: bool = False
    fallback_systems_active: List[str] = None
    estimated_recovery_time: Optional[datetime] = None
    
    def __post_init__(self):
        """Set default empty list for fallback systems."""
        if self.fallback_systems_active is None:
            object.__setattr__(self, 'fallback_systems_active', [])


class PIIDetector(Protocol):
    """Protocol for PII detection implementations."""

    def contains_pii(self, text: str) -> tuple[bool, List[Any]]:
        """Detect PII patterns in text."""
        ...

    def calculate_risk_score(self, data: dict) -> float:
        """Calculate risk score for data payload."""
        ...


class CircuitBreaker(Protocol):
    """Protocol for circuit breaker implementations."""

    async def call(self, func, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        ...

    async def get_status(self) -> CircuitBreakerStatus:
        """Get current circuit breaker status."""
        ...

    async def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        ...


@dataclass(frozen=True)
class ParallelCallRequest:
    """Request to make a call to Parallel.ai API."""

    endpoint: str
    payload: dict
    timeout_seconds: int = 30
    retry_count: int = 0
    context: Optional[str] = None


@dataclass(frozen=True)
class ParallelCallResponse:
    """Response from Parallel.ai API call."""

    success: bool
    data: Optional[dict] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    response_time_ms: int = 0
    cost_euros: float = 0.0


@dataclass(frozen=True)
class PIIGuardMetrics:
    """Metrics for PII boundary guard performance."""

    total_checks: int
    violations_blocked: int
    false_positives: int
    average_check_time_ms: float
    patterns_detected: dict[PIIViolationType, int]
    last_violation_time: Optional[datetime] = None


@dataclass(frozen=True)
class DegradedModeStatus:
    """Status information for degraded mode operations."""
    
    active: bool
    activated_at: Optional[datetime]
    trigger_reason: str
    active_fallbacks: List[str]
    estimated_coverage_percentage: float
    recovery_detection_active: bool
    automatic_recovery: bool = True
    manual_override: bool = False


@dataclass(frozen=True)
class ServiceHealthStatus:
    """Health status for external service monitoring."""
    
    service_name: str
    is_healthy: bool
    last_check_time: datetime
    response_time_ms: Optional[int]
    error_message: Optional[str] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    health_score: float = 1.0  # 0.0 to 1.0


@dataclass(frozen=True)
class DegradedModeConfig:
    """Configuration for degraded mode behavior."""
    
    auto_activation_enabled: bool = True
    fallback_activation_delay_seconds: int = 60
    recovery_check_interval_seconds: int = 300  # 5 minutes
    max_degraded_duration_hours: int = 24
    coverage_threshold_percentage: float = 0.6  # Minimum acceptable coverage
    health_check_timeout_seconds: int = 10
