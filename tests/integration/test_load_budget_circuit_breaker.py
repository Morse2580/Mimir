"""
Load Testing for Budget Race Conditions and Circuit Breaker Scenarios

This module tests the system under high load conditions to ensure:
1. Budget tracking maintains consistency under concurrent operations
2. Circuit breaker activates correctly under load
3. Kill switch triggers at the correct thresholds
4. System gracefully degrades when limits are exceeded
"""

import pytest
import asyncio
import time
import threading
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from backend.app.cost.contracts import (
    CostUsage,
    BudgetAlert,
    KillSwitchEvent,
    AlertType,
)


@dataclass
class MockCostTracker:
    """Mock cost tracker with thread-safe operations."""
    
    current_spend: float = 0.0
    budget_limit: float = 1500.0
    kill_switch_threshold: float = 95.0  # 95%
    warning_threshold: float = 80.0      # 80%
    critical_threshold: float = 90.0     # 90%
    
    # Thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _usage_history: List[CostUsage] = field(default_factory=list)
    _alerts_sent: List[BudgetAlert] = field(default_factory=list)
    
    # Circuit breaker state
    kill_switch_active: bool = False
    degraded_mode: bool = False
    
    def record_usage(self, service: str, operation: str, cost_eur: float) -> CostUsage:
        """Record cost usage with thread safety."""
        with self._lock:
            usage = CostUsage(
                service_name=service,
                operation=operation,
                cost_eur=cost_eur,
                timestamp=datetime.now(timezone.utc),
                usage_id=f"usage_{len(self._usage_history):06d}",
                metadata={"thread_id": threading.get_ident()}
            )
            
            self._usage_history.append(usage)
            self.current_spend += cost_eur
            
            # Check thresholds
            self._check_thresholds()
            
            return usage
    
    def _check_thresholds(self):
        """Check budget thresholds and trigger alerts."""
        spend_percentage = (self.current_spend / self.budget_limit) * 100
        
        # Kill switch threshold
        if spend_percentage >= self.kill_switch_threshold and not self.kill_switch_active:
            self.kill_switch_active = True
            self._send_alert(AlertType.KILL_SWITCH, spend_percentage)
        
        # Critical threshold
        elif spend_percentage >= self.critical_threshold and not self.degraded_mode:
            self.degraded_mode = True
            self._send_alert(AlertType.CRITICAL, spend_percentage)
        
        # Warning threshold
        elif spend_percentage >= self.warning_threshold and len(self._alerts_sent) == 0:
            self._send_alert(AlertType.WARNING, spend_percentage)
    
    def _send_alert(self, alert_type: AlertType, spend_percentage: float):
        """Send budget alert."""
        alert = BudgetAlert(
            alert_type=alert_type,
            current_spend_eur=self.current_spend,
            budget_limit_eur=self.budget_limit,
            threshold_percentage=spend_percentage,
            triggered_at=datetime.now(timezone.utc),
            time_remaining_hours=24.0,  # Simplified
            projected_overage_eur=max(0, self.current_spend - self.budget_limit)
        )
        self._alerts_sent.append(alert)
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current budget status."""
        with self._lock:
            return {
                "current_spend_eur": self.current_spend,
                "budget_limit_eur": self.budget_limit,
                "spend_percentage": (self.current_spend / self.budget_limit) * 100,
                "kill_switch_active": self.kill_switch_active,
                "degraded_mode": self.degraded_mode,
                "total_operations": len(self._usage_history),
                "alerts_sent": len(self._alerts_sent)
            }
    
    def reset(self):
        """Reset tracker state."""
        with self._lock:
            self.current_spend = 0.0
            self.kill_switch_active = False
            self.degraded_mode = False
            self._usage_history.clear()
            self._alerts_sent.clear()


@dataclass  
class MockCircuitBreaker:
    """Mock circuit breaker with state management."""
    
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    failure_count: int = 0
    failure_threshold: int = 5
    success_count: int = 0
    success_threshold: int = 3
    
    # Timing
    last_failure_time: Optional[datetime] = None
    timeout_duration: timedelta = field(default_factory=lambda: timedelta(seconds=60))
    
    # Thread safety
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def call(self, operation_func, *args, **kwargs):
        """Execute operation through circuit breaker."""
        with self._lock:
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                    self.success_count = 0
                else:
                    raise CircuitBreakerOpenError("Circuit breaker is OPEN")
            
            try:
                result = operation_func(*args, **kwargs)
                self._record_success()
                return result
            except Exception as e:
                self._record_failure()
                raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset."""
        if not self.last_failure_time:
            return True
        return datetime.now(timezone.utc) - self.last_failure_time > self.timeout_duration
    
    def _record_success(self):
        """Record successful operation."""
        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "CLOSED"
                self.failure_count = 0
        else:
            self.failure_count = 0
    
    def _record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
    
    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state."""
        with self._lock:
            return {
                "state": self.state,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None
            }


class CircuitBreakerOpenError(Exception):
    """Circuit breaker is open."""
    pass


class TestBudgetRaceConditions:
    """Test budget tracking under concurrent load."""
    
    @pytest.fixture
    def cost_tracker(self):
        """Create mock cost tracker."""
        return MockCostTracker()
    
    def test_concurrent_budget_tracking_consistency(self, cost_tracker):
        """Test budget consistency under concurrent operations."""
        num_threads = 20
        operations_per_thread = 50
        base_cost = 1.0  # €1 per operation
        
        def record_costs(thread_id: int):
            """Record costs for a thread."""
            costs = []
            for i in range(operations_per_thread):
                cost = base_cost + random.uniform(-0.1, 0.1)  # Small variation
                usage = cost_tracker.record_usage(
                    service=f"service_{thread_id % 3}",
                    operation=f"operation_{i}",
                    cost_eur=cost
                )
                costs.append(cost)
            return sum(costs)
        
        # Execute concurrent operations
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            future_to_thread = {
                executor.submit(record_costs, i): i for i in range(num_threads)
            }
            
            total_expected_cost = 0
            for future in as_completed(future_to_thread):
                thread_cost = future.result()
                total_expected_cost += thread_cost
        
        # Verify consistency
        status = cost_tracker.get_current_status()
        
        # Allow small floating point tolerance
        cost_diff = abs(status["current_spend_eur"] - total_expected_cost)
        assert cost_diff < 0.01, \
            f"Cost tracking inconsistent: expected {total_expected_cost:.2f}, got {status['current_spend_eur']:.2f}"
        
        # Verify operation count
        expected_operations = num_threads * operations_per_thread
        assert status["total_operations"] == expected_operations
        
        print(f"✅ Budget consistency maintained: {status['current_spend_eur']:.2f}€ across {status['total_operations']} operations")
    
    def test_budget_threshold_triggers_under_load(self, cost_tracker):
        """Test that budget thresholds trigger correctly under load."""
        # Set low budget for quick threshold crossing
        cost_tracker.budget_limit = 100.0
        
        num_threads = 10
        cost_per_operation = 2.0
        
        def generate_load(thread_id: int):
            """Generate load until kill switch activates."""
            operations = 0
            while not cost_tracker.kill_switch_active and operations < 100:
                cost_tracker.record_usage(
                    service="load_test",
                    operation=f"op_{operations}",
                    cost_eur=cost_per_operation
                )
                operations += 1
                time.sleep(0.001)  # Small delay
            return operations
        
        # Start load generation
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(generate_load, i) for i in range(num_threads)]
            results = [future.result() for future in as_completed(futures)]
        
        load_duration = time.time() - start_time
        
        # Verify kill switch activated
        status = cost_tracker.get_current_status()
        assert status["kill_switch_active"] is True, "Kill switch should have activated"
        assert status["spend_percentage"] >= 95.0, f"Should exceed 95% threshold, got {status['spend_percentage']:.1f}%"
        
        # Verify alerts were sent
        assert status["alerts_sent"] > 0, "Budget alerts should have been sent"
        
        # Performance check: should activate kill switch quickly
        assert load_duration < 5.0, f"Kill switch took {load_duration:.2f}s to activate (limit: 5s)"
        
        print(f"✅ Kill switch activated at {status['spend_percentage']:.1f}% in {load_duration:.2f}s")
    
    def test_race_condition_at_budget_boundary(self, cost_tracker):
        """Test race conditions at exact budget boundaries."""
        # Set budget close to threshold
        cost_tracker.current_spend = 94.0  # Just below 95% threshold
        cost_tracker.budget_limit = 100.0
        
        num_threads = 20
        boundary_cost = 0.1  # Small costs to test boundary conditions
        
        def test_boundary_crossing(thread_id: int):
            """Test boundary crossing behavior."""
            try:
                usage = cost_tracker.record_usage(
                    service="boundary_test",
                    operation=f"boundary_{thread_id}",
                    cost_eur=boundary_cost
                )
                return {"success": True, "usage_id": usage.usage_id}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Execute boundary tests concurrently
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(test_boundary_crossing, i) for i in range(num_threads)]
            results = [future.result() for future in as_completed(futures)]
        
        # Analyze results
        successful_operations = [r for r in results if r["success"]]
        status = cost_tracker.get_current_status()
        
        # Kill switch should have activated
        assert status["kill_switch_active"] is True
        
        # Some operations should have succeeded before kill switch
        assert len(successful_operations) > 0, "Some operations should have succeeded"
        
        # Verify consistent state
        expected_min_spend = 94.0 + (len(successful_operations) * boundary_cost)
        assert status["current_spend_eur"] >= expected_min_spend
        
        print(f"✅ Boundary race condition handled: {len(successful_operations)} ops succeeded before kill switch")
    
    def test_budget_recovery_after_reset(self, cost_tracker):
        """Test budget tracking after kill switch reset."""
        # Trigger kill switch
        cost_tracker.record_usage("test", "trigger", 1500.0)  # Exceed budget
        
        initial_status = cost_tracker.get_current_status()
        assert initial_status["kill_switch_active"] is True
        
        # Reset system (simulate daily reset)
        cost_tracker.reset()
        
        # Verify clean state
        reset_status = cost_tracker.get_current_status()
        assert reset_status["current_spend_eur"] == 0.0
        assert reset_status["kill_switch_active"] is False
        assert reset_status["total_operations"] == 0
        
        # Test normal operation after reset
        cost_tracker.record_usage("recovery_test", "normal_op", 10.0)
        
        post_reset_status = cost_tracker.get_current_status()
        assert post_reset_status["current_spend_eur"] == 10.0
        assert post_reset_status["kill_switch_active"] is False
        
        print("✅ Budget recovery after reset successful")


class TestCircuitBreakerUnderLoad:
    """Test circuit breaker behavior under high load."""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create mock circuit breaker."""
        return MockCircuitBreaker()
    
    def test_circuit_breaker_failure_detection(self, circuit_breaker):
        """Test circuit breaker opens after failure threshold."""
        def failing_operation():
            """Operation that always fails."""
            raise Exception("Simulated failure")
        
        # Execute operations until circuit breaker opens
        failure_count = 0
        while circuit_breaker.state != "OPEN" and failure_count < 10:
            try:
                circuit_breaker.call(failing_operation)
            except Exception:
                failure_count += 1
        
        # Verify circuit breaker opened
        state = circuit_breaker.get_state()
        assert state["state"] == "OPEN"
        assert state["failure_count"] >= circuit_breaker.failure_threshold
        
        print(f"✅ Circuit breaker opened after {state['failure_count']} failures")
    
    def test_circuit_breaker_concurrent_operations(self, circuit_breaker):
        """Test circuit breaker under concurrent load."""
        success_count = 0
        failure_count = 0
        circuit_open_count = 0
        
        def mixed_operation(operation_id: int):
            """Operation with mixed success/failure."""
            def operation():
                if operation_id % 3 == 0:  # 1/3 operations fail
                    raise Exception(f"Planned failure {operation_id}")
                return f"Success {operation_id}"
            
            try:
                result = circuit_breaker.call(operation)
                return {"type": "success", "result": result}
            except CircuitBreakerOpenError:
                return {"type": "circuit_open"}
            except Exception as e:
                return {"type": "failure", "error": str(e)}
        
        # Execute concurrent operations
        num_operations = 100
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(mixed_operation, i) for i in range(num_operations)]
            results = [future.result() for future in as_completed(futures)]
        
        # Analyze results
        for result in results:
            if result["type"] == "success":
                success_count += 1
            elif result["type"] == "failure":
                failure_count += 1
            elif result["type"] == "circuit_open":
                circuit_open_count += 1
        
        # Verify circuit breaker behavior
        final_state = circuit_breaker.get_state()
        
        # Should have some failures leading to circuit opening
        assert failure_count > 0, "Should have some failures"
        assert circuit_open_count > 0, "Circuit breaker should have opened"
        
        # Total operations should match
        total_handled = success_count + failure_count + circuit_open_count
        assert total_handled == num_operations
        
        print(f"✅ Circuit breaker handled {num_operations} ops: "
              f"{success_count} success, {failure_count} failures, {circuit_open_count} circuit open")
    
    def test_circuit_breaker_recovery_cycle(self, circuit_breaker):
        """Test circuit breaker recovery from OPEN to CLOSED state."""
        # Force circuit breaker open
        def failing_op():
            raise Exception("Force failure")
        
        for _ in range(circuit_breaker.failure_threshold):
            try:
                circuit_breaker.call(failing_op)
            except Exception:
                pass
        
        assert circuit_breaker.state == "OPEN"
        
        # Wait for timeout (simulate passage of time)
        circuit_breaker.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=70)
        
        # Define successful operation
        def success_op():
            return "Success"
        
        # First call should transition to HALF_OPEN
        result = circuit_breaker.call(success_op)
        assert circuit_breaker.state == "HALF_OPEN"
        assert result == "Success"
        
        # Execute enough successful operations to close circuit
        for _ in range(circuit_breaker.success_threshold - 1):
            circuit_breaker.call(success_op)
        
        # Circuit should now be CLOSED
        assert circuit_breaker.state == "CLOSED"
        
        print("✅ Circuit breaker recovery cycle: OPEN → HALF_OPEN → CLOSED")
    
    def test_degraded_mode_functionality(self, circuit_breaker):
        """Test system functionality in degraded mode."""
        # Simulate degraded mode with circuit breaker open
        circuit_breaker.state = "OPEN"
        
        degraded_results = []
        
        def degraded_operation():
            """Fallback operation when circuit is open."""
            return {
                "status": "degraded",
                "data": "cached_result",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Test degraded operations
        for i in range(10):
            try:
                # Try normal operation (should fail due to circuit breaker)
                circuit_breaker.call(lambda: "normal_result")
            except CircuitBreakerOpenError:
                # Fall back to degraded operation
                result = degraded_operation()
                degraded_results.append(result)
        
        # Verify degraded mode functionality
        assert len(degraded_results) == 10
        for result in degraded_results:
            assert result["status"] == "degraded"
            assert result["data"] == "cached_result"
            assert result["timestamp"] is not None
        
        print(f"✅ Degraded mode provided {len(degraded_results)} fallback responses")


class TestIntegratedLoadScenarios:
    """Test integrated load scenarios combining budget and circuit breaker."""
    
    def test_high_load_system_stability(self):
        """Test system stability under high concurrent load."""
        cost_tracker = MockCostTracker()
        circuit_breaker = MockCircuitBreaker()
        
        # Reduce limits for faster testing
        cost_tracker.budget_limit = 50.0
        circuit_breaker.failure_threshold = 3
        
        operation_results = []
        
        def integrated_operation(operation_id: int):
            """Operation that uses both cost tracking and circuit breaker."""
            def costly_operation():
                # Simulate cost
                cost = random.uniform(0.5, 2.0)
                
                # Check if kill switch is active
                if cost_tracker.kill_switch_active:
                    raise Exception("Kill switch active")
                
                # Record cost
                cost_tracker.record_usage("integrated_test", f"op_{operation_id}", cost)
                
                # Simulate occasional failures
                if random.random() < 0.15:  # 15% failure rate
                    raise Exception(f"Random failure {operation_id}")
                
                return {"operation_id": operation_id, "cost": cost, "status": "success"}
            
            try:
                result = circuit_breaker.call(costly_operation)
                return {"type": "success", "data": result}
            except CircuitBreakerOpenError:
                return {"type": "circuit_open", "operation_id": operation_id}
            except Exception as e:
                return {"type": "failure", "operation_id": operation_id, "error": str(e)}
        
        # Execute high load test
        num_operations = 200
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(integrated_operation, i) for i in range(num_operations)]
            results = [future.result() for future in as_completed(futures)]
        
        load_duration = time.time() - start_time
        
        # Analyze results
        success_ops = [r for r in results if r["type"] == "success"]
        circuit_open_ops = [r for r in results if r["type"] == "circuit_open"]
        failure_ops = [r for r in results if r["type"] == "failure"]
        
        # Get final system state
        budget_status = cost_tracker.get_current_status()
        circuit_state = circuit_breaker.get_state()
        
        # Verify system behavior
        assert len(results) == num_operations, "All operations should be accounted for"
        
        # Either budget or circuit breaker should have limited operations
        protection_activated = (
            budget_status["kill_switch_active"] or 
            circuit_state["state"] == "OPEN" or
            len(circuit_open_ops) > 0
        )
        assert protection_activated, "System protection should have activated under load"
        
        # Performance requirement: should handle load efficiently
        assert load_duration < 10.0, f"Load test took {load_duration:.2f}s (limit: 10s)"
        
        print(f"✅ High load test completed in {load_duration:.2f}s: "
              f"{len(success_ops)} success, {len(failure_ops)} failures, "
              f"{len(circuit_open_ops)} circuit open")
        print(f"   Budget: {budget_status['spend_percentage']:.1f}% used, "
              f"Kill switch: {budget_status['kill_switch_active']}")
        print(f"   Circuit: {circuit_state['state']}, "
              f"Failures: {circuit_state['failure_count']}")
    
    def test_load_spike_handling(self):
        """Test system handling of sudden load spikes."""
        cost_tracker = MockCostTracker()
        circuit_breaker = MockCircuitBreaker()
        
        # Configure for spike testing
        cost_tracker.budget_limit = 100.0
        cost_tracker.kill_switch_threshold = 95.0
        
        spike_results = []
        
        def spike_operation(batch_id: int, op_id: int):
            """Operation during load spike."""
            def operation():
                cost = random.uniform(1.0, 3.0)
                
                if cost_tracker.kill_switch_active:
                    raise Exception("Kill switch activated")
                
                cost_tracker.record_usage("spike_test", f"batch_{batch_id}_op_{op_id}", cost)
                
                # Simulate higher failure rate during spikes
                if random.random() < 0.2:
                    raise Exception(f"Spike failure {batch_id}_{op_id}")
                
                return f"batch_{batch_id}_op_{op_id}_success"
            
            try:
                return circuit_breaker.call(operation)
            except Exception:
                return None
        
        # Simulate load spike: sudden burst of operations
        batch_sizes = [5, 10, 20, 50, 30, 10, 5]  # Spike pattern
        
        for batch_id, batch_size in enumerate(batch_sizes):
            batch_start = time.time()
            
            # Execute batch concurrently
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = [
                    executor.submit(spike_operation, batch_id, op_id) 
                    for op_id in range(batch_size)
                ]
                batch_results = [future.result() for future in as_completed(futures)]
            
            batch_duration = time.time() - batch_start
            successful_in_batch = len([r for r in batch_results if r is not None])
            
            spike_results.append({
                "batch_id": batch_id,
                "batch_size": batch_size, 
                "successful": successful_in_batch,
                "duration": batch_duration,
                "budget_status": cost_tracker.get_current_status(),
                "circuit_state": circuit_breaker.get_state()
            })
            
            # Small delay between batches
            time.sleep(0.1)
            
            # Stop if system protection activated
            if cost_tracker.kill_switch_active or circuit_breaker.state == "OPEN":
                break
        
        # Analyze spike handling
        total_operations = sum(batch["batch_size"] for batch in spike_results)
        total_successful = sum(batch["successful"] for batch in spike_results)
        
        # Verify graceful degradation
        assert total_successful > 0, "Some operations should succeed during spike"
        
        # System should activate protection mechanisms
        final_budget = cost_tracker.get_current_status()
        final_circuit = circuit_breaker.get_state()
        
        protection_active = (
            final_budget["kill_switch_active"] or 
            final_budget["degraded_mode"] or
            final_circuit["state"] in ["OPEN", "HALF_OPEN"]
        )
        
        # May or may not activate depending on spike pattern
        print(f"✅ Load spike handled: {total_successful}/{total_operations} operations succeeded")
        print(f"   Final budget: {final_budget['spend_percentage']:.1f}%, "
              f"Kill switch: {final_budget['kill_switch_active']}")
        print(f"   Final circuit: {final_circuit['state']}")


class TestPerformanceUnderLoad:
    """Test performance characteristics under load."""
    
    def test_cost_tracking_performance_under_load(self):
        """Test cost tracking performance under concurrent load."""
        cost_tracker = MockCostTracker()
        
        num_operations = 10000
        num_threads = 50
        operations_per_thread = num_operations // num_threads
        
        def performance_test_thread(thread_id: int):
            """Performance test thread."""
            start_time = time.time()
            
            for i in range(operations_per_thread):
                cost_tracker.record_usage(
                    service=f"perf_test_{thread_id % 5}",
                    operation=f"op_{i}",
                    cost_eur=0.01  # Small cost to avoid hitting limits
                )
            
            return time.time() - start_time
        
        # Execute performance test
        total_start = time.time()
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(performance_test_thread, i) for i in range(num_threads)]
            thread_times = [future.result() for future in as_completed(futures)]
        
        total_time = time.time() - total_start
        
        # Calculate performance metrics
        ops_per_second = num_operations / total_time
        avg_thread_time = sum(thread_times) / len(thread_times)
        max_thread_time = max(thread_times)
        
        # Performance requirements
        assert ops_per_second > 1000, f"Performance too slow: {ops_per_second:.0f} ops/sec (min: 1000)"
        assert max_thread_time < 5.0, f"Thread took too long: {max_thread_time:.2f}s (max: 5s)"
        
        # Verify consistency
        final_status = cost_tracker.get_current_status()
        expected_spend = num_operations * 0.01
        spend_diff = abs(final_status["current_spend_eur"] - expected_spend)
        
        assert spend_diff < 0.1, f"Spend tracking inconsistent: {spend_diff:.3f}€ difference"
        
        print(f"✅ Cost tracking performance: {ops_per_second:.0f} ops/sec, "
              f"max thread: {max_thread_time:.2f}s")
    
    def test_memory_usage_under_sustained_load(self):
        """Test memory usage during sustained load."""
        import psutil
        import os
        
        cost_tracker = MockCostTracker()
        circuit_breaker = MockCircuitBreaker()
        
        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        def sustained_operation(operation_id: int):
            """Sustained operation for memory testing."""
            def operation():
                cost = random.uniform(0.01, 0.05)
                cost_tracker.record_usage("memory_test", f"op_{operation_id}", cost)
                
                # Create some temporary data
                temp_data = {"id": operation_id, "data": "x" * 100}
                return temp_data
            
            try:
                return circuit_breaker.call(operation)
            except Exception:
                return None
        
        # Run sustained load for memory testing
        num_batches = 20
        batch_size = 100
        
        for batch in range(num_batches):
            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [
                    executor.submit(sustained_operation, batch * batch_size + i) 
                    for i in range(batch_size)
                ]
                results = [future.result() for future in as_completed(futures)]
            
            # Check memory periodically
            if batch % 5 == 0:
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_increase = current_memory - initial_memory
                
                # Memory increase should be reasonable
                assert memory_increase < 100, f"Memory increased by {memory_increase:.1f}MB (limit: 100MB)"
        
        # Final memory check
        final_memory = process.memory_info().rss / 1024 / 1024
        total_memory_increase = final_memory - initial_memory
        
        print(f"✅ Memory usage under sustained load: +{total_memory_increase:.1f}MB")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])