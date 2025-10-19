"""Pipeline stages for voice typing workflows.

This module contains the core stages for the voice typing pipeline:
- record_audio: Record audio from microphone
- transcribe: Transcribe audio to text
- type_text: Type text via virtual keyboard
"""

from .record_audio import TemporaryAudioFile, record_audio
from .transcribe import transcribe
from .type_text import type_text

__all__ = [
    "TemporaryAudioFile",
    "record_audio",
    "transcribe",
    "type_text",
]
