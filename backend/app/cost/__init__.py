"""
Cost tracking module with €1,500 budget enforcement and 95% kill switch.

This module provides:
- Redis-based real-time spend tracking
- Pre-flight cost validation (<10ms)
- Automatic kill switch at 95% threshold (€1,425)
- Audit trail with 0.001 EUR accuracy
"""

from .core import (
    calculate_api_cost,
    should_activate_kill_switch,
    calculate_budget_utilization,
    get_budget_status,
    get_threshold_amount,
    MONTHLY_CAP_EUR,
    KILL_SWITCH_THRESHOLD_PERCENT,
)
from .contracts import (
    CostEntry,
    BudgetState,
    PreFlightCheck,
    BudgetStatus,
    BudgetAlert,
    SpendLimits,
)
from .events import (
    BudgetThresholdExceeded,
    KillSwitchActivated,
    CostRecorded,
    BudgetReset,
    KillSwitchOverridden,
)
from .shell import CostTracker, reset_monthly_budget, manual_kill_switch_override

__all__ = [
    # Core functions
    "calculate_api_cost",
    "should_activate_kill_switch",
    "calculate_budget_utilization",
    "get_budget_status",
    "get_threshold_amount",
    "MONTHLY_CAP_EUR",
    "KILL_SWITCH_THRESHOLD_PERCENT",
    # Contracts
    "CostEntry",
    "BudgetState",
    "PreFlightCheck",
    "BudgetStatus",
    "BudgetAlert",
    "SpendLimits",
    # Events
    "BudgetThresholdExceeded",
    "KillSwitchActivated",
    "CostRecorded",
    "BudgetReset",
    "KillSwitchOverridden",
    # Shell operations
    "CostTracker",
    "reset_monthly_budget",
    "manual_kill_switch_override",
]
