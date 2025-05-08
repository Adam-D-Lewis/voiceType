# voiceType

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

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/voicetype.git # Replace with the actual URL if different
    cd voicetype
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
    If you are on Linux and want to run VoiceType as a systemd user service (recommended for background operation and auto-start on login), use the `voicetype/install.py` script.
    ```bash
    python voicetype/install.py install
    ```
    You will be prompted to enter your `OPENAI_API_KEY`. This key will be stored securely in `~/.config/voicetype/.env`.

    The script will:
    - Create a systemd service file at `~/.config/systemd/user/voicetype.service`.
    - Store your OpenAI API key in `~/.config/voicetype/.env` (with restricted permissions).
    - Reload the systemd user daemon, enable the `voicetype.service` to start on login, and start it immediately.

    For other operating systems, or if you prefer not to use the systemd service on Linux, you can run the application directly after installation (see Usage).

## Usage

-   **If using the Linux systemd service:** The service will start automatically on login. VoiceType will be listening for the hotkey in the background.
-   **To run manually (e.g., for testing or on non-Linux systems):**
    Activate your virtual environment and run:
    ```bash
    python -m voicetype
    ```

**Using the Hotkey:**
1.  Press and hold the configured hotkey (default is the `Pause/Break` key, as specified in `voicetype/__main__.py`).
2.  Speak clearly.
3.  Release the hotkey to stop recording.
4.  The transcribed text should then be typed into your currently active application.

## Managing the Service (Linux with systemd)

If you used `voicetype/install.py install`:

-   **Check service status:**
    ```bash
    python voicetype/install.py status
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
python voicetype/install.py uninstall
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

## License
This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
