"""Type text stage for pipeline execution.

This stage types text character-by-character using the virtual keyboard.
"""

from typing import Optional

from loguru import logger

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY


@STAGE_REGISTRY.register(
    name="type_text",
    input_type=Optional[str],
    output_type=type(None),
    description="Type text using virtual keyboard",
    required_resources={Resource.KEYBOARD},
)
def type_text(input_data: Optional[str], context: PipelineContext) -> None:
    """Type text stage implementation.

    Types the input text character-by-character using the virtual keyboard.
    If input is None, returns immediately.

    Type signature: StageFunction[Optional[str], None]
    - Input: Optional[str] (text to type or None)
    - Output: None (final stage)

    Config parameters:
    - typing_speed: Optional typing speed in characters per second

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
