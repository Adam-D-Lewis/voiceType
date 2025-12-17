"""XDG Desktop Portal GlobalShortcuts implementation for Wayland.

This module provides a hotkey listener that uses the XDG Desktop Portal
GlobalShortcuts API to capture global hotkeys on Wayland without requiring
root privileges. Works on GNOME 48+, KDE Plasma, and Hyprland.
"""

import asyncio
import secrets
import subprocess
import threading
from typing import Callable, Optional

from loguru import logger

from .hotkey_listener import HotkeyListener


class PortalHotkeyListener(HotkeyListener):
    """Wayland hotkey listener using XDG Desktop Portal GlobalShortcuts.

    This implementation works on GNOME 48+, KDE Plasma, and Hyprland
    without requiring root privileges.
    """

    PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
    PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
    SHORTCUTS_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
    REQUEST_INTERFACE = "org.freedesktop.portal.Request"

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[], None]] = None,
        on_hotkey_release: Optional[Callable[[], None]] = None,
    ):
        """Initialize the portal hotkey listener.

        Args:
            on_hotkey_press: Callback function to execute when the hotkey is pressed.
            on_hotkey_release: Callback function to execute when the hotkey is released.
        """
        super().__init__(on_hotkey_press, on_hotkey_release)
        self._bus = None
        self._session_handle: Optional[str] = None
        self._shortcut_id = "voicetype-record"
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._shortcuts_iface = None
        self._preferred_trigger: str = "Pause"

    def set_hotkey(self, hotkey: str) -> None:
        """Set the preferred hotkey trigger.

        Note: On portal, the user confirms/modifies this in a system dialog.
        The format should match XDG shortcut spec (e.g., "Pause", "Control+Alt+R").

        This method converts pynput format to portal format:
        - <pause> -> Pause
        - <ctrl>+<alt>+r -> Control+Alt+R

        Args:
            hotkey: The hotkey string (pynput or portal format).
        """
        self._hotkey = hotkey
        self._preferred_trigger = self._convert_hotkey_format(hotkey)
        logger.info(
            f"Preferred hotkey set to: {hotkey} (portal format: {self._preferred_trigger})"
        )

    def _convert_hotkey_format(self, hotkey: str) -> str:
        """Convert pynput hotkey format to XDG portal format.

        Args:
            hotkey: Hotkey in pynput format (e.g., "<ctrl>+<alt>+r" or "<pause>")

        Returns:
            Hotkey in XDG portal format (e.g., "Control+Alt+R" or "Pause")
        """
        # Mapping from pynput format to portal format
        key_map = {
            "<pause>": "Pause",
            "<ctrl>": "Control",
            "<alt>": "Alt",
            "<shift>": "Shift",
            "<cmd>": "Super",
            "<super>": "Super",
            "<tab>": "Tab",
            "<space>": "space",
            "<enter>": "Return",
            "<esc>": "Escape",
            "<backspace>": "BackSpace",
            "<delete>": "Delete",
            "<insert>": "Insert",
            "<home>": "Home",
            "<end>": "End",
            "<page_up>": "Page_Up",
            "<page_down>": "Page_Down",
            "<up>": "Up",
            "<down>": "Down",
            "<left>": "Left",
            "<right>": "Right",
            "<f1>": "F1",
            "<f2>": "F2",
            "<f3>": "F3",
            "<f4>": "F4",
            "<f5>": "F5",
            "<f6>": "F6",
            "<f7>": "F7",
            "<f8>": "F8",
            "<f9>": "F9",
            "<f10>": "F10",
            "<f11>": "F11",
            "<f12>": "F12",
        }

        # If it's already in portal format (no angle brackets), return as-is
        if "<" not in hotkey:
            return hotkey

        parts = hotkey.lower().split("+")
        converted_parts = []

        for part in parts:
            part = part.strip()
            if part in key_map:
                converted_parts.append(key_map[part])
            elif part.startswith("<") and part.endswith(">"):
                # Unknown special key, try to capitalize the name
                key_name = part[1:-1].capitalize()
                converted_parts.append(key_name)
            else:
                # Regular character key, uppercase it
                converted_parts.append(part.upper())

        return "+".join(converted_parts)

    async def _setup_session(self) -> bool:
        """Create a GlobalShortcuts session and bind our shortcut."""
        try:
            from dbus_next import Variant
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType

            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

            # Get introspection for the portal
            introspection = await self._bus.introspect(
                self.PORTAL_BUS_NAME, self.PORTAL_OBJECT_PATH
            )
            proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, self.PORTAL_OBJECT_PATH, introspection
            )

            self._shortcuts_iface = proxy.get_interface(self.SHORTCUTS_INTERFACE)

            # Generate unique tokens for handle paths
            sender = self._bus.unique_name.replace(":", "").replace(".", "_")
            session_token = f"voicetype_{secrets.token_hex(8)}"

            # Step 1: Create session
            session_handle = await self._create_session(sender, session_token)
            if not session_handle:
                return False

            self._session_handle = session_handle
            logger.info(f"Session created: {session_handle}")

            # Step 2: Bind shortcuts
            success = await self._bind_shortcuts(sender)
            if not success:
                return False

            # Step 3: Subscribe to Activated/Deactivated signals
            self._shortcuts_iface.on_activated(self._on_shortcut_activated)
            self._shortcuts_iface.on_deactivated(self._on_shortcut_deactivated)

            logger.info("Portal GlobalShortcuts session ready")
            return True

        except Exception as e:
            logger.error(f"Failed to setup portal session: {e}")
            return False

    async def _create_session(self, sender: str, session_token: str) -> Optional[str]:
        """Create a GlobalShortcuts session."""
        from dbus_next import Variant

        request_token = f"req_{secrets.token_hex(8)}"
        expected_request_path = (
            f"/org/freedesktop/portal/desktop/request/{sender}/{request_token}"
        )

        # Set up response handler BEFORE making the call (avoid race condition)
        response_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_response(response_code, results):
            if response_future.done():
                return
            if response_code == 0:  # Success
                session_handle = results.get("session_handle")
                if session_handle:
                    # Handle both Variant and raw value
                    handle_value = (
                        session_handle.value
                        if hasattr(session_handle, "value")
                        else session_handle
                    )
                    response_future.set_result(handle_value)
                else:
                    response_future.set_exception(
                        Exception("No session_handle in response")
                    )
            elif response_code == 1:
                response_future.set_exception(
                    Exception("User cancelled session creation")
                )
            else:
                response_future.set_exception(
                    Exception(f"Session creation failed: {response_code}")
                )

        # Subscribe to the Response signal on the expected request path
        try:
            request_introspection = await self._bus.introspect(
                self.PORTAL_BUS_NAME, expected_request_path
            )
            request_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, expected_request_path, request_introspection
            )
            request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
            request_iface.on_response(on_response)
        except Exception as e:
            logger.debug(
                f"Could not subscribe to request path before call: {e}. "
                "Will try inline response handling."
            )

        # Now make the CreateSession call
        options = {
            "handle_token": Variant("s", request_token),
            "session_handle_token": Variant("s", session_token),
        }

        request_handle = await self._shortcuts_iface.call_create_session(options)
        logger.debug(f"CreateSession request: {request_handle}")

        # If we couldn't subscribe to request path, try subscribing now
        if not response_future.done():
            try:
                request_introspection = await self._bus.introspect(
                    self.PORTAL_BUS_NAME, request_handle
                )
                request_proxy = self._bus.get_proxy_object(
                    self.PORTAL_BUS_NAME, request_handle, request_introspection
                )
                request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
                request_iface.on_response(on_response)
            except Exception as e:
                logger.debug(f"Could not subscribe to actual request handle: {e}")

        # Wait for the response
        try:
            session_handle = await asyncio.wait_for(response_future, timeout=30.0)
            return session_handle
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for CreateSession response")
            return None
        except Exception as e:
            logger.error(f"CreateSession failed: {e}")
            return None

    async def _bind_shortcuts(self, sender: str) -> bool:
        """Bind our recording shortcut to the session."""
        from dbus_next import Variant

        request_token = f"bind_{secrets.token_hex(8)}"
        expected_request_path = (
            f"/org/freedesktop/portal/desktop/request/{sender}/{request_token}"
        )

        response_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_response(response_code, results):
            if response_future.done():
                return
            if response_code == 0:
                shortcuts = results.get("shortcuts", [])
                logger.info(f"Shortcuts bound: {shortcuts}")
                response_future.set_result(True)
            elif response_code == 1:
                logger.warning("User cancelled shortcut binding")
                response_future.set_result(False)
            else:
                response_future.set_exception(
                    Exception(f"BindShortcuts failed: {response_code}")
                )

        # Subscribe to Response signal
        try:
            request_introspection = await self._bus.introspect(
                self.PORTAL_BUS_NAME, expected_request_path
            )
            request_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, expected_request_path, request_introspection
            )
            request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
            request_iface.on_response(on_response)
        except Exception as e:
            logger.debug(f"Could not subscribe to request path before call: {e}")

        # Define our shortcut
        shortcuts = [
            (
                self._shortcut_id,
                {
                    "description": Variant("s", "Start/stop voice recording"),
                    "preferred_trigger": Variant("s", self._preferred_trigger),
                },
            )
        ]

        options = {
            "handle_token": Variant("s", request_token),
        }

        # parent_window can be empty for CLI/background apps
        parent_window = ""

        request_handle = await self._shortcuts_iface.call_bind_shortcuts(
            self._session_handle, shortcuts, parent_window, options
        )
        logger.debug(f"BindShortcuts request: {request_handle}")

        # If we couldn't subscribe to request path, try subscribing now
        if not response_future.done():
            try:
                request_introspection = await self._bus.introspect(
                    self.PORTAL_BUS_NAME, request_handle
                )
                request_proxy = self._bus.get_proxy_object(
                    self.PORTAL_BUS_NAME, request_handle, request_introspection
                )
                request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
                request_iface.on_response(on_response)
            except Exception as e:
                logger.debug(f"Could not subscribe to actual request handle: {e}")

        try:
            success = await asyncio.wait_for(
                response_future, timeout=60.0
            )  # User interaction
            return success
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for BindShortcuts response")
            return False
        except Exception as e:
            logger.error(f"BindShortcuts failed: {e}")
            return False

    def _on_shortcut_activated(
        self, session_handle: str, shortcut_id: str, timestamp: int, options: dict
    ):
        """Called when the shortcut is pressed."""
        if shortcut_id == self._shortcut_id:
            logger.debug(f"Shortcut activated: {shortcut_id} at {timestamp}")
            if self.on_hotkey_press:
                self.on_hotkey_press()

    def _on_shortcut_deactivated(
        self, session_handle: str, shortcut_id: str, timestamp: int, options: dict
    ):
        """Called when the shortcut is released."""
        if shortcut_id == self._shortcut_id:
            logger.debug(f"Shortcut deactivated: {shortcut_id} at {timestamp}")
            if self.on_hotkey_release:
                self.on_hotkey_release()

    def start_listening(self) -> None:
        """Start the portal hotkey listener.

        This runs the asyncio event loop in a background thread.

        Raises:
            RuntimeError: If the GlobalShortcuts session fails to initialize.
        """
        if self._running:
            logger.info("Portal listener already running")
            return

        setup_complete = threading.Event()
        setup_error: list = []

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            try:
                success = self._loop.run_until_complete(self._setup_session())
                if success:
                    self._running = True
                    setup_complete.set()
                    logger.info("Portal hotkey listener started")
                    self._loop.run_forever()
                else:
                    setup_error.append(
                        RuntimeError("Failed to setup GlobalShortcuts session")
                    )
                    setup_complete.set()
            except Exception as e:
                setup_error.append(e)
                setup_complete.set()
            finally:
                if self._loop and self._loop.is_running():
                    self._loop.stop()

        self._thread = threading.Thread(
            target=run_loop, daemon=True, name="portal-dbus"
        )
        self._thread.start()

        # Wait for setup to complete
        setup_complete.wait(timeout=65.0)  # Allow time for user interaction

        if setup_error:
            self._running = False
            raise setup_error[0]

        if not self._running:
            raise RuntimeError("Portal listener failed to start")

    def stop_listening(self) -> None:
        """Stop the portal hotkey listener and clean up resources."""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping portal hotkey listener...")

        if self._loop:
            # Schedule loop stop from the loop's thread
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("Portal listener thread did not stop gracefully")

        # Clean up bus connection
        if self._bus:
            try:
                self._bus.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting bus: {e}")
            self._bus = None

        self._loop = None
        self._thread = None
        self._session_handle = None
        self._shortcuts_iface = None
        logger.info("Portal hotkey listener stopped")


def is_portal_available() -> bool:
    """Check if the GlobalShortcuts portal is available.

    Returns:
        True if the GlobalShortcuts portal interface is available, False otherwise.
    """
    # Primary method: Use dbus-send to introspect and check for GlobalShortcuts interface
    try:
        result = subprocess.run(
            [
                "dbus-send",
                "--session",
                "--print-reply",
                "--dest=org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.DBus.Introspectable.Introspect",
            ],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0 and b"GlobalShortcuts" in result.stdout:
            return True
    except FileNotFoundError:
        pass  # dbus-send not available, try busctl
    except Exception:
        pass

    # Fallback method: Use busctl and check for actual methods in output
    try:
        result = subprocess.run(
            [
                "busctl",
                "--user",
                "introspect",
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.GlobalShortcuts",
            ],
            capture_output=True,
            timeout=5,
            text=True,
        )
        # busctl returns 0 even if interface doesn't exist, but output will be empty
        # Check if we got actual method definitions (e.g., "CreateSession")
        if result.returncode == 0 and "CreateSession" in result.stdout:
            return True
    except Exception:
        pass

    return False
