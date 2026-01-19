#!/usr/bin/env python3
"""
Type a sentence using libei with PERSISTENT session permissions.

This script demonstrates how to use restore_token and persist_mode to
avoid the user approval dialog on subsequent runs.

First run: Shows dialog, saves token to ~/.cache/voicetype/restore_token
Subsequent runs: Uses saved token, no dialog needed!

Usage:
    python type_sentence_persistent.py           # Normal run (uses token if available)
    python type_sentence_persistent.py --reset   # Clear saved token, force new dialog
"""

import argparse
import io
import os
import select
import time
from pathlib import Path
from typing import Optional

import dbus
import snegg.ei as ei
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

# Setup D-Bus with GLib main loop
DBusGMainLoop(set_as_default=True)

# Portal constants
PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
REMOTE_DESKTOP_IFACE = "org.freedesktop.portal.RemoteDesktop"
REQUEST_IFACE = "org.freedesktop.portal.Request"

# Device type flags
DEVICE_KEYBOARD = 1

# Token storage location
TOKEN_DIR = Path.home() / ".cache" / "voicetype"
TOKEN_FILE = TOKEN_DIR / "restore_token"

# Persist mode options
PERSIST_MODE_NONE = 0  # Don't persist (default)
PERSIST_MODE_APP = 1  # Persist while app is running
PERSIST_MODE_PERMANENT = 2  # Persist until explicitly revoked


def load_restore_token() -> Optional[str]:
    """Load saved restore token from disk."""
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        if token:
            print(f"Loaded restore token from {TOKEN_FILE}")
            return token
    return None


def save_restore_token(token: str):
    """Save restore token to disk."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token)
    print(f"Saved restore token to {TOKEN_FILE}")


def clear_restore_token():
    """Delete saved restore token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"Cleared restore token from {TOKEN_FILE}")


# Linux input event codes (evdev keycodes) - QWERTY layout
QWERTY_KEY_CODES = {
    "a": 30,
    "b": 48,
    "c": 46,
    "d": 32,
    "e": 18,
    "f": 33,
    "g": 34,
    "h": 35,
    "i": 23,
    "j": 36,
    "k": 37,
    "l": 38,
    "m": 50,
    "n": 49,
    "o": 24,
    "p": 25,
    "q": 16,
    "r": 19,
    "s": 31,
    "t": 20,
    "u": 22,
    "v": 47,
    "w": 17,
    "x": 45,
    "y": 21,
    "z": 44,
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
    " ": 57,
    ".": 52,
    ",": 51,
    "'": 40,
    "-": 12,
    "=": 13,
    "\n": 28,
}
KEY_LEFTSHIFT = 42


def get_key_info(char: str) -> tuple[int, bool]:
    """Get (keycode, needs_shift) for a character."""
    if char.isupper():
        lower_char = char.lower()
        if lower_char in QWERTY_KEY_CODES:
            return (QWERTY_KEY_CODES[lower_char], True)
        return (-1, False)

    if char in QWERTY_KEY_CODES:
        return (QWERTY_KEY_CODES[char], False)

    return (-1, False)


class PersistentRemoteDesktopSession:
    """RemoteDesktop session with token persistence support."""

    def __init__(self):
        self.bus = dbus.SessionBus()
        self.portal = self.bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)
        self.remote_desktop = dbus.Interface(self.portal, REMOTE_DESKTOP_IFACE)

        self.session_handle: Optional[str] = None
        self.is_fd: Optional[int] = None
        self.restore_token: Optional[str] = None
        self.loop = GLib.MainLoop()

        self.request_token_counter = 0

    def _get_request_token(self) -> str:
        self.request_token_counter += 1
        return f"u{os.getpid()}_{self.request_token_counter}"

    def _get_session_token(self) -> str:
        return f"u{os.getpid()}_session"

    def _get_request_path(self, token: str) -> str:
        sender = self.bus.get_unique_name().replace(".", "_").replace(":", "")
        return f"/org/freedesktop/portal/desktop/request/{sender}/{token}"

    def create_session(self) -> str:
        """Create a RemoteDesktop session."""
        print("Creating RemoteDesktop session...")

        token = self._get_request_token()
        session_token = self._get_session_token()
        request_path = self._get_request_path(token)

        result = {"session_handle": None, "done": False}

        def on_response(response, results):
            print(f"CreateSession response: {response}")
            if response == 0:
                result["session_handle"] = results.get("session_handle", "")
                print(f"Session created: {result['session_handle']}")
            else:
                print(f"CreateSession failed with response {response}")
            result["done"] = True
            self.loop.quit()

        self.bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=request_path,
        )

        options = {
            "handle_token": token,
            "session_handle_token": session_token,
        }

        try:
            self.remote_desktop.CreateSession(options)
            self.loop.run()
        finally:
            self.bus.remove_signal_receiver(
                on_response,
                signal_name="Response",
                dbus_interface=REQUEST_IFACE,
                path=request_path,
            )

        if not result["session_handle"]:
            raise RuntimeError("Failed to create session")

        self.session_handle = result["session_handle"]
        return self.session_handle

    def select_devices(self, restore_token: Optional[str] = None):
        """Select input devices with persistence support.

        Args:
            restore_token: If provided, attempts to restore a previous session
                          without showing the user dialog.
        """
        print(
            f"Selecting devices (with {'saved token' if restore_token else 'new session'})..."
        )

        token = self._get_request_token()
        request_path = self._get_request_path(token)

        result = {"done": False, "success": False}

        def on_response(response, results):
            print(f"SelectDevices response: {response}")
            result["success"] = response == 0
            result["done"] = True
            self.loop.quit()

        self.bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=request_path,
        )

        options = {
            "handle_token": token,
            "types": dbus.UInt32(DEVICE_KEYBOARD),
            "persist_mode": dbus.UInt32(
                PERSIST_MODE_PERMANENT
            ),  # Key: request permanent persistence
        }

        # If we have a restore token, include it
        if restore_token:
            options["restore_token"] = restore_token

        try:
            self.remote_desktop.SelectDevices(self.session_handle, options)
            self.loop.run()
        finally:
            self.bus.remove_signal_receiver(
                on_response,
                signal_name="Response",
                dbus_interface=REQUEST_IFACE,
                path=request_path,
            )

        if not result["success"]:
            raise RuntimeError("Failed to select devices")

    def start(self, parent_window: str = "") -> Optional[str]:
        """Start the session and return the restore token for future use."""
        print("Starting session...")

        token = self._get_request_token()
        request_path = self._get_request_path(token)

        result = {"done": False, "success": False, "restore_token": None}

        def on_response(response, results):
            print(f"Start response: {response}")
            result["success"] = response == 0
            # Capture the restore_token from the response!
            result["restore_token"] = results.get("restore_token", None)
            if result["restore_token"]:
                print(f"Got restore token: {result['restore_token'][:20]}...")
            result["done"] = True
            self.loop.quit()

        self.bus.add_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            path=request_path,
        )

        options = {"handle_token": token}

        try:
            self.remote_desktop.Start(self.session_handle, parent_window, options)
            self.loop.run()
        finally:
            self.bus.remove_signal_receiver(
                on_response,
                signal_name="Response",
                dbus_interface=REQUEST_IFACE,
                path=request_path,
            )

        if not result["success"]:
            raise RuntimeError("Session start failed or was cancelled")

        self.restore_token = result["restore_token"]
        return self.restore_token

    def connect_to_is(self) -> int:
        """Get the IS file descriptor for libei."""
        print("Connecting to IS...")
        # Must specify signature for empty dict, dbus-python can't infer it
        options = dbus.Dictionary(signature="sv")
        fd = self.remote_desktop.ConnectToIS(self.session_handle, options)
        self.is_fd = fd.take()
        print(f"Got IS fd: {self.is_fd}")
        return self.is_fd


def type_char(device: ei.Device, char: str):
    """Type a single character."""
    keycode, needs_shift = get_key_info(char)
    if keycode == -1:
        print(f"Warning: No keycode for '{char}', skipping")
        return

    device.start_emulating()

    if needs_shift:
        device.keyboard_key(KEY_LEFTSHIFT, True)
        device.frame()
        device.keyboard_key(keycode, True)
        device.frame()
        device.keyboard_key(keycode, False)
        device.frame()
        device.keyboard_key(KEY_LEFTSHIFT, False)
        device.frame()
    else:
        device.keyboard_key(keycode, True)
        device.frame()
        device.keyboard_key(keycode, False)
        device.frame()

    device.stop_emulating()


def wait_for_device(ctx: ei.Sender, poll: select.poll, kept_refs: list) -> ei.Device:
    """Wait for a keyboard device to become available."""
    print("Waiting for keyboard device...")
    while True:
        poll.poll(500)
        ctx.dispatch()
        try:
            events = list(ctx.events)
        except ValueError as e:
            # snegg may raise ValueError for unknown event types
            print(f"Warning: {e}, continuing...")
            continue

        for event in events:
            kept_refs.append(event)

            try:
                event_type = event.event_type
            except ValueError:
                # Unknown event type, skip it
                continue

            if event_type == ei.EventType.SEAT_ADDED:
                seat = event.seat
                if seat:
                    seat.bind((ei.DeviceCapability.KEYBOARD,))
                    kept_refs.append(seat)

            elif event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    print(f"Keyboard device ready: {dev.name}")
                    kept_refs.append(dev)
                    return dev


def type_sentence_simple(device: ei.Device, text: str):
    """Type text character by character with simple timing."""
    print(f"Typing: {text}")
    for i, char in enumerate(text):
        type_char(device, char)
        print(f"  Typed '{char}' ({i + 1}/{len(text)})")
        time.sleep(0.05)  # 50ms between chars
    print("Done typing!")


def main():
    parser = argparse.ArgumentParser(
        description="Type text with persistent permissions"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Clear saved token and force new dialog"
    )
    parser.add_argument(
        "--text", default="Hello from persistent libei!", help="Text to type"
    )
    args = parser.parse_args()

    if args.reset:
        clear_restore_token()

    # Try to load existing token
    saved_token = load_restore_token()

    session = PersistentRemoteDesktopSession()
    is_file = None

    try:
        session.create_session()

        # Pass the saved token to select_devices
        # If token is valid, no dialog will appear!
        session.select_devices(restore_token=saved_token)

        # Start returns a new token for next time
        new_token = session.start()

        # Save the new token for future runs
        if new_token:
            save_restore_token(new_token)

        is_fd = session.connect_to_is()

        # Setup libei
        is_file = io.FileIO(is_fd, mode="r+b", closefd=False)
        ctx = ei.Sender.create_for_fd(fd=is_file, name="libei-persistent-test")

        print("\nYou have 3 seconds to focus on a text editor...")
        time.sleep(3)

        kept_refs: list = []
        poll = select.poll()
        poll.register(ctx.fd)

        device = wait_for_device(ctx, poll, kept_refs)
        type_sentence_simple(device, args.text)

    except Exception as e:
        print(f"Error: {e}")
        # If the token failed, clear it so next run shows dialog
        if saved_token and "cancelled" in str(e).lower():
            print("Token may be expired, clearing...")
            clear_restore_token()
        raise
    finally:
        if is_file is not None:
            try:
                os.close(is_file.fileno())
            except OSError:
                pass


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
        exit_code = 130
    except Exception as e:
        print(f"Error: {e}")
        exit_code = 1

    os._exit(exit_code)
