"""
Cost tracking contracts and type definitions.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any
from enum import Enum


class BudgetStatus(Enum):
    """Budget status levels."""
    NORMAL = "normal"
    WARNING = "warning"  # 50%
    ALERT = "alert"      # 80%
    ESCALATION = "escalation"  # 90%
    KILL_SWITCH = "kill_switch"  # 95%


@dataclass(frozen=True)
class SpendLimits:
    """Budget spend limits configuration."""
    monthly_cap_eur: Decimal
    kill_switch_threshold_percent: Decimal
    warning_threshold_percent: Decimal = Decimal("50")
    alert_threshold_percent: Decimal = Decimal("80")
    escalation_threshold_percent: Decimal = Decimal("90")


@dataclass(frozen=True)
class CostEntry:
    """Record of API cost incurred."""
    id: Optional[str]
    tenant: str
    api_type: str  # "search" or "task"
    processor: str  # "base", "pro", "core"
    cost_eur: Decimal
    use_case: str
    timestamp: datetime
    request_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class BudgetState:
    """Current budget state."""
    tenant: str
    current_spend_eur: Decimal
    monthly_cap_eur: Decimal
    utilization_percent: Decimal
    status: BudgetStatus
    kill_switch_active: bool
    last_updated: datetime


@dataclass(frozen=True)
class PreFlightCheck:
    """Result of pre-flight budget check."""
    allowed: bool
    current_spend_eur: Decimal
    proposed_cost_eur: Decimal
    projected_spend_eur: Decimal
    utilization_after_percent: Decimal
    kill_switch_would_activate: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class BudgetAlert:
    """Budget alert information."""
    tenant: str
    threshold_percent: Decimal
    current_spend_eur: Decimal
    utilization_percent: Decimal
    status: BudgetStatus
    timestamp: datetime
    alert_level: str  # "email", "teams", "escalation", "kill_switch"