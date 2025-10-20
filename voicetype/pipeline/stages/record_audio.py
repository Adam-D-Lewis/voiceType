"""Record audio stage for pipeline execution.

This stage records audio from the microphone until the trigger completes
(e.g., hotkey is released) and returns the filepath to the temporary audio file.
"""

import os
import queue
import sys
import tempfile
import threading
import time
from typing import Any, Optional

import numpy as np
import sounddevice as sd
import soundfile as sf
from loguru import logger

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage

# Audio processing constants
MIN_RMS_RANGE = 0.001  # Minimum RMS range to avoid division by zero


class SoundDeviceError(Exception):
    """Exception raised for audio device and sound processing errors."""


@STAGE_REGISTRY.register
class RecordAudio(PipelineStage[None, Optional[str]]):
    """Record audio until trigger completes.

    Records audio from the microphone until the trigger completes (e.g., hotkey
    is released) or max_duration timeout is reached. Filters out recordings
    shorter than minimum_duration.

    Type signature: PipelineStage[None, Optional[str]]
    - Input: None (first stage)
    - Output: Optional[str] (filepath to audio file or None if too short)

    Config parameters:
    - max_duration: Maximum recording duration in seconds (default: 60)
    - minimum_duration: Minimum duration to process in seconds (default: 0.25)
    - device_name: Optional audio device name (default: system default)
    - audio_format: Audio format for recordings (default: "wav")
    """

    required_resources = {Resource.AUDIO_INPUT}

    # RMS tracking for volume monitoring
    max_rms = 0
    min_rms = 1e5
    pct = 0.0

    def __init__(self, config: dict, metadata: dict):
        """Initialize the record audio stage.

        Args:
            config: Stage-specific configuration
            metadata: Shared pipeline metadata (not used in this refactored version)
        """
        self.config = config
        self.audio_format = config.get("audio_format", "wav")

        if self.audio_format not in ["wav", "mp3", "webm"]:
            raise ValueError(
                f"Unsupported audio format: {self.audio_format}. "
                f"Supported formats are 'wav', 'mp3', and 'webm'."
            )

        # Initialize audio device
        device_name = config.get("device_name")
        self.device_id = self._find_device_id(device_name)
        logger.debug(f"Using input device ID: {self.device_id}")

        # Get sample rate from device
        try:
            device_info = sd.query_devices(self.device_id, "input")
            self.sample_rate = int(device_info["default_samplerate"])
            logger.debug(f"Using sample rate: {self.sample_rate} Hz")
        except (TypeError, ValueError, KeyError) as e:
            logger.debug(
                f"Warning: Could not query default sample rate ({e}), falling back to 16kHz."
            )
            self.sample_rate = 16000
        except sd.PortAudioError as e:
            raise SoundDeviceError("PortAudio error querying device.") from e

        # Recording state
        self.q = queue.Queue()
        self.stream = None
        self.audio_file = None
        self.temp_wav = None
        self.is_recording = False
        self.start_time = None
        self._stop_event = threading.Event()
        self.current_recording: Optional[str] = None

    def _find_device_id(self, device_name: Optional[str]) -> Optional[int]:
        """Find the input device ID by name or return None for default.

        Args:
            device_name: Name of the audio device to search for, or None for default

        Returns:
            Device ID integer or None for default device

        Raises:
            SoundDeviceError: If no audio devices are found
            ValueError: If specified device name is not found
        """
        devices = sd.query_devices()
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

        # No specific device name provided, return None for default
        logger.debug(
            "No specific device name provided; sounddevice will use the system's default input device."
        )
        return None

    def _callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
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
        if self._stop_event.is_set():
            raise sd.CallbackStop
        try:
            rms = np.sqrt(np.mean(indata**2))
            # Update RMS tracking (optional, could be used for visual feedback)
            self.max_rms = max(self.max_rms, rms)
            self.min_rms = min(self.min_rms, rms)

            rng = self.max_rms - self.min_rms
            if rng > MIN_RMS_RANGE:
                self.pct = (rms - self.min_rms) / rng
            else:
                self.pct = 0.5  # Avoid division by zero if range is tiny

            self.q.put(indata.copy())
        except Exception as e:
            logger.debug(f"Error in audio callback: {e}", file=sys.stderr)

    def _start_recording(self) -> None:
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
        self._stop_event.clear()

        try:
            temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            self.temp_wav = temp_wav.name
            temp_wav.close()

            self.audio_file = sf.SoundFile(
                self.temp_wav,
                mode="w",
                samplerate=self.sample_rate,
                channels=1,
            )
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                callback=self._callback,
                device=self.device_id,
            )
            self.stream.start()
            self.start_time = time.time()
            self.is_recording = True
            logger.debug(f"Recording started, saving to {self.temp_wav}")
        except sd.PortAudioError as e:
            self.is_recording = False
            if self.audio_file:
                self.audio_file.close()
                self.audio_file = None
            if self.temp_wav and os.path.exists(self.temp_wav):
                os.unlink(self.temp_wav)
                self.temp_wav = None
            raise SoundDeviceError(f"PortAudio error starting audio stream: {e}") from e
        except Exception as e:
            self.is_recording = False
            if self.audio_file:
                self.audio_file.close()
                self.audio_file = None
            if self.temp_wav and os.path.exists(self.temp_wav):
                os.unlink(self.temp_wav)
                self.temp_wav = None
            logger.debug(f"An unexpected error occurred during start_recording: {e}")
            raise

    def _stop_recording(self) -> tuple[Optional[str], float]:
        """Stop recording audio and save to temporary file.

        Processes any remaining audio data in the queue and closes the audio file.

        Returns:
            tuple: (Path to the saved WAV file or None if not recording, duration in seconds)
        """
        if not self.is_recording:
            logger.debug("Not recording.")
            return None, 0.0

        logger.debug("Stopping recording...")
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                logger.debug("Audio stream stopped and closed.")
            except sd.PortAudioError as e:
                logger.debug(f"Warning: PortAudioError stopping/closing stream: {e}")
            except Exception as e:
                logger.debug(f"Warning: Unexpected error stopping/closing stream: {e}")
            finally:
                self.stream = None

        self._stop_event.set()

        # Process any remaining items in the queue after stopping the stream
        logger.debug(
            f"Processing remaining audio data (queue size: {self.q.qsize()})..."
        )

        while not self.q.empty():
            try:
                data = self.q.get_nowait()
                if self.audio_file and not self.audio_file.closed:
                    self.audio_file.write(data)
            except queue.Empty:
                break
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

        duration = time.time() - self.start_time if self.start_time else 0.0
        recorded_filename = self.temp_wav
        self.temp_wav = None
        self.is_recording = False
        self.start_time = None
        logger.debug(f"Recording stopped. Duration: {duration:.2f}s")
        return recorded_filename, duration

    def execute(self, input_data: None, context: PipelineContext) -> Optional[str]:
        """Execute audio recording.

        Args:
            input_data: None (first stage in pipeline)
            context: PipelineContext with config and trigger_event

        Returns:
            Filepath to audio file or None if recording was too short
        """
        # Start recording
        self._start_recording()
        context.icon_controller.set_icon("recording")
        logger.debug("Recording started")

        # Wait for trigger completion (e.g., key release)
        max_duration = self.config.get("max_duration", 60.0)

        if context.trigger_event:
            context.trigger_event.wait_for_completion(timeout=max_duration)
        else:
            # No trigger event: wait for cancellation or timeout
            context.cancel_requested.wait(timeout=max_duration)

        # Stop recording
        filename, duration = self._stop_recording()
        logger.debug(f"Recording stopped: duration={duration:.2f}s")

        # Store filepath for cleanup
        self.current_recording = filename

        # Filter out too-short recordings
        min_duration = self.config.get("minimum_duration", 0.25)
        if duration < min_duration:
            logger.info(
                f"Recording too short ({duration:.2f}s < {min_duration}s), filtering out"
            )
            return None

        return filename

    def cleanup(self):
        """Clean up temporary recording file.

        Called by pipeline manager in finally block.
        """
        if self.current_recording:
            if os.path.exists(self.current_recording):
                try:
                    os.unlink(self.current_recording)
                    logger.debug(f"Cleaned up temp file: {self.current_recording}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {self.current_recording}: {e}")
            self.current_recording = None
