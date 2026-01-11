#!/usr/bin/env python3
"""
Optimized sentence typing using libei via snegg.

This version applies the fast typing techniques from type_sentence_ctypes.py
to the snegg-based approach, avoiding per-character start/stop emulating overhead.
"""

import select
import time

import snegg.ei as ei
import snegg.oeffis as oeffis

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


def wait_for_portal() -> oeffis.Oeffis:
    """Connect to the RemoteDesktop portal and wait for IS connection."""
    print("Connecting to RemoteDesktop portal...")
    print("A dialog will appear asking you to approve input device access.")

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


def type_key_fast(device: ei.Device, char: str):
    """Type a single key without start/stop emulating (caller manages session)."""
    keycode, needs_shift = get_key_info(char)
    if keycode == -1:
        return

    if needs_shift:
        device.keyboard_key(KEY_LEFTSHIFT, True)
        device.keyboard_key(keycode, True)
        device.keyboard_key(keycode, False)
        device.keyboard_key(KEY_LEFTSHIFT, False)
    else:
        device.keyboard_key(keycode, True)
        device.keyboard_key(keycode, False)


def type_char_slow(device: ei.Device, char: str):
    """Type a single character with its own emulation sequence (original slow method)."""
    keycode, needs_shift = get_key_info(char)
    if keycode == -1:
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
                    print(f"  Device ready: {dev.name}")
                    kept_refs.append(dev)
                    return dev


def type_sentence_fast(ctx: ei.Sender, device: ei.Device, text: str, delay_ms: int = 5):
    """Type text fast with per-character emulating cycles and rollback on device removal.

    This is the optimized version that:
    - Uses shorter delays between characters
    - Does non-blocking event polling
    - Has rollback on device removal to retype dropped characters
    """
    print(f"Typing {len(text)} chars: {text[:50]}{'...' if len(text) > 50 else ''}")

    poll = select.poll()
    poll.register(ctx.fd, select.POLLIN | select.POLLOUT)
    kept_refs = [device]
    current_device = device

    idx = 0
    last_confirmed = 0  # Last position confirmed received

    while idx < len(text):
        char = text[idx]

        # Check for device changes (non-blocking)
        if poll.poll(0):
            ctx.dispatch()
            for event in ctx.events:
                kept_refs.append(event)
                if event.event_type == ei.EventType.DEVICE_REMOVED:
                    current_device = None
                elif event.event_type == ei.EventType.DEVICE_RESUMED:
                    dev = event.device
                    if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                        current_device = dev
                        kept_refs.append(dev)

        if current_device is None:
            # Rollback to last confirmed position
            idx = last_confirmed
            current_device = wait_for_device(ctx, poll, kept_refs)
            continue

        # Type one character with its own emulating session
        current_device.start_emulating()
        type_key_fast(current_device, char)
        current_device.frame()
        current_device.stop_emulating()

        # Wait longer for first few chars (mutter needs to settle)
        wait_time = 50 if idx < 3 else delay_ms

        poll.poll(wait_time)
        ctx.dispatch()

        # Check for device removal
        device_ok = True
        for event in ctx.events:
            kept_refs.append(event)
            if event.event_type == ei.EventType.DEVICE_REMOVED:
                current_device = None
                device_ok = False
            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    current_device = dev
                    kept_refs.append(dev)

        if device_ok:
            last_confirmed = idx + 1
            idx += 1
        else:
            # Rollback
            idx = last_confirmed
            if current_device is None:
                current_device = wait_for_device(ctx, poll, kept_refs)

    print("Done typing!")


def type_sentence_slow(ctx: ei.Sender, device: ei.Device, text: str):
    """Original slow implementation for comparison."""
    print(f"Typing (slow): {text}")

    poll = select.poll()
    poll.register(ctx.fd, select.POLLOUT | select.POLLIN)
    current_device = device
    kept_refs: list = [device]

    for idx, char in enumerate(text):
        # Process events before typing
        poll.poll(5)
        ctx.dispatch()
        for event in ctx.events:
            kept_refs.append(event)
            if event.event_type == ei.EventType.DEVICE_REMOVED:
                current_device = None
            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    current_device = dev
                    kept_refs.append(dev)

        if current_device is None:
            current_device = wait_for_device(ctx, poll, kept_refs)

        type_char_slow(current_device, char)
        print(f"  Typed '{char}' ({idx + 1}/{len(text)})")

        # Process events after typing
        poll.poll(5)
        ctx.dispatch()
        for event in ctx.events:
            kept_refs.append(event)
            if event.event_type == ei.EventType.DEVICE_RESUMED:
                dev = event.device
                if dev and ei.DeviceCapability.KEYBOARD in dev.capabilities:
                    current_device = dev
                    kept_refs.append(dev)

    print("Done typing!")


def main():
    import sys

    # Test sentence - repeat to make timing difference more noticeable
    sentence = "Hello from libei!" * 3

    use_slow = "--slow" in sys.argv

    # Connect to portal
    portal = wait_for_portal()

    # Create libei Sender context
    ctx = ei.Sender.create_for_fd(fd=portal.is_fd, name="libei-fast-test")

    print("\nYou have 3 seconds to focus on a text editor...")
    time.sleep(3)

    # Keep references to prevent GC
    kept_refs: list = []

    poll = select.poll()
    poll.register(ctx.fd)

    # Wait for device
    device = wait_for_device(ctx, poll, kept_refs)

    # Time the typing
    start_time = time.perf_counter()

    if use_slow:
        type_sentence_slow(ctx, device, sentence)
    else:
        type_sentence_fast(ctx, device, sentence)

    elapsed = time.perf_counter() - start_time
    chars_per_sec = len(sentence) / elapsed
    print(
        f"\nTyped {len(sentence)} chars in {elapsed:.3f}s ({chars_per_sec:.1f} chars/sec)"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        raise
