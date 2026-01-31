import threading
from typing import Callable, Dict, Optional, Set

from loguru import logger

from voicetype._vendor import pynput

from .hotkey_listener import HotkeyListener

keyboard = pynput.keyboard


class PynputHotkeyListener(HotkeyListener):
    """Cross-platform hotkey listener implementation using pynput.

    This class handles keyboard events to detect when specific hotkey
    combinations are pressed and released. Supports multiple hotkeys
    simultaneously. Works on Windows, Linux (X11), and macOS.
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[str], None]] = None,
        on_hotkey_release: Optional[Callable[[str], None]] = None,
    ):
        super().__init__(on_hotkey_press, on_hotkey_release)
        # hotkey_string -> parsed key set
        self._hotkey_combos: Dict[str, Set[keyboard.Key | keyboard.KeyCode]] = {}
        self._listener: Optional[keyboard.Listener] = None
        self._pressed_keys: Set[keyboard.Key | keyboard.KeyCode] = set()
        # Track press state per hotkey string
        self._hotkey_pressed: Dict[str, bool] = {}
        self._lock = threading.Lock()

    def add_hotkey(self, hotkey: str, name: str = "") -> None:
        try:
            combo = set(keyboard.HotKey.parse(hotkey))
            self._hotkey_combos[hotkey] = combo
            self._hotkey_pressed[hotkey] = False
            logger.info(f"Hotkey added: {hotkey} -> {combo}")
        except ValueError as e:
            logger.error(f"Error parsing hotkey '{hotkey}': {e}")
            raise ValueError(f"Invalid hotkey format: {hotkey}") from e

    def clear_hotkeys(self) -> None:
        self._hotkey_combos.clear()
        self._hotkey_pressed.clear()

    def _on_key_press(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        if key is None or not self._hotkey_combos:
            return

        with self._lock:
            canonical_key = self._listener.canonical(key)
            self._pressed_keys.add(canonical_key)

            for hotkey_str, combo in self._hotkey_combos.items():
                if not self._hotkey_pressed[hotkey_str] and combo.issubset(
                    self._pressed_keys
                ):
                    logger.debug(f"Hotkey detected: {hotkey_str}")
                    self._hotkey_pressed[hotkey_str] = True
                    self._trigger_hotkey_press(hotkey_str)

    def _on_key_release(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        if key is None or not self._hotkey_combos:
            return

        canonical_key = self._listener.canonical(key)

        with self._lock:
            for hotkey_str, combo in self._hotkey_combos.items():
                if self._hotkey_pressed[hotkey_str] and canonical_key in combo:
                    any_hotkey_key_pressed = any(
                        k in self._pressed_keys for k in combo if k != canonical_key
                    )
                    if not any_hotkey_key_pressed:
                        self._hotkey_pressed[hotkey_str] = False
                        self._trigger_hotkey_release(hotkey_str)

            if canonical_key in self._pressed_keys:
                self._pressed_keys.remove(canonical_key)

    def start_listening(self) -> None:
        if self._listener is not None and self._listener.is_alive():
            logger.info("Listener already running.")
            return

        if not self._hotkey_combos:
            raise ValueError("No hotkeys registered before starting listener.")

        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )

        self._listener.start()
        logger.debug(f"Current thread: {threading.get_ident()}")
        logger.debug(f"Listener thread: {self._listener.ident}")
        assert (
            threading.get_ident() != self._listener.ident
        ), "Listener thread should not be the main thread."
        logger.info("Pynput hotkey listener started.")

    def stop_listening(self) -> None:
        if self._listener and self._listener.is_alive():
            logger.info("Stopping pynput hotkey listener...")
            self._listener.stop()
            assert (
                threading.get_ident() != self._listener.ident
            ), "Listener thread should not be the main thread."
            self._listener.join()
            logger.info("Pynput hotkey listener stopped.")

        self._listener = None
        self._pressed_keys.clear()
        for k in self._hotkey_pressed:
            self._hotkey_pressed[k] = False
