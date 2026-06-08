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
    """Ensure the module-level resident-model cache is empty around each test."""
    transcribe_mod._MODEL_CACHE.clear()
    yield
    transcribe_mod._MODEL_CACHE.clear()


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
