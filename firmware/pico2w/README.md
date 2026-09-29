# voiceType remote button (Raspberry Pi Pico 2 W)

Turns a Pico 2 W into a dictation button for another computer (e.g. a
Chromebook). Plug the Pico into the Chromebook, hold its button, and speak:
voiceType on your desktop records from the desktop's microphone, transcribes,
and sends the text back to the Pico, which types it into the Chromebook as a
USB keyboard.

```
Pico (USB keyboard in the Chromebook)       Desktop (voiceType)
  button down  ─────────────────────────▶   start recording (desktop mic)
  button up    ─────────────────────────▶   stop, transcribe
  types text   ◀─────────────────────────   text
```

The Pico keeps one TLS connection open to voiceType. It checks voiceType's
certificate, and voiceType checks the Pico's token. The Pico never accepts
incoming connections.

> **Tested on real hardware:** a Pico 2 W typing into a Chromebook set to
> Programmer Dvorak, triggered from a desktop hotkey. The LED patterns and the
> faster typing have only run in the simulation tests so far (the firmware under
> CPython against the real listener). See the
> [hardware checklist](#hardware-checklist).

## What you need

- A Pico 2 W with CircuitPython 9 or newer
- Optionally, a push button (or a foot pedal) wired between **GP15** and any
  **GND** pin. Without one, trigger dictation with a desktop hotkey whose
  pipeline uses `keyboard_backend = "remote"`.
- voiceType on the desktop, with this feature

## 1. Set up voiceType (desktop)

Create the certificate and token:

```bash
voicetype remote-setup
```

This writes `cert.pem`, `key.pem` and `token` to `~/.config/voicetype/remote/`
and prints the settings for the next steps. Add to
`~/.config/voicetype/settings.toml`, reusing your own stage names:

```toml
[remote]
enabled = true
# port = 8684

[stage_configs.TypeText_remote]
stage_class = "TypeText"
keyboard_backend = "remote"

[[pipelines]]
name = "remote"
hotkey = "remote:main"
stages = ["RecordAudio_default", "Transcribe_local", "CorrectTypos_default", "TypeText_remote"]
```

Restart voiceType (`systemctl --user restart app-io.github.voicetype.VoiceType.service`).
Its log should say `Remote listener on 0.0.0.0:8684 (TLS), buttons: main`.

If the desktop's firewall is on, open the port to your home network, e.g.
`sudo ufw allow from 192.168.1.0/24 to any port 8684 proto tcp`.

`keyboard_backend = "remote"` works with any hotkey, so you can also add a
pipeline where a desktop key (say `<ctrl>+<pause>`) types on the Chromebook.

## 2. Test the desktop side (no Pico needed)

From the Chromebook's Linux terminal or any other machine, with a copy of
`cert.pem` and the token:

```bash
python3 scripts/fake_pico.py --host nirvana --hold 3 --cert cert.pem --token-file token
```

Speak for 3 seconds; it prints the transcription. This checks the network,
firewall, TLS and token before the Pico is involved.

## 3. Set up the Pico

1. Plug the Pico in **without** holding BOOTSEL. The `CIRCUITPY` drive appears.
   (Holding BOOTSEL starts the chip's bootloader instead: that drive is called
   `RP2350` and only has `INDEX.HTM` and `INFO_UF2.TXT`. Your files are still
   there; replug normally.)
2. Copy `code.py`, `boot.py` and `hid_layouts.py` from this folder to `CIRCUITPY`.
   No libraries are needed.
3. Copy `~/.config/voicetype/remote/cert.pem` to `CIRCUITPY` as `voicetype_cert.pem`.
4. Copy `settings.toml.example` to `CIRCUITPY/settings.toml` (or merge it into
   yours) and fill it in. Set `VOICETYPE_LAYOUT` to the Chromebook's keyboard
   layout (see [Keyboard layouts](#keyboard-layouts)).
5. Eject `CIRCUITPY` before unplugging, so the computer finishes writing.

To watch what the Pico is doing, open the serial console: on a Chromebook,
open https://code.circuitpython.org in Chrome and connect over USB. On Linux,
use a serial terminal such as `screen /dev/ttyACM0 115200`.

## Using it

Hold the button, speak, and release. The text appears wherever the cursor is.
The desktop plays voiceType's start sound when recording begins. If the Pico
disconnects mid-recording, voiceType discards that recording and plays its
error sound.

| Pico LED                        | Meaning                                                    |
| ------------------------------- | ---------------------------------------------------------- |
| Slow blink (once a second)      | Connecting to WiFi / voiceType                             |
| Short blip every 10 s           | Connected and ready (heartbeat; `VOICETYPE_HEARTBEAT_MS`)  |
| On                              | Typing, or the Pico's button is held (recording)           |
| Fast blink                      | Transcribing, after you release the Pico's button          |
| Three quick flashes             | Typing failed, or voiceType didn't start recording         |
| Constant fast flicker           | Setup problem; the serial console says what to fix         |

## Keyboard layouts

A USB keyboard sends key positions, not characters, and the computer turns them
into characters using its own layout setting. So the Pico needs to know that
layout: set `VOICETYPE_LAYOUT` to `us` (QWERTY), `dvorak`, or `dvp`
(Programmer Dvorak). Gibberish means the setting doesn't match the layout
selected in ChromeOS.

The Pico types printable ASCII plus Enter and Tab. voiceType simplifies other
characters before sending them (`“café” — naïve` becomes `"cafe" -- naive`).

## Buttons

`VOICETYPE_BUTTONS = "GP15=main,GP14=jarvis"` adds a second button. Each name
triggers the pipeline whose hotkey is `remote:<name>`, e.g. a Jarvis pipeline
with `hotkey = "remote:jarvis"`.

## Security

- Traffic is TLS-encrypted, and the Pico only trusts your desktop's certificate.
- voiceType only accepts devices that send the token. Rotate the certificate and
  token with `voicetype remote-setup --force`, then update the Pico.
- Once everything works, set `VOICETYPE_HIDE_USB = 1` and replug. The Pico then
  shows up as just a keyboard: `CIRCUITPY` (which holds your WiFi password and
  token) and the serial console are hidden. To get them back, hold the
  voiceType button (not BOOTSEL) while plugging in, and keep holding it until
  the drive appears. The Pico checks the button only once, a moment after it
  powers up.
- Don't set `CIRCUITPY_WEB_API_PASSWORD`: it turns on CircuitPython's web
  workflow, which lets anyone with the password change the Pico's code over WiFi.

## Hardware checklist

Things to confirm on real hardware (checked items are confirmed):

- [x] `voicetype remote-setup` works, and voiceType logs `Remote listener on 0.0.0.0:8684 (TLS)`.
- [ ] `scripts/fake_pico.py --host nirvana --hold 3` from another machine prints
      what you said. This covers the network path, firewall, TLS and token.
- [x] The Pico connects: voiceType logs `Remote device connected: pico2w`.
      On the Pico's serial console that's `WiFi connected`, then
      `Connecting to nirvana at 192.168.1.109`, then `Connected to voiceType`.
      If `nirvana` doesn't resolve, try `nirvana.attlocal.net`, then the IP
      address. (`nirvana.local` is untested; CircuitPython may not look up
      `.local` names.)
- [x] The Pico completes the TLS handshake. If it reports a certificate or
      handshake error, recopy `cert.pem` as `voicetype_cert.pem`.
- [x] A dictation triggered from a desktop hotkey types correctly on the
      Chromebook (Programmer Dvorak).
- [ ] Dictating "Testing 1, 2, 3. Does punctuation work? Yes, it does!" into a
      text editor on the Chromebook types exactly that, with no dropped or
      wrong characters (the digits exercise Shift on Programmer Dvorak).
- [ ] Long dictation (30+ seconds) types completely.
- [ ] Repeated letters and capitals type correctly with one report per
      keystroke, e.g. "Mississippi, AAA, aA".
- [ ] The LED blips every 10 seconds while connected, stays on while typing,
      and blinks slowly while disconnected.
- [ ] Hold the button and unplug the Pico: within ~3 seconds voiceType logs
      that the device went away and plays the error sound.
- [ ] Restart voiceType while the Pico is plugged in: the LED blinks slowly,
      then the Pico reconnects within ~10 seconds.
- [x] Set `VOICETYPE_HIDE_USB = 1` and replug: no drive appears. Replug while
      holding the button until the drive appears: the drive is back.

## Protocol

One JSON object per line, over TLS. See the docstring in
[`voicetype/hotkey_listener/remote_hotkey_listener.py`](../../voicetype/hotkey_listener/remote_hotkey_listener.py).
