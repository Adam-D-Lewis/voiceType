"""Type text stage for pipeline execution.

This stage types text character-by-character using the virtual keyboard.
"""

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
    - typing_speed: Optional typing speed in characters per second
    """

    required_resources = {Resource.KEYBOARD}

    def __init__(self, config: dict, metadata: dict):
        """Initialize the type text stage.

        Args:
            config: Stage-specific configuration
            metadata: Shared pipeline metadata (unused for this stage)
        """
        self.config = config

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

        # Type each character
        # TODO: Add typing_speed support from config
        for char in input_data:
            keyboard.type(char)

        context.icon_controller.set_icon("idle")
        logger.debug("Typing complete")
