#!/usr/bin/env python3
"""Analyze voicetype traces to compare LLM and transcription performance."""

import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_TRACE_FILE = Path.home() / ".config" / "voicetype" / "traces.jsonl"

# Filter out no-op durations (under 10ms usually means skipped)
MIN_DURATION_THRESHOLD_MS = 10.0


def load_traces(trace_file: Path) -> list[dict]:
    """Load and parse traces from JSONL file."""
    traces = []
    with open(trace_file, "r") as f:
        for line in f:
            try:
                traces.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return traces


def analyze_llm_models(
    traces: list[dict], min_duration: float = MIN_DURATION_THRESHOLD_MS
):
    """Analyze LLM stage performance by model."""
    models = defaultdict(list)

    for span in traces:
        attrs = span.get("attributes", {})
        if attrs.get("stage.name") != "LLMAgent":
            continue

        duration = attrs.get("stage.duration_ms", 0)
        if duration < min_duration:
            continue

        model = attrs.get("stage.config.model", "unknown")
        models[model].append(
            {
                "duration_ms": duration,
                "timestamp": span.get("start_time", 0),
                "status": span.get("status", {}).get("status_code", "unknown"),
            }
        )

    return models


def analyze_transcribe(
    traces: list[dict], min_duration: float = MIN_DURATION_THRESHOLD_MS
):
    """Analyze Transcribe stage performance by provider/model."""
    providers = defaultdict(list)

    for span in traces:
        attrs = span.get("attributes", {})
        if attrs.get("stage.name") != "Transcribe":
            continue

        duration = attrs.get("stage.duration_ms", 0)
        if duration < min_duration:
            continue

        provider = attrs.get("stage.config.provider", "unknown")
        model = attrs.get("stage.config.model", "default")
        device = attrs.get("stage.config.device", "")

        key = f"{provider}/{model}"
        if device:
            key += f" ({device})"

        providers[key].append(
            {
                "duration_ms": duration,
                "timestamp": span.get("start_time", 0),
                "status": span.get("status", {}).get("status_code", "unknown"),
            }
        )

    return providers


def compute_stats(entries: list[dict]) -> dict:
    """Compute statistics for a list of duration entries."""
    durations = [e["duration_ms"] for e in entries]
    if not durations:
        return {}

    return {
        "count": len(durations),
        "mean": statistics.mean(durations),
        "median": statistics.median(durations),
        "stdev": statistics.stdev(durations) if len(durations) > 1 else 0,
        "min": min(durations),
        "max": max(durations),
        "p90": (
            statistics.quantiles(durations, n=10)[8]
            if len(durations) >= 10
            else max(durations)
        ),
        "p95": (
            statistics.quantiles(durations, n=20)[18]
            if len(durations) >= 20
            else max(durations)
        ),
    }


def format_duration(ms: float) -> str:
    """Format duration in human-readable form."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms/1000:.2f}s"


def print_comparison_table(data: dict[str, list], title: str):
    """Print a comparison table for different models/providers."""
    print(f"\n{'=' * 80}")
    print(f" {title}")
    print(f"{'=' * 80}")

    if not data:
        print("No data found.")
        return

    # Sort by median duration
    sorted_items = sorted(
        [(k, compute_stats(v)) for k, v in data.items() if v],
        key=lambda x: x[1].get("median", float("inf")),
    )

    # Header
    print(
        f"{'Model/Provider':<40} {'Count':>8} {'Median':>10} {'Mean':>10} {'P90':>10} {'P95':>10}"
    )
    print("-" * 80)

    for name, stats in sorted_items:
        if not stats:
            continue
        print(
            f"{name:<40} "
            f"{stats['count']:>8} "
            f"{format_duration(stats['median']):>10} "
            f"{format_duration(stats['mean']):>10} "
            f"{format_duration(stats['p90']):>10} "
            f"{format_duration(stats['p95']):>10}"
        )

    print()


def export_to_csv(data: dict[str, list], filename: str, category: str):
    """Export detailed data to CSV for further analysis."""
    with open(filename, "w") as f:
        f.write(f"category,model_provider,duration_ms,timestamp_ns,status\n")
        for name, entries in data.items():
            for entry in entries:
                f.write(
                    f"{category},{name},{entry['duration_ms']},{entry['timestamp']},{entry['status']}\n"
                )
    print(f"Exported to {filename}")


def convert_to_jaeger_format(traces: list[dict], output_file: Path):
    """Convert traces to Jaeger-compatible JSON format.

    Jaeger UI can import traces via the /api/traces endpoint or the UI.
    This format matches what Jaeger exports.
    """
    # Group spans by trace_id
    trace_groups = defaultdict(list)
    for span in traces:
        trace_id = span.get("context", {}).get("trace_id", "")
        if trace_id:
            trace_groups[trace_id].append(span)

    jaeger_traces = []
    for trace_id, spans in trace_groups.items():
        jaeger_spans = []
        process_id = "p1"

        for span in spans:
            ctx = span.get("context", {})
            attrs = span.get("attributes", {})

            # Convert nanoseconds to microseconds (Jaeger uses microseconds)
            start_time = span.get("start_time", 0) // 1000
            end_time = span.get("end_time", 0) // 1000
            duration = end_time - start_time

            # Convert attributes to Jaeger tags format
            tags = [
                {"key": k, "type": "string", "value": str(v)} for k, v in attrs.items()
            ]

            # Add status as tag
            status = span.get("status", {})
            if status.get("status_code"):
                tags.append(
                    {
                        "key": "otel.status_code",
                        "type": "string",
                        "value": status["status_code"],
                    }
                )
            if status.get("description"):
                tags.append(
                    {
                        "key": "otel.status_description",
                        "type": "string",
                        "value": status["description"],
                    }
                )

            jaeger_span = {
                "traceID": ctx.get("trace_id", ""),
                "spanID": ctx.get("span_id", ""),
                "operationName": span.get("name", ""),
                "references": [],
                "startTime": start_time,
                "duration": duration,
                "tags": tags,
                "logs": [],
                "processID": process_id,
            }

            # Add parent reference if exists
            parent_id = span.get("parent_id")
            if parent_id:
                jaeger_span["references"].append(
                    {
                        "refType": "CHILD_OF",
                        "traceID": ctx.get("trace_id", ""),
                        "spanID": parent_id,
                    }
                )

            jaeger_spans.append(jaeger_span)

        if jaeger_spans:
            jaeger_traces.append(
                {
                    "traceID": trace_id,
                    "spans": jaeger_spans,
                    "processes": {
                        process_id: {
                            "serviceName": "voicetype",
                            "tags": [],
                        }
                    },
                    "warnings": None,
                }
            )

    output = {"data": jaeger_traces}
    with open(output_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Converted {len(jaeger_traces)} traces to Jaeger format: {output_file}")
    print(
        f"Import in Jaeger UI: Upload at http://localhost:16686/search -> JSON File tab"
    )


def main():
    # Parse trace file from args (skip flags starting with --)
    trace_file = DEFAULT_TRACE_FILE
    for arg in sys.argv[1:]:
        if not arg.startswith("--") and not arg.startswith("-"):
            trace_file = Path(arg)
            break

    if not trace_file.exists():
        print(f"Error: Trace file not found: {trace_file}")
        print(f"Enable telemetry in settings.toml and run some pipelines first.")
        sys.exit(1)

    print(f"Loading traces from: {trace_file}")
    traces = load_traces(trace_file)
    print(f"Loaded {len(traces)} spans")

    # Analyze LLM models
    llm_data = analyze_llm_models(traces)
    print_comparison_table(llm_data, "LLM Agent Performance by Model")

    # Analyze transcription
    transcribe_data = analyze_transcribe(traces)
    print_comparison_table(
        transcribe_data, "Transcription Performance by Provider/Model"
    )

    # Overall pipeline stats
    pipeline_spans = [
        s
        for s in traces
        if s.get("name", "").startswith("pipeline.")
        and s.get("attributes", {}).get("pipeline.duration_ms", 0)
        > MIN_DURATION_THRESHOLD_MS
    ]
    if pipeline_spans:
        durations = [s["attributes"]["pipeline.duration_ms"] for s in pipeline_spans]
        stats = compute_stats([{"duration_ms": d} for d in durations])
        print(f"\n{'=' * 80}")
        print(f" Overall Pipeline Performance")
        print(f"{'=' * 80}")
        print(f"Total runs: {stats['count']}")
        print(f"Median: {format_duration(stats['median'])}")
        print(f"Mean: {format_duration(stats['mean'])}")
        print(f"P90: {format_duration(stats['p90'])}")
        print(f"P95: {format_duration(stats['p95'])}")

    # Option to export CSV
    if "--export" in sys.argv:
        export_to_csv(llm_data, "llm_traces.csv", "llm")
        export_to_csv(transcribe_data, "transcribe_traces.csv", "transcribe")

    # Option to convert to Jaeger format
    if "--jaeger" in sys.argv:
        jaeger_output = Path("voicetype_traces_jaeger.json")
        convert_to_jaeger_format(traces, jaeger_output)


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: analyze_traces.py [trace_file] [options]")
        print()
        print("Options:")
        print(
            "  --export    Export data to CSV files (llm_traces.csv, transcribe_traces.csv)"
        )
        print("  --jaeger    Convert traces to Jaeger-compatible JSON format")
        print("  -h, --help  Show this help message")
        print()
        print("Example:")
        print("  python scripts/analyze_traces.py")
        print(
            "  python scripts/analyze_traces.py ~/.config/voicetype/traces.jsonl --jaeger"
        )
        sys.exit(0)
    main()
