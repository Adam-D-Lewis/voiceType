# voiceType - type with your voice

![voiceType Logo](voicetype/assets/imgs/yellow-splotch-logo.png)

[![Tests](https://github.com/Adam-D-Lewis/voicetype/actions/workflows/tests.yaml/badge.svg)](https://github.com/Adam-D-Lewis/voicetype/actions/workflows/tests.yaml)

## Features

- Press a hotkey (default: `Pause/Break` key) to start recording audio.
- Release the hotkey to stop recording.
- The recorded audio is transcribed to text (e.g., using OpenAI's Whisper model).
- The transcribed text is typed into the currently active application.

## Prerequisites

- Python 3.8+
- `pip` (Python package installer)
- For Linux installation: `systemd` (common in most modern Linux distributions)
- For Linux: `sudo` access (required for keyboard capture - see [Linux Architecture](#linux-architecture))
- An OpenAI API Key (if using OpenAI for transcription)

## Installation

### Option 1: Install from PyPI

```bash
pip install voicetype2
```

### Option 2: Install from Source

1.  **Clone the repository (including submodules):**
    ```bash
    git clone --recurse-submodules https://github.com/Adam-D-Lewis/voicetype.git
    cd voicetype
    ```

    If you already cloned without `--recurse-submodules`, initialize the submodules:
    ```bash
    git submodule update --init --recursive
    ```

2.  **Set up a Python virtual environment (recommended):**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`
    ```

3.  **Install the package and its dependencies:**
    This project uses `pyproject.toml` with `setuptools`. Install the `voicetype` package and its dependencies using pip:
    ```bash
    pip install .
    ```
    This command reads `pyproject.toml`, installs all necessary dependencies, and makes the `voicetype` script available (callable as `python -m voicetype`).

4.  **Run the installation script (for Linux with systemd):**
    If you are on Linux and want to run VoiceType as a systemd service (recommended for background operation and auto-start on login), use the CLI entrypoint installed with the package. Ensure you're in the environment where you installed dependencies.
    ```bash
    voicetype install
    ```
    During install you'll be prompted to:
    - Choose a provider [litellm, local]. If you choose `litellm` you'll be prompted for your `OPENAI_API_KEY`
    - Enter a hotkey (default: `<pause>`)

    The script will create **two systemd services** (see [Linux Architecture](#linux-architecture)):
    - `voicetype-listener.service` - System service running as root for keyboard capture
    - `voicetype.service` - User service running as your user for the tray icon

    Configuration is stored in `~/.config/voicetype/.env` with restricted permissions.

    For other operating systems, or if you prefer not to use the systemd service on Linux, you can run the application directly after installation (see Usage).

## Configuration

VoiceType can be configured using a `settings.toml` file. The application looks for configuration files in the following locations (in priority order):

1. `./settings.toml` - Current directory
2. `~/.config/voicetype/settings.toml` - User config directory
3. `/etc/voicetype/settings.toml` - System-wide config

### Available Settings

VoiceType uses a pipeline-based configuration system. See [settings.example.toml](settings.example.toml) for a complete, documented example configuration including:

- Stage definitions (RecordAudio, Transcribe, CorrectTypos, TypeText, LLMAgent)
- Local and cloud transcription options with fallback support
- Pipeline configuration with hotkey bindings
- Telemetry and logging settings

**Note:** If you used `voicetype install` and configured litellm during installation, your API key is stored separately in `~/.config/voicetype/.env`.

## Monitoring Pipeline Performance with OpenTelemetry

VoiceType includes built-in OpenTelemetry instrumentation to track pipeline execution and stage performance. When enabled, traces are exported to a local file for offline analysis.

### Enabling Telemetry

Telemetry is disabled by default. To enable it, add to your `settings.toml`:

```toml
[telemetry]
enabled = true
```

### Trace File Location

Traces are automatically saved to:
- Linux: `~/.config/voicetype/traces.jsonl`
- macOS: `~/Library/Application Support/voicetype/traces.jsonl`
- Windows: `%APPDATA%/voicetype/traces.jsonl`

### What You Can See

Each pipeline execution creates a trace with:
- **Overall pipeline duration** - Total time from start to finish
- **Individual stage timings** - How long each stage (RecordAudio, Transcribe, etc.) took
- **Pipeline metadata** - Pipeline name, ID, stage count
- **Error tracking** - Any exceptions or failures with stack traces

### Example Trace

Each span is written as a JSON line:
```json
{
  "name": "pipeline.default",
  "context": {...},
  "start_time": 1234567890,
  "end_time": 1234567895,
  "attributes": {
    "pipeline.id": "abc-123",
    "pipeline.name": "default",
    "pipeline.duration_ms": 5200
  }
}
```

### Managing Trace Files

**Automatic rotation:**
Trace files are automatically rotated when they reach 10 MB. Rotated files are timestamped (e.g., `traces.20250117_143022.jsonl`) and kept indefinitely.

**View traces:**
```bash
# Pretty-print the current trace file
cat ~/.config/voicetype/traces.jsonl | jq

# View all trace files (including rotated)
cat ~/.config/voicetype/traces*.jsonl | jq

# Or just view in any text editor
cat ~/.config/voicetype/traces.jsonl
```

**Clear old traces:**
```bash
# Delete all trace files
rm ~/.config/voicetype/traces*.jsonl
```

**Analyze with grep:**
```bash
# Find slow stages in current file
grep "duration_ms" ~/.config/voicetype/traces.jsonl | grep -E "duration_ms\":[0-9]{4,}"

# Search across all trace files
grep "duration_ms" ~/.config/voicetype/traces*.jsonl | grep -E "duration_ms\":[0-9]{4,}"
```

### Configuration

**Custom trace file location:**
```toml
[telemetry]
enabled = true
trace_file = "~/my-custom-traces.jsonl"
```

**Adjust rotation size or disable rotation:**
```toml
[telemetry]
enabled = true
rotation_max_size_mb = 50  # Rotate at 50 MB instead of 10 MB

# Or disable rotation entirely
# rotation_enabled = false
```

**Export to OTLP endpoint only (disable file export):**
```toml
[telemetry]
enabled = true
export_to_file = false
otlp_endpoint = "http://localhost:4317"
```

## Usage

-   **If using the Linux systemd service:** Both services will start automatically on login. VoiceType will be listening for the hotkey in the background.

-   **To run manually on Linux (for testing):**
    You need to run two processes in separate terminals:

    **Terminal 1 - Start the privileged keyboard service:**
    ```bash
    sudo python -m voicetype.hotkey_listener.privileged_service \
        --socket /run/user/$(id -u)/voicetype-hotkey.sock \
        --hotkey "<pause>"
    ```

    **Terminal 2 - Start the main application:**
    ```bash
    python -m voicetype
    ```

-   **To run on Windows or macOS:**
    No privilege separation is needed. Simply run:
    ```bash
    python -m voicetype
    ```

**Using the Hotkey:**
1.  Press and hold the configured hotkey (default is `Pause/Break`).
2.  Speak clearly.
3.  Release the hotkey to stop recording.
4.  The transcribed text should then be typed into your currently active application.

## Managing the Service (Linux with systemd)

If you used `voicetype install`:

-   **Check service status:**
    ```bash
    voicetype status
    ```
    Or check each service individually:
    ```bash
    systemctl --user status voicetype.service
    sudo systemctl status voicetype-service.service
    ```

-   **View service logs:**
    ```bash
    # Main application logs
    journalctl --user -u voicetype.service -f

    # Keyboard service logs
    sudo journalctl -u voicetype-service.service -f
    ```

-   **Restart the services:**
    (e.g., after changing the `OPENAI_API_KEY` in `~/.config/voicetype/.env`)
    ```bash
    systemctl --user restart voicetype.service
    sudo systemctl restart voicetype-service.service
    ```

-   **Stop the services:**
    ```bash
    systemctl --user stop voicetype.service
    sudo systemctl stop voicetype-service.service
    ```

-   **Start the services manually:**
    ```bash
    sudo systemctl start voicetype-service.service
    systemctl --user start voicetype.service
    ```

-   **Disable auto-start on login:**
    ```bash
    systemctl --user disable voicetype.service
    sudo systemctl disable voicetype-service.service
    ```

-   **Enable auto-start on login (if previously disabled):**
    ```bash
    sudo systemctl enable voicetype-service.service
    systemctl --user enable voicetype.service
    ```

## Uninstallation (Linux with systemd)

To stop the services, disable auto-start, and remove the systemd service files and associated configuration:
```bash
voicetype uninstall
```
This will:
- Stop and disable both `voicetype.service` and `voicetype-service.service`
- Remove the user service file (`~/.config/systemd/user/voicetype.service`)
- Remove the system service file (`/etc/systemd/system/voicetype-service.service`)
- Remove the environment file (`~/.config/voicetype/.env` containing your API key)
- Attempt to remove the application configuration directory (`~/.config/voicetype`) if it's empty

If you installed the package using `pip install .`, you can uninstall it from your Python environment with:
```bash
pip uninstall voicetype
```

## Linux Architecture

On Linux, VoiceType uses a **two-process architecture** to handle a conflict between keyboard I/O and the system tray:

1. **The Problem:**
   - Keyboard capture requires root access to read from `/dev/input` devices
   - Reliable keyboard typing on Wayland also benefits from elevated privileges
   - `pystray` (system tray) requires access to the user's D-Bus session
   - Running the entire app as root breaks the tray icon

2. **The Solution:**
   - **Privileged Service** (`voicetype-service.service`): Runs as root, uses evdev to capture keyboard events directly from `/dev/input`, and handles keyboard typing via pynput (works reliably on Wayland)
   - **Main Application** (`voicetype.service`): Runs as your user, handles the tray icon, transcription, and orchestrates the pipeline

3. **Communication:**
   - The two processes communicate via a Unix socket at `/run/user/<uid>/voicetype-hotkey.sock`
   - The socket is created by the privileged service with permissions allowing the user to connect
   - Bidirectional: hotkey events flow from service → app, text to type flows from app → service

4. **Wayland Support:**
   - The evdev-based listener works on both X11 and Wayland for keyboard capture
   - Keyboard typing via the privileged service also works reliably on Wayland

This architecture is **only needed on Linux**. On Windows and macOS, `pynput` works without elevated privileges, so a single process handles everything.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## Architecture

VoiceType uses a pipeline-based architecture with resource-based concurrency control. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for:
- Complete system architecture diagram (Mermaid UML)
- Component descriptions and responsibilities
- Execution flow and lifecycle
- Design principles and extension points

### Platform-Specific Keyboard Handling

- **Linux**: Uses direct evdev access for keyboard capture (works on both X11 and Wayland)
- **Windows/macOS**: Uses pynput for keyboard capture

## Development

Preferred workflow: Pixi

- Pixi is the preferred way to create and manage the development environment for this project. It ensures reproducible, cross-platform setups using the definitions in pyproject.toml.

Setup Pixi
- Install Pixi:
  - Linux/macOS (official installer):
    - curl -fsSL https://pixi.sh/install.sh | bash
  - macOS (Homebrew):
    - brew install prefix-dev/pixi/pixi
  - Verify:
    - pixi --version

Development Environments

Available Pixi environments:
- **local**: Standard development environment (default)
  - `pixi install -e local && pixi shell -e local`
- **dev**: Development with testing tools
  - `pixi install -e dev && pixi shell -e dev`
- **cpu**: CPU-only (no CUDA dependencies)
  - `pixi install -e cpu && pixi shell -e cpu`
- **windows-build**: Build Windows installers (PyInstaller + dependencies)
  - `pixi install -e windows-build && pixi shell -e windows-build`

Run the application
- pixi run voicetype
  - Equivalent to:
    - python -m voicetype

Run tests
- If a test task is defined:
  - pixi run test
- Otherwise (pytest directly):
  - pixi run python -m pytest

Lint and format
- If tasks are defined:
  - pixi run lint
  - pixi run fmt
- Or run tools directly:
  - pixi run ruff format
  - pixi run ruff check .

Pre-commit hooks (recommended)
- Install hooks:
  - pixi run pre-commit install
- Run on all files:
  - pixi run pre-commit run --all-files

Building Windows Installers (Windows only)

Using Pixi:
- Setup build environment:
  - `pixi install -e windows-build`
  - `pixi shell -e windows-build`
- Install NSIS (one-time):
  - Download from https://nsis.sourceforge.io/Download
  - Or via Chocolatey: `choco install nsis`
- Build installer:
  - `pixi run -e windows-build build-windows`
  - Output: `dist/VoiceType-Setup.exe`

Or build executable only (no installer):
- `pixi run -e windows-build build-exe`
- Output: `dist/voicetype/voicetype.exe`

Clean build artifacts:
- `pixi run -e windows-build clean-build`

See [docs/BUILDING.md](docs/BUILDING.md) for detailed build instructions.

Alternative: Python venv (fallback)
- Ensure Python 3.11+ is installed.
- Create and activate a venv:
  - python -m venv .venv
  - source .venv/bin/activate
- Editable install with dev dependencies:
  - pip install -U pip
  - pip install -e ".[dev]"
- Run the app:
  - python -m voicetype

Notes
- Dependency definitions live in pyproject.toml
- After changing dependencies, update pyproject.toml then run:
  - pixi install
## License
This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
