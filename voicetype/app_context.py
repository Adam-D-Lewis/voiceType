from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from voicetype.state import AppState

if TYPE_CHECKING:
    from voicetype.hotkey_listener.hotkey_listener import HotkeyListener


@dataclass
class AppContext:
    """
    The application context, containing all services and state.
    """

    state: AppState
    hotkey_listener: Optional["HotkeyListener"]
