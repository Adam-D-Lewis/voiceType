import os
import threading
from typing import Iterable

# For this minimal tutorial, force GTK for simplicity and determinism.
# This avoids backend differences and we sequence menu init safely.
os.environ["PYSTRAY_BACKEND"] = "gtk"

import pystray
from PIL import Image, ImageDraw
from pystray import Menu
from pystray import MenuItem as Item

# Minimal in-memory state
counter = 0
lock = threading.Lock()


def make_icon(size: int = 64, color=(0, 128, 255)) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size // 2 - 4
    c = (size // 2, size // 2)
    d.ellipse(
        [c[0] - r, c[1] - r, c[0] + r, c[1] + r],
        fill=color,
        outline=(30, 30, 30, 255),
        width=3,
    )
    return img


def increment(icon: pystray._base.Icon, item: Item):
    global counter
    with lock:
        counter += 1
    # Tell pystray to re-evaluate any callable menu content next time it opens
    icon.update_menu()


def dynamic_section() -> Iterable[Item]:
    # This function will be invoked without arguments
    with lock:
        current = counter
    yield Item(text=f"Counter: {current}", action=lambda i, it: None, enabled=False)
    yield Item(text="Increment counter", action=increment)


def main():
    # Construct the icon with the menu directly; dynamic_section is zero-arg, which GTK accepts.
    icon = pystray.Icon(
        name="pystray_dynamic_minimal",
        title="Dynamic Menu (Minimal)",
        icon=make_icon(64),
        menu=Menu(
            Item("Dynamic", Menu(dynamic_section)),
            Item("---", None),
            Item("Quit", lambda icon, item: icon.stop()),
        ),
    )
    # Blocking run keeps the app alive
    icon.run()


if __name__ == "__main__":
    main()
