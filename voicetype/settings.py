from pathlib import Path
from typing import Any, Dict, List, Optional

import toml
from loguru import logger
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class TelemetryConfig(BaseModel):
    """Telemetry configuration for OpenTelemetry tracing."""

    enabled: bool = False
    service_name: str = "voicetype"
    export_to_file: bool = True
    trace_file: Optional[str] = None
    otlp_endpoint: Optional[str] = None


class Settings(BaseSettings):
    """Main application settings."""

    # Named stage configurations (new format)
    # Format: {stage_instance_name: {class: stage_class_name, **config}}
    stage_configs: Optional[Dict[str, Dict[str, Any]]] = {
        "RecordAudio": {
            "minimum_duration": 0.25,
        },
        "Transcribe": {
            "provider": "local",
        },
        "CorrectTypos": {
            "case_sensitive": False,
            "whole_word_only": True,
            "corrections": [],
        },
        "LLMAgent": {"provider": "openai:gpt-5-mini", "trigger_keywords": ["Jarvis"]},
        "TypeText": {},
    }

    pipelines: Optional[List[Dict[str, Any]]] = [
        {
            "name": "default",
            "enabled": True,
            "hotkey": "<pause>",
            "stages": [
                "RecordAudio",
                "Transcribe",
                "CorrectTypos",
                # "LLMAgent",  # TODO: Get this working with a local model by default so it's faster
                "TypeText",
            ],
        }
    ]

    # Telemetry configuration (enabled by default with file export)
    telemetry: TelemetryConfig = TelemetryConfig()

    # Path to log file (uses platform defaults if not specified)
    log_file: Optional[Path] = None


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _validate_stage_configs(settings: Settings) -> None:
    """Warn if stage_configs are defined but not used in any pipeline."""
    if not settings.stage_configs or not settings.pipelines:
        return

    # Collect all stage names used in pipelines
    used_stages = set()
    for pipeline in settings.pipelines:
        if "stages" in pipeline:
            used_stages.update(pipeline["stages"])

    # Check for unused stage configs
    unused_configs = set(settings.stage_configs.keys()) - used_stages
    if unused_configs:
        logger.warning(
            f"Stage configs defined but not used in any pipeline: {', '.join(sorted(unused_configs))}"
        )


def load_settings(settings_file: Path | None = None) -> Settings:
    """Loads settings from a TOML file, falling back to environment variables.

    If no settings_file is provided, searches in order:
    1. ./settings.toml (current directory)
    2. ~/.config/voicetype/settings.toml (user config)
    3. /etc/voicetype/settings.toml (system-wide)
    """
    if settings_file is None:
        # Search default locations
        default_locations = [
            Path("settings.toml"),
            Path.home() / ".config" / "voicetype" / "settings.toml",
            Path("/etc/voicetype/settings.toml"),
        ]

        for location in default_locations:
            if location.is_file():
                settings_file = location
                break

    # Start with defaults
    defaults = Settings()

    if settings_file and settings_file.is_file():
        data = toml.load(settings_file)

        # Deep merge stage_configs if present
        if "stage_configs" in data and defaults.stage_configs:
            data["stage_configs"] = _deep_merge(
                defaults.stage_configs, data["stage_configs"]
            )

        settings = Settings(**data)
    else:
        settings = defaults

    # Validate that all stage_configs are used in pipelines
    _validate_stage_configs(settings)

    return settings
