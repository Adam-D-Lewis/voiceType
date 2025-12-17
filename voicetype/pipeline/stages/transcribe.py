"""Transcribe audio stage for pipeline execution.

This stage transcribes audio files to text using the configured STT provider
(local Whisper or LiteLLM API).
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

from loguru import logger
from pydantic import BaseModel, Field
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError, CouldntEncodeError

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage
from voicetype.utils import get_app_data_dir


def get_bundled_model_path(model_name: str) -> Optional[Path]:
    """Get path to bundled Whisper model if it exists.

    Checks for a bundled model in the application's models directory.
    This is used when running from a PyInstaller bundle.

    Args:
        model_name: Name of the model (e.g., 'tiny', 'base', 'small')

    Returns:
        Path to the bundled model directory, or None if not found
    """
    # When running from PyInstaller bundle, sys._MEIPASS points to the temp dir
    if hasattr(sys, "_MEIPASS"):
        bundled_path = (
            Path(sys._MEIPASS) / "voicetype" / "models" / f"faster-whisper-{model_name}"
        )
        if bundled_path.exists():
            logger.debug(f"Found bundled model at {bundled_path}")
            return bundled_path

    # Also check relative to the voicetype package (for development)
    package_dir = Path(__file__).parent.parent.parent
    dev_path = package_dir / "models" / f"faster-whisper-{model_name}"
    if dev_path.exists():
        logger.debug(f"Found model at {dev_path}")
        return dev_path

    return None


class TranscriptionError(Exception):
    """Exception raised for transcription errors."""


# =============================================================================
# Runtime Models - Unified STT runtime configurations
# =============================================================================

FasterWhisperModels = Literal[
    "tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"
]


class LocalSTTRuntime(BaseModel):
    """Configuration for local Whisper transcription runtime."""

    provider: Literal["local"] = "local"
    model: FasterWhisperModels = Field(
        default="tiny",
        description="Whisper model: tiny, base, small, medium, large-v3, large-v3-turbo",
    )
    device: Literal["cuda", "cpu"] = Field(
        default="cpu", description="Device for inference"
    )


class LiteLLMSTTRuntime(BaseModel):
    """Configuration for LiteLLM API transcription runtime."""

    provider: Literal["litellm"] = "litellm"
    model: str = Field(
        default="whisper-1",
        description="LiteLLM model identifier (e.g., whisper-1, azure/whisper)",
    )


# Discriminated union for runtime types
STTRuntime = Annotated[
    Union[LocalSTTRuntime, LiteLLMSTTRuntime],
    Field(discriminator="provider"),
]


# =============================================================================
# Stage Configuration
# =============================================================================


class TranscribeConfig(BaseModel):
    """Configuration for the Transcribe stage with fallback support."""

    # Primary runtime (required)
    runtime: STTRuntime = Field(
        default_factory=LocalSTTRuntime,
        description="Primary STT runtime configuration",
    )

    # Fallback runtimes (optional)
    fallback_runtimes: list[STTRuntime] = Field(
        default_factory=list,
        description="Fallback runtimes to try if primary fails",
    )

    # Shared settings
    language: str = Field(
        default="en",
        description="Language code for transcription (e.g., en, es, fr)",
    )
    audio_format: str = Field(
        default="wav",
        description="Audio format for processing",
    )
    download_root: Optional[str] = Field(
        default=None,
        description="Directory for model downloads (local provider only)",
    )


@STAGE_REGISTRY.register
class Transcribe(PipelineStage[Optional[str], Optional[str]]):
    """Transcribe audio file to text.

    Transcribes the audio file to text using the configured STT runtime.
    Supports fallback runtimes - if the primary runtime fails, each fallback
    is tried in order until one succeeds.

    If input is None (e.g., recording was too short), returns None.

    Type signature: PipelineStage[Optional[str], Optional[str]]
    - Input: Optional[str] (filepath to audio file or None)
    - Output: Optional[str] (transcribed text or None)

    Config parameters:
    - runtime: Primary STT runtime (LocalSTTRuntime or LiteLLMSTTRuntime)
    - fallback_runtimes: List of fallback runtimes to try if primary fails
    - language: Language code for transcription
    - audio_format: Audio format for processing
    - download_root: Directory for model downloads (local provider only)
    """

    required_resources = set()  # No exclusive resources needed

    def __init__(self, config: dict):
        """Initialize the transcribe stage.

        Args:
            config: Stage-specific configuration dict

        Raises:
            ValueError: If config validation fails
        """
        self.cfg = TranscribeConfig(**config)
        # Keep audio_format accessible for compatibility
        self.audio_format = self.cfg.audio_format

    def _get_runtime_description(self, runtime: STTRuntime) -> str:
        """Get a human-readable description of a runtime configuration."""
        if isinstance(runtime, LocalSTTRuntime):
            return f"local(model={runtime.model}, device={runtime.device})"
        elif isinstance(runtime, LiteLLMSTTRuntime):
            return f"litellm(model={runtime.model})"
        else:
            return f"unknown({type(runtime).__name__})"

    def _transcribe_with_local_runtime(
        self,
        filename: str,
        runtime: LocalSTTRuntime,
        language: str = "en",
        download_root: Optional[str] = None,
    ) -> str:
        """Transcribe audio using a local Whisper runtime.

        Args:
            filename: Path to audio file
            runtime: LocalSTTRuntime configuration to use
            language: Language code for transcription (default: "en")
            download_root: Directory where models are downloaded/cached

        Returns:
            str: Transcribed text with leading/trailing whitespace removed

        Raises:
            Exception: Any error during transcription (to allow fallback handling)
        """
        from faster_whisper import WhisperModel

        model = runtime.model
        device = runtime.device

        # Check for bundled model first (for PyInstaller builds)
        bundled_path = get_bundled_model_path(model)
        if bundled_path:
            model_path = str(bundled_path)
            logger.info(f"Using bundled Whisper model from {bundled_path}")
        else:
            model_path = model
            logger.debug(
                f"No bundled model found for '{model}', will download if needed"
            )

        # Build init options - default to app data dir for models so they get cleaned up on uninstall
        models_dir = download_root or str(get_app_data_dir() / "models")
        logger.debug(f"Using model download root: {models_dir}")

        # Determine compute type based on device
        compute_type = "float16" if device == "cuda" else "int8"

        # Initialize the WhisperModel
        whisper_model = WhisperModel(
            model_path,
            device=device,
            compute_type=compute_type,
            download_root=models_dir,
        )

        # Transcribe the audio file
        segments, info = whisper_model.transcribe(
            filename,
            language=language,
        )

        # Combine all segments into a single text
        transcribed_text = " ".join(segment.text for segment in segments)

        # transcribed_text seems to come back with a leading space, so we strip it
        return transcribed_text.strip()

    def _transcribe_with_litellm_runtime(
        self,
        filename: str,
        runtime: LiteLLMSTTRuntime,
        language: str = "en",
    ) -> str:
        """Transcribe audio using LiteLLM API runtime.

        Handles file size limits by converting large WAV files to MP3.

        Args:
            filename: Path to the audio file to transcribe
            runtime: LiteLLMSTTRuntime configuration to use
            language: Language code for transcription

        Returns:
            str: Transcribed text

        Raises:
            TranscriptionError: If API key not set or transcription fails
        """
        if not os.getenv("OPENAI_API_KEY"):
            raise TranscriptionError(
                "OPENAI_API_KEY environment variable not set. "
                "Please set it to use the litellm provider."
            )

        if not filename or not os.path.exists(filename):
            raise TranscriptionError(f"Audio file not found or invalid: {filename}")

        logger.debug(f"Transcribing {filename} with LiteLLM...")
        final_filename = filename
        use_audio_format = self.audio_format
        converted_file: Optional[str] = None

        # Check file size and convert if too large and format is wav
        file_size = Path(filename).stat().st_size
        if file_size > 24.9 * 1024 * 1024 and self.audio_format == "wav":
            logger.debug(
                f"Warning: {filename} ({file_size / (1024 * 1024):.1f} MB) "
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
                    converted_file = tmp_file.name
                logger.debug(f"Converting {filename} to {use_audio_format}...")
                audio = AudioSegment.from_wav(filename)
                audio.export(converted_file, format=use_audio_format)
                logger.debug(f"Conversion successful: {converted_file}")
                final_filename = converted_file
            except (CouldntDecodeError, CouldntEncodeError) as e:
                logger.debug(
                    f"Error converting audio to {use_audio_format}: {e}. "
                    f"Will attempt transcription with original WAV."
                )
                final_filename = filename
                converted_file = None
            except (OSError, FileNotFoundError) as e:
                logger.debug(
                    f"File system error during conversion: {e}. "
                    f"Will attempt transcription with original WAV."
                )
                final_filename = filename
                converted_file = None
            except Exception as e:
                logger.debug(
                    f"Unexpected error during audio conversion: {e}. "
                    f"Will attempt transcription with original WAV."
                )
                final_filename = filename
                converted_file = None

        # Transcribe
        try:
            with Path(final_filename).open("rb") as fh:
                import litellm

                transcript = litellm.transcription(
                    model=runtime.model,
                    file=fh,
                    language=language,
                )
                transcript_text = transcript.text
                logger.debug("Transcription successful.")
        except Exception as err:
            raise TranscriptionError(f"LiteLLM transcription failed: {err}") from err
        finally:
            # Cleanup converted file if we created one
            if converted_file:
                try:
                    Path(converted_file).unlink(missing_ok=True)
                    logger.debug(
                        f"Cleaned up temporary converted file: {converted_file}"
                    )
                except OSError as e:
                    logger.debug(
                        f"Warning: Could not remove temporary converted file {converted_file}: {e}"
                    )

        return transcript_text.strip() if transcript_text else ""

    def _transcribe_single_runtime(
        self,
        filename: str,
        runtime: STTRuntime,
    ) -> str:
        """Transcribe audio using a single runtime configuration.

        Dispatches to the appropriate runtime-specific method based on runtime type.

        Args:
            filename: Path to audio file
            runtime: STTRuntime configuration (LocalSTTRuntime or LiteLLMSTTRuntime)

        Returns:
            str: Transcribed text

        Raises:
            Exception: Any error during transcription
        """
        if isinstance(runtime, LocalSTTRuntime):
            return self._transcribe_with_local_runtime(
                filename=filename,
                runtime=runtime,
                language=self.cfg.language,
                download_root=self.cfg.download_root,
            )
        elif isinstance(runtime, LiteLLMSTTRuntime):
            return self._transcribe_with_litellm_runtime(
                filename=filename,
                runtime=runtime,
                language=self.cfg.language,
            )
        else:
            raise TranscriptionError(f"Unknown runtime type: {type(runtime).__name__}")

    def _transcribe_with_fallbacks(self, filename: str) -> str:
        """Transcribe audio with fallback support across all runtime types.

        Attempts transcription with the primary runtime first. If it fails, tries each
        fallback runtime in order until one succeeds.

        Args:
            filename: Path to audio file

        Returns:
            str: Transcribed text

        Raises:
            TranscriptionError: If all runtimes fail
        """
        all_runtimes = [self.cfg.runtime] + self.cfg.fallback_runtimes
        last_error: Optional[Exception] = None

        for i, runtime in enumerate(all_runtimes):
            runtime_desc = self._get_runtime_description(runtime)
            is_fallback = i > 0

            if is_fallback:
                logger.info(f"Trying fallback runtime {i}: {runtime_desc}")
            else:
                logger.info(f"Trying primary runtime: {runtime_desc}")

            try:
                result = self._transcribe_single_runtime(filename, runtime)
                if is_fallback:
                    logger.info(f"Fallback runtime {i} succeeded: {runtime_desc}")
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Runtime failed ({runtime_desc}): {type(e).__name__}: {e}"
                )
                continue

        # All runtimes failed
        raise TranscriptionError(
            f"All {len(all_runtimes)} transcription runtime(s) failed. "
            f"Last error: {type(last_error).__name__}: {last_error}"
        )

    def execute(
        self, input_data: Optional[str], context: PipelineContext
    ) -> Optional[str]:
        """Execute transcription with fallback support.

        Attempts transcription with the primary runtime, falling back to
        configured fallback runtimes if the primary fails.

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

        # Transcribe with fallback support
        text = self._transcribe_with_fallbacks(input_data)

        # Replace multiple spaces with single space
        text = " ".join(text.split())

        if text:
            logger.info(f"Transcription result: {text}")
        else:
            logger.warning("Transcription returned no text")

        return text
