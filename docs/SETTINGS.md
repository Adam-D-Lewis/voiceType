# VoiceType Settings Configuration

VoiceType uses TOML configuration files to define voice transcription pipelines.

## Settings File Locations

Settings files are searched in the following order:

1. `./settings.toml` (current directory)
2. `~/.config/voicetype/settings.toml` (user config)
3. `/etc/voicetype/settings.toml` (system-wide)

You can also specify a custom settings file using the `--settings-file` command-line argument.

## Quick Start

Copy the example settings file:

```bash
cp settings.example.toml settings.toml
```

The default configuration provides a basic voice-to-text pipeline using the Pause key.

## Pipeline Configuration

Pipelines define sequences of stages that process voice input. Each pipeline consists of:

- **name**: Unique identifier for the pipeline
- **enabled**: Whether the pipeline is active (true/false)
- **hotkey**: Key combination to trigger the pipeline
- **stages**: Ordered list of processing stages

### Example Pipeline

```toml
[[pipelines]]
name = "default"
enabled = true
hotkey = "<pause>"

[[pipelines.stages]]
func = "record_audio"

[[pipelines.stages]]
func = "transcribe"
provider = "local"
minimum_duration = 0.25

[[pipelines.stages]]
func = "type_text"
```

## Available Stages

### record_audio

Records audio while the hotkey is held down.

**Parameters:** None

**Input:** None
**Output:** Audio file (automatically cleaned up)

---

### transcribe

Converts recorded audio to text using speech recognition.

**Parameters:**
- `provider` (string): Transcription provider
  - `"local"`: Uses faster-whisper for local transcription (default, offline)
  - `"litellm"`: Uses cloud-based transcription (requires API key)
- `minimum_duration` (float): Minimum audio duration in seconds to process (default: 0.25)

**Input:** Audio file
**Output:** Transcribed text string

---

### type_text

Types the transcribed text at the current cursor position.

**Parameters:** None

**Input:** Text string
**Output:** None

## Hotkey Format

Hotkeys can be:

- **Special keys**: `<pause>`, `<f1>`, `<f2>`, ..., `<f12>`, `<esc>`, etc.
- **With modifiers**: `<ctrl>+<alt>+p`, `<shift>+<f1>`, etc.
- **Regular keys**: `a`, `b`, `1`, `2`, etc.

**Note:** The current implementation supports one active hotkey at a time (the first enabled pipeline's hotkey).

## Multiple Pipelines

You can define multiple pipelines with different configurations:

```toml
# Fast local transcription
[[pipelines]]
name = "quick_transcribe"
enabled = true
hotkey = "<pause>"

[[pipelines.stages]]
func = "record_audio"

[[pipelines.stages]]
func = "transcribe"
provider = "local"
minimum_duration = 0.25

[[pipelines.stages]]
func = "type_text"


# Higher quality cloud transcription (disabled by default)
[[pipelines]]
name = "cloud_transcribe"
enabled = false
hotkey = "<f12>"

[[pipelines.stages]]
func = "record_audio"

[[pipelines.stages]]
func = "transcribe"
provider = "litellm"
minimum_duration = 0.5

[[pipelines.stages]]
func = "type_text"
```

## Legacy Configuration

For backward compatibility, the old configuration format is still supported:

```toml
[voice]
provider = "local"
minimum_duration = 0.25

[hotkey]
hotkey = "<pause>"
```

These settings are automatically migrated to a default pipeline configuration at runtime.

## Command-Line Usage

```bash
# Use default settings location
voicetype

# Use custom settings file
voicetype --settings-file /path/to/settings.toml
```

## Troubleshooting

### "No pipelines configured" warning

This means no `[[pipelines]]` section was found in your settings file. Either:
1. Copy `settings.example.toml` to `settings.toml`
2. Add legacy `[voice]` and `[hotkey]` sections (will be auto-migrated)

### "No enabled pipelines found" warning

All pipelines have `enabled = false`. Set at least one pipeline to `enabled = true`.

### Hotkey not working

- Ensure the hotkey format is correct (e.g., `<pause>` not `pause`)
- Check system permissions for keyboard input
- On Linux Wayland, ensure XWayland is available
