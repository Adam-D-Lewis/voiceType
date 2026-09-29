"""Keyboard layouts for typing text as a USB keyboard.

A USB keyboard doesn't send characters. It sends which key was pressed, and the
computer turns keys into characters using its own keyboard layout setting. So
to type "h" on a computer set to Programmer Dvorak, the Pico has to press the
key that says "j" on a QWERTY keyboard. These tables map each character to the
key (and Shift state) that types it under the computer's layout.

Set VOICETYPE_LAYOUT in settings.toml to the layout the computer uses. The
tables match xkeyboard-config (which ChromeOS uses): us, us(dvorak), us(dvp).
"""

# HID usage IDs of the 47 character keys: the number row (starting with the key
# left of 1), then the three letter rows, each left to right. The comments say
# what the keys type on a US QWERTY keyboard.
# fmt: off
KEYS = (
    # ` 1 2 3 4 5 6 7 8 9 0 - =
    0x35, 0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2D, 0x2E,
    # q w e r t y u i o p [ ] \
    0x14, 0x1A, 0x08, 0x15, 0x17, 0x1C, 0x18, 0x0C, 0x12, 0x13, 0x2F, 0x30, 0x31,
    # a s d f g h j k l ; '
    0x04, 0x16, 0x07, 0x09, 0x0A, 0x0B, 0x0D, 0x0E, 0x0F, 0x33, 0x34,
    # z x c v b n m , . /
    0x1D, 0x1B, 0x06, 0x19, 0x05, 0x11, 0x10, 0x36, 0x37, 0x38,
)
# fmt: on

SPACE = 0x2C
ENTER = 0x28
TAB = 0x2B
LEFT_SHIFT = 0xE1

# What each key in KEYS types on the computer: (without Shift, with Shift)
LAYOUTS = {
    "us": (
        "`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./",
        '~!@#$%^&*()_+QWERTYUIOP{}|ASDFGHJKL:"ZXCVBNM<>?',
    ),
    "dvorak": (
        "`1234567890[]',.pyfgcrl/=\\aoeuidhtns-;qjkxbmwvz",
        '~!@#$%^&*(){}"<>PYFGCRL?+|AOEUIDHTNS_:QJKXBMWVZ',
    ),
    # Programmer Dvorak: symbols on the number row, digits need Shift
    "dvp": (
        "$&[{}(=*)+]!#;,.pyfgcrl/@\\aoeuidhtns-'qjkxbmwvz",
        '~%7531902468`:<>PYFGCRL?^|AOEUIDHTNS_"QJKXBMWVZ',
    ),
}

ALIASES = {
    "qwerty": "us",
    "programmer-dvorak": "dvp",
    "programmer_dvorak": "dvp",
}


def keymap(layout):
    """Return {character: (keycode, needs_shift)} for a layout name."""
    name = ALIASES.get(layout.lower(), layout.lower())
    if name not in LAYOUTS:
        raise ValueError(
            "Unknown keyboard layout '{}'. Choose one of: {}".format(
                layout, ", ".join(sorted(LAYOUTS))
            )
        )
    unshifted, shifted = LAYOUTS[name]
    table = {" ": (SPACE, False), "\n": (ENTER, False), "\t": (TAB, False)}
    for keycode, char in zip(KEYS, shifted):
        table[char] = (keycode, True)
    for keycode, char in zip(KEYS, unshifted):
        table[char] = (keycode, False)
    return table
