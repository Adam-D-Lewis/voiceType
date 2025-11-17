"""
OpenTelemetry telemetry initialization and configuration.

This module provides utilities for initializing OpenTelemetry tracing to monitor
pipeline execution, stage performance, and resource utilization.

Supports multiple export modes:
- OTLP: Send traces to Jaeger/OTEL collector (requires running collector)
- File: Export traces to JSON files for offline viewing
- Both: Export to both OTLP and files simultaneously
"""

import json
import os
from pathlib import Path
from typing import IO, Optional, Sequence

from loguru import logger
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

# Global tracer instance
_tracer: Optional[trace.Tracer] = None
_tracer_provider: Optional[TracerProvider] = None


class OTLPJSONFileExporter(SpanExporter):
    """
    Exports spans to a JSON Lines file in OTLP JSON format.

    Each line in the file is a valid JSON object representing span data
    that can be imported by OpenTelemetry-compatible tools.
    """

    def __init__(self, file_handle: IO[str], resource: Resource):
        """
        Initialize the JSON file exporter.

        Args:
            file_handle: Open file handle to write JSON lines to
            resource: Resource information (service name, etc.)
        """
        self.file_handle = file_handle
        self.resource = resource

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """
        Export spans to the file in OTLP JSON format.

        Args:
            spans: Sequence of spans to export

        Returns:
            SpanExportResult indicating success or failure
        """
        if not spans:
            return SpanExportResult.SUCCESS

        try:
            for span in spans:
                # Convert span to OTLP-compatible JSON format
                span_data = {
                    "name": span.name,
                    "context": {
                        "trace_id": format(span.context.trace_id, "032x"),
                        "span_id": format(span.context.span_id, "016x"),
                        "trace_state": (
                            str(span.context.trace_state)
                            if span.context.trace_state
                            else ""
                        ),
                    },
                    "kind": str(span.kind),
                    "parent_id": (
                        format(span.parent.span_id, "016x") if span.parent else None
                    ),
                    "start_time": span.start_time,
                    "end_time": span.end_time,
                    "status": {
                        "status_code": str(span.status.status_code),
                        "description": span.status.description,
                    },
                    "attributes": dict(span.attributes) if span.attributes else {},
                    "events": [
                        {
                            "name": event.name,
                            "timestamp": event.timestamp,
                            "attributes": (
                                dict(event.attributes) if event.attributes else {}
                            ),
                        }
                        for event in (span.events or [])
                    ],
                    "links": [
                        {
                            "context": {
                                "trace_id": format(link.context.trace_id, "032x"),
                                "span_id": format(link.context.span_id, "016x"),
                            },
                            "attributes": (
                                dict(link.attributes) if link.attributes else {}
                            ),
                        }
                        for link in (span.links or [])
                    ],
                    "resource": {
                        "attributes": (
                            dict(self.resource.attributes)
                            if self.resource.attributes
                            else {}
                        ),
                    },
                }

                # Write as single line JSON (JSONL format)
                json_line = json.dumps(span_data, default=str)
                self.file_handle.write(json_line + "\n")
                self.file_handle.flush()

            return SpanExportResult.SUCCESS
        except Exception as e:
            logger.error(f"Failed to export spans to JSON file: {e}")
            return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        """Shutdown the exporter and close the file."""
        try:
            self.file_handle.close()
        except Exception as e:
            logger.warning(f"Error closing trace file: {e}")


def _get_trace_file_path(trace_file: Optional[str] = None) -> Path:
    """Get the path to the trace export file.

    Args:
        trace_file: Optional custom path. If None, uses platform defaults.

    Returns:
        Path to the trace file
    """
    import sys

    if trace_file is not None:
        return Path(trace_file).expanduser().resolve()

    # Use platform-specific default locations
    if sys.platform == "win32":
        config_dir = (
            Path(os.environ.get("APPDATA", "~/.config")).expanduser() / "voicetype"
        )
    elif sys.platform == "darwin":
        config_dir = Path.home() / "Library" / "Application Support" / "voicetype"
    else:  # Linux and other Unix-like systems
        config_dir = (
            Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
            / "voicetype"
        )

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "traces.jsonl"


def initialize_telemetry(
    service_name: str = "voicetype",
    otlp_endpoint: Optional[str] = None,
    export_to_file: bool = True,
    trace_file: Optional[str] = None,
    enabled: bool = True,
) -> None:
    """
    Initialize OpenTelemetry tracing with configurable exporters.

    Args:
        service_name: Name of the service for tracing (default: "voicetype")
        otlp_endpoint: OTLP collector endpoint (default: None, disables OTLP export)
        export_to_file: Whether to export traces to a file (default: True)
        trace_file: Custom path for trace file (default: platform-specific)
        enabled: Whether to enable telemetry (default: True)

    Export modes (default: file export only):
        - enabled=False: Telemetry completely disabled
        - export_to_file=True (default): Export to file
        - otlp_endpoint set: Also send to OTLP collector
        - export_to_file=False, otlp_endpoint set: OTLP only (no file)
    """
    global _tracer, _tracer_provider

    if not enabled:
        logger.info("Telemetry disabled")
        return

    if not otlp_endpoint and not export_to_file:
        logger.warning(
            "Telemetry enabled but no exporters configured. "
            "Set otlp_endpoint or export_to_file=true"
        )
        return

    try:
        # Create resource with service name
        resource = Resource(attributes={SERVICE_NAME: service_name})

        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)

        exporters_configured = []

        # Add OTLP exporter if endpoint is configured
        if otlp_endpoint:
            try:
                otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
                otlp_processor = BatchSpanProcessor(otlp_exporter)
                _tracer_provider.add_span_processor(otlp_processor)
                exporters_configured.append(f"OTLP({otlp_endpoint})")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize OTLP exporter to {otlp_endpoint}: {e}. "
                    "Traces will not be sent to collector."
                )

        # Add file exporter if enabled
        if export_to_file:
            try:
                trace_file_path = _get_trace_file_path(trace_file)
                # Ensure parent directory exists
                trace_file_path.parent.mkdir(parents=True, exist_ok=True)

                # Open file in append mode
                trace_file_handle = open(trace_file_path, "a", encoding="utf-8")

                # Use our custom OTLP JSON exporter
                # This writes proper OTLP JSON format, one span per line (JSONL format)
                file_exporter = OTLPJSONFileExporter(
                    file_handle=trace_file_handle, resource=resource
                )
                file_processor = BatchSpanProcessor(file_exporter)
                _tracer_provider.add_span_processor(file_processor)
                exporters_configured.append(f"File({trace_file_path})")

                logger.info(f"Traces will be exported to: {trace_file_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize file exporter: {e}. "
                    "Traces will not be saved to file."
                )

        if not exporters_configured:
            logger.warning("No trace exporters were successfully initialized")
            _tracer = None
            _tracer_provider = None
            return

        # Set global tracer provider
        trace.set_tracer_provider(_tracer_provider)

        # Get tracer instance
        _tracer = trace.get_tracer(__name__)

        logger.info(
            f"Telemetry initialized: service={service_name}, "
            f"exporters={', '.join(exporters_configured)}"
        )
    except Exception as e:
        logger.warning(
            f"Failed to initialize telemetry: {e}. Continuing without tracing."
        )
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
