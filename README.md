# voiceType

![voiceType Logo](voicetype/assets/imgs/yellow-splotch-logo.png)

Type with your voice.

## Features

- Press a hotkey (default: `Pause/Break` key) to start recording audio.
- Release the hotkey to stop recording.
- The recorded audio is transcribed to text (e.g., using OpenAI's Whisper model).
- The transcribed text is typed into the currently active application.

## Prerequisites

- Python 3.8+
- `pip` (Python package installer)
- For Linux installation: `systemd` (common in most modern Linux distributions).
- An OpenAI API Key (if using OpenAI for transcription).

## Installation

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
    If you are on Linux and want to run VoiceType as a systemd user service (recommended for background operation and auto-start on login), use the CLI entrypoint installed with the package. Ensure you're in the environment where you installed dependencies.
    ```bash
    voicetype install
    ```
    During install you'll be prompted to choose a provider [litellm, local]. If you choose `litellm` you'll then be prompted for your `OPENAI_API_KEY`. Values are stored in `~/.config/voicetype/.env` with restricted permissions.

    The script will:
    - Create a systemd service file at `~/.config/systemd/user/voicetype.service`.
    - Store your OpenAI API key in `~/.config/voicetype/.env` (with restricted permissions).
    - Reload the systemd user daemon, enable the `voicetype.service` to start on login, and start it immediately.

    For other operating systems, or if you prefer not to use the systemd service on Linux, you can run the application directly after installation (see Usage).

## Configuration

VoiceType can be configured using a `settings.toml` file. The application looks for configuration files in the following locations (in priority order):

1. `./settings.toml` - Current directory
2. `~/.config/voicetype/settings.toml` - User config directory
3. `/etc/voicetype/settings.toml` - System-wide config

### Available Settings

Create a `settings.toml` file with any of the following options:

```toml
[voice]
# Provider for voice transcription (default: "local")
# Options: "litellm" (requires OpenAI API key) or "local" (uses faster-whisper locally)
provider = "local"

# Minimum duration (in seconds) of audio to process (default: 0.25)
# Filters out accidental hotkey presses
minimum_duration = 0.25

[hotkey]
# Global hotkey to trigger recording (default: "<pause>")
# Use pynput format, e.g., "<f12>", "<ctrl>+<alt>+r", "<pause>"
hotkey = "<pause>"
```

**Note:** If you used `voicetype install` and configured litellm during installation, your API key is stored separately in `~/.config/voicetype/.env`.

## Usage

-   **If using the Linux systemd service:** The service will start automatically on login. VoiceType will be listening for the hotkey in the background.
-   **To run manually (e.g., for testing or on non-Linux systems):**
    Activate your virtual environment and run:
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
    Alternatively:
    ```bash
    systemctl --user status voicetype.service
    ```

-   **View service logs:**
    ```bash
    journalctl --user -u voicetype.service -f
    ```

-   **Restart the service:**
    (e.g., after changing the `OPENAI_API_KEY` in `~/.config/voicetype/.env`)
    ```bash
    systemctl --user restart voicetype.service
    ```

-   **Stop the service:**
    ```bash
    systemctl --user stop voicetype.service
    ```

-   **Start the service manually (if not enabled to start on login):**
    ```bash
    systemctl --user start voicetype.service
    ```

-   **Disable auto-start on login:**
    ```bash
    systemctl --user disable voicetype.service
    ```

-   **Enable auto-start on login (if previously disabled):**
    ```bash
    systemctl --user enable voicetype.service
    ```

## Uninstallation (Linux with systemd)

To stop the service, disable auto-start, and remove the systemd service file and associated configuration:
```bash
voicetype uninstall
```
This will:
- Stop and disable the `voicetype.service`.
- Remove the service file (`~/.config/systemd/user/voicetype.service`).
- Remove the environment file (`~/.config/voicetype/.env` containing your API key).
- Attempt to remove the application configuration directory (`~/.config/voicetype`) if it's empty.

If you installed the package using `pip install .`, you can uninstall it from your Python environment with:
```bash
pip uninstall voicetype
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## Architecture

VoiceType uses a pipeline-based architecture with resource-based concurrency control. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for:
- Complete system architecture diagram (Mermaid UML)
- Component descriptions and responsibilities
- Execution flow and lifecycle
- Design principles and extension points

## Development

Preferred workflow: Pixi

- Pixi is the preferred way to create and manage the development environment for this project. It ensures reproducible, cross-platform setups using the definitions in environment.yaml and pyproject.toml.

Setup Pixi
- Install Pixi:
  - Linux/macOS (official installer):
    - curl -fsSL https://pixi.sh/install.sh | bash
  - macOS (Homebrew):
    - brew install prefix-dev/pixi/pixi
  - Verify:
    - pixi --version

Create and activate the environment
- From the project root:
  - pixi install -e local
  - pixi shell -e local

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
- Dependency definitions live in pyproject.toml; additional environment details may be in environment.yaml.
- After changing dependencies, update pyproject.toml (and environment.yaml if needed), then run:
  - pixi install
## License
This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
