"""Run command stage for pipeline execution.

This stage runs an arbitrary shell command when triggered by a hotkey.
"""

import subprocess
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field

from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage


class RunCommandConfig(BaseModel):
    """Configuration for RunCommand stage."""

    command: str = Field(
        description="Shell command to execute.",
    )
    timeout: Optional[float] = Field(
        default=30.0,
        description="Timeout in seconds for the command (None for no timeout).",
    )


@STAGE_REGISTRY.register
class RunCommand(PipelineStage[None, None]):
    """Run a shell command.

    Executes a configured shell command when the pipeline is triggered.
    Useful for triggering external scripts or tools via hotkey.

    Type signature: PipelineStage[None, None]
    - Input: None (first/only stage)
    - Output: None (final stage)

    Config parameters:
    - command: Shell command to execute
    - timeout: Timeout in seconds (default: 30, None for no timeout)
    """

    def __init__(self, config: dict):
        self.cfg = RunCommandConfig(**config)

    def execute(self, input_data: None, context: PipelineContext) -> None:
        context.icon_controller.set_icon("processing")
        logger.info(f"Running command: {self.cfg.command}")

        try:
            result = subprocess.run(
                self.cfg.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.cfg.timeout,
            )
            if result.returncode == 0:
                logger.info(f"Command succeeded: {result.stdout.strip()}")
            else:
                logger.warning(
                    f"Command exited with code {result.returncode}: "
                    f"{result.stderr.strip()}"
                )
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out after {self.cfg.timeout}s")

        context.icon_controller.set_icon("idle")
