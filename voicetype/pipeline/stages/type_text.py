"""Type text stage for pipeline execution.

This stage types text character-by-character using the virtual keyboard.
"""

import time
from typing import Optional

from loguru import logger

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


@STAGE_REGISTRY.register
class TypeText(PipelineStage[Optional[str], None]):
    """Type text using virtual keyboard.

    Types the input text character-by-character using the virtual keyboard.
    If input is None, returns immediately.

    Type signature: PipelineStage[Optional[str], None]
    - Input: Optional[str] (text to type or None)
    - Output: None (final stage)

    Config parameters:
    - char_delay: Delay in seconds between each character (default: 0.005)
                  Increase this value if you experience scrambled letters
    """

    required_resources = {Resource.KEYBOARD}

    def __init__(self, config: dict):
        """Initialize the type text stage.

        Args:
            config: Stage-specific configuration
        """
        self.config = config
        self.char_delay = config.get("char_delay", 0.005)

    def execute(self, input_data: Optional[str], context: PipelineContext) -> None:
        """Execute text typing.

        Args:
            input_data: Text to type or None
            context: PipelineContext with config

        Returns:
            None
        """
        if input_data is None:
            logger.info("No text to type (input is None)")
            return

        logger.debug(f"Typing text: {input_data}")

        # Import keyboard controller
        # Import from _vendor package which sets up sys.path correctly
        from voicetype._vendor import pynput

        keyboard = pynput.keyboard.Controller()

        # Type each character with a delay to prevent scrambled letters
        for i, char in enumerate(input_data):
            keyboard.type(char)
            # Don't sleep after the last character
            if self.char_delay > 0 and i < len(input_data) - 1:
                time.sleep(self.char_delay)

        context.icon_controller.set_icon("idle")
        logger.debug("Typing complete")
