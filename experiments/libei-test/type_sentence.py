#!/usr/bin/env python3
"""
Sample program that types a sentence using libei via the RemoteDesktop portal.

This demonstrates the full workflow:
1. Connect to the XDG RemoteDesktop portal via liboeffis
2. Get an IS file descriptor from the portal
3. Use libei to send keyboard events

The RemoteDesktop portal will show a dialog asking the user to approve
input device access.
"""

import select
import time
from typing import Optional

import snegg.ei as ei
import snegg.oeffis as oeffis

# Linux input event codes for common keys
# From: linux/input-event-codes.h
# These are evdev keycodes (physical key positions on QWERTY keyboard)
# The compositor's XKB keymap translates these to characters

# QWERTY layout keycodes (physical positions)
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
    " ": 57,  # space
    ".": 52,
    ",": 51,
    "'": 40,  # apostrophe
    "-": 12,
    "=": 13,
    "\n": 28,  # enter
}

# Custom Dvorak Programmer layout - user's specific mapping
# '!' is on the '-' key (keycode 12) without shift
# Map symbol -> (keycode, needs_shift)
DVORAK_PROGRAMMER_SYMBOLS = {
    "!": (12, False),  # '-' key (near 0) without shift = !
    # Add more symbols as needed - leaving others commented until confirmed
    # '@': (3, False),
    # '#': (4, False),
    # etc.
}

# Dvorak layout: maps Dvorak character -> QWERTY physical key that produces it
# (since libei sends physical scancodes that get translated by XKB keymap)
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

# Choose which layout to use
USE_DVORAK_PROGRAMMER = True


def get_key_info(char: str) -> tuple[int, bool]:
    """Get (keycode, needs_shift) for a character based on keyboard layout.

    Returns (-1, False) if character not found.
    """
    # Check Dvorak Programmer symbols first (numbers/symbols on number row)
    if USE_DVORAK_PROGRAMMER and char in DVORAK_PROGRAMMER_SYMBOLS:
        return DVORAK_PROGRAMMER_SYMBOLS[char]

    # Check if it's an uppercase letter
    if char.isupper():
        lower_char = char.lower()
        if USE_DVORAK_PROGRAMMER and lower_char in DVORAK_TO_QWERTY:
            qwerty_char = DVORAK_TO_QWERTY[lower_char]
            if qwerty_char in QWERTY_KEY_CODES:
                return (QWERTY_KEY_CODES[qwerty_char], True)
        if lower_char in QWERTY_KEY_CODES:
            return (QWERTY_KEY_CODES[lower_char], True)
        return (-1, False)

    # Lowercase letter or other character
    lower_char = char.lower()
    if USE_DVORAK_PROGRAMMER and lower_char in DVORAK_TO_QWERTY:
        qwerty_char = DVORAK_TO_QWERTY[lower_char]
        if qwerty_char in QWERTY_KEY_CODES:
            return (QWERTY_KEY_CODES[qwerty_char], False)

    # Fall back to QWERTY keycodes
    if lower_char in QWERTY_KEY_CODES:
        return (QWERTY_KEY_CODES[lower_char], False)

    return (-1, False)


KEY_LEFTSHIFT = 42


def wait_for_portal() -> oeffis.Oeffis:
    """
    Connect to the RemoteDesktop portal and wait for IS connection.
    This will trigger a system dialog asking the user to approve input access.
    """
    print("Connecting to RemoteDesktop portal...")
    print("A dialog will appear asking you to approve input device access.")

    # Request keyboard access via the portal
    portal = oeffis.Oeffis.create(devices=oeffis.DeviceType.KEYBOARD)

    poll = select.poll()
    poll.register(portal.fd)

    while poll.poll():
        try:
            if portal.dispatch():
                print("Connected to IS!")
                return portal
        except oeffis.SessionClosedError as e:
            print(f"Session closed: {e.message}")
            raise SystemExit(1)
        except oeffis.DisconnectedError as e:
            print(f"Disconnected: {e.message}")
            raise SystemExit(1)

    raise RuntimeError("Failed to connect to portal")


def type_char(device: ei.Device, char: str):
    """Type a single character with its own emulation sequence."""
    keycode, needs_shift = get_key_info(char)
    if keycode == -1:
        print(f"Warning: No keycode for character '{char}', skipping")
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


def wait_for_device(ctx: ei.Sender, poll: select.poll) -> ei.Device:
    """Wait for a keyboard device to become available."""
    while True:
        poll.poll(500)
        ctx.dispatch()
        for event in ctx.events:
            print(f"    Event: {event.event_type.name}")
            if event.event_type == ei.EventType.DEVICE_ADDED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    print(f"    New device: {dev.name}")
                    return dev
            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    print(f"    Device resumed: {dev.name}")
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


def type_sentence(ctx: ei.Sender, device: ei.Device, text: str):
    """Type a full sentence - dispatch before AND after each character."""
    print(f"Typing: {text}")

    poll = select.poll()
    poll.register(ctx.fd, select.POLLOUT | select.POLLIN)
    current_device = device

    # CRITICAL: Keep references to prevent garbage collection of snegg objects
    kept_refs: list = [device]

    idx = 0
    while idx < len(text):
        char = text[idx]

        # Process any pending events BEFORE typing
        poll.poll(5)
        new_dev, was_removed = process_events(ctx, kept_refs)
        if was_removed:
            current_device = None
        if new_dev:
            current_device = new_dev

        # Ensure we have a device
        if current_device is None:
            print(f"  Waiting for device before typing '{char}'...")
            current_device = wait_for_device(ctx, poll)
            kept_refs.append(current_device)

        # Type the character
        type_char(current_device, char)
        print(f"  Typed '{char}' ({idx + 1}/{len(text)})")

        # Process events AFTER typing to check for removal
        poll.poll(5)
        new_dev, was_removed = process_events(ctx, kept_refs)
        if new_dev:
            current_device = new_dev

        # If device was removed, retry this character
        if was_removed:
            print(f"    Device removed after typing '{char}' - will retry")
            current_device = None
            continue

        idx += 1

    print("Done typing!")


def main():
    # Sample sentence to type
    sentence = "Hello from libei!"

    # Step 1: Connect to the RemoteDesktop portal
    portal = wait_for_portal()

    # Step 2: Create a libei Sender context using the portal's IS fd
    ctx = ei.Sender.create_for_fd(fd=portal.is_fd, name="libei-type-test")

    keyboard: Optional[ei.Device] = None

    # Step 3: Process events and find the keyboard device
    poll = select.poll()
    poll.register(ctx.fd)

    print("Waiting for keyboard device...")
    print("You have 5 seconds to click on the window where you want to type.")
    time.sleep(5)

    while poll.poll(1000):  # 1 second timeout in milliseconds
        ctx.dispatch()
        for event in ctx.events:
            print(f"Event: {event.event_type.name}")

            if event.event_type == ei.EventType.SEAT_ADDED:
                seat = event.seat
                if seat:
                    print(f"Seat added: {seat.name}")
                    # Bind to keyboard capability
                    seat.bind((ei.DeviceCapability.KEYBOARD,))

            elif event.event_type == ei.EventType.DEVICE_ADDED:
                device = event.device
                if device and ei.DeviceCapability.KEYBOARD in device.capabilities:
                    print(f"Keyboard device found: {device.name}")
                    keyboard = device

            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                device = event.device
                if device and ei.DeviceCapability.KEYBOARD in device.capabilities:
                    print(f"Device resumed: {device.name}, starting to type...")
                    type_sentence(ctx, device, sentence)
                    return

    if keyboard is None:
        print("No keyboard device found!")
        return

    # If we got a keyboard but no DEVICE_RESUMED event, try typing anyway
    print("Attempting to type...")
    type_sentence(ctx, keyboard, sentence)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        raise
