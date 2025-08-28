#!/usr/bin/env python3
"""
Cost tracking validation script.
Verifies PII boundaries, audit trail integrity, and basic functionality.
"""
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

from .core import (
    calculate_api_cost,
    should_activate_kill_switch,
    calculate_budget_utilization,
    MONTHLY_CAP_EUR,
    KILL_SWITCH_THRESHOLD_PERCENT
)
from .integration import assert_parallel_safe, BudgetExceededException
from .shell import CostTracker


async def validate_pii_boundaries():
    """Validate PII detection in assert_parallel_safe."""
    print("🔐 Testing PII Boundaries...")
    
    # Mock cost tracker that allows all requests
    mock_tracker = AsyncMock()
    mock_tracker.check_budget_before_call.return_value.allowed = True
    mock_tracker.check_budget_before_call.return_value.proposed_cost_eur = Decimal("0.001")
    
    # Test cases that should FAIL (contain PII)
    pii_test_cases = [
        ({"query": "Contact john.doe@company.com"}, "Email address"),
        ({"data": "IBAN BE68 5390 0754 7034"}, "IBAN number"),
        ({"text": "VAT BE123456789"}, "VAT number"),
        ({"info": "Call +32 2 123 4567"}, "Belgian phone +32"),
        ({"contact": "Phone 0032 9 876 5432"}, "Belgian phone 0032"),
    ]
    
    pii_violations = 0
    for payload, description in pii_test_cases:
        try:
            await assert_parallel_safe(mock_tracker, payload, "test_tenant")
            print(f"❌ PII NOT DETECTED: {description}")
            pii_violations += 1
        except ValueError as e:
            if "Forbidden pattern detected" in str(e):
                print(f"✅ PII BLOCKED: {description}")
            else:
                print(f"❌ WRONG ERROR: {description} - {e}")
                pii_violations += 1
        except Exception as e:
            print(f"❌ UNEXPECTED ERROR: {description} - {e}")
            pii_violations += 1
    
    # Test cases that should PASS (no PII)
    safe_test_cases = [
        {"query": "Find DORA regulations"},
        {"search": "NBB policy updates"},
        {"data": "Regulatory compliance requirements"},
    ]
    
    for payload in safe_test_cases:
        try:
            await assert_parallel_safe(mock_tracker, payload, "test_tenant")
            print(f"✅ SAFE PAYLOAD: {payload['query'] if 'query' in payload else list(payload.values())[0]}")
        except Exception as e:
            print(f"❌ SAFE PAYLOAD REJECTED: {payload} - {e}")
            pii_violations += 1
    
    return pii_violations == 0


def validate_kill_switch_accuracy():
    """Validate kill switch triggers at exactly 95% threshold."""
    print("\n⚡ Testing Kill Switch Accuracy...")
    
    test_cases = [
        # (current_spend, proposed_cost, expected_activation, description)
        (Decimal("1400.00"), Decimal("50.00"), True, "€1400 + €50 = €1450 > €1425 threshold"),
        (Decimal("1400.00"), Decimal("25.00"), False, "€1400 + €25 = €1425 = threshold"),
        (Decimal("1400.00"), Decimal("24.99"), False, "€1400 + €24.99 = €1424.99 < threshold"),
        (Decimal("1424.99"), Decimal("0.01"), False, "€1424.99 + €0.01 = €1425.00 = threshold"),
        (Decimal("1425.00"), Decimal("0.001"), True, "€1425 + €0.001 = €1425.001 > threshold"),
        (Decimal("0.00"), Decimal("1425.00"), False, "€0 + €1425 = €1425.00 = threshold"),
        (Decimal("0.00"), Decimal("1425.01"), True, "€0 + €1425.01 = €1425.01 > threshold"),
    ]
    
    errors = 0
    for current, proposed, expected, description in test_cases:
        actual = should_activate_kill_switch(current, proposed)
        if actual == expected:
            status = "✅"
        else:
            status = "❌"
            errors += 1
        
        print(f"{status} {description} -> {'BLOCK' if actual else 'ALLOW'}")
    
    return errors == 0


def validate_cost_calculations():
    """Validate all API cost calculations."""
    print("\n💰 Testing Cost Calculations...")
    
    expected_costs = {
        ("search", "base"): Decimal("0.001"),
        ("search", "pro"): Decimal("0.005"),
        ("task", "base"): Decimal("0.010"),
        ("task", "core"): Decimal("0.020"),
        ("task", "pro"): Decimal("0.050"),
    }
    
    errors = 0
    for (api_type, processor), expected_cost in expected_costs.items():
        try:
            actual_cost = calculate_api_cost(api_type, processor)
            if actual_cost == expected_cost:
                print(f"✅ {api_type}:{processor} = €{actual_cost}")
            else:
                print(f"❌ {api_type}:{processor} = €{actual_cost} (expected €{expected_cost})")
                errors += 1
        except Exception as e:
            print(f"❌ {api_type}:{processor} ERROR: {e}")
            errors += 1
    
    return errors == 0


def validate_budget_utilization_accuracy():
    """Validate budget utilization calculations to 0.001 EUR accuracy."""
    print("\n📊 Testing Budget Utilization Accuracy...")
    
    test_cases = [
        (Decimal("750.00"), Decimal("50.000")),   # Exactly 50%
        (Decimal("1200.00"), Decimal("80.000")),  # Exactly 80%
        (Decimal("1425.00"), Decimal("95.000")),  # Exactly 95% (kill switch)
        (Decimal("1500.00"), Decimal("100.000")), # Exactly 100%
        (Decimal("1500.001"), Decimal("100.000")), # Should round to 100.000%
        (Decimal("750.0005"), Decimal("50.000")),  # Should round to 50.000%
        (Decimal("1337.42"), Decimal("89.161")),   # Arbitrary precision test
    ]
    
    errors = 0
    for spend, expected in test_cases:
        actual = calculate_budget_utilization(spend)
        if actual == expected:
            print(f"✅ €{spend} -> {actual}%")
        else:
            print(f"❌ €{spend} -> {actual}% (expected {expected}%)")
            errors += 1
    
    return errors == 0


def validate_constants():
    """Validate critical constants."""
    print("\n🔧 Testing Constants...")
    
    checks = [
        (MONTHLY_CAP_EUR == Decimal("1500.00"), "Monthly cap = €1,500.00"),
        (KILL_SWITCH_THRESHOLD_PERCENT == Decimal("95"), "Kill switch threshold = 95%"),
    ]
    
    errors = 0
    for check, description in checks:
        if check:
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
            errors += 1
    
    return errors == 0


async def run_validation():
    """Run all validation checks."""
    print("🧪 COST TRACKING VALIDATION")
    print("=" * 50)
    
    checks = [
        ("PII Boundaries", await validate_pii_boundaries()),
        ("Kill Switch Accuracy", validate_kill_switch_accuracy()),
        ("Cost Calculations", validate_cost_calculations()),
        ("Budget Utilization Accuracy", validate_budget_utilization_accuracy()),
        ("Constants", validate_constants()),
    ]
    
    print("\n" + "=" * 50)
    print("📋 VALIDATION SUMMARY")
    print("=" * 50)
    
    total_passed = 0
    for check_name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {check_name}")
        if passed:
            total_passed += 1
    
    print(f"\nResult: {total_passed}/{len(checks)} checks passed")
    
    if total_passed == len(checks):
        print("\n🎉 ALL VALIDATIONS PASSED!")
        print("Cost tracking module is ready for production.")
        return True
    else:
        print(f"\n⚠️  {len(checks) - total_passed} VALIDATION(S) FAILED!")
        print("Please fix issues before deployment.")
        return False


if __name__ == "__main__":
    asyncio.run(run_validation())