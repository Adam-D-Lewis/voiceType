"""Tests for CUDA memory management in the Transcribe stage.

These tests verify that VRAM is properly freed after both failed and
successful WhisperModel loads. They require a CUDA GPU and skip
automatically if one is not available.

The core issue: CTranslate2 uses async CUDA operations during model loading.
When the constructor fails (e.g. OOM), pending async ops hold partially-allocated
GPU memory. cudaDeviceSynchronize() forces cleanup of that leaked memory.
"""

import ctypes
import gc
import os
import subprocess
import time

import pytest

# Skip entire module if no CUDA GPU available
try:
    import ctranslate2

    _has_cuda = ctranslate2.get_cuda_device_count() > 0
except Exception:
    _has_cuda = False

pytestmark = pytest.mark.skipif(not _has_cuda, reason="No CUDA GPU available")


def _get_process_vram_mib():
    """Get VRAM usage for this process in MiB via nvidia-smi."""
    pid = os.getpid()
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(",")
        if int(parts[0].strip()) == pid:
            return int(parts[1].strip())
    return 0


def _get_free_vram_mib():
    """Get total free VRAM in MiB."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def _cuda_malloc(size_bytes):
    """Allocate CUDA memory directly via cudaMalloc."""
    libcudart = ctypes.CDLL("libcudart.so")
    ptr = ctypes.c_void_p()
    ret = libcudart.cudaMalloc(ctypes.byref(ptr), ctypes.c_size_t(size_bytes))
    if ret != 0:
        raise RuntimeError(f"cudaMalloc failed with error code {ret}")
    return ptr, libcudart


def _fill_vram_to(target_free_mib):
    """Fill VRAM until free drops near target_free_mib. Returns (allocations, libcudart)."""
    free = _get_free_vram_mib()
    if free < 500:
        pytest.skip(f"GPU only has {free} MiB free, not enough headroom to test")

    libcudart = ctypes.CDLL("libcudart.so")
    allocations = []

    for chunk_mib in [512, 128, 32, 8]:
        chunk_bytes = chunk_mib * 1024 * 1024
        while _get_free_vram_mib() > target_free_mib + chunk_mib:
            ptr = ctypes.c_void_p()
            ret = libcudart.cudaMalloc(ctypes.byref(ptr), ctypes.c_size_t(chunk_bytes))
            if ret != 0:
                break
            allocations.append(ptr)

    if not allocations:
        pytest.skip("Could not allocate CUDA padding memory")

    time.sleep(0.3)
    return allocations, libcudart


@pytest.fixture()
def fill_vram():
    """Fill VRAM to ~50 MiB free — too tight for any model to load."""
    allocations, libcudart = _fill_vram_to(50)

    remaining = _get_free_vram_mib()
    if remaining > 120:
        for ptr in allocations:
            libcudart.cudaFree(ptr)
        pytest.skip(f"Could not reduce free VRAM enough ({remaining} MiB remaining)")

    yield

    for ptr in allocations:
        libcudart.cudaFree(ptr)
    time.sleep(0.3)


@pytest.fixture()
def fill_vram_partial():
    """Fill VRAM to ~300 MiB free — enough for a partial allocation to leak.

    The small model needs ~600 MiB, so ~300 MiB free means CTranslate2 will
    start allocating, get partway through, then OOM — leaking the partial
    allocation.
    """
    allocations, libcudart = _fill_vram_to(300)

    remaining = _get_free_vram_mib()
    if remaining > 500:
        for ptr in allocations:
            libcudart.cudaFree(ptr)
        pytest.skip(f"Could not reduce free VRAM enough ({remaining} MiB remaining)")

    yield

    for ptr in allocations:
        libcudart.cudaFree(ptr)
    time.sleep(0.3)


class TestCudaMemoryCleanup:
    """Test that CUDA memory is properly cleaned up after model operations."""

    def test_cuda_synchronize_frees_leaked_memory(self, fill_vram_partial):
        """A failed CUDA model load leaks VRAM; _cuda_synchronize must reclaim it.

        Uses the small model (~600 MiB) with ~300 MiB free so that CTranslate2
        starts allocating, gets partway, then OOMs — leaking a partial allocation.
        """
        from faster_whisper import WhisperModel

        from voicetype.pipeline.stages.transcribe import _cuda_synchronize
        from voicetype.utils import get_app_data_dir

        models_dir = str(get_app_data_dir() / "models")

        vram_before = _get_process_vram_mib()

        # Attempt to load model on CUDA — should OOM and leak memory
        with pytest.raises(RuntimeError, match="CUDA|out of memory|memory"):
            WhisperModel(
                "small",
                device="cuda",
                compute_type="float16",
                download_root=models_dir,
            )

        time.sleep(0.3)
        vram_after_oom = _get_process_vram_mib()
        leaked = vram_after_oom - vram_before

        if leaked <= 0:
            pytest.skip(
                "CTranslate2 failed before allocating anything — "
                "no leak to test (VRAM may be too tight)"
            )

        # cudaDeviceSynchronize should reclaim the leaked memory
        _cuda_synchronize()
        time.sleep(0.3)
        vram_after_sync = _get_process_vram_mib()
        recovered = vram_after_oom - vram_after_sync

        assert recovered >= leaked - 10, (
            f"cudaDeviceSynchronize did not free leaked VRAM: "
            f"leaked={leaked} MiB, recovered={recovered} MiB"
        )

    def test_successful_load_cleanup_frees_vram(self):
        """A successfully loaded model must release VRAM after del + gc.collect."""
        from faster_whisper import WhisperModel

        from voicetype.utils import get_app_data_dir

        models_dir = str(get_app_data_dir() / "models")

        vram_before = _get_process_vram_mib()

        model = WhisperModel(
            "tiny",
            device="cuda",
            compute_type="float16",
            download_root=models_dir,
        )

        time.sleep(0.3)
        vram_loaded = _get_process_vram_mib()
        model_vram = vram_loaded - vram_before
        assert model_vram > 50, (
            f"Model doesn't seem to be using VRAM "
            f"(before={vram_before}, loaded={vram_loaded})"
        )

        del model
        gc.collect()
        time.sleep(0.3)
        vram_after = _get_process_vram_mib()
        freed = vram_loaded - vram_after

        assert freed >= model_vram - 20, (
            f"del + gc.collect did not free model VRAM: "
            f"model_vram={model_vram} MiB, freed={freed} MiB"
        )

    def test_transcribe_stage_cleanup_frees_vram(self):
        """The Transcribe stage's cleanup() method must release VRAM."""
        from voicetype.pipeline.stages.transcribe import Transcribe

        stage = Transcribe(
            config={"runtime": {"provider": "local", "model": "tiny", "device": "cuda"}}
        )

        # Wait for background preload to finish
        stage._model_ready.wait(timeout=10)
        assert stage._preload_error is None, f"Preload failed: {stage._preload_error}"
        assert stage._preloaded_model is not None

        time.sleep(0.3)
        vram_loaded = _get_process_vram_mib()

        stage.cleanup()
        time.sleep(0.3)
        vram_after = _get_process_vram_mib()
        freed = vram_loaded - vram_after

        assert freed > 50, (
            f"Transcribe.cleanup() did not free VRAM: "
            f"loaded={vram_loaded} MiB, after={vram_after} MiB, freed={freed} MiB"
        )

    def test_transcribe_stage_failed_preload_no_leak(self, fill_vram):
        """When preload fails due to VRAM pressure, no CUDA memory should leak."""
        from voicetype.pipeline.stages.transcribe import Transcribe

        vram_before = _get_process_vram_mib()

        stage = Transcribe(
            config={"runtime": {"provider": "local", "model": "tiny", "device": "cuda"}}
        )

        stage._model_ready.wait(timeout=10)
        assert stage._preload_error is not None, "Expected preload to fail with OOM"

        time.sleep(0.3)
        vram_after = _get_process_vram_mib()
        leaked = vram_after - vram_before

        stage.cleanup()

        assert leaked <= 10, (
            f"Failed preload leaked {leaked} MiB of VRAM "
            f"(before={vram_before}, after={vram_after})"
        )
