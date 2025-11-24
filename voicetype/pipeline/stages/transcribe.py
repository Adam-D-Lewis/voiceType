"""Transcribe audio stage for pipeline execution.

This stage transcribes audio files to text using the configured STT provider
(local Whisper or LiteLLM API).
"""

import enum
import os
import tempfile
from pathlib import Path
from typing import Literal, Optional, Union

from loguru import logger
from pydantic import BaseModel, Field
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError, CouldntEncodeError

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


class VoiceSettingsProvider(enum.Enum):
    """Speech-to-text provider options."""

    LITELLM = "litellm"
    LOCAL = "local"


class TranscriptionError(Exception):
    """Exception raised for transcription errors."""


class LocalTranscribeConfig(BaseModel):
    """Configuration for local transcription provider."""

    provider: Literal["local"] = "local"
    model: str = Field(
        default="large-v3-turbo",
        description="Whisper model: tiny, base, small, medium, large-v3, large-v3-turbo",
    )
    language: str = Field(default="en", description="Language code (e.g., en, es, fr)")
    device: Literal["cuda", "cpu"] = Field(
        default="cuda", description="Device for inference"
    )
    audio_format: str = Field(default="wav", description="Audio format")
    history: Optional[str] = Field(
        default=None, description="Optional context (unused for local)"
    )


class LiteLLMTranscribeConfig(BaseModel):
    """Configuration for LiteLLM transcription provider."""

    provider: Literal["litellm"] = "litellm"
    language: str = Field(default="en", description="Language code for transcription")
    audio_format: str = Field(default="wav", description="Audio format")
    history: Optional[str] = Field(
        default=None, description="Optional context for better accuracy"
    )


# Union type for discriminated configuration
TranscribeConfigUnion = Union[LocalTranscribeConfig, LiteLLMTranscribeConfig]


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
    - model: Model name (default: "large-v3-turbo" for local, provider-specific for litellm)
    - language: Language code (default: "en")
    - device: Device for local transcription ("cuda" or "cpu", default: "cuda")
    - history: Optional context for better accuracy
    - audio_format: Audio format (default: "wav")
    """

    required_resources = set()  # No exclusive resources needed

    def __init__(self, config: dict):
        """Initialize the transcribe stage.

        Args:
            config: Stage-specific configuration dict

        Raises:
            ValueError: If config validation fails or provider is unknown
        """
        # Parse and validate config based on provider
        provider = config.get("provider", "local")

        if provider == "local":
            self.cfg: TranscribeConfigUnion = LocalTranscribeConfig(**config)
        elif provider == "litellm":
            self.cfg: TranscribeConfigUnion = LiteLLMTranscribeConfig(**config)
        else:
            raise ValueError(
                f"Unknown provider: {provider}. Must be 'local' or 'litellm'"
            )

        # Keep audio_format accessible for compatibility
        self.audio_format = self.cfg.audio_format

    def _transcribe_with_local(
        self,
        filename: str,
        model: str = "large-v3-turbo",
        language: str = "en",
        device: str = "cuda",
        history: Optional[str] = None,
    ) -> str:
        """Transcribe audio using local Whisper model via speech_recognition.

        Args:
            filename: Path to audio file
            model: Whisper model to use (default: "large-v3-turbo")
            language: Language code for transcription (default: "en")
            device: Device to use for inference ("cuda" or "cpu", default: "cuda")
            history: Unused in local transcription

        Returns:
            str: Transcribed text with leading/trailing whitespace removed
        """
        import speech_recognition as sr
        from speech_recognition.recognizers.whisper_local import faster_whisper

        audio = sr.AudioData.from_file(filename)

        transcribed_text = faster_whisper.recognize(
            None,
            audio_data=audio,
            model=model,
            language=language,
            init_options=faster_whisper.InitOptionalParameters(
                device=device,
            ),
        )

        # transcribed_text seems to come back with a leading space, so we strip it
        return transcribed_text.strip()

    def _transcribe_with_litellm(
        self,
        filename: str,
        history: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Optional[str]:
        """Transcribe audio using OpenAI's Whisper API via litellm.

        Handles file size limits by converting large WAV files to MP3.
        Automatically cleans up temporary files after transcription.

        Args:
            filename: Path to the audio file to transcribe
            history: Optional context to improve transcription accuracy
            language: Optional language code for transcription

        Returns:
            str: Transcribed text, or None if transcription fails

        Raises:
            TranscriptionError: If OPENAI_API_KEY environment variable is not set
        """
        if not os.getenv("OPENAI_API_KEY"):
            raise TranscriptionError(
                "OPENAI_API_KEY environment variable not set. "
                "Please set it to use the litellm provider."
            )

        if not filename or not os.path.exists(filename):
            logger.debug(f"Error: Audio file not found or invalid: {filename}")
            return None

        logger.debug(f"Transcribing {filename}...")
        final_filename = filename
        use_audio_format = self.audio_format

        # Check file size and offer to convert if too large and format is wav
        file_size = Path(filename).stat().st_size
        if file_size > 24.9 * 1024 * 1024 and self.audio_format == "wav":
            logger.debug(
                f"\nWarning: {filename} ({file_size / (1024 * 1024):.1f} MB) "
                f"may be too large for some APIs, converting to mp3."
            )
            use_audio_format = "mp3"

        # Convert if necessary
        if use_audio_format != "wav":
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=f".{use_audio_format}",
                    delete=False,
                ) as tmp_file:
                    new_filename = tmp_file.name
                logger.debug(f"Converting {filename} to {use_audio_format}...")
                audio = AudioSegment.from_wav(filename)
                audio.export(new_filename, format=use_audio_format)
                logger.debug(f"Conversion successful: {new_filename}")
                # Keep original wav for now, transcribe the converted file
                final_filename = new_filename
            except (CouldntDecodeError, CouldntEncodeError) as e:
                logger.debug(
                    f"Error converting audio to {use_audio_format}: {e}. "
                    f"Will attempt transcription with original WAV."
                )
                final_filename = filename  # Fallback to original wav
            except (OSError, FileNotFoundError) as e:
                logger.debug(
                    f"File system error during conversion: {e}. "
                    f"Will attempt transcription with original WAV."
                )
                final_filename = filename
            except Exception as e:
                logger.debug(
                    f"Unexpected error during audio conversion: {e}. "
                    f"Will attempt transcription with original WAV."
                )
                final_filename = filename

        # Transcribe
        transcript_text = None
        try:
            with Path.open(final_filename, "rb") as fh:
                import litellm

                transcript = litellm.transcription(
                    model="whisper-1",
                    file=fh,
                    prompt=history,
                    language=language,
                )
                transcript_text = transcript.text
                logger.debug("Transcription successful.")
        except Exception as err:
            logger.debug(f"Error during transcription of {final_filename}: {err}")
            transcript_text = None  # Ensure it's None on error

        # Cleanup
        if final_filename != filename:
            # If conversion happened, remove the converted file
            try:
                Path(final_filename).unlink(missing_ok=True)
                logger.debug(f"Cleaned up temporary converted file: {final_filename}")
            except OSError as e:
                logger.debug(
                    f"Warning: Could not remove temporary converted file {final_filename}: {e}"
                )

        # Always remove the original temporary WAV file
        try:
            Path(filename).unlink(missing_ok=True)
            logger.debug(f"Cleaned up original recording file: {filename}")
        except OSError as e:
            logger.debug(
                f"Warning: Could not remove original recording file {filename}: {e}"
            )

        return transcript_text

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

        logger.info(f"Using '{self.cfg.provider}' provider for transcription.")

        # Transcribe based on provider using type-safe config
        if isinstance(self.cfg, LocalTranscribeConfig):
            text = self._transcribe_with_local(
                input_data,
                model=self.cfg.model,
                language=self.cfg.language,
                device=self.cfg.device,
                history=self.cfg.history,
            )
        elif isinstance(self.cfg, LiteLLMTranscribeConfig):
            text = self._transcribe_with_litellm(
                input_data,
                history=self.cfg.history,
                language=self.cfg.language,
            )
        else:
            raise NotImplementedError(
                f"Provider '{self.cfg.provider}' is not supported."
            )

        # replace multiple spaces with single space
        text = " ".join(text.split())

        if text:
            logger.info(f"Transcription result: {text}")
        else:
            logger.warning("Transcription returned no text")

        return text
