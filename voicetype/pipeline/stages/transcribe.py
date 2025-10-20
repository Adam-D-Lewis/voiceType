"""Transcribe audio stage for pipeline execution.

This stage transcribes audio files to text using the configured STT provider
(local Whisper or LiteLLM API).
"""

from typing import Optional

from loguru import logger

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


@STAGE_REGISTRY.register
class Transcribe(PipelineStage[Optional[str], Optional[str]]):
    """Transcribe audio file to text.

    Transcribes the audio file to text using the configured STT provider.
    If input is None (e.g., recording was too short), returns None.

    Type signature: PipelineStage[Optional[str], Optional[str]]
    - Input: Optional[str] (filepath to audio file or None)
    - Output: Optional[str] (transcribed text or None)

    Config parameters:
    - provider: STT provider ("local" or "litellm", default: "local")
    - model: Model name (optional, provider-specific)
    - language: Language code (default: "en")
    - history: Optional context for better accuracy
    """

    required_resources = set()  # No exclusive resources needed

    def __init__(self, config: dict, metadata: dict):
        """Initialize the transcribe stage.

        Args:
            config: Stage-specific configuration
            metadata: Shared pipeline metadata containing speech_processor
        """
        self.config = config
        self.speech_processor = metadata.get("speech_processor")
        if not self.speech_processor:
            raise RuntimeError("Speech processor not found in pipeline metadata")

    def execute(
        self, input_data: Optional[str], context: PipelineContext
    ) -> Optional[str]:
        """Execute transcription.

        Args:
            input_data: Filepath to audio file or None
            context: PipelineContext with config

        Returns:
            Transcribed text or None if no input
        """
        if input_data is None:
            logger.info("No audio to transcribe (input is None)")
            return None

        # Update icon to processing state
        context.icon_controller.set_icon("processing")
        logger.debug(f"Transcribing audio file: {input_data}")

        # Transcribe the audio file
        text = self.speech_processor.transcribe(
            filename=input_data,
            provider=self.config.get("provider", "local"),
            history=self.config.get("history"),
            language=self.config.get("language", "en"),
        )

        if text:
            logger.info(f"Transcription result: {text}")
        else:
            logger.warning("Transcription returned no text")

        return text
