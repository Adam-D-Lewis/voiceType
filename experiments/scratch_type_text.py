import time

from voicetype.utils import type_text


def main():
    """
    Tests the type_text function.
    Waits for 3 seconds, then types a predefined string into the active window.
    """
    print("Switch to the target window now. Typing will start in 3 seconds...")
    time.sleep(3)

    test_string = "Hello, this is a test of the text typing functionality!\nIt should handle multiple lines.\nAnd special characters like !@#$%^&*()."
    print(f"Typing: '{test_string}'")

    try:
        type_text(test_string)
        print("Typing complete.")
    except Exception as e:
        print(f"An error occurred during typing: {e}")


if __name__ == "__main__":
    main()
