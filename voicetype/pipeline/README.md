# Pipeline Stage Development Guide

This directory contains the voiceType pipeline system, which processes voice input through a series of modular stages. This guide explains how to create new pipeline stages.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Stage Anatomy](#stage-anatomy)
- [Type Safety](#type-safety)
- [Configuration](#configuration)
- [Resource Management](#resource-management)
- [Best Practices](#best-practices)
- [Examples](#examples)

## Overview

The pipeline system is a type-safe, modular architecture where data flows through a series of stages. Each stage:

1. Receives input from the previous stage (or `None` for the first stage)
2. Has access to a shared `PipelineContext` containing configuration and utilities
3. Returns output to pass to the next stage
4. Optionally implements cleanup logic for resource management

## Quick Start

Here's a minimal pipeline stage:

```python
from typing import Optional
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage

@STAGE_REGISTRY.register
class MyStage(PipelineStage[str, str]):
    """Brief description of what this stage does."""

    required_resources = set()  # Add resources if needed

    def __init__(self, config: dict, metadata: dict):
        """Initialize the stage with configuration."""
        self.config = config

    def execute(self, input_data: str, context: PipelineContext) -> str:
        """Execute the stage logic.

        Args:
            input_data: Output from previous stage
            context: Shared pipeline context

        Returns:
            Output to pass to next stage
        """
        # Your stage logic here
        result = input_data.upper()
        return result

    def cleanup(self) -> None:
        """Optional: Clean up resources (called in finally block)."""
        pass
```

## Stage Anatomy

### 1. Class Definition

```python
@STAGE_REGISTRY.register
class RecordAudio(PipelineStage[None, Optional[str]]):
    """Record audio until trigger completes."""
```

- **Decorator**: `@STAGE_REGISTRY.register` registers the stage automatically
- **Name**: Class name becomes the stage name (use PascalCase, e.g., `RecordAudio`, `Transcribe`)
- **Type Parameters**: `PipelineStage[TInput, TOutput]` defines input and output types
- **Docstring**: First line becomes the stage description

### 2. Resource Declaration

```python
from voicetype.pipeline import Resource

required_resources = {Resource.AUDIO_INPUT}
```

Declare any exclusive resources your stage needs. Available resources:
- `Resource.AUDIO_INPUT` - Microphone access
- `Resource.AUDIO_OUTPUT` - Speaker access
- `Resource.KEYBOARD` - Keyboard control

Stages requiring the same resource cannot run in parallel pipelines.

### 3. Initialization

```python
def __init__(self, config: dict, metadata: dict):
    """Initialize the stage.

    Args:
        config: Stage-specific configuration from settings.toml
        metadata: Shared pipeline metadata dictionary
    """
    self.config = config
    # Initialize stage state
```

The `__init__` method receives:
- `config`: Configuration dict specific to this stage
- `metadata`: Shared dict for inter-stage communication (e.g., speech_processor)

### 4. Execute Method

```python
def execute(self, input_data: TInput, context: PipelineContext) -> TOutput:
    """Execute the stage logic.

    Args:
        input_data: Output from previous stage (None for first stage)
        context: PipelineContext with config, icon_controller, trigger_event

    Returns:
        Output data to pass to next stage
    """
```

The `execute` method is where your stage logic lives. It receives:

- `input_data`: Typed output from the previous stage (or `None` for the first stage)
- `context`: A `PipelineContext` instance with:
  - `config`: Stage configuration dict
  - `icon_controller`: Interface to update system tray icon
  - `trigger_event`: Optional trigger event (for hotkey/timer triggers)
  - `cancel_requested`: Threading event for cancellation
  - `metadata`: Shared metadata dict for inter-stage communication

### 5. Cleanup Method (Optional)

```python
def cleanup(self) -> None:
    """Clean up resources held by this stage.

    Called by pipeline manager in finally block after pipeline completes.
    """
    # Release resources, delete temp files, etc.
```

Implement `cleanup()` if your stage creates resources that need explicit cleanup (temp files, connections, etc.). This is called even if the pipeline fails.

## Type Safety

The pipeline system enforces type safety at registration time:

### Type Hints Are Required

```python
# Good: Explicit type hints
def execute(self, input_data: Optional[str], context: PipelineContext) -> Optional[str]:
    ...

# Bad: Missing type hints - will raise TypeError at registration
def execute(self, input_data, context):
    ...
```

### Pipeline Validation

The registry validates that stages are compatible:

```python
# This pipeline is valid:
["RecordAudio", "Transcribe", "TypeText"]
# RecordAudio: None -> Optional[str]
# Transcribe: Optional[str] -> Optional[str]
# TypeText: Optional[str] -> None

# This would fail validation:
["RecordAudio", "TypeText"]
# RecordAudio outputs Optional[str] but TypeText expects str (not Optional)
```

### Common Type Patterns

```python
from typing import Optional

# First stage (no input)
PipelineStage[None, str]

# Middle stage with required input/output
PipelineStage[str, str]

# Stage that may receive/return None
PipelineStage[Optional[str], Optional[str]]

# Final stage (no output needed)
PipelineStage[str, None]
```

## Configuration

Stages receive configuration from `settings.toml`. Access via `self.config` or `context.config`:

```python
def execute(self, input_data: str, context: PipelineContext) -> str:
    # Get config with defaults
    max_duration = self.config.get("max_duration", 60.0)
    device_name = self.config.get("device_name")

    # Use configuration
    if device_name:
        logger.info(f"Using device: {device_name}")
```

Example `settings.toml`:

```toml
[record_audio_stage]
max_duration = 60.0
minimum_duration = 0.25
device_name = "USB Microphone"

[transcribe_stage]
provider = "local"
language = "en"
```

## Resource Management

### Using the Icon Controller

Update the system tray icon to provide user feedback:

```python
def execute(self, input_data: str, context: PipelineContext) -> str:
    # Set icon to recording state
    context.icon_controller.set_icon("recording")

    # Set icon temporarily (reverts after duration)
    context.icon_controller.set_icon("processing", duration=2.0)

    # Flash the icon
    context.icon_controller.start_flashing("recording")
    # ... do work ...
    context.icon_controller.stop_flashing()
```

Available icon states: `"idle"`, `"recording"`, `"processing"`, `"error"`

### Using the Trigger Event

For stages that need to wait for user input (e.g., hotkey release):

```python
def execute(self, input_data: None, context: PipelineContext) -> str:
    # Start some operation
    self._start_recording()

    # Wait for trigger completion (e.g., key release)
    if context.trigger_event:
        context.trigger_event.wait_for_completion(timeout=60.0)
    else:
        # No trigger: wait for cancellation or timeout
        context.cancel_requested.wait(timeout=60.0)

    # Finish operation
    return self._stop_recording()
```

### Handling Cancellation

Check for cancellation in long-running operations:

```python
def execute(self, input_data: str, context: PipelineContext) -> str:
    while processing:
        if context.cancel_requested.is_set():
            logger.info("Cancellation requested, stopping early")
            break
        # Continue processing
    return result
```

### Temporary Files

Clean up temporary files in `cleanup()`:

```python
def __init__(self, config: dict, metadata: dict):
    self.temp_file = None

def execute(self, input_data: str, context: PipelineContext) -> str:
    # Create temp file
    self.temp_file = tempfile.NamedTemporaryFile(delete=False)
    # ... use file ...
    return self.temp_file.name

def cleanup(self) -> None:
    """Clean up temp file."""
    if self.temp_file and os.path.exists(self.temp_file.name):
        os.unlink(self.temp_file.name)
```

## Best Practices

### 1. Logging

Use structured logging with loguru:

```python
from loguru import logger

logger.debug("Detailed information for debugging")
logger.info("Important user-facing information")
logger.warning("Something unexpected but recoverable")
logger.error("An error occurred", exc_info=True)
```

### 2. Error Handling

Let exceptions propagate - the pipeline manager handles them:

```python
def execute(self, input_data: str, context: PipelineContext) -> str:
    if not input_data:
        raise ValueError("Input data cannot be empty")

    # Don't catch exceptions unless you can handle them
    result = self._process(input_data)
    return result
```

### 3. Handle None Inputs

If your stage accepts `Optional[T]`, handle None gracefully:

```python
def execute(self, input_data: Optional[str], context: PipelineContext) -> Optional[str]:
    if input_data is None:
        logger.info("No input data, skipping stage")
        return None

    # Process non-None input
    return self._process(input_data)
```

### 4. Use Metadata for Shared State

Share objects between stages via `context.metadata`:

```python
# In one stage:
def execute(self, input_data: str, context: PipelineContext) -> str:
    processor = SpeechProcessor()
    context.metadata["speech_processor"] = processor
    return result

# In another stage:
def execute(self, input_data: str, context: PipelineContext) -> str:
    processor = context.metadata.get("speech_processor")
    if processor:
        processor.do_something()
```

### 5. Keep Stages Focused

Each stage should have a single, clear responsibility:

- **Good**: `RecordAudio`, `Transcribe`, `TypeText` (separate concerns)
- **Bad**: `RecordAndTranscribe` (combines multiple concerns)

### 6. Document Configuration

Document expected config parameters in the class docstring:

```python
@STAGE_REGISTRY.register
class MyStage(PipelineStage[str, str]):
    """Process text in some way.

    Config parameters:
    - timeout: Maximum processing time in seconds (default: 30)
    - mode: Processing mode ("fast" or "accurate", default: "fast")
    - api_key: Optional API key for external service
    """
```

## Examples

### Example 1: Simple Text Transformation

```python
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage

@STAGE_REGISTRY.register
class UppercaseText(PipelineStage[str, str]):
    """Convert text to uppercase."""

    required_resources = set()

    def __init__(self, config: dict, metadata: dict):
        self.config = config

    def execute(self, input_data: str, context: PipelineContext) -> str:
        """Convert input text to uppercase."""
        return input_data.upper()
```

### Example 2: Stage with Configuration

```python
@STAGE_REGISTRY.register
class FilterProfanity(PipelineStage[str, str]):
    """Filter profanity from text.

    Config parameters:
    - replacement: Text to replace profanity with (default: "***")
    - case_sensitive: Whether matching is case sensitive (default: false)
    """

    required_resources = set()

    def __init__(self, config: dict, metadata: dict):
        self.config = config
        self.replacement = config.get("replacement", "***")
        self.case_sensitive = config.get("case_sensitive", False)

    def execute(self, input_data: str, context: PipelineContext) -> str:
        """Filter profanity from input text."""
        # Your filtering logic here
        filtered = self._filter_text(input_data)
        logger.info(f"Filtered {len(input_data) - len(filtered)} characters")
        return filtered
```

### Example 3: Stage with Optional Input/Output

```python
from typing import Optional

@STAGE_REGISTRY.register
class ValidateText(PipelineStage[Optional[str], Optional[str]]):
    """Validate text meets minimum requirements.

    Config parameters:
    - min_length: Minimum text length (default: 1)
    - max_length: Maximum text length (default: 10000)
    """

    required_resources = set()

    def __init__(self, config: dict, metadata: dict):
        self.config = config
        self.min_length = config.get("min_length", 1)
        self.max_length = config.get("max_length", 10000)

    def execute(self, input_data: Optional[str], context: PipelineContext) -> Optional[str]:
        """Validate text length, return None if invalid."""
        if input_data is None:
            logger.info("No input to validate")
            return None

        if len(input_data) < self.min_length:
            logger.warning(f"Text too short ({len(input_data)} < {self.min_length})")
            return None

        if len(input_data) > self.max_length:
            logger.warning(f"Text too long ({len(input_data)} > {self.max_length})")
            return None

        return input_data
```

### Example 4: Stage with Resource Management

```python
import tempfile
import os
from typing import Optional

@STAGE_REGISTRY.register
class SaveToFile(PipelineStage[str, str]):
    """Save text to a temporary file and return the path.

    Config parameters:
    - prefix: Filename prefix (default: "voicetype_")
    - suffix: Filename suffix (default: ".txt")
    """

    required_resources = set()

    def __init__(self, config: dict, metadata: dict):
        self.config = config
        self.temp_file = None
        self.prefix = config.get("prefix", "voicetype_")
        self.suffix = config.get("suffix", ".txt")

    def execute(self, input_data: str, context: PipelineContext) -> str:
        """Save text to temp file and return path."""
        with tempfile.NamedTemporaryFile(
            mode='w',
            prefix=self.prefix,
            suffix=self.suffix,
            delete=False
        ) as f:
            f.write(input_data)
            self.temp_file = f.name

        logger.info(f"Saved text to {self.temp_file}")
        return self.temp_file

    def cleanup(self) -> None:
        """Clean up temporary file."""
        if self.temp_file and os.path.exists(self.temp_file):
            try:
                os.unlink(self.temp_file)
                logger.debug(f"Cleaned up temp file: {self.temp_file}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {self.temp_file}: {e}")
            self.temp_file = None
```

### Example 5: CorrectTypos Stage (Text Correction with Configuration)

```python
import re
from typing import Optional
from loguru import logger

@STAGE_REGISTRY.register
class CorrectTypos(PipelineStage[Optional[str], Optional[str]]):
    """Replace configured typos with correct spellings.

    This stage allows you to fix common speech-to-text errors, correct
    capitalization, or standardize terminology before text is typed.

    Config parameters:
    - case_sensitive: Default case sensitivity for matching (default: false)
    - whole_word_only: Default whole-word matching (default: true)
    - corrections: List of correction rules. Each rule is a list with:
      [typo, correction] or [typo, correction, "overrides"]
      where overrides can be "case_sensitive=true" or "whole_word_only=false"
      or both: "case_sensitive=true,whole_word_only=false"

    Example configuration in settings.toml:
    ```toml
    [[pipelines.stages]]
    stage = "CorrectTypos"
    case_sensitive = false
    whole_word_only = true
    corrections = [
        ["machinelearning", "machine learning"],
        ["air quotes", "error codes"],
        ["Python", "python", "case_sensitive=true"],
        ["machine", "machine", "whole_word_only=false"],
    ]
    ```
    """

    required_resources = set()

    def __init__(self, config: dict, metadata: dict):
        self.config = config
        self.case_sensitive = config.get("case_sensitive", False)
        self.whole_word_only = config.get("whole_word_only", True)
        self._patterns = self._parse_and_compile_corrections()

    def _compile_pattern(
        self, typo: str, case_sensitive: bool, whole_word_only: bool
    ) -> re.Pattern:
        """Compile a regex pattern for a typo."""
        escaped_typo = re.escape(typo)
        if whole_word_only:
            pattern_str = rf"\b{escaped_typo}\b"
        else:
            pattern_str = escaped_typo
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.compile(pattern_str, flags)

    def _parse_and_compile_corrections(self) -> list:
        """Parse corrections from config and compile regex patterns."""
        patterns = []
        corrections_list = self.config.get("corrections", [])

        for entry in corrections_list:
            if not isinstance(entry, list) or len(entry) < 2:
                logger.warning(f"Invalid correction entry: {entry}. Skipping.")
                continue

            typo = entry[0]
            correction = entry[1]
            case_sensitive = self.case_sensitive
            whole_word_only = self.whole_word_only

            # Parse overrides if present
            if len(entry) > 2:
                for pair in entry[2].split(","):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        if key.strip() == "case_sensitive":
                            case_sensitive = value.strip().lower() == "true"
                        elif key.strip() == "whole_word_only":
                            whole_word_only = value.strip().lower() == "true"

            pattern = self._compile_pattern(typo, case_sensitive, whole_word_only)
            patterns.append((pattern, correction, typo))

        logger.debug(f"Loaded {len(patterns)} typo correction(s)")
        return patterns

    def execute(
        self, input_data: Optional[str], context: PipelineContext
    ) -> Optional[str]:
        """Apply typo corrections to input text."""
        if input_data is None:
            logger.debug("No input to correct")
            return None

        if not self._patterns:
            logger.debug("No corrections configured")
            return input_data

        result = input_data
        corrections_made = []

        for pattern, replacement, original_typo in self._patterns:
            matches = pattern.findall(result)
            if matches:
                result = pattern.sub(replacement, result)
                corrections_made.append(f"'{matches[0]}' → '{replacement}'")

        if corrections_made:
            logger.info(
                f"Applied {len(corrections_made)} correction(s): "
                f"{', '.join(corrections_made)}"
            )

        return result
```

## Testing Your Stage

1. **Add your stage to a pipeline** in `settings.toml`:

```toml
[pipelines.test_pipeline]
stages = ["RecordAudio", "Transcribe", "YourNewStage", "TypeText"]
```

2. **Import your stage** in `voicetype/pipeline/stages/__init__.py`:

```python
from .your_stage import YourStage
```

3. **Run voiceType** and test your pipeline

4. **Check logs** for any errors or warnings

## Additional Resources

- [stage_registry.py](stage_registry.py) - Stage registration and validation
- [context.py](context.py) - PipelineContext and IconController interfaces
- [pipeline_manager.py](pipeline_manager.py) - Pipeline execution logic
- [stages/](stages/) - Example stage implementations

## Getting Help

If you run into issues:
1. Check the existing stages in `stages/` for examples
2. Verify your type hints are correct
3. Check logs for detailed error messages
4. Ensure your stage is imported in `stages/__init__.py`
