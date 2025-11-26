import os
import sys
import time
from pathlib import Path

from loguru import logger

from voicetype._vendor import pynput


def get_app_data_dir() -> Path:
    """Get the platform-specific application data directory for voicetype.

    Returns:
        Path to the voicetype application data directory:
        - Windows: %APPDATA%/voicetype
        - macOS: ~/Library/Application Support/voicetype
        - Linux: $XDG_CONFIG_HOME/voicetype or ~/.config/voicetype
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:  # Linux and other Unix-like systems
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    return base / "voicetype"


def type_text(text):
    keyboard = pynput.keyboard.Controller()

    # Type each character in the text
    for char in text:
        keyboard.tap(char)
        time.sleep(0.001)  # Adjust the delay between keypresses if needed

    # Press Enter key at the end
    keyboard.press("\n")
    keyboard.release("\n")


def play_sound(sound_path):
    """Play a sound file using playsound3 with threading to avoid blocking.

    Args:
        sound_path: Path to the sound file to play

    """
    import threading
    from pathlib import Path

    def _play_sound_thread():
        try:
            from playsound3 import playsound

            sound_file = Path(sound_path)
            if not sound_file.exists():
                logger.warning(f"Sound file does not exist: {sound_file}")
                return

            logger.debug(f"Playing sound: {sound_file}")
            playsound(str(sound_file), block=True)
        except Exception as e:
            logger.error(f"Failed to play sound {sound_path}: {e}")

    # Each sound gets its own thread - simpler and more reliable
    threading.Thread(target=_play_sound_thread, daemon=True).start()
