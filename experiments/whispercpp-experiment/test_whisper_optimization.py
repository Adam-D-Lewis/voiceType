"""
Optimize Whisper.cpp performance by testing small models with different thread counts.

This script focuses on:
1. Testing tiny, base, and small models only (fastest models)
2. Varying n_threads parameter (1, 2, 4, 6, 8, 12) to find optimal setting
3. Comparing pywhispercpp vs faster-whisper for these small models
4. Running multiple iterations to get statistical performance data

Goal: Find the fastest configuration for real-time transcription.

Usage:
    python test_whisper_optimization.py
    python test_whisper_optimization.py --runs 5  # Run each config 5 times
    python test_whisper_optimization.py --runs 3 --threads 1,2,4,8  # Custom threads
"""

import argparse
import os
import random
import statistics
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Test audio file
SCRIPT_DIR = Path(__file__).parent
TEST_AUDIO = str(SCRIPT_DIR / "jumping-jacks-champion.wav")

# Fallback to other locations if not found
if not Path(TEST_AUDIO).exists():
    PROJECT_ROOT = SCRIPT_DIR.parent.parent
    TEST_AUDIO = str(
        PROJECT_ROOT
        / "experiments"
        / "whispercpp-experiment"
        / "jumping-jacks-champion.wav"
    )


class BenchmarkResult:
    """Store benchmark results for comparison."""

    def __init__(
        self,
        backend: str,
        model_size: str,
        transcription: str,
        duration: float,
        n_threads: Optional[int] = None,
        error: Optional[str] = None,
    ):
        self.backend = backend
        self.model_size = model_size
        self.transcription = transcription
        self.duration = duration
        self.n_threads = n_threads
        self.error = error

    def __repr__(self):
        status = "ERROR" if self.error else "OK"
        threads_str = f" [{self.n_threads}t]" if self.n_threads else ""
        return (
            f"[{status}] {self.backend}{threads_str} ({self.model_size}): "
            f"{self.duration:.3f}s - '{self.transcription[:60]}...'"
        )


class AggregatedResult:
    """Store aggregated results from multiple runs."""

    def __init__(
        self,
        backend: str,
        model_size: str,
        durations: List[float],
        n_threads: Optional[int] = None,
        transcription: str = "",
        error_count: int = 0,
    ):
        self.backend = backend
        self.model_size = model_size
        self.durations = durations
        self.n_threads = n_threads
        self.transcription = transcription
        self.error_count = error_count

        # Calculate statistics
        if durations:
            self.mean = statistics.mean(durations)
            self.median = statistics.median(durations)
            self.min = min(durations)
            self.max = max(durations)
            self.stdev = statistics.stdev(durations) if len(durations) > 1 else 0
        else:
            self.mean = self.median = self.min = self.max = self.stdev = 0

    def __repr__(self):
        threads_str = f" [{self.n_threads}t]" if self.n_threads else ""
        return (
            f"{self.backend}{threads_str} ({self.model_size}): "
            f"mean={self.mean:.3f}s ±{self.stdev:.3f}s "
            f"[min={self.min:.3f}s, max={self.max:.3f}s]"
        )


def test_pywhispercpp_with_threads(
    audio_file: str, model_size: str = "tiny.en", n_threads: int = 4
) -> BenchmarkResult:
    """Test pywhispercpp backend with specific thread count."""
    temp_file = None
    try:
        from pydub import AudioSegment
        from pywhispercpp.model import Model

        # pywhispercpp requires 16kHz WAV, so convert if needed
        audio = AudioSegment.from_file(audio_file)

        # Convert to 16kHz mono if needed
        if audio.frame_rate != 16000 or audio.channels != 1:
            audio = audio.set_frame_rate(16000).set_channels(1)

            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            audio.export(temp_file.name, format="wav")
            audio_file_to_use = temp_file.name
        else:
            audio_file_to_use = audio_file

        start = time.time()

        # Suppress verbose whisper.cpp logs
        model = Model(
            model_size,
            n_threads=n_threads,
            print_realtime=False,
            print_progress=False,
            redirect_whispercpp_logs_to=None,
        )
        segments = model.transcribe(audio_file_to_use)

        # Combine all segments
        transcription = " ".join([segment.text for segment in segments])

        duration = time.time() - start
        return BenchmarkResult(
            backend="pywhispercpp",
            model_size=model_size,
            transcription=transcription.strip(),
            duration=duration,
            n_threads=n_threads,
        )

    except Exception as e:
        return BenchmarkResult(
            backend="pywhispercpp",
            model_size=model_size,
            transcription="",
            duration=0,
            n_threads=n_threads,
            error=str(e),
        )
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass


def test_faster_whisper_cpu(
    audio_file: str, model_size: str = "tiny.en"
) -> BenchmarkResult:
    """Test faster-whisper backend on CPU."""
    try:
        import speech_recognition as sr
        from speech_recognition.recognizers.whisper_local import faster_whisper

        start = time.time()

        audio = sr.AudioData.from_file(audio_file)

        transcribed_text = faster_whisper.recognize(
            None,
            audio_data=audio,
            model=model_size,
            language="en",
            init_options=faster_whisper.InitOptionalParameters(
                device="cpu",
                compute_type="int8",
            ),
        )

        duration = time.time() - start
        return BenchmarkResult(
            backend="faster-whisper",
            model_size=model_size,
            transcription=transcribed_text.strip(),
            duration=duration,
        )

    except Exception as e:
        return BenchmarkResult(
            backend="faster-whisper",
            model_size=model_size,
            transcription="",
            duration=0,
            error=str(e),
        )


def aggregate_results(results: List[BenchmarkResult]) -> List[AggregatedResult]:
    """Aggregate multiple benchmark results by configuration.

    Args:
        results: List of individual benchmark results

    Returns:
        List of aggregated results with statistics
    """
    # Group results by configuration
    config_groups: Dict[tuple, List[BenchmarkResult]] = {}

    for result in results:
        key = (result.backend, result.model_size, result.n_threads)
        if key not in config_groups:
            config_groups[key] = []
        config_groups[key].append(result)

    # Create aggregated results
    aggregated = []
    for (backend, model_size, n_threads), group_results in config_groups.items():
        successful = [r for r in group_results if not r.error]
        errors = [r for r in group_results if r.error]

        if successful:
            durations = [r.duration for r in successful]
            transcription = successful[
                0
            ].transcription  # Use first successful transcription
            aggregated.append(
                AggregatedResult(
                    backend=backend,
                    model_size=model_size,
                    durations=durations,
                    n_threads=n_threads,
                    transcription=transcription,
                    error_count=len(errors),
                )
            )

    return aggregated


def run_optimization_benchmarks(
    audio_file: str,
    num_runs: int = 5,
    thread_counts: List[int] = None,
    models: List[str] = None,
) -> List[BenchmarkResult]:
    """Run optimization benchmarks focusing on small models and thread counts.

    Args:
        audio_file: Path to audio file to test
        num_runs: Number of times to run each configuration
        thread_counts: List of thread counts to test (default: [1, 2, 4])
        models: List of model names to test (default: ["tiny.en", "base.en"])
    """
    results = []

    print("=" * 80)
    print("WHISPER.CPP OPTIMIZATION BENCHMARKS")
    print("=" * 80)
    print(f"Test audio: {audio_file}")
    print(f"Runs per configuration: {num_runs}")
    print()

    # Check if file exists
    if not Path(audio_file).exists():
        print(f"ERROR: Audio file not found: {audio_file}")
        return results

    # Model sizes to test
    if models is None:
        models = ["tiny.en", "base.en"]

    # Thread counts to test
    if thread_counts is None:
        thread_counts = [1, 2, 4]

    # Build all test configurations
    test_configs: List[Tuple[str, str, Optional[int], int]] = []

    # pywhispercpp configurations
    for model in models:
        for n_threads in thread_counts:
            for run_num in range(num_runs):
                test_configs.append(("pywhispercpp", model, n_threads, run_num))

    # faster-whisper configurations
    for model in models:
        for run_num in range(num_runs):
            test_configs.append(("faster-whisper", model, None, run_num))

    # Randomize test order
    random.shuffle(test_configs)

    total_tests = len(test_configs)

    print(f"Running {total_tests} tests in randomized order...")
    print("-" * 80)

    # Run all tests in randomized order
    for idx, (backend, model, n_threads, run_num) in enumerate(test_configs, 1):
        if backend == "pywhispercpp":
            config_name = f"{backend} ({model}, {n_threads} threads)"
            print(
                f"[{idx}/{total_tests}] {config_name} - Run {run_num + 1}/{num_runs}...",
                end=" ",
                flush=True,
            )
            result = test_pywhispercpp_with_threads(audio_file, model, n_threads)
        else:  # faster-whisper
            config_name = f"{backend} ({model})"
            print(
                f"[{idx}/{total_tests}] {config_name} - Run {run_num + 1}/{num_runs}...",
                end=" ",
                flush=True,
            )
            result = test_faster_whisper_cpu(audio_file, model)

        results.append(result)

        if result.error:
            print(f"ERROR: {result.error}")
        else:
            print(f"{result.duration:.3f}s")

    print("\nAll tests complete!")
    return results


def print_optimization_summary(results: List[BenchmarkResult]):
    """Print summary of optimization results with statistics."""
    print("\n" + "=" * 80)
    print("OPTIMIZATION SUMMARY (Statistical Analysis)")
    print("=" * 80)

    # Aggregate results
    aggregated = aggregate_results(results)

    if not aggregated:
        print("No successful tests to compare.")
        return

    # Overall fastest (by mean)
    fastest = min(aggregated, key=lambda x: x.mean)
    print(f"\nFASTEST OVERALL (by mean):")
    threads_str = f" with {fastest.n_threads} threads" if fastest.n_threads else ""
    print(f"  {fastest.backend} ({fastest.model_size}){threads_str}")
    print(f"  Mean: {fastest.mean:.3f}s ± {fastest.stdev:.3f}s")
    print(f"  Range: [{fastest.min:.3f}s - {fastest.max:.3f}s]")
    print(f"  Transcription: '{fastest.transcription}'")

    # pywhispercpp analysis
    pywhisper_results = [r for r in aggregated if r.backend == "pywhispercpp"]
    if pywhisper_results:
        print("\n" + "-" * 80)
        print("PYWHISPERCPP ANALYSIS (by model):")
        print("-" * 80)

        for model in ["tiny.en", "base.en", "small.en"]:
            model_results = [r for r in pywhisper_results if r.model_size == model]
            if model_results:
                print(f"\n{model.upper()}:")
                model_results.sort(key=lambda x: x.mean)

                fastest_for_model = model_results[0]
                slowest_for_model = model_results[-1]

                print(
                    f"  Fastest: {fastest_for_model.n_threads} threads = "
                    f"{fastest_for_model.mean:.3f}s ± {fastest_for_model.stdev:.3f}s"
                )
                print(
                    f"  Slowest: {slowest_for_model.n_threads} threads = "
                    f"{slowest_for_model.mean:.3f}s ± {slowest_for_model.stdev:.3f}s"
                )
                print(
                    f"  Speedup: {slowest_for_model.mean / fastest_for_model.mean:.2f}x"
                )

                print(f"\n  All thread counts (by mean, fastest to slowest):")
                for r in model_results:
                    speedup = fastest_for_model.mean / r.mean if r.mean > 0 else 0
                    slower_str = (
                        f" ({1/speedup:.2f}x slower)" if speedup < 1 else " (fastest)"
                    )
                    cv = (
                        (r.stdev / r.mean * 100) if r.mean > 0 else 0
                    )  # Coefficient of variation
                    print(
                        f"    {r.n_threads:2d} threads: {r.mean:.3f}s ± {r.stdev:.3f}s "
                        f"(CV: {cv:.1f}%){slower_str}"
                    )

    # Comparison: pywhispercpp vs faster-whisper
    faster_whisper_results = [r for r in aggregated if r.backend == "faster-whisper"]
    if pywhisper_results and faster_whisper_results:
        print("\n" + "-" * 80)
        print("BACKEND COMPARISON:")
        print("-" * 80)

        for model in ["tiny.en", "base.en", "small.en"]:
            fw_result = next(
                (r for r in faster_whisper_results if r.model_size == model), None
            )
            pw_results = [r for r in pywhisper_results if r.model_size == model]

            if fw_result and pw_results:
                fastest_pw = min(pw_results, key=lambda x: x.mean)
                print(f"\n{model.upper()}:")
                print(
                    f"  faster-whisper (CPU): {fw_result.mean:.3f}s ± {fw_result.stdev:.3f}s"
                )
                print(
                    f"  pywhispercpp ({fastest_pw.n_threads} threads): "
                    f"{fastest_pw.mean:.3f}s ± {fastest_pw.stdev:.3f}s"
                )

                if fastest_pw.mean < fw_result.mean:
                    speedup = fw_result.mean / fastest_pw.mean
                    print(f"  → pywhispercpp is {speedup:.2f}x FASTER")
                else:
                    slowdown = fastest_pw.mean / fw_result.mean
                    print(f"  → faster-whisper is {slowdown:.2f}x faster")

    # Most consistent (lowest coefficient of variation)
    results_with_variance = [r for r in aggregated if r.stdev > 0 and r.mean > 0]
    if results_with_variance:
        print("\n" + "-" * 80)
        print("MOST CONSISTENT PERFORMANCE (lowest variability):")
        print("-" * 80)

        # Calculate coefficient of variation (CV = stdev/mean * 100)
        for r in results_with_variance:
            r.cv = (r.stdev / r.mean) * 100

        results_with_variance.sort(key=lambda x: x.cv)

        for i, r in enumerate(results_with_variance[:5], 1):
            threads_str = f" [{r.n_threads}t]" if r.n_threads else ""
            print(
                f"{i}. {r.backend}{threads_str} ({r.model_size}): "
                f"CV={r.cv:.1f}% (mean={r.mean:.3f}s ± {r.stdev:.3f}s)"
            )

    # Recommendations
    print("\n" + "=" * 80)
    print("RECOMMENDATIONS:")
    print("=" * 80)

    if pywhisper_results:
        # Find best configuration for each model
        for model in ["tiny.en", "base.en", "small.en"]:
            model_results = [r for r in pywhisper_results if r.model_size == model]
            if model_results:
                best = min(model_results, key=lambda x: x.mean)
                print(
                    f"\nFor {model}: Use {best.n_threads} threads "
                    f"({best.mean:.3f}s ± {best.stdev:.3f}s)"
                )

        # Overall recommendation
        overall_best = min(pywhisper_results, key=lambda x: x.mean)
        print(f"\n🏆 RECOMMENDED CONFIGURATION (fastest on average):")
        print(f"   Backend: pywhispercpp")
        print(f"   Model: {overall_best.model_size}")
        print(f"   Threads: {overall_best.n_threads}")
        print(f"   Mean speed: {overall_best.mean:.3f}s ± {overall_best.stdev:.3f}s")
        print(f"   Range: [{overall_best.min:.3f}s - {overall_best.max:.3f}s]")
        print(f"   Transcription: '{overall_best.transcription}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Optimize Whisper.cpp performance by testing thread counts"
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of times to run each configuration (default: 5)",
    )
    parser.add_argument(
        "--threads",
        type=str,
        default="1,2,4",
        help="Comma-separated list of thread counts to test (default: 1,2,4)",
    )
    parser.add_argument(
        "--models",
        type=str,
        default="tiny.en,base.en",
        help="Comma-separated list of models to test (default: tiny.en,base.en)",
    )
    args = parser.parse_args()

    # Parse thread counts if provided
    thread_counts = None
    if args.threads:
        thread_counts = [int(t.strip()) for t in args.threads.split(",")]

    # Parse models if provided
    models = None
    if args.models:
        models = [m.strip() for m in args.models.split(",")]

    results = run_optimization_benchmarks(
        TEST_AUDIO, num_runs=args.runs, thread_counts=thread_counts, models=models
    )
    print_optimization_summary(results)
