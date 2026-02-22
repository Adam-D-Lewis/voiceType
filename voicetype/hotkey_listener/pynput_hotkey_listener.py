import re
import threading
from typing import Any, Callable, Dict, Optional, Set

from loguru import logger

from voicetype._vendor import pynput

from .hotkey_listener import HotkeyListener

keyboard = pynput.keyboard
mouse = pynput.mouse

_MOUSE_TOKEN_RE = re.compile(r"<mouse(\d+)>", re.IGNORECASE)


class MouseButton:
    """Sentinel representing a mouse button for use in hotkey combo sets.

    Lives alongside pynput keyboard.Key / keyboard.KeyCode objects in the
    shared _pressed_keys set.
    """

    __slots__ = ("number",)

    def __init__(self, number: int):
        self.number = number

    def __eq__(self, other):
        return isinstance(other, MouseButton) and self.number == other.number

    def __hash__(self):
        return hash(("MouseButton", self.number))

    def __repr__(self):
        return f"<mouse{self.number}>"


def _pynput_button_to_number(button: Any) -> Optional[int]:
    """Extract the integer button number from a pynput mouse.Button value."""
    # pynput Button enum: left=1, middle=2, right=3 on X11
    # Extra buttons (8, 9, ...) are created dynamically with matching values
    try:
        val = button.value
        if isinstance(val, int):
            return val
    except AttributeError:
        pass
    # Fallback: parse digits from the name (e.g. "x1" -> 1, "button8" -> 8)
    name = getattr(button, "name", str(button))
    match = re.search(r"(\d+)", name)
    if match:
        return int(match.group(1))
    return None


def _parse_hotkey(hotkey_str: str):
    """Parse a hotkey string that may contain <mouseN> tokens.

    Returns:
        (combo_set, has_mouse_buttons) where combo_set contains a mix of
        keyboard.Key/KeyCode objects and MouseButton sentinels.
    """
    mouse_buttons: Set[MouseButton] = set()
    keyboard_tokens = []

    for token in hotkey_str.split("+"):
        token = token.strip()
        match = _MOUSE_TOKEN_RE.fullmatch(token)
        if match:
            mouse_buttons.add(MouseButton(int(match.group(1))))
        else:
            keyboard_tokens.append(token)

    keyboard_keys: set = set()
    if keyboard_tokens:
        keyboard_str = "+".join(keyboard_tokens)
        keyboard_keys = set(keyboard.HotKey.parse(keyboard_str))

    return keyboard_keys | mouse_buttons, bool(mouse_buttons)


class PynputHotkeyListener(HotkeyListener):
    """Cross-platform hotkey listener implementation using pynput.

    This class handles keyboard and mouse button events to detect when
    specific hotkey combinations are pressed and released. Supports
    multiple hotkeys simultaneously, including mouse buttons via the
    <mouseN> syntax (e.g. <mouse8> for thumb button).

    Works on Windows, Linux (X11), and macOS.
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[str], None]] = None,
        on_hotkey_release: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(on_hotkey_press, on_hotkey_release)
        # hotkey_string -> parsed key/button set
        self._hotkey_combos: Dict[str, set] = {}
        self._keyboard_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None
        self._pressed_keys: set = set()
        # Track press state per hotkey string
        self._hotkey_pressed: Dict[str, bool] = {}
        self._needs_mouse: bool = False
        self._lock = threading.Lock()

    def add_hotkey(self, hotkey: str, name: str = "") -> None:
        try:
            combo, has_mouse = _parse_hotkey(hotkey)
        except ValueError as e:
            logger.error(f"Error parsing hotkey '{hotkey}': {e}")
            raise ValueError(f"Invalid hotkey format: {hotkey}") from e

        self._hotkey_combos[hotkey] = combo
        self._hotkey_pressed[hotkey] = False
        if has_mouse:
            self._needs_mouse = True
        logger.info(f"Hotkey added: {hotkey} -> {combo}")

    def clear_hotkeys(self) -> None:
        self._hotkey_combos.clear()
        self._hotkey_pressed.clear()
        self._needs_mouse = False

    # -- shared press/release logic --

    def _handle_press(self, key) -> None:
        """Common press handler for both keyboard keys and mouse buttons."""
        if not self._hotkey_combos:
            return

        with self._lock:
            self._pressed_keys.add(key)

            for hotkey_str, combo in self._hotkey_combos.items():
                if not self._hotkey_pressed[hotkey_str] and combo.issubset(
                    self._pressed_keys
                ):
                    logger.debug(f"Hotkey detected: {hotkey_str}")
                    self._hotkey_pressed[hotkey_str] = True
                    self._trigger_hotkey_press(hotkey_str)

    def _handle_release(self, key) -> None:
        """Common release handler for both keyboard keys and mouse buttons."""
        if not self._hotkey_combos:
            return

        with self._lock:
            for hotkey_str, combo in self._hotkey_combos.items():
                if self._hotkey_pressed[hotkey_str] and key in combo:
                    any_hotkey_key_pressed = any(
                        k in self._pressed_keys for k in combo if k != key
                    )
                    if not any_hotkey_key_pressed:
                        self._hotkey_pressed[hotkey_str] = False
                        self._trigger_hotkey_release(hotkey_str)

            self._pressed_keys.discard(key)

    # -- keyboard callbacks --

    def _on_key_press(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        if key is None:
            return
        canonical_key = self._keyboard_listener.canonical(key)
        self._handle_press(canonical_key)

    def _on_key_release(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        if key is None:
            return
        canonical_key = self._keyboard_listener.canonical(key)
        self._handle_release(canonical_key)

    # -- mouse callbacks --

    def _on_mouse_click(self, x: int, y: int, button, pressed: bool):
        btn_num = _pynput_button_to_number(button)
        if btn_num is None:
            return
        sentinel = MouseButton(btn_num)
        if pressed:
            self._handle_press(sentinel)
        else:
            self._handle_release(sentinel)

    # -- lifecycle --

    def start_listening(self) -> None:
        if self._keyboard_listener is not None and self._keyboard_listener.is_alive():
            logger.info("Listener already running.")
            return

        if not self._hotkey_combos:
            raise ValueError("No hotkeys registered before starting listener.")

        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._keyboard_listener.start()
        logger.debug(f"Keyboard listener thread: {self._keyboard_listener.ident}")

        if self._needs_mouse:
            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click,
            )
            self._mouse_listener.start()
            logger.debug(f"Mouse listener thread: {self._mouse_listener.ident}")
            logger.info("Pynput hotkey listener started (keyboard + mouse).")
        else:
            logger.info("Pynput hotkey listener started (keyboard only).")

    def stop_listening(self) -> None:
        if self._keyboard_listener and self._keyboard_listener.is_alive():
            logger.info("Stopping pynput keyboard listener...")
            self._keyboard_listener.stop()
            self._keyboard_listener.join()
            logger.info("Pynput keyboard listener stopped.")

        if self._mouse_listener and self._mouse_listener.is_alive():
            logger.info("Stopping pynput mouse listener...")
            self._mouse_listener.stop()
            self._mouse_listener.join()
            logger.info("Pynput mouse listener stopped.")

        self._keyboard_listener = None
        self._mouse_listener = None
        self._pressed_keys.clear()
        for k in self._hotkey_pressed:
            self._hotkey_pressed[k] = False
