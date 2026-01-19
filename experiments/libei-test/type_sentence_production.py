#!/usr/bin/env python3
"""
Production-ready libei typing for speech-to-text applications.

Combines the best features from all experiments:
- Persistent permissions (no dialog after first approval)
- Fast typing (~100+ chars/sec) with device removal rollback
- Dynamic XKB keyboard layout detection (works with any layout)
- Clean error handling and graceful degradation

Usage:
    python type_sentence_production.py                    # Type demo text
    python type_sentence_production.py --text "Hello"     # Type custom text
    python type_sentence_production.py --reset            # Clear saved permissions
    python type_sentence_production.py --show-layout      # Show keyboard mapping
    python type_sentence_production.py --layout us --variant dvorak  # Override layout
"""

import argparse
import ctypes
import ctypes.util
import os
import select
import subprocess
import time
from pathlib import Path
from typing import Iterator, Optional

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

# Setup D-Bus with GLib main loop (must be done before any D-Bus calls)
DBusGMainLoop(set_as_default=True)


# =============================================================================
# Configuration
# =============================================================================

# Local config directory (kept within experiments dir)
CONFIG_DIR = Path(__file__).parent / ".libei-config"
TOKEN_FILE = CONFIG_DIR / "restore_token"
LAYOUT_FILE = CONFIG_DIR / "keyboard_layout"

# Portal constants
PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
REMOTE_DESKTOP_IFACE = "org.freedesktop.portal.RemoteDesktop"
REQUEST_IFACE = "org.freedesktop.portal.Request"

# Device type flags
DEVICE_KEYBOARD = 1

# Persist mode options
PERSIST_MODE_PERMANENT = 2  # Persist until explicitly revoked

# Typing speed (ms delay after each character)
# Lower = faster, but may drop chars on slow systems
FAST_DELAY_MS = 5
INITIAL_SETTLE_MS = 50  # Extra delay for first few chars

# Standard modifier keycodes (evdev)
KEY_LEFTSHIFT = 42


# =============================================================================
# libei ctypes bindings (avoids snegg debug spam)
# =============================================================================

_libei_path = ctypes.util.find_library("ei")
if not _libei_path:
    for path in ["libei.so.1", "libei.so.0", "libei.so"]:
        try:
            _libei = ctypes.CDLL(path)
            break
        except OSError:
            continue
    else:
        raise ImportError(
            "Could not find libei library. Install with: sudo apt install libei1"
        )
else:
    _libei = ctypes.CDLL(_libei_path)


class _EiPtr(ctypes.c_void_p):
    pass


class _EiSeatPtr(ctypes.c_void_p):
    pass


class _EiDevicePtr(ctypes.c_void_p):
    pass


class _EiEventPtr(ctypes.c_void_p):
    pass


# Function signatures
_libei.ei_new_sender.argtypes = [ctypes.c_void_p]
_libei.ei_new_sender.restype = _EiPtr
_libei.ei_unref.argtypes = [_EiPtr]
_libei.ei_unref.restype = _EiPtr
_libei.ei_setup_backend_fd.argtypes = [_EiPtr, ctypes.c_int]
_libei.ei_setup_backend_fd.restype = ctypes.c_int
_libei.ei_get_fd.argtypes = [_EiPtr]
_libei.ei_get_fd.restype = ctypes.c_int
_libei.ei_dispatch.argtypes = [_EiPtr]
_libei.ei_dispatch.restype = ctypes.c_int
_libei.ei_configure_name.argtypes = [_EiPtr, ctypes.c_char_p]
_libei.ei_configure_name.restype = None
_libei.ei_get_event.argtypes = [_EiPtr]
_libei.ei_get_event.restype = _EiEventPtr
_libei.ei_event_unref.argtypes = [_EiEventPtr]
_libei.ei_event_unref.restype = _EiEventPtr
_libei.ei_event_get_type.argtypes = [_EiEventPtr]
_libei.ei_event_get_type.restype = ctypes.c_int
_libei.ei_event_get_seat.argtypes = [_EiEventPtr]
_libei.ei_event_get_seat.restype = _EiSeatPtr
_libei.ei_event_get_device.argtypes = [_EiEventPtr]
_libei.ei_event_get_device.restype = _EiDevicePtr
_libei.ei_seat_get_name.argtypes = [_EiSeatPtr]
_libei.ei_seat_get_name.restype = ctypes.c_char_p
_libei.ei_seat_ref.argtypes = [_EiSeatPtr]
_libei.ei_seat_ref.restype = _EiSeatPtr
_libei.ei_seat_unref.argtypes = [_EiSeatPtr]
_libei.ei_seat_unref.restype = _EiSeatPtr
_libei.ei_seat_bind_capabilities.restype = ctypes.c_int
_libei.ei_device_get_name.argtypes = [_EiDevicePtr]
_libei.ei_device_get_name.restype = ctypes.c_char_p
_libei.ei_device_has_capability.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_libei.ei_device_has_capability.restype = ctypes.c_bool
_libei.ei_device_ref.argtypes = [_EiDevicePtr]
_libei.ei_device_ref.restype = _EiDevicePtr
_libei.ei_device_unref.argtypes = [_EiDevicePtr]
_libei.ei_device_unref.restype = _EiDevicePtr
_libei.ei_device_start_emulating.argtypes = [_EiDevicePtr, ctypes.c_uint32]
_libei.ei_device_start_emulating.restype = None
_libei.ei_device_stop_emulating.argtypes = [_EiDevicePtr]
_libei.ei_device_stop_emulating.restype = None
_libei.ei_device_frame.argtypes = [_EiDevicePtr, ctypes.c_uint64]
_libei.ei_device_frame.restype = None
_libei.ei_device_keyboard_key.argtypes = [_EiDevicePtr, ctypes.c_uint32, ctypes.c_bool]
_libei.ei_device_keyboard_key.restype = None


class EventType:
    """libei event types."""

    CONNECT = 1
    DISCONNECT = 2
    SEAT_ADDED = 3
    SEAT_REMOVED = 4
    DEVICE_ADDED = 5
    DEVICE_REMOVED = 6
    DEVICE_PAUSED = 7
    DEVICE_RESUMED = 8


class DeviceCapability:
    """libei device capabilities (bit flags)."""

    POINTER = 1 << 0
    POINTER_ABSOLUTE = 1 << 1
    KEYBOARD = 1 << 2
    TOUCH = 1 << 3
    SCROLL = 1 << 4
    BUTTON = 1 << 5


class EiEvent:
    """Wrapper for ei_event."""

    def __init__(self, ptr: _EiEventPtr):
        self._ptr = ptr
        self._type: Optional[int] = None

    @property
    def event_type(self) -> int:
        if self._type is None:
            self._type = _libei.ei_event_get_type(self._ptr)
        return self._type

    @property
    def seat(self) -> Optional["EiSeat"]:
        seat_ptr = _libei.ei_event_get_seat(self._ptr)
        if seat_ptr:
            _libei.ei_seat_ref(seat_ptr)
            return EiSeat(seat_ptr)
        return None

    @property
    def device(self) -> Optional["EiDevice"]:
        dev_ptr = _libei.ei_event_get_device(self._ptr)
        if dev_ptr:
            _libei.ei_device_ref(dev_ptr)
            return EiDevice(dev_ptr)
        return None

    def __del__(self):
        if self._ptr:
            _libei.ei_event_unref(self._ptr)


class EiSeat:
    """Wrapper for ei_seat."""

    def __init__(self, ptr: _EiSeatPtr):
        self._ptr = ptr

    @property
    def name(self) -> str:
        name = _libei.ei_seat_get_name(self._ptr)
        return name.decode("utf-8") if name else ""

    def bind_keyboard(self):
        """Bind keyboard capability to this seat."""
        _libei.ei_seat_bind_capabilities(self._ptr, DeviceCapability.KEYBOARD, 0)

    def __del__(self):
        if self._ptr:
            _libei.ei_seat_unref(self._ptr)


class EiDevice:
    """Wrapper for ei_device."""

    def __init__(self, ptr: _EiDevicePtr):
        self._ptr = ptr
        self._sequence = 0

    @property
    def name(self) -> str:
        name = _libei.ei_device_get_name(self._ptr)
        return name.decode("utf-8") if name else ""

    def is_keyboard(self) -> bool:
        """Check if this device is a keyboard."""
        if _libei.ei_device_has_capability(self._ptr, DeviceCapability.KEYBOARD):
            name = self.name.lower()
            return "pointer" not in name or "keyboard" in name
        return "keyboard" in self.name.lower()

    def start_emulating(self):
        self._sequence += 1
        _libei.ei_device_start_emulating(self._ptr, self._sequence)

    def stop_emulating(self):
        _libei.ei_device_stop_emulating(self._ptr)

    def frame(self):
        _libei.ei_device_frame(self._ptr, 0)

    def keyboard_key(self, keycode: int, pressed: bool):
        _libei.ei_device_keyboard_key(self._ptr, keycode, pressed)

    def __del__(self):
        if self._ptr:
            _libei.ei_device_unref(self._ptr)


class EiSender:
    """EI sender context for sending input events."""

    def __init__(self, ptr: _EiPtr):
        self._ptr = ptr

    @classmethod
    def create_for_fd(cls, fd: int, name: str = "voicetype") -> "EiSender":
        ptr = _libei.ei_new_sender(None)
        if not ptr:
            raise RuntimeError("Failed to create ei sender context")
        _libei.ei_configure_name(ptr, name.encode("utf-8"))
        ret = _libei.ei_setup_backend_fd(ptr, fd)
        if ret != 0:
            _libei.ei_unref(ptr)
            raise RuntimeError(f"Failed to setup backend fd: {ret}")
        return cls(ptr)

    @property
    def fd(self) -> int:
        return _libei.ei_get_fd(self._ptr)

    def dispatch(self):
        _libei.ei_dispatch(self._ptr)

    @property
    def events(self) -> Iterator[EiEvent]:
        while True:
            event_ptr = _libei.ei_get_event(self._ptr)
            if not event_ptr:
                break
            yield EiEvent(event_ptr)

    def __del__(self):
        if self._ptr:
            _libei.ei_unref(self._ptr)


# =============================================================================
# libxkbcommon bindings for keyboard layout detection
# =============================================================================

_xkb_path = ctypes.util.find_library("xkbcommon")
if not _xkb_path:
    raise ImportError(
        "Could not find libxkbcommon. Install with: sudo apt install libxkbcommon-dev"
    )
_xkb = ctypes.CDLL(_xkb_path)


class _XkbContextPtr(ctypes.c_void_p):
    pass


class _XkbKeymapPtr(ctypes.c_void_p):
    pass


class _XkbStatePtr(ctypes.c_void_p):
    pass


class _XkbRuleNames(ctypes.Structure):
    _fields_ = [
        ("rules", ctypes.c_char_p),
        ("model", ctypes.c_char_p),
        ("layout", ctypes.c_char_p),
        ("variant", ctypes.c_char_p),
        ("options", ctypes.c_char_p),
    ]


XKB_CONTEXT_NO_FLAGS = 0
XKB_KEYMAP_COMPILE_NO_FLAGS = 0
XKB_KEY_DOWN = 1
EVDEV_OFFSET = 8

_xkb.xkb_context_new.argtypes = [ctypes.c_int]
_xkb.xkb_context_new.restype = _XkbContextPtr
_xkb.xkb_context_unref.argtypes = [_XkbContextPtr]
_xkb.xkb_context_unref.restype = None
_xkb.xkb_keymap_new_from_names.argtypes = [
    _XkbContextPtr,
    ctypes.POINTER(_XkbRuleNames),
    ctypes.c_int,
]
_xkb.xkb_keymap_new_from_names.restype = _XkbKeymapPtr
_xkb.xkb_keymap_unref.argtypes = [_XkbKeymapPtr]
_xkb.xkb_keymap_unref.restype = None
_xkb.xkb_keymap_min_keycode.argtypes = [_XkbKeymapPtr]
_xkb.xkb_keymap_min_keycode.restype = ctypes.c_uint32
_xkb.xkb_keymap_max_keycode.argtypes = [_XkbKeymapPtr]
_xkb.xkb_keymap_max_keycode.restype = ctypes.c_uint32
_xkb.xkb_state_new.argtypes = [_XkbKeymapPtr]
_xkb.xkb_state_new.restype = _XkbStatePtr
_xkb.xkb_state_unref.argtypes = [_XkbStatePtr]
_xkb.xkb_state_unref.restype = None
_xkb.xkb_state_key_get_utf8.argtypes = [
    _XkbStatePtr,
    ctypes.c_uint32,
    ctypes.c_char_p,
    ctypes.c_size_t,
]
_xkb.xkb_state_key_get_utf8.restype = ctypes.c_int
_xkb.xkb_state_update_key.argtypes = [_XkbStatePtr, ctypes.c_uint32, ctypes.c_int]
_xkb.xkb_state_update_key.restype = ctypes.c_uint32


def get_system_xkb_settings() -> tuple[str, str, str, str, str]:
    """Get current XKB settings from the system."""
    try:
        result = subprocess.run(
            ["setxkbmap", "-query"], capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            settings = {}
            for line in result.stdout.strip().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    settings[key.strip()] = value.strip()

            layout = settings.get("layout", "us")
            variant = settings.get("variant", "")

            # Handle comma-separated layouts (use first one)
            if "," in layout:
                layouts = layout.split(",")
                variants = variant.split(",") if variant else [""] * len(layouts)
                layout = layouts[0]
                variant = variants[0] if variants else ""

            return (
                settings.get("rules", "evdev"),
                settings.get("model", "pc105"),
                layout,
                variant,
                settings.get("options", ""),
            )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to environment variables
    return (
        "evdev",
        "pc105",
        os.environ.get("XKB_DEFAULT_LAYOUT", "us"),
        os.environ.get("XKB_DEFAULT_VARIANT", ""),
        "",
    )


class KeyboardLayout:
    """XKB keyboard layout with character → keycode mapping."""

    def __init__(self, layout: Optional[str] = None, variant: Optional[str] = None):
        self._ctx: Optional[_XkbContextPtr] = None
        self._keymap: Optional[_XkbKeymapPtr] = None
        self._char_map: dict[str, tuple[int, bool]] = {}

        # Get settings
        if layout is None:
            rules, model, layout, detected_variant, options = get_system_xkb_settings()
            variant = variant or detected_variant
        else:
            rules, model, options = "evdev", "pc105", ""
            variant = variant or ""

        self.layout_name = layout
        self.variant_name = variant

        self._init_xkb(rules, model, layout, variant, options)
        self._build_char_map()

    def _init_xkb(
        self, rules: str, model: str, layout: str, variant: str, options: str
    ):
        self._ctx = _xkb.xkb_context_new(XKB_CONTEXT_NO_FLAGS)
        if not self._ctx:
            raise RuntimeError("Failed to create XKB context")

        names = _XkbRuleNames(
            rules=rules.encode() if rules else None,
            model=model.encode() if model else None,
            layout=layout.encode() if layout else None,
            variant=variant.encode() if variant else None,
            options=options.encode() if options else None,
        )

        self._keymap = _xkb.xkb_keymap_new_from_names(
            self._ctx, ctypes.byref(names), XKB_KEYMAP_COMPILE_NO_FLAGS
        )
        if not self._keymap:
            raise RuntimeError(
                f"Failed to create keymap for layout '{layout}' variant '{variant}'"
            )

    def _get_char_for_key(self, xkb_keycode: int, with_shift: bool = False) -> str:
        state = _xkb.xkb_state_new(self._keymap)
        if not state:
            return ""
        try:
            if with_shift:
                _xkb.xkb_state_update_key(
                    state, KEY_LEFTSHIFT + EVDEV_OFFSET, XKB_KEY_DOWN
                )
            buf = ctypes.create_string_buffer(8)
            size = _xkb.xkb_state_key_get_utf8(state, xkb_keycode, buf, 8)
            return buf.value.decode("utf-8") if size > 0 else ""
        finally:
            _xkb.xkb_state_unref(state)

    def _build_char_map(self):
        min_kc = _xkb.xkb_keymap_min_keycode(self._keymap)
        max_kc = _xkb.xkb_keymap_max_keycode(self._keymap)

        for xkb_kc in range(min_kc, max_kc + 1):
            evdev_kc = xkb_kc - EVDEV_OFFSET
            if evdev_kc < 1 or evdev_kc > 255:
                continue

            # Without shift
            char = self._get_char_for_key(xkb_kc, with_shift=False)
            if char and char not in self._char_map:
                self._char_map[char] = (evdev_kc, False)

            # With shift
            char_shift = self._get_char_for_key(xkb_kc, with_shift=True)
            if char_shift and char_shift != char and char_shift not in self._char_map:
                self._char_map[char_shift] = (evdev_kc, True)

        # Ensure essential keys are mapped
        self._char_map.setdefault(" ", (57, False))  # Space
        self._char_map.setdefault("\n", (28, False))  # Enter
        self._char_map.setdefault("\t", (15, False))  # Tab

    def get_key_info(self, char: str) -> tuple[int, bool]:
        """Get (evdev_keycode, needs_shift) for a character."""
        return self._char_map.get(char, (-1, False))

    def print_mapping(
        self,
        chars: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?'\"-",
    ):
        """Print the keycode mapping for debugging."""
        print(
            f"\nKeyboard Layout: {self.layout_name} (variant: {self.variant_name or 'none'})"
        )
        print("Character -> Keycode mapping:")
        for char in chars:
            kc, shift = self.get_key_info(char)
            shift_str = "+Shift" if shift else ""
            display_char = repr(char) if char in " \n\t" else f"'{char}'"
            if kc != -1:
                print(f"  {display_char:6} -> keycode {kc}{shift_str}")
            else:
                print(f"  {display_char:6} -> NOT FOUND")

    def __del__(self):
        if hasattr(self, "_keymap") and self._keymap:
            _xkb.xkb_keymap_unref(self._keymap)
        if hasattr(self, "_ctx") and self._ctx:
            _xkb.xkb_context_unref(self._ctx)


# =============================================================================
# Token persistence
# =============================================================================


def load_restore_token() -> Optional[str]:
    """Load saved restore token from disk."""
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            return token
    return None


def save_restore_token(token: str):
    """Save restore token to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)


def clear_restore_token():
    """Delete saved restore token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"Cleared saved permissions from {TOKEN_FILE}")


def load_keyboard_config() -> tuple[Optional[str], Optional[str]]:
    """Load saved keyboard layout from local config.

    Returns (layout, variant) or (None, None) if not configured.
    """
    if LAYOUT_FILE.exists():
        content = LAYOUT_FILE.read_text().strip()
        if content:
            parts = content.split(":", 1)
            layout = parts[0] if parts[0] else None
            variant = parts[1] if len(parts) > 1 and parts[1] else None
            return (layout, variant)
    return (None, None)


def save_keyboard_config(layout: str, variant: Optional[str] = None):
    """Save keyboard layout to local config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    content = f"{layout}:{variant or ''}"
    LAYOUT_FILE.write_text(content)
    print(f"Saved keyboard layout to {LAYOUT_FILE}")


# =============================================================================
# RemoteDesktop Portal Session
# =============================================================================


class RemoteDesktopSession:
    """RemoteDesktop session with persistent permissions support."""

    def __init__(self):
        self.bus = dbus.SessionBus()
        self.portal = self.bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)
        self.remote_desktop = dbus.Interface(self.portal, REMOTE_DESKTOP_IFACE)
        self.session_handle: Optional[str] = None
        self.restore_token: Optional[str] = None
        self.loop = GLib.MainLoop()
        self._request_counter = 0

    def _get_request_token(self) -> str:
        self._request_counter += 1
        return f"u{os.getpid()}_{self._request_counter}"

    def _get_request_path(self, token: str) -> str:
        sender = self.bus.get_unique_name().replace(".", "_").replace(":", "")
        return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    def create_session(self):
        """Create a RemoteDesktop session."""
        token = self._get_request_token()
        session_token = f"u{os.getpid()}_session"
        request_path = self._get_request_path(token)
        result = {"session_handle": None}

        def on_response(response, results):
            if response == 0:
                result["session_handle"] = results.get("session_handle", "")
            self.loop.quit()

        self.bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=request_path,
        )
        try:
            self.remote_desktop.CreateSession(
                {
                    "handle_token": token,
                    "session_handle_token": session_token,
                }
            )
            self.loop.run()
        finally:
            self.bus.remove_signal_receiver(
                on_response,
                signal_name="Response",
                dbus_interface=REQUEST_IFACE,
                path=request_path,
            )

        if not result["session_handle"]:
            raise RuntimeError("Failed to create session")
        self.session_handle = result["session_handle"]

    def select_devices(self, restore_token: Optional[str] = None):
        """Select input devices with persistence support."""
        token = self._get_request_token()
        request_path = self._get_request_path(token)
        result = {"success": False}

        def on_response(response, results):
            result["success"] = response == 0
            self.loop.quit()

        self.bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=request_path,
        )

        options = {
            "handle_token": token,
            "types": dbus.UInt32(DEVICE_KEYBOARD),
            "persist_mode": dbus.UInt32(PERSIST_MODE_PERMANENT),
        }
        if restore_token:
            options["restore_token"] = restore_token

        try:
            self.remote_desktop.SelectDevices(self.session_handle, options)
            self.loop.run()
        finally:
            self.bus.remove_signal_receiver(
                on_response,
                signal_name="Response",
                dbus_interface=REQUEST_IFACE,
                path=request_path,
            )

        if not result["success"]:
            raise RuntimeError("Failed to select devices (user cancelled?)")

    def start(self) -> Optional[str]:
        """Start the session and return the new restore token."""
        token = self._get_request_token()
        request_path = self._get_request_path(token)
        result = {"success": False, "restore_token": None}

        def on_response(response, results):
            result["success"] = response == 0
            result["restore_token"] = results.get("restore_token")
            self.loop.quit()

        self.bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=request_path,
        )

        try:
            self.remote_desktop.Start(self.session_handle, "", {"handle_token": token})
            self.loop.run()
        finally:
            self.bus.remove_signal_receiver(
                on_response,
                signal_name="Response",
                dbus_interface=REQUEST_IFACE,
                path=request_path,
            )

        if not result["success"]:
            raise RuntimeError("Session start failed or was cancelled")

        self.restore_token = result["restore_token"]
        return self.restore_token

    def connect_to_is(self) -> int:
        """Get the IS file descriptor for libei."""
        options = dbus.Dictionary(signature="sv")
        fd = self.remote_desktop.ConnectToIS(self.session_handle, options)
        return fd.take()


# =============================================================================
# Typing engine
# =============================================================================


def wait_for_keyboard(ctx: EiSender, poll: select.poll, kept_refs: list) -> EiDevice:
    """Wait for a keyboard device to become available."""
    while True:
        poll.poll(500)
        ctx.dispatch()
        for event in ctx.events:
            kept_refs.append(event)

            if event.event_type == EventType.SEAT_ADDED:
                seat = event.seat
                if seat:
                    seat.bind_keyboard()
                    kept_refs.append(seat)

            elif event.event_type == EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and dev.is_keyboard():
                    kept_refs.append(dev)
                    return dev


def type_text_fast(
    ctx: EiSender,
    device: EiDevice,
    text: str,
    layout: KeyboardLayout,
    delay_ms: int = FAST_DELAY_MS,
) -> tuple[int, int]:
    """
    Type text fast with device removal rollback.

    Returns (typed_count, skipped_count).
    """
    poll = select.poll()
    poll.register(ctx.fd, select.POLLIN | select.POLLOUT)
    kept_refs = [device]
    current_device = device

    idx = 0
    last_confirmed = 0
    skipped = 0

    while idx < len(text):
        char = text[idx]

        # Check for device changes (non-blocking)
        if poll.poll(0):
            ctx.dispatch()
            for event in ctx.events:
                kept_refs.append(event)
                if event.event_type == EventType.DEVICE_REMOVED:
                    current_device = None
                elif event.event_type == EventType.DEVICE_RESUMED:
                    dev = event.device
                    if dev and dev.is_keyboard():
                        current_device = dev
                        kept_refs.append(dev)

        if current_device is None:
            # Rollback to last confirmed position
            idx = last_confirmed
            current_device = wait_for_keyboard(ctx, poll, kept_refs)
            continue

        # Look up keycode
        keycode, needs_shift = layout.get_key_info(char)
        if keycode == -1:
            skipped += 1
            idx += 1
            last_confirmed = idx
            continue

        # Type the character
        current_device.start_emulating()
        if needs_shift:
            current_device.keyboard_key(KEY_LEFTSHIFT, True)
            current_device.keyboard_key(keycode, True)
            current_device.keyboard_key(keycode, False)
            current_device.keyboard_key(KEY_LEFTSHIFT, False)
        else:
            current_device.keyboard_key(keycode, True)
            current_device.keyboard_key(keycode, False)
        current_device.frame()
        current_device.stop_emulating()

        # Wait (longer for first few chars to let Mutter settle)
        wait_time = INITIAL_SETTLE_MS if idx < 3 else delay_ms
        poll.poll(wait_time)
        ctx.dispatch()

        # Check for device removal after typing
        device_ok = True
        for event in ctx.events:
            kept_refs.append(event)
            if event.event_type == EventType.DEVICE_REMOVED:
                current_device = None
                device_ok = False
            elif event.event_type == EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and dev.is_keyboard():
                    current_device = dev
                    kept_refs.append(dev)

        if device_ok:
            last_confirmed = idx + 1
            idx += 1
        else:
            # Rollback
            idx = last_confirmed
            if current_device is None:
                current_device = wait_for_keyboard(ctx, poll, kept_refs)

    return (len(text) - skipped, skipped)


# =============================================================================
# Public API
# =============================================================================


class LibeiTyper:
    """
    High-level API for typing text via libei.

    Usage:
        typer = LibeiTyper()
        typer.connect()  # Shows permission dialog on first run
        typer.type_text("Hello, world!")
        # ... type more text as needed
    """

    def __init__(self, layout: Optional[str] = None, variant: Optional[str] = None):
        """
        Initialize the typer.

        Args:
            layout: Keyboard layout override (e.g., "us", "de"). Auto-detected if None.
            variant: Layout variant override (e.g., "dvorak"). Auto-detected if None.
        """
        self.keyboard = KeyboardLayout(layout=layout, variant=variant)
        self._session: Optional[RemoteDesktopSession] = None
        self._ctx: Optional[EiSender] = None
        self._device: Optional[EiDevice] = None
        self._poll: Optional[select.poll] = None
        self._kept_refs: list = []
        self._connected = False

    def connect(self, use_saved_token: bool = True) -> bool:
        """
        Connect to the RemoteDesktop portal.

        Args:
            use_saved_token: If True, try to use saved permissions (no dialog).

        Returns:
            True if connected successfully, False if user cancelled.
        """
        saved_token = load_restore_token() if use_saved_token else None

        try:
            self._session = RemoteDesktopSession()
            self._session.create_session()
            self._session.select_devices(restore_token=saved_token)
            new_token = self._session.start()

            if new_token:
                save_restore_token(new_token)

            is_fd = self._session.connect_to_is()
            self._ctx = EiSender.create_for_fd(is_fd, name="voicetype")

            self._poll = select.poll()
            self._poll.register(self._ctx.fd)

            self._device = wait_for_keyboard(self._ctx, self._poll, self._kept_refs)
            self._connected = True
            return True

        except RuntimeError as e:
            if "cancelled" in str(e).lower() and saved_token:
                clear_restore_token()
            raise

    def type_text(self, text: str, delay_ms: int = FAST_DELAY_MS) -> tuple[int, int]:
        """
        Type text.

        Args:
            text: The text to type.
            delay_ms: Delay between characters in milliseconds.

        Returns:
            (typed_count, skipped_count) tuple.
        """
        if not self._connected:
            raise RuntimeError("Not connected. Call connect() first.")

        return type_text_fast(self._ctx, self._device, text, self.keyboard, delay_ms)

    @property
    def layout_info(self) -> str:
        """Get human-readable layout information."""
        return (
            f"{self.keyboard.layout_name} ({self.keyboard.variant_name or 'default'})"
        )


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Production-ready libei typing for speech-to-text",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                              # Type demo text
    %(prog)s --text "Hello, world!"       # Type custom text
    %(prog)s --reset                       # Clear saved permissions
    %(prog)s --show-layout                 # Show keyboard mapping
    %(prog)s --layout us --variant dvp --save-layout  # Save Dvorak Programmer
    %(prog)s --layout de                   # Use German layout
""",
    )
    parser.add_argument(
        "--text", default="Hello from VoiceType! 123", help="Text to type"
    )
    parser.add_argument("--reset", action="store_true", help="Clear saved permissions")
    parser.add_argument(
        "--show-layout", action="store_true", help="Show keyboard layout mapping"
    )
    parser.add_argument("--layout", help="Override keyboard layout (e.g., us, de, fr)")
    parser.add_argument(
        "--variant", help="Override layout variant (e.g., dvorak, dvp, colemak)"
    )
    parser.add_argument(
        "--save-layout", action="store_true", help="Save --layout/--variant as default"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=FAST_DELAY_MS,
        help=f"Delay between chars in ms (default: {FAST_DELAY_MS})",
    )
    parser.add_argument(
        "--countdown", type=int, default=3, help="Countdown before typing (default: 3)"
    )
    args = parser.parse_args()

    if args.reset:
        clear_restore_token()
        return

    # Load saved keyboard config if no override specified
    if args.layout is None:
        saved_layout, saved_variant = load_keyboard_config()
        if saved_layout:
            args.layout = saved_layout
            args.variant = args.variant or saved_variant
            print(f"Using saved layout: {args.layout}:{args.variant or 'default'}")

    # Save layout if requested
    if args.save_layout:
        if args.layout:
            save_keyboard_config(args.layout, args.variant)
        else:
            print("Error: --save-layout requires --layout")
            return

    # Initialize keyboard layout
    keyboard = KeyboardLayout(layout=args.layout, variant=args.variant)
    print(f"Keyboard: {keyboard.layout_name} ({keyboard.variant_name or 'default'})")

    if args.show_layout:
        keyboard.print_mapping()
        return

    # Check for saved token
    saved_token = load_restore_token()
    if saved_token:
        print("Using saved permissions (no dialog)")
    else:
        print("First run - permission dialog will appear")

    # Create session
    session = RemoteDesktopSession()

    try:
        session.create_session()
        session.select_devices(restore_token=saved_token)
        new_token = session.start()

        if new_token:
            save_restore_token(new_token)
            if not saved_token:
                print(f"Permissions saved to {TOKEN_FILE}")

        is_fd = session.connect_to_is()
        ctx = EiSender.create_for_fd(is_fd, name="voicetype-demo")

        # Countdown
        print(f"\nFocus on a text editor...")
        for i in range(args.countdown, 0, -1):
            print(f"  Typing in {i}...")
            time.sleep(1)

        # Wait for device
        poll = select.poll()
        poll.register(ctx.fd)
        kept_refs: list = []
        device = wait_for_keyboard(ctx, poll, kept_refs)
        print(f"Using keyboard: {device.name}")

        # Type!
        start_time = time.perf_counter()
        typed, skipped = type_text_fast(ctx, device, args.text, keyboard, args.delay)
        elapsed = time.perf_counter() - start_time

        chars_per_sec = typed / elapsed if elapsed > 0 else 0
        print(
            f"\nTyped {typed} chars in {elapsed:.3f}s ({chars_per_sec:.1f} chars/sec)"
        )
        if skipped:
            print(f"  ({skipped} chars skipped - no keycode)")

    except RuntimeError as e:
        if "cancelled" in str(e).lower():
            print("Permission denied by user")
            if saved_token:
                print("Saved token may be expired, clearing...")
                clear_restore_token()
        else:
            raise


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
        exit_code = 130
    except Exception as e:
        print(f"Error: {e}")
        exit_code = 1

    # Use os._exit() to avoid D-Bus/GLib cleanup errors
    os._exit(exit_code)
