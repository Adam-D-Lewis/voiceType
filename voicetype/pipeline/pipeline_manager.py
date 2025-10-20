"""Pipeline manager for loading, validating, and managing multiple pipelines.

The PipelineManager:
- Loads pipeline configurations from settings
- Validates pipeline compatibility at startup
- Manages pipeline execution via PipelineExecutor
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from .context import IconController
from .pipeline_executor import PipelineExecutor
from .resource_manager import ResourceManager
from .stage_registry import STAGE_REGISTRY
from .trigger_events import TriggerEvent


class PipelineConfig:
    """Configuration for a single pipeline."""

    def __init__(
        self,
        name: str,
        enabled: bool,
        hotkey: str,
        stages: List[Dict[str, Any]],
    ):
        """Initialize pipeline configuration.

        Args:
            name: Unique pipeline name
            enabled: Whether pipeline is enabled
            hotkey: Hotkey string to trigger this pipeline
            stages: List of stage configurations
        """
        self.name = name
        self.enabled = enabled
        self.hotkey = hotkey
        self.stages = stages

    def __repr__(self):
        return (
            f"PipelineConfig(name={self.name}, enabled={self.enabled}, "
            f"hotkey={self.hotkey}, stages={len(self.stages)})"
        )


class PipelineManager:
    """Manages multiple pipelines and their execution.

    Responsibilities:
    - Load and validate pipeline configurations
    - Detect hotkey conflicts
    - Execute pipelines via PipelineExecutor
    """

    def __init__(
        self,
        resource_manager: ResourceManager,
        icon_controller: IconController,
        max_workers: int = 4,
    ):
        """Initialize the pipeline manager.

        Args:
            resource_manager: Manager for resource locking
            icon_controller: Controller for system tray icon
            max_workers: Maximum concurrent pipeline workers
        """
        self.resource_manager = resource_manager
        self.icon_controller = icon_controller
        self.executor = PipelineExecutor(resource_manager, icon_controller, max_workers)
        self.pipelines: Dict[str, PipelineConfig] = {}
        self.hotkey_to_pipeline: Dict[str, str] = {}  # hotkey -> pipeline_name

    def load_pipelines(self, pipelines_config: List[Dict[str, Any]]):
        """Load and validate pipeline configurations.

        Args:
            pipelines_config: List of pipeline configurations from settings

        Raises:
            ValueError: If hotkey conflicts or invalid configurations detected
            TypeError: If pipeline stages have type mismatches
        """
        logger.info(f"Loading {len(pipelines_config)} pipeline(s)...")

        for config in pipelines_config:
            name = config["name"]
            enabled = config.get("enabled", True)
            hotkey = config["hotkey"]
            stages = config["stages"]

            # Validate hotkey uniqueness
            if hotkey in self.hotkey_to_pipeline:
                conflicting = self.hotkey_to_pipeline[hotkey]
                raise ValueError(
                    f"Hotkey conflict: '{hotkey}' is used by both "
                    f"'{conflicting}' and '{name}'"
                )

            # Extract stage names for validation
            stage_names = [stage["stage"] for stage in stages]

            # Validate pipeline type compatibility
            STAGE_REGISTRY.validate_pipeline(stage_names)

            # Create pipeline config
            pipeline = PipelineConfig(
                name=name, enabled=enabled, hotkey=hotkey, stages=stages
            )

            self.pipelines[name] = pipeline
            if enabled:
                self.hotkey_to_pipeline[hotkey] = name

            logger.info(
                f"Loaded pipeline '{name}': {' -> '.join(stage_names)} "
                f"(hotkey={hotkey}, enabled={enabled})"
            )

        logger.info("All pipelines loaded and validated successfully")

    def get_pipeline_by_name(self, name: str) -> Optional[PipelineConfig]:
        """Get pipeline configuration by name.

        Args:
            name: Pipeline name

        Returns:
            PipelineConfig or None if not found
        """
        return self.pipelines.get(name)

    def get_pipeline_by_hotkey(self, hotkey: str) -> Optional[PipelineConfig]:
        """Get enabled pipeline configuration by hotkey.

        Args:
            hotkey: Hotkey string

        Returns:
            PipelineConfig or None if no enabled pipeline for this hotkey
        """
        pipeline_name = self.hotkey_to_pipeline.get(hotkey)
        if pipeline_name:
            return self.pipelines[pipeline_name]
        return None

    def trigger_pipeline(
        self,
        pipeline_name: str,
        trigger_event: Optional[TriggerEvent] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Trigger a pipeline execution.

        Args:
            pipeline_name: Name of the pipeline to execute
            trigger_event: Optional trigger event
            metadata: Optional initial metadata

        Returns:
            Pipeline execution ID if started, None if resources unavailable
        """
        pipeline = self.get_pipeline_by_name(pipeline_name)
        if not pipeline:
            logger.error(f"Pipeline '{pipeline_name}' not found")
            return None

        if not pipeline.enabled:
            logger.warning(f"Pipeline '{pipeline_name}' is disabled")
            return None

        return self.executor.execute_pipeline(
            pipeline_name=pipeline.name,
            stages=pipeline.stages,
            trigger_event=trigger_event,
            initial_metadata=metadata,
        )

    def list_pipelines(self) -> List[str]:
        """Get list of all pipeline names.

        Returns:
            List of pipeline names
        """
        return list(self.pipelines.keys())

    def list_enabled_pipelines(self) -> List[str]:
        """Get list of enabled pipeline names.

        Returns:
            List of enabled pipeline names
        """
        return [name for name, pipeline in self.pipelines.items() if pipeline.enabled]

    def shutdown(self, timeout: float = 5.0):
        """Shutdown the pipeline manager.

        Args:
            timeout: Maximum time to wait for active pipelines
        """
        logger.info("Shutting down pipeline manager...")
        self.executor.shutdown(timeout)
        logger.info("Pipeline manager shutdown complete")
