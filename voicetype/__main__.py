import logging
import os
import platform
import queue
import time

from voicetype.globals import hotkey_listener, is_recording, typing_queue, voice
from voicetype.hotkey_listener.hotkey_listener import HotkeyListener
from voicetype.settings import settings
from voicetype.sounds import ERROR_SOUND, START_RECORD_SOUND
from voicetype.utils import type_text  # play_audio,
from voicetype.voice.voice import Voice

# Basic Logging Setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def get_platform_listener() -> HotkeyListener:
    """Detects the platform and display server/session type, then returns the appropriate listener."""
    system = platform.system()
    if system == "Linux":
        session_type = os.environ.get("XDG_SESSION_TYPE", "unknown").lower()
        logging.info(f"Detected Linux with session type: {session_type}")

        if session_type == "wayland":
            logging.info("Attempting to use Wayland (D-Bus) listener.")
            try:
                from voicetype.hotkey_listener.linux_wayland_hotkey_listener import (
                    LinuxWaylandHotkeyListener,
                )

                wayland_listener = LinuxWaylandHotkeyListener(
                    on_hotkey_press=handle_hotkey_press,
                    on_hotkey_release=handle_hotkey_release,
                )
                # Check if the detected DE is actually supported by the Wayland listener
                # Accessing protected member _de_detected is acceptable here for this check.
                if wayland_listener._de_detected == "gnome":
                    logging.info(
                        "GNOME detected, proceeding with Wayland D-Bus listener."
                    )
                    # Note: Wayland listener simulates release immediately after press.
                    return wayland_listener
                else:
                    logging.warning(
                        f"Wayland session detected, but DE '{wayland_listener._de_detected}' "
                        "is not supported by the D-Bus listener. Falling back to X11/pynput listener."
                    )
                    # Explicitly fall through to the X11 listener code below
            except ImportError as e:
                logging.error(f"Failed to import Wayland listener: {e}")
                raise
            except Exception as e:
                logging.warning(
                    f"Failed to initialize Wayland listener ({e}), falling back to X11 listener."
                )
                # Fall through to X11/pynput listener as a fallback if Wayland init fails for other reasons

        # Default to X11/pynput listener if session is not Wayland or Wayland init failed
        logging.info("Using X11 (pynput) listener.")
        try:
            from voicetype.hotkey_listener.linux_x11_hotkey_listener import (
                LinuxX11HotkeyListener,
            )

            return LinuxX11HotkeyListener(
                on_hotkey_press=handle_hotkey_press,
                on_hotkey_release=handle_hotkey_release,
            )
        except ImportError:
            logging.error("Failed to import X11 listener. Is 'pynput' installed?")
            raise
        except Exception as e:
            logging.error(f"Failed to initialize X11 listener: {e}", exc_info=True)
            raise RuntimeError("Could not initialize any Linux hotkey listener.") from e

    elif system == "Windows":
        # TODO: Implement Windows listener
        logging.warning("Windows detected, but listener not implemented.")
        raise NotImplementedError("Windows hotkey listener not yet implemented.")
    elif system == "Darwin":  # macOS
        # TODO: Implement macOS listener
        logging.warning("macOS detected, but listener not implemented.")
    else:
        raise OSError(f"Unsupported operating system: {system}")


def handle_hotkey_press():
    """Callback function when the hotkey is pressed."""
    global is_recording
    if not is_recording:
        logging.info("Hotkey pressed - Starting recording...")
        is_recording = True
        # TODO: Start actual audio recording stream here (requires Voice class refactor)
        voice.start_recording()
        # TODO: Update tray icon state to "recording"
        # play_audio(START_RECORD_SOUND)  # Provide feedback
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
            recording_file = (
                voice.stop_recording()
            )  # Placeholder for actual stop recording
            text = voice.transcribe(
                recording_file
            )  # Placeholder for actual transcription

            # transcribed_text = voice.transcribe(audio_data) # Placeholder
            transcribed_text = text
            logging.info(f"Transcription result: {transcribed_text}")
            if transcribed_text:
                typing_queue.put(transcribed_text)  # Add to queue for typing
            # TODO: Update tray icon state back to "idle"
        except Exception as e:
            logging.error(f"Error during transcription or typing: {e}", exc_info=True)
            # TODO: Update tray icon state to "error"
            # play_audio(ERROR_SOUND)  # Provide error feedback
        finally:
            # Ensure recording flag is reset even if errors occur
            is_recording = False
            # TODO: Reset tray icon to idle if it wasn't already
    else:
        logging.debug("Hotkey released while not recording. Ignoring.")


def main():
    """Main application entry point."""
    global hotkey_listener, voice
    logging.info("Starting VoiceType application...")

    try:
        voice = Voice(settings=settings.voice)  # Initialize audio processing class
        hotkey_listener = get_platform_listener()  # Get the platform-specific listener
        hotkey_listener.set_hotkey(settings.hotkey.hotkey)  # Configure the hotkey
        hotkey_listener.start_listening()  # Start listening in a background thread

        logging.info(f"Intended hotkey: {settings.hotkey.hotkey}")
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
        if hotkey_listener:
            try:
                hotkey_listener.stop_listening()
                logging.info("Hotkey listener stopped.")
            except Exception as e:
                logging.error(f"Error stopping listener: {e}", exc_info=True)
        # Add any other cleanup needed here
        logging.info("VoiceType application finished.")


if __name__ == "__main__":
    main()
