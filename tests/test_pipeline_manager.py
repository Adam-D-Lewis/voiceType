"""Unit tests for PipelineManager."""

import pytest

from voicetype.pipeline import PipelineManager, ResourceManager


class MockIconController:
    """Mock icon controller for testing."""

    def set_icon(self, state: str, duration: float = None):
        pass

    def start_flashing(self, state: str):
        pass

    def stop_flashing(self):
        pass


class TestPipelineManagerStageResolution:
    """Tests for PipelineManager stage resolution logic."""

    def test_resolve_direct_class_reference_with_config(self):
        """Test resolving direct class name with default config."""
        resource_manager = ResourceManager()
        icon_controller = MockIconController()
        manager = PipelineManager(
            resource_manager=resource_manager,
            icon_controller=icon_controller,
        )

        # Stage definitions without 'class' field (direct class reference)
        stage_definitions = {
            "RecordAudio": {
                "minimum_duration": 0.5,
            },
            "Transcribe": {
                "provider": "local",
            },
        }

        # Pipeline referencing stages by class name
        pipelines_config = [
            {
                "name": "test",
                "enabled": True,
                "hotkey": "<pause>",
                "stages": ["RecordAudio", "Transcribe"],
            }
        ]

        # Should not raise - stages exist in definitions
        manager.load_pipelines(pipelines_config, stage_definitions=stage_definitions)

        # Verify pipeline was loaded
        pipeline = manager.get_pipeline_by_name("test")
        assert pipeline is not None
        assert pipeline.name == "test"

    def test_resolve_named_instance_with_class_field(self):
        """Test resolving named instance with 'class' field."""
        resource_manager = ResourceManager()
        icon_controller = MockIconController()
        manager = PipelineManager(
            resource_manager=resource_manager,
            icon_controller=icon_controller,
        )

        # Named instance with 'class' field
        stage_definitions = {
            "RecordAudio_custom": {
                "class": "RecordAudio",
                "minimum_duration": 1.0,
            },
            "Transcribe_cloud": {
                "class": "Transcribe",
                "provider": "litellm",
            },
        }

        pipelines_config = [
            {
                "name": "custom_pipeline",
                "enabled": True,
                "hotkey": "<f12>",
                "stages": ["RecordAudio_custom", "Transcribe_cloud"],
            }
        ]

        # Should not raise
        manager.load_pipelines(pipelines_config, stage_definitions=stage_definitions)

        pipeline = manager.get_pipeline_by_name("custom_pipeline")
        assert pipeline is not None

    def test_resolve_stage_not_in_definitions(self):
        """Test that stage not in definitions still works (uses stage defaults)."""
        resource_manager = ResourceManager()
        icon_controller = MockIconController()
        manager = PipelineManager(
            resource_manager=resource_manager,
            icon_controller=icon_controller,
        )

        # Empty stage definitions
        stage_definitions = {}

        pipelines_config = [
            {
                "name": "default",
                "enabled": True,
                "hotkey": "<pause>",
                "stages": ["RecordAudio", "Transcribe"],
            }
        ]

        # Should not raise - stages will use their own defaults
        manager.load_pipelines(pipelines_config, stage_definitions=stage_definitions)

        pipeline = manager.get_pipeline_by_name("default")
        assert pipeline is not None

    def test_mixed_stage_references(self):
        """Test pipeline with mix of direct references and named instances."""
        resource_manager = ResourceManager()
        icon_controller = MockIconController()
        manager = PipelineManager(
            resource_manager=resource_manager,
            icon_controller=icon_controller,
        )

        stage_definitions = {
            "RecordAudio": {
                "minimum_duration": 0.25,
            },
            "Transcribe_custom": {
                "class": "Transcribe",
                "provider": "litellm",
            },
        }

        pipelines_config = [
            {
                "name": "mixed",
                "enabled": True,
                "hotkey": "<pause>",
                "stages": ["RecordAudio", "Transcribe_custom", "TypeText"],
            }
        ]

        # Should work - RecordAudio uses default config, Transcribe_custom uses
        # named instance, TypeText uses stage's own defaults
        manager.load_pipelines(pipelines_config, stage_definitions=stage_definitions)

        pipeline = manager.get_pipeline_by_name("mixed")
        assert pipeline is not None

    def test_hotkey_conflict_raises_error(self):
        """Test that duplicate hotkeys raise an error."""
        resource_manager = ResourceManager()
        icon_controller = MockIconController()
        manager = PipelineManager(
            resource_manager=resource_manager,
            icon_controller=icon_controller,
        )

        pipelines_config = [
            {
                "name": "pipeline1",
                "enabled": True,
                "hotkey": "<pause>",
                "stages": ["RecordAudio"],
            },
            {
                "name": "pipeline2",
                "enabled": True,
                "hotkey": "<pause>",  # Duplicate!
                "stages": ["RecordAudio"],
            },
        ]

        with pytest.raises(ValueError, match="Hotkey conflict"):
            manager.load_pipelines(pipelines_config)

    def test_disabled_pipeline_no_hotkey_conflict(self):
        """Test that disabled pipelines don't cause hotkey conflicts."""
        resource_manager = ResourceManager()
        icon_controller = MockIconController()
        manager = PipelineManager(
            resource_manager=resource_manager,
            icon_controller=icon_controller,
        )

        pipelines_config = [
            {
                "name": "pipeline1",
                "enabled": True,
                "hotkey": "<pause>",
                "stages": ["RecordAudio"],
            },
            {
                "name": "pipeline2",
                "enabled": False,  # Disabled
                "hotkey": "<pause>",
                "stages": ["RecordAudio"],
            },
        ]

        # Should not raise - disabled pipeline doesn't count
        manager.load_pipelines(pipelines_config)

        enabled = manager.list_enabled_pipelines()
        assert len(enabled) == 1
        assert "pipeline1" in enabled
