"""Resource management for pipeline execution.

The ResourceManager provides fine-grained locking of system resources (audio device,
keyboard, clipboard) to allow concurrent pipeline execution when resources don't conflict.
"""

import threading
from enum import Enum
from typing import Dict, Set

from loguru import logger


class Resource(Enum):
    """Available system resources that stages may lock.

    Resources are locked exclusively - only one pipeline can use a resource at a time.
    This enables concurrent pipeline execution when resources don't conflict.
    """

    AUDIO_INPUT = "audio_input"  # Microphone/audio capture device
    KEYBOARD = "keyboard"  # Virtual keyboard for typing
    CLIPBOARD = "clipboard"  # System clipboard


class ResourceManager:
    """Manages resource locks for pipeline execution.

    Uses fine-grained resource locking instead of a global pipeline lock,
    allowing multiple pipelines to run concurrently if they don't conflict.
    """

    def __init__(self):
        """Initialize the resource manager with locks for each resource."""
        self._locks: Dict[Resource, threading.Lock] = {
            resource: threading.Lock() for resource in Resource
        }
        self._pipeline_resources: Dict[str, Set[Resource]] = (
            {}
        )  # pipeline_id -> set of acquired resources

    def get_required_resources(self, stages: list[str]) -> Set[Resource]:
        """Determine which resources a pipeline needs based on its stages.

        Uses the stage registry to look up resource requirements.

        Args:
            stages: List of stage names in the pipeline

        Returns:
            Set of resources required by the pipeline
        """
        # Import here to avoid circular dependency
        from .stage_registry import STAGE_REGISTRY

        resources = set()
        for stage_name in stages:
            stage_metadata = STAGE_REGISTRY.get(stage_name)
            resources.update(stage_metadata.required_resources)
        return resources

    def can_acquire(self, pipeline_id: str, resources: Set[Resource]) -> bool:
        """Check if all required resources are available (non-blocking).

        WARNING: This method should NOT be used as a pre-check before calling acquire()
        due to race conditions. Instead, call acquire() directly with blocking=False.
        This method is kept for informational/debugging purposes only.

        Args:
            pipeline_id: Unique identifier for this pipeline execution
            resources: Set of resources to check

        Returns:
            True if all resources are currently available
        """
        return all(not lock.locked() for lock in (self._locks[r] for r in resources))

    def acquire(
        self,
        pipeline_id: str,
        resources: Set[Resource],
        blocking: bool = True,
        timeout: float | None = None,
    ) -> bool:
        """Acquire all required resources atomically.

        Args:
            pipeline_id: Unique identifier for this pipeline execution
            resources: Set of resources to acquire
            blocking: If False, return immediately if resources unavailable
            timeout: Maximum time to wait for resources (if blocking=True)

        Returns:
            True if all resources acquired, False otherwise
        """
        acquired = []

        try:
            # Try to acquire all locks atomically
            for resource in resources:
                # Handle Lock.acquire() signature: timeout can't be passed when blocking=False
                if blocking and timeout is not None:
                    success = self._locks[resource].acquire(
                        blocking=True, timeout=timeout
                    )
                else:
                    success = self._locks[resource].acquire(blocking=blocking)

                if not success:
                    # Failed to acquire this lock, release all previous ones
                    for prev_resource in acquired:
                        self._locks[prev_resource].release()
                    logger.debug(
                        f"Pipeline {pipeline_id} failed to acquire {resource.value}"
                    )
                    return False
                acquired.append(resource)
                logger.debug(f"Pipeline {pipeline_id} acquired {resource.value}")

            # Successfully acquired all resources
            self._pipeline_resources[pipeline_id] = resources
            logger.debug(
                f"Pipeline {pipeline_id} successfully acquired all resources: {[r.value for r in resources]}"
            )
            return True

        except Exception as e:
            # On any error, release all acquired locks
            logger.error(f"Error acquiring resources for pipeline {pipeline_id}: {e}")
            for resource in acquired:
                self._locks[resource].release()
            raise

    def release(self, pipeline_id: str):
        """Release all resources held by a pipeline.

        Args:
            pipeline_id: Unique identifier for the pipeline execution
        """
        if pipeline_id not in self._pipeline_resources:
            logger.debug(f"Pipeline {pipeline_id} has no resources to release")
            return

        resources = self._pipeline_resources.pop(pipeline_id)
        for resource in resources:
            self._locks[resource].release()
            logger.debug(f"Pipeline {pipeline_id} released {resource.value}")

    def get_blocked_by(self, resources: Set[Resource]) -> Set[Resource]:
        """Return which of the requested resources are currently locked.

        Args:
            resources: Set of resources to check

        Returns:
            Subset of resources that are currently locked
        """
        return {r for r in resources if self._locks[r].locked()}
