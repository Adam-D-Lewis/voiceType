"""Runs once at power-up, before the computer sees the Pico's USB devices.

Once everything works, set VOICETYPE_HIDE_USB = 1 in settings.toml so the Pico
shows up as just a keyboard: this hides the CIRCUITPY drive (which holds your
WiFi password and voiceType token) and the serial console.

To get the drive back, hold the voiceType button (the one wired to the first
pin in VOICETYPE_BUTTONS, GP15 by default) while plugging the Pico in. Don't
hold BOOTSEL: that starts the chip's bootloader, whose drive is called RP2350
and only holds INDEX.HTM and INFO_UF2.TXT.

Changes to this file take effect after unplugging and replugging the Pico.
"""

import os

import board
import digitalio
import storage
import usb_cdc


def hide_requested():
    return str(os.getenv("VOICETYPE_HIDE_USB")).strip().lower() in ("1", "true", "yes")


def button_held():
    spec = os.getenv("VOICETYPE_BUTTONS") or "GP15=main"
    pin_name = spec.split(",")[0].split("=")[0].strip()
    button = digitalio.DigitalInOut(getattr(board, pin_name))
    button.switch_to_input(pull=digitalio.Pull.UP)
    held = not button.value  # The button connects the pin to ground
    button.deinit()
    return held


if hide_requested() and not button_held():
    storage.disable_usb_drive()
    usb_cdc.disable()
