"""
Experiment to compare different Whisper backends and configurations.

This script tests:
1. faster-whisper with CUDA (current implementation)
2. faster-whisper with CPU
3. pywhispercpp with CPU
4. Different model sizes (tiny, base, small, medium, large-v3-turbo)

Run this to explore CPU-only options for better portability.

Usage:
    python test_whisper_backends.py           # Run all tests (GPU + CPU)
    python test_whisper_backends.py --cpu-only  # Run CPU tests only
"""

import argparse
import contextlib
import os
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional

# Test audio file - using the jumping-jacks-champion WAV file for a longer, more realistic test
# Adjust path based on where script is run from
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
        device: str,
        model_size: str,
        transcription: str,
        duration: float,
        error: Optional[str] = None,
        similarity_score: Optional[float] = None,
    ):
        self.backend = backend
        self.device = device
        self.model_size = model_size
        self.transcription = transcription
        self.duration = duration
        self.error = error
        self.similarity_score = similarity_score

    def __repr__(self):
        status = "ERROR" if self.error else "OK"
        score_str = (
            f" (similarity: {self.similarity_score:.1%})"
            if self.similarity_score is not None
            else ""
        )
        return (
            f"[{status}] {self.backend} ({self.device}, {self.model_size}): "
            f"{self.duration:.3f}s{score_str} - '{self.transcription}'"
        )


def test_faster_whisper(
    audio_file: str, device: str = "cuda", model_size: str = "large-v3-turbo"
) -> BenchmarkResult:
    """Test faster-whisper backend (current implementation)."""
    try:
        import speech_recognition as sr
        from speech_recognition.recognizers.whisper_local import faster_whisper

        start = time.time()

        audio = sr.AudioData.from_file(audio_file)

        compute_type = "float16" if device == "cuda" else "int8"

        transcribed_text = faster_whisper.recognize(
            None,
            audio_data=audio,
            model=model_size,
            language="en",
            init_options=faster_whisper.InitOptionalParameters(
                device=device,
                compute_type=compute_type,
            ),
        )

        duration = time.time() - start
        return BenchmarkResult(
            backend="faster-whisper",
            device=device,
            model_size=model_size,
            transcription=transcribed_text.strip(),
            duration=duration,
        )

    except Exception as e:
        return BenchmarkResult(
            backend="faster-whisper",
            device=device,
            model_size=model_size,
            transcription="",
            duration=0,
            error=str(e),
        )


def test_pywhispercpp(audio_file: str, model_size: str = "base.en") -> BenchmarkResult:
    """Test pywhispercpp backend (CPU-optimized)."""
    import tempfile

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
            n_threads=4,
            print_realtime=False,
            print_progress=False,
            redirect_whispercpp_logs_to=None,  # Redirect to devnull
        )
        segments = model.transcribe(audio_file_to_use)

        # Combine all segments
        transcription = " ".join([segment.text for segment in segments])

        duration = time.time() - start
        return BenchmarkResult(
            backend="pywhispercpp",
            device="cpu",
            model_size=model_size,
            transcription=transcription.strip(),
            duration=duration,
        )

    except Exception as e:
        return BenchmarkResult(
            backend="pywhispercpp",
            device="cpu",
            model_size=model_size,
            transcription="",
            duration=0,
            error=str(e),
        )
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass


def calculate_similarity(text1: str, text2: str) -> float:
    """Calculate similarity between two transcriptions using SequenceMatcher.

    Returns a value between 0 and 1, where 1 is identical.
    """
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def run_benchmarks(audio_file: str, cpu_only: bool = False) -> List[BenchmarkResult]:
    """Run all benchmark tests.

    Args:
        audio_file: Path to audio file to test
        cpu_only: If True, skip CUDA/GPU tests
    """
    results = []

    print("=" * 80)
    print("WHISPER BACKEND BENCHMARKS")
    if cpu_only:
        print("(CPU-only mode)")
    print("=" * 80)
    print(f"Test audio: {audio_file}")
    print()

    # Check if file exists
    if not Path(audio_file).exists():
        print(f"ERROR: Audio file not found: {audio_file}")
        return results

    # Test configurations
    configs = []

    # GPU tests (skip if cpu_only)
    if not cpu_only:
        configs.extend(
            [
                {
                    "name": "faster-whisper (CUDA, large-v3-turbo)",
                    "func": lambda: test_faster_whisper(
                        audio_file, device="cuda", model_size="large-v3-turbo"
                    ),
                },
                {
                    "name": "faster-whisper (CUDA, tiny)",
                    "func": lambda: test_faster_whisper(
                        audio_file, device="cuda", model_size="tiny"
                    ),
                },
                {
                    "name": "faster-whisper (CUDA, base)",
                    "func": lambda: test_faster_whisper(
                        audio_file, device="cuda", model_size="base"
                    ),
                },
            ]
        )

    # CPU tests (always included)
    configs.extend(
        [
            # faster-whisper multilingual models
            {
                "name": "faster-whisper (CPU, tiny)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="tiny"
                ),
            },
            {
                "name": "faster-whisper (CPU, base)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="base"
                ),
            },
            {
                "name": "faster-whisper (CPU, small)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="small"
                ),
            },
            {
                "name": "faster-whisper (CPU, large-v3-turbo)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="large-v3-turbo"
                ),
            },
            # faster-whisper English-only models (faster)
            {
                "name": "faster-whisper (CPU, tiny.en)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="tiny.en"
                ),
            },
            {
                "name": "faster-whisper (CPU, base.en)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="base.en"
                ),
            },
            {
                "name": "faster-whisper (CPU, small.en)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="small.en"
                ),
            },
            {
                "name": "faster-whisper (CPU, medium.en)",
                "func": lambda: test_faster_whisper(
                    audio_file, device="cpu", model_size="medium.en"
                ),
            },
            # pywhispercpp (CPU-optimized)
            {
                "name": "pywhispercpp (CPU, tiny.en)",
                "func": lambda: test_pywhispercpp(audio_file, model_size="tiny.en"),
            },
            {
                "name": "pywhispercpp (CPU, base.en)",
                "func": lambda: test_pywhispercpp(audio_file, model_size="base.en"),
            },
            {
                "name": "pywhispercpp (CPU, small.en)",
                "func": lambda: test_pywhispercpp(audio_file, model_size="small.en"),
            },
        ]
    )

    for config in configs:
        print(f"Testing: {config['name']}...")
        result = config["func"]()
        results.append(result)
        print(f"  {result}")
        if result.error:
            print(f"  Error details: {result.error}")
        print()

    # Calculate similarity scores against the reference (large-v3-turbo on GPU if available, otherwise CPU)
    reference_result = None

    # Try to find large-v3-turbo GPU result as reference
    if not cpu_only:
        reference_result = next(
            (
                r
                for r in results
                if r.model_size == "large-v3-turbo"
                and r.device == "cuda"
                and not r.error
            ),
            None,
        )

    # Fallback to large-v3-turbo CPU if GPU not available
    if reference_result is None:
        reference_result = next(
            (
                r
                for r in results
                if r.model_size == "large-v3-turbo"
                and r.device == "cpu"
                and not r.error
            ),
            None,
        )

    if reference_result:
        print("\n" + "=" * 80)
        print(
            f"REFERENCE TRANSCRIPTION (from {reference_result.backend} {reference_result.device} {reference_result.model_size}):"
        )
        print(f"'{reference_result.transcription}'")
        print("=" * 80)
        print("\nCalculating similarity scores against reference...")

        for result in results:
            if not result.error and result != reference_result:
                result.similarity_score = calculate_similarity(
                    reference_result.transcription, result.transcription
                )
                print(
                    f"  {result.backend} ({result.device}, {result.model_size}): {result.similarity_score:.1%}"
                )

        # Reference gets 100% similarity
        reference_result.similarity_score = 1.0
        print()

    return results


def print_summary(results: List[BenchmarkResult]):
    """Print summary comparison."""
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    successful_results = [r for r in results if not r.error]

    if not successful_results:
        print("No successful tests to compare.")
        return

    # Sort by duration
    successful_results.sort(key=lambda x: x.duration)

    print("\nFastest to Slowest:")
    for i, result in enumerate(successful_results, 1):
        similarity_str = (
            f" | Similarity: {result.similarity_score:.1%}"
            if result.similarity_score is not None
            else ""
        )
        print(
            f"{i}. {result.backend} ({result.device}, {result.model_size}): "
            f"{result.duration:.3f}s{similarity_str}"
        )

    # Show best accuracy (highest similarity)
    results_with_scores = [
        r for r in successful_results if r.similarity_score is not None
    ]
    if results_with_scores:
        print("\nBest Accuracy (highest similarity to reference):")
        results_with_scores.sort(key=lambda x: x.similarity_score, reverse=True)
        for i, result in enumerate(results_with_scores[:5], 1):
            print(
                f"{i}. {result.backend} ({result.device}, {result.model_size}): "
                f"{result.similarity_score:.1%} | {result.duration:.3f}s"
            )

    print("\nRecommendations:")
    fastest_cpu = next((r for r in successful_results if r.device == "cpu"), None)
    if fastest_cpu:
        similarity_str = (
            f" | Similarity: {fastest_cpu.similarity_score:.1%}"
            if fastest_cpu.similarity_score
            else ""
        )
        print(
            f"  Fastest CPU option: {fastest_cpu.backend} with {fastest_cpu.model_size}"
        )
        print(f"    - Speed: {fastest_cpu.duration:.3f}s{similarity_str}")
        print(f"    - Transcription: '{fastest_cpu.transcription}'")

    # Best CPU option (balance of speed and accuracy)
    cpu_results = [
        r
        for r in successful_results
        if r.device == "cpu" and r.similarity_score is not None
    ]
    if cpu_results:
        # Score = similarity / normalized_duration (higher is better)
        max_duration = max(r.duration for r in cpu_results)
        for r in cpu_results:
            r.combined_score = r.similarity_score * (
                1 - (r.duration / max_duration) * 0.5
            )

        best_balanced = max(cpu_results, key=lambda x: x.combined_score)
        print(
            f"\n  Best balanced CPU option (speed + accuracy): {best_balanced.backend} with {best_balanced.model_size}"
        )
        print(f"    - Speed: {best_balanced.duration:.3f}s")
        print(f"    - Similarity: {best_balanced.similarity_score:.1%}")
        print(f"    - Transcription: '{best_balanced.transcription}'")

    fastest_gpu = next((r for r in successful_results if r.device == "cuda"), None)
    if fastest_gpu and fastest_cpu:
        speedup = fastest_cpu.duration / fastest_gpu.duration
        print(f"\n  GPU speedup vs fastest CPU: {speedup:.1f}x faster")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Benchmark different Whisper backends and configurations"
    )
    parser.add_argument(
        "--cpu-only",
        action="store_true",
        help="Run CPU tests only (skip CUDA/GPU tests)",
    )
    args = parser.parse_args()

    results = run_benchmarks(TEST_AUDIO, cpu_only=args.cpu_only)
    print_summary(results)
