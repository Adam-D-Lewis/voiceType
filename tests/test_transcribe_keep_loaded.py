"""Tests for the resident-model (``keep_loaded``) option of the Transcribe stage.

These tests patch the model constructor so they run without a GPU or the
faster-whisper package being able to load a real model.
"""

from unittest.mock import patch

import pytest

import voicetype.pipeline.stages.transcribe as transcribe_mod
from voicetype.pipeline.stages.transcribe import (
    LocalSTTRuntime,
    Transcribe,
    TranscribeConfig,
)


@pytest.fixture
def clear_model_cache():
    """Reset the module-level cache and runtime override around each test."""
    transcribe_mod._MODEL_CACHE.clear()
    transcribe_mod._keep_loaded_override = None
    yield
    transcribe_mod._MODEL_CACHE.clear()
    transcribe_mod._keep_loaded_override = None


class TestKeepLoadedConfig:
    """The keep_loaded flag is configurable and defaults to off."""

    def test_keep_loaded_defaults_false(self):
        assert LocalSTTRuntime().keep_loaded is False

    def test_keep_loaded_settable(self):
        runtime = LocalSTTRuntime(
            model="large-v3-turbo", device="cuda", keep_loaded=True
        )
        assert runtime.keep_loaded is True

    def test_keep_loaded_via_transcribe_config(self):
        config = TranscribeConfig(
            runtime={
                "provider": "local",
                "model": "tiny",
                "device": "cpu",
                "keep_loaded": True,
            }
        )
        assert isinstance(config.runtime, LocalSTTRuntime)
        assert config.runtime.keep_loaded is True


class TestResidentModelCache:
    """When keep_loaded is on, the model is loaded once and reused."""

    def _local_cfg(self, keep_loaded):
        return {
            "runtime": {
                "provider": "local",
                "model": "tiny",
                "device": "cpu",
                "keep_loaded": keep_loaded,
            }
        }

    def test_resident_model_loaded_once_and_reused(self, clear_model_cache):
        created = []

        def fake_create(model_path, device, compute_type, models_dir):
            obj = object()
            created.append(obj)
            return obj

        with patch.object(
            transcribe_mod, "_create_whisper_model", side_effect=fake_create
        ):
            s1 = Transcribe(config=self._local_cfg(keep_loaded=True))
            assert s1._model_ready.wait(timeout=10)
            assert s1._preload_error is None

            s2 = Transcribe(config=self._local_cfg(keep_loaded=True))
            assert s2._model_ready.wait(timeout=10)
            assert s2._preload_error is None

        # Constructed exactly once; both stages share the same instance.
        assert len(created) == 1
        assert s1._preloaded_model is created[0]
        assert s2._preloaded_model is s1._preloaded_model

    def test_non_resident_model_loaded_each_time(self, clear_model_cache):
        created = []

        def fake_create(model_path, device, compute_type, models_dir):
            obj = object()
            created.append(obj)
            return obj

        with patch.object(
            transcribe_mod, "_create_whisper_model", side_effect=fake_create
        ):
            s1 = Transcribe(config=self._local_cfg(keep_loaded=False))
            assert s1._model_ready.wait(timeout=10)
            s2 = Transcribe(config=self._local_cfg(keep_loaded=False))
            assert s2._model_ready.wait(timeout=10)

        assert len(created) == 2
        assert s1._preloaded_model is not s2._preloaded_model
        # Nothing cached when keep_loaded is off.
        assert transcribe_mod._MODEL_CACHE == {}

    def test_cleanup_retains_resident_model(self, clear_model_cache):
        with patch.object(
            transcribe_mod, "_create_whisper_model", side_effect=lambda *a: object()
        ):
            stage = Transcribe(config=self._local_cfg(keep_loaded=True))
            assert stage._model_ready.wait(timeout=10)

            assert len(transcribe_mod._MODEL_CACHE) == 1
            cached = next(iter(transcribe_mod._MODEL_CACHE.values()))

            stage.cleanup()

        # Stage drops its own reference, but the cache keeps the model resident.
        assert stage._preloaded_model is None
        assert len(transcribe_mod._MODEL_CACHE) == 1
        assert next(iter(transcribe_mod._MODEL_CACHE.values())) is cached

    def test_cleanup_evicts_non_resident_model(self, clear_model_cache):
        with patch.object(
            transcribe_mod, "_create_whisper_model", side_effect=lambda *a: object()
        ):
            stage = Transcribe(config=self._local_cfg(keep_loaded=False))
            assert stage._model_ready.wait(timeout=10)
            assert stage._preloaded_model is not None

            stage.cleanup()

        assert stage._preloaded_model is None
        assert transcribe_mod._MODEL_CACHE == {}


class TestRuntimeKeepLoadedToggle:
    """The keep_loaded state can be flipped at runtime (e.g. from the tray menu)."""

    def test_resolve_follows_config_when_no_override(self, clear_model_cache):
        assert transcribe_mod.is_keep_loaded() is False
        assert transcribe_mod._resolve_keep_loaded(True) is True
        assert transcribe_mod._resolve_keep_loaded(False) is False

    def test_init_seeds_once(self, clear_model_cache):
        transcribe_mod.init_keep_loaded(True)
        assert transcribe_mod.is_keep_loaded() is True
        # A second init does not override an already-set value.
        transcribe_mod.init_keep_loaded(False)
        assert transcribe_mod.is_keep_loaded() is True

    def test_override_wins_over_config(self, clear_model_cache):
        transcribe_mod.set_keep_loaded(True)
        assert transcribe_mod.is_keep_loaded() is True
        assert transcribe_mod._resolve_keep_loaded(False) is True  # config says off

        transcribe_mod.set_keep_loaded(False)
        assert transcribe_mod.is_keep_loaded() is False
        assert transcribe_mod._resolve_keep_loaded(True) is False  # config says on

    def test_disabling_evicts_resident_models(self, clear_model_cache):
        transcribe_mod._MODEL_CACHE[("tiny", "cuda", "float16")] = object()
        transcribe_mod.set_keep_loaded(False)
        assert transcribe_mod._MODEL_CACHE == {}

    def test_clear_resident_models(self, clear_model_cache):
        transcribe_mod._MODEL_CACHE[("tiny", "cpu", "int8")] = object()
        transcribe_mod.clear_resident_models()
        assert transcribe_mod._MODEL_CACHE == {}

    def test_runtime_override_controls_caching(self, clear_model_cache):
        """A stage whose config says keep_loaded=False still caches when the
        runtime override is on (mirrors toggling the tray item on)."""
        transcribe_mod.set_keep_loaded(True)
        created = []
        with patch.object(
            transcribe_mod,
            "_create_whisper_model",
            side_effect=lambda *a: created.append(object()) or created[-1],
        ):
            cfg = {
                "runtime": {
                    "provider": "local",
                    "model": "tiny",
                    "device": "cpu",
                    "keep_loaded": False,
                }
            }
            s1 = Transcribe(config=cfg)
            assert s1._model_ready.wait(timeout=10)
            s2 = Transcribe(config=cfg)
            assert s2._model_ready.wait(timeout=10)

        assert len(created) == 1
        assert s1._preloaded_model is s2._preloaded_model


class TestLocalFilesOnly:
    """The loader avoids the HuggingFace Hub when the model is already cached."""

    def test_uses_local_cache_without_network(self, monkeypatch):
        import faster_whisper

        calls = []

        class FakeModel:
            def __init__(self, path, **kw):
                calls.append(kw.get("local_files_only"))

        monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
        transcribe_mod._create_whisper_model("tiny", "cpu", "int8", "/tmp/models")
        # Loaded straight from cache; no second (networked) attempt.
        assert calls == [True]

    def test_falls_back_to_download_when_not_cached(self, monkeypatch):
        import faster_whisper

        try:
            from huggingface_hub.errors import LocalEntryNotFoundError
        except ImportError:
            from huggingface_hub.utils import LocalEntryNotFoundError

        calls = []

        class FakeModel:
            def __init__(self, path, **kw):
                lfo = kw.get("local_files_only")
                calls.append(lfo)
                if lfo:
                    raise LocalEntryNotFoundError("not cached")

        monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
        transcribe_mod._create_whisper_model("tiny", "cpu", "int8", "/tmp/models")
        # First tried offline, then allowed the network download.
        assert calls == [True, False]

    def test_non_cache_error_does_not_trigger_network_retry(self, monkeypatch):
        import faster_whisper

        calls = []

        class FakeModel:
            def __init__(self, path, **kw):
                calls.append(kw.get("local_files_only"))
                raise RuntimeError("CUDA out of memory")

        monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
        with pytest.raises(RuntimeError, match="CUDA out of memory"):
            transcribe_mod._create_whisper_model(
                "tiny", "cuda", "float16", "/tmp/models"
            )
        # A CUDA error must propagate from the first attempt, not retry online.
        assert calls == [True]
