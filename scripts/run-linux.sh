#!/bin/bash
# Helper script to run VoiceType on Linux with privilege separation
# This script starts both the privileged keyboard listener and the main application

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
HOTKEY="${VOICETYPE_HOTKEY:-<pause>}"
SOCKET_PATH="/run/user/$(id -u)/voicetype-hotkey.sock"

# Find the Python executable - we need the FULL PATH for sudo
# sudo doesn't inherit the pixi environment, so we must use absolute path
if [ -n "$PIXI_PROJECT_ROOT" ] && [ -f "$PIXI_PROJECT_ROOT/.pixi/envs/dev/bin/python" ]; then
    # Running inside pixi environment - use the full path
    PYTHON="$PIXI_PROJECT_ROOT/.pixi/envs/dev/bin/python"
elif [ -f "$PROJECT_ROOT/.pixi/envs/dev/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/.pixi/envs/dev/bin/python"
elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
    # Fallback to system python - may not have dependencies
    PYTHON="$(which python3)"
fi

echo "==================================================="
echo "VoiceType Linux Launcher"
echo "==================================================="
echo "Python: $PYTHON"
echo "Hotkey: $HOTKEY"
echo "Socket: $SOCKET_PATH"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down..."
    if [ -n "$LISTENER_PID" ]; then
        sudo kill "$LISTENER_PID" 2>/dev/null || true
        wait "$LISTENER_PID" 2>/dev/null || true
    fi
    # Remove socket file if it exists
    rm -f "$SOCKET_PATH" 2>/dev/null || true
    echo "Cleanup complete."
}

trap cleanup EXIT INT TERM

# Start the privileged listener in the background
echo "Starting privileged keyboard listener (requires sudo)..."
sudo -E "$PYTHON" -m voicetype.hotkey_listener.privileged_listener \
    --socket "$SOCKET_PATH" \
    --hotkey "$HOTKEY" &
LISTENER_PID=$!

# Wait a moment for the listener to start and create the socket
echo "Waiting for listener to initialize..."
for i in {1..10}; do
    if [ -S "$SOCKET_PATH" ]; then
        echo "Listener ready!"
        break
    fi
    sleep 0.5
done

if [ ! -S "$SOCKET_PATH" ]; then
    echo "ERROR: Listener failed to start (socket not created)"
    exit 1
fi

# Start the main application in the foreground
echo ""
echo "Starting main VoiceType application..."
echo "==================================================="
"$PYTHON" -m voicetype

# The cleanup trap will handle shutting down the listener
