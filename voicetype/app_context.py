from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from voicetype.settings import FileOpenersConfig
from voicetype.state import AppState

if TYPE_CHECKING:
    from voicetype.hotkey_listener.hotkey_listener import HotkeyListener
    from voicetype.pipeline.pipeline_manager import PipelineManager


@dataclass
class AppContext:
    """
    The application context, containing all services and state.
    """

    state: AppState
    hotkey_listener: Optional["HotkeyListener"]
    pipeline_manager: Optional["PipelineManager"] = None
    log_file_path: Optional[Path] = None
    telemetry_enabled: bool = False
    trace_file_path: Optional[Path] = None
    file_openers: FileOpenersConfig = field(default_factory=FileOpenersConfig)

    @property
    def has_active_pipelines(self) -> bool:
        """Check if any pipelines are currently executing.

        Returns:
            bool: True if any pipelines are active, False otherwise
        """
        if self.pipeline_manager:
            return len(self.pipeline_manager.executor.active_pipelines) > 0
        return False

    @property
    def active_pipeline_count(self) -> int:
        """Get the number of currently executing pipelines.

        Returns:
            int: Number of active pipelines
        """
        if self.pipeline_manager:
            return len(self.pipeline_manager.executor.active_pipelines)
        return 0
