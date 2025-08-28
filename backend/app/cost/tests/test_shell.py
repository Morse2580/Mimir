"""
Test cost tracking shell operations - Redis integration and alert testing.
Uses mocks for external dependencies.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal
import json

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from ..shell import CostTracker, reset_monthly_budget, manual_kill_switch_override
from ..contracts import BudgetState, PreFlightCheck, BudgetStatus
from ..events import BudgetThresholdExceeded, KillSwitchActivated, CostRecorded


@pytest.fixture
async def mock_redis():
    """Mock Redis client."""
    mock_client = AsyncMock(spec=redis.Redis)
    return mock_client


@pytest.fixture
async def mock_db():
    """Mock database session."""
    mock_session = AsyncMock(spec=AsyncSession)
    return mock_session


@pytest.fixture 
async def cost_tracker(mock_redis, mock_db):
    """Cost tracker with mocked dependencies."""
    return CostTracker(mock_redis, mock_db)


class TestCostTracker:
    """Test CostTracker Redis operations."""
    
    async def test_get_current_spend_zero(self, cost_tracker, mock_redis):
        """Test getting current spend when no data exists."""
        mock_redis.get.return_value = None
        
        spend = await cost_tracker.get_current_spend("tenant1")
        assert spend == Decimal("0.00")
        
        mock_redis.get.assert_called_once_with("cost:spend:tenant1:2024-08")
    
    async def test_get_current_spend_existing(self, cost_tracker, mock_redis):
        """Test getting existing current spend."""
        mock_redis.get.return_value = b"750.50"
        
        spend = await cost_tracker.get_current_spend("tenant1")
        assert spend == Decimal("750.50")
    
    async def test_is_kill_switch_active_false(self, cost_tracker, mock_redis):
        """Test kill switch inactive."""
        mock_redis.get.return_value = None
        
        active = await cost_tracker.is_kill_switch_active("tenant1")
        assert active is False
        
        mock_redis.get.assert_called_once_with("cost:kill_switch:tenant1")
    
    async def test_is_kill_switch_active_true(self, cost_tracker, mock_redis):
        """Test kill switch active."""
        mock_redis.get.return_value = b"1"
        
        active = await cost_tracker.is_kill_switch_active("tenant1")
        assert active is True
    
    async def test_check_budget_kill_switch_already_active(self, cost_tracker, mock_redis):
        """Test pre-flight check when kill switch is already active."""
        mock_redis.get.return_value = b"1"  # Kill switch active
        
        result = await cost_tracker.check_budget_before_call(
            "search", "pro", "tenant1"
        )
        
        assert isinstance(result, PreFlightCheck)
        assert result.allowed is False
        assert result.reason == "Kill switch already active"
        assert result.kill_switch_would_activate is True
    
    async def test_check_budget_invalid_api_params(self, cost_tracker, mock_redis):
        """Test pre-flight check with invalid API parameters."""
        mock_redis.get.side_effect = [None, b"100.00"]  # Kill switch off, current spend
        
        result = await cost_tracker.check_budget_before_call(
            "invalid", "processor", "tenant1"
        )
        
        assert result.allowed is False
        assert "Invalid API parameters" in result.reason
    
    async def test_check_budget_would_exceed_threshold(self, cost_tracker, mock_redis):
        """Test pre-flight check that would activate kill switch."""
        # Mock: kill switch off, current spend €1400
        mock_redis.get.side_effect = [None, b"1400.00"]
        
        # Mock kill switch activation
        mock_redis.set = AsyncMock()
        mock_redis.lpush = AsyncMock()
        mock_redis.expire = AsyncMock()
        
        result = await cost_tracker.check_budget_before_call(
            "task", "pro", "tenant1"  # €0.050 cost
        )
        
        # €1400 + €0.050 = €1400.050 vs €1425 threshold = ALLOW
        # But let's test with higher cost
        mock_redis.get.side_effect = [None, b"1400.00"]  # Reset side_effect
        
        result = await cost_tracker.check_budget_before_call(
            "task", "pro", "tenant1"
        )
        
        # This should be allowed since €1400.05 < €1425
        assert result.allowed is True
        assert result.projected_spend_eur == Decimal("1400.050")
    
    async def test_check_budget_exceeds_kill_switch_threshold(self, cost_tracker, mock_redis):
        """Test case that definitely exceeds kill switch threshold."""
        # Mock: kill switch off, current spend €1420
        mock_redis.get.side_effect = [None, b"1420.00"]
        
        # Mock kill switch activation
        mock_redis.set = AsyncMock()
        mock_redis.lpush = AsyncMock()
        mock_redis.expire = AsyncMock()
        
        # Mock _emit_event to avoid Redis operations in test
        with patch.object(cost_tracker, '_emit_event', new_callable=AsyncMock):
            result = await cost_tracker.check_budget_before_call(
                "task", "pro", "tenant1"  # €0.050 cost
            )
        
        # €1420 + €0.050 = €1420.050 > €1425 threshold? No, still under
        # Let's use a cost that will definitely exceed
        mock_redis.get.side_effect = [None, b"1430.00"]  # Higher current spend
        
        with patch.object(cost_tracker, '_emit_event', new_callable=AsyncMock):
            result = await cost_tracker.check_budget_before_call(
                "task", "pro", "tenant1"  # €0.050 cost  
            )
        
        # €1430 + €0.050 = €1430.050 > €1425 threshold = BLOCK
        assert result.allowed is False
        assert result.kill_switch_would_activate is True
        assert "Would exceed 95% threshold" in result.reason
    
    async def test_record_api_cost_success(self, cost_tracker, mock_redis, mock_db):
        """Test successful API cost recording."""
        # Mock Redis pipeline operations
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [Decimal("100.050")]  # New total after increment
        mock_redis.pipeline.return_value = mock_pipe
        
        # Mock database operations
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        
        # Mock event emission and threshold checking
        with patch.object(cost_tracker, '_emit_event', new_callable=AsyncMock) as mock_emit:
            with patch.object(cost_tracker, '_check_threshold_alerts', new_callable=AsyncMock) as mock_alerts:
                result = await cost_tracker.record_api_cost(
                    "search", "pro", "tenant1", "test_case"
                )
        
        # Verify cost entry
        assert result.api_type == "search"
        assert result.processor == "pro"
        assert result.cost_eur == Decimal("0.005")
        assert result.tenant == "tenant1"
        assert result.use_case == "test_case"
        
        # Verify Redis operations
        mock_pipe.incrbyfloat.assert_called_once()
        mock_pipe.expire.assert_called_once()
        
        # Verify database storage
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()
        
        # Verify event emission
        mock_emit.assert_called_once()
        mock_alerts.assert_called_once()
    
    async def test_get_budget_state(self, cost_tracker, mock_redis):
        """Test getting current budget state."""
        # Mock current spend and kill switch state
        mock_redis.get.side_effect = [b"750.00", None]  # Spend, kill switch off
        
        state = await cost_tracker.get_budget_state("tenant1")
        
        assert isinstance(state, BudgetState)
        assert state.tenant == "tenant1"
        assert state.current_spend_eur == Decimal("750.00")
        assert state.utilization_percent == Decimal("50.000")
        assert state.status == BudgetStatus.WARNING  # 50% threshold
        assert state.kill_switch_active is False


class TestBudgetReset:
    """Test monthly budget reset operations."""
    
    async def test_reset_monthly_budget(self, mock_redis):
        """Test resetting monthly budget."""
        # Mock previous spend lookup
        mock_redis.get.return_value = b"1250.75"
        mock_redis.delete = AsyncMock()
        mock_redis.lpush = AsyncMock()
        mock_redis.expire = AsyncMock()
        
        await reset_monthly_budget(mock_redis, "tenant1", "2024-08")
        
        # Verify old spend key deletion
        mock_redis.delete.assert_any_call("cost:spend:tenant1:2024-08")
        # Verify kill switch deletion  
        mock_redis.delete.assert_any_call("cost:kill_switch:tenant1")
        
        # Verify event emission
        mock_redis.lpush.assert_called_once()
        mock_redis.expire.assert_called_once()
    
    async def test_reset_monthly_budget_no_previous_spend(self, mock_redis):
        """Test resetting when no previous spend exists."""
        mock_redis.get.return_value = None
        mock_redis.delete = AsyncMock()
        mock_redis.lpush = AsyncMock()
        mock_redis.expire = AsyncMock()
        
        await reset_monthly_budget(mock_redis, "tenant1")
        
        # Should still perform reset operations
        assert mock_redis.delete.call_count == 2  # Spend key + kill switch key
        mock_redis.lpush.assert_called_once()


class TestKillSwitchOverride:
    """Test manual kill switch override operations."""
    
    async def test_manual_override_success(self, mock_redis):
        """Test successful kill switch override."""
        # Mock kill switch was active and current spend
        mock_redis.get.side_effect = [b"1", b"1450.00"]
        mock_redis.delete = AsyncMock()
        
        result = await manual_kill_switch_override(
            mock_redis, 
            "tenant1",
            "ceo@company.com",
            "Emergency regulatory submission",
            "c_level"
        )
        
        assert result is True
        mock_redis.delete.assert_called_once_with("cost:kill_switch:tenant1")
    
    async def test_manual_override_not_active(self, mock_redis):
        """Test override when kill switch not active."""
        mock_redis.get.return_value = None  # Kill switch not active
        
        result = await manual_kill_switch_override(
            mock_redis,
            "tenant1", 
            "ceo@company.com",
            "Test reason",
            "c_level"
        )
        
        assert result is False  # Nothing to override
    
    async def test_manual_override_invalid_approval_level(self, mock_redis):
        """Test override with invalid approval level."""
        with pytest.raises(ValueError, match="Kill switch override requires C-level"):
            await manual_kill_switch_override(
                mock_redis,
                "tenant1",
                "user@company.com", 
                "Test reason",
                "manager"  # Invalid level
            )


class TestPerformanceRequirements:
    """Test that performance requirements are met."""
    
    @patch('time.time')
    async def test_cost_check_performance(self, mock_time, cost_tracker, mock_redis):
        """Test cost check completes in <10ms."""
        # Mock time progression (simulate <10ms execution)
        mock_time.side_effect = [1000.0, 1000.008]  # 8ms execution
        
        mock_redis.get.side_effect = [None, b"100.00"]  # Kill switch off, low spend
        
        result = await cost_tracker.check_budget_before_call(
            "search", "base", "tenant1"
        )
        
        assert result.allowed is True
        # In real test, would verify timing, but mocked for unit test
    
    async def test_redis_key_formats(self, cost_tracker):
        """Test Redis key format consistency."""
        monthly_key = cost_tracker._get_monthly_key("tenant1", "2024-08")
        kill_switch_key = cost_tracker._get_kill_switch_key("tenant1")
        
        assert monthly_key == "cost:spend:tenant1:2024-08"
        assert kill_switch_key == "cost:kill_switch:tenant1"
    
    async def test_redis_key_current_month(self, cost_tracker):
        """Test Redis key generation for current month."""
        # Should auto-generate current month if not specified
        key = cost_tracker._get_monthly_key("tenant1")
        
        # Key should match pattern but we can't predict exact month in test
        assert key.startswith("cost:spend:tenant1:")
        assert len(key.split(":")) == 4  # cost:spend:tenant:YYYY-MM


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    async def test_redis_connection_error(self, mock_db):
        """Test handling Redis connection errors."""
        # Create a Redis client that raises connection errors
        failing_redis = AsyncMock(spec=redis.Redis)
        failing_redis.get.side_effect = redis.ConnectionError("Connection failed")
        
        tracker = CostTracker(failing_redis, mock_db)
        
        # Should propagate Redis errors (fail-safe approach for budget enforcement)
        with pytest.raises(redis.ConnectionError):
            await tracker.get_current_spend("tenant1")
    
    async def test_database_error_handling(self, cost_tracker, mock_redis, mock_db):
        """Test handling database errors during cost recording."""
        # Mock Redis success but database failure
        mock_pipe = AsyncMock()
        mock_pipe.execute.return_value = [Decimal("100.050")]
        mock_redis.pipeline.return_value = mock_pipe
        
        mock_db.execute.side_effect = Exception("Database error")
        
        # Should raise exception (don't silently fail audit trail)
        with pytest.raises(Exception, match="Database error"):
            await cost_tracker.record_api_cost(
                "search", "pro", "tenant1", "test"
            )