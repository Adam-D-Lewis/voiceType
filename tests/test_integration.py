"""Integration tests for pipeline system with main application components."""

import threading
from typing import Optional
from unittest.mock import MagicMock, Mock

import pytest

from voicetype.pipeline import (
    HotkeyDispatcher,
    PipelineManager,
    ResourceManager,
)


class MockIconController:
    """Mock IconController for testing."""

    def __init__(self):
        self.state = "idle"
        self.flashing = False

    def set_icon(self, state: str, duration: Optional[float] = None) -> None:
        """Set the icon state."""
        self.state = state

    def start_flashing(self, state: str) -> None:
        """Start flashing the icon."""
        self.flashing = True
        self.state = state

    def stop_flashing(self) -> None:
        """Stop flashing the icon."""
        self.flashing = False


def test_icon_controller_mock():
    """Test that MockIconController implements the IconController protocol."""
    controller = MockIconController()

    # Test set_icon method
    controller.set_icon("idle")
    assert controller.state == "idle"

    controller.set_icon("recording")
    assert controller.state == "recording"

    controller.set_icon("processing")
    assert controller.state == "processing"

    controller.set_icon("error")
    assert controller.state == "error"


def test_pipeline_manager_with_metadata():
    """Test that PipelineManager can pass metadata to pipelines."""
    # Create mock icon controller
    icon_controller = MockIconController()

    # Create resource manager and pipeline manager
    resource_manager = ResourceManager()
    pipeline_manager = PipelineManager(
        resource_manager=resource_manager,
        icon_controller=icon_controller,
        max_workers=2,
    )

    # Load a simple pipeline
    stage_definitions = {
        "RecordAudio": {},
        "Transcribe": {"provider": "local"},
        "TypeText": {},
    }

    pipeline_config = [
        {
            "name": "test_pipeline",
            "enabled": True,
            "hotkey": "<pause>",
            "stages": ["RecordAudio", "Transcribe", "TypeText"],
        }
    ]

    pipeline_manager.load_pipelines(
        pipeline_config, stage_definitions=stage_definitions
    )

    # Verify pipeline loaded
    assert len(pipeline_manager.pipelines) == 1
    assert "test_pipeline" in pipeline_manager.pipelines


def test_hotkey_dispatcher_integration():
    """Test HotkeyDispatcher integration with PipelineManager."""
    # Create mock icon controller
    icon_controller = MockIconController()

    # Create resource manager and pipeline manager
    resource_manager = ResourceManager()
    pipeline_manager = PipelineManager(
        resource_manager=resource_manager,
        icon_controller=icon_controller,
        max_workers=2,
    )

    # Load a pipeline
    stage_definitions = {
        "RecordAudio": {},
        "Transcribe": {"provider": "local"},
        "TypeText": {},
    }

    pipeline_config = [
        {
            "name": "test_pipeline",
            "enabled": True,
            "hotkey": "<pause>",
            "stages": ["RecordAudio", "Transcribe", "TypeText"],
        }
    ]

    pipeline_manager.load_pipelines(
        pipeline_config, stage_definitions=stage_definitions
    )

    # Create hotkey dispatcher
    hotkey_dispatcher = HotkeyDispatcher(pipeline_manager)

    # Verify hotkey dispatcher initialized
    assert hotkey_dispatcher.pipeline_manager == pipeline_manager


def test_full_integration_mock():
    """Test full integration with mocked components."""
    # Create mock components
    icon_controller = MockIconController()

    # Create managers
    resource_manager = ResourceManager()
    pipeline_manager = PipelineManager(
        resource_manager=resource_manager,
        icon_controller=icon_controller,
        max_workers=2,
    )

    # Load pipeline
    stage_definitions = {
        "RecordAudio": {},
        "Transcribe": {"provider": "local"},
        "TypeText": {},
    }

    pipeline_config = [
        {
            "name": "default",
            "enabled": True,
            "hotkey": "<pause>",
            "stages": ["RecordAudio", "Transcribe", "TypeText"],
        }
    ]

    pipeline_manager.load_pipelines(
        pipeline_config, stage_definitions=stage_definitions
    )

    # Create hotkey dispatcher
    hotkey_dispatcher = HotkeyDispatcher(pipeline_manager)

    # Simulate hotkey press/release
    hotkey_string = "<pause>"

    # Press
    hotkey_dispatcher._on_press(hotkey_string)

    # Verify trigger event created
    assert hotkey_string in hotkey_dispatcher.active_events

    # Release
    hotkey_dispatcher._on_release(hotkey_string)

    # Verify trigger event removed
    assert hotkey_string not in hotkey_dispatcher.active_events

    # Wait a bit for pipeline to complete
    import time

    time.sleep(0.5)

    # Shutdown
    pipeline_manager.shutdown(timeout=2.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
