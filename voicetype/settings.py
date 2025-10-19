from pathlib import Path
from typing import Any, Dict, List, Optional

import toml
from loguru import logger
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Main application settings."""

    pipelines: Optional[List[Dict[str, Any]]] = None


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

        # Check for legacy settings format and provide helpful error
        if "voice" in data or "hotkey" in data:
            logger.error(
                f"Legacy settings format detected in {settings_file}\n"
                f"The [voice] and [hotkey] sections are no longer supported.\n"
                f"Please update your settings file to use the [[pipelines]] format.\n"
                f"See settings.example.toml for the new format.\n"
                f"\nExample migration:\n"
                f"  [voice]\n"
                f'  provider = "local"\n'
                f"  minimum_duration = 0.25\n"
                f"  [hotkey]\n"
                f'  hotkey = "<pause>"\n'
                f"\n"
                f"  Becomes:\n"
                f"\n"
                f"  [[pipelines]]\n"
                f'  name = "default"\n'
                f"  enabled = true\n"
                f'  hotkey = "<pause>"\n'
                f"  [[pipelines.stages]]\n"
                f'  func = "record_audio"\n'
                f"  minimum_duration = 0.25\n"
                f"  [[pipelines.stages]]\n"
                f'  func = "transcribe"\n'
                f'  provider = "local"\n'
                f"  [[pipelines.stages]]\n"
                f'  func = "type_text"\n'
            )
            raise ValueError(
                f"Legacy settings format no longer supported. "
                f"Please update {settings_file} to use [[pipelines]] format. "
                f"See settings.example.toml for details."
            )

        return Settings(**data)
    return Settings()
