from dataclasses import dataclass
from pathlib import Path
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
    log_file_path: Optional[Path] = None
    telemetry_enabled: bool = False
    trace_file_path: Optional[Path] = None

    @property
    def has_active_pipelines(self) -> bool:
        """Check if any pipelines are currently executing.

        Returns:
            bool: True if any pipelines are active, False otherwise
        """
        if hasattr(self, "pipeline_manager"):
            return len(self.pipeline_manager.executor.active_pipelines) > 0
        return False

    @property
    def active_pipeline_count(self) -> int:
        """Get the number of currently executing pipelines.

        Returns:
            int: Number of active pipelines
        """
        if hasattr(self, "pipeline_manager"):
            return len(self.pipeline_manager.executor.active_pipelines)
        return 0
