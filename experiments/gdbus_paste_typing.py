#!/usr/bin/env python3
"""Experiment: Type text via clipboard + gdbus paste action.

This experiment tests using clipboard copy + gdbus to trigger paste
in GNOME applications on Wayland.

Usage:
    # Focus a text input field, then run:
    python experiments/gdbus_paste_typing.py

The idea is to:
1. Copy text to clipboard via wl-copy
2. Use gdbus to invoke the paste action on the focused application
"""

import os
import shutil
import subprocess
import sys
import time


def set_clipboard(text: str) -> bool:
    """Set clipboard contents using wl-copy.

    Args:
        text: Text to copy to clipboard

    Returns:
        True if successful
    """
    if not shutil.which("wl-copy"):
        print("Error: wl-copy not found. Install wl-clipboard package.")
        return False

    try:
        result = subprocess.run(
            ["wl-copy"],
            input=text,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error: Failed to write clipboard: {e}")
        return False


def get_focused_window_info() -> dict:
    """Get information about the currently focused window using gdbus.

    Returns:
        Dict with window info or empty dict if failed
    """
    info = {}

    # Try to get focused window via GNOME Shell eval
    try:
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.gnome.Shell",
                "--object-path",
                "/org/gnome/Shell",
                "--method",
                "org.gnome.Shell.Eval",
                "global.display.focus_window ? global.display.focus_window.get_wm_class() : 'none'",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print(f"Focused window class: {result.stdout.strip()}")
            info["wm_class"] = result.stdout.strip()
    except Exception as e:
        print(f"Could not get focused window: {e}")

    return info


def list_gtk_actions() -> None:
    """List available GTK application actions via gdbus."""
    print("\n--- Exploring D-Bus for paste actions ---\n")

    # List session bus names
    try:
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.DBus",
                "--object-path",
                "/org/freedesktop/DBus",
                "--method",
                "org.freedesktop.DBus.ListNames",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Filter for GTK/GNOME related names
            names = result.stdout
            gtk_names = [
                n
                for n in names.replace("(", "")
                .replace(")", "")
                .replace("'", "")
                .replace(",", "")
                .split()
                if "gtk" in n.lower() or "gnome" in n.lower() or "org.g" in n.lower()
            ]
            print("GTK/GNOME related bus names:")
            for name in gtk_names[:20]:
                print(f"  {name}")
    except Exception as e:
        print(f"Error listing bus names: {e}")


def try_gtk_application_paste(app_id: str) -> bool:
    """Try to invoke paste action on a GTK application.

    Args:
        app_id: The D-Bus application ID (e.g., org.gnome.TextEditor)

    Returns:
        True if successful
    """
    print(f"\nTrying to invoke paste on {app_id}...")

    # GTK4 apps expose actions via org.gtk.Actions interface
    try:
        # First, list available actions
        result = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                app_id,
                "--object-path",
                f"/{app_id.replace('.', '/')}",
                "--method",
                "org.gtk.Actions.List",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print(f"Available actions: {result.stdout.strip()}")

            # Check if paste action exists
            if "paste" in result.stdout.lower():
                # Try to activate paste action
                paste_result = subprocess.run(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        app_id,
                        "--object-path",
                        f"/{app_id.replace('.', '/')}",
                        "--method",
                        "org.gtk.Actions.Activate",
                        "paste",
                        "[]",
                        "{}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if paste_result.returncode == 0:
                    print("Paste action invoked successfully!")
                    return True
                else:
                    print(f"Paste failed: {paste_result.stderr}")
        else:
            print(f"Could not list actions: {result.stderr}")
    except Exception as e:
        print(f"Error: {e}")

    return False


def try_atspi_paste() -> bool:
    """Try to paste using AT-SPI (Accessibility).

    AT-SPI can send text to accessible applications.

    Returns:
        True if successful
    """
    print("\n--- Trying AT-SPI approach ---")

    try:
        # Check if AT-SPI is available
        result = subprocess.run(
            [
                "gdbus",
                "introspect",
                "--session",
                "--dest",
                "org.a11y.Bus",
                "--object-path",
                "/org/a11y/bus",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print("AT-SPI bus is available")
            print(result.stdout[:500] if len(result.stdout) > 500 else result.stdout)
        else:
            print("AT-SPI bus not available")
    except Exception as e:
        print(f"AT-SPI error: {e}")

    return False


def try_input_method_paste(text: str) -> bool:
    """Try to paste using IBus or other input method.

    Returns:
        True if successful
    """
    print("\n--- Trying IBus input method ---")

    try:
        # Check if IBus is running
        result = subprocess.run(
            [
                "gdbus",
                "introspect",
                "--session",
                "--dest",
                "org.freedesktop.IBus",
                "--object-path",
                "/org/freedesktop/IBus",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print("IBus is available")

            # Try to commit text via IBus
            # This would require finding the current input context
            print("IBus introspection:")
            print(result.stdout[:1000] if len(result.stdout) > 1000 else result.stdout)
        else:
            print(f"IBus not available: {result.stderr}")
    except Exception as e:
        print(f"IBus error: {e}")

    return False


def try_gnome_shell_keyboard() -> bool:
    """Try to simulate keyboard via GNOME Shell.

    Returns:
        True if successful
    """
    print("\n--- Trying GNOME Shell keyboard simulation ---")

    # GNOME Shell can evaluate JavaScript including simulating input
    # However, this is very limited and sandboxed

    try:
        # Check what methods GNOME Shell exposes
        result = subprocess.run(
            [
                "gdbus",
                "introspect",
                "--session",
                "--dest",
                "org.gnome.Shell",
                "--object-path",
                "/org/gnome/Shell",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            print("GNOME Shell interface:")
            # Look for keyboard-related methods
            lines = result.stdout.split("\n")
            for line in lines:
                if "method" in line.lower() or "keyboard" in line.lower():
                    print(f"  {line.strip()}")
    except Exception as e:
        print(f"GNOME Shell error: {e}")

    return False


def main():
    """Main entry point for the experiment."""
    print("=" * 60)
    print("D-Bus Paste Typing Experiment (GNOME Wayland)")
    print("=" * 60)
    print()

    test_text = "Hello from gdbus paste experiment!"

    # Step 1: Copy to clipboard
    print(f"Step 1: Copying text to clipboard: {test_text!r}")
    if not set_clipboard(test_text):
        print("Failed to copy to clipboard")
        return 1
    print("Text copied to clipboard successfully")

    # Step 2: Get info about focused window
    print("\nStep 2: Getting focused window info...")
    get_focused_window_info()

    # Step 3: List available D-Bus services
    list_gtk_actions()

    # Step 4: Try various paste methods
    print("\n" + "=" * 60)
    print("Trying various paste methods...")
    print("=" * 60)

    # Try common GNOME apps
    common_apps = [
        "org.gnome.TextEditor",
        "org.gnome.gedit",
        "org.gnome.Terminal",
        "org.gnome.Nautilus",
    ]

    for app in common_apps:
        if try_gtk_application_paste(app):
            print(f"\nSuccess with {app}!")
            return 0

    # Try AT-SPI
    try_atspi_paste()

    # Try IBus
    try_input_method_paste(test_text)

    # Try GNOME Shell
    try_gnome_shell_keyboard()

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(
        """
The text has been copied to the clipboard. You can manually paste with Ctrl+V.

Unfortunately, programmatically triggering paste on GNOME Wayland is very
restricted for security reasons. The main options are:

1. **ydotool** - Uses uinput (kernel-level), requires ydotoold daemon
   sudo apt install ydotool
   sudo systemctl enable --now ydotool
   ydotool key ctrl+v

2. **dotool** - Similar to ydotool, uses uinput
   https://sr.ht/~geb/dotool/

3. **GNOME extension** - Some extensions can enable virtual keyboard protocol
   for tools like wtype

4. **XWayland apps** - Apps running under XWayland can receive xdotool input

The clipboard approach works for copying, but sending the paste keystroke
requires one of the above solutions on GNOME Wayland.
"""
    )

    return 1


if __name__ == "__main__":
    sys.exit(main())
