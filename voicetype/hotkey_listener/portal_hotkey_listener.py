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
from typing import Callable, Dict, List, Optional, Tuple

from loguru import logger

from .hotkey_listener import HotkeyListener


class PortalHotkeyListener(HotkeyListener):
    """Wayland hotkey listener using XDG Desktop Portal GlobalShortcuts.

    This implementation works on GNOME 48+, KDE Plasma, and Hyprland
    without requiring root privileges. Supports multiple hotkeys.
    """

    PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
    PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
    SHORTCUTS_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
    REQUEST_INTERFACE = "org.freedesktop.portal.Request"

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[str], None]] = None,
        on_hotkey_release: Optional[Callable[[str], None]] = None,
        log_key_repeat_debug: bool = False,
    ):
        super().__init__(on_hotkey_press, on_hotkey_release)
        self._bus = None
        self._session_handle: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._shortcuts_iface = None
        self._log_key_repeat_debug = log_key_repeat_debug
        self._logged_debug_hint = False

        # Multi-hotkey support:
        # shortcut_id -> hotkey_string (pynput format, e.g. "<pause>")
        self._shortcut_id_to_hotkey: Dict[str, str] = {}
        # hotkey_string -> portal trigger format
        self._hotkey_triggers: Dict[str, str] = {}
        # Track key repeat state per shortcut_id
        self._press_callback_fired: Dict[str, bool] = {}
        # shortcut_id -> human-readable name
        self._shortcut_id_to_name: Dict[str, str] = {}

    def add_hotkey(self, hotkey: str, name: str = "") -> None:
        idx = len(self._shortcut_id_to_hotkey)
        # Include hotkey and name in ID so GNOME portal cache invalidates when hotkey changes
        key_slug = hotkey.strip("<>").replace("+", "-")
        name_slug = name.replace(" ", "-") if name else str(idx)
        shortcut_id = f"voicetype-{name_slug}-{key_slug}"
        self._shortcut_id_to_hotkey[shortcut_id] = hotkey
        self._shortcut_id_to_name[shortcut_id] = name or f"shortcut {idx}"
        self._hotkey_triggers[hotkey] = self._convert_hotkey_format(hotkey)
        self._press_callback_fired[shortcut_id] = False
        logger.info(
            f"Hotkey added: {hotkey} (portal: {self._hotkey_triggers[hotkey]}, id: {shortcut_id})"
        )

    def clear_hotkeys(self) -> None:
        self._shortcut_id_to_hotkey.clear()
        self._shortcut_id_to_name.clear()
        self._hotkey_triggers.clear()
        self._press_callback_fired.clear()

    def set_hotkey(self, hotkey: str) -> None:
        """Convenience: clear and add a single hotkey."""
        self.clear_hotkeys()
        self.add_hotkey(hotkey)

    def _convert_hotkey_format(self, hotkey: str) -> str:
        """Convert pynput hotkey format to XDG portal format."""
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

        if "<" not in hotkey:
            return hotkey

        parts = hotkey.lower().split("+")
        converted_parts = []

        for part in parts:
            part = part.strip()
            if part in key_map:
                converted_parts.append(key_map[part])
            elif part.startswith("<") and part.endswith(">"):
                key_name = part[1:-1].capitalize()
                converted_parts.append(key_name)
            else:
                converted_parts.append(part.upper())

        return "+".join(converted_parts)

    async def _setup_session(self) -> bool:
        """Create a GlobalShortcuts session and bind our shortcuts."""
        try:
            from dbus_next import Variant
            from dbus_next import introspection as intr
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType

            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

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

            sender = self._bus.unique_name.replace(":", "").replace(".", "_")
            session_token = "voicetype_session"

            session_handle = await self._create_session(sender, session_token)
            if not session_handle:
                return False

            self._session_handle = session_handle
            logger.info(f"Session created: {session_handle}")

            success = await self._bind_shortcuts(sender)
            if not success:
                return False

            logger.debug("Subscribing to Activated signal...")
            self._shortcuts_iface.on_activated(self._on_shortcut_activated)
            logger.debug("Subscribing to Deactivated signal...")
            self._shortcuts_iface.on_deactivated(self._on_shortcut_deactivated)

            logger.info(
                "Portal GlobalShortcuts session ready and listening for signals"
            )
            logger.info(f"Monitoring session: {self._session_handle}")
            logger.info(f"Registered shortcuts: {dict(self._shortcut_id_to_hotkey)}")

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

        response_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_response(response_code, results):
            if response_future.done():
                return
            if response_code == 0:
                session_handle = results.get("session_handle")
                if session_handle:
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

        options = {
            "handle_token": Variant("s", request_token),
            "session_handle_token": Variant("s", session_token),
        }

        request_handle = await self._shortcuts_iface.call_create_session(options)
        logger.debug(f"CreateSession request: {request_handle}")

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
            session_handle = await asyncio.wait_for(response_future, timeout=30.0)
            return session_handle
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for CreateSession response")
            return None
        except Exception as e:
            logger.error(f"CreateSession failed: {e}")
            return None

    async def _bind_shortcuts(self, sender: str) -> bool:
        """Bind all registered shortcuts to the session."""
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
            if response_code in (0, 2):
                shortcuts = results.get("shortcuts", [])
                logger.info(f"Shortcuts bound (code {response_code}): {shortcuts}")
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
                                logger.warning(
                                    f"Portal bound shortcut '{shortcut_id}' to trigger: {trigger_value}"
                                )
                except Exception as e:
                    logger.debug(f"Could not parse trigger description: {e}")

                if response_code == 0 or shortcuts:
                    response_future.set_result(True)
                else:
                    logger.warning("BindShortcuts returned code 2 with no shortcuts")
                    response_future.set_result(False)
            elif response_code == 1:
                logger.warning("User cancelled shortcut binding")
                response_future.set_result(False)
            else:
                response_future.set_exception(
                    Exception(f"BindShortcuts failed: {response_code}")
                )

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

        # Build shortcuts array with ALL registered hotkeys
        shortcuts = []
        for shortcut_id, hotkey_str in self._shortcut_id_to_hotkey.items():
            trigger = self._hotkey_triggers[hotkey_str]
            display_name = self._shortcut_id_to_name.get(shortcut_id, shortcut_id)
            shortcuts.append(
                [
                    shortcut_id,
                    {
                        "description": Variant("s", f"VoiceType: {display_name}"),
                        "preferred_trigger": Variant("s", trigger),
                    },
                ]
            )

        options = {
            "handle_token": Variant("s", request_token),
        }

        parent_window = ""

        request_handle = await self._shortcuts_iface.call_bind_shortcuts(
            self._session_handle, shortcuts, parent_window, options
        )
        logger.debug(f"BindShortcuts request: {request_handle}")

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
            success = await asyncio.wait_for(response_future, timeout=60.0)
            return success
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for BindShortcuts response")
            return False
        except Exception as e:
            logger.error(f"BindShortcuts failed: {e}")
            return False

    async def _configure_shortcuts(self, sender: str) -> bool:
        """Show the configuration dialog to let user change shortcut bindings."""
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

        parent_window = ""

        request_handle = await self._shortcuts_iface.call_configure_shortcuts(
            self._session_handle, parent_window, options
        )
        logger.debug(f"ConfigureShortcuts request: {request_handle}")

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
            success = await asyncio.wait_for(response_future, timeout=60.0)
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
        """Called when a shortcut is pressed."""
        if self._log_key_repeat_debug:
            logger.debug(
                f"Portal signal received - Activated: session={session_handle}, shortcut={shortcut_id}, timestamp={timestamp}"
            )

        hotkey_str = self._shortcut_id_to_hotkey.get(shortcut_id)
        if hotkey_str is None:
            logger.warning(
                f"Received activation for unknown shortcut: {shortcut_id} "
                f"(known: {list(self._shortcut_id_to_hotkey.keys())})"
            )
            return

        if self._press_callback_fired.get(shortcut_id, False):
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

        self._press_callback_fired[shortcut_id] = True
        logger.info(f"Shortcut activated: {shortcut_id} ({hotkey_str}) at {timestamp}")
        self._trigger_hotkey_press(hotkey_str)

    def _on_shortcut_deactivated(
        self, session_handle: str, shortcut_id: str, timestamp: int, options: dict
    ):
        """Called when a shortcut is released."""
        if self._log_key_repeat_debug:
            logger.debug(
                f"Portal signal received - Deactivated: session={session_handle}, shortcut={shortcut_id}, timestamp={timestamp}"
            )

        hotkey_str = self._shortcut_id_to_hotkey.get(shortcut_id)
        if hotkey_str is None:
            logger.warning(
                f"Received deactivation for unknown shortcut: {shortcut_id} "
                f"(known: {list(self._shortcut_id_to_hotkey.keys())})"
            )
            return

        if not self._press_callback_fired.get(shortcut_id, False):
            if self._log_key_repeat_debug:
                logger.debug("Ignoring Deactivated signal (press callback never fired)")
            return

        self._press_callback_fired[shortcut_id] = False
        logger.info(
            f"Shortcut deactivated: {shortcut_id} ({hotkey_str}) at {timestamp}"
        )
        self._trigger_hotkey_release(hotkey_str)

    def start_listening(self) -> None:
        """Start the portal hotkey listener."""
        if self._running:
            logger.info("Portal listener already running")
            return

        if not self._shortcut_id_to_hotkey:
            raise ValueError("No hotkeys registered before starting listener.")

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

        setup_complete.wait(timeout=65.0)

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
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning("Portal listener thread did not stop gracefully")

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
        """Force the portal to show the shortcut configuration dialog again."""
        if not self._running or not self._loop or not self._session_handle:
            raise RuntimeError(
                "Portal listener is not running. Call start_listening() first."
            )

        rebind_complete = threading.Event()
        rebind_result: list = [False]

        async def do_rebind_async():
            sender = self._bus.unique_name.replace(":", "").replace(".", "_")
            try:
                result = await self._configure_shortcuts(sender)
                return result
            except Exception as e:
                if "No such method" in str(e) or "ConfigureShortcuts" in str(e):
                    logger.info(
                        "ConfigureShortcuts not available (portal v1), "
                        "recreating session to rebind"
                    )
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

        rebind_complete.wait(timeout=65.0)
        return rebind_result[0]

    async def _recreate_session_for_rebind(self, sender: str) -> bool:
        """Recreate the portal session to allow rebinding shortcuts."""
        from dbus_next import introspection as intr

        try:
            self._shortcuts_iface.off_activated(self._on_shortcut_activated)
            self._shortcuts_iface.off_deactivated(self._on_shortcut_deactivated)
        except Exception as e:
            logger.debug(f"Error unsubscribing from signals: {e}")

        old_session = self._session_handle
        self._session_handle = None

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
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"Error closing old session (may already be closed): {e}")

        session_token = f"voicetype_session_{secrets.token_hex(4)}"
        new_session = await self._create_session(sender, session_token)
        if not new_session:
            logger.error("Failed to create new session for rebind")
            return False

        self._session_handle = new_session
        logger.info(f"New session created: {new_session}")

        success = await self._bind_shortcuts(sender)
        if not success:
            return False

        logger.debug("Re-subscribing to Activated signal...")
        self._shortcuts_iface.on_activated(self._on_shortcut_activated)
        logger.debug("Re-subscribing to Deactivated signal...")
        self._shortcuts_iface.on_deactivated(self._on_shortcut_deactivated)

        logger.info("Session recreated and shortcuts rebound successfully")
        return True


def is_portal_available() -> bool:
    """Check if the GlobalShortcuts portal is available."""
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
        pass
    except Exception:
        pass

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
        if result.returncode == 0 and "CreateSession" in result.stdout:
            return True
    except Exception:
        pass

    return False
