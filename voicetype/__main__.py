import argparse
import os
import platform
import threading
from pathlib import Path

from loguru import logger

from voicetype.app_context import AppContext
from voicetype.assets.sounds import EMPTY_SOUND, ERROR_SOUND, START_RECORD_SOUND
from voicetype.audio_capture import SpeechProcessor
from voicetype.hotkey_listener.hotkey_listener import HotkeyListener
from voicetype.settings import VoiceSettingsProvider, load_settings
from voicetype.state import AppState, State
from voicetype.trayicon import create_tray
from voicetype.utils import play_sound, type_text

HERE = Path(__file__).resolve().parent


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

        # Default to X11/pynput listener if session is not Wayland or Wayland init failed
        logger.info("Using X11 (pynput) listener.")
        try:
            from voicetype.hotkey_listener.linux_x11_hotkey_listener import (
                LinuxX11HotkeyListener,
            )

            return LinuxX11HotkeyListener(
                on_hotkey_press=on_press, on_hotkey_release=on_release
            )
        except Exception as e:
            logger.error(f"Failed to initialize X11 listener: {e}", exc_info=True)
            raise RuntimeError("Could not initialize any Linux hotkey listener.") from e

    elif system == "Windows":
        logger.warning("Windows detected, but listener not implemented.")
        raise NotImplementedError("Windows hotkey listener not yet implemented.")
    elif system == "Darwin":  # macOS
        logger.warning("macOS detected, but listener not implemented.")
        raise NotImplementedError("macOS hotkey listener not yet implemented.")
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
        "--settings-file", type=Path, help="Path to the settings TOML file."
    )
    args = parser.parse_args()

    settings = load_settings(args.settings_file)

    logger.info("Starting VoiceType application...")

    try:
        # Forward-declare context so callbacks can use it.
        # It will be properly initialized before the listener is started.
        ctx = None

        def on_hotkey_press():
            if ctx and ctx.state.state == State.LISTENING:
                ctx.state.state = State.RECORDING
                logger.debug("Hotkey pressed: State -> RECORDING")
                play_sound(START_RECORD_SOUND)
                ctx.speech_processor.start_recording()
            else:
                logger.warning(
                    f"Hotkey pressed in unexpected state: {ctx.state.state if ctx else 'uninitialized'}"
                )

        def on_hotkey_release():
            if ctx and ctx.state.state == State.RECORDING:
                ctx.state.state = State.PROCESSING
                logger.debug("Hotkey released: State -> PROCESSING")
                audio_file = ctx.speech_processor.stop_recording()

                def transcribe_and_type():
                    try:
                        if not audio_file:
                            text = ctx.speech_processor.transcribe(audio_file)
                            if text:
                                try:
                                    type_text(text)
                                except Exception as e:
                                    logger.error(f"Failed to type text: {e}")
                                    play_sound(ERROR_SOUND)
                            else:
                                logger.warning("Transcription returned no text")
                                play_sound(ERROR_SOUND)
                        else:
                            logger.warning("No audio file to transcribe")
                            play_sound(ERROR_SOUND)
                    except Exception as e:
                        logger.error(f"Transcription failed: {e}")
                        play_sound(ERROR_SOUND)
                    finally:
                        ctx.state.state = State.LISTENING
                        logger.debug("State -> LISTENING")

                threading.Thread(target=transcribe_and_type, daemon=True).start()
            else:
                logger.warning(
                    f"Hotkey released in unexpected state: {ctx.state.state if ctx else 'uninitialized'}"
                )

        hotkey_listener = get_platform_listener(
            on_press=on_hotkey_press, on_release=on_hotkey_release
        )
        hotkey_listener.set_hotkey(settings.hotkey.hotkey)

        speech_processor = SpeechProcessor(settings=settings.voice)

        ctx = AppContext(
            state=AppState(),
            speech_processor=speech_processor,
            hotkey_listener=hotkey_listener,
        )
        ctx.state.state = State.LISTENING

        # Play empty sound to initialize audio system (workaround for first sound not playing)
        play_sound(EMPTY_SOUND)

        hotkey_listener.start_listening()

        logger.info(f"Intended hotkey: {settings.hotkey.hotkey}")
        logger.info("Press Ctrl+C to exit.")

        # Start the system tray icon (blocks until closed)
        tray = create_tray(ctx)
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
        if "listener" in locals() and hotkey_listener:
            try:
                hotkey_listener.stop_listening()
                logger.info("Hotkey listener stopped.")
            except Exception as e:
                logger.error(f"Error stopping listener: {e}", exc_info=True)
        logger.info("VoiceType application finished.")


if __name__ == "__main__":
    main()
