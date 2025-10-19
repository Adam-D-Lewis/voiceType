"""Transcribe audio stage for pipeline execution.

This stage transcribes audio files to text using the configured STT provider
(local Whisper or LiteLLM API).
"""

from typing import Optional

from loguru import logger

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY

from .record_audio import TemporaryAudioFile


@STAGE_REGISTRY.register(
    name="transcribe",
    input_type=Optional[TemporaryAudioFile],
    output_type=Optional[str],
    description="Transcribe audio file to text",
    required_resources=set(),  # No exclusive resources needed
)
def transcribe(
    input_data: Optional[TemporaryAudioFile], context: PipelineContext
) -> Optional[str]:
    """Transcribe audio stage implementation.

    Transcribes the audio file to text using the configured STT provider.
    If input is None (e.g., recording was too short), returns None.

    Type signature: StageFunction[Optional[TemporaryAudioFile], Optional[str]]
    - Input: Optional[TemporaryAudioFile] (audio file wrapper or None)
    - Output: Optional[str] (transcribed text or None)

    Config parameters:
    - provider: STT provider ("local" or "litellm", default: "local")
    - model: Model name (optional, provider-specific)
    - language: Language code (default: "en")
    - history: Optional context for better accuracy

    Args:
        input_data: TemporaryAudioFile wrapper or None
        context: PipelineContext with config

    Returns:
        Transcribed text or None if no input
    """
    if input_data is None:
        logger.info("No audio to transcribe (input is None)")
        return None

    # Get speech processor from metadata
    speech_processor = context.metadata.get("speech_processor")
    if not speech_processor:
        raise RuntimeError("Speech processor not found in pipeline metadata")

    # Update icon to processing state
    context.icon_controller.set_icon("processing")
    logger.debug(f"Transcribing audio file: {input_data.filepath}")

    # Transcribe the audio file
    # The pipeline manager will clean up the file later
    text = speech_processor.transcribe(
        filename=input_data.filepath,
        history=context.config.get("history"),
        language=context.config.get("language", "en"),
    )

    if text:
        logger.info(f"Transcription result: {text}")
    else:
        logger.warning("Transcription returned no text")

    return text
