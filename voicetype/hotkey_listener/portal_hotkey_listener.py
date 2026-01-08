"""XDG Desktop Portal GlobalShortcuts implementation for Wayland.

This module provides a hotkey listener that uses the XDG Desktop Portal
GlobalShortcuts API to capture global hotkeys on Wayland without requiring
root privileges. Works on GNOME 48+, KDE Plasma, and Hyprland.

Spec: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html

Note: GNOME's portal is currently version 1, which lacks ConfigureShortcuts
for rebinding. Track progress: https://gitlab.gnome.org/GNOME/xdg-desktop-portal-gnome/-/issues/197
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
        log_key_repeat_debug: bool = False,
    ):
        """Initialize the portal hotkey listener.

        Args:
            on_hotkey_press: Callback function to execute when the hotkey is pressed.
            on_hotkey_release: Callback function to execute when the hotkey is released.
            log_key_repeat_debug: Whether to log key repeat debug messages.
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
        self._log_key_repeat_debug = log_key_repeat_debug
        self._logged_debug_hint = (
            False  # Track if we've shown the hint about debug logging
        )
        # Track key state to handle key repeat
        # Portal sends Activated/Deactivated pairs for each key repeat event.
        # The pattern is:
        #   - Initial press: Activated
        #   - After ~100ms: Deactivated (system's internal timing)
        #   - After ~500ms from initial: Activated (key repeat starts)
        #   - Then Deactivated/Activated pairs every ~30ms
        #
        # Our approach: Track "logical" key state separately from portal events.
        # Only trigger release callback when we're confident it's a real release,
        # not a key repeat artifact.
        self._key_is_pressed = False  # Logical state: is the physical key held?
        self._press_callback_fired = False  # Have we called on_hotkey_press?
        self._pending_release_task: Optional[asyncio.TimerHandle] = None
        self._last_deactivated_time: float = 0.0
        # Debounce threshold in seconds - if no Activated signal arrives within
        # this time after a Deactivated, we consider it a real release.
        # Must be longer than the keyboard's initial repeat delay (~500ms typical)
        self._debounce_threshold_sec = 0.6

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
            from dbus_next import introspection as intr
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType

            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

            # Manually define the GlobalShortcuts interface to avoid introspection issues
            # with other interfaces on the same object path (e.g., power-saver-enabled property)
            shortcuts_introspection = intr.Node.parse(
                """
            <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
             "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
            <node>
              <interface name="org.freedesktop.portal.GlobalShortcuts">
                <method name="CreateSession">
                  <arg type="a{sv}" name="options" direction="in"/>
                  <arg type="o" name="handle" direction="out"/>
                </method>
                <method name="BindShortcuts">
                  <arg type="o" name="session_handle" direction="in"/>
                  <arg type="a(sa{sv})" name="shortcuts" direction="in"/>
                  <arg type="s" name="parent_window" direction="in"/>
                  <arg type="a{sv}" name="options" direction="in"/>
                  <arg type="o" name="handle" direction="out"/>
                </method>
                <method name="ListShortcuts">
                  <arg type="o" name="session_handle" direction="in"/>
                  <arg type="a{sv}" name="options" direction="in"/>
                  <arg type="o" name="handle" direction="out"/>
                </method>
                <method name="ConfigureShortcuts">
                  <arg type="o" name="session_handle" direction="in"/>
                  <arg type="s" name="parent_window" direction="in"/>
                  <arg type="a{sv}" name="options" direction="in"/>
                  <arg type="o" name="handle" direction="out"/>
                </method>
                <signal name="Activated">
                  <arg type="o" name="session_handle"/>
                  <arg type="s" name="shortcut_id"/>
                  <arg type="t" name="timestamp"/>
                  <arg type="a{sv}" name="options"/>
                </signal>
                <signal name="Deactivated">
                  <arg type="o" name="session_handle"/>
                  <arg type="s" name="shortcut_id"/>
                  <arg type="t" name="timestamp"/>
                  <arg type="a{sv}" name="options"/>
                </signal>
              </interface>
            </node>
            """
            )

            proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, self.PORTAL_OBJECT_PATH, shortcuts_introspection
            )

            self._shortcuts_iface = proxy.get_interface(self.SHORTCUTS_INTERFACE)

            # Generate unique tokens for handle paths
            sender = self._bus.unique_name.replace(":", "").replace(".", "_")
            session_token = f"voicetype_session"

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
            logger.debug("Subscribing to Activated signal...")
            self._shortcuts_iface.on_activated(self._on_shortcut_activated)
            logger.debug("Subscribing to Deactivated signal...")
            self._shortcuts_iface.on_deactivated(self._on_shortcut_deactivated)

            logger.info(
                "Portal GlobalShortcuts session ready and listening for signals"
            )
            logger.info(f"Monitoring session: {self._session_handle}")
            logger.info(f"Shortcut ID: {self._shortcut_id}")

            # Store the actual bound trigger for user display
            if hasattr(self, "_actual_bound_trigger"):
                logger.info(
                    f"IMPORTANT: Use the shortcut shown in the system dialog, NOT '{self._preferred_trigger}'"
                )

            return True

        except Exception as e:
            logger.error(f"Failed to setup portal session: {e}")
            return False

    async def _create_session(self, sender: str, session_token: str) -> Optional[str]:
        """Create a GlobalShortcuts session."""
        from dbus_next import Variant
        from dbus_next import introspection as intr

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
        # Use manual introspection to avoid issues with other properties
        request_introspection_xml = intr.Node.parse(
            """
        <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
         "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
        <node>
          <interface name="org.freedesktop.portal.Request">
            <signal name="Response">
              <arg type="u" name="response"/>
              <arg type="a{sv}" name="results"/>
            </signal>
          </interface>
        </node>
        """
        )

        try:
            request_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, expected_request_path, request_introspection_xml
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
                request_proxy = self._bus.get_proxy_object(
                    self.PORTAL_BUS_NAME, request_handle, request_introspection_xml
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
        from dbus_next import introspection as intr

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
                logger.info(f"Shortcuts bound successfully: {shortcuts}")
                # Extract and log the actual trigger that was bound
                try:
                    if shortcuts and hasattr(shortcuts, "value"):
                        shortcuts_list = shortcuts.value
                    else:
                        shortcuts_list = shortcuts

                    if shortcuts_list:
                        for shortcut in shortcuts_list:
                            shortcut_id = shortcut[0]
                            shortcut_props = shortcut[1]
                            trigger = shortcut_props.get("trigger_description")
                            if trigger:
                                trigger_value = (
                                    trigger.value
                                    if hasattr(trigger, "value")
                                    else trigger
                                )
                                self._actual_bound_trigger = trigger_value
                                logger.warning(
                                    f"Portal bound shortcut '{shortcut_id}' to trigger: {trigger_value}"
                                )
                                if (
                                    self._preferred_trigger.lower()
                                    not in str(trigger_value).lower()
                                ):
                                    logger.warning(
                                        f"NOTE: Portal changed your preferred trigger '{self._preferred_trigger}' to '{trigger_value}'"
                                    )
                except Exception as e:
                    logger.debug(f"Could not parse trigger description: {e}")

                response_future.set_result(True)
            elif response_code == 1:
                logger.warning("User cancelled shortcut binding")
                response_future.set_result(False)
            else:
                response_future.set_exception(
                    Exception(f"BindShortcuts failed: {response_code}")
                )

        # Subscribe to Response signal
        # Use manual introspection to avoid issues with other properties
        request_introspection_xml = intr.Node.parse(
            """
        <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
         "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
        <node>
          <interface name="org.freedesktop.portal.Request">
            <signal name="Response">
              <arg type="u" name="response"/>
              <arg type="a{sv}" name="results"/>
            </signal>
          </interface>
        </node>
        """
        )

        try:
            request_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, expected_request_path, request_introspection_xml
            )
            request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
            request_iface.on_response(on_response)
        except Exception as e:
            logger.debug(f"Could not subscribe to request path before call: {e}")

        # Define our shortcut
        # Note: Must be a list of lists, not list of tuples, for dbus-next
        shortcuts = [
            [
                self._shortcut_id,
                {
                    "description": Variant("s", "Start/stop voice recording"),
                    "preferred_trigger": Variant("s", self._preferred_trigger),
                },
            ]
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
                request_proxy = self._bus.get_proxy_object(
                    self.PORTAL_BUS_NAME, request_handle, request_introspection_xml
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

    async def _configure_shortcuts(self, sender: str) -> bool:
        """Show the configuration dialog to let user change shortcut bindings.

        This uses ConfigureShortcuts (added in portal version 2) which allows
        reconfiguring shortcuts after the initial BindShortcuts call.
        Unlike BindShortcuts, this can be called multiple times on the same session.
        """
        from dbus_next import Variant
        from dbus_next import introspection as intr

        request_token = f"conf_{secrets.token_hex(8)}"
        expected_request_path = (
            f"/org/freedesktop/portal/desktop/request/{sender}/{request_token}"
        )

        response_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_response(response_code, results):
            if response_future.done():
                return
            if response_code == 0:
                shortcuts = results.get("shortcuts", [])
                logger.info(f"Shortcuts configured successfully: {shortcuts}")
                # Extract and log the actual trigger that was bound
                try:
                    if shortcuts and hasattr(shortcuts, "value"):
                        shortcuts_list = shortcuts.value
                    else:
                        shortcuts_list = shortcuts

                    if shortcuts_list:
                        for shortcut in shortcuts_list:
                            shortcut_id = shortcut[0]
                            shortcut_props = shortcut[1]
                            trigger = shortcut_props.get("trigger_description")
                            if trigger:
                                trigger_value = (
                                    trigger.value
                                    if hasattr(trigger, "value")
                                    else trigger
                                )
                                self._actual_bound_trigger = trigger_value
                                logger.warning(
                                    f"Portal configured shortcut '{shortcut_id}' to trigger: {trigger_value}"
                                )
                except Exception as e:
                    logger.debug(f"Could not parse trigger description: {e}")

                response_future.set_result(True)
            elif response_code == 1:
                logger.warning("User cancelled shortcut configuration")
                response_future.set_result(False)
            else:
                response_future.set_exception(
                    Exception(f"ConfigureShortcuts failed: {response_code}")
                )

        # Subscribe to Response signal
        request_introspection_xml = intr.Node.parse(
            """
        <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
         "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
        <node>
          <interface name="org.freedesktop.portal.Request">
            <signal name="Response">
              <arg type="u" name="response"/>
              <arg type="a{sv}" name="results"/>
            </signal>
          </interface>
        </node>
        """
        )

        try:
            request_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, expected_request_path, request_introspection_xml
            )
            request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
            request_iface.on_response(on_response)
        except Exception as e:
            logger.debug(f"Could not subscribe to request path before call: {e}")

        options = {
            "handle_token": Variant("s", request_token),
        }

        # parent_window can be empty for CLI/background apps
        parent_window = ""

        request_handle = await self._shortcuts_iface.call_configure_shortcuts(
            self._session_handle, parent_window, options
        )
        logger.debug(f"ConfigureShortcuts request: {request_handle}")

        # If we couldn't subscribe to request path, try subscribing now
        if not response_future.done():
            try:
                request_proxy = self._bus.get_proxy_object(
                    self.PORTAL_BUS_NAME, request_handle, request_introspection_xml
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
            logger.error("Timeout waiting for ConfigureShortcuts response")
            return False
        except Exception as e:
            logger.error(f"ConfigureShortcuts failed: {e}")
            return False

    def _on_shortcut_activated(
        self, session_handle: str, shortcut_id: str, timestamp: int, options: dict
    ):
        """Called when the shortcut is pressed.

        Note: The XDG Portal GlobalShortcuts API sends Activated/Deactivated pairs
        for each key repeat event (not just the initial press). We handle this by:
        1. Cancelling any pending release when we receive an Activated signal
        2. Only triggering press callback once per physical key press
        """
        if self._log_key_repeat_debug:
            logger.debug(
                f"Portal signal received - Activated: session={session_handle}, shortcut={shortcut_id}, timestamp={timestamp}"
            )
        if shortcut_id == self._shortcut_id:
            # Cancel any pending release - this Activated means the key is still held
            if self._pending_release_task is not None:
                self._pending_release_task.cancel()
                self._pending_release_task = None
                if self._log_key_repeat_debug:
                    logger.debug("Cancelled pending release (key repeat detected)")

            # Mark key as logically pressed
            self._key_is_pressed = True

            if self._press_callback_fired:
                # We already fired the press callback for this key press session
                # This is a key repeat - ignore
                if self._log_key_repeat_debug:
                    logger.debug(
                        "Ignoring key repeat Activated signal (press callback already fired)"
                    )
                elif not self._logged_debug_hint:
                    logger.debug(
                        "Key repeat signals detected (this is normal). "
                        "Set log_key_repeat_debug = true in settings.toml for detailed logs."
                    )
                    self._logged_debug_hint = True
                return

            # First Activated for this physical key press - fire the callback
            self._press_callback_fired = True
            logger.info(f"Shortcut activated: {shortcut_id} at {timestamp}")
            if self.on_hotkey_press:
                self.on_hotkey_press()
        else:
            logger.warning(
                f"Received activation for unknown shortcut: {shortcut_id} (expected: {self._shortcut_id})"
            )

    def _on_shortcut_deactivated(
        self, session_handle: str, shortcut_id: str, timestamp: int, options: dict
    ):
        """Called when the shortcut is released.

        Note: The XDG Portal sends Deactivated for both real releases AND key repeats.
        We use a delayed release approach: schedule the release callback after a short
        delay. If an Activated signal arrives before the delay expires (indicating key
        repeat), we cancel the pending release.
        """
        if self._log_key_repeat_debug:
            logger.debug(
                f"Portal signal received - Deactivated: session={session_handle}, shortcut={shortcut_id}, timestamp={timestamp}"
            )
        if shortcut_id == self._shortcut_id:
            if not self._press_callback_fired:
                # We never fired the press callback, so don't fire release either
                if self._log_key_repeat_debug:
                    logger.debug(
                        "Ignoring Deactivated signal (press callback never fired)"
                    )
                return

            # Mark key as not physically pressed (but keep _press_callback_fired until
            # we confirm it's a real release via debounce timeout)
            self._key_is_pressed = False

            # Cancel any existing pending release and schedule a new one
            if self._pending_release_task is not None:
                self._pending_release_task.cancel()
                self._pending_release_task = None

            # Schedule a delayed release - will be cancelled if Activated arrives
            if self._log_key_repeat_debug:
                logger.debug(
                    f"Scheduling delayed release in {self._debounce_threshold_sec}s"
                )
            if self._loop:
                self._pending_release_task = self._loop.call_later(
                    self._debounce_threshold_sec,
                    self._execute_release,
                    shortcut_id,
                    timestamp,
                )
            else:
                # Fallback: if no loop, execute immediately (shouldn't happen)
                logger.warning("No event loop available, executing release immediately")
                self._execute_release(shortcut_id, timestamp)
        else:
            logger.warning(
                f"Received deactivation for unknown shortcut: {shortcut_id} (expected: {self._shortcut_id})"
            )

    def _execute_release(self, shortcut_id: str, timestamp: int):
        """Execute the actual release callback after debounce delay."""
        self._pending_release_task = None
        self._key_is_pressed = False
        self._press_callback_fired = False  # Reset for next key press
        logger.info(f"Shortcut deactivated: {shortcut_id} at {timestamp}")
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

        # Cancel any pending release task
        if self._pending_release_task is not None:
            self._pending_release_task.cancel()
            self._pending_release_task = None

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

    def rebind_shortcut(self) -> bool:
        """Force the portal to show the shortcut configuration dialog again.

        This allows the user to change their hotkey binding. On portal version 2+,
        uses ConfigureShortcuts. On portal version 1, recreates the session
        (which triggers a new BindShortcuts dialog).

        Returns:
            True if configuration succeeded, False otherwise.

        Raises:
            RuntimeError: If the listener is not running.
        """
        if not self._running or not self._loop or not self._session_handle:
            raise RuntimeError(
                "Portal listener is not running. Call start_listening() first."
            )

        rebind_complete = threading.Event()
        rebind_result: list = [False]

        async def do_rebind_async():
            sender = self._bus.unique_name.replace(":", "").replace(".", "_")
            # Try ConfigureShortcuts first (portal version 2+)
            try:
                result = await self._configure_shortcuts(sender)
                return result
            except Exception as e:
                if "No such method" in str(e) or "ConfigureShortcuts" in str(e):
                    logger.info(
                        "ConfigureShortcuts not available (portal v1), "
                        "recreating session to rebind"
                    )
                    # Fall back to recreating session for portal v1
                    return await self._recreate_session_for_rebind(sender)
                else:
                    raise

        def do_rebind():
            future = asyncio.ensure_future(do_rebind_async())

            def on_done(fut):
                try:
                    rebind_result[0] = fut.result()
                except Exception as e:
                    logger.error(f"Rebind failed: {e}")
                    rebind_result[0] = False
                rebind_complete.set()

            future.add_done_callback(on_done)

        self._loop.call_soon_threadsafe(do_rebind)

        # Wait for user interaction (60s timeout like initial bind)
        rebind_complete.wait(timeout=65.0)
        return rebind_result[0]

    async def _recreate_session_for_rebind(self, sender: str) -> bool:
        """Recreate the portal session to allow rebinding shortcuts.

        This is the fallback for portal version 1 which doesn't have
        ConfigureShortcuts. We close the current session and create a new one,
        which will show the BindShortcuts dialog again.
        """
        from dbus_next import introspection as intr

        # Unsubscribe from current signals
        try:
            self._shortcuts_iface.off_activated(self._on_shortcut_activated)
            self._shortcuts_iface.off_deactivated(self._on_shortcut_deactivated)
        except Exception as e:
            logger.debug(f"Error unsubscribing from signals: {e}")

        old_session = self._session_handle
        self._session_handle = None

        # Explicitly close the old session via D-Bus Session.Close() method
        logger.info(f"Closing old session: {old_session}")
        try:
            session_introspection = intr.Node.parse(
                """
            <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
             "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
            <node>
              <interface name="org.freedesktop.portal.Session">
                <method name="Close">
                </method>
              </interface>
            </node>
            """
            )
            session_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, old_session, session_introspection
            )
            session_iface = session_proxy.get_interface(
                "org.freedesktop.portal.Session"
            )
            await session_iface.call_close()
            logger.info("Old session closed successfully")
            # Give the portal a moment to clean up
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"Error closing old session (may already be closed): {e}")
            # Continue anyway - session might have been closed already

        # Create new session with a unique token to avoid conflicts
        session_token = f"voicetype_session_{secrets.token_hex(4)}"
        new_session = await self._create_session(sender, session_token)
        if not new_session:
            logger.error("Failed to create new session for rebind")
            return False

        self._session_handle = new_session
        logger.info(f"New session created: {new_session}")

        # Bind shortcuts again (this shows the dialog)
        success = await self._bind_shortcuts(sender)
        if not success:
            return False

        # Re-subscribe to signals
        logger.debug("Re-subscribing to Activated signal...")
        self._shortcuts_iface.on_activated(self._on_shortcut_activated)
        logger.debug("Re-subscribing to Deactivated signal...")
        self._shortcuts_iface.on_deactivated(self._on_shortcut_deactivated)

        logger.info("Session recreated and shortcuts rebound successfully")
        return True


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
