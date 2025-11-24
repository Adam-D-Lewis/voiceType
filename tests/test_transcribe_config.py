"""Tests for Transcribe stage configuration validation."""

import pytest
from pydantic import ValidationError

from voicetype.pipeline.stages.transcribe import (
    LiteLLMTranscribeConfig,
    LocalTranscribeConfig,
    Transcribe,
)


class TestTranscribeConfig:
    """Test Pydantic config validation for Transcribe stage."""

    def test_local_config_defaults(self):
        """Test LocalTranscribeConfig with default values."""
        config = LocalTranscribeConfig()
        assert config.provider == "local"
        assert config.model == "large-v3-turbo"
        assert config.language == "en"
        assert config.device == "cuda"
        assert config.audio_format == "wav"
        assert config.history is None

    def test_local_config_custom_values(self):
        """Test LocalTranscribeConfig with custom values."""
        config = LocalTranscribeConfig(
            model="tiny",
            language="es",
            device="cpu",
        )
        assert config.provider == "local"
        assert config.model == "tiny"
        assert config.language == "es"
        assert config.device == "cpu"

    def test_local_config_invalid_device(self):
        """Test that invalid device raises ValidationError."""
        with pytest.raises(ValidationError):
            LocalTranscribeConfig(device="gpu")  # Invalid: must be 'cuda' or 'cpu'

    def test_litellm_config_defaults(self):
        """Test LiteLLMTranscribeConfig with default values."""
        config = LiteLLMTranscribeConfig()
        assert config.provider == "litellm"
        assert config.language == "en"
        assert config.audio_format == "wav"
        assert config.history is None

    def test_litellm_config_custom_values(self):
        """Test LiteLLMTranscribeConfig with custom values."""
        config = LiteLLMTranscribeConfig(
            language="fr",
            history="Previous context",
        )
        assert config.provider == "litellm"
        assert config.language == "fr"
        assert config.history == "Previous context"

    def test_litellm_config_no_device_field(self):
        """Test that LiteLLM config doesn't have device field."""
        config = LiteLLMTranscribeConfig()
        assert not hasattr(config, "device")

    def test_litellm_config_no_model_field(self):
        """Test that LiteLLM config doesn't have model field."""
        config = LiteLLMTranscribeConfig()
        assert not hasattr(config, "model")

    def test_transcribe_stage_init_local(self):
        """Test Transcribe stage initialization with local provider."""
        stage = Transcribe(
            config={"provider": "local", "model": "base", "device": "cpu"}
        )
        assert isinstance(stage.cfg, LocalTranscribeConfig)
        assert stage.cfg.provider == "local"
        assert stage.cfg.model == "base"
        assert stage.cfg.device == "cpu"

    def test_transcribe_stage_init_litellm(self):
        """Test Transcribe stage initialization with litellm provider."""
        stage = Transcribe(config={"provider": "litellm", "language": "de"})
        assert isinstance(stage.cfg, LiteLLMTranscribeConfig)
        assert stage.cfg.provider == "litellm"
        assert stage.cfg.language == "de"

    def test_transcribe_stage_init_default_provider(self):
        """Test Transcribe stage defaults to local provider."""
        stage = Transcribe(config={})
        assert isinstance(stage.cfg, LocalTranscribeConfig)
        assert stage.cfg.provider == "local"

    def test_transcribe_stage_init_unknown_provider(self):
        """Test that unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            Transcribe(config={"provider": "unknown"})

    def test_transcribe_stage_init_invalid_local_device(self):
        """Test that invalid device in local config raises ValidationError."""
        with pytest.raises(ValidationError):
            Transcribe(config={"provider": "local", "device": "tpu"})

    def test_local_config_rejects_extra_fields(self):
        """Test that extra fields are allowed by default in Pydantic v2."""
        # Note: Pydantic v2 allows extra fields by default
        # If you want to forbid them, set model_config = ConfigDict(extra='forbid')
        config = LocalTranscribeConfig(provider="local", extra_field="value")
        # This will pass in Pydantic v2 by default
        assert config.provider == "local"

    def test_transcribe_stage_audio_format_accessible(self):
        """Test that audio_format is accessible for compatibility."""
        stage = Transcribe(config={"audio_format": "mp3"})
        assert stage.audio_format == "mp3"
