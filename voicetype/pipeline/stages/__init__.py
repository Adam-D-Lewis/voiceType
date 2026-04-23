"""Pipeline stages for voice typing workflows.

This module contains the core stages for the voice typing pipeline:
- RecordAudio: Record audio from microphone
- Transcribe: Transcribe audio to text
- CorrectTypos: Correct typos and common speech-to-text errors
- StripTrailingEllipsis: Remove trailing ellipsis from transcribed text
- LLMAgent: Process text through an LLM agent
- TypeText: Type text via virtual keyboard
"""

from .correct_typos import CorrectTypos
from .llm_agent import LLMAgent
from .record_audio import RecordAudio
from .run_command import RunCommand
from .strip_trailing_ellipsis import StripTrailingEllipsis
from .transcribe import Transcribe
from .type_text import TypeText

__all__ = [
    "RecordAudio",
    "Transcribe",
    "CorrectTypos",
    "StripTrailingEllipsis",
    "LLMAgent",
    "RunCommand",
    "TypeText",
]
