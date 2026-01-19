"""Keyboard backends for typing text on different platforms.

This module provides a factory function to create the appropriate
keyboard backend based on the current platform and configuration.
"""

import sys
from typing import Union

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
from voicetype.pipeline.stages.keyboard_backends.wtype_backend import (
    WtypeKeyboard,
    WtypeNotFoundError,
)

__all__ = [
    "KeyboardBackend",
    "PynputKeyboard",
    "WtypeKeyboard",
    "EitypeKeyboard",
    "WtypeNotFoundError",
    "EitypeNotFoundError",
    "clear_eitype_connection",
    "create_keyboard_backend",
]


def create_keyboard_backend(
    method: str = "auto",
    char_delay: float = 0.001,
) -> Union[PynputKeyboard, WtypeKeyboard, EitypeKeyboard]:
    """Create the appropriate keyboard backend for the current platform.

    Args:
        method: Backend selection method:
            - "auto": Automatically detect based on platform (default)
            - "pynput": Force pynput (X11, Windows, macOS)
            - "wtype": Force wtype (Wayland wlroots)
            - "eitype": Force eitype (Wayland GNOME/KDE)
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

    if method != "auto":
        raise ValueError(
            f"Invalid keyboard_backend method: '{method}'. "
            "Valid options: auto, pynput, wtype, eitype"
        )

    # Auto-detection logic
    return _create_auto_backend(char_delay)


def _create_auto_backend(
    char_delay: float,
) -> Union[PynputKeyboard, WtypeKeyboard, EitypeKeyboard]:
    """Auto-detect and create the appropriate keyboard backend.

    Detection priority:
    1. Not Linux -> pynput
    2. X11 -> pynput
    3. Wayland + EI support (GNOME/KDE) -> eitype
    4. Wayland + wlroots compositor -> wtype
    5. Fallback -> pynput with warning

    Args:
        char_delay: Delay between characters (only used by pynput)

    Returns:
        A keyboard backend instance
    """
    # Not Linux - use pynput
    if sys.platform != "linux":
        logger.info(f"Using pynput keyboard backend (platform: {sys.platform})")
        return PynputKeyboard(char_delay=char_delay)

    # Import platform detection (only available on Linux)
    from voicetype.platform_detection import (
        CompositorType,
        get_compositor_type,
        is_wayland,
        is_x11,
        supports_is,
    )

    # X11 - use pynput
    if is_x11():
        logger.info("Using pynput keyboard backend (X11 display server)")
        return PynputKeyboard(char_delay=char_delay)

    # Not Wayland and not X11 - fallback to pynput
    if not is_wayland():
        logger.warning(
            "Unknown display server, falling back to pynput keyboard backend. "
            "Set keyboard_backend explicitly if typing doesn't work."
        )
        return PynputKeyboard(char_delay=char_delay)

    # Wayland - determine which backend to use
    compositor = get_compositor_type()
    logger.debug(f"Detected Wayland compositor type: {compositor.value}")

    # GNOME or KDE with EI support -> try eitype
    if compositor in (CompositorType.GNOME, CompositorType.KDE) and supports_is():
        logger.info(
            f"Using eitype keyboard backend (Wayland {compositor.value} with EI support)"
        )
        return EitypeKeyboard()

    # wlroots-based compositor -> use wtype
    if compositor == CompositorType.WLROOTS:
        logger.info("Using wtype keyboard backend (Wayland wlroots compositor)")
        return WtypeKeyboard()

    # Unknown Wayland compositor - try eitype first (if portal available), then wtype
    if supports_is():
        logger.info(
            f"Using eitype keyboard backend (Wayland {compositor.value} with RemoteDesktop portal)"
        )
        return EitypeKeyboard()

    # Last resort for Wayland - try wtype
    logger.info(
        f"Using wtype keyboard backend (Wayland {compositor.value}, no EI support)"
    )
    return WtypeKeyboard()
