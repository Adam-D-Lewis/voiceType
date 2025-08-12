# import math # No longer needed directly
import os
import queue
import sys  # For stderr output
import tempfile
import threading
import time
import warnings

import numpy as np
from loguru import logger

from voicetype.audio_capture.dump import dump  # noqa: F401
from voicetype.settings import VoiceSettings, VoiceSettingsProvider

warnings.filterwarnings(
    "ignore",
    message="Couldn't find ffmpeg or avconv - defaulting to ffmpeg, but may not work",
)
warnings.filterwarnings("ignore", category=SyntaxWarning)


from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError, CouldntEncodeError

try:
    import soundfile as sf
except (OSError, ModuleNotFoundError):
    sf = None


class SoundDeviceError(Exception):
    """Exception raised for audio device and sound processing errors."""

    pass


class SpeechProcessor:
    """Audio recording and transcription system.

    Provides functionality for:
    - Recording audio from microphones using sounddevice
    - Real-time RMS calculation for volume monitoring
    - Audio transcription using OpenAI Whisper API or local Whisper models
    - Format conversion between wav, mp3, and webm
    """

    max_rms = 0
    min_rms = 1e5
    pct = 0.0  # Initialize pct

    threshold = 0.15  # Threshold for RMS visualization (if needed later)

    def __init__(self, settings: VoiceSettings, audio_format="wav", device_name=None):
        """Initialize SpeechProcessor with audio settings and device configuration.

        Args:
            settings: VoiceSettings instance containing provider and model config
            audio_format: Audio format for recordings ("wav", "mp3", or "webm")
            device_name: Specific audio device name to use, or None for default

        Raises:
            SoundDeviceError: If audio libraries are unavailable or device setup fails
            ValueError: If unsupported audio format is specified
        """
        self.settings = settings
        if sf is None:
            raise SoundDeviceError("SoundFile library not available.")
        try:
            logger.debug("Initializing sound device...")
            import sounddevice as sd

            self.sd = sd
        except (OSError, ModuleNotFoundError) as e:
            raise SoundDeviceError(f"SoundDevice library error: {e}")

        self.device_id = self._find_device_id(device_name)
        logger.debug(f"Using input device ID: {self.device_id}")

        if audio_format not in ["wav", "mp3", "webm"]:
            raise ValueError(f"Unsupported audio format: {audio_format}")
        self.audio_format = audio_format

        try:
            device_info = self.sd.query_devices(self.device_id, "input")
            self.sample_rate = int(device_info["default_samplerate"])
            logger.debug(f"Using sample rate: {self.sample_rate} Hz")
        except (TypeError, ValueError, KeyError) as e:
            logger.debug(
                f"Warning: Could not query default sample rate ({e}), falling back to 16kHz."
            )
            self.sample_rate = 16000
        except self.sd.PortAudioError as e:
            raise SoundDeviceError(f"PortAudio error querying device: {e}")

        self.q = queue.Queue()
        self.stream = None
        self.audio_file = None
        self.temp_wav = None
        self.is_recording = False
        self.start_time = None
        self._stop_event = (
            threading.Event()
        )  # Used to signal the callback to stop processing

    def _find_device_id(self, device_name):
        """Find the input device ID by name or return None for default.

        Args:
            device_name: Name of the audio device to search for, or None for default

        Returns:
            Device ID integer or None for default device

        Raises:
            SoundDeviceError: If no audio devices are found
            ValueError: If specified device name is not found
        """
        devices = self.sd.query_devices()
        if not devices:
            raise SoundDeviceError("No audio devices found.")

        input_devices = [
            (i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0
        ]
        if not input_devices:
            raise SoundDeviceError("No audio input devices found.")

        if device_name:
            for i, device in input_devices:
                if device_name.lower() in device["name"].lower():
                    logger.debug(f"Found specified device: {device['name']} (ID: {i})")
                    return i
            available_names = [d["name"] for _, d in input_devices]
            raise ValueError(
                f"Device '{device_name}' not found. Available input devices: {available_names}"
            )
        else:
            # No specific device name provided, return None to let sounddevice pick the default input device.
            logger.debug(
                "No specific device name provided; sounddevice will use the system's default input device."
            )
            return None

    def callback(self, indata, frames, time_info, status):
        """Audio callback function called for each audio block during recording.

        Calculates RMS values for volume monitoring and queues audio data for processing.
        Called from a separate thread by sounddevice.

        Args:
            indata: Input audio data as numpy array
            frames: Number of frames in the audio block
            time_info: Timing information from sounddevice
            status: Status flags from sounddevice
        """
        if status:
            logger.debug(f"Audio callback status: {status}", file=sys.stderr)
        if self._stop_event.is_set():  # Check if stop signal received
            raise self.sd.CallbackStop  # Signal sounddevice to stop the callback chain
        try:
            rms = np.sqrt(np.mean(indata**2))
            # Update RMS tracking (optional, could be used for visual feedback)
            self.max_rms = max(self.max_rms, rms)
            self.min_rms = min(self.min_rms, rms)

            rng = self.max_rms - self.min_rms
            if rng > 0.001:
                self.pct = (rms - self.min_rms) / rng
            else:
                self.pct = 0.5  # Avoid division by zero if range is tiny

            self.q.put(indata.copy())
        except Exception as e:
            logger.debug(f"Error in audio callback: {e}", file=sys.stderr)
            # Decide if the error is critical enough to stop recording
            # For now, just print it.

    # Removed get_prompt method as it's no longer used
    # def get_prompt(self): ...

    def start_recording(self):
        """Start recording audio from the configured input device.

        Creates a temporary WAV file and begins streaming audio data.
        Resets RMS tracking values for volume monitoring.

        Raises:
            SoundDeviceError: If audio stream cannot be started
        """
        if self.is_recording:
            logger.debug("Already recording.")
            return

        logger.debug("Starting recording...")
        self.max_rms = 0  # Reset RMS tracking
        self.min_rms = 1e5
        self.pct = 0.0
        self._stop_event.clear()  # Ensure stop event is clear

        try:
            self.temp_wav = tempfile.mktemp(suffix=".wav")
            self.audio_file = sf.SoundFile(
                self.temp_wav, mode="x", samplerate=self.sample_rate, channels=1
            )
            self.stream = self.sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self.callback,
                device=self.device_id,
            )
            self.stream.start()
            self.start_time = time.time()
            self.is_recording = True
            logger.debug(f"Recording started, saving to {self.temp_wav}")
        except self.sd.PortAudioError as e:
            self.is_recording = False  # Ensure state is correct
            if self.audio_file:
                self.audio_file.close()
                self.audio_file = None
            if os.path.exists(self.temp_wav):
                os.remove(self.temp_wav)
                self.temp_wav = None
            raise SoundDeviceError(f"Failed to start audio stream: {e}")
        except Exception as e:
            self.is_recording = False
            if self.audio_file:
                self.audio_file.close()
                self.audio_file = None
            if self.temp_wav and os.path.exists(self.temp_wav):
                os.remove(self.temp_wav)
                self.temp_wav = None
            logger.debug(f"An unexpected error occurred during start_recording: {e}")
            raise  # Re-raise the exception

    def stop_recording(self):
        """Stop recording audio and save to temporary file.

        Processes any remaining audio data in the queue and closes the audio file.

        Returns:
            str: Path to the saved WAV file, or None if not recording
        """
        if not self.is_recording:
            logger.debug("Not recording.")
            return None

        logger.debug("Stopping recording...")
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                logger.debug("Audio stream stopped and closed.")
            except self.sd.PortAudioError as e:
                logger.debug(f"Warning: PortAudioError stopping/closing stream: {e}")
            except Exception as e:
                logger.debug(f"Warning: Unexpected error stopping/closing stream: {e}")
            finally:
                self.stream = None

        self._stop_event.set()  # Signal callback to stop processing queue

        # Process any remaining items in the queue after stopping the stream
        logger.debug(
            f"Processing remaining audio data (queue size: {self.q.qsize()})..."
        )

        # Give a moment for the last chunks of audio to arrive in the queue
        time.sleep(0.1)

        while not self.q.empty():
            try:
                data = self.q.get_nowait()
                if self.audio_file and not self.audio_file.closed:
                    self.audio_file.write(data)
            except queue.Empty:
                break  # Queue is empty
            except Exception as e:
                logger.debug(f"Error writing remaining audio data: {e}")

        if self.audio_file:
            try:
                self.audio_file.close()
                logger.debug(f"Audio file closed: {self.temp_wav}")
            except Exception as e:
                logger.debug(f"Warning: Error closing audio file: {e}")
            finally:
                self.audio_file = None

        recorded_filename = self.temp_wav
        self.temp_wav = None  # Clear temp path
        self.is_recording = False
        self.start_time = None
        logger.debug("Recording stopped.")
        return recorded_filename

    def transcribe(self, filename, history=None, language=None):
        """Transcribe audio file to text using the configured provider.

        Args:
            filename: Path to the audio file to transcribe
            history: Optional context/history for better transcription accuracy
            language: Optional language code for transcription

        Returns:
            str: Transcribed text, or None if transcription fails

        Raises:
            NotImplementedError: If provider is not supported
        """
        provider = self.settings.provider
        logger.info(f"Using '{provider}' provider for transcription.")

        if provider == VoiceSettingsProvider.LITELLM:
            return self._transcribe_with_litellm(filename, history, language)
        elif provider == VoiceSettingsProvider.LOCAL:
            return self._transcribe_with_local(filename, history, language)
        else:
            raise NotImplementedError(f"Provider '{provider}' is not supported.")

    def _transcribe_with_local(self, filename, history, language):
        """Transcribe audio using local Whisper model via speech_recognition.

        Args:
            filename: Path to audio file
            history: Unused in local transcription
            language: Unused in local transcription (defaults to English)

        Returns:
            str: Transcribed text with leading/trailing whitespace removed
        """
        import speech_recognition as sr
        from speech_recognition.recognizers.whisper_local import faster_whisper

        audio = sr.AudioData.from_file(filename)

        transcribed_text = faster_whisper.recognize(
            None, audio_data=audio, model="large-v3", language="en"
        )

        # transcribed_text seems to come back with a leading space, so we strip it
        return transcribed_text.strip()

    def _transcribe_with_litellm(self, filename, history=None, language=None):
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
            SoundDeviceError: If OPENAI_API_KEY environment variable is not set
        """
        if not os.getenv("OPENAI_API_KEY"):
            raise SoundDeviceError(
                "OPENAI_API_KEY environment variable not set. Please set it to use the litellm provider."
            )

        if not filename or not os.path.exists(filename):
            logger.debug(f"Error: Audio file not found or invalid: {filename}")
            return None

        logger.debug(f"Transcribing {filename}...")
        final_filename = filename
        use_audio_format = self.audio_format

        # Check file size and offer to convert if too large and format is wav
        file_size = os.path.getsize(filename)
        if file_size > 24.9 * 1024 * 1024 and self.audio_format == "wav":
            logger.debug(
                f"\nWarning: {filename} ({file_size / (1024 * 1024):.1f} MB) may be too large for some APIs, converting to mp3."
            )
            use_audio_format = "mp3"

        # Convert if necessary
        if use_audio_format != "wav":
            try:
                new_filename = tempfile.mktemp(suffix=f".{use_audio_format}")
                logger.debug(f"Converting {filename} to {use_audio_format}...")
                audio = AudioSegment.from_wav(filename)
                audio.export(new_filename, format=use_audio_format)
                logger.debug(f"Conversion successful: {new_filename}")
                # Keep original wav for now, transcribe the converted file
                final_filename = new_filename
            except (CouldntDecodeError, CouldntEncodeError) as e:
                logger.debug(
                    f"Error converting audio to {use_audio_format}: {e}. Will attempt transcription with original WAV."
                )
                final_filename = filename  # Fallback to original wav
            except (OSError, FileNotFoundError) as e:
                logger.debug(
                    f"File system error during conversion: {e}. Will attempt transcription with original WAV."
                )
                final_filename = filename
            except Exception as e:
                logger.debug(
                    f"Unexpected error during audio conversion: {e}. Will attempt transcription with original WAV."
                )
                final_filename = filename

        # Transcribe
        transcript_text = None
        try:
            with open(final_filename, "rb") as fh:
                from aider.llm import litellm

                transcript = litellm.transcription(
                    model="whisper-1", file=fh, prompt=history, language=language
                )
                transcript_text = transcript.text
                logger.debug("Transcription successful.")
        except Exception as err:
            logger.debug(f"Error during transcription of {final_filename}: {err}")
            transcript_text = None  # Ensure it's None on error

        # Cleanup
        if (
            final_filename != filename
        ):  # If conversion happened, remove the converted file
            try:
                # os.remove(final_filename)
                logger.debug(f"Cleaned up temporary converted file: {final_filename}")
            except OSError as e:
                logger.debug(
                    f"Warning: Could not remove temporary converted file {final_filename}: {e}"
                )

        # Always remove the original temporary WAV file
        try:
            # os.remove(filename)
            logger.debug(f"Cleaned up original recording file: {filename}")
        except OSError as e:
            logger.debug(
                f"Warning: Could not remove original recording file {filename}: {e}"
            )

        return transcript_text
