import argparse
import os
import platform
import sys
from pathlib import Path

from loguru import logger

from voicetype.app_context import AppContext
from voicetype.assets.sounds import EMPTY_SOUND, ERROR_SOUND, START_RECORD_SOUND
from voicetype.hotkey_listener.hotkey_listener import HotkeyListener
from voicetype.pipeline import (
    HotkeyDispatcher,
    PipelineManager,
    ResourceManager,
)
from voicetype.settings import load_settings
from voicetype.state import AppState, State
from voicetype.telemetry import (
    _get_trace_file_path,
    initialize_telemetry,
    shutdown_telemetry,
)
from voicetype.trayicon import TrayIconController, create_tray
from voicetype.utils import play_sound, type_text

HERE = Path(__file__).resolve().parent


def get_log_file_path() -> Path:
    """Get the default path to the log file in the user's config directory."""
    if sys.platform == "win32":
        config_dir = Path(os.environ.get("APPDATA", "~/.config")) / "voicetype"
    elif sys.platform == "darwin":
        config_dir = Path.home() / "Library" / "Application Support" / "voicetype"
    else:  # Linux and other Unix-like systems
        config_dir = (
            Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
            / "voicetype"
        )

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
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        backtrace=True,
        diagnose=True,
    )

    logger.info(f"Logging to file: {log_file}")
    return log_file


def get_platform_listener(on_press: callable, on_release: callable) -> HotkeyListener:
    """Detect the platform/session and return a listener instance (callbacks bound later)."""
    system = platform.system()

    if system == "Linux":
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()
        logger.info(f"Detected Linux with session type: {session_type}")

        if session_type == "wayland":
            # Check if XWayland is available
            xwayland_available = os.environ.get("XWAYLAND_DISPLAY") is not None
            if xwayland_available:
                logger.info("XWayland appears to be available.")
            else:
                raise NotImplementedError(
                    "Wayland hotkey listener only currently implemented for XWayland."
                )

        # Default to pynput listener for Linux X11
        logger.info("Using pynput listener for Linux.")
        try:
            from voicetype.hotkey_listener.pynput_hotkey_listener import (
                PynputHotkeyListener,
            )

            return PynputHotkeyListener(
                on_hotkey_press=on_press, on_hotkey_release=on_release
            )
        except Exception as e:
            logger.error(f"Failed to initialize pynput listener: {e}", exc_info=True)
            raise RuntimeError("Could not initialize Linux hotkey listener.") from e

    elif system == "Windows":
        logger.info("Using pynput listener for Windows.")
        try:
            from voicetype.hotkey_listener.pynput_hotkey_listener import (
                PynputHotkeyListener,
            )

            return PynputHotkeyListener(
                on_hotkey_press=on_press, on_hotkey_release=on_release
            )
        except Exception as e:
            logger.error(f"Failed to initialize pynput listener: {e}", exc_info=True)
            raise RuntimeError("Could not initialize Windows hotkey listener.") from e

    elif system == "Darwin":  # macOS
        logger.info("Using pynput listener for macOS.")
        try:
            from voicetype.hotkey_listener.pynput_hotkey_listener import (
                PynputHotkeyListener,
            )

            return PynputHotkeyListener(
                on_hotkey_press=on_press, on_hotkey_release=on_release
            )
        except Exception as e:
            logger.error(f"Failed to initialize pynput listener: {e}", exc_info=True)
            raise RuntimeError("Could not initialize macOS hotkey listener.") from e
    else:
        raise OSError(f"Unsupported operating system: {system}")


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
        )

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

            # Get the first enabled pipeline's hotkey for the listener
            # NOTE: Current HotkeyListener only supports single hotkey
            # For multi-hotkey support, we'd need to extend the listener
            first_pipeline = pipeline_manager.pipelines[enabled_pipelines[0]]
            hotkey_string = first_pipeline.hotkey

            # Create hotkey callbacks that delegate to HotkeyDispatcher
            def on_hotkey_press():
                """Hotkey press handler - delegates to pipeline manager."""
                if ctx.state.state == State.ENABLED:
                    logger.debug("Hotkey pressed")
                    play_sound(START_RECORD_SOUND)
                    # Trigger pipeline via hotkey dispatcher
                    hotkey_dispatcher._on_press(hotkey_string)
                else:
                    logger.debug(
                        f"Hotkey pressed but app is disabled (state: {ctx.state.state})"
                    )

            def on_hotkey_release():
                """Hotkey release handler - delegates to pipeline manager."""
                if ctx.state.state == State.ENABLED:
                    logger.debug("Hotkey released")
                    # Signal release to hotkey dispatcher
                    hotkey_dispatcher._on_release(hotkey_string)
                else:
                    logger.debug(
                        f"Hotkey released but app is disabled (state: {ctx.state.state})"
                    )

            # Create platform-specific listener
            hotkey_listener = get_platform_listener(
                on_press=on_hotkey_press, on_release=on_hotkey_release
            )
            hotkey_listener.set_hotkey(hotkey_string)

            # Set the listener in hotkey dispatcher (for compatibility)
            hotkey_dispatcher.set_hotkey_listener(hotkey_listener)

            # Update context with listener
            ctx.hotkey_listener = hotkey_listener

            # Play empty sound to initialize audio system
            play_sound(EMPTY_SOUND)

            # Start listening
            hotkey_listener.start_listening()

            logger.info(f"Listening for hotkey: {hotkey_string}")
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
