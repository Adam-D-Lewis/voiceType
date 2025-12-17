# Implementing Wayland Global Shortcuts for VoiceType

This guide explains how to implement the XDG Desktop Portal GlobalShortcuts API to enable VoiceType to work on Wayland without root privileges.

## Background

### The Problem

On Wayland, applications cannot capture global keyboard input directly (unlike X11). This is a security feature - only the compositor receives all keyboard events. VoiceType currently uses pynput, which:
- Works on X11
- Works on Wayland **only with root** (via `/dev/input` evdev)

### The Solution

The **XDG Desktop Portal GlobalShortcuts** API provides a secure, rootless way for applications to register global hotkeys. The compositor handles the actual key detection and notifies your app via D-Bus signals.

### Desktop Support (as of late 2025)

| Desktop | Status |
|---------|--------|
| KDE Plasma | Supported (since ~2023) |
| GNOME 48+ | Supported (March 2025) |
| Hyprland | Supported (limited UX) |
| wlroots/Sway | Not yet implemented |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Compositor                               │
│  (GNOME Shell / KWin / Hyprland)                                │
│  - Receives ALL keyboard input                                   │
│  - Runs xdg-desktop-portal-gnome/kde/hyprland                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ D-Bus (org.freedesktop.portal.Desktop)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    xdg-desktop-portal                            │
│  - Routes requests to correct backend                            │
│  - Manages sessions                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ D-Bus signals (Activated/Deactivated)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       VoiceType                                  │
│  - Creates session                                               │
│  - Binds shortcuts                                               │
│  - Receives activation signals                                   │
└─────────────────────────────────────────────────────────────────┘
```

## D-Bus API Reference

FYI: Can maybe use libportal instead of [XDG Portals D-Bus APIs directly](https://flatpak.github.io/xdg-desktop-portal/docs/convenience-libraries.html) once https://github.com/flatpak/libportal/issues/134 is resolved.  Maybe could use [ashpd](https://github.com/bilelmoussaoui/ashpd) if they [provide python bindings](https://github.com/bilelmoussaoui/ashpd/issues/64).

### Service Details

- **Bus**: Session Bus
- **Service**: `org.freedesktop.portal.Desktop`
- **Object Path**: `/org/freedesktop/portal/desktop`
- **Interface**: `org.freedesktop.portal.GlobalShortcuts`

### Key Methods

#### 1. CreateSession

Creates a new shortcuts session.

```
CreateSession(options: a{sv}) → (request_handle: o)
```

**Options:**
- `handle_token` (s): Token for the request handle path
- `session_handle_token` (s): Token for the session handle path

**Response** (via `org.freedesktop.portal.Request::Response` signal):
- `session_handle` (s): The session object path (note: string, not object path due to historical bug)

#### 2. BindShortcuts

Registers shortcuts for the session. Typically shows a user dialog.

```
BindShortcuts(session_handle: o, shortcuts: a(sa{sv}), parent_window: s, options: a{sv}) → (request_handle: o)
```

**Shortcuts array format:**
```python
[
    ("shortcut-id", {
        "description": ("s", "Start/stop voice recording"),
        "preferred_trigger": ("s", "Pause")  # Optional hint
    })
]
```

**Response** (via signal):
- `shortcuts` (a(sa{sv})): Bound shortcuts with actual triggers

#### 3. ListShortcuts

Lists all shortcuts in a session.

```
ListShortcuts(session_handle: o, options: a{sv}) → (request_handle: o)
```

### Key Signals

#### Activated

Emitted when a shortcut is triggered.

```
Activated(session_handle: o, shortcut_id: s, timestamp: t, options: a{sv})
```

#### Deactivated

Emitted when a shortcut is released.

```
Deactivated(session_handle: o, shortcut_id: s, timestamp: t, options: a{sv})
```

## Implementation Guide

### Step 1: Choose a D-Bus Library

**Recommended: `dbus-next`** (pure Python, asyncio support)

```bash
pip install dbus-next
```

Alternatives:
- `dbus-python`: Legacy, requires native libs
- `dasbus`: Fedora's library, good typing
- `pydbus`: Simpler but less maintained

### Step 2: Create the Portal Listener Class

Create `voicetype/hotkey_listener/portal_hotkey_listener.py`:

```python
"""XDG Desktop Portal GlobalShortcuts implementation for Wayland."""

import asyncio
import secrets
from typing import Callable, Optional

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.constants import BusType
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
        super().__init__(on_hotkey_press, on_hotkey_release)
        self._bus: Optional[MessageBus] = None
        self._session_handle: Optional[str] = None
        self._shortcut_id = "voicetype-record"
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False

    def set_hotkey(self, hotkey: str) -> None:
        """Set the preferred hotkey trigger.

        Note: On portal, the user confirms/modifies this in a system dialog.
        The format should match XDG shortcut spec (e.g., "Pause", "Control+Alt+R").
        """
        self._hotkey = hotkey
        logger.info(f"Preferred hotkey set to: {hotkey}")

    async def _setup_session(self) -> bool:
        """Create a GlobalShortcuts session and bind our shortcut."""
        try:
            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

            # Get introspection for the portal
            introspection = await self._bus.introspect(
                self.PORTAL_BUS_NAME,
                self.PORTAL_OBJECT_PATH
            )
            proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME,
                self.PORTAL_OBJECT_PATH,
                introspection
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
        request_token = f"req_{secrets.token_hex(8)}"
        expected_request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{request_token}"

        # Set up response handler BEFORE making the call (avoid race condition)
        response_future: asyncio.Future = asyncio.Future()

        def on_response(response_code, results):
            if response_code == 0:  # Success
                session_handle = results.get("session_handle")
                if session_handle:
                    response_future.set_result(session_handle.value)
                else:
                    response_future.set_exception(Exception("No session_handle in response"))
            elif response_code == 1:
                response_future.set_exception(Exception("User cancelled session creation"))
            else:
                response_future.set_exception(Exception(f"Session creation failed: {response_code}"))

        # Subscribe to the Response signal on the expected request path
        request_introspection = await self._bus.introspect(
            self.PORTAL_BUS_NAME,
            expected_request_path
        )
        request_proxy = self._bus.get_proxy_object(
            self.PORTAL_BUS_NAME,
            expected_request_path,
            request_introspection
        )
        request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
        request_iface.on_response(on_response)

        # Now make the CreateSession call
        options = {
            "handle_token": Variant("s", request_token),
            "session_handle_token": Variant("s", session_token),
        }

        request_handle = await self._shortcuts_iface.call_create_session(options)
        logger.debug(f"CreateSession request: {request_handle}")

        # Wait for the response
        try:
            session_handle = await asyncio.wait_for(response_future, timeout=30.0)
            return session_handle
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for CreateSession response")
            return None

    async def _bind_shortcuts(self, sender: str) -> bool:
        """Bind our recording shortcut to the session."""
        request_token = f"bind_{secrets.token_hex(8)}"
        expected_request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{request_token}"

        response_future: asyncio.Future = asyncio.Future()

        def on_response(response_code, results):
            if response_code == 0:
                shortcuts = results.get("shortcuts", [])
                logger.info(f"Shortcuts bound: {shortcuts}")
                response_future.set_result(True)
            elif response_code == 1:
                logger.warning("User cancelled shortcut binding")
                response_future.set_result(False)
            else:
                response_future.set_exception(Exception(f"BindShortcuts failed: {response_code}"))

        # Subscribe to Response signal
        request_introspection = await self._bus.introspect(
            self.PORTAL_BUS_NAME,
            expected_request_path
        )
        request_proxy = self._bus.get_proxy_object(
            self.PORTAL_BUS_NAME,
            expected_request_path,
            request_introspection
        )
        request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
        request_iface.on_response(on_response)

        # Define our shortcut
        shortcuts = [
            (self._shortcut_id, {
                "description": Variant("s", "Start/stop voice recording"),
                "preferred_trigger": Variant("s", self._hotkey or "Pause"),
            })
        ]

        options = {
            "handle_token": Variant("s", request_token),
        }

        # parent_window can be empty for CLI/background apps
        parent_window = ""

        request_handle = await self._shortcuts_iface.call_bind_shortcuts(
            self._session_handle,
            shortcuts,
            parent_window,
            options
        )
        logger.debug(f"BindShortcuts request: {request_handle}")

        try:
            success = await asyncio.wait_for(response_future, timeout=60.0)  # User interaction
            return success
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for BindShortcuts response")
            return False

    def _on_shortcut_activated(self, session_handle: str, shortcut_id: str,
                                timestamp: int, options: dict):
        """Called when the shortcut is pressed."""
        if shortcut_id == self._shortcut_id:
            logger.debug(f"Shortcut activated: {shortcut_id} at {timestamp}")
            if self.on_hotkey_press:
                self.on_hotkey_press()

    def _on_shortcut_deactivated(self, session_handle: str, shortcut_id: str,
                                  timestamp: int, options: dict):
        """Called when the shortcut is released."""
        if shortcut_id == self._shortcut_id:
            logger.debug(f"Shortcut deactivated: {shortcut_id} at {timestamp}")
            if self.on_hotkey_release:
                self.on_hotkey_release()

    def start_listening(self) -> None:
        """Start the portal hotkey listener."""
        if self._running:
            logger.info("Portal listener already running")
            return

        # Run the async setup in a new event loop (or existing one)
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            success = self._loop.run_until_complete(self._setup_session())
            if not success:
                raise RuntimeError("Failed to setup GlobalShortcuts session")

            self._running = True
            logger.info("Portal hotkey listener started")

            # Keep the event loop running to receive signals
            # This would typically be integrated with your app's main loop

        except Exception as e:
            logger.error(f"Failed to start portal listener: {e}")
            raise

    def stop_listening(self) -> None:
        """Stop the portal hotkey listener."""
        if not self._running:
            return

        self._running = False

        if self._bus:
            self._bus.disconnect()
            self._bus = None

        if self._loop:
            self._loop.close()
            self._loop = None

        self._session_handle = None
        logger.info("Portal hotkey listener stopped")


def is_portal_available() -> bool:
    """Check if the GlobalShortcuts portal is available."""
    import subprocess
    try:
        result = subprocess.run(
            ["busctl", "--user", "introspect",
             "org.freedesktop.portal.Desktop",
             "/org/freedesktop/portal/desktop",
             "org.freedesktop.portal.GlobalShortcuts"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False
```

### Step 3: Create a Factory Function

Update `voicetype/hotkey_listener/__init__.py`:

```python
import os
from typing import Callable, Optional

from loguru import logger

from .hotkey_listener import HotkeyListener
from .pynput_hotkey_listener import PynputHotkeyListener


def create_hotkey_listener(
    on_hotkey_press: Optional[Callable[[], None]] = None,
    on_hotkey_release: Optional[Callable[[], None]] = None,
) -> HotkeyListener:
    """Create the appropriate hotkey listener for the current platform.

    Priority:
    1. On Wayland with portal support: Use PortalHotkeyListener
    2. Otherwise: Use PynputHotkeyListener (X11, macOS, Windows)
    """

    # Check if we're on Wayland
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    xdg_session_type = os.environ.get("XDG_SESSION_TYPE")
    is_wayland = wayland_display or xdg_session_type == "wayland"

    if is_wayland:
        try:
            from .portal_hotkey_listener import PortalHotkeyListener, is_portal_available

            if is_portal_available():
                logger.info("Using XDG Portal GlobalShortcuts (Wayland)")
                return PortalHotkeyListener(
                    on_hotkey_press=on_hotkey_press,
                    on_hotkey_release=on_hotkey_release,
                )
            else:
                logger.warning(
                    "Wayland detected but GlobalShortcuts portal not available. "
                    "Falling back to pynput (may require root)."
                )
        except ImportError as e:
            logger.warning(f"Portal listener not available: {e}")

    # Default to pynput
    logger.info("Using pynput hotkey listener")
    return PynputHotkeyListener(
        on_hotkey_press=on_hotkey_press,
        on_hotkey_release=on_hotkey_release,
    )
```

### Step 4: Handle Event Loop Integration

The portal listener needs an event loop for D-Bus signals. For VoiceType's architecture, you have options:

**Option A: Threading (simpler)**

Run the asyncio event loop in a background thread:

```python
import threading

class PortalHotkeyListener(HotkeyListener):
    # ... existing code ...

    def start_listening(self) -> None:
        if self._running:
            return

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            success = self._loop.run_until_complete(self._setup_session())
            if success:
                self._running = True
                self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
```

**Option B: Integrate with existing event loop**

If your app already uses asyncio or GLib main loop, integrate the D-Bus handling there.

### Step 5: Add Dependencies

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
wayland = [
    "dbus-next>=0.2.3",
]
```

Or include by default if you want out-of-box Wayland support.

## Key Differences from Pynput

| Aspect | Pynput | Portal |
|--------|--------|--------|
| Key detection | App monitors all keys | Compositor notifies app |
| User control | None (app decides) | User confirms via dialog |
| Hotkey format | `<pause>`, `<ctrl>+<alt>+r` | `Pause`, `Control+Alt+R` |
| Press/Release | Both supported | Both supported |
| Permissions | Root on Wayland | None needed |

## Testing

### Manual Testing

1. Check portal availability:
```bash
busctl --user introspect org.freedesktop.portal.Desktop \
    /org/freedesktop/portal/desktop \
    org.freedesktop.portal.GlobalShortcuts
```

2. Test with `dbus-monitor`:
```bash
dbus-monitor --session "interface='org.freedesktop.portal.GlobalShortcuts'"
```

### Unit Testing

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_portal_session_creation():
    with patch("dbus_next.aio.MessageBus") as mock_bus:
        # Set up mocks for D-Bus interactions
        mock_bus_instance = AsyncMock()
        mock_bus.return_value.connect = AsyncMock(return_value=mock_bus_instance)

        listener = PortalHotkeyListener()
        # ... test session creation
```

## Troubleshooting

### "No such interface 'org.freedesktop.portal.GlobalShortcuts'"

- Your desktop doesn't support the portal yet
- Update to GNOME 48+ or latest KDE Plasma
- Check `xdg-desktop-portal-*` package is installed

### "Invalid session" errors

- Ensure you're using the session_handle as a **string**, not object path
- The handle returned from CreateSession response must be used exactly

### User dialog doesn't appear

- Try passing a valid `parent_window` (Wayland window handle)
- Some compositors (Hyprland) don't show dialogs

### Shortcuts not persisting

- Some backends don't persist shortcuts across restarts
- Store user preferences and re-bind on startup

## References

- [XDG Desktop Portal GlobalShortcuts Spec](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html)
- [XDG Desktop Portal Request Interface](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Request.html)
- [XDG Desktop Portal Gnome](https://gitlab.gnome.org/GNOME/xdg-desktop-portal-gnome)
- [GNOME 48 Release Notes](https://release.gnome.org/48/developers/index.html)
- [dbus-next Documentation](https://python-dbus-next.readthedocs.io/)
- [Mumble Portal Implementation PR](https://github.com/mumble-voip/mumble/pull/5976)
