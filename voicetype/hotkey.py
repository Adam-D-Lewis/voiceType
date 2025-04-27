\
import abc
import threading
from typing import Callable, Optional

class HotkeyListener(abc.ABC):
    \"\"\"Abstract base class for platform-specific hotkey listeners.\"\"\"

    def __init__(self, hotkey: str, on_press: Callable[[], None], on_release: Callable[[], None]):
        \"\"\"
        Initializes the listener.

        Args:
            hotkey: The hotkey string to listen for (format may vary by implementation).
            on_press: Callback function to execute when the hotkey is pressed.
            on_release: Callback function to execute when the hotkey is released.
        \"\"\"
        self._hotkey = hotkey
        self._on_press = on_press
        self._on_release = on_release
        self._listener_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @abc.abstractmethod
    def _run_listener(self):
        \"\"\"Platform-specific implementation to run the listener loop.\"\"\"
        pass

    def start_listening(self):
        \"\"\"Starts the hotkey listener in a separate thread.\"\"\"
        if self._listener_thread is None or not self._listener_thread.is_alive():
            self._stop_event.clear()
            self._listener_thread = threading.Thread(target=self._run_listener, daemon=True)
            self._listener_thread.start()
            print(f"Hotkey listener started for '{self._hotkey}'.") # Add logging later

    def stop_listening(self):
        \"\"\"Stops the hotkey listener thread.\"\"\"
        if self._listener_thread and self._listener_thread.is_alive():
            self._stop_event.set()
            # Implementations might need additional logic here to interrupt blocking calls
            self._listener_thread.join(timeout=1.0) # Wait briefly for thread to exit
            if self._listener_thread.is_alive():
                 print("Warning: Hotkey listener thread did not stop gracefully.") # Add logging
            print("Hotkey listener stopped.") # Add logging
        self._listener_thread = None

    def set_hotkey(self, hotkey: str):
        \"\"\"
        Updates the hotkey to listen for.
        Requires stopping and restarting the listener.
        \"\"\"
        was_running = self._listener_thread is not None and self._listener_thread.is_alive()
        if was_running:
            self.stop_listening()
        self._hotkey = hotkey
        if was_running:
            self.start_listening()

    @property
    def hotkey(self) -> str:
        return self._hotkey

# Example of how platform detection might work (to be implemented elsewhere)
def get_platform_listener() -> type[HotkeyListener]:
    import platform
    import os

    system = platform.system()
    if system == "Linux":
        # Basic check, more robust Wayland detection needed
        is_wayland = "WAYLAND_DISPLAY" in os.environ
        if is_wayland:
            # raise NotImplementedError("Wayland listener not yet implemented.")
            print("Warning: Wayland detected, attempting X11 listener as fallback (may not work).")
            # Fallback to X11 for now, replace with Wayland implementation later
            from .hotkey_linux_x11 import LinuxX11HotkeyListener # Placeholder
            return LinuxX11HotkeyListener
        else:
            from .hotkey_linux_x11 import LinuxX11HotkeyListener # Placeholder
            return LinuxX11HotkeyListener
    elif system == "Windows":
        raise NotImplementedError("Windows listener not yet implemented.")
        # from .hotkey_windows import WindowsHotkeyListener # Placeholder
        # return WindowsHotkeyListener
    elif system == "Darwin": # macOS
        raise NotImplementedError("macOS listener not yet implemented.")
        # from .hotkey_mac import MacHotkeyListener # Placeholder
        # return MacHotkeyListener
    else:
        raise OSError(f"Unsupported operating system: {system}")

