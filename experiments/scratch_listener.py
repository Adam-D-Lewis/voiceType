# /home/balast/CodingProjects/voiceType/scratch_listener.py
import sys

from pynput import keyboard


def on_press(key):
    try:
        print(f"Key {key.char} pressed")
        breakpoint()
        if key.char == "=":
            print(f'You pressed the "=" key. {"="*50}')
    except AttributeError:
        print(f"Special key {key} pressed")


def on_release(key):
    print(f"Key {key} released")
    if key == keyboard.Key.esc:
        # Stop listener
        print("ESC pressed, stopping listener...")
        return False


# Check if running under X11 (basic check)
# Note: A more robust check might be needed for production
import os

if "WAYLAND_DISPLAY" in os.environ:
    print(
        "Warning: This script is designed for X11 and might not work correctly under Wayland.",
        file=sys.stderr,
    )
    # Optionally exit or proceed with caution
    # sys.exit(1)

print("Starting keyboard listener (Press ESC to stop)...")

# Collect events until released
try:
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
except Exception as e:
    print(f"An error occurred: {e}", file=sys.stderr)
    print(
        "Ensure you are running this in a graphical session (X11 recommended) and have necessary permissions.",
        file=sys.stderr,
    )

print("Listener stopped.")
