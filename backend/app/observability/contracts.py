"""
Observability contracts and type definitions.
Defines all types used across the observability module.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Generic, Optional, TypeVar, Union


class MetricType(Enum):
    """Supported OpenTelemetry metric types."""
    COUNTER = "counter"
    GAUGE = "gauge" 
    HISTOGRAM = "histogram"


class Severity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertOperator(Enum):
    """Alert threshold operators."""
    GT = "greater_than"
    LT = "less_than"
    EQ = "equals"
    GTE = "greater_than_or_equal"
    LTE = "less_than_or_equal"


class CircuitBreakerState(Enum):
    """Circuit breaker states for monitoring."""
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


@dataclass(frozen=True)
class Metric:
    """
    Standardized metric structure for RegOps observability.
    """
    name: str
    value: float
    labels: Dict[str, str]
    metric_type: MetricType
    timestamp: datetime
    unit: Optional[str] = None


@dataclass(frozen=True)
class SLODefinition:
    """
    Service Level Objective definition.
    """
    name: str
    target_value: float
    time_window: timedelta
    operator: AlertOperator
    description: str


@dataclass(frozen=True)
class SLOStatus:
    """
    Current SLO compliance status.
    """
    definition: SLODefinition
    current_value: float
    compliance_percent: float
    is_violated: bool
    last_evaluation: datetime


@dataclass(frozen=True)
class AlertRule:
    """
    Alert rule configuration.
    """
    metric_name: str
    threshold: float
    operator: AlertOperator
    severity: Severity
    message_template: str
    time_window: Optional[timedelta] = None


@dataclass(frozen=True)
class Alert:
    """
    Triggered alert instance.
    """
    rule: AlertRule
    current_value: float
    message: str
    timestamp: datetime
    labels: Dict[str, str]


T = TypeVar('T')
E = TypeVar('E')


@dataclass(frozen=True)
class Success(Generic[T]):
    """Success result wrapper."""
    value: T


@dataclass(frozen=True) 
class Failure(Generic[E]):
    """Failure result wrapper."""
    error: E


Result = Union[Success[T], Failure[E]]


@dataclass(frozen=True)
class MetricValidationError:
    """Metric validation error details."""
    field: str
    message: str
    value: Optional[str] = None


@dataclass(frozen=True)
class DashboardConfig:
    """Dashboard configuration."""
    name: str
    title: str
    description: str
    refresh_interval: timedelta
    panels: list[str]


@dataclass(frozen=True)
class PerformanceTarget:
    """Performance SLO target definition."""
    operation: str
    target_ms: int
    percentile: int  # e.g., 95 for p95
    description: str