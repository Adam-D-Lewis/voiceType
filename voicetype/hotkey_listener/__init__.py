"""Hotkey listener module for VoiceType.

This module provides platform-specific hotkey listeners for capturing
global keyboard shortcuts. It automatically selects the appropriate
implementation based on the current platform and environment.
"""

import os
from typing import Callable, Optional

from loguru import logger

from .hotkey_listener import HotkeyListener
from .pynput_hotkey_listener import PynputHotkeyListener

__all__ = [
    "HotkeyListener",
    "PynputHotkeyListener",
    "create_hotkey_listener",
]


def create_hotkey_listener(
    on_hotkey_press: Optional[Callable[[], None]] = None,
    on_hotkey_release: Optional[Callable[[], None]] = None,
) -> HotkeyListener:
    """Create the appropriate hotkey listener for the current platform.

    This factory function selects the best hotkey listener implementation
    based on the current environment:

    Priority:
    1. On Wayland with GlobalShortcuts portal support: Use PortalHotkeyListener
    2. Otherwise: Use PynputHotkeyListener (X11, macOS, Windows)

    Args:
        on_hotkey_press: Callback function to execute when the hotkey is pressed.
        on_hotkey_release: Callback function to execute when the hotkey is released.

    Returns:
        An appropriate HotkeyListener instance for the current platform.

    Raises:
        RuntimeError: If no suitable hotkey listener can be initialized.
    """
    # Check if we're on Wayland
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    xdg_session_type = os.environ.get("XDG_SESSION_TYPE")
    is_wayland = wayland_display or xdg_session_type == "wayland"

    if is_wayland:
        logger.info("Wayland session detected")

        try:
            from .portal_hotkey_listener import (
                PortalHotkeyListener,
                is_portal_available,
            )

            if is_portal_available():
                logger.info("Using XDG Portal GlobalShortcuts (Wayland)")
                return PortalHotkeyListener(
                    on_hotkey_press=on_hotkey_press,
                    on_hotkey_release=on_hotkey_release,
                )
            else:
                logger.warning(
                    "Wayland detected but GlobalShortcuts portal not available. "
                    "Your desktop environment may not support this feature yet. "
                    "Supported: GNOME 48+, KDE Plasma, Hyprland. "
                    "Falling back to pynput (may require XWayland or root)."
                )
        except ImportError as e:
            logger.warning(
                f"Portal listener not available (missing dbus-next?): {e}. "
                "Install with: pip install dbus-next"
            )

    # Default to pynput
    logger.info("Using pynput hotkey listener")
    return PynputHotkeyListener(
        on_hotkey_press=on_hotkey_press,
        on_hotkey_release=on_hotkey_release,
    )
