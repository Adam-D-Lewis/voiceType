import argparse
import os
import platform
import queue
import threading
from pathlib import Path

from loguru import logger

from voicetype.globals import hotkey_listener, is_recording, typing_queue, voice
from voicetype.hotkey_listener.hotkey_listener import HotkeyListener
from voicetype.settings import VoiceSettingsProvider, load_settings
from voicetype.sounds import ERROR_SOUND, START_RECORD_SOUND
from voicetype.utils import type_text
from voicetype.voice.voice import Voice

HERE = Path(__file__).resolve().parent
SOUNDS_DIR = HERE / "sounds"


def get_platform_listener() -> HotkeyListener:
    """Detects the platform and display server/session type, then returns the appropriate listener."""
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
                on_hotkey_press=handle_hotkey_press,
                on_hotkey_release=handle_hotkey_release,
            )
        except Exception as e:
            logger.error(f"Failed to initialize X11 listener: {e}", exc_info=True)
            raise RuntimeError("Could not initialize any Linux hotkey listener.") from e

    elif system == "Windows":
        # TODO: Implement Windows listener
        logger.warning("Windows detected, but listener not implemented.")
        raise NotImplementedError("Windows hotkey listener not yet implemented.")
    elif system == "Darwin":  # macOS
        # TODO: Implement macOS listener
        logger.warning("macOS detected, but listener not implemented.")
    else:
        raise OSError(f"Unsupported operating system: {system}")


def handle_hotkey_press():
    """Callback function when the hotkey is pressed."""
    global is_recording
    if not is_recording:
        logger.info("Hotkey pressed - Starting recording...")
        is_recording = True
        # TODO: Start actual audio recording stream here (requires Voice class refactor)
        voice.start_recording()
        # TODO: Update tray icon state to "recording"
        # play_audio(START_RECORD_SOUND)  # Provide feedback
    else:
        logger.warning("Hotkey pressed while already recording. Ignoring.")


def handle_hotkey_release():
    """Callback function when the hotkey is released."""
    global is_recording
    if is_recording:
        logger.info("Hotkey released - Stopping recording and processing...")
        is_recording = False
        # TODO: Stop audio recording stream here (requires Voice class refactor)
        # TODO: Update tray icon state to "processing"

        try:
            # TODO: Get audio data from the stream and pass to voice.transcribe()
            recording_file = (
                voice.stop_recording()
            )  # Placeholder for actual stop recording
            text = voice.transcribe(
                recording_file
            )  # Placeholder for actual transcription

            # transcribed_text = voice.transcribe(audio_data) # Placeholder
            transcribed_text = text
            logger.info(f"Transcription result: {transcribed_text}")
            if transcribed_text:
                typing_queue.put(transcribed_text)  # Add to queue for typing
            # TODO: Update tray icon state back to "idle"
        except Exception as e:
            logger.error(f"Error during transcription or typing: {e}", exc_info=True)
            # TODO: Update tray icon state to "error"
            # play_audio(ERROR_SOUND)  # Provide error feedback
        finally:
            # Ensure recording flag is reset even if errors occur
            is_recording = False
            # TODO: Reset tray icon to idle if it wasn't already
    else:
        logger.debug("Hotkey released while not recording. Ignoring.")


def load_model_in_background():
    import speech_recognition as sr
    from speech_recognition.recognizers.whisper_local import faster_whisper

    r = sr.Recognizer()
    # pass in empty file to force load
    audio = sr.AudioData.from_file(str(SOUNDS_DIR / "empty.wav"))

    logger.info("Loading local model in background...")
    _ = faster_whisper.recognize(
        r,
        audio_data=audio,
        model="large-v3",
        language="en",
    )
    logger.info("Local model loaded.")


def main():
    """Main application entry point."""
    global hotkey_listener, voice

    parser = argparse.ArgumentParser(description="VoiceType application.")
    parser.add_argument(
        "--settings-file", type=Path, help="Path to the settings TOML file."
    )
    args = parser.parse_args()

    settings = load_settings(args.settings_file)

    # Load local model if configured
    if settings.voice.provider == VoiceSettingsProvider.LOCAL:
        # load in background
        threading.Thread(target=load_model_in_background, daemon=True).start()

    logger.info("Starting VoiceType application...")

    try:
        voice = Voice(settings=settings.voice)
        hotkey_listener = get_platform_listener()
        hotkey_listener.set_hotkey(settings.hotkey.hotkey)
        hotkey_listener.start_listening()

        logger.info(f"Intended hotkey: {settings.hotkey.hotkey}")
        logger.info("Press Ctrl+C to exit.")

        while True:
            # Keep the main thread alive.
            # If using pystray, icon.run() would block here.
            # If the listener runs in the main thread and blocks, this loop isn't needed.
            # If the listener runs in a background thread, we need to keep alive.
            try:
                transcribed_text = typing_queue.get(timeout=1)
                type_text(transcribed_text)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing typing queue: {e}", exc_info=True)
                break

    except KeyboardInterrupt:
        logger.info("Shutdown requested via KeyboardInterrupt.")
    except NotImplementedError as e:
        logger.error(f"Initialization failed: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        logger.info("Shutting down...")
        if hotkey_listener:
            try:
                hotkey_listener.stop_listening()
                logger.info("Hotkey listener stopped.")
            except Exception as e:
                logger.error(f"Error stopping listener: {e}", exc_info=True)
        logger.info("VoiceType application finished.")


if __name__ == "__main__":
    main()
