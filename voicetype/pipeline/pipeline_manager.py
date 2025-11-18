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

    def load_pipelines(
        self,
        pipelines_config: List[Dict[str, Any]],
        stage_definitions: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """Load and validate pipeline configurations.

        Args:
            pipelines_config: List of pipeline configurations from settings
            stage_definitions: Optional dict of named stage instances from settings

        Raises:
            ValueError: If hotkey conflicts or invalid configurations detected
            TypeError: If pipeline stages have type mismatches
        """
        logger.info(f"Loading {len(pipelines_config)} pipeline(s)...")

        stage_definitions = stage_definitions or {}

        for config in pipelines_config:
            name = config["name"]
            enabled = config.get("enabled", True)
            hotkey = config["hotkey"]
            stages_input = config["stages"]

            # Validate hotkey uniqueness (only for enabled pipelines)
            if enabled and hotkey in self.hotkey_to_pipeline:
                conflicting = self.hotkey_to_pipeline[hotkey]
                raise ValueError(
                    f"Hotkey conflict: '{hotkey}' is used by both "
                    f"'{conflicting}' and '{name}'"
                )

            # Resolve stages: convert stage names to full stage configs
            stages = self._resolve_stages(stages_input, stage_definitions)

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

    def _resolve_stages(
        self,
        stages_input: List[Any],
        stage_definitions: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Resolve stage references to full stage configurations.

        Args:
            stages_input: List of stage class names or instance names (strings)
            stage_definitions: Named stage instance definitions

        Returns:
            List of resolved stage configurations

        Raises:
            ValueError: If stage instance not found in definitions
        """
        resolved = []

        for stage_ref in stages_input:
            if not isinstance(stage_ref, str):
                raise ValueError(
                    f"Stage references must be strings (stage class or instance names), "
                    f"got {type(stage_ref).__name__}. "
                    f"Please define stages in [stage_configs.{stage_ref if isinstance(stage_ref, str) else 'YourStageName'}] "
                    f"section and reference them by name in the pipeline."
                )

            # Check if this is a named instance or a direct class reference
            if stage_ref in stage_definitions:
                stage_def = stage_definitions[stage_ref]

                # Check if this is a named instance (has "stage_class" or "class" field) or direct class reference
                # Support both "stage_class" and "class" for flexibility
                stage_class_key = (
                    "stage_class"
                    if "stage_class" in stage_def
                    else "class" if "class" in stage_def else None
                )

                if stage_class_key:
                    # Named instance - use the specific configuration with different class name
                    stage_class = stage_def[stage_class_key]
                    stage_config = {"stage": stage_class}
                    stage_config.update(
                        {k: v for k, v in stage_def.items() if k != stage_class_key}
                    )
                else:
                    # Direct class reference with default config
                    stage_config = {"stage": stage_ref}
                    stage_config.update(stage_def)
            else:
                # No config found - use just the class name
                # The stage itself will use its own defaults
                stage_config = {"stage": stage_ref}

            resolved.append(stage_config)

        return resolved

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
    ) -> Optional[str]:
        """Trigger a pipeline execution.

        Args:
            pipeline_name: Name of the pipeline to execute
            trigger_event: Optional trigger event

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
