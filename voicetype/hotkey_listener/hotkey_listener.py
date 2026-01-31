import abc
from typing import Callable, Optional


class HotkeyListener(abc.ABC):
    """
    Abstract base class for platform-specific hotkey listeners.

    Subclasses must implement the abstract methods to provide platform-specific
    hotkey detection. They should call the `on_press` and `on_release`
    callbacks when the configured hotkey is pressed or released, respectively.

    Callbacks receive the hotkey string that was pressed/released, enabling
    support for multiple hotkeys on a single listener.
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[str], None]] = None,
        on_hotkey_release: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the listener with optional callbacks.

        Args:
            on_hotkey_press: Callback function to execute when a hotkey is pressed.
                Receives the hotkey string that was pressed.
            on_hotkey_release: Callback function to execute when a hotkey is released.
                Receives the hotkey string that was released.
        """
        self.on_hotkey_press = on_hotkey_press
        self.on_hotkey_release = on_hotkey_release

    @abc.abstractmethod
    def add_hotkey(self, hotkey: str, name: str = "") -> None:
        """
        Register an additional hotkey to listen for.

        Args:
            hotkey: The hotkey string to add.
            name: Optional human-readable name (e.g. pipeline name).
        """
        raise NotImplementedError

    def set_hotkey(self, hotkey: str) -> None:
        """
        Convenience method: clear all hotkeys and add a single one.

        Args:
            hotkey: The hotkey string.
        """
        self.clear_hotkeys()
        self.add_hotkey(hotkey)

    @abc.abstractmethod
    def clear_hotkeys(self) -> None:
        """Remove all registered hotkeys."""
        raise NotImplementedError

    @abc.abstractmethod
    def start_listening(self) -> None:
        """
        Start listening for the configured hotkey events.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def stop_listening(self) -> None:
        """
        Stop listening for hotkey events.
        """
        raise NotImplementedError

    def _trigger_hotkey_press(self, hotkey: str) -> None:
        """Helper method for subclasses to trigger the press callback."""
        if self.on_hotkey_press:
            self.on_hotkey_press(hotkey)

    def _trigger_hotkey_release(self, hotkey: str) -> None:
        """Helper method for subclasses to trigger the release callback."""
        if self.on_hotkey_release:
            self.on_hotkey_release(hotkey)
