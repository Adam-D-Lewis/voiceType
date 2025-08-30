from dataclasses import dataclass
from typing import TYPE_CHECKING

from voicetype.state import AppState

if TYPE_CHECKING:
    from voicetype.audio_capture import SpeechProcessor
    from voicetype.hotkey_listener.hotkey_listener import HotkeyListener


@dataclass
class AppContext:
    """
    The application context, containing all services and state.
    """

    state: AppState
    speech_processor: "SpeechProcessor"
    hotkey_listener: "HotkeyListener"
