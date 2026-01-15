"""Pynput keyboard backend for X11, Windows, and macOS.

This backend uses pynput to type text character-by-character.
Works on X11, Windows, and macOS. On Wayland, it may work through
XWayland but native Wayland support requires eitype or wtype.
"""

import time

from loguru import logger


class PynputKeyboard:
    """Keyboard backend using pynput.

    Types text character-by-character with an optional delay between
    characters to prevent scrambled output on some systems.
    """

    def __init__(self, char_delay: float = 0.001):
        """Initialize the pynput keyboard backend.

        Args:
            char_delay: Delay in seconds between each character.
                       Increase if letters appear scrambled.
        """
        self.char_delay = char_delay
        self._controller = None

    def _get_controller(self):
        """Lazily initialize the pynput keyboard controller."""
        if self._controller is None:
            from voicetype._vendor import pynput

            self._controller = pynput.keyboard.Controller()
        return self._controller

    def type_text(self, text: str) -> None:
        """Type the given text character-by-character.

        Args:
            text: The text to type
        """
        logger.debug(f"PynputKeyboard: typing {len(text)} characters")
        keyboard = self._get_controller()

        for i, char in enumerate(text):
            keyboard.type(char)
            # Don't sleep after the last character
            if self.char_delay > 0 and i < len(text) - 1:
                time.sleep(self.char_delay)

        logger.debug("PynputKeyboard: typing complete")
