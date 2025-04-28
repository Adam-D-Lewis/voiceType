import abc
from typing import Callable, Optional


class HotkeyListener(abc.ABC):
    """
    Abstract base class for platform-specific hotkey listeners.

    Subclasses must implement the abstract methods to provide platform-specific
    hotkey detection. They should call the `on_press` and `on_release`
    callbacks when the configured hotkey is pressed or released, respectively.
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[], None]] = None,
        on_hotkey_release: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize the listener with optional callbacks.

        Args:
            on_press: Callback function to execute when the hotkey is pressed.
            on_release: Callback function to execute when the hotkey is released.
        """
        self.on_hotkey_press = on_hotkey_press
        self.on_hotkey_release = on_hotkey_release
        self._hotkey: Optional[str] = None  # Store the configured hotkey

    @abc.abstractmethod
    def set_hotkey(self, hotkey: str) -> None:
        """
        Set the hotkey combination to listen for.

        The format of the hotkey string might be platform-dependent or
        standardized by the implementation (e.g., 'ctrl+alt+p').

        Args:
            hotkey: The hotkey string.
        """
        self._hotkey = hotkey
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

    def _trigger_hotkey_press(self) -> None:
        """Helper method for subclasses to trigger the press callback."""
        self.on_hotkey_press()

    def _trigger_hotkey_release(self) -> None:
        """Helper method for subclasses to trigger the release callback."""
        self.on_hotkey_release()
