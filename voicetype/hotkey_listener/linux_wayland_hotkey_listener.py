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


# Constants for GNOME Keybinding D-Bus interface
GNOME_SETTINGS_DAEMON_SERVICE = "org.gnome.settings-daemon.plugins.media-keys"
GNOME_SETTINGS_DAEMON_OBJECT_PATH = "/org/gnome/settings_daemon/plugins/media_keys"
GNOME_SETTINGS_DAEMON_INTERFACE = "org.gnome.settings-daemon.plugins.media-keys"

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
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
    ):
        super().__init__(on_press, on_release)
        self._hotkey: Optional[str] = None
        self._bus: Optional[SessionMessageBus] = None
        self._proxy: Optional[ObjectProxy] = None
        self._loop: Optional[EventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._is_listening: bool = False
        self._de_detected: str = "unknown" # e.g., "gnome", "kde", "unity", "unknown"

        # Detect Desktop Environment (basic detection)
        # Detect Desktop Environment (more robust detection)
        self._de_detected = "unknown" # Default
        original_xdg_desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
        processed_xdg_desktop = original_xdg_desktop.lower()

        # Split by colon and check each part for known DEs
        desktop_parts = [part for part in processed_xdg_desktop.split(':') if part] # Filter out empty strings
        is_gnome = any("gnome" in part for part in desktop_parts)
        is_kde = any("kde" in part for part in desktop_parts)

        if is_gnome:
            self._de_detected = "gnome"
            logger.info(f"Detected GNOME environment ('{original_xdg_desktop}') for Wayland listener.")
        elif is_kde:
            # Keep KDE detection separate, even if GNOME is also present (unlikely but possible)
            self._de_detected = "kde"
            logger.warning(f"Detected KDE environment ('{original_xdg_desktop}'). Wayland listener currently only supports GNOME.")
        else:
            # If neither GNOME nor KDE found, store the first non-empty part (or 'unknown') for logging
            self._de_detected = desktop_parts[0] if desktop_parts else "unknown"
            logger.warning(
                f"Detected unsupported/unknown DE for Wayland: '{self._de_detected}' "
                f"(from XDG_CURRENT_DESKTOP='{original_xdg_desktop}'). Hotkeys via D-Bus may not work."
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

    def _dbus_signal_handler(self, application: str, keybinding: str):
        """Callback executed when the D-Bus signal is received."""
        logger.debug(f"D-Bus signal received: app='{application}', binding='{keybinding}'")
        # Note: GNOME's media-keys interface only signals press, not release.
        # To make it work with the press/release callback structure, we trigger
        # release immediately after press. This changes the interaction model
        # for Wayland users: they tap the hotkey once to start *and* stop/transcribe.
        if application == APP_ID and keybinding == DBUS_BINDING_NAME:
            logger.info("Hotkey activated (detected via D-Bus)")
            self._trigger_hotkey_press()
            self._trigger_hotkey_release() # Simulate release immediately

    def _run_dbus_loop(self):
        """Runs the D-Bus event loop in a dedicated thread."""
        try:
            # Create loop and connect to bus within the thread
            self._loop = EventLoop()
            self._bus = SessionMessageBus()
            logger.info("D-Bus session bus connected.")

            if self._de_detected == "gnome":
                self._proxy = self._bus.get_proxy(
                    DBusServiceIdentifier(service_name=GNOME_SETTINGS_DAEMON_SERVICE),
                    DBusObjectIdentifier(object_path=GNOME_SETTINGS_DAEMON_OBJECT_PATH)
                )

                # Subscribe to the signal emitted when a custom keybinding is pressed
                # Ensure the signal and interface names are correct
                signal_interface = GNOME_SETTINGS_DAEMON_INTERFACE
                signal_name = "MediaPlayerKeyPressed"
                signal_obj = getattr(self._proxy, signal_name) # Access signal object

                signal_obj.connect(self._dbus_signal_handler)
                logger.info(f"Connected to D-Bus signal: {signal_interface}.{signal_name}")

                # Register the hotkey with GNOME
                # Arguments: Application ID (string), Application Description (string), Keybinding Name (string), Hotkey Combo (string)
                # The description seems unused but required by some versions.
                # The keybinding name (DBUS_BINDING_NAME) is what's passed to the signal handler.
                # Use GrabCustomKeybinding method
                grab_method = getattr(self._proxy, "GrabCustomKeybinding")
                grab_method(APP_ID, "VoiceType Hotkey Action", DBUS_BINDING_NAME, self._hotkey)
                logger.info(f"Registered custom keybinding with GNOME: '{self._hotkey}' as '{DBUS_BINDING_NAME}'")

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
        if self._proxy and self._de_detected == "gnome":
            try:
                # Use the binding name provided during registration
                release_method = getattr(self._proxy, "ReleaseCustomKeybinding")
                release_method(DBUS_BINDING_NAME)
                logger.info(f"Unregistered custom keybinding '{DBUS_BINDING_NAME}' from GNOME.")
            except Exception as e:
                # Log error but continue cleanup
                logger.error(f"Error unregistering D-Bus keybinding '{DBUS_BINDING_NAME}': {e}")

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
