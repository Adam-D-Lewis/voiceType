"""Record audio stage for pipeline execution.

This stage records audio from the microphone until the trigger completes
(e.g., hotkey is released) and returns a TemporaryAudioFile wrapper.
"""

import os
from pathlib import Path
from typing import Optional

from loguru import logger

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY


class TemporaryAudioFile:
    """Wrapper for temporary audio files with automatic cleanup.

    This class provides a consistent interface for temporary audio files
    and implements the cleanup protocol expected by the pipeline manager.
    """

    def __init__(self, filepath: str, duration: float = 0.0):
        """Initialize the temporary audio file wrapper.

        Args:
            filepath: Path to the temporary audio file
            duration: Duration of the audio in seconds
        """
        self.filepath = filepath
        self.duration = duration

    def cleanup(self):
        """Remove temporary file - called by pipeline manager ONLY.

        This method should NEVER be called by stages. The pipeline manager
        is solely responsible for calling cleanup() in its finally block.
        """
        if os.path.exists(self.filepath):
            try:
                os.unlink(self.filepath)
                logger.debug(f"Cleaned up temp file: {self.filepath}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {self.filepath}: {e}")

    def __repr__(self):
        return f"TemporaryAudioFile(filepath={self.filepath}, duration={self.duration:.2f}s)"


@STAGE_REGISTRY.register(
    name="record_audio",
    input_type=type(None),
    output_type=Optional[TemporaryAudioFile],
    description="Record audio until trigger completes",
    required_resources={Resource.AUDIO_INPUT},
)
def record_audio(
    input_data: None, context: PipelineContext
) -> Optional[TemporaryAudioFile]:
    """Record audio stage implementation.

    Records audio from the microphone until the trigger completes (e.g., hotkey
    is released) or max_duration timeout is reached. Filters out recordings
    shorter than minimum_duration.

    Type signature: StageFunction[None, Optional[TemporaryAudioFile]]
    - Input: None (first stage)
    - Output: Optional[TemporaryAudioFile] (audio file wrapper or None if too short)

    Config parameters:
    - max_duration: Maximum recording duration in seconds (default: 60)
    - minimum_duration: Minimum duration to process in seconds (default: 0.25)
    - device_name: Optional audio device name (default: system default)

    Args:
        input_data: None (first stage in pipeline)
        context: PipelineContext with config and trigger_event

    Returns:
        TemporaryAudioFile wrapper or None if recording was too short
    """
    # Get speech processor from metadata
    speech_processor = context.metadata.get("speech_processor")
    if not speech_processor:
        raise RuntimeError(
            "Speech processor not found in pipeline metadata. "
            "Ensure it's added to initial_metadata when executing pipeline."
        )

    # Start recording
    speech_processor.start_recording()
    context.icon_controller.set_icon("recording")
    logger.debug("Recording started")

    # Wait for trigger completion (e.g., key release)
    max_duration = context.config.get("max_duration", 60.0)

    if context.trigger_event:
        context.trigger_event.wait_for_completion(timeout=max_duration)
    else:
        # No trigger event: wait for cancellation or timeout
        context.cancel_requested.wait(timeout=max_duration)

    # Stop recording
    filename, duration = speech_processor.stop_recording()
    logger.debug(f"Recording stopped: duration={duration:.2f}s")

    # Create wrapper object
    audio_file = TemporaryAudioFile(filepath=filename, duration=duration)

    # Filter out too-short recordings
    min_duration = context.config.get("minimum_duration", 0.25)
    if duration < min_duration:
        logger.info(
            f"Recording too short ({duration:.2f}s < {min_duration}s), filtering out"
        )
        # Store for cleanup but don't return
        # Pipeline manager will still call cleanup() on this resource
        context.metadata["_temp_resources"].append(audio_file)
        return None

    # Return wrapper - pipeline manager will call cleanup() in finally block
    return audio_file
