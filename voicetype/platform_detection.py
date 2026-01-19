"""Platform detection utilities for VoiceType.

This module provides centralized functions for detecting:
- Display server (Wayland vs X11)
- Compositor type (GNOME, KDE, wlroots-based, etc.)
- IS (Extended Input Simulation) support
"""

import functools
import os
import subprocess
from enum import Enum
from typing import Optional

from loguru import logger


class CompositorType(Enum):
    """Known compositor/desktop environment types."""

    GNOME = "gnome"
    KDE = "kde"
    WLROOTS = "wlroots"  # Sway, Hyprland, Wayfire, River, etc.
    OTHER = "other"
    UNKNOWN = "unknown"


# Known wlroots-based compositors (lowercase for matching)
WLROOTS_COMPOSITORS = frozenset(
    {
        "sway",
        "hyprland",
        "wayfire",
        "river",
        "labwc",
        "dwl",
        "cage",
        "phoc",  # Phosh's compositor
        "newm",
        "waymonad",
        "hikari",
        "japokwm",
        "velox",
        "taiwins",
        "bspwwm",  # Not actually wlroots but similar limitations
    }
)


@functools.lru_cache(maxsize=1)
def get_display_server() -> str:
    """Detect the current display server.

    Returns:
        'wayland', 'x11', or 'unknown'

    Priority order (most reliable first):
    1. XDG_SESSION_TYPE - Explicitly set by login manager
    2. WAYLAND_DISPLAY - Present when Wayland compositor is running
    3. DISPLAY - Present when X11 server is available
    """
    # Check XDG_SESSION_TYPE first (most reliable)
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session_type == "wayland":
        return "wayland"
    if session_type == "x11":
        return "x11"

    # Fallback to checking display environment variables
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"

    if os.environ.get("DISPLAY"):
        return "x11"

    return "unknown"


def is_wayland() -> bool:
    """Check if running on Wayland.

    Returns:
        True if the current session is Wayland
    """
    return get_display_server() == "wayland"


def is_x11() -> bool:
    """Check if running on X11.

    Returns:
        True if the current session is X11
    """
    return get_display_server() == "x11"


@functools.lru_cache(maxsize=1)
def get_compositor_name() -> str:
    """Get the raw compositor/desktop environment name.

    Returns:
        The compositor name in lowercase, or empty string if unknown.

    Checks (in order):
    1. XDG_CURRENT_DESKTOP
    2. XDG_SESSION_DESKTOP
    3. DESKTOP_SESSION
    4. Compositor-specific environment variables
    """
    # Check standard desktop environment variables
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if desktop:
        # XDG_CURRENT_DESKTOP can be colon-separated (e.g., "ubuntu:GNOME")
        # Return the last component as it's usually the most specific
        parts = desktop.split(":")
        return parts[-1].lower()

    desktop = os.environ.get("XDG_SESSION_DESKTOP", "")
    if desktop:
        return desktop.lower()

    desktop = os.environ.get("DESKTOP_SESSION", "")
    if desktop:
        return desktop.lower()

    # Check compositor-specific environment variables
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "hyprland"

    if os.environ.get("SWAYSOCK"):
        return "sway"

    return ""


@functools.lru_cache(maxsize=1)
def get_compositor_type() -> CompositorType:
    """Detect the compositor/desktop environment type.

    Returns:
        CompositorType enum indicating the general category:
        - GNOME: GNOME Shell / Mutter
        - KDE: KDE Plasma / KWin
        - WLROOTS: wlroots-based compositors (Sway, Hyprland, etc.)
        - OTHER: Known but uncategorized compositor
        - UNKNOWN: Could not determine
    """
    name = get_compositor_name()

    if not name:
        return CompositorType.UNKNOWN

    # Check for GNOME
    if "gnome" in name:
        return CompositorType.GNOME

    # Check for KDE/Plasma
    if "kde" in name or "plasma" in name:
        return CompositorType.KDE

    # Check for wlroots-based compositors
    if name in WLROOTS_COMPOSITORS:
        return CompositorType.WLROOTS

    # Also check environment variables for wlroots compositors
    # (in case XDG_CURRENT_DESKTOP doesn't match)
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return CompositorType.WLROOTS

    if os.environ.get("SWAYSOCK"):
        return CompositorType.WLROOTS

    return CompositorType.OTHER


def _check_dbus_interface(bus_name: str, object_path: str, interface: str) -> bool:
    """Check if a D-Bus interface exists using dbus-send or busctl.

    Args:
        bus_name: The D-Bus bus name (e.g., "org.freedesktop.portal.Desktop")
        object_path: The object path (e.g., "/org/freedesktop/portal/desktop")
        interface: The interface name to check for

    Returns:
        True if the interface exists, False otherwise
    """
    # Try dbus-send first
    try:
        result = subprocess.run(
            [
                "dbus-send",
                "--session",
                "--print-reply",
                f"--dest={bus_name}",
                object_path,
                "org.freedesktop.DBus.Introspectable.Introspect",
            ],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0 and interface.encode() in result.stdout:
            return True
    except FileNotFoundError:
        pass  # dbus-send not available, try busctl
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout checking D-Bus interface {interface}")
        return False
    except Exception as e:
        logger.debug(f"dbus-send failed: {e}")

    # Try busctl as fallback
    try:
        result = subprocess.run(
            [
                "busctl",
                "--user",
                "introspect",
                bus_name,
                object_path,
                interface,
            ],
            capture_output=True,
            timeout=5,
        )
        # busctl returns 0 even if interface doesn't exist,
        # so we need to check for actual method names
        if result.returncode == 0:
            output = result.stdout.decode()
            # Check for typical portal methods
            if "CreateSession" in output or "Start" in output:
                return True
    except FileNotFoundError:
        logger.debug("Neither dbus-send nor busctl available")
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout checking D-Bus interface {interface} with busctl")
    except Exception as e:
        logger.debug(f"busctl failed: {e}")

    return False


@functools.lru_cache(maxsize=1)
def is_remote_desktop_portal_available() -> bool:
    """Check if the RemoteDesktop portal D-Bus interface is available.

    This portal is required for IS (libei) input simulation on Wayland.

    Returns:
        True if org.freedesktop.portal.RemoteDesktop is available
    """
    return _check_dbus_interface(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.RemoteDesktop",
    )


@functools.lru_cache(maxsize=1)
def supports_is() -> bool:
    """Check if the current compositor supports IS (Extended Input Simulation).

    IS allows programmatic input injection on Wayland via the RemoteDesktop portal.
    It is supported by:
    - GNOME 46+ (Mutter)
    - KDE Plasma 6+ (KWin)

    NOT supported by wlroots-based compositors (Sway, Hyprland, etc.)
    which use alternative methods like wtype or ydotool.

    Returns:
        True if IS is likely supported
    """
    # Not on Wayland = no IS needed (X11 has other methods)
    if not is_wayland():
        return False

    # wlroots compositors don't support IS
    compositor = get_compositor_type()
    if compositor == CompositorType.WLROOTS:
        return False

    # GNOME and KDE support IS - verify portal is actually available
    if compositor in (CompositorType.GNOME, CompositorType.KDE):
        return is_remote_desktop_portal_available()

    # Unknown compositor - check if portal is available
    return is_remote_desktop_portal_available()


def get_platform_info() -> dict:
    """Get a summary of platform detection results.

    Useful for debugging and logging.

    Returns:
        Dictionary with display_server, compositor_name, compositor_type,
        supports_is, and is_wayland keys.
    """
    return {
        "display_server": get_display_server(),
        "compositor_name": get_compositor_name(),
        "compositor_type": get_compositor_type().value,
        "supports_is": supports_is(),
        "is_wayland": is_wayland(),
        "is_x11": is_x11(),
    }


def clear_cache() -> None:
    """Clear all cached detection results.

    Useful for testing or if the environment changes.
    """
    get_display_server.cache_clear()
    get_compositor_name.cache_clear()
    get_compositor_type.cache_clear()
    is_remote_desktop_portal_available.cache_clear()
    supports_is.cache_clear()
