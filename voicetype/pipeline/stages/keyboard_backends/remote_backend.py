"""Remote keyboard backend: types text on a remote device.

Sends the text to the device connected to voiceType's remote listener (e.g. a
Pico 2 W plugged into another computer as a USB keyboard), which types it.
"""

import unicodedata

from loguru import logger

from voicetype.hotkey_listener.remote_hotkey_listener import (
    RemoteNotConnectedError,
    get_active_remote_listener,
)

# Typographic characters with a close ASCII equivalent
_ASCII_REPLACEMENTS = str.maketrans(
    {
        "‘": "'",  # ‘
        "’": "'",  # ’
        "‚": "'",  # ‚
        "‛": "'",  # ‛
        "′": "'",  # ′
        "“": '"',  # “
        "”": '"',  # ”
        "„": '"',  # „
        "‟": '"',  # ‟
        "″": '"',  # ″
        "«": '"',  # «
        "»": '"',  # »
        "‐": "-",  # hyphen
        "‑": "-",  # non-breaking hyphen
        "‒": "-",  # figure dash
        "–": "-",  # en dash
        "−": "-",  # minus sign
        "—": "--",  # em dash
        "―": "--",  # horizontal bar
        "•": "*",  # bullet
        "·": "*",  # middle dot
        "×": "x",  # multiplication sign
        "ß": "ss",  # ß
        "æ": "ae",  # æ
        "Æ": "AE",  # Æ
        "œ": "oe",  # œ
        "Œ": "OE",  # Œ
        "ø": "o",  # ø
        "Ø": "O",  # Ø
        "ł": "l",  # ł
        "Ł": "L",  # Ł
        "đ": "d",  # đ
        "Đ": "D",  # Đ
        "ı": "i",  # dotless i
    }
)


def to_hid_text(text: str) -> str:
    """Reduce text to what a USB keyboard can type: printable ASCII, newline, tab.

    A USB keyboard sends key positions, not characters, so the remote device can
    only type characters on its keyboard layout's keys. Typographic punctuation
    becomes its ASCII equivalent and accents are dropped
    ("café — naïve" -> "cafe -- naive"); anything else is removed.
    """
    text = unicodedata.normalize("NFKD", text.translate(_ASCII_REPLACEMENTS))
    return "".join(ch for ch in text if " " <= ch <= "~" or ch in "\n\t")


class RemoteKeyboard:
    """Keyboard backend that types on the remote device connected to voiceType."""

    def type_text(self, text: str) -> None:
        """Send text for the remote device to type.

        Args:
            text: The text to type

        Raises:
            RemoteNotConnectedError: If the remote listener isn't running or no
                device is connected.
        """
        listener = get_active_remote_listener()
        if listener is None:
            raise RemoteNotConnectedError(
                'keyboard_backend = "remote" needs the remote listener; '
                "set enabled = true under [remote] in settings.toml"
            )

        hid_text = to_hid_text(text)
        if hid_text != text:
            logger.debug(f"Simplified text for the remote keyboard: {hid_text!r}")
        if not hid_text:
            logger.info("No typeable characters to send to the remote device")
            return
        listener.send_text(hid_text)
