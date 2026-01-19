#!/usr/bin/env python3
"""Experiment: Type text via clipboard paste instead of character-by-character.

This experiment tests using clipboard copy + Ctrl+V paste as an alternative
to pynput's character-by-character typing. This approach may work better
on Wayland native applications where virtual keyboard input doesn't work.

Usage:
    # Focus a text input field, then run:
    python experiments/clipboard_paste_typing.py

Requirements:
    - Wayland: wl-clipboard package (wl-copy, wl-paste commands)
    - X11: xclip or xsel package

The script will:
1. Detect display server (Wayland or X11)
2. Save current clipboard contents
3. Copy test text to clipboard
4. Simulate Ctrl+V to paste
5. Restore original clipboard contents
"""

import os
import shutil
import subprocess
import sys
import time

# Add parent directory to path so we can import from voicetype
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def detect_display_server() -> str:
    """Detect whether we're running on Wayland or X11.

    Returns:
        'wayland' or 'x11'
    """
    # Check XDG_SESSION_TYPE first (most reliable)
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session_type == "wayland":
        return "wayland"
    if session_type == "x11":
        return "x11"

    # Check WAYLAND_DISPLAY
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"

    # Check DISPLAY (X11)
    if os.environ.get("DISPLAY"):
        return "x11"

    # Default to x11 as fallback
    return "x11"


def get_clipboard(display_server: str) -> str | None:
    """Get current clipboard contents.

    Args:
        display_server: 'wayland' or 'x11'

    Returns:
        Clipboard contents or None if failed
    """
    try:
        if display_server == "wayland":
            if shutil.which("wl-paste"):
                result = subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout
                # Empty clipboard returns exit code 1
                return ""
        else:
            if shutil.which("xclip"):
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout
            elif shutil.which("xsel"):
                result = subprocess.run(
                    ["xsel", "--clipboard", "--output"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout
    except subprocess.TimeoutExpired:
        print("Warning: Clipboard read timed out")
    except Exception as e:
        print(f"Warning: Failed to read clipboard: {e}")

    return None


def set_clipboard(text: str, display_server: str) -> bool:
    """Set clipboard contents.

    Args:
        text: Text to copy to clipboard
        display_server: 'wayland' or 'x11'

    Returns:
        True if successful
    """
    try:
        if display_server == "wayland":
            if shutil.which("wl-copy"):
                result = subprocess.run(
                    ["wl-copy"],
                    input=text,
                    text=True,
                    timeout=5,
                )
                return result.returncode == 0
            else:
                print("Error: wl-copy not found. Install wl-clipboard package.")
                return False
        else:
            if shutil.which("xclip"):
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text,
                    text=True,
                    timeout=5,
                )
                return result.returncode == 0
            elif shutil.which("xsel"):
                result = subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text,
                    text=True,
                    timeout=5,
                )
                return result.returncode == 0
            else:
                print("Error: xclip or xsel not found. Install xclip package.")
                return False
    except subprocess.TimeoutExpired:
        print("Error: Clipboard write timed out")
    except Exception as e:
        print(f"Error: Failed to write clipboard: {e}")

    return False


def send_paste_keystroke(display_server: str) -> bool:
    """Send Ctrl+V keystroke to paste from clipboard.

    Args:
        display_server: 'wayland' or 'x11'

    Returns:
        True if successful
    """
    if display_server == "wayland":
        # Use wtype for Wayland - it can send key combinations
        if shutil.which("wtype"):
            print("Using wtype for Wayland paste...")
            try:
                # wtype -M ctrl -P v -m ctrl sends Ctrl+V
                result = subprocess.run(
                    ["wtype", "-M", "ctrl", "-P", "v", "-m", "ctrl"],
                    timeout=5,
                )
                return result.returncode == 0
            except subprocess.TimeoutExpired:
                print("Error: wtype timed out")
                return False
            except Exception as e:
                print(f"Error running wtype: {e}")
                return False
        else:
            print("Error: wtype not found. Install wtype package for Wayland support.")
            print("  On Debian/Ubuntu: sudo apt install wtype")
            return False
    else:
        # Use pynput for X11
        print("Using pynput for X11 paste...")
        try:
            from voicetype._vendor import pynput

            keyboard = pynput.keyboard.Controller()
            keyboard.press(pynput.keyboard.Key.ctrl)
            keyboard.press("v")
            keyboard.release("v")
            keyboard.release(pynput.keyboard.Key.ctrl)
            return True
        except Exception as e:
            print(f"Error with pynput: {e}")
            return False


def type_via_clipboard(
    text: str, restore_clipboard: bool = True, paste_delay: float = 0.05
) -> bool:
    """Type text by copying to clipboard and pasting with Ctrl+V.

    Args:
        text: Text to type
        restore_clipboard: Whether to restore previous clipboard contents
        paste_delay: Delay after copying before pasting (seconds)

    Returns:
        True if successful
    """
    # Detect display server
    display_server = detect_display_server()
    print(f"Detected display server: {display_server}")

    # Save current clipboard contents if we want to restore
    old_clipboard = None
    if restore_clipboard:
        old_clipboard = get_clipboard(display_server)
        if old_clipboard is not None:
            print(f"Saved clipboard contents (length: {len(old_clipboard)})")

    try:
        # Copy text to clipboard
        print(f"Copying text to clipboard: {text!r}")
        if not set_clipboard(text, display_server):
            print("Failed to copy text to clipboard")
            return False

        # Small delay to ensure clipboard is ready
        time.sleep(paste_delay)

        # Paste using Ctrl+V
        print("Sending Ctrl+V to paste...")
        if not send_paste_keystroke(display_server):
            print("Failed to send paste keystroke")
            return False

        print("Paste command sent!")

        # Restore clipboard if requested
        if restore_clipboard and old_clipboard is not None:
            time.sleep(0.1)  # Wait for paste to complete
            set_clipboard(old_clipboard, display_server)
            print("Restored original clipboard contents")

        return True

    except Exception as e:
        print(f"Error during clipboard paste: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point for the experiment."""
    print("=" * 60)
    print("Clipboard Paste Typing Experiment")
    print("=" * 60)
    print()
    print("This experiment will type text using clipboard paste (Ctrl+V)")
    print("instead of character-by-character typing.")
    print()
    print("Instructions:")
    print("  1. Focus a text input field (editor, browser, terminal, etc.)")
    print("  2. Wait for the countdown...")
    print("  3. The text should appear in the focused field")
    print()

    # Countdown to give user time to focus
    for i in range(3, 0, -1):
        print(f"  Starting in {i}...")
        time.sleep(1)

    print()
    test_text = "Hello from clipboard paste! 🎉 This works on Wayland native apps."
    print(f"Typing: {test_text!r}")
    print()

    success = type_via_clipboard(test_text, restore_clipboard=True)

    print()
    if success:
        print("✓ Experiment completed successfully!")
    else:
        print("✗ Experiment failed")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
