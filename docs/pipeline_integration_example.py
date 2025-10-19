"""Example of how to integrate the new pipeline system with the main application.

This is a reference implementation showing how to wire up the pipeline system
with the existing hotkey listener and application context.
"""

from pathlib import Path

from loguru import logger

from voicetype.audio_capture import SpeechProcessor
from voicetype.pipeline import (
    HotkeyManager,
    PipelineManager,
    Resource,
    ResourceManager,
)
from voicetype.settings import load_settings


class SimpleIconController:
    """Simple icon controller implementation for demonstration.

    In the real application, this would wrap the pystray tray icon.
    """

    def __init__(self):
        self.current_state = "idle"

    def set_icon(self, state: str, duration: float = None):
        """Set the system tray icon state."""
        logger.info(f"Icon state: {state}")
        self.current_state = state

    def start_flashing(self, state: str):
        """Start flashing the icon."""
        logger.info(f"Icon flashing: {state}")

    def stop_flashing(self):
        """Stop flashing the icon."""
        logger.info("Icon stopped flashing")


def main_example():
    """Example main function showing pipeline system integration."""

    # 1. Load settings (with automatic migration)
    settings = load_settings()
    logger.info("Settings loaded")

    # 2. Initialize components
    resource_manager = ResourceManager()
    icon_controller = SimpleIconController()
    speech_processor = SpeechProcessor(settings=settings.voice)

    # 3. Create pipeline manager
    pipeline_manager = PipelineManager(
        resource_manager=resource_manager,
        icon_controller=icon_controller,
        max_workers=4,
    )

    # 4. Load pipelines from settings
    if settings.pipelines:
        pipeline_manager.load_pipelines(settings.pipelines)
    else:
        logger.warning("No pipelines configured")
        return

    # 5. Create hotkey manager
    hotkey_manager = HotkeyManager(pipeline_manager)

    # 6. Set up hotkey listener (platform-specific)
    # In real app, this would be PynputHotkeyListener or LinuxX11HotkeyListener
    from voicetype.hotkey_listener.pynput_hotkey_listener import (
        PynputHotkeyListener,
    )

    # Create listener with callbacks from hotkey manager
    listener = PynputHotkeyListener(
        on_hotkey_press=lambda: None,  # Will be replaced per-hotkey
        on_hotkey_release=lambda: None,  # Will be replaced per-hotkey
    )

    hotkey_manager.set_hotkey_listener(listener)

    # 7. Register all pipeline hotkeys
    # Note: The actual registration would need to be adapted to work with
    # the existing hotkey listener API, which may need refactoring
    for pipeline in pipeline_manager.pipelines.values():
        if pipeline.enabled:
            logger.info(
                f"Would register hotkey '{pipeline.hotkey}' for pipeline '{pipeline.name}'"
            )
            # In real implementation:
            # listener.register(pipeline.hotkey,
            #                   on_press=lambda: hotkey_manager._on_press(pipeline.hotkey),
            #                   on_release=lambda: hotkey_manager._on_release(pipeline.hotkey))

    # 8. Add speech processor to initial metadata for stages
    # This would be passed when triggering pipelines
    initial_metadata = {"speech_processor": speech_processor}

    # 9. Example: Trigger a pipeline programmatically
    pipeline_id = pipeline_manager.trigger_pipeline(
        pipeline_name="basic_dictation",
        trigger_event=None,  # Or create a ProgrammaticTriggerEvent
        metadata=initial_metadata,
    )

    if pipeline_id:
        logger.info(f"Pipeline triggered with ID: {pipeline_id}")
    else:
        logger.error("Failed to trigger pipeline (resources busy)")

    # 10. In real app, start the hotkey listener and tray icon
    # listener.start_listening()
    # tray.run()

    # 11. Cleanup on shutdown
    try:
        # Application runs here...
        import time

        time.sleep(60)  # Simulate running
    finally:
        pipeline_manager.shutdown(timeout=5.0)
        logger.info("Application shut down")


if __name__ == "__main__":
    # This is just an example and won't run as-is
    # It shows the structure of how to integrate the pipeline system
    logger.info("This is an integration example, not meant to be run directly")
    logger.info("See voicetype/__main__.py for the actual implementation")
