import time

from pynput import keyboard

# --- Configuration ---
HOTKEY = keyboard.Key.pause  # Use the Pause/Break key as the hotkey
TEXT_TO_TYPE = "Hello, world!"
# -------------------

is_recording = False
keyboard_controller = keyboard.Controller()


def on_press(key):
    """Callback function when a key is pressed."""
    global is_recording
    try:
        # Check if the pressed key matches the configured hotkey
        if key == HOTKEY and not is_recording:
            is_recording = True
            print("Hotkey pressed - Recording started...")
            # Add any start recording logic here (e.g., play sound)
    except AttributeError:
        # Handle cases where the key might not have a `char` attribute (like special keys)
        pass


def on_release(key):
    """Callback function when a key is released."""
    global is_recording
    if key == HOTKEY and is_recording:
        is_recording = False
        print("Hotkey released - Recording stopped.")
        # Simulate transcription and typing
        print(f"Typing: '{TEXT_TO_TYPE}'")
        # time.sleep(0.1) # Small delay before typing
        try:
            for char in TEXT_TO_TYPE:
                keyboard_controller.press(char)
                keyboard_controller.release(char)
                time.sleep(0.01)
            print("Typing complete.")
        except Exception as e:
            print(f"Error during typing: {e}")
        # Add any stop recording logic here (e.g., play sound)


def main():
    """Main function to start the listener."""
    print(f"Listening for hotkey: {HOTKEY}")
    print("Press the hotkey to start 'recording', release to 'type'.")
    print("Press Ctrl+C in the terminal to exit.")

    # Set up the listener in a non-blocking way
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)  # Keep the main thread alive
    except KeyboardInterrupt:
        print("\nExiting...")
        listener.stop()
        print("Listener stopped.")


if __name__ == "__main__":
    main()
