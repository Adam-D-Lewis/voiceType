"""Pipeline stages for voice typing workflows.

This module contains the core stages for the voice typing pipeline:
- RecordAudio: Record audio from microphone
- Transcribe: Transcribe audio to text
- CorrectTypos: Correct typos and common speech-to-text errors
- LLMAgent: Process text through an LLM agent
- TypeText: Type text via virtual keyboard
"""

from .correct_typos import CorrectTypos
from .llm_agent import LLMAgent
from .record_audio import RecordAudio
from .transcribe import Transcribe
from .type_text import TypeText

__all__ = [
    "RecordAudio",
    "Transcribe",
    "CorrectTypos",
    "LLMAgent",
    "TypeText",
]
