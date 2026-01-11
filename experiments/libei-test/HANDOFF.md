# libei Typing Experiment - Handoff Summary

## Goal
Create a program that types text using libei on Wayland (GNOME/mutter). This is for a voice typing application.

## Current Status: WORKING ✓
The script `type_sentence_dbus.py` successfully types "Hello from libei!" using direct D-Bus interaction with the XDG RemoteDesktop portal.

## The Problem We Solved
Mutter periodically removes and re-adds virtual keyboard devices mid-typing. Characters sent during this removal window are **silently dropped** - no error, they just vanish. This is intentional behavior by mutter, not a bug.

## The Solution
1. **Direct D-Bus** - Bypass liboeffis, use `dbus-python` + `PyGObject` to talk to `org.freedesktop.portal.RemoteDesktop`
2. **50ms settle time** - After each character, wait 50ms for compositor to send any device removal events
3. **Rollback logic** - Track "last confirmed" position; when device removal detected, roll back and retry from there

## Key Files
- `type_sentence_dbus.py` - Working implementation
- `type_sentence.py` - Original liboeffis-based version (less reliable)
- `NOTES.md` - Detailed notes on failed approaches and insights
- `pyproject.toml` - Pixi config with dependencies

## To Run
```bash
pixi run run-dbus 2>/dev/null  # stderr has harmless cleanup warnings
```

## Key Technical Details
- libei sends **evdev keycodes** (physical key positions), compositor's XKB translates to characters
- Uses `snegg` Python bindings for libei
- Each character needs its own `start_emulating()`/`stop_emulating()` cycle
- Must keep Python references to snegg objects to prevent GC issues
- **Don't use `time.sleep()`** - breaks the connection

## Known Limitations
- 50ms per character = ~20 chars/sec max typing speed
- The device removal/re-addition behavior appears to be **mutter-specific**, not a libei protocol limitation
- No existing mutter issue about this; may be worth filing one

## libei Documentation Clarification
The [libei README](https://gitlab.freedesktop.org/libinput/libei/-/blob/main/README.md) says two things that seem contradictory:
1. "The above caters for the xdotool use-case" - they explicitly support this
2. "libei is not designed for short-lived fire-and-forget-type applications like xdotool"

The distinction: libei **can** do xdotool-like typing/input injection, but requires a **persistent connection**. The fire-and-forget pattern (run command, exit immediately) isn't supported. A daemon-style approach works fine.

The device removal issue we encountered is **not documented** in libei - it's compositor behavior. Worth checking if other compositors (wlroots-based, KWin) have the same aggressive device removal.

## Related Issues Found
- [input-leap#1699](https://github.com/input-leap/input-leap/issues/1699) - Similar device removal issue, fixed with `restore_token`
- Talon voice control doesn't work on Wayland due to missing APIs

## Dependencies
- `dbus-python`, `pygobject` (from conda-forge)
- `snegg` (from git, Python bindings for libei)
- System: `libei1`, `liboeffis1`
