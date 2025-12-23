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
    method: str = "auto",
    log_key_repeat_debug: bool = False,
) -> HotkeyListener:
    """Create the appropriate hotkey listener for the current platform.

    This factory function selects the best hotkey listener implementation
    based on the current environment and the specified method:

    Methods:
    - "auto" (default): Try portal on Wayland, fall back to pynput
    - "portal": Force XDG Portal GlobalShortcuts (Wayland only)
    - "pynput": Force pynput listener (works on X11, may need XWayland on Wayland)

    Args:
        on_hotkey_press: Callback function to execute when the hotkey is pressed.
        on_hotkey_release: Callback function to execute when the hotkey is released.
        method: Hotkey listener method ("auto", "portal", or "pynput")
        log_key_repeat_debug: Whether to log key repeat debug messages (portal only)

    Returns:
        An appropriate HotkeyListener instance for the current platform.

    Raises:
        RuntimeError: If no suitable hotkey listener can be initialized.
    """
    # Force pynput if requested
    if method == "pynput":
        logger.info("Using pynput hotkey listener (forced by configuration)")
        return PynputHotkeyListener(
            on_hotkey_press=on_hotkey_press,
            on_hotkey_release=on_hotkey_release,
        )

    # Check if we're on Wayland
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    xdg_session_type = os.environ.get("XDG_SESSION_TYPE")
    is_wayland = wayland_display or xdg_session_type == "wayland"

    # Try portal if on Wayland (or forced)
    if is_wayland or method == "portal":
        if is_wayland:
            logger.info("Wayland session detected")

        if method == "portal" and not is_wayland:
            logger.warning(
                "Portal method requested but not on Wayland. Trying anyway..."
            )

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
                    log_key_repeat_debug=log_key_repeat_debug,
                )
            else:
                if method == "portal":
                    raise RuntimeError(
                        "Portal method requested but GlobalShortcuts portal not available. "
                        "Your desktop environment may not support this feature yet. "
                        "Supported: GNOME 48+, KDE Plasma, Hyprland."
                    )
                logger.warning(
                    "Wayland detected but GlobalShortcuts portal not available. "
                    "Your desktop environment may not support this feature yet. "
                    "Supported: GNOME 48+, KDE Plasma, Hyprland. "
                    "Falling back to pynput (may require XWayland or root)."
                )
        except ImportError as e:
            if method == "portal":
                raise RuntimeError(
                    f"Portal method requested but dbus-next not available: {e}. "
                    "Install with: pip install dbus-next"
                )
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
