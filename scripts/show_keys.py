#!/usr/bin/env python3
"""Show each key you press and how to write it as a voiceType hotkey.

    pixi run python scripts/show_keys.py

A small window opens. With it focused, press keys (with Ctrl/Alt/Shift/Super
held for combinations). Close the window to quit. Keys your desktop keeps for
itself (e.g. Print Screen on GNOME) never reach the window, which also means
they'd make poor hotkeys.
"""

import tkinter as tk

# X key names that voiceType's hotkey syntax spells differently
RENAMES = {
    "Return": "<enter>",
    "Escape": "<esc>",
    "Prior": "<page_up>",
    "Next": "<page_down>",
    "BackSpace": "<backspace>",
    "space": "<space>",
}
MODIFIER_KEYS = ("Control", "Alt", "Shift", "Super", "Meta", "Hyper", "ISO_Level3")
# (Tk event.state bit, voiceType name)
MODIFIER_BITS = [(0x4, "<ctrl>"), (0x8, "<alt>"), (0x1, "<shift>"), (0x40, "<super>")]


def on_key(event):
    name = event.keysym
    if name.startswith(MODIFIER_KEYS):
        label.config(text=f"{name}\n(a modifier: hold it and press another key)")
        return
    key = RENAMES.get(name, name.lower() if len(name) == 1 else f"<{name.lower()}>")
    held = [mod for bit, mod in MODIFIER_BITS if event.state & bit]
    hotkey = "+".join(held + [key])
    label.config(text=f'{name}\nhotkey = "{hotkey}"')
    print(f'{name:<20} hotkey = "{hotkey}"', flush=True)


root = tk.Tk()
root.title("voiceType: press a key")
root.geometry("520x140")
label = tk.Label(root, text="Press a key...", font=("Sans", 18))
label.pack(expand=True)
root.bind("<Key>", on_key)
root.mainloop()
