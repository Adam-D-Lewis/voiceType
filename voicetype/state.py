import threading
from enum import Enum, auto


class State(Enum):
    """
    The state of the application.
    """

    IDLE = auto()
    LISTENING = auto()
    RECORDING = auto()
    PROCESSING = auto()


class AppState:
    """
    Thread-safe state management for the application.
    """

    def __init__(self):
        self._state = State.IDLE
        self._lock = threading.Lock()

    @property
    def state(self):
        with self._lock:
            return self._state

    @state.setter
    def state(self, new_state: State):
        with self._lock:
            self._state = new_state
