#!/usr/bin/env python3
"""Test script to read keyboard events directly using evdev.

This tests if we can read from /dev/input/event* devices directly,
which is what the pynput uinput backend should be doing.

Run as root:
    sudo python test_evdev_direct.py
"""
import os
import sys

print(f"Python: {sys.executable}")
print(f"Running as UID: {os.geteuid()}")

try:
    import evdev

    print(
        f"evdev version: {evdev.__version__ if hasattr(evdev, '__version__') else 'unknown'}"
    )
except ImportError:
    print("evdev not installed. Install with: pip install evdev")
    sys.exit(1)

# List all input devices
devices = [evdev.InputDevice(path) for path in evdev.list_devices()]

print("\n" + "=" * 60)
print("Available input devices:")
print("=" * 60)
for device in devices:
    caps = device.capabilities(verbose=True)
    has_keys = ("EV_KEY", 1) in caps or 1 in device.capabilities()
    print(f"  {device.path}: {device.name}")
    if has_keys:
        print(f"    ^ Has keyboard capabilities")

# Find keyboard devices
keyboards = []
for device in devices:
    caps = device.capabilities()
    # Check if device has EV_KEY capability with actual key codes
    if 1 in caps:  # EV_KEY = 1
        key_codes = caps[1]
        # Check for common letter keys (KEY_A=30 through KEY_Z=44+)
        if any(30 <= k <= 52 for k in key_codes):
            keyboards.append(device)

if not keyboards:
    print("\nNo keyboard devices found!")
    sys.exit(1)

print(f"\n" + "=" * 60)
print(f"Found {len(keyboards)} keyboard device(s). Will listen on all.")
print("=" * 60)
print("Press keys to test. Press Ctrl+C to exit.\n")

import select

# Open all keyboard devices for reading
fds = {dev.fd: dev for dev in keyboards}

try:
    while True:
        r, w, x = select.select(fds.keys(), [], [])
        for fd in r:
            device = fds[fd]
            for event in device.read():
                if event.type == 1:  # EV_KEY
                    key_state = (
                        "PRESS"
                        if event.value == 1
                        else "RELEASE" if event.value == 0 else "REPEAT"
                    )
                    try:
                        key_name = evdev.ecodes.KEY[event.code]
                    except KeyError:
                        key_name = f"KEY_{event.code}"
                    print(
                        f"[{device.name}] {key_state}: {key_name} (code={event.code})"
                    )
except KeyboardInterrupt:
    print("\nDone")
