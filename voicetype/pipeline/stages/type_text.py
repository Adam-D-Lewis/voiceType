"""Type text stage for pipeline execution.

This stage types text character-by-character using the virtual keyboard.

On Linux, this uses the privileged service for typing (via socket) to ensure
reliable keyboard input on both X11 and Wayland. On Windows/macOS, it uses
pynput directly.
"""

import platform
import time
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


class TypeTextConfig(BaseModel):
    """Configuration for TypeText stage."""

    char_delay: float = Field(
        default=0.001,
        ge=0,
        description="Delay in seconds between each character (increase if letters are scrambled)",
    )


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
            config: Stage-specific configuration dict

        Raises:
            ValidationError: If config validation fails
        """
        # Parse and validate config
        self.cfg = TypeTextConfig(**config)

        # Keep char_delay accessible for compatibility
        self.char_delay = self.cfg.char_delay

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

        if platform.system() == "Linux":
            # On Linux, use privileged service for typing (works on Wayland)
            self._type_via_socket(input_data)
        else:
            # On Windows/macOS, use pynput directly
            self._type_with_pynput(input_data)

        context.icon_controller.set_icon("idle")
        logger.debug("Typing complete")

    def _type_via_socket(self, text: str) -> None:
        """Type text via the privileged service socket.

        This is used on Linux to ensure reliable typing on both X11 and Wayland.

        Args:
            text: The text to type.
        """
        from voicetype.hotkey_listener.socket_listener import get_active_socket_listener

        listener = get_active_socket_listener()
        if listener is not None and listener.is_connected():
            logger.debug("Typing via privileged service")
            listener.type_text(text, self.char_delay)
        else:
            # Fallback to direct pynput (may not work on Wayland)
            logger.warning(
                "Privileged service not connected, falling back to direct pynput"
            )
            self._type_with_pynput(text)

    def _type_with_pynput(self, text: str) -> None:
        """Type text directly using pynput.

        This is used on Windows/macOS, or as a fallback on Linux.

        Args:
            text: The text to type.
        """
        import pynput

        keyboard = pynput.keyboard.Controller()

        # Type each character with a delay to prevent scrambled letters
        for i, char in enumerate(text):
            keyboard.type(char)
            # Don't sleep after the last character
            if self.char_delay > 0 and i < len(text) - 1:
                time.sleep(self.char_delay)
