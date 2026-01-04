#!/usr/bin/env python3
"""Run VoiceType on Linux with privilege separation.

This script starts both the privileged keyboard listener (with sudo) and
the main application. It handles cleanup when either process exits.
"""

import atexit
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def get_socket_path() -> str:
    """Get the socket path for IPC."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return os.path.join(runtime_dir, "voicetype-hotkey.sock")
    return f"/run/user/{os.getuid()}/voicetype-hotkey.sock"


def get_python_executable() -> str:
    """Get the Python executable path.

    When running via pixi, we need the full path for sudo since
    sudo doesn't inherit the pixi environment.
    """
    # First, try the current interpreter
    python = sys.executable

    # If we're in a pixi environment, verify the path exists
    if python and Path(python).exists():
        return python

    # Fallback to system python
    return "python3"


# Global process references for signal handler
_listener_proc = None
_app_proc = None
_socket_path = None
_shutting_down = False


def cleanup():
    """Clean up child processes and socket."""
    global _listener_proc, _app_proc, _socket_path, _shutting_down

    if _shutting_down:
        return
    _shutting_down = True

    print("\nShutting down...", flush=True)

    # Kill the main app first
    if _app_proc and _app_proc.poll() is None:
        try:
            _app_proc.terminate()
            _app_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _app_proc.kill()
            _app_proc.wait()

    # Kill the privileged listener
    if _listener_proc and _listener_proc.poll() is None:
        try:
            subprocess.run(
                ["sudo", "kill", str(_listener_proc.pid)],
                check=False,
                capture_output=True,
            )
            _listener_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            subprocess.run(
                ["sudo", "kill", "-9", str(_listener_proc.pid)],
                check=False,
                capture_output=True,
            )

    # Remove socket file if it exists
    if _socket_path:
        try:
            if os.path.exists(_socket_path):
                os.unlink(_socket_path)
        except OSError:
            pass

    print("Cleanup complete.", flush=True)


def signal_handler(signum, frame):
    """Handle SIGINT/SIGTERM by cleaning up and exiting."""
    cleanup()
    sys.exit(0)


def main():
    """Run VoiceType with privilege separation."""
    global _listener_proc, _app_proc, _socket_path

    import platform

    if platform.system() != "Linux":
        print("This script is only for Linux. On other platforms, run:")
        print("  python -m voicetype")
        sys.exit(1)

    hotkey = os.environ.get("VOICETYPE_HOTKEY", "<pause>")
    _socket_path = get_socket_path()
    python = get_python_executable()

    print("=" * 51)
    print("VoiceType Linux Launcher")
    print("=" * 51)
    print(f"Python: {python}")
    print(f"Hotkey: {hotkey}")
    print(f"Socket: {_socket_path}")
    print(flush=True)

    # Register cleanup handlers
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start the privileged listener
    print("Starting privileged keyboard listener (requires sudo)...")
    listener_cmd = [
        "sudo",
        "-E",
        python,
        "-u",  # Unbuffered output
        "-m",
        "voicetype.hotkey_listener.privileged_listener",
        "--socket",
        _socket_path,
        "--hotkey",
        hotkey,
    ]

    try:
        _listener_proc = subprocess.Popen(
            listener_cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    except Exception as e:
        print(f"ERROR: Failed to start listener: {e}")
        sys.exit(1)

    # Wait for socket to be created
    print("Waiting for listener to initialize...")
    sys.stdout.flush()
    for i in range(10):
        if os.path.exists(_socket_path):
            print("Listener ready!")
            break
        time.sleep(0.5)
    else:
        print("ERROR: Listener failed to start (socket not created)")
        cleanup()
        sys.exit(1)

    # Start the main application
    print()
    print("Starting main VoiceType application...")
    print("=" * 51)
    sys.stdout.flush()

    try:
        # Run the main app as a Popen so we can terminate it on signal
        _app_proc = subprocess.Popen(
            [python, "-u", "-m", "voicetype"],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        returncode = _app_proc.wait()
        cleanup()
        sys.exit(returncode)
    except KeyboardInterrupt:
        cleanup()
        sys.exit(0)


if __name__ == "__main__":
    main()
