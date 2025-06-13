import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

SERVICE_NAME = "voicetype.service"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_FILE_PATH = SYSTEMD_USER_DIR / SERVICE_NAME

APP_CONFIG_DIR = Path.home() / ".config" / "voicetype"
ENV_FILE_PATH = APP_CONFIG_DIR / ".env"


def get_project_root() -> Path:
    """
    Determines the project root directory.
    Assumes this script (install.py) is in <project_root>/voicetype/install.py
    """
    # Path(__file__).resolve() is /path/to/project/voicetype/install.py
    # Path(__file__).resolve().parent is /path/to/project/voicetype/
    # Path(__file__).resolve().parent.parent is /path/to/project/
    return Path(__file__).resolve().parent.parent


def get_service_file_content() -> str:
    """Generates the content for the systemd service file."""
    python_executable = sys.executable
    project_root = get_project_root()

    # Use `python -m voicetype` to run the application.
    # This assumes `voicetype` is a package with a `__main__.py` file.
    # `WorkingDirectory` is set to the project root, so Python can find the `voicetype` module.
    exec_start = f"{shlex.quote(python_executable)} -m voicetype"
    working_directory = shlex.quote(str(project_root))
    # %h in systemd unit files expands to the user's home directory.
    # The '-' before the path means that systemd will not fail if the file is missing.
    environment_file_path = f"-{shlex.quote(str(ENV_FILE_PATH))}"

    return f"""[Unit]
Description=VoiceType Application
# Start after the graphical session is available
After=graphical-session.target
# If the graphical session is stopped, this service will be stopped too
PartOf=graphical-session.target

[Service]
ExecStart={exec_start}
WorkingDirectory={working_directory}
Restart=always
RestartSec=5
# Ensures Python output is not buffered, useful for journald logging
Environment="PYTHONUNBUFFERED=1"
# Load environment variables from the specified file
EnvironmentFile={environment_file_path}
# StandardOutput=journal # Systemd default for user services
# StandardError=journal  # Systemd default for user services

[Install]
# Enable this service for the default user target (starts on login)
WantedBy=default.target
"""


def run_systemctl_command(command: list[str], ignore_errors: bool = False):
    """Runs a systemctl command."""
    try:
        full_command = ["systemctl", "--user"] + command
        print(f"Running: {' '.join(full_command)}")
        # For commands like stop/disable during uninstall, we might not want to exit on error
        if ignore_errors:
            subprocess.run(full_command, check=False)
        else:
            subprocess.run(full_command, check=True)
        print("Command processed.")
    except subprocess.CalledProcessError as e:
        if not ignore_errors:
            print(
                f"Error running command: {' '.join(full_command)}\n{e}", file=sys.stderr
            )
            sys.exit(1)
        else:
            print(
                f"Command {' '.join(full_command)} failed but errors are ignored. Error: {e}",
                file=sys.stderr,
            )
    except FileNotFoundError:
        print(
            "Error: systemctl command not found. Is systemd running and in your PATH?",
            file=sys.stderr,
        )
        sys.exit(1)


def install_service():
    """Installs and starts the systemd user service."""
    print(f"Installing VoiceType systemd user service ('{SERVICE_NAME}')...")

    if sys.platform != "linux":
        print(
            "This installation is for Linux systems with systemd only.", file=sys.stderr
        )
        sys.exit(1)

    # --- Provider and API Key Configuration ---
    provider = ""
    while provider not in ["litellm", "local"]:
        provider = input("Choose a voice provider [litellm, local]: ").strip().lower()
        if provider not in ["litellm", "local"]:
            print("Invalid provider. Please choose 'litellm' or 'local'.")

    env_vars = {"VOICE__PROVIDER": provider}

    if provider == "litellm":
        api_key = input("Please enter your OPENAI_API_KEY: ").strip()
        if not api_key:
            print(
                "OPENAI_API_KEY cannot be empty for the 'litellm' provider. Installation aborted.",
                file=sys.stderr,
            )
            sys.exit(1)
        env_vars["OPENAI_API_KEY"] = api_key

    # Create app config directory and .env file
    APP_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(ENV_FILE_PATH, "w") as f:
            for key, value in env_vars.items():
                f.write(f"{key}={shlex.quote(value)}\n")
        # Set restrictive permissions for the .env file
        os.chmod(ENV_FILE_PATH, 0o600)
        print(f"Configuration stored in {ENV_FILE_PATH}")
    except IOError as e:
        print(
            f"Error writing environment file to {ENV_FILE_PATH}: {e}", file=sys.stderr
        )
        sys.exit(1)

    # Create systemd service file
    service_content = get_service_file_content()
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with open(SERVICE_FILE_PATH, "w") as f:
            f.write(service_content)
        print(f"Service file created at {SERVICE_FILE_PATH}")
    except IOError as e:
        print(f"Error writing service file: {e}", file=sys.stderr)
        # Attempt to clean up the .env file if service file creation fails
        if ENV_FILE_PATH.exists():
            try:
                ENV_FILE_PATH.unlink()
            except OSError:
                pass  # Ignore error during cleanup
        sys.exit(1)

    run_systemctl_command(["daemon-reload"])
    run_systemctl_command(["enable", SERVICE_NAME])
    run_systemctl_command(["start", SERVICE_NAME])

    print(f"\nVoiceType service '{SERVICE_NAME}' installed and started.")
    if "OPENAI_API_KEY" in env_vars:
        print(f"The OPENAI_API_KEY has been stored in {ENV_FILE_PATH}.")
        print("If you need to change the API key, you can edit this file and then run:")
    else:
        print(f"The provider has been set to 'local' in {ENV_FILE_PATH}.")
        print(
            "If you need to change the provider, you can edit this file and then run:"
        )
    print(f"  systemctl --user restart {SERVICE_NAME}")
    print("\nYou can check the service status with:")
    print(f"  systemctl --user status {SERVICE_NAME}")
    print("And view logs with:")
    print(f"  journalctl --user -u {SERVICE_NAME} -f")


def uninstall_service():
    """Stops, disables, and removes the systemd user service."""
    print(f"Uninstalling VoiceType systemd user service ('{SERVICE_NAME}')...")

    if sys.platform != "linux":
        print(
            "This uninstallation is for Linux systems with systemd only.",
            file=sys.stderr,
        )
        # Allow to proceed if systemctl is not found, as the file might still exist.
        # run_systemctl_command will handle FileNotFoundError for systemctl itself.

    # Try to stop and disable, ignoring errors if service is not found/loaded
    run_systemctl_command(["stop", SERVICE_NAME], ignore_errors=True)
    run_systemctl_command(["disable", SERVICE_NAME], ignore_errors=True)

    if SERVICE_FILE_PATH.exists():
        try:
            SERVICE_FILE_PATH.unlink()
            print(f"Service file removed: {SERVICE_FILE_PATH}")
        except OSError as e:
            print(
                f"Error removing service file {SERVICE_FILE_PATH}: {e}", file=sys.stderr
            )
            # Continue to daemon-reload even if file removal fails
    else:
        print(f"Service file {SERVICE_FILE_PATH} not found.")

    run_systemctl_command(["daemon-reload"])  # Reload even if files were not present

    # Remove the .env file
    if ENV_FILE_PATH.exists():
        try:
            ENV_FILE_PATH.unlink()
            print(f"Environment file removed: {ENV_FILE_PATH}")
        except OSError as e:
            print(
                f"Error removing environment file {ENV_FILE_PATH}: {e}", file=sys.stderr
            )
    else:
        print(f"Environment file {ENV_FILE_PATH} not found.")

    # Attempt to remove the app config directory if it's empty
    if APP_CONFIG_DIR.exists():
        try:
            # Check if directory is empty
            if not any(APP_CONFIG_DIR.iterdir()):
                APP_CONFIG_DIR.rmdir()
                print(f"Removed empty configuration directory: {APP_CONFIG_DIR}")
            else:
                print(
                    f"Configuration directory {APP_CONFIG_DIR} is not empty, not removing."
                )
        except OSError as e:
            print(
                f"Error removing configuration directory {APP_CONFIG_DIR}: {e}",
                file=sys.stderr,
            )
            print(f"You may need to remove it manually: rmdir {APP_CONFIG_DIR}")

    print(f"VoiceType service '{SERVICE_NAME}' uninstalled.")


def service_status():
    """Checks the status of the systemd user service."""
    if sys.platform != "linux":
        print(
            "This status check is for Linux systems with systemd only.", file=sys.stderr
        )
        sys.exit(1)
    run_systemctl_command(["status", SERVICE_NAME], ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Manage VoiceType systemd user service for Linux."
    )
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    install_parser = subparsers.add_parser(
        "install", help="Install and start the systemd service."
    )
    install_parser.set_defaults(func=install_service)

    uninstall_parser = subparsers.add_parser(
        "uninstall", help="Stop, disable and uninstall the systemd service."
    )
    uninstall_parser.set_defaults(func=uninstall_service)

    status_parser = subparsers.add_parser(
        "status", help="Check the status of the systemd service."
    )
    status_parser.set_defaults(func=service_status)

    args = parser.parse_args()
    args.func()


if __name__ == "__main__":
    main()
