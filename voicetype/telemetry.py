"""
OpenTelemetry telemetry initialization and configuration.

This module provides utilities for initializing OpenTelemetry tracing to monitor
pipeline execution, stage performance, and resource utilization.
"""

from typing import Optional

from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Global tracer instance
_tracer: Optional[trace.Tracer] = None
_tracer_provider: Optional[TracerProvider] = None


def initialize_telemetry(
    service_name: str = "voicetype",
    otlp_endpoint: Optional[str] = None,
    enabled: bool = True,
) -> None:
    """
    Initialize OpenTelemetry tracing with OTLP exporter.

    Args:
        service_name: Name of the service for tracing (default: "voicetype")
        otlp_endpoint: OTLP collector endpoint (default: "http://localhost:4317")
        enabled: Whether to enable telemetry (default: True)
    """
    global _tracer, _tracer_provider

    if not enabled:
        logger.info("Telemetry disabled")
        return

    # Default to local Jaeger OTLP endpoint
    if otlp_endpoint is None:
        otlp_endpoint = "http://localhost:4317"

    try:
        # Create resource with service name
        resource = Resource(attributes={SERVICE_NAME: service_name})

        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)

        # Create OTLP exporter
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)

        # Add batch span processor
        span_processor = BatchSpanProcessor(otlp_exporter)
        _tracer_provider.add_span_processor(span_processor)

        # Set global tracer provider
        trace.set_tracer_provider(_tracer_provider)

        # Get tracer instance
        _tracer = trace.get_tracer(__name__)

        logger.info(
            f"Telemetry initialized: service={service_name}, endpoint={otlp_endpoint}"
        )
    except Exception as e:
        logger.warning(f"Failed to initialize telemetry: {e}. Continuing without tracing.")
        _tracer = None
        _tracer_provider = None


def get_tracer() -> Optional[trace.Tracer]:
    """
    Get the global tracer instance.

    Returns:
        The tracer instance, or None if telemetry is not initialized
    """
    return _tracer


def shutdown_telemetry() -> None:
    """Shutdown telemetry and flush any pending spans."""
    global _tracer_provider

    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("Telemetry shutdown complete")
        except Exception as e:
            logger.warning(f"Error during telemetry shutdown: {e}")
        finally:
            _tracer_provider = None
