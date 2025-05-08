import abc
import os
import threading
from typing import Callable, Optional

from dasbus.connection import SessionMessageBus
from dasbus.loop import EventLoop
from dasbus.identifier import DBusServiceIdentifier, DBusObjectIdentifier
from dasbus.client.proxy import ObjectProxy

from loguru import logger

# Assuming HotkeyListener is in the same directory or correctly importable
# If HotkeyListener is in ..hotkey_listener.py, adjust the import
try:
    from .hotkey_listener import HotkeyListener
except ImportError:
    # Fallback if running the script directly for testing might need adjustment
    from hotkey_listener import HotkeyListener


# Constants for GNOME Shell Keybinding D-Bus interface
GNOME_SHELL_SERVICE = "org.gnome.Shell"
GNOME_SHELL_OBJECT_PATH = "/org/gnome/Shell"
GNOME_SHELL_INTERFACE = "org.gnome.Shell"

# Constants for KDE Keybinding D-Bus interface (Placeholder)
# KDE_GLOBALACCEL_SERVICE = "org.kde.kglobalaccel"
# KDE_GLOBALACCEL_OBJECT_PATH = "/kglobalaccel"
# KDE_GLOBALACCEL_INTERFACE = "org.kde.kglobalaccel"

# Application ID for D-Bus registration - Consider making this configurable or more unique
APP_ID = "io.github.user.voicetype" # Replace with your actual app ID if you have one
APP_OBJECT_PATH = f"/{APP_ID.replace('.', '/')}/HotkeyListener"
# Binding name used internally with D-Bus
DBUS_BINDING_NAME = "voicetype-hotkey"


class LinuxWaylandHotkeyListener(HotkeyListener):
    """
    Hotkey listener implementation for Linux Wayland using D-Bus.

    This implementation primarily targets GNOME's media-keys plugin.
    It relies on the Desktop Environment to capture the key combination
    and notify this application via D-Bus signals.

    NOTE: Due to limitations in many DE D-Bus interfaces (like GNOME's media-keys),
          this listener reliably detects hotkey *presses* but not *releases*.
          To work with the press/release abstraction, it triggers the `on_release`
          callback immediately after the `on_press` callback upon receiving the
          D-Bus signal. This means the user interaction model under Wayland/GNOME
          is a single *tap* of the hotkey to trigger the full record-transcribe cycle.

    Requires `dasbus` library: pip install dasbus
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[], None]] = None,
        on_hotkey_release: Optional[Callable[[], None]] = None,
    ):
        super().__init__(on_hotkey_press, on_hotkey_release)
        self._hotkey: Optional[str] = None
        self._bus: Optional[SessionMessageBus] = None
        self._proxy: Optional[ObjectProxy] = None
        self._loop: Optional[EventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._is_listening: bool = False
        self._de_detected: str = "unknown" # e.g., "gnome", "kde", "unity", "unknown"
        self._action_id: Optional[int] = None # Store the action ID from GrabAccelerator

        # Detect Desktop Environment (basic detection)
        # Detect Desktop Environment (even more robust detection)
        self._de_detected = "unknown" # Default
        xdg_current = os.environ.get("XDG_CURRENT_DESKTOP", "")
        original_xdg_current = os.environ.get("ORIGINAL_XDG_CURRENT_DESKTOP", "")
        gnome_session_mode = os.environ.get("GNOME_SHELL_SESSION_MODE", "")

        # Combine relevant variables for easier checking
        combined_desktop_info = f"{xdg_current}:{original_xdg_current}:{gnome_session_mode}".lower()
        desktop_parts = [part for part in combined_desktop_info.split(':') if part]

        is_gnome = any("gnome" in part for part in desktop_parts)
        # Check KDE only if not GNOME, as GNOME takes precedence for our implementation
        is_kde = False
        if not is_gnome:
            # Check only XDG_CURRENT_DESKTOP for KDE for now
            is_kde = any("kde" in part for part in xdg_current.lower().split(':') if part)

        log_xdg_current = xdg_current if xdg_current else "Not set"
        log_original_xdg = original_xdg_current if original_xdg_current else "Not set"
        log_gnome_mode = gnome_session_mode if gnome_session_mode else "Not set"

        if is_gnome:
            self._de_detected = "gnome"
            logger.info(
                f"Detected GNOME environment for Wayland listener "
                f"(XDG_CURRENT_DESKTOP='{log_xdg_current}', "
                f"ORIGINAL_XDG_CURRENT_DESKTOP='{log_original_xdg}', "
                f"GNOME_SHELL_SESSION_MODE='{log_gnome_mode}')"
            )
        elif is_kde:
            self._de_detected = "kde"
            logger.warning(
                f"Detected KDE environment (XDG_CURRENT_DESKTOP='{log_xdg_current}'). "
                "Wayland listener currently only supports GNOME."
            )
        else:
            # Fallback: Use the primary XDG_CURRENT_DESKTOP value for logging if available
            self._de_detected = xdg_current.lower().split(':')[0] if xdg_current else "unknown"
            logger.warning(
                f"Detected unsupported/unknown DE for Wayland: '{self._de_detected}' "
                f"(XDG_CURRENT_DESKTOP='{log_xdg_current}', "
                f"ORIGINAL_XDG_CURRENT_DESKTOP='{log_original_xdg}', "
                f"GNOME_SHELL_SESSION_MODE='{log_gnome_mode}'). "
                "Hotkeys via D-Bus may not work."
            )


    def set_hotkey(self, hotkey: str) -> None:
        """
        Sets the hotkey combination to listen for.

        Args:
            hotkey: A string representation of the hotkey (e.g., "<Control><Alt>X").
                    Format should match the target DE's expectation (e.g., GNOME's format).
        """
        # Basic validation/normalization could be added here
        # Ensure format is suitable for GNOME D-Bus (e.g., "<Control><Alt>p")
        if not (hotkey.startswith("<") and hotkey.endswith(">")):
             logger.warning(f"Hotkey '{hotkey}' might not be in the expected D-Bus format (e.g., '<Control><Alt>X').")
        self._hotkey = hotkey
        logger.info(f"Wayland hotkey set to: {self._hotkey}")

    def _dbus_signal_handler(self, action_id: int, parameters: dict):
        """Callback executed when the AcceleratorActivated D-Bus signal is received."""
        logger.debug(f"D-Bus AcceleratorActivated signal received: action_id={action_id}, params={parameters}")
        # Check if the received action_id matches the one we registered
        if self._action_id is not None and action_id == self._action_id:
            logger.info("Hotkey activated (detected via D-Bus AcceleratorActivated)")
            # Simulate press and immediate release as before
            self._trigger_hotkey_press()
            self._trigger_hotkey_release()
        else:
            logger.debug(f"Ignoring signal for unknown or mismatched action_id: {action_id} (expected {self._action_id})")


    def _run_dbus_loop(self):
        """Runs the D-Bus event loop in a dedicated thread."""
        try:
            # Create loop and connect to bus within the thread
            self._loop = EventLoop()
            self._bus = SessionMessageBus()
            logger.info("D-Bus session bus connected.")

            if self._de_detected == "gnome":
                # Pass the service name and object path strings directly to get_proxy
                self._proxy = self._bus.get_proxy(
                    GNOME_SHELL_SERVICE,
                    GNOME_SHELL_OBJECT_PATH
                )

                # Subscribe to the AcceleratorActivated signal
                signal_interface = GNOME_SHELL_INTERFACE
                signal_name = "AcceleratorActivated"
                signal_obj = getattr(self._proxy, signal_name) # Access signal object

                signal_obj.connect(self._dbus_signal_handler)
                logger.info(f"Connected to D-Bus signal: {signal_interface}.{signal_name}")

                # Register the hotkey with GNOME Shell using GrabAccelerator
                # Arguments: Description (string), Accelerator (string), Flags (uint), ModeFlags (uint)
                # Flags and ModeFlags might need adjustment based on desired behavior (e.g., ShellBuiltin = 1 << 0)
                # Using 0 for both flags seems common for basic application shortcuts.
                grab_method = getattr(self._proxy, "GrabAccelerator")  # TODO: FIX I think this is a permissions issue currently.
                # GrabAccelerator returns the action_id (uint32)
                self._action_id = grab_method(self._hotkey, 0, 0) # Flags=0, ModeFlags=0
                if self._action_id is None or self._action_id == 0:
                     logger.error(f"Failed to grab accelerator '{self._hotkey}'. GrabAccelerator returned {self._action_id}.")
                     # Handle error - maybe raise exception or disconnect?
                     raise RuntimeError(f"Failed to register hotkey '{self._hotkey}' with GNOME Shell.")
                else:
                    logger.info(f"Registered accelerator with GNOME Shell: '{self._hotkey}' -> action_id={self._action_id}")

            elif self._de_detected == "kde":
                # Placeholder for KDE implementation
                logger.error("KDE D-Bus hotkey registration not yet implemented.")
                # Need to implement interaction with org.kde.kglobalaccel
                return # Stop if KDE detected but not implemented

            else:
                logger.error(f"Cannot register hotkey: Unsupported DE '{self._de_detected}'")
                return # Stop if DE not supported

            logger.info("D-Bus listener setup complete. Starting event loop...")
            self._is_listening = True
            self._loop.run() # Blocks here until loop.quit() is called

        except ImportError:
            logger.error("Failed to import 'dasbus'. Please install it: pip install dasbus", exc_info=True)
        except Exception as e:
            logger.error(f"Error during D-Bus setup or loop: {e}", exc_info=True)
            # Attempt cleanup if possible
            if self._bus:
                try:
                    self._bus.disconnect()
                except Exception as disconnect_err:
                    logger.error(f"Error disconnecting D-Bus: {disconnect_err}")
        finally:
            logger.info("D-Bus event loop stopped.")
            self._is_listening = False # Ensure flag is reset
            # Reset D-Bus related objects
            self._proxy = None
            self._bus = None
            self._loop = None


    def start_listening(self) -> None:
        """Starts the hotkey listener by setting up D-Bus communication in a background thread."""
        if self._is_listening or (self._loop_thread is not None and self._loop_thread.is_alive()):
            logger.warning("Listener already running or starting.")
            return

        if self._hotkey is None:
            raise ValueError("Hotkey not set before starting listener.")

        if self._de_detected != "gnome":
             # If not GNOME, we don't proceed with D-Bus setup for now.
             # The fallback mechanism in __main__.py should handle this.
             logger.error(f"Cannot start Wayland listener: Only GNOME D-Bus is implemented (Detected: {self._de_detected}).")
             raise NotImplementedError(f"Wayland support only implemented for GNOME (Detected: {self._de_detected}).")

        logger.info("Starting Wayland D-Bus hotkey listener thread...")
        # D-Bus operations need their own event loop, run in a separate thread
        self._is_listening = True # Set flag early to prevent race conditions
        self._loop_thread = threading.Thread(target=self._run_dbus_loop, name="DBusLoopThread", daemon=True)
        self._loop_thread.start()

    def stop_listening(self) -> None:
        """Stops the hotkey listener and cleans up D-Bus resources."""
        if not self._is_listening and (self._loop_thread is None or not self._loop_thread.is_alive()):
            logger.warning("Listener not running or already stopped.")
            return

        logger.info("Stopping Wayland D-Bus hotkey listener...")
        self._is_listening = False # Signal intention to stop

        # Unregister the hotkey from D-Bus first
        if self._proxy and self._de_detected == "gnome" and self._action_id is not None:
            try:
                # Use the action_id obtained during registration
                ungrab_method = getattr(self._proxy, "UngrabAccelerator")
                ungrab_method(self._action_id)
                logger.info(f"Unregistered accelerator action_id={self._action_id} ('{self._hotkey}') from GNOME Shell.")
                self._action_id = None # Clear the stored ID
            except Exception as e:
                # Log error but continue cleanup
                logger.error(f"Error unregistering D-Bus accelerator action_id={self._action_id}: {e}")

        # Disconnect signal handler *before* quitting loop if possible
        # This might require storing the signal connection object if dasbus provides one,
        # or handling potential errors if the proxy/bus is already gone.
        # Simple approach: just try to quit the loop.
        # More robust: Ensure signal disconnect happens if proxy exists.
        # Currently, dasbus might handle disconnects implicitly on proxy cleanup or bus disconnect.

        # Stop the D-Bus event loop from the outside
        if self._loop:
            try:
                self._loop.quit()
                logger.debug("Requested D-Bus event loop quit.")
            except Exception as e:
                logger.error(f"Error requesting D-Bus loop quit: {e}")

        # Wait for the thread to finish
        if self._loop_thread and self._loop_thread.is_alive():
            logger.debug("Waiting for D-Bus listener thread to join...")
            self._loop_thread.join(timeout=3.0) # Add a longer timeout
            if self._loop_thread.is_alive():
                logger.warning("D-Bus listener thread did not exit cleanly after timeout.")

        self._loop_thread = None
        # Ensure D-Bus objects are cleared after thread stops
        self._proxy = None
        self._bus = None
        self._loop = None
        logger.info("Wayland D-Bus hotkey listener stopped.")

    def __del__(self):
        # Ensure cleanup happens if the object is garbage collected,
        # though explicit stop_listening() is strongly preferred.
        if self._is_listening or (self._loop_thread is not None and self._loop_thread.is_alive()):
            logger.warning("HotkeyListener object deleted without explicit stop. Attempting cleanup...")
            self.stop_listening()
