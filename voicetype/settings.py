from pathlib import Path
from typing import Any, Dict, List, Optional

import toml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Main application settings."""

    pipelines: Optional[List[Dict[str, Any]]] = [
        {
            "name": "default",
            "enabled": True,
            "hotkey": "<pause>",
            "stages": [
                {
                    "stage": "RecordAudio",
                    "minimum_duration": 0.25,
                },
                {
                    "stage": "Transcribe",
                    "provider": "local",
                },
                {
                    "stage": "TypeText",
                },
            ],
        }
    ]


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

    if settings_file and settings_file.is_file():
        data = toml.load(settings_file)
        return Settings(**data)
    return Settings()
