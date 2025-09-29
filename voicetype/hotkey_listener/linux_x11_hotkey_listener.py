import threading
from typing import Callable, Optional, Set

from loguru import logger

from voicetype._vendor import pynput

from .hotkey_listener import HotkeyListener

keyboard = pynput.keyboard


class LinuxX11HotkeyListener(HotkeyListener):
    """Hotkey listener implementation for Linux X11 using pynput.

    This class handles keyboard events to detect when a specific hotkey
    combination is pressed and released.
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[], None]] = None,
        on_hotkey_release: Optional[Callable[[], None]] = None,
    ):
        """Initialize the Linux X11 hotkey listener.

        Args:
            on_press: Callback function to execute when the hotkey is pressed.
            on_release: Callback function to execute when the hotkey is released.

        """
        super().__init__(on_hotkey_press, on_hotkey_release)
        self._hotkey_combination: Optional[Set[keyboard.Key | keyboard.KeyCode]] = None
        self._listener: Optional[keyboard.Listener] = None
        self._pressed_keys: Set[keyboard.Key | keyboard.KeyCode] = set()
        self._hotkey_pressed: bool = False
        self._lock = threading.Lock()

    def set_hotkey(self, hotkey: str) -> None:
        """Sets the hotkey combination to listen for.

        Args:
            hotkey: A string representation of the hotkey (e.g., "<ctrl>+<alt>+x").
                   Uses pynput's format.

        Raises:
            ValueError: If the hotkey string cannot be parsed.

        """
        try:
            self._hotkey_combination = set(keyboard.HotKey.parse(hotkey))
            logger.info(f"Hotkey set to: {hotkey} -> {self._hotkey_combination}")
        except ValueError as e:
            logger.error(f"Error parsing hotkey '{hotkey}': {e}")
            self._hotkey_combination = None
            raise ValueError(f"Invalid hotkey format: {hotkey}") from e

    def _on_key_press(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        """Internal handler for key press events.

        Args:
            key: The key that was pressed.

        """
        if key is None or self._hotkey_combination is None:
            return

        with self._lock:
            # Ensure key equality works despite modifier state
            canonical_key = self._listener.canonical(key)
            self._pressed_keys.add(canonical_key)

            if not self._hotkey_pressed and self._hotkey_combination.issubset(
                self._pressed_keys,
            ):
                logger.debug(f"Hotkey detected: {canonical_key}")
                self._hotkey_pressed = True
                self._trigger_hotkey_press()

    def _on_key_release(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        """Internal handler for key release events.

        Args:
            key: The key that was released.

        """
        if key is None or self._hotkey_combination is None:
            return

        canonical_key = self._listener.canonical(key)

        with self._lock:
            # Check if the released key was part of the hotkey combination
            # and if the hotkey was previously considered pressed
            if self._hotkey_pressed and canonical_key in self._hotkey_combination:
                # Check if any key from the hotkey combo is still pressed
                # This handles cases where modifiers are released after the main key
                any_hotkey_key_pressed = any(
                    k in self._pressed_keys
                    for k in self._hotkey_combination
                    if k != canonical_key
                )
                if not any_hotkey_key_pressed:
                    self._hotkey_pressed = False
                    self._trigger_hotkey_release()

            # Remove the key from the set of pressed keys
            if canonical_key in self._pressed_keys:
                self._pressed_keys.remove(canonical_key)

    def start_listening(self) -> None:
        """Starts the hotkey listener.

        Raises:
            ValueError: If hotkey is not set before starting listener.

        """
        if self._listener is not None and self._listener.is_alive():
            logger.info("Listener already running.")
            return

        if self._hotkey_combination is None:
            raise ValueError("Hotkey not set before starting listener.")

        # Create and initialize the keyboard listener
        # Note: pynput might require DISPLAY environment variable to be set
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
            # Explicitly setting suppress=False might be needed depending on environment
            # suppress=False # Try this if keys are blocked system-wide
        )

        # Start the listener's internal thread
        self._listener.start()
        logger.debug(f"Current thread: {threading.get_ident()}")
        logger.debug(f"Listener thread: {self._listener.ident}")
        assert (
            threading.get_ident() != self._listener.ident
        ), "Listener thread should not be the main thread."
        logger.info("X11 Hotkey listener started.")

    def stop_listening(self) -> None:
        """Stops the hotkey listener and cleans up resources."""
        if self._listener and self._listener.is_alive():
            logger.info("Stopping X11 hotkey listener...")
            self._listener.stop()
            assert (
                threading.get_ident() != self._listener.ident
            ), "Listener thread should not be the main thread."
            self._listener.join()  # Wait for the listener thread to finish
            logger.info("X11 Hotkey listener stopped.")

        self._listener = None
        self._pressed_keys.clear()
        self._hotkey_pressed = False
