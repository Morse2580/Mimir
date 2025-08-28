"""
OpenTelemetry Integration for Belgian RegOps Platform
Configures OpenTelemetry for Azure Application Insights and local development.
"""

import logging
import os
from typing import Dict, Optional

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


class ObservabilityIntegration:
    """
    Manages OpenTelemetry setup for the RegOps platform.
    Configures traces, metrics, and instrumentation.
    """

    def __init__(
        self,
        service_name: str = "regops-platform",
        service_version: str = "1.0.0",
        environment: str = "production",
        tenant: Optional[str] = None,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.environment = environment
        self.tenant = tenant or "default"
        self.is_initialized = False

    def initialize(self) -> None:
        """
        Initialize OpenTelemetry with appropriate exporters.
        Must be called during application startup.
        """
        if self.is_initialized:
            logger.warning("ObservabilityIntegration already initialized")
            return

        try:
            # Create resource with service information
            resource = Resource.create({
                "service.name": self.service_name,
                "service.version": self.service_version,
                "service.namespace": "regops",
                "deployment.environment": self.environment,
                "regops.tenant": self.tenant,
                "regops.country": "BE",  # Belgian RegOps
            })

            # Initialize tracing
            self._setup_tracing(resource)
            
            # Initialize metrics
            self._setup_metrics(resource)
            
            # Setup auto-instrumentation
            self._setup_instrumentation()
            
            self.is_initialized = True
            logger.info(f"OpenTelemetry initialized for {self.service_name} ({self.environment})")
            
        except Exception as e:
            logger.error(f"Failed to initialize OpenTelemetry: {e}", exc_info=True)
            raise

    def _setup_tracing(self, resource: Resource) -> None:
        """Setup distributed tracing with appropriate exporter."""
        # Determine exporter based on environment
        if self.environment == "production":
            # Azure Application Insights
            endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
            if not endpoint:
                logger.warning("No Azure Application Insights endpoint configured")
                return
                
            span_exporter = OTLPSpanExporter(
                endpoint=endpoint,
                headers=self._get_azure_headers(),
            )
        else:
            # Local development - use OTLP to local collector or Jaeger
            span_exporter = OTLPSpanExporter(
                endpoint=os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://localhost:4317"),
                insecure=True,
            )

        # Create tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Add batch span processor
        span_processor = BatchSpanProcessor(
            span_exporter=span_exporter,
            max_queue_size=512,
            max_export_batch_size=64,
            export_timeout_millis=5000,
        )
        tracer_provider.add_span_processor(span_processor)

    def _setup_metrics(self, resource: Resource) -> None:
        """Setup metrics collection with appropriate exporter."""
        # Determine exporter based on environment
        if self.environment == "production":
            # Azure Application Insights
            endpoint = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
            if not endpoint:
                logger.warning("No Azure Application Insights metrics endpoint configured")
                return
                
            metric_exporter = OTLPMetricExporter(
                endpoint=endpoint,
                headers=self._get_azure_headers(),
            )
        else:
            # Local development
            metric_exporter = OTLPMetricExporter(
                endpoint=os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://localhost:4317"),
                insecure=True,
            )

        # Create metric reader with periodic export
        metric_reader = PeriodicExportingMetricReader(
            exporter=metric_exporter,
            export_interval_millis=30000,  # Export every 30 seconds
            export_timeout_millis=5000,
        )

        # Create meter provider
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        metrics.set_meter_provider(meter_provider)

    def _setup_instrumentation(self) -> None:
        """Setup automatic instrumentation for common libraries."""
        try:
            # HTTP client instrumentation (for Parallel.ai calls)
            HTTPXClientInstrumentor().instrument(
                tracer_provider=trace.get_tracer_provider(),
                meter_provider=metrics.get_meter_provider(),
            )
            
            # Redis instrumentation
            RedisInstrumentor().instrument(
                tracer_provider=trace.get_tracer_provider(),
            )
            
            # SQLAlchemy instrumentation  
            SQLAlchemyInstrumentor().instrument(
                tracer_provider=trace.get_tracer_provider(),
                enable_commenter=True,  # Add SQL comments with trace info
            )
            
            logger.info("Auto-instrumentation enabled for httpx, redis, sqlalchemy")
            
        except Exception as e:
            logger.error(f"Failed to setup auto-instrumentation: {e}")

    def _get_azure_headers(self) -> Dict[str, str]:
        """Get headers for Azure Application Insights."""
        headers = {}
        
        # Add Application Insights instrumentation key if available
        app_insights_key = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
        if app_insights_key:
            headers["Authorization"] = f"Bearer {app_insights_key}"
        
        return headers

    def create_tracer(self, name: str) -> trace.Tracer:
        """
        Create a tracer for a specific component.
        
        Args:
            name: Name of the component (e.g., "regops.parallel", "regops.cost")
            
        Returns:
            Configured tracer instance
        """
        return trace.get_tracer(name, version=self.service_version)

    def create_meter(self, name: str) -> metrics.Meter:
        """
        Create a meter for a specific component.
        
        Args:
            name: Name of the component (e.g., "regops.parallel", "regops.cost")
            
        Returns:
            Configured meter instance
        """
        return metrics.get_meter(name, version=self.service_version)

    def shutdown(self) -> None:
        """
        Shutdown OpenTelemetry providers.
        Should be called during application shutdown.
        """
        try:
            # Shutdown tracer provider
            tracer_provider = trace.get_tracer_provider()
            if hasattr(tracer_provider, 'shutdown'):
                tracer_provider.shutdown()
            
            # Shutdown meter provider
            meter_provider = metrics.get_meter_provider()
            if hasattr(meter_provider, 'shutdown'):
                meter_provider.shutdown()
                
            logger.info("OpenTelemetry shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during OpenTelemetry shutdown: {e}")


# Global integration instance
_global_integration: Optional[ObservabilityIntegration] = None


def initialize_observability(
    service_name: str = "regops-platform",
    service_version: str = "1.0.0", 
    environment: Optional[str] = None,
    tenant: Optional[str] = None,
) -> ObservabilityIntegration:
    """
    Initialize global observability integration.
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        environment: Deployment environment (defaults to DEPLOY_ENV env var)
        tenant: Tenant identifier
        
    Returns:
        Configured ObservabilityIntegration instance
    """
    global _global_integration
    
    if _global_integration is not None:
        logger.warning("Observability already initialized globally")
        return _global_integration
    
    # Default environment from env var
    if environment is None:
        environment = os.getenv("DEPLOY_ENV", "local")
    
    _global_integration = ObservabilityIntegration(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        tenant=tenant,
    )
    
    _global_integration.initialize()
    return _global_integration


def get_global_integration() -> Optional[ObservabilityIntegration]:
    """Get the global observability integration instance."""
    return _global_integration


def shutdown_observability() -> None:
    """Shutdown global observability integration."""
    global _global_integration
    
    if _global_integration is not None:
        _global_integration.shutdown()
        _global_integration = None


# Convenience functions for getting tracers and meters
def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for the given component name."""
    integration = get_global_integration()
    if integration:
        return integration.create_tracer(name)
    else:
        # Fallback to default tracer
        return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Get a meter for the given component name."""
    integration = get_global_integration()
    if integration:
        return integration.create_meter(name)
    else:
        # Fallback to default meter
        return metrics.get_meter(name)


# Context managers for tracking operations
class TrackedOperation:
    """
    Context manager for tracking operation duration and creating spans.
    """

    def __init__(
        self,
        operation_name: str,
        tracer: Optional[trace.Tracer] = None,
        attributes: Optional[Dict[str, str]] = None,
    ):
        self.operation_name = operation_name
        self.tracer = tracer or get_tracer("regops.operations")
        self.attributes = attributes or {}
        self.span = None
        self.start_time = None

    def __enter__(self):
        self.span = self.tracer.start_span(
            self.operation_name,
            attributes=self.attributes,
        )
        self.span.__enter__()
        
        # Record start time for duration tracking
        import time
        self.start_time = time.time()
        
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            # Add duration attribute
            if self.start_time:
                import time
                duration_ms = (time.time() - self.start_time) * 1000
                self.span.set_attribute("operation.duration_ms", duration_ms)
            
            # Mark span as error if exception occurred
            if exc_type is not None:
                self.span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc_val)))
                self.span.record_exception(exc_val)
            
            self.span.__exit__(exc_type, exc_val, exc_tb)

    def add_attribute(self, key: str, value: str) -> None:
        """Add attribute to the current span."""
        if self.span:
            self.span.set_attribute(key, value)

    def add_event(self, name: str, attributes: Optional[Dict[str, str]] = None) -> None:
        """Add event to the current span."""
        if self.span:
            self.span.add_event(name, attributes or {})