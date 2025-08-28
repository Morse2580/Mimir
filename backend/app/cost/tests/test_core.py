"""
Test cost tracking core logic - Pure function tests.
NO I/O operations, NO mocks needed.
"""
import pytest
from decimal import Decimal

from ..core import (
    calculate_api_cost,
    should_activate_kill_switch,
    calculate_budget_utilization,
    get_budget_status,
    get_threshold_amount,
    MONTHLY_CAP_EUR,
    KILL_SWITCH_THRESHOLD_PERCENT
)


class TestCalculateApiCost:
    """Test API cost calculations for all 5 API types."""
    
    def test_search_base_cost(self):
        cost = calculate_api_cost("search", "base")
        assert cost == Decimal("0.001")
    
    def test_search_pro_cost(self):
        cost = calculate_api_cost("search", "pro")
        assert cost == Decimal("0.005")
    
    def test_task_base_cost(self):
        cost = calculate_api_cost("task", "base")
        assert cost == Decimal("0.010")
    
    def test_task_core_cost(self):
        cost = calculate_api_cost("task", "core")
        assert cost == Decimal("0.020")
    
    def test_task_pro_cost(self):
        cost = calculate_api_cost("task", "pro")
        assert cost == Decimal("0.050")
    
    def test_invalid_api_type(self):
        with pytest.raises(ValueError, match="Invalid api_type: invalid"):
            calculate_api_cost("invalid", "base")
    
    def test_invalid_processor_for_search(self):
        with pytest.raises(ValueError, match="Invalid processor 'core' for api_type 'search'"):
            calculate_api_cost("search", "core")
    
    def test_invalid_processor_for_task(self):
        with pytest.raises(ValueError, match="Invalid processor 'invalid' for api_type 'task'"):
            calculate_api_cost("task", "invalid")
    
    def test_request_size_ignored(self):
        # request_size parameter should not affect cost (reserved for future)
        cost1 = calculate_api_cost("search", "pro", 100)
        cost2 = calculate_api_cost("search", "pro", 1000)
        assert cost1 == cost2 == Decimal("0.005")


class TestKillSwitchLogic:
    """Test kill switch activation logic."""
    
    def test_kill_switch_at_exactly_95_percent(self):
        """Current €1,400 + €50 call = €1,450 > €1,425 threshold = BLOCK"""
        current_spend = Decimal("1400.00")
        proposed_cost = Decimal("50.00")
        
        should_activate = should_activate_kill_switch(current_spend, proposed_cost)
        assert should_activate is True
    
    def test_kill_switch_under_95_percent(self):
        """Current €1,400 + €5 call = €1,405 < €1,425 threshold = ALLOW"""
        current_spend = Decimal("1400.00") 
        proposed_cost = Decimal("5.00")
        
        should_activate = should_activate_kill_switch(current_spend, proposed_cost)
        assert should_activate is False
    
    def test_kill_switch_at_threshold_boundary(self):
        """Test exactly at 95% threshold (€1,425)"""
        # €1,424.99 + €0.01 = €1,425.00 exactly at threshold = ALLOW
        current_spend = Decimal("1424.99")
        proposed_cost = Decimal("0.01")
        
        should_activate = should_activate_kill_switch(current_spend, proposed_cost)
        assert should_activate is False
        
        # €1,425.00 + €0.001 = €1,425.001 > threshold = BLOCK
        current_spend = Decimal("1425.00")
        proposed_cost = Decimal("0.001")
        
        should_activate = should_activate_kill_switch(current_spend, proposed_cost)
        assert should_activate is True
    
    def test_kill_switch_custom_threshold(self):
        """Test with custom threshold (80%)"""
        current_spend = Decimal("1000.00")
        proposed_cost = Decimal("300.00")  # Would put at €1,300 = 86.67%
        
        should_activate = should_activate_kill_switch(
            current_spend, 
            proposed_cost,
            threshold_percent=Decimal("80")
        )
        assert should_activate is True
    
    def test_kill_switch_custom_monthly_cap(self):
        """Test with custom monthly cap"""
        current_spend = Decimal("900.00")
        proposed_cost = Decimal("100.00")  # Would put at €1,000
        monthly_cap = Decimal("1000.00")
        
        # 95% of €1,000 = €950, so €1,000 > €950 = BLOCK
        should_activate = should_activate_kill_switch(
            current_spend,
            proposed_cost, 
            monthly_cap=monthly_cap
        )
        assert should_activate is True
    
    def test_kill_switch_zero_current_spend(self):
        """Test with zero current spend"""
        should_activate = should_activate_kill_switch(
            Decimal("0.00"),
            Decimal("1500.00")  # Exactly at cap
        )
        assert should_activate is True  # 100% > 95%
    
    def test_kill_switch_invalid_monthly_cap(self):
        """Test with invalid monthly cap"""
        with pytest.raises(ValueError, match="Monthly cap must be positive"):
            should_activate_kill_switch(
                Decimal("100.00"),
                Decimal("10.00"),
                monthly_cap=Decimal("0.00")
            )
    
    def test_kill_switch_invalid_threshold_percent(self):
        """Test with invalid threshold percentage"""
        with pytest.raises(ValueError, match="Threshold percent must be between 0 and 100"):
            should_activate_kill_switch(
                Decimal("100.00"),
                Decimal("10.00"),
                threshold_percent=Decimal("101")
            )


class TestBudgetUtilization:
    """Test budget utilization calculations with 0.001 EUR accuracy."""
    
    def test_zero_utilization(self):
        utilization = calculate_budget_utilization(Decimal("0.00"))
        assert utilization == Decimal("0.000")
    
    def test_50_percent_utilization(self):
        utilization = calculate_budget_utilization(Decimal("750.00"))
        assert utilization == Decimal("50.000")
    
    def test_95_percent_utilization(self):
        utilization = calculate_budget_utilization(Decimal("1425.00"))
        assert utilization == Decimal("95.000")
    
    def test_100_percent_utilization(self):
        utilization = calculate_budget_utilization(Decimal("1500.00"))
        assert utilization == Decimal("100.000")
    
    def test_over_100_percent_utilization(self):
        utilization = calculate_budget_utilization(Decimal("1600.00"))
        assert utilization == Decimal("106.667")  # Rounded to 3 decimals
    
    def test_accuracy_to_001_eur(self):
        """Test accuracy to 0.001 EUR as required"""
        # €1,500.001 should be 100.000067% but rounded to 100.000%
        utilization = calculate_budget_utilization(Decimal("1500.001"))
        assert utilization == Decimal("100.000")
        
        # €750.0005 should be exactly 50.000%
        utilization = calculate_budget_utilization(Decimal("750.0005"))
        assert utilization == Decimal("50.000")
    
    def test_custom_monthly_cap(self):
        utilization = calculate_budget_utilization(
            Decimal("500.00"),
            monthly_cap=Decimal("1000.00")
        )
        assert utilization == Decimal("50.000")
    
    def test_invalid_monthly_cap(self):
        with pytest.raises(ValueError, match="Monthly cap must be positive"):
            calculate_budget_utilization(
                Decimal("100.00"),
                monthly_cap=Decimal("0.00")
            )


class TestBudgetStatus:
    """Test budget status determination."""
    
    def test_normal_status(self):
        # Under 50% = normal
        status = get_budget_status(Decimal("700.00"))  # 46.67%
        assert status == "normal"
    
    def test_warning_status(self):
        # 50% threshold = warning
        status = get_budget_status(Decimal("750.00"))  # 50.00%
        assert status == "warning"
        
        status = get_budget_status(Decimal("1000.00"))  # 66.67%
        assert status == "warning"
    
    def test_alert_status(self):
        # 80% threshold = alert
        status = get_budget_status(Decimal("1200.00"))  # 80.00%
        assert status == "alert"
        
        status = get_budget_status(Decimal("1300.00"))  # 86.67%
        assert status == "alert"
    
    def test_escalation_status(self):
        # 90% threshold = escalation
        status = get_budget_status(Decimal("1350.00"))  # 90.00%
        assert status == "escalation"
        
        status = get_budget_status(Decimal("1400.00"))  # 93.33%
        assert status == "escalation"
    
    def test_kill_switch_status(self):
        # 95% threshold = kill_switch
        status = get_budget_status(Decimal("1425.00"))  # 95.00%
        assert status == "kill_switch"
        
        status = get_budget_status(Decimal("1500.00"))  # 100.00%
        assert status == "kill_switch"
        
        status = get_budget_status(Decimal("2000.00"))  # 133.33%
        assert status == "kill_switch"


class TestThresholdCalculations:
    """Test threshold amount calculations."""
    
    def test_95_percent_threshold(self):
        amount = get_threshold_amount(Decimal("95"))
        assert amount == Decimal("1425.00")
    
    def test_50_percent_threshold(self):
        amount = get_threshold_amount(Decimal("50"))
        assert amount == Decimal("750.00")
    
    def test_80_percent_threshold(self):
        amount = get_threshold_amount(Decimal("80"))
        assert amount == Decimal("1200.00")
    
    def test_custom_monthly_cap(self):
        amount = get_threshold_amount(
            Decimal("90"),
            monthly_cap=Decimal("1000.00")
        )
        assert amount == Decimal("900.00")
    
    def test_invalid_threshold_percent(self):
        with pytest.raises(ValueError, match="Threshold percent must be between 0 and 100"):
            get_threshold_amount(Decimal("101"))
    
    def test_invalid_monthly_cap(self):
        with pytest.raises(ValueError, match="Monthly cap must be positive"):
            get_threshold_amount(Decimal("50"), monthly_cap=Decimal("-100"))


class TestConstants:
    """Test module constants have expected values."""
    
    def test_monthly_cap_eur(self):
        assert MONTHLY_CAP_EUR == Decimal("1500.00")
    
    def test_kill_switch_threshold_percent(self):
        assert KILL_SWITCH_THRESHOLD_PERCENT == Decimal("95")


class TestDeterminism:
    """Test that all core functions are deterministic."""
    
    def test_calculate_api_cost_deterministic(self):
        """Same inputs should always return same output."""
        cost1 = calculate_api_cost("task", "pro")
        cost2 = calculate_api_cost("task", "pro")
        cost3 = calculate_api_cost("task", "pro")
        
        assert cost1 == cost2 == cost3 == Decimal("0.050")
    
    def test_kill_switch_deterministic(self):
        """Same inputs should always return same output."""
        inputs = (Decimal("1400.00"), Decimal("50.00"))
        
        result1 = should_activate_kill_switch(*inputs)
        result2 = should_activate_kill_switch(*inputs)
        result3 = should_activate_kill_switch(*inputs)
        
        assert result1 == result2 == result3 is True
    
    def test_budget_utilization_deterministic(self):
        """Same inputs should always return same output."""
        spend = Decimal("1337.42")
        
        util1 = calculate_budget_utilization(spend)
        util2 = calculate_budget_utilization(spend)
        util3 = calculate_budget_utilization(spend)
        
        expected = Decimal("89.161")  # 1337.42 / 1500 * 100, rounded
        assert util1 == util2 == util3 == expected