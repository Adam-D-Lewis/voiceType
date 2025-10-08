import enum
from pathlib import Path

import toml
from pydantic import Field
from pydantic_settings import BaseSettings


class VoiceSettingsProvider(enum.Enum):
    LITELLM = "litellm"
    LOCAL = "local"


class VoiceSettings(BaseSettings):
    """Settings related to the voice transcription service."""

    provider: VoiceSettingsProvider = VoiceSettingsProvider.LOCAL
    minimum_duration: float = Field(
        0.25,
        ge=0.0,
        description="Minimum duration (in seconds) of audio to process. Intended to filter out accidental hotkey presses.",
    )


class HotkeySettings(BaseSettings):
    """Settings for the global hotkey."""

    hotkey: str = "<pause>"


class Settings(BaseSettings):
    """Main application settings."""

    voice: VoiceSettings = VoiceSettings()
    hotkey: HotkeySettings = HotkeySettings()


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
