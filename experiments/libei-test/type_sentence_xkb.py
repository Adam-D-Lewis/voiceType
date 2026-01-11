#!/usr/bin/env python3
"""
Optimized sentence typing using libei with dynamic XKB keyboard layout detection.

Instead of hardcoding keyboard layouts, this uses libxkbcommon to:
1. Load the current keyboard layout from system settings
2. Build a reverse lookup table: character → (keycode, needs_shift)
3. Type using the correct keycodes for any layout
"""

import ctypes
import ctypes.util
import os
import select
import subprocess
import time
from typing import Optional

import snegg.ei as ei
import snegg.oeffis as oeffis

# ============================================================================
# libxkbcommon ctypes bindings
# ============================================================================

_xkb_path = ctypes.util.find_library("xkbcommon")
if not _xkb_path:
    raise ImportError("Could not find libxkbcommon library")
_xkb = ctypes.CDLL(_xkb_path)


# Opaque pointer types
class XkbContextPtr(ctypes.c_void_p):
    pass


class XkbKeymapPtr(ctypes.c_void_p):
    pass


class XkbStatePtr(ctypes.c_void_p):
    pass


# Constants
XKB_CONTEXT_NO_FLAGS = 0
XKB_KEYMAP_COMPILE_NO_FLAGS = 0
XKB_KEYMAP_FORMAT_TEXT_V1 = 1

# Modifier indices (standard XKB)
XKB_MOD_NAME_SHIFT = b"Shift"
XKB_MOD_NAME_CAPS = b"Lock"
XKB_MOD_NAME_CTRL = b"Control"
XKB_MOD_NAME_ALT = b"Mod1"

# Key state
XKB_KEY_UP = 0
XKB_KEY_DOWN = 1

# Function signatures
_xkb.xkb_context_new.argtypes = [ctypes.c_int]
_xkb.xkb_context_new.restype = XkbContextPtr

_xkb.xkb_context_unref.argtypes = [XkbContextPtr]
_xkb.xkb_context_unref.restype = None


# Rule names structure for xkb_keymap_new_from_names
class XkbRuleNames(ctypes.Structure):
    _fields_ = [
        ("rules", ctypes.c_char_p),
        ("model", ctypes.c_char_p),
        ("layout", ctypes.c_char_p),
        ("variant", ctypes.c_char_p),
        ("options", ctypes.c_char_p),
    ]


_xkb.xkb_keymap_new_from_names.argtypes = [
    XkbContextPtr,
    ctypes.POINTER(XkbRuleNames),
    ctypes.c_int,
]
_xkb.xkb_keymap_new_from_names.restype = XkbKeymapPtr

_xkb.xkb_keymap_unref.argtypes = [XkbKeymapPtr]
_xkb.xkb_keymap_unref.restype = None

_xkb.xkb_keymap_min_keycode.argtypes = [XkbKeymapPtr]
_xkb.xkb_keymap_min_keycode.restype = ctypes.c_uint32

_xkb.xkb_keymap_max_keycode.argtypes = [XkbKeymapPtr]
_xkb.xkb_keymap_max_keycode.restype = ctypes.c_uint32

_xkb.xkb_state_new.argtypes = [XkbKeymapPtr]
_xkb.xkb_state_new.restype = XkbStatePtr

_xkb.xkb_state_unref.argtypes = [XkbStatePtr]
_xkb.xkb_state_unref.restype = None

_xkb.xkb_state_key_get_utf8.argtypes = [
    XkbStatePtr,
    ctypes.c_uint32,
    ctypes.c_char_p,
    ctypes.c_size_t,
]
_xkb.xkb_state_key_get_utf8.restype = ctypes.c_int

_xkb.xkb_state_update_key.argtypes = [XkbStatePtr, ctypes.c_uint32, ctypes.c_int]
_xkb.xkb_state_update_key.restype = ctypes.c_uint32

_xkb.xkb_keymap_mod_get_index.argtypes = [XkbKeymapPtr, ctypes.c_char_p]
_xkb.xkb_keymap_mod_get_index.restype = ctypes.c_uint32


# ============================================================================
# XKB Keyboard Layout Handler
# ============================================================================

# evdev keycode offset (XKB keycodes = evdev + 8)
EVDEV_OFFSET = 8

# Standard modifier keycodes (evdev)
KEY_LEFTSHIFT = 42
KEY_RIGHTSHIFT = 54
KEY_LEFTCTRL = 29
KEY_LEFTALT = 56


def get_current_xkb_settings() -> tuple[str, str, str, str, str]:
    """Get current XKB settings from the system.

    Returns: (rules, model, layout, variant, options)
    """
    # Try setxkbmap first (works on both X11 and Wayland with XWayland)
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

            # For multiple layouts, take the first one
            layout = settings.get("layout", "us")
            variant = settings.get("variant", "")

            # Handle comma-separated layouts/variants
            if "," in layout:
                layouts = layout.split(",")
                variants = variant.split(",") if variant else [""] * len(layouts)
                # Use first layout
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

    # Try environment variables
    layout = os.environ.get("XKB_DEFAULT_LAYOUT", "us")
    variant = os.environ.get("XKB_DEFAULT_VARIANT", "")

    return ("evdev", "pc105", layout, variant, "")


class XkbKeyboardLayout:
    """Manages XKB keyboard layout and provides character → keycode mapping."""

    def __init__(self, layout: Optional[str] = None, variant: Optional[str] = None):
        """Initialize with optional layout override.

        If layout is None, auto-detects from system settings.
        """
        self._ctx: Optional[XkbContextPtr] = None
        self._keymap: Optional[XkbKeymapPtr] = None
        self._state: Optional[XkbStatePtr] = None

        # Character to (evdev_keycode, needs_shift) mapping
        self._char_map: dict[str, tuple[int, bool]] = {}

        # Get settings
        if layout is None:
            rules, model, layout, variant, options = get_current_xkb_settings()
        else:
            rules, model, options = "evdev", "pc105", ""
            variant = variant or ""

        print(f"XKB Layout: {layout} (variant: {variant or 'none'})")

        self._init_xkb(rules, model, layout, variant or "", options)
        self._build_char_map()

    def _init_xkb(
        self, rules: str, model: str, layout: str, variant: str, options: str
    ):
        """Initialize xkbcommon context and keymap."""
        self._ctx = _xkb.xkb_context_new(XKB_CONTEXT_NO_FLAGS)
        if not self._ctx:
            raise RuntimeError("Failed to create XKB context")

        # Set up rule names
        names = XkbRuleNames(
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

        self._state = _xkb.xkb_state_new(self._keymap)
        if not self._state:
            raise RuntimeError("Failed to create XKB state")

    def _get_char_for_key(self, xkb_keycode: int, with_shift: bool = False) -> str:
        """Get the character produced by a keycode (optionally with shift)."""
        # Create a fresh state for this query
        state = _xkb.xkb_state_new(self._keymap)
        if not state:
            return ""

        try:
            if with_shift:
                # Press shift (XKB keycode for left shift = evdev + 8)
                _xkb.xkb_state_update_key(
                    state, KEY_LEFTSHIFT + EVDEV_OFFSET, XKB_KEY_DOWN
                )

            # Get the character
            buf = ctypes.create_string_buffer(8)
            size = _xkb.xkb_state_key_get_utf8(state, xkb_keycode, buf, 8)

            if size > 0:
                return buf.value.decode("utf-8")
            return ""
        finally:
            _xkb.xkb_state_unref(state)

    def _build_char_map(self):
        """Build mapping from characters to (evdev_keycode, needs_shift)."""
        min_kc = _xkb.xkb_keymap_min_keycode(self._keymap)
        max_kc = _xkb.xkb_keymap_max_keycode(self._keymap)

        for xkb_kc in range(min_kc, max_kc + 1):
            evdev_kc = xkb_kc - EVDEV_OFFSET

            # Skip invalid evdev keycodes
            if evdev_kc < 1 or evdev_kc > 255:
                continue

            # Get character without shift
            char = self._get_char_for_key(xkb_kc, with_shift=False)
            if char and char not in self._char_map:
                self._char_map[char] = (evdev_kc, False)

            # Get character with shift
            char_shift = self._get_char_for_key(xkb_kc, with_shift=True)
            if char_shift and char_shift != char and char_shift not in self._char_map:
                self._char_map[char_shift] = (evdev_kc, True)

        # Always ensure space, enter, tab are mapped
        if " " not in self._char_map:
            self._char_map[" "] = (57, False)  # KEY_SPACE
        if "\n" not in self._char_map:
            self._char_map["\n"] = (28, False)  # KEY_ENTER
        if "\t" not in self._char_map:
            self._char_map["\t"] = (15, False)  # KEY_TAB

    def get_key_info(self, char: str) -> tuple[int, bool]:
        """Get (evdev_keycode, needs_shift) for a character.

        Returns (-1, False) if character not found.
        """
        return self._char_map.get(char, (-1, False))

    def __del__(self):
        if self._state:
            _xkb.xkb_state_unref(self._state)
        if self._keymap:
            _xkb.xkb_keymap_unref(self._keymap)
        if self._ctx:
            _xkb.xkb_context_unref(self._ctx)

    def print_mapping(self, chars: str = "abcdefghijklmnopqrstuvwxyz0123456789 .,!?"):
        """Print the keycode mapping for debugging."""
        print("\nCharacter → Keycode mapping:")
        for char in chars:
            kc, shift = self.get_key_info(char)
            shift_str = "+Shift" if shift else ""
            if kc != -1:
                print(f"  '{char}' → keycode {kc}{shift_str}")
            else:
                print(f"  '{char}' → NOT FOUND")


# ============================================================================
# Typing Functions
# ============================================================================


def wait_for_portal() -> oeffis.Oeffis:
    """Connect to the RemoteDesktop portal and wait for IS connection."""
    print("Connecting to RemoteDesktop portal...")
    print("A dialog will appear asking you to approve input device access.")

    portal = oeffis.Oeffis.create(devices=oeffis.DeviceType.KEYBOARD)

    poll = select.poll()
    poll.register(portal.fd)

    while poll.poll():
        try:
            if portal.dispatch():
                print("Connected to IS!")
                return portal
        except oeffis.SessionClosedError as e:
            print(f"Session closed: {e.message}")
            raise SystemExit(1)
        except oeffis.DisconnectedError as e:
            print(f"Disconnected: {e.message}")
            raise SystemExit(1)

    raise RuntimeError("Failed to connect to portal")


def type_key_fast(device: ei.Device, keycode: int, needs_shift: bool):
    """Type a single key without start/stop emulating (caller manages session)."""
    if needs_shift:
        device.keyboard_key(KEY_LEFTSHIFT, True)
        device.keyboard_key(keycode, True)
        device.keyboard_key(keycode, False)
        device.keyboard_key(KEY_LEFTSHIFT, False)
    else:
        device.keyboard_key(keycode, True)
        device.keyboard_key(keycode, False)


def wait_for_device(ctx: ei.Sender, poll: select.poll, kept_refs: list) -> ei.Device:
    """Wait for a keyboard device to become available."""
    print("Waiting for keyboard device...")
    while True:
        poll.poll(500)
        ctx.dispatch()
        for event in ctx.events:
            kept_refs.append(event)

            if event.event_type == ei.EventType.SEAT_ADDED:
                seat = event.seat
                if seat:
                    print(f"  Seat added: {seat.name}")
                    seat.bind((ei.DeviceCapability.KEYBOARD,))
                    kept_refs.append(seat)

            elif event.event_type == ei.EventType.DEVICE_ADDED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    print(f"  Keyboard device found: {dev.name}")
                    kept_refs.append(dev)

            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    print(f"  Device ready: {dev.name}")
                    kept_refs.append(dev)
                    return dev


def type_sentence_fast(
    ctx: ei.Sender,
    device: ei.Device,
    text: str,
    layout: XkbKeyboardLayout,
    delay_ms: int = 5,
):
    """Type text fast with XKB-based keycode lookup."""
    print(f"Typing {len(text)} chars: {text[:50]}{'...' if len(text) > 50 else ''}")

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
                if event.event_type == ei.EventType.DEVICE_REMOVED:
                    current_device = None
                elif event.event_type == ei.EventType.DEVICE_RESUMED:
                    dev = event.device
                    if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                        current_device = dev
                        kept_refs.append(dev)

        if current_device is None:
            idx = last_confirmed
            current_device = wait_for_device(ctx, poll, kept_refs)
            continue

        # Look up keycode for this character
        keycode, needs_shift = layout.get_key_info(char)
        if keycode == -1:
            print(f"  Warning: No keycode for '{char}' (U+{ord(char):04X}), skipping")
            skipped += 1
            idx += 1
            last_confirmed = idx
            continue

        # Type one character
        current_device.start_emulating()
        type_key_fast(current_device, keycode, needs_shift)
        current_device.frame()
        current_device.stop_emulating()

        # Wait longer for first few chars
        wait_time = 50 if idx < 3 else delay_ms

        poll.poll(wait_time)
        ctx.dispatch()

        # Check for device removal
        device_ok = True
        for event in ctx.events:
            kept_refs.append(event)
            if event.event_type == ei.EventType.DEVICE_REMOVED:
                current_device = None
                device_ok = False
            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    current_device = dev
                    kept_refs.append(dev)

        if device_ok:
            last_confirmed = idx + 1
            idx += 1
        else:
            idx = last_confirmed
            if current_device is None:
                current_device = wait_for_device(ctx, poll, kept_refs)

    print(f"Done typing! ({skipped} chars skipped)")


def main():
    import sys

    # Parse arguments
    show_mapping = "--show-mapping" in sys.argv
    layout_override = None
    variant_override = None

    for i, arg in enumerate(sys.argv):
        if arg == "--layout" and i + 1 < len(sys.argv):
            layout_override = sys.argv[i + 1]
        if arg == "--variant" and i + 1 < len(sys.argv):
            variant_override = sys.argv[i + 1]

    # Initialize XKB layout (auto-detect or use override)
    layout = XkbKeyboardLayout(layout=layout_override, variant=variant_override)

    if show_mapping:
        layout.print_mapping()
        return

    # Test sentence
    sentence = "Hello from libei!" * 3

    # Connect to portal
    portal = wait_for_portal()

    # Create libei Sender context
    ctx = ei.Sender.create_for_fd(fd=portal.is_fd, name="libei-xkb-test")

    print("\nYou have 3 seconds to focus on a text editor...")
    time.sleep(3)

    kept_refs: list = []
    poll = select.poll()
    poll.register(ctx.fd)

    # Wait for device
    device = wait_for_device(ctx, poll, kept_refs)

    # Time the typing
    start_time = time.perf_counter()
    type_sentence_fast(ctx, device, sentence, layout)
    elapsed = time.perf_counter() - start_time

    chars_per_sec = len(sentence) / elapsed
    print(
        f"\nTyped {len(sentence)} chars in {elapsed:.3f}s ({chars_per_sec:.1f} chars/sec)"
    )


if __name__ == "__main__":
    print("XKB Dynamic Keyboard Layout Test")
    print("=" * 40)
    print("Usage:")
    print("  python type_sentence_xkb.py              # Auto-detect layout")
    print("  python type_sentence_xkb.py --show-mapping  # Show char→keycode map")
    print("  python type_sentence_xkb.py --layout us --variant dvp  # Override layout")
    print()

    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        raise
