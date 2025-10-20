"""Pipeline stages for voice typing workflows.

This module contains the core stages for the voice typing pipeline:
- RecordAudio: Record audio from microphone
- Transcribe: Transcribe audio to text
- TypeText: Type text via virtual keyboard
"""

from .record_audio import RecordAudio
from .transcribe import Transcribe
from .type_text import TypeText

# Export both old names (for compatibility) and new names
RecordAudioStage = RecordAudio  # Compatibility alias
TranscribeStage = Transcribe  # Compatibility alias
TypeTextStage = TypeText  # Compatibility alias

__all__ = [
    "RecordAudio",
    "RecordAudioStage",  # Keep for compatibility
    "Transcribe",
    "TranscribeStage",  # Keep for compatibility
    "TypeText",
    "TypeTextStage",  # Keep for compatibility
]
