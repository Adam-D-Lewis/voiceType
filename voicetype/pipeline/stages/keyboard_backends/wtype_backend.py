"""Wtype keyboard backend for Wayland (wlroots-based compositors).

This backend uses the wtype CLI tool to type text on Wayland compositors
that are based on wlroots (Sway, Hyprland, Wayfire, River, etc.).
"""

import shutil
import subprocess

from loguru import logger


class WtypeNotFoundError(RuntimeError):
    """Raised when wtype is required but not installed."""

    pass


class WtypeKeyboard:
    """Keyboard backend using wtype for Wayland wlroots compositors.

    Uses the wtype CLI tool to type text. wtype types the entire
    text at once, so char_delay is not applicable.
    """

    def __init__(self):
        """Initialize the wtype keyboard backend.

        Raises:
            WtypeNotFoundError: If wtype is not installed
        """
        self._wtype_path = shutil.which("wtype")
        if self._wtype_path is None:
            raise WtypeNotFoundError(
                "wtype is required for typing on Wayland with wlroots-based "
                "compositors (Sway, Hyprland, Wayfire, River, etc.).\n\n"
                "Install wtype:\n"
                "  - Arch Linux: sudo pacman -S wtype\n"
                "  - Debian/Ubuntu: sudo apt install wtype\n"
                "  - Fedora: sudo dnf install wtype\n"
                "  - Or build from source: https://github.com/atx/wtype"
            )
        logger.debug(f"WtypeKeyboard: using wtype at {self._wtype_path}")

    def type_text(self, text: str) -> None:
        """Type the given text using wtype.

        Args:
            text: The text to type

        Raises:
            RuntimeError: If wtype command fails
        """
        logger.debug(f"WtypeKeyboard: typing {len(text)} characters")

        try:
            # Use "--" to prevent text starting with "-" being interpreted as flags
            result = subprocess.run(
                [self._wtype_path, "--", text],
                capture_output=True,
                timeout=30,
            )

            if result.returncode != 0:
                stderr = result.stderr.decode() if result.stderr else ""
                raise RuntimeError(
                    f"wtype failed with exit code {result.returncode}: {stderr}"
                )

            logger.debug("WtypeKeyboard: typing complete")

        except subprocess.TimeoutExpired:
            raise RuntimeError("wtype command timed out after 30 seconds")
