"""Evdev-based keyboard listener for Linux.

This module provides direct evdev access for keyboard events, bypassing pynput's
uinput backend which requires `dumpkeys` (doesn't work in graphical environments).

This listener reads directly from /dev/input/event* devices and works on both
X11 and Wayland, but requires root access.
"""

import select
import threading
from typing import Callable, Dict, List, Optional, Set

import evdev
from evdev import ecodes
from loguru import logger

# Map pynput-style hotkey names to evdev key codes
HOTKEY_MAP: Dict[str, int] = {
    # Special keys
    "<pause>": ecodes.KEY_PAUSE,
    "<break>": ecodes.KEY_PAUSE,  # Pause/Break is the same key
    "<esc>": ecodes.KEY_ESC,
    "<escape>": ecodes.KEY_ESC,
    "<tab>": ecodes.KEY_TAB,
    "<caps_lock>": ecodes.KEY_CAPSLOCK,
    "<space>": ecodes.KEY_SPACE,
    "<enter>": ecodes.KEY_ENTER,
    "<return>": ecodes.KEY_ENTER,
    "<backspace>": ecodes.KEY_BACKSPACE,
    "<delete>": ecodes.KEY_DELETE,
    "<insert>": ecodes.KEY_INSERT,
    "<home>": ecodes.KEY_HOME,
    "<end>": ecodes.KEY_END,
    "<page_up>": ecodes.KEY_PAGEUP,
    "<page_down>": ecodes.KEY_PAGEDOWN,
    "<up>": ecodes.KEY_UP,
    "<down>": ecodes.KEY_DOWN,
    "<left>": ecodes.KEY_LEFT,
    "<right>": ecodes.KEY_RIGHT,
    # Modifiers
    "<shift>": ecodes.KEY_LEFTSHIFT,
    "<shift_l>": ecodes.KEY_LEFTSHIFT,
    "<shift_r>": ecodes.KEY_RIGHTSHIFT,
    "<ctrl>": ecodes.KEY_LEFTCTRL,
    "<ctrl_l>": ecodes.KEY_LEFTCTRL,
    "<ctrl_r>": ecodes.KEY_RIGHTCTRL,
    "<alt>": ecodes.KEY_LEFTALT,
    "<alt_l>": ecodes.KEY_LEFTALT,
    "<alt_r>": ecodes.KEY_RIGHTALT,
    "<alt_gr>": ecodes.KEY_RIGHTALT,
    "<cmd>": ecodes.KEY_LEFTMETA,
    "<cmd_l>": ecodes.KEY_LEFTMETA,
    "<cmd_r>": ecodes.KEY_RIGHTMETA,
    "<super>": ecodes.KEY_LEFTMETA,
    "<super_l>": ecodes.KEY_LEFTMETA,
    "<super_r>": ecodes.KEY_RIGHTMETA,
    # Function keys
    "<f1>": ecodes.KEY_F1,
    "<f2>": ecodes.KEY_F2,
    "<f3>": ecodes.KEY_F3,
    "<f4>": ecodes.KEY_F4,
    "<f5>": ecodes.KEY_F5,
    "<f6>": ecodes.KEY_F6,
    "<f7>": ecodes.KEY_F7,
    "<f8>": ecodes.KEY_F8,
    "<f9>": ecodes.KEY_F9,
    "<f10>": ecodes.KEY_F10,
    "<f11>": ecodes.KEY_F11,
    "<f12>": ecodes.KEY_F12,
    # Print/Scroll/Pause
    "<print_screen>": ecodes.KEY_SYSRQ,
    "<scroll_lock>": ecodes.KEY_SCROLLLOCK,
    "<num_lock>": ecodes.KEY_NUMLOCK,
    # Media keys
    "<media_play_pause>": ecodes.KEY_PLAYPAUSE,
    "<media_volume_mute>": ecodes.KEY_MUTE,
    "<media_volume_down>": ecodes.KEY_VOLUMEDOWN,
    "<media_volume_up>": ecodes.KEY_VOLUMEUP,
    "<media_previous>": ecodes.KEY_PREVIOUSSONG,
    "<media_next>": ecodes.KEY_NEXTSONG,
}

# Add letter keys a-z
for i, letter in enumerate("abcdefghijklmnopqrstuvwxyz"):
    HOTKEY_MAP[letter] = ecodes.KEY_A + i

# Add number keys 0-9
HOTKEY_MAP["0"] = ecodes.KEY_0
for i in range(1, 10):
    HOTKEY_MAP[str(i)] = ecodes.KEY_1 + (i - 1)


def parse_hotkey(hotkey_str: str) -> Set[int]:
    """Parse a pynput-style hotkey string into a set of evdev key codes.

    Args:
        hotkey_str: Hotkey string like "<pause>", "<ctrl>+<alt>+r", etc.

    Returns:
        Set of evdev key codes that make up the hotkey combination.

    Raises:
        ValueError: If any key in the hotkey string is not recognized.
    """
    keys = set()
    # Split by + for combinations like <ctrl>+<alt>+r
    parts = hotkey_str.lower().split("+")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part in HOTKEY_MAP:
            keys.add(HOTKEY_MAP[part])
        else:
            raise ValueError(f"Unknown key: {part}")

    return keys


def find_keyboard_devices() -> List[evdev.InputDevice]:
    """Find all keyboard input devices.

    Returns:
        List of evdev InputDevice objects that are keyboards.
    """
    keyboards = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            caps = device.capabilities()
            # Check if device has EV_KEY capability with letter keys
            if ecodes.EV_KEY in caps:
                key_codes = caps[ecodes.EV_KEY]
                # Check for common letter keys (KEY_A through KEY_Z)
                if any(ecodes.KEY_A <= k <= ecodes.KEY_Z for k in key_codes):
                    keyboards.append(device)
                    logger.debug(f"Found keyboard: {device.name} at {device.path}")
                else:
                    device.close()
            else:
                device.close()
        except (OSError, PermissionError) as e:
            logger.debug(f"Cannot open {path}: {e}")

    return keyboards


class EvdevKeyboardListener:
    """Direct evdev-based keyboard listener.

    This listener reads keyboard events directly from /dev/input/event* devices,
    bypassing pynput's uinput backend which requires dumpkeys.

    Works on both X11 and Wayland, but requires root access.
    """

    def __init__(
        self,
        on_press: Optional[Callable[[int], None]] = None,
        on_release: Optional[Callable[[int], None]] = None,
    ):
        """Initialize the listener.

        Args:
            on_press: Callback when a key is pressed. Receives evdev key code.
            on_release: Callback when a key is released. Receives evdev key code.
        """
        self.on_press = on_press
        self.on_release = on_release
        self._devices: List[evdev.InputDevice] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_pipe_r: Optional[int] = None
        self._stop_pipe_w: Optional[int] = None

    def start(self) -> None:
        """Start listening for keyboard events."""
        if self._running:
            logger.warning("Listener already running")
            return

        self._devices = find_keyboard_devices()
        if not self._devices:
            raise RuntimeError("No keyboard devices found")

        logger.info(f"Listening on {len(self._devices)} keyboard device(s)")

        # Create a pipe for signaling stop
        self._stop_pipe_r, self._stop_pipe_w = self._create_pipe()

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _create_pipe(self):
        """Create a pipe for stop signaling."""
        import os

        r, w = os.pipe()
        return r, w

    def stop(self) -> None:
        """Stop listening for keyboard events."""
        self._running = False

        # Signal the thread to stop
        if self._stop_pipe_w is not None:
            import os

            try:
                os.write(self._stop_pipe_w, b"x")
            except OSError:
                pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        # Close devices
        for device in self._devices:
            try:
                device.close()
            except Exception:
                pass
        self._devices = []

        # Close pipe
        import os

        if self._stop_pipe_r is not None:
            try:
                os.close(self._stop_pipe_r)
            except OSError:
                pass
            self._stop_pipe_r = None
        if self._stop_pipe_w is not None:
            try:
                os.close(self._stop_pipe_w)
            except OSError:
                pass
            self._stop_pipe_w = None

        logger.info("Evdev listener stopped")

    def _run(self) -> None:
        """Main event loop."""
        fds = {dev.fd: dev for dev in self._devices}
        # Add the stop pipe to the file descriptors we're watching
        stop_fd = self._stop_pipe_r

        try:
            while self._running:
                # Wait for events with timeout
                all_fds = list(fds.keys()) + ([stop_fd] if stop_fd else [])
                r, _, _ = select.select(all_fds, [], [], 0.5)

                for fd in r:
                    if fd == stop_fd:
                        # Stop signal received
                        return

                    device = fds.get(fd)
                    if device is None:
                        continue

                    try:
                        for event in device.read():
                            if event.type == ecodes.EV_KEY:
                                if event.value == 1:  # Key down
                                    if self.on_press:
                                        self.on_press(event.code)
                                elif event.value == 0:  # Key up
                                    if self.on_release:
                                        self.on_release(event.code)
                                # event.value == 2 is key repeat, we ignore it
                    except Exception as e:
                        if self._running:
                            logger.error(f"Error reading from device: {e}")
        except Exception as e:
            if self._running:
                logger.error(f"Listener error: {e}")


class EvdevHotkeyListener:
    """Hotkey listener using direct evdev access.

    Detects when a specific hotkey combination is pressed/released and
    calls the appropriate callbacks.
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[], None]] = None,
        on_hotkey_release: Optional[Callable[[], None]] = None,
    ):
        """Initialize the hotkey listener.

        Args:
            on_hotkey_press: Callback when hotkey is pressed.
            on_hotkey_release: Callback when hotkey is released.
        """
        self.on_hotkey_press = on_hotkey_press
        self.on_hotkey_release = on_hotkey_release
        self._hotkey_codes: Set[int] = set()
        self._pressed_keys: Set[int] = set()
        self._hotkey_active = False
        self._lock = threading.Lock()
        self._listener = EvdevKeyboardListener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )

    def set_hotkey(self, hotkey: str) -> None:
        """Set the hotkey to listen for.

        Args:
            hotkey: Hotkey string like "<pause>", "<ctrl>+<alt>+r", etc.
        """
        self._hotkey_codes = parse_hotkey(hotkey)
        logger.info(f"Hotkey set to: {hotkey} -> codes {self._hotkey_codes}")

    def start(self) -> None:
        """Start listening for the hotkey."""
        if not self._hotkey_codes:
            raise ValueError("Hotkey must be set before starting")
        self._listener.start()

    def stop(self) -> None:
        """Stop listening."""
        self._listener.stop()

    def _on_key_press(self, key_code: int) -> None:
        """Handle key press event."""
        with self._lock:
            self._pressed_keys.add(key_code)

            # Check if hotkey combination is now pressed
            if not self._hotkey_active and self._hotkey_codes.issubset(
                self._pressed_keys
            ):
                self._hotkey_active = True
                logger.debug(f"Hotkey activated (pressed keys: {self._pressed_keys})")
                if self.on_hotkey_press:
                    self.on_hotkey_press()

    def _on_key_release(self, key_code: int) -> None:
        """Handle key release event."""
        with self._lock:
            # Check if a hotkey key was released while hotkey is active
            if self._hotkey_active and key_code in self._hotkey_codes:
                # Check if any other hotkey keys are still pressed
                remaining_hotkey_keys = self._hotkey_codes - {key_code}
                still_pressed = remaining_hotkey_keys & self._pressed_keys
                if not still_pressed:
                    self._hotkey_active = False
                    logger.debug("Hotkey deactivated")
                    if self.on_hotkey_release:
                        self.on_hotkey_release()

            self._pressed_keys.discard(key_code)
