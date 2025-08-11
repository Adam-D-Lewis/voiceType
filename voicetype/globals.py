# --- Globals ---
import queue

from voicetype.audio_capture import SpeechProcessor
from voicetype.hotkey_listener.hotkey_listener import HotkeyListener

hotkey_listener: HotkeyListener | None = None
speech_processor: SpeechProcessor | None = None
is_recording: bool = False
typing_queue = queue.Queue()
is_listening: bool = False
is_enabled: bool = True
