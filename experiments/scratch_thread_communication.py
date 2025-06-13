import queue
import threading
import time

from pynput import keyboard

# Use a thread-safe queue for communication
key_queue = queue.Queue()
# Use an Event to signal the listener thread to stop
stop_event = threading.Event()


def on_press(key):
    """Callback function executed when a key is pressed."""
    key_info = None
    try:
        key_info = f"Key '{key.char}'"
        # print(f"Listener Thread: Putting '{key.char}' onto queue.") # Optional debug print
    except AttributeError:
        key_info = f"Special key '{key}'"
        # print(f"Listener Thread: Putting special key '{key}' onto queue.") # Optional debug print

    if key_info:
        key_queue.put(key_info)  # Send the key info back to the main thread

    # Check if the main thread has signaled to stop
    if stop_event.is_set():
        print("Listener Thread: Stop event detected, stopping listener...")
        key_queue.put(None)  # Send a sentinel value to unblock the main thread's get()
        return False  # Stop the listener


def keyboard_listener_thread():
    """Function running in the separate thread."""
    print("Listener Thread: Starting keyboard listener...")
    with keyboard.Listener(on_press=on_press) as listener:
        print(
            "Listener Thread: Listener started, waiting for stop signal or key events."
        )
        listener.join()  # Blocks here until the listener stops
    print("Listener Thread: Listener stopped and thread exiting.")


# --- Main Thread ---
print("Main Thread: Starting.")

listener_thread = threading.Thread(target=keyboard_listener_thread, daemon=True)

print("Main Thread: Starting the listener thread.")
listener_thread.start()

print("Main Thread: Listener is running. Press Ctrl+C in this terminal to stop.")
print("Main Thread: Waiting to process keys from the queue...")

try:
    while True:
        try:
            # Wait for a key from the listener thread (blocks if queue is empty)
            # Add a timeout to allow checking for KeyboardInterrupt periodically
            key_data = key_queue.get(timeout=0.5)  # Timeout after 0.5 seconds

            if key_data is None:  # Check for the sentinel value
                print("Main Thread: Received stop signal from queue. Exiting loop.")
                break  # Exit the loop cleanly

            # Process the key data received from the listener
            print(f"Main Thread: Received data - {key_data}")
            # Add any other processing logic here...

        except queue.Empty:
            # Timeout occurred, queue was empty. Loop again to check queue or KeyboardInterrupt.
            continue
        except Exception as e:
            print(f"Main Thread: Error processing queue item: {e}")
            break

except KeyboardInterrupt:
    print("\nMain Thread: Ctrl+C detected.")

finally:
    print("Main Thread: Signaling listener thread to stop...")
    stop_event.set()

    # Ensure the final 'None' sentinel is put on the queue if Ctrl+C happened
    # before the listener thread put it there itself. This prevents deadlock on get().
    # Use non-blocking put or check if listener is alive. A simple put is often okay here.
    try:
        key_queue.put_nowait(None)
    except queue.Full:
        pass  # Queue might be full if already stopped, that's okay.

    print("Main Thread: Waiting for listener thread to finish...")
    listener_thread.join(timeout=2)

    print(f"Main Thread: Listener thread alive: {listener_thread.is_alive()}")
    print("Main Thread: Exiting.")
