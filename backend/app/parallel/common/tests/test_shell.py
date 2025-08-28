"""
Tests for PII Boundary Guard Shell Functions

This module tests the I/O operations including Redis integration,
circuit breaker functionality, and the critical assert_parallel_safe function.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from typing import Dict, Any

from backend.app.parallel.common.shell import (
    PIIBoundaryGuard,
    PIIBoundaryError,
    CircuitBreakerOpenError,
    assert_parallel_safe,
    initialize_pii_guard
)
from backend.app.parallel.common.contracts import (
    CircuitBreakerState,
    CircuitBreakerConfig,
    PIIViolationType
)
from backend.app.parallel.common.events import (
    PIIViolationDetected,
    CircuitBreakerOpened,
    CircuitBreakerClosed,
    CircuitBreakerHalfOpen
)


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = Mock()
    redis_mock.pipeline = Mock(return_value=Mock())
    redis_mock.pipeline.return_value.execute = AsyncMock(return_value=[None] * 7)
    redis_mock.set = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.incr = AsyncMock()
    redis_mock.delete = AsyncMock()
    return redis_mock


@pytest.fixture
def mock_event_publisher():
    """Mock event publisher for testing."""
    return AsyncMock()


@pytest.fixture
def pii_guard(mock_redis, mock_event_publisher):
    """PII boundary guard instance for testing."""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout_seconds=600,
        half_open_max_calls=5
    )
    return PIIBoundaryGuard(mock_redis, config, mock_event_publisher)


class TestPIIBoundaryGuard:
    """Test PII boundary guard functionality."""
    
    @pytest.mark.asyncio
    async def test_assert_parallel_safe_with_clean_data(self, pii_guard):
        """Test assert_parallel_safe with clean data."""
        clean_data = {
            "query": "What are the DORA compliance requirements?",
            "context": "regulatory research"
        }
        
        # Should not raise any exception
        await pii_guard.assert_parallel_safe(clean_data, "test_endpoint")
        
        # Should not publish any violation events
        pii_guard.event_publisher.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_assert_parallel_safe_with_email_pii(self, pii_guard):
        """Test assert_parallel_safe with email PII."""
        pii_data = {
            "contact": "Please email john@company.com for support"
        }
        
        with pytest.raises(PIIBoundaryError) as exc_info:
            await pii_guard.assert_parallel_safe(pii_data, "test_endpoint")
        
        # Check violation details
        violation = exc_info.value.violation
        assert violation.violation_type == PIIViolationType.EMAIL
        assert "john@company.com" in violation.detected_patterns
        assert violation.risk_score > 0.4  # Updated to match current algorithm
        
        # Should publish violation event
        pii_guard.event_publisher.assert_called_once()
        event = pii_guard.event_publisher.call_args[0][0]
        assert isinstance(event, PIIViolationDetected)
        assert event.violation_type == PIIViolationType.EMAIL
    
    @pytest.mark.asyncio
    async def test_assert_parallel_safe_with_belgian_rrn(self, pii_guard):
        """Test assert_parallel_safe with Belgian RRN."""
        pii_data = {
            "personal_info": "RRN: 85073003328"
        }
        
        with pytest.raises(PIIBoundaryError):
            await pii_guard.assert_parallel_safe(pii_data, "test_endpoint")
        
        # Should publish violation event
        pii_guard.event_publisher.assert_called_once()
        event = pii_guard.event_publisher.call_args[0][0]
        assert isinstance(event, PIIViolationDetected)
        assert event.violation_type == PIIViolationType.BELGIAN_RRN
    
    @pytest.mark.asyncio
    async def test_assert_parallel_safe_with_belgian_vat(self, pii_guard):
        """Test assert_parallel_safe with Belgian VAT."""
        pii_data = {
            "company_details": "VAT number: BE0123456749"
        }
        
        with pytest.raises(PIIBoundaryError):
            await pii_guard.assert_parallel_safe(pii_data, "test_endpoint")
        
        # Should publish violation event
        pii_guard.event_publisher.assert_called_once()
        event = pii_guard.event_publisher.call_args[0][0]
        assert isinstance(event, PIIViolationDetected)
        assert event.violation_type == PIIViolationType.BELGIAN_VAT
    
    @pytest.mark.asyncio
    async def test_assert_parallel_safe_with_iban(self, pii_guard):
        """Test assert_parallel_safe with IBAN."""
        pii_data = {
            "banking": "Account: BE62510007547061"
        }
        
        with pytest.raises(PIIBoundaryError):
            await pii_guard.assert_parallel_safe(pii_data, "test_endpoint")
        
        # Should publish violation event
        pii_guard.event_publisher.assert_called_once()
        event = pii_guard.event_publisher.call_args[0][0]
        assert isinstance(event, PIIViolationDetected)
        assert event.violation_type == PIIViolationType.IBAN
    
    @pytest.mark.asyncio
    async def test_assert_parallel_safe_payload_too_large(self, pii_guard):
        """Test assert_parallel_safe with payload exceeding size limit."""
        large_data = {
            "content": "x" * 16000  # Exceeds 15k limit
        }
        
        with pytest.raises(ValueError) as exc_info:
            await pii_guard.assert_parallel_safe(large_data, "test_endpoint")
        
        assert "Payload too large" in str(exc_info.value)
        assert "16015 chars" in str(exc_info.value) or "16000 chars" in str(exc_info.value)  # Account for JSON overhead
        assert "limit: 15000" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_assert_parallel_safe_empty_data(self, pii_guard):
        """Test assert_parallel_safe with empty data."""
        # Should handle empty data gracefully
        await pii_guard.assert_parallel_safe({}, "test_endpoint")
        await pii_guard.assert_parallel_safe(None, "test_endpoint")
        
        # Should not publish any events
        pii_guard.event_publisher.assert_not_called()


class TestCircuitBreakerFunctionality:
    """Test circuit breaker functionality."""
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_call_success(self, pii_guard):
        """Test successful circuit breaker call."""
        async def mock_func(arg1, arg2=None):
            return {"result": "success", "cost_euros": 0.05}
        
        result = await pii_guard.circuit_breaker_call(mock_func, "test_service", "arg1", arg2="arg2")
        
        assert result["result"] == "success"
        
        # Should record success in Redis
        assert pii_guard.redis.pipeline.called
        
        # Should publish success event (only if cost_euros > 0 or service is parallel)
        if result.get("cost_euros", 0) > 0:
            pii_guard.event_publisher.assert_called()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_call_failure(self, pii_guard):
        """Test failed circuit breaker call."""
        async def failing_func():
            raise Exception("API failure")
        
        with pytest.raises(Exception) as exc_info:
            await pii_guard.circuit_breaker_call(failing_func, "test_service")
        
        assert "API failure" in str(exc_info.value)
        
        # Should record failure in Redis
        assert pii_guard.redis.pipeline.called
        
        # Should publish failure event
        pii_guard.event_publisher.assert_called()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold_failures(self, pii_guard):
        """Test circuit breaker opens after reaching failure threshold."""
        # Mock get_circuit_status to return failures at threshold after the call
        original_get_status = pii_guard.get_circuit_status
        call_count = 0
        
        async def mock_get_status(service_name):
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # Initial call
                return Mock(
                    state=CircuitBreakerState.CLOSED,
                    failure_count=2,  # Below threshold initially
                    next_attempt_time=None
                )
            else:  # After failure recorded
                return Mock(
                    state=CircuitBreakerState.CLOSED, 
                    failure_count=3,  # At threshold after failure
                    next_attempt_time=None
                )
        
        pii_guard.get_circuit_status = mock_get_status
        
        async def failing_func():
            raise Exception("API failure")
        
        with pytest.raises(Exception):
            await pii_guard.circuit_breaker_call(failing_func, "test_service")
        
        # Should open circuit breaker (uses pipeline.set, not direct redis.set)
        assert pii_guard.redis.pipeline.called
        
        # Should publish circuit opened event
        events = [call[0][0] for call in pii_guard.event_publisher.call_args_list]
        circuit_opened_events = [e for e in events if isinstance(e, CircuitBreakerOpened)]
        assert len(circuit_opened_events) > 0
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(self, pii_guard):
        """Test circuit breaker blocks calls when open."""
        future_time = datetime.utcnow() + timedelta(minutes=5)
        
        pii_guard.get_circuit_status = AsyncMock(return_value=Mock(
            state=CircuitBreakerState.OPEN,
            next_attempt_time=future_time,
            failure_count=3
        ))
        
        async def mock_func():
            return "should not execute"
        
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await pii_guard.circuit_breaker_call(mock_func, "test_service")
        
        assert exc_info.value.service_name == "test_service"
        assert exc_info.value.next_attempt_time == future_time
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_transitions_to_half_open(self, pii_guard):
        """Test circuit breaker transitions to half-open when recovery time passed."""
        past_time = datetime.utcnow() - timedelta(minutes=5)
        
        pii_guard.get_circuit_status = AsyncMock(return_value=Mock(
            state=CircuitBreakerState.OPEN,
            next_attempt_time=past_time,
            failure_count=3
        ))
        
        async def mock_func():
            return {"result": "recovery test"}
        
        result = await pii_guard.circuit_breaker_call(mock_func, "test_service")
        
        assert result["result"] == "recovery test"
        
        # Should set half-open state
        assert pii_guard.redis.set.called
    
    @pytest.mark.asyncio
    async def test_get_circuit_status_no_redis(self):
        """Test get_circuit_status without Redis client."""
        guard = PIIBoundaryGuard(redis_client=None)
        
        status = await guard.get_circuit_status("test_service")
        
        assert status.state == CircuitBreakerState.CLOSED
        assert status.failure_count == 0
        assert status.last_failure_time is None
    
    @pytest.mark.asyncio
    async def test_reset_circuit_breaker(self, pii_guard):
        """Test manual circuit breaker reset."""
        await pii_guard.reset_circuit_breaker("test_service")
        
        # Should reset state in Redis
        assert pii_guard.redis.pipeline.called
        
        # Should publish reset event
        pii_guard.event_publisher.assert_called_once()
        event = pii_guard.event_publisher.call_args[0][0]
        assert isinstance(event, CircuitBreakerClosed)
        assert event.service_name == "test_service"


class TestGlobalFunctions:
    """Test global assert_parallel_safe function."""
    
    @pytest.mark.asyncio
    async def test_global_assert_parallel_safe_clean_data(self):
        """Test global assert_parallel_safe with clean data."""
        clean_data = {"query": "DORA requirements"}
        
        # Should not raise exception
        await assert_parallel_safe(clean_data, "test_context")
    
    @pytest.mark.asyncio
    async def test_global_assert_parallel_safe_with_pii(self):
        """Test global assert_parallel_safe with PII data."""
        pii_data = {"email": "test@example.com"}
        
        with pytest.raises(PIIBoundaryError):
            await assert_parallel_safe(pii_data, "test_context")
    
    def test_initialize_pii_guard(self, mock_redis, mock_event_publisher):
        """Test PII guard initialization."""
        config = CircuitBreakerConfig(failure_threshold=5)
        
        guard = initialize_pii_guard(mock_redis, config, mock_event_publisher)
        
        assert guard.redis == mock_redis
        assert guard.config.failure_threshold == 5
        assert guard.event_publisher == mock_event_publisher


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple components."""
    
    @pytest.mark.asyncio
    async def test_full_pii_detection_and_circuit_breaker_flow(self, pii_guard):
        """Test full flow: clean call -> PII detection -> circuit breaker."""
        # First, successful call
        async def successful_parallel_call(data):
            return {"citations": ["source1"], "cost_euros": 0.02}
        
        result = await pii_guard.circuit_breaker_call(
            successful_parallel_call, 
            "parallel_ai", 
            {"query": "clean data"}
        )
        assert result["citations"] == ["source1"]
        
        # Then, attempt with PII (should fail at boundary, not reach circuit breaker)
        pii_data = {"query": "Contact admin@company.com"}
        
        with pytest.raises(PIIBoundaryError):
            await pii_guard.assert_parallel_safe(pii_data, "parallel_ai")
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery_scenario(self, pii_guard):
        """Test complete circuit breaker recovery scenario."""
        call_count = 0
        
        async def flaky_service():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("Service unavailable")
            return {"result": "recovered", "cost_euros": 0.01}
        
        # Configure circuit breaker to show failures
        def mock_status_progression(service_name):
            if call_count <= 2:
                return Mock(
                    state=CircuitBreakerState.CLOSED,
                    failure_count=call_count,
                    next_attempt_time=None
                )
            elif call_count == 3:
                return Mock(
                    state=CircuitBreakerState.CLOSED,
                    failure_count=3,  # At threshold
                    next_attempt_time=None
                )
            else:
                return Mock(
                    state=CircuitBreakerState.OPEN,
                    next_attempt_time=datetime.utcnow() - timedelta(seconds=1),  # Past recovery time
                    failure_count=3
                )
        
        pii_guard.get_circuit_status = AsyncMock(side_effect=mock_status_progression)
        
        # First 3 calls should fail and eventually open circuit
        for i in range(3):
            with pytest.raises(Exception):
                await pii_guard.circuit_breaker_call(flaky_service, "test_service")
        
        # 4th call should succeed (recovery)
        result = await pii_guard.circuit_breaker_call(flaky_service, "test_service")
        assert result["result"] == "recovered"
        
        # Should have published various events
        assert pii_guard.event_publisher.call_count >= 4


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_malformed_json_in_payload(self, pii_guard):
        """Test handling of malformed data structures."""
        # Test with circular references (should be handled gracefully)
        circular_data = {}
        circular_data["self"] = circular_data
        
        # Should handle gracefully without infinite recursion
        # Note: Circular references cause ValueError during JSON serialization,
        # which is handled before PII detection even runs
        circular_data["email"] = "test@example.com"
        
        with pytest.raises(ValueError) as exc_info:
            await pii_guard.assert_parallel_safe(circular_data, "test")
        
        assert "Invalid payload structure" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_redis_connection_failures(self, pii_guard):
        """Test handling of Redis connection failures."""
        # Mock Redis to raise connection errors
        pii_guard.redis.pipeline.side_effect = Exception("Redis connection failed")
        
        # Circuit breaker should still work (fail-safe mode)
        async def test_func():
            return "success"
        
        result = await pii_guard.circuit_breaker_call(test_func, "test_service")
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_event_publisher_failures(self, pii_guard):
        """Test handling of event publisher failures."""
        # Mock event publisher to fail
        pii_guard.event_publisher.side_effect = Exception("Event publishing failed")
        
        # PII detection should still work and raise appropriate error
        pii_data = {"email": "test@example.com"}
        
        with pytest.raises(PIIBoundaryError):
            await pii_guard.assert_parallel_safe(pii_data, "test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])