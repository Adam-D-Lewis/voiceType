import threading
from enum import Enum, auto


class State(Enum):
    """
    The state of the application.

    DISABLED: App is disabled and will not respond to hotkeys
    ENABLED: App is enabled and will respond to hotkeys

    Note: Pipeline execution state is tracked separately by PipelineExecutor.
    """

    DISABLED = auto()
    ENABLED = auto()


class AppState:
    """
    Thread-safe state management for the application.
    """

    def __init__(self):
        self._state = State.DISABLED
        self._lock = threading.Lock()

    @property
    def state(self):
        with self._lock:
            return self._state

    @state.setter
    def state(self, new_state: State):
        with self._lock:
            self._state = new_state
