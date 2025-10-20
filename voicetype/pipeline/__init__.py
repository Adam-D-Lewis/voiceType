"""Pipeline system for configurable voice typing workflows."""

from .context import IconController, PipelineContext
from .hotkey_dispatcher import HotkeyDispatcher
from .pipeline_executor import PipelineExecutor
from .pipeline_manager import PipelineConfig, PipelineManager
from .resource_manager import Resource, ResourceManager
from .stage_registry import STAGE_REGISTRY, PipelineStage, StageMetadata, StageRegistry
from .trigger_events import (
    HotkeyTriggerEvent,
    ProgrammaticTriggerEvent,
    TimerTriggerEvent,
    TriggerEvent,
)

__all__ = [
    "IconController",
    "PipelineContext",
    "HotkeyDispatcher",
    "PipelineExecutor",
    "PipelineConfig",
    "PipelineManager",
    "Resource",
    "ResourceManager",
    "STAGE_REGISTRY",
    "PipelineStage",
    "StageMetadata",
    "StageRegistry",
    "HotkeyTriggerEvent",
    "ProgrammaticTriggerEvent",
    "TimerTriggerEvent",
    "TriggerEvent",
    "stages",
]

# Import stages to trigger registration (must be after Resource is defined)
from . import stages  # noqa: F401
