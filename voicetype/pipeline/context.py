"""Pipeline context and icon controller interfaces.

The PipelineContext provides shared state and configuration for all stages
in a pipeline execution.
"""

import threading
from typing import Any, Dict, Optional, Protocol

from .trigger_events import TriggerEvent


class IconController(Protocol):
    """Interface for controlling the system tray icon state.

    This protocol defines the interface that stages use to update the
    system tray icon. The actual implementation is provided by the
    tray icon module.
    """

    def set_icon(self, state: str, duration: Optional[float] = None) -> None:
        """Set the system tray icon to a specific state.

        Args:
            state: Icon state (e.g., "idle", "recording", "processing", "error")
            duration: Optional duration in seconds before reverting to previous icon
        """
        ...

    def start_flashing(self, state: str) -> None:
        """Start flashing the icon in the specified state.

        Args:
            state: Icon state to flash (e.g., "recording")
        """
        ...

    def stop_flashing(self) -> None:
        """Stop flashing and return to the current non-flashing state."""
        ...


class PipelineContext:
    """Shared context for all stages in a pipeline execution.

    This context is passed to each stage and provides:
    - Stage-specific configuration
    - Icon controller for updating system tray
    - Optional trigger event (for hotkey/timer triggers)
    - Cancellation event
    - Shared metadata dictionary for inter-stage communication
    """

    def __init__(
        self,
        config: Dict[str, Any],
        icon_controller: IconController,
        trigger_event: Optional[TriggerEvent] = None,
        cancel_requested: Optional[threading.Event] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a new pipeline context.

        Args:
            config: Stage-specific configuration from settings.toml
            icon_controller: Interface to update system tray icon
            trigger_event: Optional trigger event (hotkey/timer)
            cancel_requested: Event set when pipeline should be cancelled
            metadata: Shared data between stages (e.g., speech_processor)
        """
        self.config = config
        self.icon_controller = icon_controller
        self.trigger_event = trigger_event
        self.cancel_requested = cancel_requested or threading.Event()
        self.metadata = metadata or {}
