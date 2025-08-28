"""
Test the observability shell module - I/O operations with mocks.
Tests metric storage, alert emission, and SLO tracking.
"""

import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import redis.asyncio as redis

from ..contracts import (
    AlertOperator,
    Failure,
    MetricType,
    SLODefinition,
    Severity,
    Success,
)
from ..core import create_metric
from ..shell import ObservabilityStorage, PerformanceTracker, record_metric


@pytest.fixture
async def mock_redis():
    """Create a mock Redis client."""
    mock_client = AsyncMock(spec=redis.Redis)
    
    # Mock pipeline operations
    mock_pipeline = AsyncMock()
    mock_pipeline.execute.return_value = None
    mock_client.pipeline.return_value.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_client.pipeline.return_value.__aexit__ = AsyncMock(return_value=None)
    
    return mock_client


@pytest.fixture
async def storage(mock_redis):
    """Create an ObservabilityStorage instance with mocked dependencies."""
    storage = ObservabilityStorage(
        redis_client=mock_redis,
        database_url="sqlite:///test.db",
        tenant="test_tenant"
    )
    await storage.initialize()
    return storage


class TestObservabilityStorage:
    """Test the ObservabilityStorage class."""

    @pytest.mark.asyncio
    async def test_record_metric_success(self, storage, mock_redis):
        """Test successful metric recording."""
        # Create a test metric
        metric_result = create_metric(
            name="test.metric.count",
            value=42.0,
            labels={"service": "test"},
            metric_type=MetricType.COUNTER,
        )
        assert isinstance(metric_result, Success)
        metric = metric_result.value

        # Record the metric
        result = await storage.record_metric(metric, emit_events=False)
        
        assert isinstance(result, Success)
        
        # Verify Redis operations were called
        assert mock_redis.pipeline.called

    @pytest.mark.asyncio
    async def test_record_metric_with_redis_error(self, storage, mock_redis):
        """Test metric recording with Redis error."""
        # Configure Redis to raise an exception
        mock_redis.pipeline.side_effect = Exception("Redis connection failed")

        # Create a test metric
        metric_result = create_metric(
            name="test.metric.count",
            value=42.0,
        )
        assert isinstance(metric_result, Success)
        metric = metric_result.value

        # Record the metric (should handle error gracefully)
        result = await storage.record_metric(metric, emit_events=False)
        
        assert isinstance(result, Failure)
        assert "Redis connection failed" in result.error

    @pytest.mark.asyncio
    async def test_get_metric_value_current(self, storage, mock_redis):
        """Test getting current metric value."""
        # Mock Redis to return a value
        mock_redis.hget.return_value = "42.5"

        result = await storage.get_metric_value("test.metric.count")
        
        assert isinstance(result, Success)
        assert result.value == 42.5
        
        # Verify Redis was called correctly
        mock_redis.hget.assert_called_once_with("metrics:test_tenant:test.metric.count", "value")

    @pytest.mark.asyncio
    async def test_get_metric_value_not_found(self, storage, mock_redis):
        """Test getting metric value when not found."""
        # Mock Redis to return None
        mock_redis.hget.return_value = None

        result = await storage.get_metric_value("nonexistent.metric")
        
        assert isinstance(result, Success)
        assert result.value is None

    @pytest.mark.asyncio
    async def test_get_metric_value_aggregated(self, storage, mock_redis):
        """Test getting aggregated metric value over time window."""
        # Mock time series data
        mock_data = [
            (json.dumps({"value": 10.0, "timestamp": "2023-01-01T00:00:00"}), 1672531200.0),
            (json.dumps({"value": 20.0, "timestamp": "2023-01-01T01:00:00"}), 1672534800.0),
            (json.dumps({"value": 30.0, "timestamp": "2023-01-01T02:00:00"}), 1672538400.0),
        ]
        mock_redis.zrangebyscore.return_value = mock_data

        time_window = timedelta(hours=3)
        result = await storage.get_metric_value("test.metric.count", time_window)
        
        assert isinstance(result, Success)
        assert result.value == 20.0  # Average of 10, 20, 30

    @pytest.mark.asyncio
    async def test_get_slo_status(self, storage, mock_redis):
        """Test getting SLO status."""
        # Mock metric value
        mock_redis.hget.return_value = "85.0"

        slo_definition = SLODefinition(
            name="test.slo",
            target_value=100.0,
            time_window=timedelta(minutes=5),
            operator=AlertOperator.GT,
            description="Test SLO"
        )

        result = await storage.get_slo_status(slo_definition)
        
        assert isinstance(result, Success)
        slo_status = result.value
        
        assert slo_status.definition == slo_definition
        assert slo_status.current_value == 85.0
        assert slo_status.compliance_percent < 100.0  # 85 is less than 100

    @pytest.mark.asyncio 
    async def test_emit_alert_to_multiple_channels(self, storage):
        """Test alert emission to multiple channels."""
        # Create test alert
        from ..contracts import Alert, AlertRule
        
        alert_rule = AlertRule(
            metric_name="test.metric",
            threshold=100.0,
            operator=AlertOperator.GT,
            severity=Severity.CRITICAL,
            message_template="Test alert: {value}"
        )
        
        alert = Alert(
            rule=alert_rule,
            current_value=150.0,
            message="Test alert: 150.0",
            timestamp=datetime.utcnow(),
            labels={}
        )

        # Test emission with specific channels
        result = await storage.emit_alert(alert, channels=["redis", "log"])
        
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_alert_evaluation_for_metric(self, storage):
        """Test alert evaluation when recording metrics."""
        # Create a metric that should trigger an alert
        metric_result = create_metric(
            name="pii.violations.total",
            value=1.0,  # Should trigger PII alert
            metric_type=MetricType.COUNTER,
        )
        assert isinstance(metric_result, Success)
        metric = metric_result.value

        # Mock the alert emission to avoid external dependencies
        with patch.object(storage, 'emit_alert', new_callable=AsyncMock) as mock_emit:
            result = await storage.record_metric(metric, emit_events=False)
            
            assert isinstance(result, Success)
            # Should have triggered alert for PII violation
            mock_emit.assert_called()

    @pytest.mark.asyncio
    async def test_metric_collection_failure_event(self, storage, mock_redis):
        """Test that metric collection failures emit events."""
        # Configure Redis to fail
        mock_redis.pipeline.side_effect = Exception("Network error")

        metric_result = create_metric(name="test.metric", value=1.0)
        assert isinstance(metric_result, Success)
        metric = metric_result.value

        # Mock event emission
        with patch.object(storage, '_emit_event', new_callable=AsyncMock) as mock_emit:
            result = await storage.record_metric(metric, emit_events=False)
            
            assert isinstance(result, Failure)
            # Should have emitted failure event
            mock_emit.assert_called()
            
            # Check the event type
            call_args = mock_emit.call_args[0][0]
            from ..events import MetricCollectionFailed
            assert isinstance(call_args, MetricCollectionFailed)


class TestPerformanceTracker:
    """Test the PerformanceTracker class."""

    @pytest.fixture
    async def performance_tracker(self, storage):
        """Create a PerformanceTracker instance."""
        return PerformanceTracker(storage)

    @pytest.mark.asyncio
    async def test_track_operation_within_target(self, performance_tracker, storage):
        """Test tracking operation that meets performance target."""
        # Track PII detection within target (50ms)
        result = await performance_tracker.track_operation_duration(
            operation="pii_detection",
            duration_ms=25.0,
            labels={"module": "parallel"}
        )
        
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_track_operation_exceeds_target(self, performance_tracker, storage):
        """Test tracking operation that exceeds performance target."""
        # Mock event emission
        with patch.object(storage, '_emit_event', new_callable=AsyncMock) as mock_emit:
            result = await performance_tracker.track_operation_duration(
                operation="pii_detection",
                duration_ms=75.0,  # Exceeds 50ms target
                labels={"module": "parallel"}
            )
            
            assert isinstance(result, Success)
            
            # Should emit performance threshold exceeded event
            mock_emit.assert_called()
            call_args = mock_emit.call_args[0][0]
            from ..events import PerformanceThresholdExceeded
            assert isinstance(call_args, PerformanceThresholdExceeded)
            assert call_args.operation == "pii_detection"
            assert call_args.actual_duration_ms == 75.0

    @pytest.mark.asyncio
    async def test_track_unknown_operation(self, performance_tracker):
        """Test tracking operation with no defined target."""
        result = await performance_tracker.track_operation_duration(
            operation="unknown_operation",
            duration_ms=100.0
        )
        
        assert isinstance(result, Failure)
        assert "No target defined" in result.error


class TestConvenienceFunctions:
    """Test convenience functions for metric recording."""

    @pytest.mark.asyncio
    async def test_record_metric_convenience_function(self, storage):
        """Test the convenience record_metric function."""
        result = await record_metric(
            name="convenience.test",
            value=123.0,
            labels={"test": "true"},
            metric_type=MetricType.GAUGE,
            storage=storage
        )
        
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_record_metric_without_storage(self):
        """Test convenience function without storage instance."""
        result = await record_metric(
            name="convenience.test",
            value=123.0,
            storage=None
        )
        
        assert isinstance(result, Failure)
        assert "No storage instance" in result.error

    @pytest.mark.asyncio
    async def test_record_metric_with_invalid_name(self, storage):
        """Test convenience function with invalid metric name."""
        result = await record_metric(
            name="Invalid-Name",
            value=123.0,
            storage=storage
        )
        
        assert isinstance(result, Failure)
        assert "Invalid metric" in result.error


class TestAlertEmission:
    """Test alert emission to different channels."""

    @pytest.mark.asyncio
    async def test_emit_alert_to_redis(self, storage, mock_redis):
        """Test emitting alert to Redis."""
        from ..contracts import Alert, AlertRule
        
        alert_rule = AlertRule(
            metric_name="test.metric",
            threshold=50.0,
            operator=AlertOperator.GT,
            severity=Severity.WARNING,
            message_template="Warning: {value}"
        )
        
        alert = Alert(
            rule=alert_rule,
            current_value=75.0,
            message="Warning: 75.0",
            timestamp=datetime.utcnow(),
            labels={"service": "test"}
        )

        # Call internal method directly
        await storage._emit_alert_to_redis(alert)
        
        # Verify Redis operations
        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()

    @pytest.mark.asyncio
    async def test_emit_alert_to_log(self, storage):
        """Test emitting alert to logs."""
        from ..contracts import Alert, AlertRule
        
        alert_rule = AlertRule(
            metric_name="test.metric", 
            threshold=50.0,
            operator=AlertOperator.GT,
            severity=Severity.CRITICAL,
            message_template="Critical: {value}"
        )
        
        alert = Alert(
            rule=alert_rule,
            current_value=100.0,
            message="Critical: 100.0",
            timestamp=datetime.utcnow(),
            labels={}
        )

        # Mock logger to capture log calls
        with patch('backend.app.observability.shell.logger') as mock_logger:
            await storage._emit_alert_to_log(alert)
            
            # Verify log was called with appropriate level
            mock_logger.log.assert_called()
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == 50  # logging.CRITICAL level


class TestEventEmission:
    """Test domain event emission."""

    @pytest.mark.asyncio
    async def test_emit_metric_recorded_event(self, storage):
        """Test emitting MetricRecorded event."""
        metric_result = create_metric(name="test.event", value=1.0)
        assert isinstance(metric_result, Success)
        metric = metric_result.value

        with patch.object(storage, '_emit_event', new_callable=AsyncMock) as mock_emit:
            result = await storage.record_metric(metric, emit_events=True)
            
            assert isinstance(result, Success)
            mock_emit.assert_called()
            
            # Verify event type
            call_args = mock_emit.call_args[0][0]
            from ..events import MetricRecorded
            assert isinstance(call_args, MetricRecorded)
            assert call_args.metric == metric

    @pytest.mark.asyncio  
    async def test_emit_slo_violated_event(self, storage, mock_redis):
        """Test emitting SLOViolated event when SLO is violated."""
        # Mock metric value that violates SLO
        mock_redis.hget.return_value = "10.0"  # Much lower than target

        slo_definition = SLODefinition(
            name="test.slo",
            target_value=100.0,
            time_window=timedelta(minutes=5),
            operator=AlertOperator.GT,
            description="Test SLO that should be violated"
        )

        with patch.object(storage, '_emit_event', new_callable=AsyncMock) as mock_emit:
            result = await storage.get_slo_status(slo_definition)
            
            assert isinstance(result, Success)
            
            # Should emit SLO violated event
            mock_emit.assert_called()
            call_args = mock_emit.call_args[0][0]
            from ..events import SLOViolated
            assert isinstance(call_args, SLOViolated)


# Integration tests
class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    @pytest.mark.asyncio
    async def test_pii_violation_complete_flow(self, storage):
        """Test complete flow for PII violation detection and alerting."""
        # Create PII violation metric
        metric_result = create_metric(
            name="pii.violations.total",
            value=1.0,
            labels={"module": "parallel", "pattern_type": "email"},
            metric_type=MetricType.COUNTER,
        )
        assert isinstance(metric_result, Success)
        metric = metric_result.value

        # Mock alert and event emission
        with patch.object(storage, 'emit_alert', new_callable=AsyncMock) as mock_alert, \
             patch.object(storage, '_emit_event', new_callable=AsyncMock) as mock_event:
            
            result = await storage.record_metric(metric, emit_events=True)
            
            assert isinstance(result, Success)
            
            # Should have triggered alert
            mock_alert.assert_called()
            
            # Should have emitted events
            assert mock_event.call_count >= 1  # MetricRecorded + possibly SecurityMetricViolation

    @pytest.mark.asyncio
    async def test_budget_threshold_complete_flow(self, storage):
        """Test complete flow for budget threshold monitoring."""
        # Create budget utilization metric at kill switch threshold
        metric_result = create_metric(
            name="budget.utilization.percent",
            value=96.0,  # Above 95% kill switch
            labels={"tenant": "test"},
            metric_type=MetricType.GAUGE,
        )
        assert isinstance(metric_result, Success)
        metric = metric_result.value

        with patch.object(storage, 'emit_alert', new_callable=AsyncMock) as mock_alert:
            result = await storage.record_metric(metric, emit_events=True)
            
            assert isinstance(result, Success)
            
            # Should trigger critical alert for kill switch
            mock_alert.assert_called()
            
            # Verify alert details
            alert_call = mock_alert.call_args[0][0]
            assert alert_call.rule.severity == Severity.CRITICAL
            assert "kill switch" in alert_call.message.lower()

    @pytest.mark.asyncio
    async def test_performance_slo_monitoring_flow(self, storage):
        """Test complete flow for performance SLO monitoring."""
        performance_tracker = PerformanceTracker(storage)
        
        with patch.object(storage, '_emit_event', new_callable=AsyncMock) as mock_event:
            # Track operation that exceeds target
            result = await performance_tracker.track_operation_duration(
                operation="onegate_export",
                duration_ms=35 * 60 * 1000,  # 35 minutes (exceeds 30 min target)
                labels={"export_type": "incident"}
            )
            
            assert isinstance(result, Success)
            
            # Should emit performance threshold exceeded event
            mock_event.assert_called()
            
            # Find the PerformanceThresholdExceeded event
            from ..events import PerformanceThresholdExceeded
            events = [call.args[0] for call in mock_event.call_args_list]
            perf_event = next((e for e in events if isinstance(e, PerformanceThresholdExceeded)), None)
            
            assert perf_event is not None
            assert perf_event.operation == "onegate_export"
            assert perf_event.actual_duration_ms == 35 * 60 * 1000
            assert perf_event.target_duration_ms == 30 * 60 * 1000