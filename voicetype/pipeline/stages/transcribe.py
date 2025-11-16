"""Transcribe audio stage for pipeline execution.

This stage transcribes audio files to text using the configured STT provider
(local Whisper or LiteLLM API).
"""

import enum
import os
import tempfile
from pathlib import Path
from typing import Optional

from loguru import logger
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
    - backend: Backend for local provider ("faster-whisper" or "pywhispercpp", default: "faster-whisper")
    - device: Device for inference ("cuda" or "cpu", default: "cuda")
    - model: Model name (e.g., "large-v3-turbo", "base", "tiny.en")
    - compute_type: Compute type for faster-whisper ("float16", "int8", default: auto)
    - n_threads: Number of threads for pywhispercpp (default: 4)
    - language: Language code (default: "en")
    - history: Optional context for better accuracy
    - audio_format: Audio format (default: "wav")
    """

    required_resources = set()  # No exclusive resources needed

    def __init__(self, config: dict):
        """Initialize the transcribe stage.

        Args:
            config: Stage-specific configuration
        """
        self.config = config
        self.audio_format = config.get("audio_format", "wav")

    def _transcribe_with_faster_whisper(
        self,
        filename: str,
        model: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: Optional[str] = None,
        language: str = "en",
    ) -> str:
        """Transcribe audio using faster-whisper backend.

        Args:
            filename: Path to audio file
            model: Model size (e.g., "large-v3-turbo", "base", "tiny")
            device: Device to use ("cuda" or "cpu")
            compute_type: Compute type ("float16", "int8", None for auto)
            language: Language code

        Returns:
            str: Transcribed text with leading/trailing whitespace removed
        """
        import speech_recognition as sr
        from speech_recognition.recognizers.whisper_local import faster_whisper

        audio = sr.AudioData.from_file(filename)

        # Auto-select compute type if not specified
        if compute_type is None:
            compute_type = "float16" if device == "cuda" else "int8"

        transcribed_text = faster_whisper.recognize(
            None,
            audio_data=audio,
            model=model,
            language=language,
            init_options=faster_whisper.InitOptionalParameters(
                device=device,
                compute_type=compute_type,
            ),
        )

        # transcribed_text seems to come back with a leading space, so we strip it
        return transcribed_text.strip()

    def _transcribe_with_pywhispercpp(
        self,
        filename: str,
        model: str = "base.en",
        n_threads: int = 4,
        language: str = "en",
    ) -> str:
        """Transcribe audio using pywhispercpp backend (whisper.cpp).

        Note: pywhispercpp requires 16kHz mono WAV. This method will automatically
        convert the audio if needed.

        Args:
            filename: Path to audio file
            model: Model size (e.g., "base.en", "tiny.en", "small.en")
            n_threads: Number of CPU threads to use
            language: Language code (note: .en models are English-only)

        Returns:
            str: Transcribed text with leading/trailing whitespace removed
        """
        import tempfile

        from pywhispercpp.model import Model

        temp_file = None
        try:
            # pywhispercpp requires 16kHz mono WAV, so convert if needed
            audio = AudioSegment.from_file(filename)

            # Convert to 16kHz mono if needed
            if audio.frame_rate != 16000 or audio.channels != 1:
                audio = audio.set_frame_rate(16000).set_channels(1)

                # Save to temporary file
                temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                audio.export(temp_file.name, format="wav")
                filename_to_use = temp_file.name
                logger.debug(
                    f"Converted audio to 16kHz mono for pywhispercpp: {temp_file.name}"
                )
            else:
                filename_to_use = filename

            # Suppress verbose whisper.cpp logs
            whisper_model = Model(
                model,
                n_threads=n_threads,
                print_realtime=False,
                print_progress=False,
                redirect_whispercpp_logs_to=None,  # Redirect to devnull
            )
            segments = whisper_model.transcribe(filename_to_use, language=language)

            # Combine all segments into a single string
            transcription = " ".join([segment.text for segment in segments])

            return transcription.strip()

        finally:
            # Clean up temporary file if created
            if temp_file and Path(temp_file.name).exists():
                try:
                    Path(temp_file.name).unlink()
                    logger.debug(f"Cleaned up temporary file: {temp_file.name}")
                except OSError as e:
                    logger.debug(
                        f"Warning: Could not remove temporary file {temp_file.name}: {e}"
                    )

    def _transcribe_with_local(
        self,
        filename: str,
        history: Optional[str] = None,
        language: Optional[str] = None,
    ) -> str:
        """Transcribe audio using local Whisper model.

        Routes to the appropriate backend based on configuration.

        Args:
            filename: Path to audio file
            history: Unused in local transcription
            language: Language code (defaults to "en")

        Returns:
            str: Transcribed text with leading/trailing whitespace removed
        """
        backend = self.config.get("backend", "pywhispercpp")
        device = self.config.get("device", "cuda")
        model = self.config.get("model", "tiny.en")
        language = language or self.config.get("language", "en")

        if backend == "faster-whisper":
            compute_type = self.config.get("compute_type")
            return self._transcribe_with_faster_whisper(
                filename=filename,
                model=model,
                device=device,
                compute_type=compute_type,
                language=language,
            )
        elif backend == "pywhispercpp":
            n_threads = self.config.get("n_threads", 4)
            return self._transcribe_with_pywhispercpp(
                filename=filename,
                model=model,
                n_threads=n_threads,
                language=language,
            )
        else:
            raise NotImplementedError(
                f"Backend '{backend}' is not supported. "
                f"Use 'faster-whisper' or 'pywhispercpp'."
            )

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

        # Get transcription settings
        provider = self.config.get("provider", "local")
        history = self.config.get("history")
        language = self.config.get("language", "en")

        # Convert string to enum if needed
        if isinstance(provider, str):
            provider = provider.lower()
            if provider == "litellm":
                provider_enum = VoiceSettingsProvider.LITELLM
            elif provider == "local":
                provider_enum = VoiceSettingsProvider.LOCAL
            else:
                raise NotImplementedError(f"Provider '{provider}' is not supported.")
        else:
            provider_enum = provider

        logger.info(f"Using '{provider_enum.value}' provider for transcription.")

        # Transcribe based on provider
        if provider_enum == VoiceSettingsProvider.LITELLM:
            text = self._transcribe_with_litellm(input_data, history, language)
        elif provider_enum == VoiceSettingsProvider.LOCAL:
            text = self._transcribe_with_local(input_data, history, language)
        else:
            raise NotImplementedError(f"Provider '{provider_enum}' is not supported.")

        # replace multiple spaces with single space
        text = " ".join(text.split())

        if text:
            logger.info(f"Transcription result: {text}")
        else:
            logger.warning("Transcription returned no text")

        return text
