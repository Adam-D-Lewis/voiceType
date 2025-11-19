"""Pipeline executor for running pipeline stages with resource management and cleanup.

The PipelineExecutor manages the execution of individual pipeline stages, handling:
- Resource acquisition and release
- Stage execution with error handling
- Temporary resource cleanup
- Cancellation support
"""

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set

from loguru import logger
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from voicetype.telemetry import get_tracer

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
        app_state=None,
    ):
        """Initialize the pipeline executor.

        Args:
            resource_manager: Manager for resource locking
            icon_controller: Controller for system tray icon
            max_workers: Maximum number of concurrent pipeline workers
            app_state: Optional AppState for checking enabled/disabled state
        """
        self.resource_manager = resource_manager
        self.icon_controller = icon_controller
        self.app_state = app_state
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="pipeline"
        )
        self.active_pipelines: Dict[str, Future] = {}  # pipeline_id -> Future
        self.cancel_events: Dict[str, threading.Event] = (
            {}
        )  # pipeline_id -> cancel_event
        self._shutdown = False

    def execute_pipeline(
        self,
        pipeline_name: str,
        stages: List[Dict[str, Any]],
        trigger_event: Optional[TriggerEvent] = None,
    ) -> Optional[str]:
        """Execute a pipeline asynchronously.

        Args:
            pipeline_name: Name of the pipeline for logging
            stages: List of stage configurations (each with 'func' key)
            trigger_event: Optional trigger event (hotkey/timer)

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

        # Create cancel event for this pipeline
        cancel_event = threading.Event()
        self.cancel_events[pipeline_id] = cancel_event

        # Submit to thread pool (returns immediately)
        future = self.executor.submit(
            self._execute_pipeline,
            pipeline_id,
            pipeline_name,
            stages,
            trigger_event,
            cancel_event,
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
        cancel_event: threading.Event,
    ):
        """Execute pipeline stages sequentially (runs on worker thread).

        This method runs on the thread pool worker and can block for as long
        as needed. It will not affect the hotkey listener responsiveness.

        Args:
            pipeline_id: Unique identifier for this execution
            pipeline_name: Name of the pipeline for logging
            stages: List of stage configurations
            trigger_event: Optional trigger event
            cancel_event: Event to signal cancellation request
        """
        # Get tracer for OpenTelemetry spans
        tracer = get_tracer()

        # Create pipeline context with the shared cancel event
        context = PipelineContext(
            config={},
            icon_controller=self.icon_controller,
            trigger_event=trigger_event,
            cancel_requested=cancel_event,
        )

        result = None
        stage_instances = []  # Track stage instances for cleanup
        pipeline_start_time = time.time()

        # Create top-level pipeline span using context manager for proper nesting
        if tracer is not None:
            pipeline_span = tracer.start_as_current_span(
                f"pipeline.{pipeline_name}",
                attributes={
                    "pipeline.id": pipeline_id,
                    "pipeline.name": pipeline_name,
                    "pipeline.stage_count": len(stages),
                },
            )
        else:
            # No-op context manager if telemetry disabled
            from contextlib import nullcontext

            pipeline_span = nullcontext()

        try:
            # Enter the pipeline span context
            with pipeline_span:
                for stage_index, stage_config in enumerate(stages):
                    # Check for cancellation
                    if context.cancel_requested.is_set():
                        logger.info(f"Pipeline '{pipeline_name}' cancelled")
                        trace.get_current_span().set_status(
                            Status(StatusCode.ERROR, "Cancelled")
                        )
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

                    # Create stage span with configuration as attributes
                    if tracer is not None:
                        # Build attributes with stage config
                        stage_attributes = {
                            "pipeline.id": pipeline_id,
                            "pipeline.name": pipeline_name,
                            "stage.name": stage_name,
                            "stage.index": stage_index,
                        }

                        # Add stage configuration as attributes with "stage.config." prefix
                        for config_key, config_value in stage_specific_config.items():
                            # Convert value to string for OpenTelemetry attribute
                            stage_attributes[f"stage.config.{config_key}"] = str(
                                config_value
                            )

                        stage_span = tracer.start_as_current_span(
                            f"stage.{stage_name}",
                            attributes=stage_attributes,
                        )
                    else:
                        from contextlib import nullcontext

                        stage_span = nullcontext()

                    with stage_span:
                        stage_start_time = time.time()

                        try:

                            # Instantiate stage with config
                            stage_instance = stage_class(config=stage_specific_config)
                            stage_instances.append(stage_instance)

                            # Update context with stage-specific config
                            context.config = stage_specific_config

                            # Execute stage (may block for seconds)
                            result = stage_instance.execute(result, context)

                            # Record stage completion
                            stage_duration = time.time() - stage_start_time
                            current_span = trace.get_current_span()
                            if current_span.is_recording():
                                current_span.set_attribute(
                                    "stage.duration_ms", stage_duration * 1000
                                )
                                current_span.set_status(Status(StatusCode.OK))

                            logger.debug(
                                f"[{pipeline_name}] Stage {stage_name} completed in {stage_duration:.2f}s"
                            )

                        except Exception as e:
                            stage_duration = time.time() - stage_start_time
                            current_span = trace.get_current_span()
                            if current_span.is_recording():
                                current_span.set_attribute(
                                    "stage.duration_ms", stage_duration * 1000
                                )
                                current_span.set_status(
                                    Status(StatusCode.ERROR, str(e))
                                )
                                current_span.record_exception(e)
                            raise

                # Pipeline completed successfully
                pipeline_duration = time.time() - pipeline_start_time
                current_span = trace.get_current_span()
                if current_span.is_recording():
                    current_span.set_attribute(
                        "pipeline.duration_ms", pipeline_duration * 1000
                    )
                    current_span.set_status(Status(StatusCode.OK))

                logger.info(
                    f"Pipeline '{pipeline_name}' completed successfully in {pipeline_duration:.2f}s"
                )

        except Exception as e:
            pipeline_duration = time.time() - pipeline_start_time
            logger.error(
                f"Pipeline '{pipeline_name}' failed: {e}",
                exc_info=True,
            )
            current_span = trace.get_current_span()
            if current_span.is_recording():
                current_span.set_attribute(
                    "pipeline.duration_ms", pipeline_duration * 1000
                )
                current_span.set_status(Status(StatusCode.ERROR, str(e)))
                current_span.record_exception(e)
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

            # Reset icon based on app state
            if self.app_state:
                from voicetype.state import State

                if self.app_state.state == State.ENABLED:
                    self.icon_controller.set_icon("idle")
                else:
                    self.icon_controller.set_icon("disabled")
            else:
                # Fallback if no app_state provided
                self.icon_controller.set_icon("idle")

            # Span will be automatically ended by the context manager

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
            # Remove from active pipelines and cancel events
            self.active_pipelines.pop(pipeline_id, None)
            self.cancel_events.pop(pipeline_id, None)

    def cancel_pipeline(self, pipeline_id: str):
        """Cancel a specific running pipeline.

        Args:
            pipeline_id: Pipeline identifier to cancel
        """
        if pipeline_id in self.cancel_events:
            # Signal cancellation to the running pipeline
            self.cancel_events[pipeline_id].set()
            logger.info(f"Requested cancellation of pipeline {pipeline_id}")

        if pipeline_id in self.active_pipelines:
            future = self.active_pipelines[pipeline_id]
            if not future.done():
                future.cancel()

    def cancel_all_pipelines(self):
        """Request cancellation of all active pipelines.

        This signals all running pipelines to stop gracefully by setting
        their cancel_requested events. Stages should check this event
        periodically and stop their work when it's set.
        """
        if not self.cancel_events:
            logger.debug("No active pipelines to cancel")
            return

        logger.info(
            f"Requesting cancellation of {len(self.cancel_events)} active pipeline(s)"
        )
        for pipeline_id, cancel_event in list(self.cancel_events.items()):
            cancel_event.set()
            logger.debug(f"Signaled cancellation for pipeline {pipeline_id}")

    def shutdown(self, timeout: float = 5.0):
        """Gracefully shutdown pipeline executor with timeout.

        Args:
            timeout: Maximum time to wait for active pipelines to complete
        """
        logger.info("Shutting down pipeline executor...")
        self._shutdown = True

        # Signal all pipelines to cancel gracefully
        self.cancel_all_pipelines()

        # Also cancel all pending futures
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
