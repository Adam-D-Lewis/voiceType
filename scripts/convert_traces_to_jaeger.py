#!/usr/bin/env python3
"""
Convert OTLP JSONL trace files to Jaeger UI import format.

Usage:
    python convert_traces_to_jaeger.py ~/.config/voicetype/traces.jsonl -o jaeger_traces.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


def convert_to_jaeger_format(jsonl_file: Path) -> Dict[str, Any]:
    """
    Convert OTLP JSONL traces to Jaeger import format.

    Args:
        jsonl_file: Path to JSONL file with OTLP spans

    Returns:
        Dictionary in Jaeger import format
    """
    # Read all spans from JSONL file
    spans = []
    with open(jsonl_file, "r") as f:
        for line in f:
            if line.strip():
                spans.append(json.loads(line))

    # Group spans by trace_id
    traces_by_id: Dict[str, List[Dict]] = defaultdict(list)
    for span in spans:
        trace_id = span["context"]["trace_id"]
        traces_by_id[trace_id].append(span)

    # Convert each trace to Jaeger format
    jaeger_traces = []
    for trace_id, trace_spans in traces_by_id.items():
        # Build processes map (one per service)
        processes = {}
        service_name = (
            trace_spans[0]
            .get("resource", {})
            .get("attributes", {})
            .get("service.name", "unknown")
        )
        processes["p1"] = {"serviceName": service_name, "tags": []}

        # Convert spans to Jaeger format
        jaeger_spans = []
        for span in trace_spans:
            # Convert timestamps from nanoseconds to microseconds
            start_time_us = span["start_time"] // 1000
            duration_us = (span["end_time"] - span["start_time"]) // 1000

            # Convert attributes to tags
            tags = []
            for key, value in (span.get("attributes") or {}).items():
                tags.append({"key": key, "type": "string", "value": str(value)})

            # Add status as tag
            status_code = span.get("status", {}).get("status_code", "")
            if status_code:
                tags.append(
                    {"key": "otel.status_code", "type": "string", "value": status_code}
                )

            # Convert kind
            kind = span.get("kind", "SpanKind.INTERNAL")
            if "INTERNAL" in kind:
                span_kind = "internal"
            elif "CLIENT" in kind:
                span_kind = "client"
            elif "SERVER" in kind:
                span_kind = "server"
            else:
                span_kind = "internal"

            tags.append({"key": "span.kind", "type": "string", "value": span_kind})

            # Build references (parent relationships)
            references = []
            if span.get("parent_id"):
                references.append(
                    {
                        "refType": "CHILD_OF",
                        "traceID": trace_id,
                        "spanID": span["parent_id"],
                    }
                )

            # Convert events to logs
            logs = []
            for event in span.get("events") or []:
                fields = [{"key": "event", "type": "string", "value": event["name"]}]
                for key, value in (event.get("attributes") or {}).items():
                    fields.append({"key": key, "type": "string", "value": str(value)})
                logs.append(
                    {
                        "timestamp": event["timestamp"]
                        // 1000,  # Convert to microseconds
                        "fields": fields,
                    }
                )

            jaeger_span = {
                "traceID": trace_id,
                "spanID": span["context"]["span_id"],
                "operationName": span["name"],
                "references": references,
                "startTime": start_time_us,
                "duration": duration_us,
                "tags": tags,
                "logs": logs,
                "processID": "p1",
                "warnings": None,
                "flags": 1,
            }

            jaeger_spans.append(jaeger_span)

        # Create trace object
        jaeger_trace = {
            "traceID": trace_id,
            "spans": jaeger_spans,
            "processes": processes,
            "warnings": None,
        }

        jaeger_traces.append(jaeger_trace)

    # Return in Jaeger format
    return {"data": jaeger_traces}


def main():
    parser = argparse.ArgumentParser(
        description="Convert OTLP JSONL traces to Jaeger import format"
    )
    parser.add_argument("input", type=Path, help="Input JSONL file with OTLP traces")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output JSON file (default: input with .jaeger.json extension)",
    )

    args = parser.parse_args()

    # Determine output file
    if args.output is None:
        output_file = args.input.with_suffix(".jaeger.json")
    else:
        output_file = args.output

    print(f"Converting {args.input} to Jaeger format...")

    # Convert traces
    jaeger_data = convert_to_jaeger_format(args.input)

    # Write output
    with open(output_file, "w") as f:
        json.dump(jaeger_data, f, indent=2)

    trace_count = len(jaeger_data["data"])
    span_count = sum(len(trace["spans"]) for trace in jaeger_data["data"])

    print(f"✓ Converted {span_count} spans across {trace_count} trace(s)")
    print(f"✓ Written to: {output_file}")
    print(f"\nTo view in Jaeger UI:")
    print(f"1. Open http://localhost:16686")
    print(f"2. Click 'Upload JSON' in the top-right")
    print(f"3. Select: {output_file}")


if __name__ == "__main__":
    main()
