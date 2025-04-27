import abc
import threading
from typing import Callable, Optional, Set

from pynput import keyboard

from .hotkey_listener import HotkeyListener


class LinuxX11HotkeyListener(HotkeyListener):
    """
    Hotkey listener implementation for Linux X11 using pynput.
    """

    def __init__(
        self,
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
    ):
        super().__init__(on_press, on_release)
        self._hotkey_combination: Optional[Set[keyboard.Key | keyboard.KeyCode]] = None
        self._listener: Optional[keyboard.Listener] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._pressed_keys: Set[keyboard.Key | keyboard.KeyCode] = set()
        self._hotkey_pressed: bool = False
        self._lock = threading.Lock()

    def set_hotkey(self, hotkey: str) -> None:
        """
        Sets the hotkey combination to listen for.

        Args:
            hotkey: A string representation of the hotkey (e.g., "<ctrl>+<alt>+x").
                    Uses pynput's format.
        """
        try:
            self._hotkey_combination = keyboard.HotKey.parse(hotkey)
            print(f"Hotkey set to: {hotkey} -> {self._hotkey_combination}")
        except ValueError as e:
            # Consider logging this error instead of just printing
            print(f"Error parsing hotkey '{hotkey}': {e}")
            self._hotkey_combination = None
            raise ValueError(f"Invalid hotkey format: {hotkey}") from e

    def _on_press(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        if key is None or self._hotkey_combination is None:
            return

        with self._lock:
            self._pressed_keys.add(key)
            # Check if the current set of pressed keys contains the hotkey combination
            if not self._hotkey_pressed and self._hotkey_combination.issubset(self._pressed_keys):
                self._hotkey_pressed = True
                self._trigger_press()


    def _on_release(self, key: Optional[keyboard.Key | keyboard.KeyCode]):
        if key is None or self._hotkey_combination is None:
            return

        with self._lock:
            # Check if the released key was part of the hotkey combination
            # and if the hotkey was previously considered pressed
            if self._hotkey_pressed and key in self._hotkey_combination:
                 # Check if *any* key from the hotkey combo is still pressed
                 # This handles cases where modifiers are released after the main key
                 any_hotkey_key_pressed = any(k in self._pressed_keys for k in self._hotkey_combination if k != key)
                 if not any_hotkey_key_pressed:
                    self._hotkey_pressed = False
                    self._trigger_release()

            # Remove the key from the set of pressed keys
            if key in self._pressed_keys:
                self._pressed_keys.remove(key)


    def start_listening(self) -> None:
        """Starts the hotkey listener thread."""
        if self._listener_thread is not None and self._listener_thread.is_alive():
            print("Listener already running.")
            return

        if self._hotkey_combination is None:
            raise ValueError("Hotkey not set before starting listener.")

        # Ensure pynput uses X11 backend explicitly if needed, though usually automatic
        # Note: pynput might require DISPLAY environment variable to be set.
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            # Explicitly setting suppress=False might be needed depending on environment
            # suppress=False # Try this if keys are blocked system-wide
        )

        # Run the listener in a separate thread
        self._listener_thread = threading.Thread(target=self._listener.run, daemon=True)
        self._listener_thread.start()
        print("X11 Hotkey listener started.")

    def stop_listening(self) -> None:
        """Stops the hotkey listener thread."""
        if self._listener:
            self._listener.stop()
            print("Stopping X11 hotkey listener...")
        if self._listener_thread:
            self._listener_thread.join()
            print("X11 Hotkey listener stopped.")
        self._listener = None
        self._listener_thread = None
        self._pressed_keys.clear()
        self._hotkey_pressed = False
