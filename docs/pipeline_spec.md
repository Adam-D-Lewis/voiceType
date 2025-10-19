# Configurable Pipeline System - Specification

## Overview
Transform the current dictation system into a flexible, configurable pipeline architecture where users can define multiple pipelines triggered by different hotkeys.

## Goals
- Enable multiple pipelines with different hotkeys
- Allow users to add, remove, or reorder stages
- Support custom stages in the future
- Maintain simplicity while enabling flexibility

## Architecture

### Pipeline Execution Model
- **Multiple pipelines**: Users can define multiple pipelines in `settings.toml`
- **Hotkey-triggered**: Hotkeys are registered outside the pipeline and trigger pipeline execution
- **Sequential execution**: Pipelines run as a sequence of stages
- **Synchronous stages**: All stages are synchronous functions (no async/await); concurrency is achieved via thread pool execution
- **Thread pool execution**: Pipelines run on worker threads to avoid blocking the hotkey listener
- **Data flow**: Each stage receives the output of the previous stage as input
- **Resource-based locking**: Pipelines lock specific resources (audio device, keyboard) rather than a global lock; multiple pipelines can run concurrently if they don't conflict on resources

### Resource-Based Locking Benefits

Instead of a single global pipeline lock, the system uses fine-grained resource locks:

**Benefits:**
1. **Concurrent execution**: Multiple pipelines can run simultaneously if they use different resources
2. **Better responsiveness**: Users can start new operations while previous ones are still finishing
3. **Flexible use cases**: Enable scenarios like "record new audio while previous transcription is typing"
4. **Graceful degradation**: System provides clear feedback about which specific resource is busy

**Example scenarios:**

| Scenario | Pipeline A | Pipeline B | Can Run Concurrently? | Reason |
|----------|-----------|-----------|----------------------|---------|
| Dictation overlap | Recording audio | Typing previous text | ✅ Yes | A uses AUDIO_INPUT, B uses KEYBOARD |
| Double recording | Recording audio | Recording audio | ❌ No | Both need AUDIO_INPUT |
| Clipboard while dictating | Recording audio | Clipboard copy | ✅ Yes | A uses AUDIO_INPUT, B uses CLIPBOARD |
| Type while typing | Typing text | Typing text | ❌ No | Both need KEYBOARD |

**Resource types:**
- `AUDIO_INPUT`: Microphone/audio capture device (exclusive)
- `KEYBOARD`: Virtual keyboard for typing (exclusive)
- `CLIPBOARD`: System clipboard (exclusive)

### Trigger System
Pipelines are triggered by external events (hotkeys, timers, programmatic calls) rather than containing trigger logic:

- **HotkeyTriggerEvent**: Triggered on key press, waits for key release
- **TimerTriggerEvent**: Triggered immediately, waits for fixed duration
- **ProgrammaticTriggerEvent**: Triggered by code, no automatic completion

Stages receive trigger information via `PipelineContext` and can wait for trigger completion (e.g., key release).

### Stage Model
Each stage is a function that:
- Receives input data from the previous stage (None for first stage)
- Receives a `PipelineContext` object containing:
  - Stage-specific configuration from settings.toml
  - Icon controller for updating system tray icon
  - Optional trigger event (for hotkey/timer triggers)
  - Cancellation event
  - Shared metadata dictionary
- Returns output data to pass to the next stage
- Logs its output via debug statements
- On error: logs error, plays error sound, updates tray icon to error state, stops pipeline

### Why Synchronous Stages?

**Design Decision:** All stages are synchronous functions, not async. Concurrency is achieved through thread pool execution.

**Rationale:**
1. **Simpler implementation**: Current codebase is synchronous; no major refactoring needed
2. **Better library compatibility**: Audio recording, STT, and keyboard simulation libraries are primarily synchronous
3. **Easier for users**: Custom stages can be written as simple functions without async/await complexity
4. **Thread pool handles concurrency**: Worker threads provide non-blocking execution without async overhead
5. **Blocking I/O is unavoidable**: Core operations (audio capture, typing simulation) inherently block and don't benefit from async

**How concurrency works:**
- Hotkey listener runs on main thread (never blocks)
- Pipeline execution happens on thread pool workers
- Multiple pipelines can run concurrently if they don't conflict on resources
- Each pipeline blocks its worker thread, but doesn't block the hotkey listener or other pipelines

**See also:** Critical Issue #1 in [pipeline_spec_review.md](pipeline_spec_review.md) for detailed analysis.

## Configuration Format

### settings.toml Structure

```toml
# Backward compatible with existing settings
[voice]
provider = "local"
minimum_duration = 0.25

[hotkey]
hotkey = "<pause>"

# New pipeline configuration (if no pipelines defined, creates default from above)
[[pipelines]]
name = "basic_dictation"
enabled = true
hotkey = "<pause>"
stages = [
    {func = "record_audio"},
    {func = "transcribe", provider = "local", minimum_duration = 0.25},
    {func = "type_text"}
]

[[pipelines]]
name = "groq_dictation"
enabled = false
hotkey = "<f12>"
stages = [
    {func = "record_audio"},
    {func = "transcribe", provider = "litellm", model = "groq/whisper-large-v3"},
    {func = "type_text"}
]
```

### Pipeline Configuration
- `name`: Unique identifier for the pipeline
- `enabled`: Boolean to enable/disable pipeline
- `hotkey`: Hotkey string to trigger this pipeline (e.g., "<pause>", "<f12>")
- `stages`: Array of stage configurations, where each stage is a dict containing:
  - `func`: The stage function name (required)
  - Additional parameters specific to that stage (optional)

### Stage Configuration
Each stage in the `stages` array is a dict with a flat structure:
- `func`: Required field identifying the stage function
- All other fields are stage-specific parameters
- Parameters are validated against the stage's Pydantic model at startup
- Examples:
  - `{func = "record_audio", max_duration = 120}`
  - `{func = "transcribe", provider = "local", model = "large-v3-turbo"}`
  - `{func = "type_text", typing_speed = 100}`

### Pydantic Validation for Stage Configs

The flat dict format enables clean Pydantic validation using discriminated unions:

```python
from typing import Literal, Optional, Annotated, Union
from pydantic import BaseModel, Field

class RecordAudioStage(BaseModel):
    func: Literal["record_audio"]
    max_duration: float = 60.0
    minimum_duration: float = 0.25
    device_name: Optional[str] = None

class TranscribeStage(BaseModel):
    func: Literal["transcribe"]
    provider: Literal["local", "litellm"] = "local"
    model: Optional[str] = None
    minimum_duration: float = 0.25
    language: str = "en"
    history: Optional[str] = None

class TypeTextStage(BaseModel):
    func: Literal["type_text"]
    typing_speed: Optional[int] = None

# Discriminated union for all stage types
StageConfig = Annotated[
    Union[RecordAudioStage, TranscribeStage, TypeTextStage],
    Field(discriminator='func')
]

class PipelineConfig(BaseModel):
    name: str
    enabled: bool = True
    hotkey: str
    stages: list[StageConfig]

class Config(BaseModel):
    pipelines: list[PipelineConfig]
```

**Benefits of this validation approach:**

1. **Type safety**: Invalid stage names are caught at config load time
   ```toml
   {func = "unknown_stage"}  # ❌ Error: 'unknown_stage' not a valid literal
   ```

2. **Parameter validation**: Typos and invalid values are caught immediately
   ```toml
   {func = "transcribe", model = "whisper"}  # ❌ Error: no field 'model'
   {func = "transcribe", provider = "invalid"}  # ❌ Error: not in ['local', 'litellm']
   ```

3. **Default values**: Missing optional parameters get sensible defaults
   ```toml
   {func = "record_audio"}  # ✓ max_duration defaults to 60.0
   ```

4. **IDE support**: Editor autocomplete works when editing TOML files with proper LSP

5. **Self-documenting**: Pydantic models serve as the source of truth for what each stage accepts

## Stage Interface

### PipelineContext

```python
class PipelineContext:
    """Shared context for all stages in a pipeline execution"""

    config: dict                          # Stage-specific configuration
    icon_controller: IconController       # Interface to update system tray
    trigger_event: Optional[TriggerEvent] # Optional trigger event (hotkey/timer)
    cancel_requested: threading.Event     # Set when pipeline should be cancelled
    metadata: dict                        # Shared data between stages
                                          # SPECIAL KEY: metadata['_temp_resources']
                                          # List of resources with cleanup() methods
                                          # that were created but not returned by stages.
                                          # Pipeline manager will call cleanup() on these.
```

### TriggerEvent Types

```python
class TriggerEvent:
    """Base class for different trigger types"""
    def wait_for_completion(self, timeout: float = None) -> bool:
        """Wait for trigger to complete (e.g., key release)"""
        raise NotImplementedError

class HotkeyTriggerEvent(TriggerEvent):
    """Hotkey-specific trigger that waits for key release"""
    press_time: float                     # Time when key was pressed
    release_event: threading.Event        # Set when key is released

    def wait_for_completion(self, timeout: float = None) -> bool:
        """Block until key is released or timeout"""
        return self.release_event.wait(timeout)

    def signal_release(self):
        """Called by hotkey manager when key is released"""
        self.release_event.set()

class TimerTriggerEvent(TriggerEvent):
    """Timer-based trigger that waits for fixed duration"""
    duration: float                       # Duration to wait in seconds

    def wait_for_completion(self, timeout: float = None) -> bool:
        """Wait for configured duration (or timeout, whichever is less)"""
        time.sleep(min(self.duration, timeout or self.duration))
        return True

class ProgrammaticTriggerEvent(TriggerEvent):
    """Programmatic trigger with no automatic completion"""

    def wait_for_completion(self, timeout: float = None) -> bool:
        """Return immediately (no wait)"""
        return True
```

### Stage Function Signature

Stages use generic type variables to ensure type safety between pipeline stages:

```python
from typing import TypeVar, Protocol, Generic, Callable

# Type variables for stage inputs and outputs
TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')

class StageFunction(Protocol, Generic[TInput, TOutput]):
    """Protocol for type-safe pipeline stages"""

    def __call__(self, input_data: TInput, context: PipelineContext) -> TOutput:
        """
        Execute a pipeline stage.

        Args:
            input_data: Output from the previous stage (None for first stage)
            context: PipelineContext containing config, icon_controller, trigger_event, etc.

        Returns:
            Output data to pass to the next stage

        Raises:
            Exception: Any errors should be raised and handled by pipeline manager
        """
        ...

# Concrete type aliases for common stage types
AudioRecordingStage = StageFunction[None, Optional[TemporaryAudioFile]]           # None -> audio file wrapper
TranscriptionStage = StageFunction[Optional[TemporaryAudioFile], Optional[str]]   # audio wrapper -> text
TypingStage = StageFunction[Optional[str], None]                                  # text -> None
```

This type system provides:
1. **Compile-time validation**: Type checkers (mypy, pyright) can verify stage compatibility
2. **IDE support**: Autocomplete knows input/output types for each stage
3. **Documentation**: Function signatures clearly show data flow
4. **Refactoring safety**: Changing a stage's output type shows all affected pipelines

**Example of type-safe stage composition:**

```python
# These stages are compatible
pipeline_stages: list[Callable] = [
    record_audio,    # StageFunction[None, Optional[TemporaryAudioFile]]
    transcribe,      # StageFunction[Optional[TemporaryAudioFile], Optional[str]]
    type_text,       # StageFunction[Optional[str], None]
]

# This would fail type checking:
bad_pipeline = [
    record_audio,    # Returns Optional[TemporaryAudioFile]
    type_text,       # Expects Optional[str] ✗ Type mismatch!
    transcribe,      # Never reached
]
```

## Pipeline Execution Flow

### Cleanup Responsibility

**CRITICAL DESIGN RULE: The pipeline manager is SOLELY responsible for ALL cleanup of temporary resources created by stages.**

**Stages MUST NEVER clean up resources themselves.** This is a strict contract that all stages must follow.

This design ensures:

1. **Guaranteed cleanup**: Resources are freed even if:
   - A stage raises an exception
   - The pipeline is cancelled mid-execution
   - A later stage never runs
   - A stage returns early (e.g., filtering out short audio)
   - Power loss occurs (OS cleans temp directories on reboot)

2. **Stage simplicity**: Stages don't need cleanup logic or complex error handling
3. **Centralized management**: All cleanup happens in one place (pipeline manager's `finally` block)
4. **Composability**: Stages can be reordered without changing cleanup logic
5. **Reliability**: No risk of double-cleanup or missed cleanup due to early returns
6. **Debuggability**: Single point of responsibility makes debugging cleanup issues easier

### Cleanup Protocol

**For resources returned by stages:**

Stages that create temporary resources (like audio files) should return objects with a `cleanup()` method. The pipeline manager will automatically detect these and call `cleanup()` in the `finally` block.

**For resources NOT returned by stages:**

If a stage creates a temporary resource but doesn't return it (e.g., an audio file that was too short and filtered out), the stage MUST store it in `context.metadata['_temp_resources']` for cleanup:

```python
# Example: Stage creates a resource but doesn't return it
temp_file = TemporaryAudioFile(filename)

if should_filter_out:
    # Store for cleanup instead of cleaning up directly
    context.metadata['_temp_resources'] = context.metadata.get('_temp_resources', [])
    context.metadata['_temp_resources'].append(temp_file)
    return None  # Pipeline manager will still clean up temp_file
```

**Resource wrapper interface:**

```python
class TemporaryAudioFile:
    """Wrapper for temporary audio files with automatic cleanup"""

    def __init__(self, filepath: str, duration: float = 0.0):
        self.filepath = filepath
        self.duration = duration

    def cleanup(self):
        """Remove temporary file - called by pipeline manager"""
        if os.path.exists(self.filepath):
            try:
                os.unlink(self.filepath)
                logger.debug(f"Cleaned up temp file: {self.filepath}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {self.filepath}: {e}")
```

The pipeline manager detects cleanup methods and invokes them in the `finally` block.

### Execution Flow

```python
# Pseudocode for pipeline execution
def execute_pipeline(pipeline_config, trigger_event: Optional[TriggerEvent] = None):
    """Execute a pipeline with optional trigger event (runs on worker thread)"""

    pipeline_id = str(uuid.uuid4())

    # Determine required resources
    required_resources = resource_manager.get_required_resources(pipeline_config["stages"])

    # Acquire resources atomically (blocking with timeout)
    # Note: Removed separate can_acquire() check to avoid race condition
    # (see Critical Issue #2 in pipeline_spec_review.md)
    if not resource_manager.acquire(pipeline_id, required_resources, blocking=True, timeout=1.0):
        logger.error(f"Failed to acquire resources for {pipeline_config['name']}")
        play_sound(ERROR_SOUND)
        return

    # Create context
    context = PipelineContext(
        config=pipeline_config.get("config", {}),
        icon_controller=icon_controller,
        trigger_event=trigger_event,
        cancel_requested=threading.Event(),
        metadata={}
    )

    result = None
    cleanup_tasks = []  # Pipeline manager tracks all cleanup tasks

    try:
        for stage_name in pipeline_config["stages"]:
            # Check for cancellation
            if context.cancel_requested.is_set():
                logger.info(f"Pipeline {pipeline_config['name']} cancelled")
                return

            logger.debug(f"Starting stage: {stage_name}")

            # Get stage function from registry (raises ValueError if unknown)
            stage_metadata = STAGE_REGISTRY.get(stage_name)
            stage_func = stage_metadata.function

            # Update context with stage-specific config
            context.config = pipeline_config.get(stage_name, {})

            # Execute stage (synchronous call - may block for seconds)
            result = stage_func(result, context)

            # Track cleanup if the result has a cleanup method
            # This allows stages to return temporary resources that need cleanup
            if hasattr(result, 'cleanup') and callable(result.cleanup):
                cleanup_tasks.append(result.cleanup)

            # IMPORTANT: Also collect temporary resources from metadata
            # Stages may create resources they don't return (e.g., filtered out files)
            # These are stored in context.metadata['_temp_resources'] for cleanup
            if '_temp_resources' in context.metadata:
                for resource in context.metadata['_temp_resources']:
                    if hasattr(resource, 'cleanup') and callable(resource.cleanup):
                        if resource.cleanup not in cleanup_tasks:
                            cleanup_tasks.append(resource.cleanup)
                # Clear the list after collecting
                context.metadata['_temp_resources'] = []

            logger.debug(f"Stage {stage_name} output: {result}")

    except Exception as e:
        logger.error(f"Pipeline {pipeline_config['name']} failed at stage {stage_name}", exc_info=True)
        play_sound(ERROR_SOUND)
        icon_controller.set_error()
        raise

    finally:
        # CRITICAL: Cleanup temporary resources created by stages
        # The pipeline manager is SOLELY responsible for all cleanup.
        # Stages must NEVER clean up resources themselves.
        #
        # This ALWAYS runs, even if:
        # - A stage raised an exception
        # - The pipeline was cancelled
        # - A return statement was hit
        #
        # Cleanup includes:
        # - Resources returned by stages (tracked via cleanup methods)
        # - Resources stored in context.metadata['_temp_resources']
        #   (for resources created but not returned, e.g., filtered out files)
        for cleanup in cleanup_tasks:
            try:
                cleanup()
            except Exception as e:
                # Don't let cleanup failures mask the original error
                logger.warning(f"Cleanup failed: {e}")

        # Release acquired resources
        resource_manager.release(pipeline_id)

        # Reset icon
        icon_controller.set_icon("idle")
```

## Core Stages (Initial Implementation)

### 1. `record_audio`

**Purpose**: Record audio while trigger is active (e.g., while hotkey is held)

**Input**: None (first stage)

**Config**:
- `max_duration`: Maximum recording duration in seconds (default: 60)
- `minimum_duration`: Minimum recording duration to process (default: 0.25)
- `device_name`: Optional audio device name (default: system default)

**Behavior**:
1. Starts audio recording immediately
2. Updates tray icon to recording state
3. Waits for trigger completion (e.g., key release) or max_duration timeout
4. Stops recording and saves to temporary audio file
5. Creates `TemporaryAudioFile` wrapper for the file
6. If recording is shorter than minimum_duration:
   - Stores the wrapper in `context.metadata['_temp_resources']` for cleanup
   - Returns None (file will still be cleaned up by pipeline manager)
7. Otherwise, returns the `TemporaryAudioFile` wrapper

**Output**: `Optional[TemporaryAudioFile]` - Object with `filepath` attribute and `cleanup()` method, or None if too short

**Cleanup**: **IMPORTANT - The stage does NOT clean up files.** The pipeline manager will call `cleanup()` on:
- The returned object (if not None)
- Any objects stored in `context.metadata['_temp_resources']` (for filtered-out recordings)

**Icon States**:
- Recording indicator during capture
- Stops when recording complete

**Example Implementation**:
```python
class TemporaryAudioFile:
    """Wrapper for temporary audio files with automatic cleanup"""

    def __init__(self, filepath: str, duration: float = 0.0):
        self.filepath = filepath
        self.duration = duration

    def cleanup(self):
        """Remove temporary file - called by pipeline manager ONLY"""
        if os.path.exists(self.filepath):
            try:
                os.unlink(self.filepath)
                logger.debug(f"Cleaned up temp file: {self.filepath}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {self.filepath}: {e}")


def record_audio(input_data: None, context: PipelineContext) -> Optional[TemporaryAudioFile]:
    """
    Record audio stage implementation.

    Type signature: StageFunction[None, Optional[TemporaryAudioFile]]
    - Input: None (first stage)
    - Output: Optional[TemporaryAudioFile] (audio file wrapper or None if too short)
    """
    processor = context.metadata.get('speech_processor')
    processor.start_recording()
    context.icon_controller.set_state("recording")

    # Wait for trigger completion (e.g., key release)
    max_duration = context.config.get('max_duration', 60)

    if context.trigger_event:
        context.trigger_event.wait_for_completion(timeout=max_duration)
    else:
        # No trigger event: wait for cancellation or timeout
        context.cancel_requested.wait(timeout=max_duration)

    filename, duration = processor.stop_recording()

    # Always return wrapper object - pipeline manager handles cleanup
    # The wrapper includes metadata (like duration) that may be needed for filtering
    audio_file = TemporaryAudioFile(filepath=filename, duration=duration)

    # Filter out too-short recordings by returning None
    # Pipeline manager will still call cleanup() on the wrapper object
    min_duration = context.config.get('minimum_duration', 0.25)
    if duration < min_duration:
        logger.info(f"Recording too short ({duration}s), ignoring")
        # DO NOT clean up here - pipeline manager owns all cleanup
        # The audio_file will be added to cleanup_tasks even though we return None
        context.metadata['_temp_resources'] = context.metadata.get('_temp_resources', [])
        context.metadata['_temp_resources'].append(audio_file)
        return None

    # Return wrapper object with cleanup support
    # Pipeline manager will call cleanup() in finally block
    return audio_file
```

### 2. `transcribe`

**Purpose**: Transcribe audio file to text via STT

**Input**: `Optional[TemporaryAudioFile]` - Audio file wrapper (None if recording was too short)

**Config**:
- `provider`: STT provider ("local" or "litellm")
- `model`: Model name (e.g., "large-v3-turbo", "groq/whisper-large-v3")
- `language`: Optional language code for transcription (default: "en")
- `history`: Optional context for better transcription accuracy

**Behavior**:
1. If input is None, return None (skip transcription)
2. Reads audio file from `input_data.filepath`
3. Sends to configured STT service
4. Returns transcribed text
5. **Note**: Does NOT clean up the audio file - the pipeline manager handles that

**Output**: `Optional[str]` - Transcribed text or None if no input

**Cleanup**: The stage does NOT handle cleanup. The pipeline manager will call `cleanup()` on the input `TemporaryAudioFile` after pipeline completion.

**Icon States**:
- Processing/thinking indicator during transcription

**Example Implementation**:
```python
def transcribe(input_data: Optional[TemporaryAudioFile], context: PipelineContext) -> Optional[str]:
    """
    Transcribe audio stage implementation.

    Type signature: StageFunction[Optional[TemporaryAudioFile], Optional[str]]
    - Input: Optional[TemporaryAudioFile] (audio file wrapper or None)
    - Output: Optional[str] (transcribed text or None)
    """
    if input_data is None:
        return None

    context.icon_controller.set_state("processing")

    processor = context.metadata.get('speech_processor')

    # Access the file path from the wrapper object
    # The pipeline manager will clean up the file later
    text = processor.transcribe(
        filename=input_data.filepath,
        history=context.config.get('history'),
        language=context.config.get('language', 'en')
    )

    return text
```

### 3. `type_text`

**Purpose**: Type text via virtual keyboard

**Input**: `Optional[str]` - Text to type (None to skip)

**Config**:
- `typing_speed`: Optional typing speed in characters per second

**Behavior**:
1. If input is None, return immediately (no text to type)
2. Types the input text character by character using virtual keyboard
3. Returns None (final stage)

**Output**: None

**Icon States**:
- Returns to idle when complete

**Example Implementation**:
```python
def type_text(input_data: Optional[str], context: PipelineContext) -> None:
    """
    Type text stage implementation.

    Type signature: StageFunction[Optional[str], None]
    - Input: Optional[str] (text to type or None)
    - Output: None (final stage)
    """
    if input_data is None:
        logger.info("No text to type")
        return

    from voicetype._vendor.pynput.keyboard import Controller
    keyboard = Controller()

    for char in input_data:
        keyboard.type(char)
        # Optional: add small delay based on typing_speed config

    context.icon_controller.set_state("idle")
```

## Icon Controller Interface

```python
class IconController:
    def set_icon(self, state: str, duration: Optional[float] = None) -> None:
        """
        Set the system tray icon to a specific state.

        Args:
            state: Icon state (e.g., "idle", "recording", "processing", "error")
            duration: Optional duration in seconds before reverting to previous icon
        """
        pass

    def start_flashing(self, state: str) -> None:
        """
        Start flashing the icon in the specified state.

        Args:
            state: Icon state to flash (e.g., "recording")
        """
        pass

    def stop_flashing(self) -> None:
        """
        Stop flashing and return to the current non-flashing state.
        """
        pass
```

## Stage Registry

### Implementation Approach

**This addresses Issue #9 from the spec review ([pipeline_spec_review.md](pipeline_spec_review.md#9-stage-registry-not-specified)).**

The stage registry uses **Option 1 (dictionary-based registry)** with **optional decorator syntax** (hybrid of Option 1 + 2) for cleaner registration. This provides:

- **Simple core implementation**: Dictionary mapping stage names to metadata (`Dict[str, StageMetadata]`)
- **Clean registration syntax**: Decorators make registration declarative and co-located with implementation
- **Type-safe validation**: Function signatures checked against declared types at registration time
- **Load-time validation**: Stage names validated when loading settings.toml, not at runtime
- **Future extensibility**: Can add dynamic imports (Option 3) later for user-defined stages

The initial implementation focuses on **built-in stages only** (record_audio, transcribe, type_text). Custom user-defined stages via dynamic imports are explicitly **out of scope** for the initial release.

The stage registry provides type-safe stage registration and validation:

```python
from typing import Dict, Callable, get_type_hints
from dataclasses import dataclass

@dataclass
class StageMetadata:
    """Metadata about a registered stage"""
    name: str
    function: Callable
    input_type: type
    output_type: type
    description: str
    required_resources: set[Resource]

class StageRegistry:
    """Registry for pipeline stages with type validation"""

    def __init__(self):
        self._stages: Dict[str, StageMetadata] = {}

    def register(
        self,
        name: str,
        input_type: type,
        output_type: type,
        description: str = "",
        required_resources: set[Resource] = None
    ):
        """Decorator to register a stage with type information"""
        def decorator(func: Callable) -> Callable:
            # Validate function signature matches declared types
            hints = get_type_hints(func)
            if hints.get('input_data') != input_type:
                raise TypeError(
                    f"Stage {name}: declared input_type {input_type} doesn't match "
                    f"function signature {hints.get('input_data')}"
                )
            if hints.get('return') != output_type:
                raise TypeError(
                    f"Stage {name}: declared output_type {output_type} doesn't match "
                    f"function signature {hints.get('return')}"
                )

            self._stages[name] = StageMetadata(
                name=name,
                function=func,
                input_type=input_type,
                output_type=output_type,
                description=description,
                required_resources=required_resources or set()
            )
            return func
        return decorator

    def get(self, name: str) -> StageMetadata:
        """Get stage metadata by name"""
        if name not in self._stages:
            raise ValueError(f"Unknown stage: {name}. Available: {list(self._stages.keys())}")
        return self._stages[name]

    def validate_pipeline(self, stage_names: list[str]) -> None:
        """
        Validate that stages in a pipeline are compatible.

        Raises ValueError if:
        - Any stage name is unknown
        - Stage output type doesn't match next stage's input type
        """
        if not stage_names:
            raise ValueError("Pipeline must have at least one stage")

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

# Global registry instance
STAGE_REGISTRY = StageRegistry()

# Example stage registration
@STAGE_REGISTRY.register(
    name="record_audio",
    input_type=type(None),
    output_type=Optional[TemporaryAudioFile],
    description="Record audio until trigger completes",
    required_resources={Resource.AUDIO_INPUT}
)
def record_audio(input_data: None, context: PipelineContext) -> Optional[TemporaryAudioFile]:
    # Implementation...
    pass

@STAGE_REGISTRY.register(
    name="transcribe",
    input_type=Optional[TemporaryAudioFile],
    output_type=Optional[str],
    description="Transcribe audio file to text",
    required_resources=set()  # No exclusive resources needed
)
def transcribe(input_data: Optional[TemporaryAudioFile], context: PipelineContext) -> Optional[str]:
    # Implementation...
    pass

@STAGE_REGISTRY.register(
    name="type_text",
    input_type=Optional[str],
    output_type=type(None),
    description="Type text using virtual keyboard",
    required_resources={Resource.KEYBOARD}
)
def type_text(input_data: Optional[str], context: PipelineContext) -> None:
    # Implementation...
    pass
```

**Benefits of this registry approach:**

1. **Compile-time validation**: Stage signatures are checked against declared types at registration
2. **Pipeline validation**: Type compatibility checked when pipeline is loaded, not when executed
3. **Clear errors**: Helpful error messages show exactly which stages are incompatible
4. **Resource tracking**: Registry knows which resources each stage needs
5. **Documentation**: Stage metadata includes descriptions and type information
6. **Extensibility**: Users can register custom stages using the same decorator

### Alternative Registration (Without Decorators)

For simpler use cases or when decorators are not desired, stages can be registered directly:

```python
# Define stage function
def record_audio(input_data: None, context: PipelineContext) -> Optional[TemporaryAudioFile]:
    # Implementation...
    pass

# Register manually
STAGE_REGISTRY._stages["record_audio"] = StageMetadata(
    name="record_audio",
    function=record_audio,
    input_type=type(None),
    output_type=Optional[TemporaryAudioFile],
    description="Record audio until trigger completes",
    required_resources={Resource.AUDIO_INPUT}
)
```

However, the decorator approach is **strongly recommended** as it provides automatic type validation and keeps registration co-located with implementation.

### Future Extensibility: User-Defined Stages

The current implementation (Option 1 + 2) can be extended with dynamic imports (Option 3) in the future:

```python
# Future: Load custom stages from user config
def load_custom_stage(module_path: str, stage_name: str):
    """Dynamically import and register a user-defined stage"""
    module = importlib.import_module(module_path)
    stage_func = getattr(module, stage_name)

    # User must provide metadata via function attributes or config
    STAGE_REGISTRY._stages[stage_name] = StageMetadata(
        name=stage_name,
        function=stage_func,
        input_type=stage_func.__annotations__.get('input_data'),
        output_type=stage_func.__annotations__.get('return'),
        description=stage_func.__doc__ or "",
        required_resources=getattr(stage_func, 'required_resources', set())
    )
```

This would enable users to add custom stages without modifying the core codebase, but is **not part of the initial implementation**.

### Stage Lookup: How Pipelines Find Stages

When a pipeline executes, it looks up each stage by name using the registry:

```python
# In pipeline execution loop
for stage_name in pipeline.stages:
    # 1. Look up stage in registry (validates name exists)
    stage_metadata = STAGE_REGISTRY.get(stage_name)

    # 2. Get the actual function to execute
    stage_func = stage_metadata.function

    # 3. Execute the stage
    result = stage_func(result, context)
```

**Validation happens at two points:**

1. **Startup (load time)**: When pipelines are loaded from settings.toml, `STAGE_REGISTRY.validate_pipeline()` checks:
   - All stage names exist in registry
   - Type compatibility between consecutive stages
   - No type mismatches that would cause runtime errors

2. **Execution (runtime)**: `STAGE_REGISTRY.get()` raises `ValueError` if stage name not found
   - This should never happen if startup validation passed
   - Provides safety net for dynamic pipelines added at runtime

This design ensures **type safety** and **fail-fast behavior** while keeping the core implementation simple (dictionary lookup).

## Pipeline Manager

The Pipeline Manager is responsible for:

### Initialization
1. Load all pipelines from settings.toml on startup
2. Validate configuration:
   - Check no hotkey conflicts exist
   - Verify all stage names are registered
   - **Validate type compatibility** between consecutive stages using `STAGE_REGISTRY.validate_pipeline()`
   - Ensure required resources are available
3. Create default pipeline if no pipelines configured (backward compatibility)
4. Initialize the ResourceManager for resource-based locking
5. Initialize the HotkeyManager with all enabled pipelines

**Type validation happens at startup**, not during execution. This provides:
- **Fast failure**: Invalid pipelines are rejected before the application starts
- **Clear errors**: Users see exactly which stages are incompatible and why
- **No runtime surprises**: Type errors can't occur during pipeline execution

### Resource Manager
Manages resource locks to allow concurrent pipeline execution when resources don't conflict:

```python
from enum import Enum
from threading import Lock
from typing import Set

class Resource(Enum):
    """Available system resources that stages may lock"""
    AUDIO_INPUT = "audio_input"      # Microphone/audio capture device
    KEYBOARD = "keyboard"             # Virtual keyboard for typing
    CLIPBOARD = "clipboard"           # System clipboard
    # Future resources can be added here

class ResourceManager:
    """Manages resource locks for pipeline execution"""

    def __init__(self):
        self._locks = {resource: Lock() for resource in Resource}
        self._pipeline_resources = {}  # pipeline_id -> set of acquired resources

    def get_required_resources(self, stages: list[str]) -> Set[Resource]:
        """
        Determine which resources a pipeline needs based on its stages.

        Uses the stage registry to look up resource requirements, ensuring
        type safety and consistency with stage definitions.
        """
        resources = set()

        for stage_name in stages:
            stage_metadata = STAGE_REGISTRY.get(stage_name)
            resources.update(stage_metadata.required_resources)

        return resources

    def can_acquire(self, pipeline_id: str, resources: Set[Resource]) -> bool:
        """
        Check if all required resources are available (non-blocking).

        WARNING: This method should NOT be used as a pre-check before calling acquire()
        due to race conditions. Instead, call acquire() directly with blocking=False.
        This method is kept for informational/debugging purposes only.
        """
        return all(not lock.locked() for lock in
                   (self._locks[r] for r in resources))

    def acquire(self, pipeline_id: str, resources: Set[Resource],
                blocking: bool = True, timeout: float = None) -> bool:
        """
        Acquire all required resources atomically.

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
                if not self._locks[resource].acquire(blocking=blocking, timeout=timeout):
                    # Failed to acquire this lock, release all previous ones
                    for prev_resource in acquired:
                        self._locks[prev_resource].release()
                    return False
                acquired.append(resource)

            # Successfully acquired all resources
            self._pipeline_resources[pipeline_id] = resources
            return True

        except Exception:
            # On any error, release all acquired locks
            for resource in acquired:
                self._locks[resource].release()
            raise

    def release(self, pipeline_id: str):
        """Release all resources held by a pipeline"""
        if pipeline_id not in self._pipeline_resources:
            return

        resources = self._pipeline_resources.pop(pipeline_id)
        for resource in resources:
            self._locks[resource].release()

    def get_blocked_by(self, resources: Set[Resource]) -> Set[Resource]:
        """Return which of the requested resources are currently locked"""
        return {r for r in resources if self._locks[r].locked()}
```

### Hotkey Manager
Separate from pipelines, manages trigger events:

```python
class HotkeyManager:
    """Manages hotkey registration and triggers pipeline execution"""

    def __init__(self, pipelines: dict[str, Pipeline]):
        self.pipelines = pipelines
        self.hotkey_map = {}  # hotkey -> pipeline
        self.active_events = {}  # hotkey -> HotkeyTriggerEvent

    def register_all(self):
        """Register all pipeline hotkeys"""
        for pipeline in self.pipelines.values():
            if not pipeline.enabled:
                continue

            hotkey = pipeline.config.hotkey
            if hotkey in self.hotkey_map:
                raise ValueError(f"Hotkey conflict: '{hotkey}' used by multiple pipelines")

            self.hotkey_map[hotkey] = pipeline
            hotkey_listener.register(
                hotkey,
                on_press=lambda p=pipeline: self._on_press(p),
                on_release=lambda h=hotkey: self._on_release(h)
            )

    def _on_press(self, pipeline: Pipeline):
        """Handle hotkey press - create trigger event and execute pipeline"""
        trigger_event = HotkeyTriggerEvent()
        self.active_events[pipeline.config.hotkey] = trigger_event

        # Execute pipeline on thread pool (non-blocking)
        # This returns immediately, so hotkey listener never blocks
        self.pipeline_manager.trigger_pipeline(pipeline, trigger_event)

    def _on_release(self, hotkey: str):
        """Handle hotkey release - signal trigger event"""
        if hotkey in self.active_events:
            self.active_events[hotkey].signal_release()
            del self.active_events[hotkey]
```

### Pipeline Execution
1. Determine required resources based on pipeline stages
2. Attempt to acquire all required resources (non-blocking)
3. If resources unavailable: play error sound and return
4. If available: acquire resources and start pipeline
5. Create PipelineContext with trigger_event
6. Execute stages sequentially
7. Handle errors from any stage
8. Cleanup temporary resources
9. Release all acquired resources when complete or on error

### Cancellation Support
Pipelines can be cancelled by:
1. Pressing the same hotkey again (toggles cancel)
2. Pressing a global cancel key (e.g., ESC)
3. Via tray menu "Cancel" option
4. Programmatically via `pipeline.cancel()`

### Error Handling
When a stage fails:
1. Log the error with full traceback
2. Play error sound
3. Update tray icon to error state
4. Stop pipeline execution
5. Run cleanup tasks
6. Release all acquired resources

### Logging
- Debug log before each stage: `"Starting stage: {stage_name}"`
- Debug log after each stage: `"Stage {stage_name} output: {output}"`
- Info log on cancellation: `"Pipeline {name} cancelled"`
- Error log on failures: `"Pipeline {name} failed at stage {stage_name}"`

## Threading Model

Pipeline execution uses a thread pool executor to ensure non-blocking hotkey handling and graceful resource management.

### Threading Guarantees

1. **Pipeline Execution**: Each pipeline runs in a worker thread from a thread pool
2. **Concurrency**: Multiple pipelines can execute concurrently if they don't conflict on resources
3. **Pool Size**: Dynamic based on typical concurrency needs (e.g., max_workers=4)
4. **Stage Execution**: Stages run sequentially on the pipeline's worker thread
5. **Hotkey Thread**: Never blocks - immediately spawns pipeline execution in pool
6. **Resource Locking**: Thread-safe atomic acquisition of multiple resources
7. **Icon Updates**: Thread-safe via queue-based communication to icon thread
8. **Shutdown**: Graceful via `executor.shutdown(wait=True, timeout=5)`
9. **Cancellation**: Via `future.cancel()` which sets `context.cancel_requested`

### Thread Architecture

```
Main Thread
├── Hotkey Listener (pynput) ← Never blocks
│   └── on_hotkey_press() ← Fast, submits to thread pool
│   └── on_hotkey_release() ← Fast, signals trigger event
│
├── Pipeline Thread Pool (max_workers=4)
│   ├── Worker Thread 1 (Pipeline A)
│   │   ├── Acquire resources: {AUDIO_INPUT, KEYBOARD}
│   │   ├── record_audio() ← Blocks for user speech duration
│   │   ├── transcribe() ← Blocks for 1-5 seconds (STT inference)
│   │   ├── type_text() ← Blocks for 5-15 seconds (typing simulation)
│   │   └── Release resources
│   │
│   ├── Worker Thread 2 (Pipeline B) ← Can run concurrently if no resource conflict
│   │   ├── Acquire resources: {CLIPBOARD}
│   │   ├── transcribe_clipboard() ← Reads from clipboard
│   │   └── Release resources
│   │
│   └── (2 more workers available for concurrent pipelines)
│
└── Icon/Tray Thread (pystray)
    └── Processes icon updates via queue
```

### Why Thread Pool Instead of Daemon Threads?

The current implementation spawns daemon threads for each pipeline execution. The thread pool approach provides:

1. **Graceful Shutdown**: Can wait for in-progress pipelines to complete
2. **Concurrency Control**: Built-in limiting via pool size
3. **Resource Management**: Combined with ResourceManager for fine-grained locking
4. **Cancellation Support**: Futures can be cancelled cleanly
5. **Resource Cleanup**: Proper cleanup even on errors via finally blocks
6. **Better Testing**: Can wait for completion in tests

### Implementation Example

```python
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional
import uuid

class PipelineManager:
    """Manages pipeline execution with thread pool and resource locking"""

    def __init__(self, resource_manager: ResourceManager):
        # Multiple workers to support concurrent pipelines
        self.executor = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="pipeline"
        )
        self.resource_manager = resource_manager
        self.active_pipelines = {}  # pipeline_id -> Future

    def trigger_pipeline(self, pipeline: Pipeline, trigger_event: TriggerEvent):
        """
        Trigger pipeline execution from hotkey thread (non-blocking).

        This method returns immediately, submitting the pipeline to the thread pool.
        The hotkey listener never blocks.
        """
        # Generate unique ID for this pipeline execution
        pipeline_id = str(uuid.uuid4())

        # Determine required resources
        required_resources = self.resource_manager.get_required_resources(pipeline.stages)

        # Try to acquire resources atomically (non-blocking)
        # Note: Removed separate can_acquire() check to avoid race condition
        # (see Critical Issue #2 in pipeline_spec_review.md)
        if not self.resource_manager.acquire(pipeline_id, required_resources,
                                              blocking=False):
            # Immediate conflict - resources already in use
            blocked = self.resource_manager.get_blocked_by(required_resources)
            logger.warning(
                f"Cannot start pipeline {pipeline.name}: resources {blocked} in use"
            )
            play_sound(ERROR_SOUND)
            return

        # Submit to thread pool (returns immediately)
        future = self.executor.submit(
            self._execute_pipeline,
            pipeline,
            pipeline_id,
            required_resources,
            trigger_event
        )

        # Track active pipeline
        self.active_pipelines[pipeline_id] = future

        # Add callback for cleanup
        future.add_done_callback(lambda f: self._on_pipeline_complete(pipeline_id, f))

    def _execute_pipeline(self, pipeline: Pipeline, pipeline_id: str,
                          required_resources: Set[Resource], trigger_event: TriggerEvent):
        """
        Execute pipeline stages sequentially (runs on worker thread).

        This method runs on the thread pool worker and can block for as long
        as needed. It will not affect the hotkey listener responsiveness.
        """
        # Acquire resources (blocking with timeout)
        if not self.resource_manager.acquire(pipeline_id, required_resources,
                                             blocking=True, timeout=1.0):
            logger.error(f"Failed to acquire resources for pipeline {pipeline.name}")
            play_sound(ERROR_SOUND)
            return

        context = PipelineContext(
            config={},
            icon_controller=self.icon_controller,
            trigger_event=trigger_event,
            cancel_requested=threading.Event(),
            metadata={"speech_processor": self.speech_processor}
        )

        result = None
        try:
            for stage_name in pipeline.stages:
                # Check cancellation between stages
                if context.cancel_requested.is_set():
                    logger.info(f"Pipeline {pipeline.name} cancelled")
                    return

                logger.debug(f"Starting stage: {stage_name}")

                # Get stage function from registry (raises ValueError if unknown)
                stage_metadata = STAGE_REGISTRY.get(stage_name)
                stage_func = stage_metadata.function

                # Update stage config
                context.config = pipeline.config.get(stage_name, {})

                # Execute stage (may block for seconds)
                result = stage_func(result, context)

                logger.debug(f"Stage {stage_name} completed")

        except Exception as e:
            logger.error(f"Pipeline {pipeline.name} failed", exc_info=True)
            play_sound(ERROR_SOUND)
            self.icon_controller.set_icon("error")

        finally:
            # Always release resources
            self.resource_manager.release(pipeline_id)
            self.icon_controller.set_icon("idle")

    def _on_pipeline_complete(self, pipeline_id: str, future: Future):
        """Callback when pipeline completes (runs on worker thread)"""
        try:
            future.result()  # Re-raises any exceptions
        except Exception as e:
            logger.error(f"Pipeline failed with exception: {e}")
        finally:
            # Remove from active pipelines
            self.active_pipelines.pop(pipeline_id, None)

    def cancel_pipeline(self, pipeline_id: str):
        """Cancel a specific running pipeline"""
        if pipeline_id in self.active_pipelines:
            future = self.active_pipelines[pipeline_id]
            if not future.done():
                # Request cancellation (checked between stages)
                future.cancel()

    def shutdown(self, timeout: float = 5.0):
        """Gracefully shutdown pipeline manager with timeout"""
        logger.info("Shutting down pipeline manager...")

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
        logger.info("Pipeline manager shutdown complete")
```

### Blocking Operations Analysis

Each stage contains blocking operations that require execution off the hotkey thread:

| Stage | Blocking Operation | Duration | Why It Blocks |
|-------|-------------------|----------|---------------|
| `record_audio` | `trigger_event.wait_for_completion()` | 0-60s | Waits for user to release hotkey |
| `transcribe` | STT inference (local or API) | 1-10s | GPU/CPU computation or network I/O |
| `type_text` | Character-by-character typing | 5-15s | System keyboard simulation with delays |

**Total blocking time per pipeline**: 6-85 seconds

Without a separate thread, the hotkey listener would be frozen for this entire duration and unable to respond to new hotkey presses.

**Concurrent pipeline example**: While Pipeline A is typing (holding KEYBOARD lock), Pipeline B can start recording audio (acquiring AUDIO_INPUT lock) without conflict.

### Thread Safety Considerations

1. **Icon Controller**: Uses queue to send updates to icon thread (already thread-safe)
2. **Resource Locks**: Managed by ResourceManager with atomic acquisition
3. **Cancel Event**: `threading.Event` is thread-safe by design
4. **Stage Functions**: Must not share mutable state between pipelines
5. **Speech Processor**: Should be thread-safe or one instance per pipeline
6. **ResourceManager**: All lock operations are atomic and thread-safe

### Migration from Daemon Threads

Current code pattern:
```python
def on_hotkey_release():
    def transcribe_and_type():
        # Blocking operations here...
        pass

    threading.Thread(target=transcribe_and_type, daemon=True).start()
```

New code pattern:
```python
def on_hotkey_release():
    trigger_event.signal_release()
    pipeline_manager.trigger_pipeline(pipeline, trigger_event)
    # Returns immediately - hotkey listener never blocks
```

The actual blocking work happens in `pipeline_manager._execute_pipeline()` on a worker thread.

## Implementation Plan

### Phase 0: Design Clarification ✓
1. ✓ Resolve trigger event architecture
2. ✓ Define PipelineContext interface
3. ✓ Define TriggerEvent types
4. ✓ Resolve async/await vs synchronous execution (chose synchronous with thread pool)
5. ✓ Answer open questions (see below)

### Phase 1: Core Infrastructure
1. Create `TriggerEvent` base class and implementations:
   - `HotkeyTriggerEvent`
   - `TimerTriggerEvent`
   - `ProgrammaticTriggerEvent`
2. Create `PipelineContext` class with proper type annotations
3. Create `IconController` interface (wrapping existing tray icon)
4. **Create type-safe stage registry** using **Option 1 (dictionary-based)** with:
   - `StageMetadata` dataclass
   - `StageRegistry` class with dictionary storage (`_stages: Dict[str, StageMetadata]`)
   - Optional decorator syntax for cleaner registration
   - Type validation at registration time
   ```python
   @STAGE_REGISTRY.register(
       name="record_audio",
       input_type=type(None),
       output_type=Optional[TemporaryAudioFile],
       required_resources={Resource.AUDIO_INPUT}
   )
   def record_audio(input_data: None, context: PipelineContext) -> Optional[TemporaryAudioFile]: ...
   ```
5. Write unit tests for infrastructure, including:
   - Type validation tests
   - Pipeline compatibility tests
   - Resource requirement tracking
   - Registry lookup and error handling

### Phase 2: Pipeline Execution Engine
1. Implement `ResourceManager` for resource-based locking
2. Implement `Pipeline` class with:
   - Resource acquisition/release
   - Cancellation support
   - Cleanup handling
   - Thread pool executor integration
3. Implement `PipelineManager` for loading/validating pipelines:
   - **Call `STAGE_REGISTRY.validate_pipeline()` at startup**
   - Validate hotkey conflicts
   - Check resource availability
4. Implement `HotkeyManager` for trigger registration
5. Write unit tests for pipeline execution, including:
   - Type safety validation
   - Resource conflict scenarios
   - Concurrent pipeline execution

### Phase 3: Migrate Existing Stages
1. Refactor current recording logic into `record_audio` stage with proper type signature
2. Refactor current transcription logic into `transcribe` stage with proper type signature
3. Refactor current typing logic into `type_text` stage with proper type signature
4. **Register each stage with `@STAGE_REGISTRY.register()` decorator**
5. Ensure each stage follows new interface (input_data: TInput, context: PipelineContext) -> TOutput
6. Test each stage independently with type checking enabled (mypy/pyright)

### Phase 4: Configuration & Integration
1. Update settings parsing to support new format
2. Add backward compatibility for old settings format
3. Create default pipeline if no pipelines configured
4. Wire up Pipeline Manager to application startup
5. Integration testing with full pipeline

### Phase 5: Multi-Pipeline Support
1. Test multiple hotkeys
2. Test hotkey conflict detection
3. Test pipeline cancellation (same hotkey again, ESC, tray menu)
4. Test programmatic pipeline triggering

### Phase 6: Polish & Documentation
1. Add comprehensive logging with structured output
2. Add observability/metrics tracking
3. Test error handling and recovery scenarios
4. Document pipeline configuration format
5. Update README with pipeline examples
6. Create migration guide for existing users

## Future Extensibility

### Custom Stages
- Users can define custom Python functions
- Custom stages registered via configuration or plugin system
- Same interface as built-in stages

### Additional Built-in Stages (Future)
- `typo_fix`: Correct common typos in text
- `llm_process`: Apply LLM transformations (formatting, tone adjustment, etc.)
- `text_replace`: Apply regex or simple replacements
- `preview_text`: Show preview before typing
- `save_text`: Save to file or clipboard

### Potential Enhancements (Future)
- Conditional branching between stages
- Parallel stage execution
- Stage output caching
- Pipeline templates/presets
- Per-pipeline error handling strategies

## Migration Notes

### Backward Compatibility
- Existing `[voice]` and `[hotkey]` sections remain valid
- If no `[pipelines]` section exists, create default pipeline from existing settings
- Migration function converts old format to new format automatically
- Warning logged on first run with legacy format

### Default Pipeline Creation
```python
def migrate_legacy_settings(data: dict) -> dict:
    """Convert old format to new pipeline format"""
    if "pipelines" in data:
        return data  # Already using new format

    voice_config = data.get("voice", {})
    hotkey_config = data.get("hotkey", {})

    default_pipeline = {
        "name": "default",
        "enabled": True,
        "hotkey": hotkey_config.get("hotkey", "<pause>"),
        "stages": [
            {"func": "record_audio"},
            {
                "func": "transcribe",
                "provider": voice_config.get("provider", "local"),
                "minimum_duration": voice_config.get("minimum_duration", 0.25),
            },
            {"func": "type_text"}
        ]
    }

    return {**data, "pipelines": [default_pipeline]}
```

## Resolved Design Questions

### 1. Should there be a default pipeline if none is configured?
**Answer: YES**
- For backward compatibility, create default pipeline from legacy `[voice]` and `[hotkey]` sections
- For new installations, provide sensible default in example settings.toml
- Default pipeline: `record_audio` → `transcribe` → `type_text` with `<pause>` hotkey

### 2. How should we handle hotkey conflicts between pipelines?
**Answer: Validate at startup and reject**
- `HotkeyManager.register_all()` validates all hotkeys are unique
- Raises `ValueError` with clear message showing conflicting pipelines
- Application fails to start if conflicts detected (fail-fast)
- User must fix settings.toml before application can run

### 3. Should pipelines be able to be triggered programmatically (not just via hotkey)?
**Answer: YES**
- Useful for testing
- Useful for future integrations (CLI, API, scripting)
- Pipeline class provides `execute(trigger_event=None)` method
- PipelineManager provides `trigger(pipeline_name, trigger_event=None)` method

### 4. Should there be a way to cancel/abort a running pipeline?
**Answer: YES - Multiple methods**
- Press same hotkey again (toggle cancel)
- Press global cancel key (ESC - optional, configurable)
- Via tray menu "Cancel Pipeline" option (grayed when idle)
- Programmatically via `pipeline.cancel()` method
- All methods set `context.cancel_requested` event, checked between stages

## Type Safety Resolution Summary

This specification resolves the type safety issues identified in the critical review (Issue #5) through:

### 1. **Generic Type System**
- Replaced `Any` types with `TypeVar`-based generics
- Introduced `StageFunction[TInput, TOutput]` protocol
- Created concrete type aliases for common stage patterns:
  - `AudioRecordingStage = StageFunction[None, Optional[str]]`
  - `TranscriptionStage = StageFunction[Optional[str], Optional[str]]`
  - `TypingStage = StageFunction[Optional[str], None]`

### 2. **Stage Registry with Validation**
- `StageRegistry` class enforces type consistency at registration time
- Decorator validates function signatures match declared types using `get_type_hints()`
- Pipeline validation checks type compatibility between consecutive stages
- Clear error messages show exactly which types are incompatible

### 3. **Compile-Time Type Checking**
- Type checkers (mypy, pyright) can verify:
  - Stage input/output types match
  - Pipeline compositions are valid
  - Function signatures are correct
- IDE autocomplete knows expected types
- Refactoring safety: changing a stage's type shows affected pipelines

### 4. **Runtime Validation**
- `STAGE_REGISTRY.validate_pipeline()` called at application startup
- Type mismatches detected before pipeline execution
- Fail-fast with helpful error messages
- No runtime type errors during execution

### 5. **Benefits Over Previous Approach**
| Aspect | Before (Issue #5) | After (This Spec) |
|--------|-------------------|-------------------|
| Type annotations | `Any` (no checking) | `TypeVar` generics (full checking) |
| Validation timing | Runtime (during execution) | Startup (before execution) |
| Error clarity | Generic failures | Specific type mismatches |
| IDE support | None | Full autocomplete |
| Refactoring | Manual checking | Automatic detection |
| Custom stages | Unclear requirements | Explicit type signatures |

### Example: Type Error Caught at Startup

```python
# Invalid pipeline configuration
[pipelines.broken]
stages = ["record_audio", "type_text", "transcribe"]

# Application startup will fail with:
# TypeError: Type mismatch in pipeline: stage 'type_text' outputs
# <class 'NoneType'> but stage 'transcribe' expects typing.Optional[str]
```

This prevents runtime failures and provides clear guidance for fixing the configuration.
