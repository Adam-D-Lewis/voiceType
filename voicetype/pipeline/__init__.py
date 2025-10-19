"""Pipeline system for configurable voice typing workflows."""

# Import stages to trigger registration
from . import stages  # noqa: F401
from .context import IconController, PipelineContext
from .hotkey_manager import HotkeyManager
from .pipeline_executor import PipelineExecutor
from .pipeline_manager import PipelineConfig, PipelineManager, migrate_legacy_settings
from .resource_manager import Resource, ResourceManager
from .stage_registry import STAGE_REGISTRY, StageMetadata, StageRegistry
from .trigger_events import (
    HotkeyTriggerEvent,
    ProgrammaticTriggerEvent,
    TimerTriggerEvent,
    TriggerEvent,
)

__all__ = [
    "IconController",
    "PipelineContext",
    "HotkeyManager",
    "PipelineExecutor",
    "PipelineConfig",
    "PipelineManager",
    "migrate_legacy_settings",
    "Resource",
    "ResourceManager",
    "STAGE_REGISTRY",
    "StageMetadata",
    "StageRegistry",
    "HotkeyTriggerEvent",
    "ProgrammaticTriggerEvent",
    "TimerTriggerEvent",
    "TriggerEvent",
    "stages",
]
