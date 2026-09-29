"""Keyboard backends for typing text on different platforms.

This module provides a factory function to create the appropriate
keyboard backend based on the current platform and configuration.
"""

import sys
import threading
from typing import Optional, Tuple, Union

from loguru import logger

from voicetype.pipeline.stages.keyboard_backends.base import KeyboardBackend
from voicetype.pipeline.stages.keyboard_backends.eitype_backend import (
    EitypeKeyboard,
    EitypeNotFoundError,
)
from voicetype.pipeline.stages.keyboard_backends.eitype_backend import (
    clear_cached_connection as clear_eitype_connection,
)
from voicetype.pipeline.stages.keyboard_backends.pynput_backend import PynputKeyboard
from voicetype.pipeline.stages.keyboard_backends.remote_backend import RemoteKeyboard
from voicetype.pipeline.stages.keyboard_backends.wtype_backend import (
    WtypeKeyboard,
    WtypeNotFoundError,
)

__all__ = [
    "KeyboardBackend",
    "PynputKeyboard",
    "WtypeKeyboard",
    "EitypeKeyboard",
    "RemoteKeyboard",
    "WtypeNotFoundError",
    "EitypeNotFoundError",
    "clear_eitype_connection",
    "create_keyboard_backend",
    "detect_auto_backend",
    "get_backend_override",
    "set_backend_override",
    "KEYBOARD_BACKENDS",
]

KEYBOARD_BACKENDS = ("auto", "pynput", "wtype", "eitype", "remote")

UNKNOWN_DISPLAY_SERVER = "unknown display server"

# Runtime override, e.g. from the tray menu, applied to every TypeText stage.
# ``None`` means each stage uses its configured keyboard_backend.
_backend_override: Optional[str] = None
_backend_override_lock = threading.Lock()


def set_backend_override(method: Optional[str]) -> None:
    """Make every TypeText stage use this backend, or None for its own setting.

    Takes effect from the next pipeline run.
    """
    global _backend_override
    if method is not None and method not in KEYBOARD_BACKENDS:
        raise ValueError(
            f"Invalid keyboard backend: '{method}'. "
            f"Valid options: {', '.join(KEYBOARD_BACKENDS)}"
        )
    with _backend_override_lock:
        _backend_override = method


def get_backend_override() -> Optional[str]:
    """Return the runtime keyboard backend override, or None if not overridden."""
    with _backend_override_lock:
        return _backend_override


def create_keyboard_backend(
    method: str = "auto",
    char_delay: float = 0.001,
) -> Union[PynputKeyboard, WtypeKeyboard, EitypeKeyboard, RemoteKeyboard]:
    """Create the appropriate keyboard backend for the current platform.

    Args:
        method: Backend selection method:
            - "auto": Automatically detect based on platform (default)
            - "pynput": Force pynput (X11, Windows, macOS)
            - "wtype": Force wtype (Wayland wlroots)
            - "eitype": Force eitype (Wayland GNOME/KDE)
            - "remote": Type on the connected remote device (e.g. a Pico 2 W)
        char_delay: Delay between characters (only used by pynput)

    Returns:
        A keyboard backend instance implementing the KeyboardBackend protocol

    Raises:
        WtypeNotFoundError: If wtype is required but not installed
        EitypeNotFoundError: If eitype is required but not installed
        ValueError: If an invalid method is specified
    """
    method = method.lower()

    if method == "pynput":
        logger.info("Using pynput keyboard backend (explicitly requested)")
        return PynputKeyboard(char_delay=char_delay)

    if method == "wtype":
        logger.info("Using wtype keyboard backend (explicitly requested)")
        return WtypeKeyboard()

    if method == "eitype":
        logger.info("Using eitype keyboard backend (explicitly requested)")
        return EitypeKeyboard()

    if method == "remote":
        logger.info("Using remote keyboard backend (types on the remote device)")
        return RemoteKeyboard()

    if method != "auto":
        raise ValueError(
            f"Invalid keyboard_backend method: '{method}'. "
            "Valid options: auto, pynput, wtype, eitype, remote"
        )

    # Auto-detection logic
    return _create_auto_backend(char_delay)


def detect_auto_backend() -> Tuple[str, str]:
    """Pick the backend "auto" uses on this platform, without creating it.

    Detection priority:
    1. Not Linux -> pynput
    2. X11 -> pynput
    3. Wayland + EI support (GNOME/KDE) -> eitype
    4. Wayland + wlroots compositor -> wtype
    5. Other Wayland -> eitype if the RemoteDesktop portal exists, else wtype
    6. Unknown display server -> pynput

    Returns:
        (backend name, reason it was picked)
    """
    # Not Linux - use pynput
    if sys.platform != "linux":
        return "pynput", f"platform: {sys.platform}"

    # Import platform detection (only available on Linux)
    from voicetype.platform_detection import (
        CompositorType,
        get_compositor_type,
        is_wayland,
        is_x11,
        supports_is,
    )

    if is_x11():
        return "pynput", "X11 display server"

    if not is_wayland():
        return "pynput", UNKNOWN_DISPLAY_SERVER

    compositor = get_compositor_type()
    if compositor in (CompositorType.GNOME, CompositorType.KDE) and supports_is():
        return "eitype", f"Wayland {compositor.value} with EI support"
    if compositor == CompositorType.WLROOTS:
        return "wtype", "Wayland wlroots compositor"
    if supports_is():
        return "eitype", f"Wayland {compositor.value} with RemoteDesktop portal"
    return "wtype", f"Wayland {compositor.value}, no EI support"


def _create_auto_backend(
    char_delay: float,
) -> Union[PynputKeyboard, WtypeKeyboard, EitypeKeyboard]:
    """Create the keyboard backend detect_auto_backend() picks.

    Args:
        char_delay: Delay between characters (only used by pynput)

    Returns:
        A keyboard backend instance
    """
    method, reason = detect_auto_backend()
    if reason == UNKNOWN_DISPLAY_SERVER:
        logger.warning(
            "Unknown display server, falling back to pynput keyboard backend. "
            "Set keyboard_backend explicitly if typing doesn't work."
        )
    else:
        logger.info(f"Using {method} keyboard backend ({reason})")

    if method == "eitype":
        return EitypeKeyboard()
    if method == "wtype":
        return WtypeKeyboard()
    return PynputKeyboard(char_delay=char_delay)
