"""
Cost tracking core logic - Pure functions only.
NEVER include I/O operations in this module.
"""
from decimal import Decimal
from typing import Dict


# API cost matrix in EUR (exact values)
API_COSTS: Dict[str, Dict[str, Decimal]] = {
    "search": {
        "base": Decimal("0.001"),
        "pro": Decimal("0.005")
    },
    "task": {
        "base": Decimal("0.010"), 
        "core": Decimal("0.020"),
        "pro": Decimal("0.050")
    }
}

# Budget constants
MONTHLY_CAP_EUR = Decimal("1500.00")
KILL_SWITCH_THRESHOLD_PERCENT = Decimal("95")


def calculate_api_cost(
    api_type: str, 
    processor: str,
    request_size: int = 0
) -> Decimal:
    """
    Calculate cost for Parallel.ai API call.
    MUST be deterministic - same inputs always return same cost.
    
    Args:
        api_type: "search" or "task"
        processor: "base", "pro", "core" (task only)
        request_size: unused for now, reserved for future request-based pricing
        
    Returns:
        Cost in EUR as Decimal for accuracy
        
    Raises:
        ValueError: If api_type or processor combination is invalid
    """
    if api_type not in API_COSTS:
        raise ValueError(f"Invalid api_type: {api_type}. Must be 'search' or 'task'")
    
    if processor not in API_COSTS[api_type]:
        valid_processors = list(API_COSTS[api_type].keys())
        raise ValueError(f"Invalid processor '{processor}' for api_type '{api_type}'. Valid: {valid_processors}")
    
    return API_COSTS[api_type][processor]


def should_activate_kill_switch(
    current_spend: Decimal,
    proposed_cost: Decimal, 
    monthly_cap: Decimal = MONTHLY_CAP_EUR,
    threshold_percent: Decimal = KILL_SWITCH_THRESHOLD_PERCENT
) -> bool:
    """
    Determine if kill switch should activate based on spend + proposed cost.
    MUST be pure function - no side effects.
    
    Args:
        current_spend: Current monthly spend in EUR
        proposed_cost: Cost of proposed API call in EUR
        monthly_cap: Monthly budget cap in EUR
        threshold_percent: Threshold percentage (default 95%)
        
    Returns:
        True if kill switch should activate, False otherwise
    """
    if monthly_cap <= 0:
        raise ValueError("Monthly cap must be positive")
    if threshold_percent <= 0 or threshold_percent > 100:
        raise ValueError("Threshold percent must be between 0 and 100")
    
    threshold_amount = monthly_cap * (threshold_percent / Decimal("100"))
    projected_spend = current_spend + proposed_cost
    
    return projected_spend > threshold_amount


def calculate_budget_utilization(
    current_spend: Decimal,
    monthly_cap: Decimal = MONTHLY_CAP_EUR
) -> Decimal:
    """
    Calculate budget utilization as percentage.
    MUST be accurate to 0.001 EUR.
    
    Args:
        current_spend: Current monthly spend in EUR
        monthly_cap: Monthly budget cap in EUR
        
    Returns:
        Utilization percentage (0.0 to 100.0+)
    """
    if monthly_cap <= 0:
        raise ValueError("Monthly cap must be positive")
    
    utilization = (current_spend / monthly_cap) * Decimal("100")
    
    # Round to 3 decimal places for 0.001 EUR accuracy
    return utilization.quantize(Decimal("0.001"))


def get_threshold_amount(
    threshold_percent: Decimal,
    monthly_cap: Decimal = MONTHLY_CAP_EUR
) -> Decimal:
    """
    Calculate threshold amount in EUR for given percentage.
    
    Args:
        threshold_percent: Threshold percentage (e.g. 95 for 95%)
        monthly_cap: Monthly budget cap in EUR
        
    Returns:
        Threshold amount in EUR
    """
    if monthly_cap <= 0:
        raise ValueError("Monthly cap must be positive")
    if threshold_percent <= 0 or threshold_percent > 100:
        raise ValueError("Threshold percent must be between 0 and 100")
        
    return (monthly_cap * threshold_percent / Decimal("100")).quantize(Decimal("0.01"))


def get_budget_status(current_spend: Decimal) -> str:
    """
    Get budget status based on current spend.
    
    Args:
        current_spend: Current monthly spend in EUR
        
    Returns:
        Status string: "normal", "warning", "alert", "escalation", "kill_switch"
    """
    utilization = calculate_budget_utilization(current_spend)
    
    if utilization >= KILL_SWITCH_THRESHOLD_PERCENT:
        return "kill_switch"
    elif utilization >= Decimal("90"):
        return "escalation"
    elif utilization >= Decimal("80"):
        return "alert"
    elif utilization >= Decimal("50"):
        return "warning"
    else:
        return "normal"