# libei Typing Experiments

Experiments with typing text programmatically on Wayland using libei (the Emulated Input protocol).

## Quick Start

```bash
# Install system dependencies
sudo apt install liboeffis1 libei1

# Install Python dependencies
pixi install

# Run the typing demo
pixi run run
```

A dialog will appear asking you to approve input device access. After approval, switch to a text editor within the countdown - the script will type text.

## File Overview

### Core Library

| File | Description |
|------|-------------|
| `libei_ctypes.py` | **Direct ctypes bindings for libei**. Bypasses snegg to avoid debug spam ("Invalid event type" messages). Provides `Sender`, `Device`, `Seat`, `Event` classes wrapping the C libei API. Use this when you need lower-level control or want to avoid snegg's overhead. |

### Test Scripts (in order of complexity)

| File | Description |
|------|-------------|
| `test_single_key.py` | **Minimal test** - presses and releases the 'a' key once. Good for verifying the basic libei → portal → compositor pipeline works. Uses snegg + oeffis. |
| `type_sentence.py` | **Original sentence typer** using snegg + oeffis. Has hardcoded Dvorak Programmer keyboard mappings. Slower approach with per-character `start_emulating()`/`stop_emulating()` calls and multiple `frame()` calls per keystroke. |
| `type_sentence_dbus.py` | **Direct D-Bus portal interaction** instead of using liboeffis. Manually calls `CreateSession()`, `SelectDevices()`, `Start()`, `ConnectToIS()` via dbus-python. Still uses snegg for the actual key sending. Good reference for understanding the portal protocol. |
| `type_sentence_ctypes.py` | **Fast typer using ctypes**. Uses `libei_ctypes.py` instead of snegg, plus direct D-Bus for the portal. Has optimized `type_sentence_fast()` with short delays (5ms), non-blocking polling, and rollback on device removal. Reports typing speed in chars/sec. |
| `type_sentence_fast.py` | **Fast typer using snegg**. Applies the optimization techniques from `type_sentence_ctypes.py` but keeps using snegg. Provides `--slow` flag to compare with original approach. Reports typing speed. |
| `type_sentence_xkb.py` | **Dynamic keyboard layout detection**. Uses libxkbcommon via ctypes to auto-detect your keyboard layout (Dvorak, QWERTY, etc.) and build the character→keycode mapping at runtime. No hardcoded layout dictionaries needed. |

### Comparison Chart

| Script | Portal Library | EI Library | Keyboard Layout | Speed |
|--------|---------------|------------|-----------------|-------|
| `test_single_key.py` | oeffis (snegg) | snegg | hardcoded | N/A |
| `type_sentence.py` | oeffis (snegg) | snegg | hardcoded Dvorak | slow |
| `type_sentence_dbus.py` | dbus-python | snegg | hardcoded Dvorak | medium |
| `type_sentence_ctypes.py` | dbus-python | ctypes | hardcoded Dvorak | fast |
| `type_sentence_fast.py` | oeffis (snegg) | snegg | hardcoded Dvorak | fast |
| `type_sentence_xkb.py` | oeffis (snegg) | snegg | **auto-detect (XKB)** | fast |

## Usage Examples

```bash
# Basic test - types 'a'
python test_single_key.py

# Original approach (slow)
python type_sentence.py

# Fast snegg version
python type_sentence_fast.py
python type_sentence_fast.py --slow  # compare with slow version

# Fast ctypes version
python type_sentence_ctypes.py
python type_sentence_ctypes.py --slow

# Auto-detect keyboard layout
python type_sentence_xkb.py
python type_sentence_xkb.py --show-mapping  # debug: show char→keycode map
python type_sentence_xkb.py --layout us --variant dvp  # override layout
```

## Key Concepts

### The libei Pipeline

```
Your App → libei → IS (compositor) → XKB keymap → Application
              ↑
         evdev keycodes (physical key positions)
```

1. **Portal Connection**: Get permission from user via RemoteDesktop portal dialog
2. **IS File Descriptor**: Portal gives you an fd to communicate with compositor
3. **Send evdev Keycodes**: libei sends physical key positions (not characters)
4. **XKB Translation**: Compositor's keymap converts keycodes to characters

### Why Keyboard Layout Matters

libei sends **evdev scancodes** (physical key positions on a US QWERTY keyboard). The compositor applies the user's XKB keymap to translate these to characters.

- To type 'a' on QWERTY: send keycode 30
- To type 'a' on Dvorak: send keycode 30 (which is physical 'a' position, producing 'a' in Dvorak too since 'a' is in same position)
- To type 'e' on Dvorak: send keycode 32 (physical 'd' position, which produces 'e' in Dvorak)

### Device Lifecycle (Mutter quirk)

Mutter frequently removes and re-adds the virtual keyboard device during typing. The fast implementations handle this with:
- Non-blocking event polling
- Rollback mechanism to retype dropped characters
- Reference keeping to prevent Python GC issues

## Performance Notes

The main speed optimizations:

1. **Fewer frame() calls** - Original: 2-4 per char. Fast: 1 per char.
2. **Shorter delays** - Original: event-driven waits. Fast: 5ms fixed delay.
3. **Non-blocking polling** - Check for events without waiting.
4. **Batched emulating** - Original: start/stop per char. Fast: start/stop per char but with minimal frames.

Typical speeds:
- Slow approach: ~10-20 chars/sec
- Fast approach: ~100+ chars/sec

## Resources

- [snegg documentation](https://libinput.pages.freedesktop.org/snegg/snegg.ei.html)
- [snegg GitLab](https://gitlab.freedesktop.org/libinput/snegg)
- [libei documentation](https://libinput.pages.freedesktop.org/libei/)
- [XDG RemoteDesktop Portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)
