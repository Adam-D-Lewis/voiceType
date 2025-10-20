"""Pipeline executor for running pipeline stages with resource management and cleanup.

The PipelineExecutor manages the execution of individual pipeline stages, handling:
- Resource acquisition and release
- Stage execution with error handling
- Temporary resource cleanup
- Cancellation support
"""

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from .context import IconController, PipelineContext
from .resource_manager import Resource, ResourceManager
from .stage_registry import STAGE_REGISTRY
from .trigger_events import TriggerEvent


class PipelineExecutor:
    """Manages pipeline execution with thread pool and resource locking.

    Provides:
    - Non-blocking pipeline execution via thread pool
    - Resource-based locking for concurrent pipeline support
    - Automatic cleanup of temporary resources
    - Cancellation support
    """

    def __init__(
        self,
        resource_manager: ResourceManager,
        icon_controller: IconController,
        max_workers: int = 4,
    ):
        """Initialize the pipeline executor.

        Args:
            resource_manager: Manager for resource locking
            icon_controller: Controller for system tray icon
            max_workers: Maximum number of concurrent pipeline workers
        """
        self.resource_manager = resource_manager
        self.icon_controller = icon_controller
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="pipeline"
        )
        self.active_pipelines: Dict[str, Future] = {}  # pipeline_id -> Future
        self._shutdown = False

    def execute_pipeline(
        self,
        pipeline_name: str,
        stages: List[Dict[str, Any]],
        trigger_event: Optional[TriggerEvent] = None,
        initial_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Execute a pipeline asynchronously.

        Args:
            pipeline_name: Name of the pipeline for logging
            stages: List of stage configurations (each with 'func' key)
            trigger_event: Optional trigger event (hotkey/timer)
            initial_metadata: Optional initial metadata for the pipeline

        Returns:
            Pipeline ID if execution started, None if resources unavailable
        """
        if self._shutdown:
            logger.warning("Pipeline executor is shut down, cannot execute pipeline")
            return None

        # Generate unique ID for this pipeline execution
        pipeline_id = str(uuid.uuid4())

        # Extract stage names
        stage_names = [stage["stage"] for stage in stages]

        # Determine required resources
        required_resources = self.resource_manager.get_required_resources(stage_names)

        # Try to acquire resources (non-blocking)
        if not self.resource_manager.acquire(
            pipeline_id, required_resources, blocking=False
        ):
            # Resources unavailable
            blocked = self.resource_manager.get_blocked_by(required_resources)
            logger.warning(
                f"Cannot start pipeline '{pipeline_name}': resources {[r.value for r in blocked]} in use"
            )
            return None

        # Submit to thread pool (returns immediately)
        future = self.executor.submit(
            self._execute_pipeline,
            pipeline_id,
            pipeline_name,
            stages,
            trigger_event,
            initial_metadata or {},
        )

        # Track active pipeline
        self.active_pipelines[pipeline_id] = future

        # Add callback for cleanup
        future.add_done_callback(lambda f: self._on_pipeline_complete(pipeline_id, f))

        logger.info(f"Started pipeline '{pipeline_name}' (id={pipeline_id})")
        return pipeline_id

    def _execute_pipeline(
        self,
        pipeline_id: str,
        pipeline_name: str,
        stages: List[Dict[str, Any]],
        trigger_event: Optional[TriggerEvent],
        metadata: Dict[str, Any],
    ):
        """Execute pipeline stages sequentially (runs on worker thread).

        This method runs on the thread pool worker and can block for as long
        as needed. It will not affect the hotkey listener responsiveness.

        Args:
            pipeline_id: Unique identifier for this execution
            pipeline_name: Name of the pipeline for logging
            stages: List of stage configurations
            trigger_event: Optional trigger event
            metadata: Initial metadata dictionary
        """
        # Create pipeline context
        context = PipelineContext(
            config={},
            icon_controller=self.icon_controller,
            trigger_event=trigger_event,
            cancel_requested=threading.Event(),
            metadata=metadata,
        )

        result = None
        stage_instances = []  # Track stage instances for cleanup

        try:
            for stage_config in stages:
                # Check for cancellation
                if context.cancel_requested.is_set():
                    logger.info(f"Pipeline '{pipeline_name}' cancelled")
                    return

                stage_name = stage_config["stage"]
                logger.debug(f"[{pipeline_name}] Starting stage: {stage_name}")

                # Get stage class from registry
                stage_metadata = STAGE_REGISTRY.get(stage_name)
                stage_class = stage_metadata.stage_class

                # Extract stage-specific config (remove 'func' key)
                stage_specific_config = {
                    k: v for k, v in stage_config.items() if k != "func"
                }

                # Instantiate stage with config and dependencies from metadata
                # Each stage is responsible for extracting what it needs from metadata
                stage_instance = stage_class(
                    config=stage_specific_config, metadata=metadata
                )
                stage_instances.append(stage_instance)

                # Update context with stage-specific config
                context.config = stage_specific_config

                # Execute stage (may block for seconds)
                result = stage_instance.execute(result, context)

                logger.debug(f"[{pipeline_name}] Stage {stage_name} completed")

            logger.info(f"Pipeline '{pipeline_name}' completed successfully")

        except Exception as e:
            logger.error(
                f"Pipeline '{pipeline_name}' failed at stage {stage_name}: {e}",
                exc_info=True,
            )
            self.icon_controller.set_icon("error")
            raise

        finally:
            # CRITICAL: Cleanup stage instances in reverse order
            # Stages own their resources and handle cleanup via cleanup() method
            for stage_instance in reversed(stage_instances):
                if hasattr(stage_instance, "cleanup") and callable(
                    stage_instance.cleanup
                ):
                    try:
                        stage_instance.cleanup()
                    except Exception as e:
                        logger.warning(f"Stage cleanup failed: {e}", exc_info=True)

            # Release acquired resources
            self.resource_manager.release(pipeline_id)

            # Reset icon
            self.icon_controller.set_icon("idle")

    def _on_pipeline_complete(self, pipeline_id: str, future: Future):
        """Callback when pipeline completes (runs on worker thread).

        Args:
            pipeline_id: Pipeline identifier
            future: Future object for the pipeline execution
        """
        try:
            future.result()  # Re-raises any exceptions
        except Exception as e:
            logger.error(f"Pipeline {pipeline_id} failed with exception: {e}")
        finally:
            # Remove from active pipelines
            self.active_pipelines.pop(pipeline_id, None)

    def cancel_pipeline(self, pipeline_id: str):
        """Cancel a specific running pipeline.

        Args:
            pipeline_id: Pipeline identifier to cancel
        """
        if pipeline_id in self.active_pipelines:
            future = self.active_pipelines[pipeline_id]
            if not future.done():
                future.cancel()
                logger.info(f"Cancelled pipeline {pipeline_id}")

    def shutdown(self, timeout: float = 5.0):
        """Gracefully shutdown pipeline executor with timeout.

        Args:
            timeout: Maximum time to wait for active pipelines to complete
        """
        logger.info("Shutting down pipeline executor...")
        self._shutdown = True

        # Cancel all pending futures
        for future in self.active_pipelines.values():
            if not future.done():
                future.cancel()

        # Wait for active pipelines with timeout
        import time

        start = time.time()
        for pipeline_id, future in list(self.active_pipelines.items()):
            remaining = timeout - (time.time() - start)
            if remaining <= 0:
                logger.warning("Shutdown timeout exceeded, forcing exit")
                break
            try:
                future.result(timeout=remaining)
            except Exception as e:
                logger.error(f"Pipeline {pipeline_id} failed during shutdown: {e}")

        # Final executor shutdown (non-blocking)
        self.executor.shutdown(wait=False, cancel_futures=True)
        logger.info("Pipeline executor shutdown complete")
