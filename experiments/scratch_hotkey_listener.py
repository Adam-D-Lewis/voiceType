from pynput import keyboard

# Global variable to store the chosen hotkey (in its canonical form)
chosen_hotkey_global = None
# Global variable to store the main listener instance (to use its .canonical() method)
main_listener_instance_global = None


def set_hotkey_from_text(hotkey_string):
    """
    Parses a hotkey string representing a SINGLE key (e.g., "a", "<space>", "<f1>", "<pause>")
    and sets it as the global hotkey.
    It ensures the parsed string results in exactly one canonical key object.
    """
    global chosen_hotkey_global
    print(f"Attempting to set single key hotkey from string: '{hotkey_string}'")
    try:
        # keyboard.HotKey.parse() returns a frozenset of canonical key objects.
        # For a single key string like "a" or "<space>", this frozenset should contain one element.
        # For combinations like "<ctrl>+a", it will contain multiple elements.
        parsed_keys = keyboard.HotKey.parse(hotkey_string)

        if not parsed_keys:
            print(f"Error: Could not parse '{hotkey_string}' into any keys.")
            chosen_hotkey_global = None
            return False

        # We expect exactly one key for a single-key hotkey.
        if len(parsed_keys) == 1:
            single_key = list(parsed_keys)[0]  # Extract the single key
            # This key is already in its canonical form thanks to HotKey.parse().
            chosen_hotkey_global = single_key
            print(
                f"Hotkey has been successfully set to: {chosen_hotkey_global} (Type: {type(chosen_hotkey_global)})"
            )
            return True
        else:
            # This case means the string was a combination (e.g., "<ctrl>+s"),
            # empty, or otherwise not representing a single key.
            print(
                f"Error: Hotkey string '{hotkey_string}' (parsed as {parsed_keys}) does not represent a single key."
            )
            print(
                "Please provide a string for one key, e.g., 'a', '<f1>', or '<pause>'."
            )
            chosen_hotkey_global = None
            return False

    except (
        ValueError
    ) as ve:  # HotKey.parse can raise ValueError for badly formed strings
        print(f"Error parsing hotkey string '{hotkey_string}': {ve}")
        chosen_hotkey_global = None
        return False
    except Exception as e:  # Catch any other unexpected errors
        print(
            f"An unexpected error occurred while parsing or setting hotkey from string '{hotkey_string}': {e}"
        )
        chosen_hotkey_global = None
        return False


def main_on_press_callback(key):
    """
    This is the on_press callback for the main listener.
    It compares the pressed key with the globally set hotkey.
    """
    global chosen_hotkey_global, main_listener_instance_global

    if chosen_hotkey_global is None:
        # Hotkey not set, optionally handle other keys or do nothing
        if key == keyboard.Key.esc:  # Example: allow Esc to exit even if no hotkey
            print("ESC pressed. Exiting...")
            return False  # Stop the listener
        return

    if main_listener_instance_global is None:
        print("Error: Main listener instance is not available for canonicalization.")
        # Fallback to direct comparison (less reliable across different key types/instances)
        current_pressed_key_canonical = key
    else:
        # Canonicalize the currently pressed key using the main listener's method
        current_pressed_key_canonical = main_listener_instance_global.canonical(key)

    # Compare the canonical form of the pressed key with the canonical form of the stored hotkey
    if current_pressed_key_canonical == chosen_hotkey_global:
        print(f"--- Hotkey '{chosen_hotkey_global}' PRESSED! ---")
        breakpoint()
        # TODO: Add your desired action here
        # For example, you could call a function, or stop the listener:
        # print("Hotkey action executed. Stopping listener as an example.")
        # return False # Uncomment to stop listener when hotkey is pressed
    else:
        # Optional: print other key presses for debugging or general feedback
        # print(f"Pressed: {current_pressed_key_canonical} (Not the hotkey: {chosen_hotkey_global})")
        pass

    # Allow Esc to always exit the main listener, regardless of hotkey match
    if key == keyboard.Key.esc:
        print("ESC pressed. Exiting main listener...")
        return False  # Stop the listener


def start_main_listener():
    """
    Starts the main keyboard listener that listens for the selected hotkey.
    """
    global main_listener_instance_global  # To store the listener instance

    if chosen_hotkey_global is None:
        print("Cannot start main listener: No hotkey has been set.")
        print("Please set a hotkey using a text string first.")
        return

    print(f"Starting main listener. Listening for hotkey: {chosen_hotkey_global}.")
    print("Press ESC to stop the listener at any time.")

    with keyboard.Listener(on_press=main_on_press_callback) as listener:
        main_listener_instance_global = (
            listener  # Store the instance for use in the callback
        )
        try:
            listener.join()  # Block execution until the listener stops
        except Exception as e:
            print(f"An error occurred in the main listener: {e}")
        finally:
            main_listener_instance_global = None

    print("Main listener has stopped.")


if __name__ == "__main__":
    # 1. Get the hotkey string from the user
    hotkey_text_input = input(
        "Enter the hotkey text (e.g., 's' for S key, '<f1>' for F5, '<space>', '<pause>'): "
    )

    # 2. Set the hotkey from the text string
    if set_hotkey_from_text(hotkey_text_input):
        # 3. If a hotkey was set successfully, start the main listener
        start_main_listener()
    else:
        print("Failed to set hotkey. Exiting program.")
