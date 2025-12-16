"""Tests for Transcribe stage configuration validation."""

import pytest
from pydantic import ValidationError

from voicetype.pipeline.stages.transcribe import (
    LiteLLMSTTRuntime,
    LocalSTTRuntime,
    Transcribe,
    TranscribeConfig,
)


class TestSTTRuntimeConfig:
    """Test STT runtime configuration models."""

    def test_local_runtime_defaults(self):
        """Test LocalSTTRuntime with default values."""
        runtime = LocalSTTRuntime()
        assert runtime.provider == "local"
        assert runtime.model == "tiny"
        assert runtime.device == "cpu"

    def test_local_runtime_custom_values(self):
        """Test LocalSTTRuntime with custom values."""
        runtime = LocalSTTRuntime(
            model="large-v3-turbo",
            device="cuda",
        )
        assert runtime.provider == "local"
        assert runtime.model == "large-v3-turbo"
        assert runtime.device == "cuda"

    def test_local_runtime_invalid_device(self):
        """Test that invalid device raises ValidationError."""
        with pytest.raises(ValidationError):
            LocalSTTRuntime(device="gpu")  # Invalid: must be 'cuda' or 'cpu'

    def test_local_runtime_invalid_model(self):
        """Test that invalid model raises ValidationError."""
        with pytest.raises(ValidationError):
            LocalSTTRuntime(model="invalid-model")

    def test_litellm_runtime_defaults(self):
        """Test LiteLLMSTTRuntime with default values."""
        runtime = LiteLLMSTTRuntime()
        assert runtime.provider == "litellm"
        assert runtime.model == "whisper-1"

    def test_litellm_runtime_custom_model(self):
        """Test LiteLLMSTTRuntime with custom model."""
        runtime = LiteLLMSTTRuntime(model="azure/whisper")
        assert runtime.provider == "litellm"
        assert runtime.model == "azure/whisper"


class TestTranscribeConfig:
    """Test TranscribeConfig with unified runtime support."""

    def test_config_defaults(self):
        """Test TranscribeConfig with default values."""
        config = TranscribeConfig()
        assert isinstance(config.runtime, LocalSTTRuntime)
        assert config.runtime.provider == "local"
        assert config.language == "en"
        assert config.audio_format == "wav"
        assert config.download_root is None
        assert config.fallback_runtimes == []

    def test_config_with_local_runtime(self):
        """Test TranscribeConfig with explicit local runtime."""
        config = TranscribeConfig(
            runtime={"provider": "local", "model": "large-v3", "device": "cuda"},
            language="es",
        )
        assert isinstance(config.runtime, LocalSTTRuntime)
        assert config.runtime.model == "large-v3"
        assert config.runtime.device == "cuda"
        assert config.language == "es"

    def test_config_with_litellm_runtime(self):
        """Test TranscribeConfig with litellm runtime."""
        config = TranscribeConfig(
            runtime={"provider": "litellm", "model": "whisper-1"},
            language="fr",
        )
        assert isinstance(config.runtime, LiteLLMSTTRuntime)
        assert config.runtime.model == "whisper-1"
        assert config.language == "fr"

    def test_config_with_fallback_runtimes(self):
        """Test TranscribeConfig with fallback runtimes."""
        config = TranscribeConfig(
            runtime={"provider": "local", "model": "large-v3-turbo", "device": "cuda"},
            fallback_runtimes=[
                {"provider": "local", "model": "large-v3-turbo", "device": "cpu"},
                {"provider": "litellm", "model": "whisper-1"},
            ],
        )
        assert isinstance(config.runtime, LocalSTTRuntime)
        assert config.runtime.device == "cuda"
        assert len(config.fallback_runtimes) == 2
        assert isinstance(config.fallback_runtimes[0], LocalSTTRuntime)
        assert config.fallback_runtimes[0].device == "cpu"
        assert isinstance(config.fallback_runtimes[1], LiteLLMSTTRuntime)

    def test_config_with_mixed_fallbacks(self):
        """Test config with mixed local and litellm fallbacks."""
        config = TranscribeConfig(
            runtime={"provider": "litellm"},
            fallback_runtimes=[
                {"provider": "local", "model": "tiny", "device": "cpu"},
            ],
        )
        assert isinstance(config.runtime, LiteLLMSTTRuntime)
        assert len(config.fallback_runtimes) == 1
        assert isinstance(config.fallback_runtimes[0], LocalSTTRuntime)


class TestTranscribeStageInit:
    """Test Transcribe stage initialization."""

    def test_stage_init_defaults(self):
        """Test Transcribe stage with default config."""
        stage = Transcribe(config={})
        assert isinstance(stage.cfg, TranscribeConfig)
        assert isinstance(stage.cfg.runtime, LocalSTTRuntime)

    def test_stage_init_local_runtime(self):
        """Test Transcribe stage with local runtime config."""
        stage = Transcribe(
            config={"runtime": {"provider": "local", "model": "base", "device": "cpu"}}
        )
        assert isinstance(stage.cfg.runtime, LocalSTTRuntime)
        assert stage.cfg.runtime.model == "base"
        assert stage.cfg.runtime.device == "cpu"

    def test_stage_init_litellm_runtime(self):
        """Test Transcribe stage with litellm runtime config."""
        stage = Transcribe(
            config={
                "runtime": {"provider": "litellm", "model": "whisper-1"},
                "language": "de",
            }
        )
        assert isinstance(stage.cfg.runtime, LiteLLMSTTRuntime)
        assert stage.cfg.language == "de"

    def test_stage_init_with_fallbacks(self):
        """Test Transcribe stage with fallback runtimes."""
        stage = Transcribe(
            config={
                "runtime": {
                    "provider": "local",
                    "model": "large-v3-turbo",
                    "device": "cuda",
                },
                "fallback_runtimes": [
                    {"provider": "local", "model": "tiny", "device": "cpu"},
                    {"provider": "litellm"},
                ],
            }
        )
        assert len(stage.cfg.fallback_runtimes) == 2
        assert isinstance(stage.cfg.fallback_runtimes[0], LocalSTTRuntime)
        assert isinstance(stage.cfg.fallback_runtimes[1], LiteLLMSTTRuntime)

    def test_stage_init_invalid_runtime_device(self):
        """Test that invalid device in runtime config raises ValidationError."""
        with pytest.raises(ValidationError):
            Transcribe(config={"runtime": {"provider": "local", "device": "tpu"}})

    def test_stage_audio_format_accessible(self):
        """Test that audio_format is accessible for compatibility."""
        stage = Transcribe(config={"audio_format": "mp3"})
        assert stage.audio_format == "mp3"

    def test_stage_init_shared_settings(self):
        """Test that shared settings are applied correctly."""
        stage = Transcribe(
            config={
                "runtime": {"provider": "local"},
                "language": "ja",
                "download_root": "/custom/models",
            }
        )
        assert stage.cfg.language == "ja"
        assert stage.cfg.download_root == "/custom/models"
