# libei Typing Experiments - Notes

## Problem (SOLVED)
When typing longer strings via libei, characters were being lost due to mutter removing/re-adding the virtual keyboard device mid-sequence. Characters sent during the removal window were silently dropped.

## Current Status

**WORKING** - The `type_sentence_dbus.py` script successfully types "Hello from libei!" by:
1. Using direct D-Bus interaction (bypassing liboeffis)
2. Waiting 50ms after each character for compositor to settle
3. Rolling back to last confirmed position on device removal

## Working Approach (type_sentence_dbus.py)

### Key Strategy: Settle Time + Rollback

1. **Direct D-Bus interaction** - Bypass liboeffis and use dbus-python + PyGObject to interact with the RemoteDesktop portal directly
2. **One emulation sequence per character** - Each character gets its own `start_emulating()` / `stop_emulating()` cycle
3. **50ms settle time after each character** - Give compositor time to process and potentially remove device
4. **Track "last confirmed" position** - Only advance when no device removal detected
5. **Rollback on removal** - When device is removed, go back to last confirmed position and retry
6. **Keep Python references** - Store events/devices to prevent garbage collection

### Why Direct D-Bus?

Using dbus-python directly instead of liboeffis gives us:
- Full control over the session lifecycle
- Better error handling and visibility
- No dependency on liboeffis (one less library)

### The Core Pattern
```python
SETTLE_TIME_MS = 50  # Critical: wait for compositor to settle

idx = 0
last_confirmed_idx = 0

while idx < len(text):
    # Drain pending events
    new_dev, was_removed = drain_events(ctx, poll, kept_refs, timeout_ms=5)
    if was_removed:
        current_device = None

    # Wait for device if needed, rollback on re-add
    if current_device is None:
        current_device = wait_for_device(...)
        if idx > last_confirmed_idx:
            idx = last_confirmed_idx  # ROLLBACK
            continue

    # Type character
    type_char(current_device, char)

    # Wait for compositor to settle
    new_dev, was_removed = drain_events(ctx, poll, kept_refs, timeout_ms=SETTLE_TIME_MS)

    if was_removed:
        idx = last_confirmed_idx  # ROLLBACK
        continue
    else:
        last_confirmed_idx = idx + 1  # Character confirmed

    idx += 1
```

## Why Mutter Removes the Device

This is **intentional behavior**, not a bug:
- The RemoteDesktop portal is designed for screen sharing/remote control
- Mutter periodically "resets" virtual devices to prevent stale connections
- The protocol expects apps to handle device removal/re-addition gracefully
- Original use case was VNC-like remote desktop, not sustained typing

## Failed Approaches

### 1. Simple sequential typing with sleep between characters
**Result:** Made it worse - sleep appears to break the libei connection/session

### 2. Batching multiple characters in one emulation sequence
**Result:** Only first ~5 characters typed due to device removal

### 3. Polling/dispatching without handling device removal
**Result:** Characters lost when device removed mid-sequence

### 4. Retry only the current character
**Result:** Lost characters sent BEFORE the removal event was received (race condition)

### 5. Short poll timeouts (5-20ms)
**Result:** Not enough time for compositor to send removal events

## Environment
- Wayland compositor (mutter/GNOME)
- snegg library (Python bindings for libei)
- dbus-python + PyGObject for portal interaction
- Custom Dvorak Programmer layout

## Key Insights
1. libei sends raw evdev keycodes (physical key positions). The compositor's XKB keymap translates these to characters.
2. Mutter periodically removes/re-adds the virtual keyboard device - you must handle this!
3. Each key event (press/release) should get its own `frame()` call
4. Don't use `time.sleep()` - it breaks the connection
5. Keep Python references to snegg objects to prevent garbage collection
6. **The settle time (50ms) is critical** - gives compositor time to send removal events
7. **Must track "last confirmed" position** - characters sent before removal detection are silently lost
