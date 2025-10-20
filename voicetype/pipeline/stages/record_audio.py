"""Record audio stage for pipeline execution.

This stage records audio from the microphone until the trigger completes
(e.g., hotkey is released) and returns the filepath to the temporary audio file.
"""

import os
from pathlib import Path
from typing import Optional

from loguru import logger

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


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
    """

    required_resources = {Resource.AUDIO_INPUT}

    def __init__(self, config: dict, metadata: dict):
        """Initialize the record audio stage.

        Args:
            config: Stage-specific configuration
            metadata: Shared pipeline metadata containing speech_processor
        """
        self.config = config
        self.speech_processor = metadata.get("speech_processor")
        if not self.speech_processor:
            raise RuntimeError(
                "Speech processor not found in pipeline metadata. "
                "Ensure it's added to initial_metadata when executing pipeline."
            )
        self.current_recording: Optional[str] = None

    def execute(self, input_data: None, context: PipelineContext) -> Optional[str]:
        """Execute audio recording.

        Args:
            input_data: None (first stage in pipeline)
            context: PipelineContext with config and trigger_event

        Returns:
            Filepath to audio file or None if recording was too short
        """
        # Start recording
        self.speech_processor.start_recording()
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
        filename, duration = self.speech_processor.stop_recording()
        logger.debug(f"Recording stopped: duration={duration:.2f}s")

        # Store filepath for cleanup
        self.current_recording = filename

        # Filter out too-short recordings
        min_duration = self.config.get("minimum_duration", 0.25)
        if duration < min_duration:
            logger.info(
                f"Recording too short ({duration:.2f}s < {min_duration}s), filtering out"
            )
            # Return None - the stage's cleanup() will still be called
            return None

        # Return filepath - stage cleanup() will handle cleanup
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
