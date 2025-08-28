"""
Test cost tracking integration helpers and decorators.
"""

import pytest
from unittest.mock import AsyncMock
from decimal import Decimal

from ..integration import (
    with_cost_tracking,
    cost_tracked_call,
    assert_parallel_safe,
    BudgetExceededException,
)
from ..shell import CostTracker
from ..contracts import PreFlightCheck


@pytest.fixture
async def mock_cost_tracker():
    """Mock cost tracker for integration tests."""
    tracker = AsyncMock(spec=CostTracker)
    return tracker


class TestCostTrackingDecorator:
    """Test the @with_cost_tracking decorator."""

    async def test_decorator_success(self, mock_cost_tracker):
        """Test successful API call with cost tracking."""
        # Mock successful pre-flight check
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.005"),
            projected_spend_eur=Decimal("100.005"),
            utilization_after_percent=Decimal("6.667"),
            kill_switch_would_activate=False,
        )

        mock_cost_tracker.record_api_cost.return_value = None

        @with_cost_tracking("search", "pro", "test_case")
        async def mock_api_call(query: str, tenant: str):
            return {"results": ["item1", "item2"]}

        # Call with cost_tracker injected
        result = await mock_api_call(
            "test query", "tenant1", cost_tracker=mock_cost_tracker
        )

        assert result == {"results": ["item1", "item2"]}

        # Verify pre-flight check was called
        mock_cost_tracker.check_budget_before_call.assert_called_once_with(
            api_type="search", processor="pro", tenant="tenant1", use_case="test_case"
        )

        # Verify cost was recorded
        mock_cost_tracker.record_api_cost.assert_called_once_with(
            api_type="search",
            processor="pro",
            tenant="tenant1",
            use_case="test_case",
            request_id=None,
            metadata={"function": "mock_api_call", "preflight_cost": 0.005},
        )

    async def test_decorator_budget_exceeded(self, mock_cost_tracker):
        """Test decorator when budget is exceeded."""
        # Mock failed pre-flight check
        preflight = PreFlightCheck(
            allowed=False,
            current_spend_eur=Decimal("1450.00"),
            proposed_cost_eur=Decimal("0.050"),
            projected_spend_eur=Decimal("1450.050"),
            utilization_after_percent=Decimal("96.670"),
            kill_switch_would_activate=True,
            reason="Would exceed 95% threshold (€1,425.00)",
        )
        mock_cost_tracker.check_budget_before_call.return_value = preflight

        @with_cost_tracking("task", "pro", "test_case")
        async def mock_api_call(query: str, tenant: str):
            return {"results": []}

        # Should raise BudgetExceededException
        with pytest.raises(BudgetExceededException) as exc_info:
            await mock_api_call("test query", "tenant1", cost_tracker=mock_cost_tracker)

        assert "Would exceed 95% threshold" in str(exc_info.value)
        assert exc_info.value.preflight_check == preflight

        # Verify cost was NOT recorded
        mock_cost_tracker.record_api_cost.assert_not_called()

    async def test_decorator_api_call_fails(self, mock_cost_tracker):
        """Test decorator when API call fails after pre-flight check."""
        # Mock successful pre-flight check
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.005"),
            projected_spend_eur=Decimal("100.005"),
            utilization_after_percent=Decimal("6.667"),
            kill_switch_would_activate=False,
        )

        @with_cost_tracking("search", "pro", "test_case")
        async def failing_api_call(query: str, tenant: str):
            raise Exception("API call failed")

        # Should propagate the API error
        with pytest.raises(Exception, match="API call failed"):
            await failing_api_call(
                "test query", "tenant1", cost_tracker=mock_cost_tracker
            )

        # Verify cost was NOT recorded (API call failed)
        mock_cost_tracker.record_api_cost.assert_not_called()

    async def test_decorator_missing_tenant(self, mock_cost_tracker):
        """Test decorator when tenant is missing."""

        @with_cost_tracking("search", "pro", "test_case")
        async def mock_api_call(query: str):
            return {"results": []}

        with pytest.raises(ValueError, match="Tenant must be provided"):
            await mock_api_call("test query", cost_tracker=mock_cost_tracker)

    async def test_decorator_missing_cost_tracker(self):
        """Test decorator when cost tracker is missing."""

        @with_cost_tracking("search", "pro", "test_case")
        async def mock_api_call(query: str, tenant: str):
            return {"results": []}

        with pytest.raises(ValueError, match="CostTracker must be injected"):
            await mock_api_call("test query", "tenant1")


class TestCostTrackedCallContextManager:
    """Test the cost_tracked_call context manager."""

    async def test_context_manager_success(self, mock_cost_tracker):
        """Test successful use of context manager."""
        # Mock successful pre-flight check
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.020"),
            projected_spend_eur=Decimal("100.020"),
            utilization_after_percent=Decimal("6.668"),
            kill_switch_would_activate=False,
        )

        mock_cost_tracker.record_api_cost.return_value = None

        async with cost_tracked_call(
            mock_cost_tracker, "task", "core", "tenant1", "test_use_case"
        ) as ctx:
            assert ctx.allowed is True
            assert ctx.reason is None

            # Simulate API call

        # Verify cost was recorded after successful context exit
        mock_cost_tracker.record_api_cost.assert_called_once_with(
            api_type="task",
            processor="core",
            tenant="tenant1",
            use_case="test_use_case",
            request_id=None,
            metadata={"preflight_cost": 0.020, "context_manager": True},
        )

    async def test_context_manager_budget_exceeded(self, mock_cost_tracker):
        """Test context manager when budget exceeded."""
        # Mock failed pre-flight check
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=False,
            current_spend_eur=Decimal("1450.00"),
            proposed_cost_eur=Decimal("0.050"),
            projected_spend_eur=Decimal("1450.050"),
            utilization_after_percent=Decimal("96.670"),
            kill_switch_would_activate=True,
            reason="Kill switch activated",
        )

        async with cost_tracked_call(
            mock_cost_tracker, "task", "pro", "tenant1"
        ) as ctx:
            assert ctx.allowed is False
            assert ctx.reason == "Kill switch activated"

            # Code should check ctx.allowed before proceeding
            if not ctx.allowed:
                # Don't make API call
                pass

        # Verify cost was NOT recorded (call not allowed)
        mock_cost_tracker.record_api_cost.assert_not_called()

    async def test_context_manager_api_exception(self, mock_cost_tracker):
        """Test context manager when exception occurs in API call."""
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.005"),
            projected_spend_eur=Decimal("100.005"),
            utilization_after_percent=Decimal("6.667"),
            kill_switch_would_activate=False,
        )

        with pytest.raises(Exception, match="Simulated API error"):
            async with cost_tracked_call(
                mock_cost_tracker, "search", "base", "tenant1"
            ) as ctx:
                assert ctx.allowed is True

                # Simulate API call failure
                raise Exception("Simulated API error")

        # Verify cost was NOT recorded (exception occurred)
        mock_cost_tracker.record_api_cost.assert_not_called()


class TestAssertParallelSafe:
    """Test enhanced assert_parallel_safe function."""

    async def test_assert_parallel_safe_success(self, mock_cost_tracker):
        """Test successful parallel safety check."""
        # Mock successful budget check
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.050"),
            projected_spend_eur=Decimal("100.050"),
            utilization_after_percent=Decimal("6.670"),
            kill_switch_would_activate=False,
        )

        payload = {
            "query": "Find DORA regulations",
            "sources": ["fsma.be", "nbb.be"],
            "max_results": 10,
        }

        # Should not raise any exception
        await assert_parallel_safe(mock_cost_tracker, payload, "tenant1", "task", "pro")

        mock_cost_tracker.check_budget_before_call.assert_called_once_with(
            api_type="task", processor="pro", tenant="tenant1"
        )

    async def test_assert_parallel_safe_budget_exceeded(self, mock_cost_tracker):
        """Test parallel safety check when budget exceeded."""
        # Mock failed budget check
        preflight = PreFlightCheck(
            allowed=False,
            current_spend_eur=Decimal("1450.00"),
            proposed_cost_eur=Decimal("0.050"),
            projected_spend_eur=Decimal("1450.050"),
            utilization_after_percent=Decimal("96.670"),
            kill_switch_would_activate=True,
            reason="Kill switch activated",
        )
        mock_cost_tracker.check_budget_before_call.return_value = preflight

        payload = {"query": "test"}

        with pytest.raises(BudgetExceededException) as exc_info:
            await assert_parallel_safe(mock_cost_tracker, payload, "tenant1")

        assert "Budget check failed" in str(exc_info.value)
        assert exc_info.value.preflight_check == preflight

    async def test_assert_parallel_safe_payload_too_large(self, mock_cost_tracker):
        """Test parallel safety check with oversized payload."""
        # Mock successful budget check
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.050"),
            projected_spend_eur=Decimal("100.050"),
            utilization_after_percent=Decimal("6.670"),
            kill_switch_would_activate=False,
        )

        # Create payload that's too large (>15k chars)
        large_payload = {"data": "x" * 16000}

        with pytest.raises(ValueError, match="Payload too large"):
            await assert_parallel_safe(mock_cost_tracker, large_payload, "tenant1")

    async def test_assert_parallel_safe_pii_detected(self, mock_cost_tracker):
        """Test parallel safety check with PII in payload."""
        # Mock successful budget check
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.050"),
            projected_spend_eur=Decimal("100.050"),
            utilization_after_percent=Decimal("6.670"),
            kill_switch_would_activate=False,
        )

        # Payload with email address (PII)
        pii_payload = {"query": "Contact john.doe@company.com about regulations"}

        with pytest.raises(ValueError, match="Forbidden pattern detected"):
            await assert_parallel_safe(mock_cost_tracker, pii_payload, "tenant1")

    async def test_assert_parallel_safe_multiple_pii_patterns(self, mock_cost_tracker):
        """Test detection of various PII patterns."""
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.050"),
            projected_spend_eur=Decimal("100.050"),
            utilization_after_percent=Decimal("6.670"),
            kill_switch_would_activate=False,
        )

        test_cases = [
            ({"data": "email@example.com"}, "@"),
            ({"data": "IBAN BE68 5390 0754 7034"}, "IBAN"),
            ({"data": "VAT number BE123456789"}, "VAT"),
            ({"data": "Phone +32 2 123 4567"}, "+32"),
            ({"data": "Call 0032 2 987 6543"}, "0032"),
        ]

        for payload, expected_pattern in test_cases:
            with pytest.raises(
                ValueError, match=f"Forbidden pattern detected.*{expected_pattern}"
            ):
                await assert_parallel_safe(mock_cost_tracker, payload, "tenant1")


class TestIntegrationErrorHandling:
    """Test error handling in integration components."""

    async def test_decorator_with_tenant_in_kwargs(self, mock_cost_tracker):
        """Test decorator extracts tenant from kwargs correctly."""
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("100.00"),
            proposed_cost_eur=Decimal("0.005"),
            projected_spend_eur=Decimal("100.005"),
            utilization_after_percent=Decimal("6.667"),
            kill_switch_would_activate=False,
        )

        @with_cost_tracking("search", "base", "test")
        async def api_call(query: str, **kwargs):
            return {"query": query}

        result = await api_call(
            "test query",
            tenant="tenant1",
            cost_tracker=mock_cost_tracker,
            extra_param="value",
        )

        assert result == {"query": "test query"}
        mock_cost_tracker.check_budget_before_call.assert_called_once_with(
            api_type="search", processor="base", tenant="tenant1", use_case="test"
        )

    async def test_context_manager_with_request_id(self, mock_cost_tracker):
        """Test context manager with request_id parameter."""
        mock_cost_tracker.check_budget_before_call.return_value = PreFlightCheck(
            allowed=True,
            current_spend_eur=Decimal("50.00"),
            proposed_cost_eur=Decimal("0.001"),
            projected_spend_eur=Decimal("50.001"),
            utilization_after_percent=Decimal("3.333"),
            kill_switch_would_activate=False,
        )

        request_id = "req_123456"

        async with cost_tracked_call(
            mock_cost_tracker,
            "search",
            "base",
            "tenant1",
            "test_case",
            request_id=request_id,
        ) as ctx:
            assert ctx.allowed is True
            # Simulate successful API call
            pass

        # Verify request_id was passed to cost recording
        mock_cost_tracker.record_api_cost.assert_called_once()
        call_args = mock_cost_tracker.record_api_cost.call_args
        assert call_args.kwargs["request_id"] == request_id
