"""Pipeline stages for voice typing workflows.

This module contains the core stages for the voice typing pipeline:
- RecordAudio: Record audio from microphone
- Transcribe: Transcribe audio to text
- TypeText: Type text via virtual keyboard
"""

from .record_audio import RecordAudio
from .transcribe import Transcribe
from .type_text import TypeText

__all__ = [
    "RecordAudio",
    "Transcribe",
    "TypeText",
]
