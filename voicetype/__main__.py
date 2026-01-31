import argparse
import platform
import sys
from pathlib import Path

from loguru import logger

from voicetype.app_context import AppContext
from voicetype.assets.sounds import EMPTY_SOUND, ERROR_SOUND, START_RECORD_SOUND
from voicetype.hotkey_listener import HotkeyListener, create_hotkey_listener
from voicetype.pipeline import (
    HotkeyDispatcher,
    PipelineManager,
    ResourceManager,
)
from voicetype.platform_detection import get_compositor_name, get_display_server
from voicetype.settings import load_settings
from voicetype.state import AppState, State
from voicetype.telemetry import (
    _get_trace_file_path,
    initialize_telemetry,
    shutdown_telemetry,
)
from voicetype.trayicon import TrayIconController, create_tray
from voicetype.utils import get_app_data_dir, play_sound, type_text

HERE = Path(__file__).resolve().parent


def get_log_file_path() -> Path:
    """Get the default path to the log file in the user's config directory."""
    config_dir = get_app_data_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "voicetype.log"


def configure_logging(log_file: Path | None = None) -> Path:
    """Configure loguru to log to both stderr and a rotating file.

    Args:
        log_file: Optional custom path to log file. If None, uses platform defaults.

    Returns:
        The path to the log file being used.
    """
    if log_file is None:
        log_file = get_log_file_path()
    else:
        # Ensure parent directory exists for custom log file
        log_file = Path(log_file).expanduser().resolve()
        log_file.parent.mkdir(parents=True, exist_ok=True)

    # Keep the default stderr handler for systemd/console output
    # Add a rotating file handler
    logger.add(
        log_file,
        rotation="10 MB",  # Rotate when file reaches 10 MB
        retention=3,  # Keep 3 old log files
        compression="zip",  # Compress rotated logs
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"Logging to file: {log_file}")
    return log_file


def get_platform_listener(
    on_press: callable,
    on_release: callable,
    method: str = "auto",
    log_key_repeat_debug: bool = False,
) -> HotkeyListener:
    """Detect the platform/session and return a listener instance.

    This function uses the factory function from the hotkey_listener module
    to automatically select the appropriate listener based on the platform:
    - Wayland with GlobalShortcuts portal: PortalHotkeyListener
    - X11, Windows, macOS: PynputHotkeyListener

    Args:
        on_press: Callback function to execute when the hotkey is pressed.
        on_release: Callback function to execute when the hotkey is released.
        method: Hotkey listener method ("auto", "portal", or "pynput")
        log_key_repeat_debug: Whether to log key repeat debug messages (portal only)

    Returns:
        An appropriate HotkeyListener instance for the current platform.

    Raises:
        RuntimeError: If no suitable hotkey listener can be initialized.
    """
    system = platform.system()
    logger.info(f"Detected platform: {system}")

    if system == "Linux":
        display_server = get_display_server()
        compositor = get_compositor_name()
        logger.info(
            f"Linux display server: {display_server}, compositor: {compositor or 'unknown'}"
        )

    try:
        return create_hotkey_listener(
            on_hotkey_press=on_press,
            on_hotkey_release=on_release,
            method=method,
            log_key_repeat_debug=log_key_repeat_debug,
        )
    except Exception as e:
        logger.error(f"Failed to initialize hotkey listener: {e}", exc_info=True)
        raise RuntimeError(f"Could not initialize hotkey listener on {system}.") from e


def unload_stt_model():
    """Unload the STT model from GPU memory"""
    import gc

    import torch

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

    gc.collect()


def main():
    """Main application entry point."""
    parser = argparse.ArgumentParser(description="VoiceType application.")
    parser.add_argument(
        "--settings-file",
        type=Path,
        help="Path to the settings TOML file.",
    )
    args = parser.parse_args()

    settings = load_settings(args.settings_file)

    # Configure logging to file + stderr (using custom path from settings if provided)
    log_file_path = configure_logging(settings.log_file)

    # Initialize telemetry (defaults: enabled=True, export_to_file=True)
    initialize_telemetry(
        service_name=settings.telemetry.service_name,
        otlp_endpoint=settings.telemetry.otlp_endpoint,
        export_to_file=settings.telemetry.export_to_file,
        trace_file=settings.telemetry.trace_file,
        enabled=settings.telemetry.enabled,
        rotation_enabled=settings.telemetry.rotation_enabled,
        rotation_max_size_mb=settings.telemetry.rotation_max_size_mb,
    )

    logger.info("Starting VoiceType application...")

    # Initialize managers
    pipeline_manager = None
    hotkey_dispatcher = None
    hotkey_listener = None
    tray = None
    icon_controller = None

    try:
        # Create app context for tray icon compatibility
        trace_file_path = None
        if settings.telemetry.enabled:
            trace_file_path = _get_trace_file_path(settings.telemetry.trace_file)

        ctx = AppContext(
            state=AppState(),
            hotkey_listener=None,  # Will be set later
            pipeline_manager=None,  # Will be set later
            log_file_path=log_file_path,
            telemetry_enabled=settings.telemetry.enabled,
            trace_file_path=trace_file_path,
        )
        # Start with app enabled
        ctx.state.state = State.ENABLED

        # Create tray icon (but don't run it yet)
        tray = create_tray(ctx)

        # Wrap tray icon with IconController interface
        icon_controller = TrayIconController(tray)

        # Initialize pipeline system
        resource_manager = ResourceManager()
        pipeline_manager = PipelineManager(
            resource_manager=resource_manager,
            icon_controller=icon_controller,
            max_workers=4,
            app_state=ctx.state,
        )

        # Set pipeline_manager in context
        ctx.pipeline_manager = pipeline_manager

        # Load pipelines
        if settings.pipelines:
            pipeline_manager.load_pipelines(
                settings.pipelines, stage_definitions=settings.stage_configs
            )
        else:
            logger.warning("No pipelines configured")

        # Initialize hotkey dispatcher
        hotkey_dispatcher = HotkeyDispatcher(pipeline_manager)

        # Check if we have any enabled pipelines
        enabled_pipelines = pipeline_manager.list_enabled_pipelines()
        if not enabled_pipelines:
            logger.warning("No enabled pipelines found")
        else:
            logger.info(
                f"Found {len(enabled_pipelines)} enabled pipeline(s): {', '.join(enabled_pipelines)}"
            )

            # Create hotkey callbacks that delegate to HotkeyDispatcher
            def on_hotkey_press(hotkey_str: str):
                """Hotkey press handler - delegates to pipeline manager."""
                if ctx.state.state == State.ENABLED:
                    logger.debug(f"Hotkey pressed: {hotkey_str}")
                    play_sound(START_RECORD_SOUND)
                    hotkey_dispatcher._on_press(hotkey_str)
                else:
                    logger.debug(
                        f"Hotkey pressed but app is disabled (state: {ctx.state.state})"
                    )

            def on_hotkey_release(hotkey_str: str):
                """Hotkey release handler - delegates to pipeline manager."""
                logger.debug(f"Hotkey released: {hotkey_str}")
                hotkey_dispatcher._on_release(hotkey_str)

            # Create platform-specific listener
            hotkey_listener = get_platform_listener(
                on_press=on_hotkey_press,
                on_release=on_hotkey_release,
                method=settings.hotkey_listener,
                log_key_repeat_debug=settings.log_key_repeat_debug,
            )

            # Register hotkeys for ALL enabled pipelines
            registered_hotkeys = set()
            for pipeline_name in enabled_pipelines:
                pipeline = pipeline_manager.pipelines[pipeline_name]
                hotkey_string = pipeline.hotkey
                if hotkey_string not in registered_hotkeys:
                    hotkey_listener.add_hotkey(hotkey_string)
                    registered_hotkeys.add(hotkey_string)
                    logger.info(
                        f"Registered hotkey '{hotkey_string}' for pipeline '{pipeline_name}'"
                    )

            # Set the listener in hotkey dispatcher (for compatibility)
            hotkey_dispatcher.set_hotkey_listener(hotkey_listener)

            # Update context with listener
            ctx.hotkey_listener = hotkey_listener

            # Play empty sound to initialize audio system
            play_sound(EMPTY_SOUND)

            # Start listening
            hotkey_listener.start_listening()

            logger.info(f"Listening for hotkeys: {registered_hotkeys}")
            logger.info("Press Ctrl+C to exit.")

        # Start the system tray icon (blocks until closed)
        tray.run()

    except KeyboardInterrupt:
        logger.info("Shutdown requested via KeyboardInterrupt.")
    except NotImplementedError as e:
        logger.error(f"Initialization failed: {e}")
    except Exception as e:
        import traceback

        logger.error(f"An unexpected error occurred: {e}\n{traceback.format_exc()}")
    finally:
        logger.info("Shutting down...")

        # Stop hotkey listener
        if hotkey_listener:
            try:
                hotkey_listener.stop_listening()
                logger.info("Hotkey listener stopped.")
            except Exception as e:
                logger.error(f"Error stopping listener: {e}", exc_info=True)

        # Shutdown pipeline manager
        if pipeline_manager:
            try:
                pipeline_manager.shutdown(timeout=5.0)
            except Exception as e:
                logger.error(
                    f"Error shutting down pipeline manager: {e}", exc_info=True
                )

        # Shutdown telemetry
        try:
            shutdown_telemetry()
        except Exception as e:
            logger.error(f"Error shutting down telemetry: {e}", exc_info=True)

        logger.info("VoiceType application finished.")


if __name__ == "__main__":
    main()
