"""Type text stage for pipeline execution.

This stage types text using the appropriate keyboard backend for the current platform.
"""

from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage
from voicetype.pipeline.stages.keyboard_backends import create_keyboard_backend


class TypeTextConfig(BaseModel):
    """Configuration for TypeText stage."""

    char_delay: float = Field(
        default=0.001,
        ge=0,
        description="Delay in seconds between each character (increase if letters are scrambled). Only used by pynput backend.",
    )
    keyboard_backend: str = Field(
        default="auto",
        description="Keyboard backend to use: auto, pynput, wtype, or eitype. "
        "auto selects based on platform (pynput for X11/Windows/Mac, "
        "eitype for Wayland GNOME/KDE, wtype for Wayland wlroots).",
    )


@STAGE_REGISTRY.register
class TypeText(PipelineStage[Optional[str], None]):
    """Type text using virtual keyboard.

    Types the input text using the appropriate keyboard backend for the
    current platform. If input is None, returns immediately.

    Type signature: PipelineStage[Optional[str], None]
    - Input: Optional[str] (text to type or None)
    - Output: None (final stage)

    Config parameters:
    - char_delay: Delay in seconds between each character (default: 0.001)
                  Only applies to pynput backend. Increase if letters are scrambled.
    - keyboard_backend: Backend selection (default: "auto")
                       - auto: Detect based on platform
                       - pynput: X11, Windows, macOS
                       - wtype: Wayland wlroots compositors (Sway, Hyprland, etc.)
                       - eitype: Wayland GNOME/KDE with EI support
    """

    required_resources = {Resource.KEYBOARD}

    def __init__(self, config: dict):
        """Initialize the type text stage.

        Args:
            config: Stage-specific configuration dict

        Raises:
            ValidationError: If config validation fails
            WtypeNotFoundError: If wtype is required but not installed
            EitypeNotFoundError: If eitype is required but not installed
        """
        # Parse and validate config
        self.cfg = TypeTextConfig(**config)

        # Keep char_delay accessible for compatibility
        self.char_delay = self.cfg.char_delay

        # Create the appropriate keyboard backend
        self.backend = create_keyboard_backend(
            method=self.cfg.keyboard_backend,
            char_delay=self.cfg.char_delay,
        )

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

        self.backend.type_text(input_data)

        context.icon_controller.set_icon("idle")
        logger.debug("Typing complete")
