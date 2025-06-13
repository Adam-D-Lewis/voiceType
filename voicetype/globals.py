# --- Globals ---
import queue

from voicetype.hotkey_listener.hotkey_listener import HotkeyListener
from voicetype.voice.voice import Voice

hotkey_listener: HotkeyListener | None = None
voice: Voice | None = None
is_recording: bool = False
typing_queue = queue.Queue()
