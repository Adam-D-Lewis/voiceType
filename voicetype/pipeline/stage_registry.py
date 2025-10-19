"""Stage registry for type-safe pipeline stage registration and validation.

The stage registry provides:
- Type-safe registration of pipeline stages
- Validation of stage function signatures
- Pipeline type compatibility checking
- Resource requirement tracking
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Protocol, Set, TypeVar, get_type_hints

from loguru import logger

from .resource_manager import Resource

# Type variables for stage inputs and outputs
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class StageFunction(Protocol[TInput, TOutput]):
    """Protocol for type-safe pipeline stages.

    All stage functions must follow this signature:
    - Take input_data from the previous stage (or None for first stage)
    - Take a PipelineContext containing configuration and shared state
    - Return output data to pass to the next stage
    """

    def __call__(self, input_data: TInput, context: Any) -> TOutput:
        """Execute a pipeline stage.

        Args:
            input_data: Output from the previous stage (None for first stage)
            context: PipelineContext containing config, icon_controller, trigger_event, etc.

        Returns:
            Output data to pass to the next stage

        Raises:
            Exception: Any errors should be raised and handled by pipeline manager
        """
        ...


@dataclass
class StageMetadata:
    """Metadata about a registered stage.

    Tracks the stage function, type information, description, and resource requirements.
    """

    name: str
    function: Callable
    input_type: type
    output_type: type
    description: str
    required_resources: Set[Resource]


class StageRegistry:
    """Registry for pipeline stages with type validation.

    Provides decorator-based registration and validates stage signatures
    at registration time. Also validates pipeline type compatibility at
    startup.
    """

    def __init__(self):
        """Initialize an empty stage registry."""
        self._stages: Dict[str, StageMetadata] = {}

    def register(
        self,
        name: str,
        input_type: type,
        output_type: type,
        description: str = "",
        required_resources: Optional[Set[Resource]] = None,
    ):
        """Decorator to register a stage with type information.

        Args:
            name: Unique name for the stage
            input_type: Expected input type for the stage
            output_type: Output type produced by the stage
            description: Human-readable description of what the stage does
            required_resources: Set of resources this stage requires

        Returns:
            Decorator function that registers the stage

        Raises:
            TypeError: If function signature doesn't match declared types
            ValueError: If stage name is already registered

        Example:
            @STAGE_REGISTRY.register(
                name="record_audio",
                input_type=type(None),
                output_type=Optional[TemporaryAudioFile],
                description="Record audio until trigger completes",
                required_resources={Resource.AUDIO_INPUT}
            )
            def record_audio(input_data: None, context: PipelineContext) -> Optional[TemporaryAudioFile]:
                ...
        """

        def decorator(func: Callable) -> Callable:
            # Check if stage already registered
            if name in self._stages:
                raise ValueError(
                    f"Stage '{name}' is already registered. "
                    f"Existing: {self._stages[name].function.__module__}.{self._stages[name].function.__name__}"
                )

            # Validate function signature matches declared types
            hints = get_type_hints(func)

            declared_input = hints.get("input_data")
            if declared_input != input_type:
                raise TypeError(
                    f"Stage {name}: declared input_type {input_type} doesn't match "
                    f"function signature {declared_input}"
                )

            declared_output = hints.get("return")
            if declared_output != output_type:
                raise TypeError(
                    f"Stage {name}: declared output_type {output_type} doesn't match "
                    f"function signature {declared_output}"
                )

            # Register the stage
            self._stages[name] = StageMetadata(
                name=name,
                function=func,
                input_type=input_type,
                output_type=output_type,
                description=description,
                required_resources=required_resources or set(),
            )

            logger.debug(
                f"Registered stage '{name}' with input={input_type}, output={output_type}, "
                f"resources={required_resources or set()}"
            )

            return func

        return decorator

    def get(self, name: str) -> StageMetadata:
        """Get stage metadata by name.

        Args:
            name: Stage name to look up

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
