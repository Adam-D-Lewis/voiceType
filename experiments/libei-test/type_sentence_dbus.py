#!/usr/bin/env python3
"""
Type a sentence using libei via direct D-Bus interaction with the RemoteDesktop portal.

This bypasses liboeffis and interacts with the XDG RemoteDesktop portal directly
using dbus-python. The workflow:
1. CreateSession() - Create a RemoteDesktop session
2. SelectDevices() - Request keyboard access
3. Start() - User approves via dialog
4. ConnectToIS() - Get file descriptor for libei
5. Use snegg/libei to send keyboard events
"""

import io
import os
import select
import time
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
DEVICE_POINTER = 2

# Linux input event codes (evdev keycodes)
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

# Dvorak Programmer special symbols
DVORAK_PROGRAMMER_SYMBOLS = {
    "!": (12, False),  # '-' key without shift
}

# Dvorak to QWERTY physical key mapping
DVORAK_TO_QWERTY = {
    "a": "a",
    "b": "n",
    "c": "i",
    "d": "h",
    "e": "d",
    "f": "y",
    "g": "u",
    "h": "j",
    "i": "g",
    "j": "c",
    "k": "v",
    "l": "p",
    "m": "m",
    "n": "l",
    "o": "s",
    "p": "r",
    "q": "x",
    "r": "o",
    "s": ";",
    "t": "k",
    "u": "f",
    "v": ".",
    "w": ",",
    "x": "b",
    "y": "t",
    "z": "/",
    ";": "z",
    ",": "w",
    ".": "e",
    "/": "[",
    "'": "q",
}

USE_DVORAK_PROGRAMMER = True
KEY_LEFTSHIFT = 42


def get_key_info(char: str) -> tuple[int, bool]:
    """Get (keycode, needs_shift) for a character."""
    if USE_DVORAK_PROGRAMMER and char in DVORAK_PROGRAMMER_SYMBOLS:
        return DVORAK_PROGRAMMER_SYMBOLS[char]

    if char.isupper():
        lower_char = char.lower()
        if USE_DVORAK_PROGRAMMER and lower_char in DVORAK_TO_QWERTY:
            qwerty_char = DVORAK_TO_QWERTY[lower_char]
            if qwerty_char in QWERTY_KEY_CODES:
                return (QWERTY_KEY_CODES[qwerty_char], True)
        if lower_char in QWERTY_KEY_CODES:
            return (QWERTY_KEY_CODES[lower_char], True)
        return (-1, False)

    lower_char = char.lower()
    if USE_DVORAK_PROGRAMMER and lower_char in DVORAK_TO_QWERTY:
        qwerty_char = DVORAK_TO_QWERTY[lower_char]
        if qwerty_char in QWERTY_KEY_CODES:
            return (QWERTY_KEY_CODES[qwerty_char], False)

    if lower_char in QWERTY_KEY_CODES:
        return (QWERTY_KEY_CODES[lower_char], False)

    return (-1, False)


class RemoteDesktopSession:
    """Manages the D-Bus RemoteDesktop portal session."""

    def __init__(self):
        self.bus = dbus.SessionBus()
        self.portal = self.bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)
        self.remote_desktop = dbus.Interface(self.portal, REMOTE_DESKTOP_IFACE)

        self.session_handle: Optional[str] = None
        self.is_fd: Optional[int] = None
        self.loop = GLib.MainLoop()

        # Generate unique token for request handle
        self.request_token_counter = 0

    def _get_request_token(self) -> str:
        """Generate a unique request token."""
        self.request_token_counter += 1
        return f"u{os.getpid()}_{self.request_token_counter}"

    def _get_session_token(self) -> str:
        """Generate a unique session token."""
        return f"u{os.getpid()}_session"

    def _get_request_path(self, token: str) -> str:
        """Build the expected request object path."""
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

        # Subscribe to the Response signal BEFORE making the call
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

    def select_devices(self, device_types: int = DEVICE_KEYBOARD):
        """Select input device types for the session."""
        print(f"Selecting devices (types={device_types})...")

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
            "types": dbus.UInt32(device_types),
        }

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

    def start(self, parent_window: str = ""):
        """Start the session (triggers user approval dialog)."""
        print("Starting session (approval dialog will appear)...")

        token = self._get_request_token()
        request_path = self._get_request_path(token)

        result = {"done": False, "success": False, "devices": 0}

        def on_response(response, results):
            print(f"Start response: {response}, results: {dict(results)}")
            result["success"] = response == 0
            result["devices"] = results.get("devices", 0)
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
        }

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
            raise RuntimeError("Session start failed or was cancelled by user")

        print(f"Session started, devices granted: {result['devices']}")

    def connect_to_is(self) -> int:
        """Get the IS file descriptor for libei."""
        print("Connecting to IS...")

        options = {}
        fd = self.remote_desktop.ConnectToIS(self.session_handle, options)

        # D-Bus returns a dbus.types.UnixFd object, extract the actual fd
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
        for event in ctx.events:
            kept_refs.append(event)
            print(f"  Event: {event.event_type.name}")

            if event.event_type == ei.EventType.SEAT_ADDED:
                seat = event.seat
                if seat:
                    print(f"  Seat added: {seat.name}")
                    seat.bind((ei.DeviceCapability.KEYBOARD,))
                    kept_refs.append(seat)

            elif event.event_type == ei.EventType.DEVICE_ADDED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    print(f"  Keyboard device found: {dev.name}")
                    kept_refs.append(dev)

            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    print(f"  Device resumed: {dev.name}")
                    kept_refs.append(dev)
                    return dev


def process_events(ctx: ei.Sender, kept_refs: list) -> tuple[ei.Device | None, bool]:
    """Process pending events and return (new_device, was_removed)."""
    ctx.dispatch()
    events = list(ctx.events)
    kept_refs.extend(events)

    new_device = None
    was_removed = False

    for event in events:
        print(f"    Event: {event.event_type.name}")
        if event.event_type == ei.EventType.DEVICE_REMOVED:
            was_removed = True
        elif event.event_type == ei.EventType.DEVICE_ADDED:
            dev = event.device
            if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                kept_refs.append(dev)
                new_device = dev
        elif event.event_type == ei.EventType.DEVICE_RESUMED:
            dev = event.device
            if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                kept_refs.append(dev)
                new_device = dev

    return new_device, was_removed


def drain_events(
    ctx: ei.Sender, poll: select.poll, kept_refs: list, timeout_ms: int = 0
) -> tuple[ei.Device | None, bool]:
    """Drain all pending events from the context."""
    new_device = None
    was_removed = False

    # Keep polling until no more events
    while True:
        ready = poll.poll(timeout_ms)
        if not ready:
            break

        ctx.dispatch()
        events = list(ctx.events)
        if not events:
            break

        kept_refs.extend(events)
        for event in events:
            print(f"    Event: {event.event_type.name}")
            if event.event_type == ei.EventType.DEVICE_REMOVED:
                was_removed = True
            elif event.event_type == ei.EventType.DEVICE_ADDED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    kept_refs.append(dev)
                    new_device = dev
            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    kept_refs.append(dev)
                    new_device = dev

        timeout_ms = 0  # After first poll, don't wait

    return new_device, was_removed


def type_sentence(ctx: ei.Sender, device: ei.Device, text: str):
    """Type a full sentence with batch processing and synchronization waits.

    Strategy: Type characters in small batches, waiting after each batch for
    the compositor to settle. If device removal is detected, go back and
    retry from the last confirmed batch.
    """
    print(f"Typing: {text}")

    poll = select.poll()
    poll.register(ctx.fd, select.POLLOUT | select.POLLIN)
    current_device = device
    kept_refs: list = [device]

    SETTLE_TIME_MS = 50  # Wait this long after each char for compositor to settle

    idx = 0
    last_confirmed_idx = 0  # Last index we're confident was received
    retry_count = 0
    max_retries = 10

    while idx < len(text):
        char = text[idx]

        # Drain any pending events first
        new_dev, was_removed = drain_events(ctx, poll, kept_refs, timeout_ms=5)
        if was_removed:
            print(f"  Device removed before typing '{char}'")
            current_device = None
        if new_dev:
            current_device = new_dev

        # Wait for device if needed
        if current_device is None:
            print(f"  Waiting for device before '{char}'...")
            current_device = wait_for_device(ctx, poll, kept_refs)
            retry_count = 0
            # On device re-add, go back to last confirmed position
            if idx > last_confirmed_idx:
                print(f"  Rolling back from {idx} to {last_confirmed_idx}")
                idx = last_confirmed_idx
                continue

        # Type the character
        type_char(current_device, char)
        print(f"  Typed '{char}' ({idx + 1}/{len(text)})")

        # CRITICAL: Wait for compositor to process the character
        # This gives mutter time to either accept it or decide to remove the device
        new_dev, was_removed = drain_events(
            ctx, poll, kept_refs, timeout_ms=SETTLE_TIME_MS
        )
        if new_dev:
            current_device = new_dev

        if was_removed:
            retry_count += 1
            if retry_count <= max_retries:
                print(
                    f"    Device removed - rolling back to pos {last_confirmed_idx}, retry {retry_count}/{max_retries}"
                )
                current_device = None
                idx = last_confirmed_idx
                continue
            else:
                print(f"    Max retries exceeded at pos {idx}, moving on")
                retry_count = 0
                last_confirmed_idx = idx + 1
        else:
            # No removal detected after waiting - this character is probably good
            last_confirmed_idx = idx + 1
            retry_count = 0

        idx += 1

    print("Done typing!")


def main():
    sentence = "Hello from libei!"

    # Create and setup the RemoteDesktop session via D-Bus
    session = RemoteDesktopSession()
    is_file = None

    try:
        session.create_session()
        session.select_devices(DEVICE_KEYBOARD)
        session.start()  # This triggers the user approval dialog
        is_fd = session.connect_to_is()

        # Now use libei/snegg with the file descriptor
        # snegg expects a file-like object, so wrap the fd
        # Use closefd=False since snegg will manage the fd lifecycle
        is_file = io.FileIO(is_fd, mode="r+b", closefd=False)
        ctx = ei.Sender.create_for_fd(fd=is_file, name="libei-dbus-test")

        print("\nYou have 5 seconds to focus on a text editor...")
        time.sleep(5)

        # Keep references to prevent GC
        kept_refs: list = []

        poll = select.poll()
        poll.register(ctx.fd)

        # Wait for device
        device = wait_for_device(ctx, poll, kept_refs)

        # Type the sentence
        type_sentence(ctx, device, sentence)

    except Exception as e:
        print(f"Error: {e}")
        raise
    finally:
        # Clean up: close the fd explicitly if we still own it
        if is_file is not None:
            try:
                os.close(is_file.fileno())
            except OSError:
                pass  # Already closed


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

    # Use os._exit() to skip Python's cleanup/finalizers
    # This avoids the "Bad file descriptor" errors from D-Bus/GLib
    # file objects trying to close already-closed fds
    os._exit(exit_code)
