#!/usr/bin/env python3
"""Test script for portal hotkey listener rebind functionality.

This tests whether:
1. The portal remembers hotkey bindings across restarts (session persistence)
2. The rebind_shortcut() method works to change the hotkey

Run with: pixi run python experiments/test_portal_rebind.py
"""

import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, "/home/balast/CodingProjects/voiceType")

from voicetype.hotkey_listener.portal_hotkey_listener import (
    PortalHotkeyListener,
    is_portal_available,
)


def on_press():
    print("\n>>> HOTKEY PRESSED! <<<")


def on_release():
    print(">>> HOTKEY RELEASED <<<\n")


def main():
    print("=" * 60)
    print("Portal Hotkey Listener - Rebind Test")
    print("=" * 60)

    # Check if portal is available
    if not is_portal_available():
        print("ERROR: GlobalShortcuts portal is not available.")
        print("Make sure you're on GNOME 48+, KDE Plasma, or Hyprland.")
        sys.exit(1)

    print("Portal is available!")
    print()

    # Create listener
    listener = PortalHotkeyListener(
        on_hotkey_press=on_press,
        on_hotkey_release=on_release,
        log_key_repeat_debug=False,
    )

    # Set initial preferred hotkey
    listener.set_hotkey("<pause>")

    print("Starting listener... (dialog should appear)")
    print()

    try:
        listener.start_listening()
        print("Listener started successfully!")
        print()
        print("Commands:")
        print("  r - Rebind shortcut (show dialog again)")
        print("  q - Quit")
        print()
        print("Try pressing your hotkey to see if it works.")
        print()

        while True:
            try:
                cmd = input("> ").strip().lower()
                if cmd == "q":
                    print("Quitting...")
                    break
                elif cmd == "r":
                    print()
                    print("Rebinding shortcut... (dialog should appear)")
                    success = listener.rebind_shortcut()
                    if success:
                        print("Rebind successful!")
                    else:
                        print("Rebind failed or was cancelled.")
                    print()
                else:
                    print("Unknown command. Use 'r' to rebind, 'q' to quit.")
            except EOFError:
                break

    except RuntimeError as e:
        print(f"Failed to start listener: {e}")
        sys.exit(1)
    finally:
        listener.stop_listening()
        print("Listener stopped.")


if __name__ == "__main__":
    main()
