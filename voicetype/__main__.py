import queue
import time
import logging
import platform
from voicetype.hotkey_listener.hotkey_listener import HotkeyListener
from voicetype.voice.voice import Voice
from voicetype.utils import play_audio, type_text
from voicetype.sounds import START_RECORD_SOUND, ERROR_SOUND

from voicetype.globals import listener, voice, is_recording, typing_queue

# Basic Logging Setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# TODO: Add configuration loading here (hotkey, model, etc.)
HOTKEY = "<pause>"


def get_platform_listener() -> HotkeyListener:
    """Detects the platform and returns the appropriate listener."""
    system = platform.system()
    if system == "Linux":
        # TODO: Add Wayland detection and listener
        logging.info("Detected Linux X11 (assuming for now).")
        # Need to ask user to add this file if we want to use it
        from voicetype.hotkey_listener.linux_x11_hotkey_listener import (
            LinuxX11HotkeyListener,
        )

        return LinuxX11HotkeyListener(
            on_press=handle_hotkey_press,
            on_release=handle_hotkey_release,
        )
    elif system == "Windows":
        # TODO: Implement Windows listener
        raise NotImplementedError("Windows hotkey listener not yet implemented.")
    elif system == "Darwin":  # macOS
        # TODO: Implement macOS listener
        raise NotImplementedError("macOS hotkey listener not yet implemented.")
    else:
        raise OSError(f"Unsupported operating system: {system}")


def handle_hotkey_press():
    """Callback function when the hotkey is pressed."""
    global is_recording
    if not is_recording:
        logging.info("Hotkey pressed - Starting recording...")
        is_recording = True
        # TODO: Start actual audio recording stream here (requires Voice class refactor)
        # TODO: Update tray icon state to "recording"
        play_audio(START_RECORD_SOUND)  # Provide feedback
    else:
        logging.warning("Hotkey pressed while already recording. Ignoring.")


def handle_hotkey_release():
    """Callback function when the hotkey is released."""
    global is_recording
    if is_recording:
        logging.info("Hotkey released - Stopping recording and processing...")
        is_recording = False
        # TODO: Stop audio recording stream here (requires Voice class refactor)
        # TODO: Update tray icon state to "processing"

        try:
            # TODO: Get audio data from the stream and pass to voice.transcribe()
            # transcribed_text = voice.transcribe(audio_data) # Placeholder
            transcribed_text = (
                "This is a placeholder transcription."  # Simulate transcription
            )
            logging.info(f"Transcription result: {transcribed_text}")
            if transcribed_text:
                typing_queue.put(transcribed_text)  # Add to queue for typing
            # TODO: Update tray icon state back to "idle"
        except Exception as e:
            logging.error(f"Error during transcription or typing: {e}", exc_info=True)
            # TODO: Update tray icon state to "error"
            play_audio(ERROR_SOUND)  # Provide error feedback
        finally:
            # Ensure recording flag is reset even if errors occur
            is_recording = False
            # TODO: Reset tray icon to idle if it wasn't already
    else:
        logging.debug("Hotkey released while not recording. Ignoring.")


def main():
    """Main application entry point."""
    global listener, voice
    logging.info("Starting VoiceType application...")

    try:
        voice = Voice()  # Initialize audio processing class
        listener = get_platform_listener()  # Get the platform-specific listener
        listener.set_hotkey(HOTKEY)  # Configure the hotkey
        listener.start_listening()  # Start listening in a background thread

        # --- Placeholder for listener until files are added ---
        logging.warning("Hotkey listener functionality is currently disabled.")
        logging.warning(
            "Please add the required platform listener file (e.g., linux_x11_hotkey_listener.py) to the chat."
        )
        logging.info(f"Intended hotkey: {HOTKEY}")
        logging.info("Press Ctrl+C to exit.")
        # --- End Placeholder ---

        # Keep the main thread alive.
        # If using pystray, icon.run() would block here.
        # If the listener runs in the main thread and blocks, this loop isn't needed.
        # If the listener runs in a background thread, we need to keep alive.
        while True:
            try:
                transribed_text = typing_queue.get(timeout=1)
                type_text(transribed_text)
            except queue.Empty:
                # No items in the queue, continue to check for hotkey events
                continue
            except Exception as e:
                logging.error(f"Error processing typing queue: {e}", exc_info=True)
                # Handle any other exceptions that might occur
                break

    except KeyboardInterrupt:
        logging.info("Shutdown requested via KeyboardInterrupt.")
    except NotImplementedError as e:
        logging.error(f"Initialization failed: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        logging.info("Shutting down...")
        if listener:
            try:
                listener.stop_listening()
                logging.info("Hotkey listener stopped.")
            except Exception as e:
                logging.error(f"Error stopping listener: {e}", exc_info=True)
        # Add any other cleanup needed here
        logging.info("VoiceType application finished.")


if __name__ == "__main__":
    main()
