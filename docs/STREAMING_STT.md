# Streaming STT (Kyutai Delayed-Streams-Modeling)

This guide covers setting up VoiceType's real-time streaming speech-to-text mode using Kyutai's delayed-streams-modeling (DSM) Rust server. In this mode, words are typed into the focused application **as you speak**, while holding a push-to-talk button.

## Prerequisites

- Linux with X11 (tested on Ubuntu with GNOME)
- Python 3.11+
- A working microphone
- The Kyutai DSM Rust server (see below)

## 1. Set Up the Kyutai DSM Rust Server

Follow the install and setup instructions at [kyutai-labs/delayed-streams-modeling](https://github.com/kyutai-labs/delayed-streams-modeling/) to build and run the Rust-based streaming server.

Once running, the server should be reachable at `ws://127.0.0.1:8080/api/asr-streaming` (default).

> **Tip:** For auto-start on boot, create a systemd service for the Rust server.

## 2. Install VoiceType

```bash
cd voiceType
git submodule update --init --recursive
uv sync
uv run python -m voicetype install
```

The installer creates a systemd user service that auto-starts on login.

## 3. Configure the Pipeline

VoiceType loads settings from (in order):
1. `./settings.toml`
2. `~/.config/voicetype/settings.toml`
3. `/etc/voicetype/settings.toml`

If no file exists, built-in defaults are used. To customize, create a `settings.toml`:

```toml
[stage_configs.StreamingSTT]
server_url = "ws://127.0.0.1:8080"   # Kyutai DSM server URL
api_key = "public_token"              # Server API key
# sample_rate = 24000                 # Must match server (default: 24000)
# block_size = 1920                   # 80ms chunks at 24kHz (default: 1920)
# max_duration = 120                  # Max streaming seconds (default: 120)
# silence_flush_duration = 1.5        # Silence sent after PTT release to flush last words (default: 1.5)
# drain_timeout = 2.0                 # Wait for final server responses (default: 2.0)
# keyboard_backend = "auto"           # auto, pynput, wtype, or eitype
# char_delay = 0.001                  # Inter-character delay for pynput backend
# device_name = "My Microphone"       # Specific audio input device (default: system default)

[[pipelines]]
name = "streaming"
enabled = true
hotkey = "<pause>"                    # See "Hotkey Options" below
stages = ["StreamingSTT"]
```

## 4. Hotkey Options

### Keyboard keys

Standard pynput key names work:

```toml
hotkey = "<pause>"          # Pause/Break key
hotkey = "<f12>"            # F12
hotkey = "<ctrl>+<shift>+s" # Modifier combo
```

### Mouse buttons

Mouse buttons are supported with the `<mouseN>` syntax:

```toml
hotkey = "<mouse8>"    # Thumb back button (common for multi-button mice)
hotkey = "<mouse9>"    # Thumb forward button
hotkey = "<mouse20>"   # Remapped button (see below)
```

Mouse buttons can also be combined with keyboard modifiers: `<ctrl>+<mouse8>`.

### Remapping mouse buttons (X11)

By default, mouse button 8 triggers "browser back" in most applications. To disable that while keeping the button usable for VoiceType, remap it via `xinput` to a high unused button number:

```bash
# Find your mouse device name
xinput list | grep -i mouse

# Check current button map
xinput get-button-map "Your Mouse Name"

# Remap button 8 to button 20 (no default action)
xinput set-button-map "Your Mouse Name" 1 2 3 4 5 6 7 20 9 10 11 12 13 14 15 16 17 18 19 20
```

Then set your hotkey to match the remapped number:

```toml
hotkey = "<mouse20>"
```

To make the remap persistent across reboots, add the `xinput set-button-map` command to `~/.xprofile`:

```bash
echo 'xinput set-button-map "Your Mouse Name" 1 2 3 4 5 6 7 20 9 10 11 12 13 14 15 16 17 18 19 20' >> ~/.xprofile
```

## 5. Usage

1. Start the Kyutai DSM Rust server
2. Start VoiceType (or let the systemd service handle it):
   ```bash
   uv run python -m voicetype
   ```
3. **Hold** the PTT button and speak — words appear in the focused app in real-time
4. **Release** the button — the mic cuts, a brief silence flush ensures the last word(s) come through, then the session ends

### Service management

```bash
voicetype status    # Check if running
voicetype restart   # Restart after config changes
voicetype stop      # Stop the service
voicetype start     # Start the service
```

Or use systemctl directly:

```bash
systemctl --user restart app-io.github.voicetype.VoiceType.service
journalctl --user -u app-io.github.voicetype.VoiceType.service -f   # Follow logs
```

## How It Works

The `StreamingSTT` stage runs a single-stage pipeline that handles everything concurrently:

1. Opens a WebSocket connection to the Kyutai DSM server
2. Captures audio from the microphone (24kHz, mono, float32, 80ms chunks)
3. Streams audio as MessagePack-encoded messages to the server
4. Receives word-by-word transcriptions and types each word immediately via the keyboard backend
5. On PTT release: stops the mic, sends silence to flush the server's pipeline, waits briefly for final words, then closes cleanly

The server also provides built-in voice activity detection (VAD), so no separate VAD setup is needed.
