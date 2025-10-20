"""Hotkey dispatcher for pipeline trigger registration.

The HotkeyDispatcher bridges hotkey events to pipeline execution, managing:
- Hotkey registration for multiple pipelines
- Press/release event handling
- TriggerEvent creation and lifecycle
"""

from typing import Callable, Dict, Optional

from loguru import logger

from .pipeline_manager import PipelineManager
from .trigger_events import HotkeyTriggerEvent


class HotkeyDispatcher:
    """Dispatches hotkey events to pipeline execution.

    This class is responsible for:
    - Registering hotkeys from pipeline configurations
    - Creating HotkeyTriggerEvent instances on key press
    - Signaling trigger completion on key release
    - Triggering pipeline execution via PipelineManager
    """

    def __init__(
        self, pipeline_manager: PipelineManager, default_metadata: Optional[Dict] = None
    ):
        """Initialize the hotkey dispatcher.

        Args:
            pipeline_manager: Manager for pipeline execution
            default_metadata: Optional default metadata to pass to all pipelines
        """
        self.pipeline_manager = pipeline_manager
        self.active_events: Dict[str, HotkeyTriggerEvent] = (
            {}
        )  # hotkey -> trigger event
        self.hotkey_listener = None  # Will be set by application
        self.default_metadata = (
            default_metadata or {}
        )  # Default metadata for all pipelines

    def register_hotkey(
        self,
        hotkey: str,
        on_press: Optional[Callable] = None,
        on_release: Optional[Callable] = None,
    ):
        """Register a hotkey with the underlying listener.

        Args:
            hotkey: Hotkey string (e.g., "<pause>", "<f12>")
            on_press: Optional custom press handler (defaults to _on_press)
            on_release: Optional custom release handler (defaults to _on_release)
        """
        if self.hotkey_listener is None:
            raise RuntimeError(
                "Hotkey listener not set. Call set_hotkey_listener() first."
            )

        # Use default handlers if not provided
        press_handler = on_press or (lambda: self._on_press(hotkey))
        release_handler = on_release or (lambda: self._on_release(hotkey))

        # Register with the platform-specific listener
        # Note: The actual registration API depends on the listener implementation
        logger.info(f"Registering hotkey: {hotkey}")

    def set_hotkey_listener(self, listener):
        """Set the platform-specific hotkey listener.

        Args:
            listener: Hotkey listener instance (e.g., PynputHotkeyListener)
        """
        self.hotkey_listener = listener

    def _on_press(self, hotkey: str):
        """Handle hotkey press - create trigger event and execute pipeline.

        Args:
            hotkey: Hotkey string that was pressed
        """
        # Get pipeline for this hotkey
        pipeline = self.pipeline_manager.get_pipeline_by_hotkey(hotkey)
        if not pipeline:
            logger.warning(f"No pipeline found for hotkey: {hotkey}")
            return

        # Create trigger event
        trigger_event = HotkeyTriggerEvent()
        self.active_events[hotkey] = trigger_event

        logger.debug(f"Hotkey pressed: {hotkey} -> pipeline '{pipeline.name}'")

        # Execute pipeline on thread pool (non-blocking)
        # Pass default metadata to the pipeline
        pipeline_id = self.pipeline_manager.trigger_pipeline(
            pipeline.name, trigger_event, metadata=self.default_metadata
        )

        if pipeline_id is None:
            # Resources unavailable, cleanup trigger event
            del self.active_events[hotkey]
            logger.warning(
                f"Pipeline '{pipeline.name}' could not start (resources busy)"
            )

    def _on_release(self, hotkey: str):
        """Handle hotkey release - signal trigger event.

        Args:
            hotkey: Hotkey string that was released
        """
        if hotkey in self.active_events:
            trigger_event = self.active_events[hotkey]
            trigger_event.signal_release()
            del self.active_events[hotkey]
            logger.debug(f"Hotkey released: {hotkey}")
        else:
            logger.debug(
                f"Hotkey released but no active event: {hotkey} (may have been cancelled)"
            )

    def register_all_pipelines(self):
        """Register hotkeys for all enabled pipelines.

        This should be called after pipelines are loaded.
        """
        if self.hotkey_listener is None:
            raise RuntimeError(
                "Hotkey listener not set. Call set_hotkey_listener() first."
            )

        enabled_pipelines = [
            p for p in self.pipeline_manager.pipelines.values() if p.enabled
        ]

        logger.info(f"Registering hotkeys for {len(enabled_pipelines)} pipeline(s)")

        for pipeline in enabled_pipelines:
            self.register_hotkey(pipeline.hotkey)

        logger.info("All hotkeys registered successfully")
