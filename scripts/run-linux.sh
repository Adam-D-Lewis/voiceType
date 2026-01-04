#!/bin/bash
# Helper script to run VoiceType on Linux with privilege separation
# This script starts both the privileged keyboard listener and the main application

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Default values
HOTKEY="${VOICETYPE_HOTKEY:-<pause>}"
SOCKET_PATH="/run/user/$(id -u)/voicetype-hotkey.sock"

# Track PIDs and shutdown state
LISTENER_PID=""
APP_PID=""
SHUTTING_DOWN=0

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
    # Prevent multiple cleanup calls
    if [ "$SHUTTING_DOWN" -eq 1 ]; then
        return
    fi
    SHUTTING_DOWN=1

    echo ""
    echo "Shutting down..."

    # Kill the main app first
    if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
        kill -TERM "$APP_PID" 2>/dev/null || true
        # Wait up to 2 seconds for graceful shutdown
        for i in {1..20}; do
            if ! kill -0 "$APP_PID" 2>/dev/null; then
                break
            fi
            sleep 0.1
        done
        # Force kill if still running
        if kill -0 "$APP_PID" 2>/dev/null; then
            kill -9 "$APP_PID" 2>/dev/null || true
        fi
    fi

    # Kill the privileged listener
    if [ -n "$LISTENER_PID" ] && kill -0 "$LISTENER_PID" 2>/dev/null; then
        sudo kill -TERM "$LISTENER_PID" 2>/dev/null || true
        # Wait up to 2 seconds for graceful shutdown
        for i in {1..20}; do
            if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
                break
            fi
            sleep 0.1
        done
        # Force kill if still running
        if kill -0 "$LISTENER_PID" 2>/dev/null; then
            sudo kill -9 "$LISTENER_PID" 2>/dev/null || true
        fi
    fi

    # Remove socket file if it exists
    rm -f "$SOCKET_PATH" 2>/dev/null || true
    echo "Cleanup complete."
}

# Set up signal handlers
trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

# Start the privileged listener in the background
echo "Starting privileged keyboard listener (requires sudo)..."
sudo -E "$PYTHON" -u -m voicetype.hotkey_listener.privileged_listener \
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

# Start the main application in the background so we can handle signals
echo ""
echo "Starting main VoiceType application..."
echo "==================================================="
"$PYTHON" -u -m voicetype &
APP_PID=$!

# Wait for the app to exit
wait "$APP_PID" 2>/dev/null || true

# Cleanup will be called by the EXIT trap
