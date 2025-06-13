import enum
from pathlib import Path
from typing import Literal

import toml
from pydantic_settings import BaseSettings


class VoiceSettingsProvider(enum.Enum):
    LITELLM = "litellm"
    LOCAL = "local"


class VoiceSettings(BaseSettings):
    """Settings related to the voice transcription service."""

    provider: VoiceSettingsProvider = VoiceSettingsProvider.LITELLM


class HotkeySettings(BaseSettings):
    """Settings for the global hotkey."""

    hotkey: str = "<pause>"


class Settings(BaseSettings):
    """Main application settings."""

    voice: VoiceSettings = VoiceSettings()
    hotkey: HotkeySettings = HotkeySettings()


def load_settings(settings_file: Path | None = None) -> Settings:
    """Loads settings from a TOML file, falling back to environment variables."""
    if settings_file and settings_file.is_file():
        data = toml.load(settings_file)
        return Settings(**data)
    return Settings()
