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