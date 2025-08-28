"""
Cost tracking domain events.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from .contracts import BudgetStatus


@dataclass(frozen=True)
class BudgetThresholdExceeded:
    """Emitted when budget threshold is crossed."""
    tenant: str
    threshold_percent: Decimal
    current_spend_eur: Decimal
    utilization_percent: Decimal
    previous_status: BudgetStatus
    new_status: BudgetStatus
    timestamp: datetime
    
    
@dataclass(frozen=True)
class KillSwitchActivated:
    """Emitted when kill switch is activated."""
    tenant: str
    current_spend_eur: Decimal
    proposed_cost_eur: Decimal
    utilization_percent: Decimal
    kill_switch_threshold_percent: Decimal
    timestamp: datetime
    blocked_request_id: Optional[str] = None
    

@dataclass(frozen=True)
class CostRecorded:
    """Emitted when API cost is recorded."""
    tenant: str
    api_type: str
    processor: str
    cost_eur: Decimal
    use_case: str
    new_total_spend: Decimal
    utilization_percent: Decimal
    timestamp: datetime
    request_id: Optional[str] = None


@dataclass(frozen=True)
class BudgetReset:
    """Emitted when monthly budget is reset."""
    tenant: str
    previous_spend_eur: Decimal
    reset_timestamp: datetime
    new_month: str  # YYYY-MM format


@dataclass(frozen=True)
class KillSwitchOverridden:
    """Emitted when kill switch is manually overridden."""
    tenant: str
    overridden_by: str  # user ID
    reason: str
    current_spend_eur: Decimal
    override_timestamp: datetime
    approval_level: str  # "c_level", "emergency"
    metadata: Optional[Dict[str, Any]] = None