"""Unit tests for settings module."""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
import toml
from loguru import logger

from voicetype.settings import Settings, _validate_stage_configs, load_settings


class TestFileOpenerConfig:
    """Tests for FileOpenerConfig model."""

    def test_file_opener_config_defaults(self):
        """Test default values for FileOpenerConfig."""
        from voicetype.settings import FileOpenerConfig

        config = FileOpenerConfig()
        assert config.command is None
        assert config.args == []

    def test_file_opener_config_with_command(self):
        """Test FileOpenerConfig with custom command."""
        from voicetype.settings import FileOpenerConfig

        config = FileOpenerConfig(command="code", args=["--goto", "{path}:999999"])
        assert config.command == "code"
        assert config.args == ["--goto", "{path}:999999"]


class TestFileOpenersConfig:
    """Tests for FileOpenersConfig model."""

    def test_file_openers_config_defaults(self):
        """Test default values for FileOpenersConfig."""
        from voicetype.settings import FileOpenersConfig

        config = FileOpenersConfig()
        assert config.logs.command is None
        assert config.traces.command is None
        assert config.settings.command is None

    def test_file_openers_config_with_custom_logs(self):
        """Test FileOpenersConfig with custom logs opener."""
        from voicetype.settings import FileOpenerConfig, FileOpenersConfig

        config = FileOpenersConfig(
            logs=FileOpenerConfig(command="code", args=["--goto", "{path}:999999"])
        )
        assert config.logs.command == "code"
        assert config.logs.args == ["--goto", "{path}:999999"]
        assert config.traces.command is None  # Still default


class TestSettingsFileOpeners:
    """Tests for file_openers in Settings."""

    def test_settings_has_file_openers_default(self):
        """Test that Settings has file_openers with defaults."""
        settings = Settings()
        assert settings.file_openers is not None
        assert settings.file_openers.logs.command is None

    def test_settings_loads_file_openers_from_toml(self):
        """Test that file_openers are loaded from TOML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            toml.dump(
                {
                    "file_openers": {
                        "logs": {
                            "command": "code",
                            "args": ["--goto", "{path}:999999"],
                        }
                    }
                },
                f,
            )
            temp_file = Path(f.name)

        try:
            settings = load_settings(temp_file)
            assert settings.file_openers.logs.command == "code"
            assert settings.file_openers.logs.args == ["--goto", "{path}:999999"]
            assert settings.file_openers.traces.command is None  # Still default
        finally:
            temp_file.unlink()


@pytest.fixture
def captured_logs():
    """Fixture to capture loguru logs."""
    log_stream = StringIO()
    handler_id = logger.add(log_stream, format="{message}")
    yield log_stream
    logger.remove(handler_id)


class TestSettingsValidation:
    """Tests for settings validation logic."""

    def test_validate_stage_configs_warns_on_unused(self, captured_logs):
        """Test that unused stage configs generate warnings."""
        settings = Settings(
            stage_configs={
                "RecordAudio": {"minimum_duration": 0.25},
                "Transcribe": {"provider": "local"},
                "UnusedStage": {"some_config": "value"},
            },
            pipelines=[
                {
                    "name": "default",
                    "enabled": True,
                    "hotkey": "<pause>",
                    "stages": ["RecordAudio", "Transcribe"],
                }
            ],
        )

        _validate_stage_configs(settings)

        log_output = captured_logs.getvalue()
        assert "UnusedStage" in log_output
        assert "not used in any pipeline" in log_output

    def test_validate_stage_configs_no_warning_when_all_used(self, captured_logs):
        """Test that no warning is generated when all stages are used."""
        settings = Settings(
            stage_configs={
                "RecordAudio": {"minimum_duration": 0.25},
                "Transcribe": {"provider": "local"},
            },
            pipelines=[
                {
                    "name": "default",
                    "enabled": True,
                    "hotkey": "<pause>",
                    "stages": ["RecordAudio", "Transcribe"],
                }
            ],
        )

        _validate_stage_configs(settings)

        log_output = captured_logs.getvalue()
        assert "not used in any pipeline" not in log_output

    def test_validate_stage_configs_multiple_pipelines(self, captured_logs):
        """Test validation with multiple pipelines using different stages."""
        settings = Settings(
            stage_configs={
                "RecordAudio": {"minimum_duration": 0.25},
                "Transcribe": {"provider": "local"},
                "CorrectTypos": {"corrections": []},
                "UnusedStage": {"config": "value"},
            },
            pipelines=[
                {
                    "name": "pipeline1",
                    "enabled": True,
                    "hotkey": "<pause>",
                    "stages": ["RecordAudio", "Transcribe"],
                },
                {
                    "name": "pipeline2",
                    "enabled": True,
                    "hotkey": "<f12>",
                    "stages": ["RecordAudio", "CorrectTypos"],
                },
            ],
        )

        _validate_stage_configs(settings)

        log_output = captured_logs.getvalue()
        # Only UnusedStage should be warned about
        assert "UnusedStage" in log_output
        # The warning message shouldn't mention used stages individually
        # (they're all in one comma-separated list)
        assert "not used in any pipeline" in log_output

    def test_validate_stage_configs_no_pipelines(self, captured_logs):
        """Test validation when no pipelines are defined."""
        settings = Settings(
            stage_configs={
                "RecordAudio": {"minimum_duration": 0.25},
            },
            pipelines=None,
        )

        _validate_stage_configs(settings)

        log_output = captured_logs.getvalue()
        # Should not crash, no warning expected
        assert "not used in any pipeline" not in log_output

    def test_validate_stage_configs_no_stage_configs(self, captured_logs):
        """Test validation when no stage configs are defined."""
        settings = Settings(
            stage_configs=None,
            pipelines=[
                {
                    "name": "default",
                    "enabled": True,
                    "hotkey": "<pause>",
                    "stages": ["RecordAudio"],
                }
            ],
        )

        _validate_stage_configs(settings)

        log_output = captured_logs.getvalue()
        # Should not crash, no warning expected
        assert "not used in any pipeline" not in log_output


class TestSettingsLoading:
    """Tests for settings loading and merging."""

    def test_load_settings_deep_merge(self):
        """Test that stage_configs are deep merged with defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            toml.dump(
                {
                    "stage_configs": {
                        "CorrectTypos": {
                            "corrections": [["foo", "bar"]],
                        }
                    }
                },
                f,
            )
            temp_file = Path(f.name)

        try:
            settings = load_settings(temp_file)

            # Should have the override value
            assert settings.stage_configs["CorrectTypos"]["corrections"] == [
                ["foo", "bar"]
            ]

            # Should still have default values
            assert settings.stage_configs["CorrectTypos"]["case_sensitive"] is False
            assert settings.stage_configs["CorrectTypos"]["whole_word_only"] is True

            # Should still have other default stage configs
            assert "RecordAudio" in settings.stage_configs
            assert "Transcribe" in settings.stage_configs

        finally:
            temp_file.unlink()

    def test_load_settings_full_override(self):
        """Test that non-dict values are fully overridden."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            toml.dump(
                {
                    "pipelines": [
                        {
                            "name": "custom",
                            "enabled": True,
                            "hotkey": "<f12>",
                            "stages": ["RecordAudio"],
                        }
                    ]
                },
                f,
            )
            temp_file = Path(f.name)

        try:
            settings = load_settings(temp_file)

            # Pipelines should be completely replaced
            assert len(settings.pipelines) == 1
            assert settings.pipelines[0]["name"] == "custom"

        finally:
            temp_file.unlink()

    def test_load_settings_validates_on_load(self, captured_logs):
        """Test that validation runs when loading settings."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            toml.dump(
                {
                    "stage_configs": {
                        "UnusedStage": {"config": "value"},
                    },
                    "pipelines": [
                        {
                            "name": "default",
                            "enabled": True,
                            "hotkey": "<pause>",
                            "stages": ["RecordAudio"],
                        }
                    ],
                },
                f,
            )
            temp_file = Path(f.name)

        try:
            load_settings(temp_file)

            log_output = captured_logs.getvalue()
            # Should warn about UnusedStage (and CorrectTypos, Transcribe, TypeText from defaults)
            assert "not used in any pipeline" in log_output

        finally:
            temp_file.unlink()
