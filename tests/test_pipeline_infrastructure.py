"""Unit tests for pipeline infrastructure components."""

import threading
import time
from typing import Optional

import pytest

from voicetype.pipeline import (
    HotkeyTriggerEvent,
    PipelineContext,
    ProgrammaticTriggerEvent,
    Resource,
    ResourceManager,
    StageRegistry,
    TimerTriggerEvent,
)


class TestTriggerEvents:
    """Tests for trigger event classes."""

    def test_hotkey_trigger_wait_for_release(self):
        """Test hotkey trigger waits for key release."""
        trigger = HotkeyTriggerEvent()

        # Start waiting in a thread
        result = []

        def wait_thread():
            result.append(trigger.wait_for_completion(timeout=1.0))

        thread = threading.Thread(target=wait_thread)
        thread.start()

        # Signal release after a short delay
        time.sleep(0.1)
        trigger.signal_release()

        thread.join()
        assert result[0] is True

    def test_hotkey_trigger_timeout(self):
        """Test hotkey trigger times out if not released."""
        trigger = HotkeyTriggerEvent()

        # Wait with short timeout, without releasing
        result = trigger.wait_for_completion(timeout=0.1)

        assert result is False

    def test_timer_trigger_completes(self):
        """Test timer trigger waits for specified duration."""
        duration = 0.1
        trigger = TimerTriggerEvent(duration)

        start_time = time.time()
        result = trigger.wait_for_completion()
        elapsed = time.time() - start_time

        assert result is True
        assert elapsed >= duration
        assert elapsed < duration + 0.1  # Some tolerance

    def test_timer_trigger_respects_timeout(self):
        """Test timer trigger respects timeout parameter."""
        trigger = TimerTriggerEvent(duration=1.0)

        start_time = time.time()
        result = trigger.wait_for_completion(timeout=0.1)
        elapsed = time.time() - start_time

        assert result is True
        assert elapsed < 0.2  # Should timeout before full duration

    def test_programmatic_trigger_returns_immediately(self):
        """Test programmatic trigger returns immediately."""
        trigger = ProgrammaticTriggerEvent()

        start_time = time.time()
        result = trigger.wait_for_completion()
        elapsed = time.time() - start_time

        assert result is True
        assert elapsed < 0.01  # Should be nearly instant


class MockIconController:
    """Mock icon controller for testing."""

    def __init__(self):
        self.state_history = []

    def set_icon(self, state: str, duration: Optional[float] = None):
        self.state_history.append(("set", state, duration))

    def start_flashing(self, state: str):
        self.state_history.append(("flash_start", state))

    def stop_flashing(self):
        self.state_history.append(("flash_stop",))


class TestPipelineContext:
    """Tests for PipelineContext class."""

    def test_context_initialization(self):
        """Test context initializes with correct values."""
        icon_controller = MockIconController()
        trigger = ProgrammaticTriggerEvent()

        context = PipelineContext(
            config={"key": "value"},
            icon_controller=icon_controller,
            trigger_event=trigger,
        )

        assert context.config == {"key": "value"}
        assert context.icon_controller is icon_controller
        assert context.trigger_event is trigger
        assert isinstance(context.cancel_requested, threading.Event)
        assert context.metadata == {}

    def test_context_with_metadata(self):
        """Test context accepts custom metadata."""
        context = PipelineContext(
            config={},
            icon_controller=MockIconController(),
            metadata={"speech_processor": "mock_processor"},
        )

        assert "speech_processor" in context.metadata
        assert context.metadata["speech_processor"] == "mock_processor"


class TestResourceManager:
    """Tests for ResourceManager class."""

    def test_acquire_and_release_single_resource(self):
        """Test acquiring and releasing a single resource."""
        manager = ResourceManager()
        pipeline_id = "test_pipeline_1"

        # Acquire resource
        result = manager.acquire(pipeline_id, {Resource.AUDIO_INPUT}, blocking=False)
        assert result is True

        # Resource should be locked
        assert Resource.AUDIO_INPUT in manager.get_blocked_by({Resource.AUDIO_INPUT})

        # Release resource
        manager.release(pipeline_id)

        # Resource should be free
        assert len(manager.get_blocked_by({Resource.AUDIO_INPUT})) == 0

    def test_acquire_multiple_resources_atomically(self):
        """Test acquiring multiple resources atomically."""
        manager = ResourceManager()
        pipeline_id = "test_pipeline_2"

        resources = {Resource.AUDIO_INPUT, Resource.KEYBOARD}
        result = manager.acquire(pipeline_id, resources, blocking=False)

        assert result is True
        assert manager.get_blocked_by(resources) == resources

        manager.release(pipeline_id)
        assert len(manager.get_blocked_by(resources)) == 0

    def test_concurrent_pipeline_different_resources(self):
        """Test two pipelines can run with different resources."""
        manager = ResourceManager()

        # Pipeline 1 acquires audio
        result1 = manager.acquire("pipeline_1", {Resource.AUDIO_INPUT}, blocking=False)
        assert result1 is True

        # Pipeline 2 can acquire keyboard (different resource)
        result2 = manager.acquire("pipeline_2", {Resource.KEYBOARD}, blocking=False)
        assert result2 is True

        # Both should be holding their resources
        assert manager.get_blocked_by({Resource.AUDIO_INPUT}) == {Resource.AUDIO_INPUT}
        assert manager.get_blocked_by({Resource.KEYBOARD}) == {Resource.KEYBOARD}

        manager.release("pipeline_1")
        manager.release("pipeline_2")

    def test_concurrent_pipeline_same_resource_fails(self):
        """Test two pipelines cannot acquire same resource."""
        manager = ResourceManager()

        # Pipeline 1 acquires audio
        result1 = manager.acquire("pipeline_1", {Resource.AUDIO_INPUT}, blocking=False)
        assert result1 is True

        # Pipeline 2 cannot acquire audio (same resource)
        result2 = manager.acquire("pipeline_2", {Resource.AUDIO_INPUT}, blocking=False)
        assert result2 is False

        # Only pipeline 1 should hold the resource
        assert manager.get_blocked_by({Resource.AUDIO_INPUT}) == {Resource.AUDIO_INPUT}

        manager.release("pipeline_1")

        # Now pipeline 2 can acquire it
        result3 = manager.acquire("pipeline_2", {Resource.AUDIO_INPUT}, blocking=False)
        assert result3 is True

        manager.release("pipeline_2")

    def test_atomic_acquisition_all_or_nothing(self):
        """Test atomic acquisition releases all if one fails."""
        manager = ResourceManager()

        # Pipeline 1 acquires keyboard
        manager.acquire("pipeline_1", {Resource.KEYBOARD}, blocking=False)

        # Pipeline 2 tries to acquire both audio and keyboard
        # Should fail because keyboard is taken, and should not hold audio either
        result = manager.acquire(
            "pipeline_2", {Resource.AUDIO_INPUT, Resource.KEYBOARD}, blocking=False
        )
        assert result is False

        # Audio should still be available (not locked by pipeline 2)
        blocked = manager.get_blocked_by({Resource.AUDIO_INPUT, Resource.KEYBOARD})
        assert blocked == {Resource.KEYBOARD}  # Only keyboard is locked

        manager.release("pipeline_1")


class TestStageRegistry:
    """Tests for StageRegistry class."""

    def test_register_stage_with_decorator(self):
        """Test registering a stage with decorator."""
        registry = StageRegistry()

        @registry.register
        class TestStage:
            """Test stage"""

            required_resources = {Resource.AUDIO_INPUT}

            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: None, context: PipelineContext) -> str:
                return "test"

        metadata = registry.get("TestStage")
        assert metadata.name == "TestStage"
        assert metadata.input_type == type(None)
        assert metadata.output_type == str
        assert metadata.description == "Test stage"
        assert metadata.required_resources == {Resource.AUDIO_INPUT}

    def test_register_duplicate_stage_fails(self):
        """Test registering duplicate stage name fails."""
        registry = StageRegistry()

        @registry.register
        class DuplicateStage:
            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: None, context: PipelineContext) -> str:
                return "test"

        with pytest.raises(ValueError, match="already registered"):

            @registry.register
            class DuplicateStage:
                def __init__(self, config: dict, metadata: dict):
                    pass

                def execute(self, input_data: None, context: PipelineContext) -> str:
                    return "test"

    def test_get_unknown_stage_fails(self):
        """Test getting unknown stage raises error."""
        registry = StageRegistry()

        with pytest.raises(ValueError, match="Unknown stage"):
            registry.get("nonexistent")

    def test_validate_compatible_pipeline(self):
        """Test validating a compatible pipeline succeeds."""
        registry = StageRegistry()

        @registry.register
        class Stage1:
            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: None, context: PipelineContext) -> str:
                return "test"

        @registry.register
        class Stage2:
            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: str, context: PipelineContext) -> int:
                return len(input_data)

        # Should not raise
        registry.validate_pipeline(["Stage1", "Stage2"])

    def test_validate_incompatible_pipeline_fails(self):
        """Test validating incompatible pipeline fails."""
        registry = StageRegistry()

        @registry.register
        class Stage1:
            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: None, context: PipelineContext) -> str:
                return "test"

        @registry.register
        class Stage2:
            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: int, context: PipelineContext) -> str:
                return str(input_data)

        # Should raise type mismatch error
        with pytest.raises(TypeError, match="Type mismatch"):
            registry.validate_pipeline(["Stage1", "Stage2"])

    def test_validate_empty_pipeline_fails(self):
        """Test validating empty pipeline fails."""
        registry = StageRegistry()

        with pytest.raises(ValueError, match="at least one stage"):
            registry.validate_pipeline([])

    def test_list_stages(self):
        """Test listing all registered stages."""
        registry = StageRegistry()

        @registry.register
        class Stage1:
            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: None, context: PipelineContext) -> str:
                return "test"

        @registry.register
        class Stage2:
            def __init__(self, config: dict, metadata: dict):
                pass

            def execute(self, input_data: str, context: PipelineContext) -> int:
                return 42

        stages = registry.list_stages()
        assert "Stage1" in stages
        assert "Stage2" in stages
        assert len(stages) == 2
