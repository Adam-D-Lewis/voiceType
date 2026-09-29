from pathlib import Path
from typing import Any, Dict, List, Optional

import toml
from loguru import logger
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

from voicetype.utils import get_app_data_dir


class FileOpenerConfig(BaseModel):
    """Configuration for opening a specific file type."""

    command: Optional[str] = None  # None = system default
    args: List[str] = []  # Args with {path} placeholder


class FileOpenersConfig(BaseModel):
    """Configuration for all file openers."""

    logs: FileOpenerConfig = FileOpenerConfig()
    traces: FileOpenerConfig = FileOpenerConfig()
    settings: FileOpenerConfig = FileOpenerConfig()


class TelemetryConfig(BaseModel):
    """Telemetry configuration for OpenTelemetry tracing."""

    enabled: bool = False
    service_name: str = "voicetype"
    export_to_file: bool = True
    trace_file: Optional[str] = None
    otlp_endpoint: Optional[str] = None

    # File rotation settings
    rotation_enabled: bool = True
    rotation_max_size_mb: int = 10  # Rotate when file reaches this size in MB


def _remote_credentials_path(filename: str) -> Path:
    return get_app_data_dir() / "remote" / filename


class RemoteConfig(BaseModel):
    """Remote trigger server, for devices like a Pico 2 W button.

    When enabled, voiceType accepts TLS connections from a remote device that
    sends button press/release events (bound to pipelines with hotkeys like
    "remote:main") and types text sent back with keyboard_backend = "remote".
    Create the certificate and token with `voicetype remote-setup`.
    """

    enabled: bool = False
    host: str = "0.0.0.0"  # Interface to listen on ("0.0.0.0" = all IPv4 interfaces)
    port: int = Field(default=8684, ge=0, le=65535)
    cert_file: Path = Field(
        default_factory=lambda: _remote_credentials_path("cert.pem")
    )
    key_file: Path = Field(default_factory=lambda: _remote_credentials_path("key.pem"))
    token_file: Path = Field(default_factory=lambda: _remote_credentials_path("token"))
    # A device holding a button that goes silent this long is treated as gone,
    # and its recording is cancelled
    press_timeout: float = Field(default=3.0, gt=0)
    # Connections that send nothing (not even pings) for this long are closed
    idle_timeout: float = Field(default=30.0, gt=0)

    @field_validator("cert_file", "key_file", "token_file")
    @classmethod
    def _expand_user(cls, value: Path) -> Path:
        return Path(value).expanduser()


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
            "model": "tiny",
            "language": "en",
            "device": "cpu",
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

    # File opener configuration
    file_openers: FileOpenersConfig = FileOpenersConfig()

    # Remote trigger server (e.g. a Pico 2 W button)
    remote: RemoteConfig = RemoteConfig()

    # Path to log file (uses platform defaults if not specified)
    log_file: Optional[Path] = None

    # Hotkey listener method: "auto", "portal", or "pynput"
    # "auto" (default): Try portal on Wayland, fall back to pynput
    # "portal": Force XDG Portal GlobalShortcuts (Wayland only)
    # "pynput": Force pynput listener (works on X11, may need XWayland on Wayland)
    hotkey_listener: str = "auto"

    # Whether to log key repeat debug messages (portal listener only)
    # Set to true for debugging key repeat issues, false to reduce log noise
    log_key_repeat_debug: bool = False


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
            get_app_data_dir() / "settings.toml",
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
