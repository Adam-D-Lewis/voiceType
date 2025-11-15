"""
Experiment to compare different Whisper backends and configurations.

This script tests:
1. faster-whisper with CUDA (current implementation)
2. faster-whisper with CPU
3. pywhispercpp with CPU
4. Different model sizes (tiny, base, small, medium, large-v3-turbo)

Run this to explore CPU-only options for better portability.
"""

import os
import time
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
    ):
        self.backend = backend
        self.device = device
        self.model_size = model_size
        self.transcription = transcription
        self.duration = duration
        self.error = error

    def __repr__(self):
        status = "ERROR" if self.error else "OK"
        return (
            f"[{status}] {self.backend} ({self.device}, {self.model_size}): "
            f"{self.duration:.3f}s - '{self.transcription}'"
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

        model = Model(model_size, n_threads=4)  # Use 4 threads for CPU
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


def run_benchmarks(audio_file: str) -> List[BenchmarkResult]:
    """Run all benchmark tests."""
    results = []

    print("=" * 80)
    print("WHISPER BACKEND BENCHMARKS")
    print("=" * 80)
    print(f"Test audio: {audio_file}")
    print()

    # Check if file exists
    if not Path(audio_file).exists():
        print(f"ERROR: Audio file not found: {audio_file}")
        return results

    # Test configurations
    configs = [
        # faster-whisper with CUDA (current setup)
        {
            "name": "faster-whisper (CUDA)",
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
        # faster-whisper with CPU
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

    for config in configs:
        print(f"Testing: {config['name']}...")
        result = config["func"]()
        results.append(result)
        print(f"  {result}")
        if result.error:
            print(f"  Error details: {result.error}")
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
        print(
            f"{i}. {result.backend} ({result.device}, {result.model_size}): "
            f"{result.duration:.3f}s"
        )

    print("\nRecommendations:")
    fastest_cpu = next((r for r in successful_results if r.device == "cpu"), None)
    if fastest_cpu:
        print(
            f"  Fastest CPU option: {fastest_cpu.backend} with {fastest_cpu.model_size}"
        )
        print(f"    - Speed: {fastest_cpu.duration:.3f}s")
        print(f"    - Transcription: '{fastest_cpu.transcription}'")

    fastest_gpu = next((r for r in successful_results if r.device == "cuda"), None)
    if fastest_gpu and fastest_cpu:
        speedup = fastest_cpu.duration / fastest_gpu.duration
        print(f"\n  GPU speedup vs fastest CPU: {speedup:.1f}x faster")


if __name__ == "__main__":
    results = run_benchmarks(TEST_AUDIO)
    print_summary(results)
