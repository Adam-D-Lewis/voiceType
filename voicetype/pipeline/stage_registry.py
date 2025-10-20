"""Stage registry for type-safe pipeline stage registration and validation.

The stage registry provides:
- Type-safe registration of pipeline stage classes
- Validation of stage execute() method signatures
- Pipeline type compatibility checking
- Resource requirement tracking
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol, Set, TypeVar, get_type_hints

from loguru import logger

from .resource_manager import Resource

# Type variables for stage inputs and outputs
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class PipelineStage(Protocol[TInput, TOutput]):
    """Protocol for type-safe pipeline stages.

    All pipeline stages must implement this protocol:
    - execute() method that takes input_data and context, returns output
    - Optional cleanup() method for resource cleanup
    """

    def execute(self, input_data: TInput, context: Any) -> TOutput:
        """Execute the stage logic.

        Args:
            input_data: Output from the previous stage (None for first stage)
            context: PipelineContext containing config, icon_controller, trigger_event, etc.

        Returns:
            Output data to pass to the next stage

        Raises:
            Exception: Any errors should be raised and handled by pipeline manager
        """
        ...

    def cleanup(self) -> None:
        """Clean up any resources held by this stage (optional).

        Called by pipeline manager in finally block after pipeline completes.
        Stages should implement this if they create resources that need cleanup.
        """
        ...


@dataclass
class StageMetadata:
    """Metadata about a registered stage.

    Tracks the stage class, type information, description, and resource requirements.
    """

    name: str
    stage_class: type  # Changed from 'function' to 'stage_class'
    input_type: type
    output_type: type
    description: str
    required_resources: Set[Resource]


class StageRegistry:
    """Registry for pipeline stages with type validation.

    Provides decorator-based registration and validates stage class execute()
    method signatures at registration time. Also validates pipeline type
    compatibility at startup.
    """

    def __init__(self):
        """Initialize an empty stage registry."""
        self._stages: Dict[str, StageMetadata] = {}

    def register(self, stage_class: type = None):
        """Decorator to register a stage class, auto-inferring type information.

        The decorator automatically infers:
        - name: From the class name directly (no transformation)
        - input_type: From execute() method's input_data parameter type hint
        - output_type: From execute() method's return type hint
        - description: From the class docstring
        - required_resources: From the class variable 'required_resources'

        Returns:
            Decorator function that registers the stage class

        Raises:
            TypeError: If execute() method is missing or has invalid signature
            ValueError: If stage name is already registered

        Example:
            @STAGE_REGISTRY.register
            class RecordAudio:
                '''Record audio until trigger completes'''
                required_resources = {Resource.AUDIO_INPUT}

                def execute(self, input_data: None, context: PipelineContext) -> Optional[str]:
                    ...
        """

        def decorator(cls: type) -> type:
            # Use class name directly - no transformation
            name = cls.__name__

            # Check if stage already registered
            if name in self._stages:
                existing = self._stages[name]
                raise ValueError(
                    f"Stage '{name}' is already registered. "
                    f"Existing: {existing.stage_class.__module__}.{existing.stage_class.__name__}"
                )

            # Validate that the class has an execute() method
            execute_method = getattr(cls, "execute", None)
            if not execute_method or not callable(execute_method):
                raise TypeError(
                    f"Stage class {cls.__name__} must have an execute() method"
                )

            # Get type hints from execute() method
            hints = get_type_hints(execute_method)
            input_type = hints.get("input_data")
            output_type = hints.get("return")

            if input_type is None:
                raise TypeError(
                    f"Stage class {cls.__name__} execute() method must have "
                    f"type hint for 'input_data' parameter"
                )
            if output_type is None:
                raise TypeError(
                    f"Stage class {cls.__name__} execute() method must have "
                    f"return type hint"
                )

            # Get metadata from class attributes
            required_resources = getattr(cls, "required_resources", set())
            description = cls.__doc__ or ""

            # Register the stage class
            self._stages[name] = StageMetadata(
                name=name,
                stage_class=cls,
                input_type=input_type,
                output_type=output_type,
                description=description.strip(),
                required_resources=required_resources,
            )

            logger.debug(
                f"Registered stage class '{name}' with "
                f"input={input_type}, output={output_type}, "
                f"resources={required_resources}"
            )

            return cls

        # Allow both @register and @register()
        if stage_class is not None:
            return decorator(stage_class)
        return decorator

    def get(self, name: str) -> StageMetadata:
        """Get stage metadata by name (PascalCase).

        Args:
            name: Stage name to look up (e.g., 'RecordAudio', 'Transcribe')

        Returns:
            StageMetadata for the stage

        Raises:
            ValueError: If stage name is not registered
        """
        if name not in self._stages:
            available = list(self._stages.keys())
            raise ValueError(f"Unknown stage: '{name}'. Available stages: {available}")
        return self._stages[name]

    def list_stages(self) -> list[str]:
        """Get a list of all registered stage names.

        Returns:
            List of stage names
        """
        return list(self._stages.keys())

    def validate_pipeline(self, stage_names: list[str]) -> None:
        """Validate that stages in a pipeline are compatible.

        Checks:
        - All stage names are registered
        - Stage output types match next stage's input types

        Args:
            stage_names: List of stage names in the pipeline

        Raises:
            ValueError: If pipeline has no stages or stage names are unknown
            TypeError: If stage output type doesn't match next stage's input type
        """
        if not stage_names:
            raise ValueError("Pipeline must have at least one stage")

        # Validate all stages exist
        stages = [self.get(name) for name in stage_names]

        # Validate type compatibility between consecutive stages
        for i in range(len(stages) - 1):
            current_output = stages[i].output_type
            next_input = stages[i + 1].input_type

            if current_output != next_input:
                raise TypeError(
                    f"Type mismatch in pipeline: stage '{stages[i].name}' outputs "
                    f"{current_output} but stage '{stages[i + 1].name}' expects {next_input}"
                )

        logger.debug(
            f"Pipeline validation successful: {' -> '.join(s.name for s in stages)}"
        )


# Global registry instance
STAGE_REGISTRY = StageRegistry()
