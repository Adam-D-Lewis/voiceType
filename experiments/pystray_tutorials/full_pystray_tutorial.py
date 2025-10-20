import os
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Tuple

import pystray

# Third-party
from loguru import logger

# IMPORTANT: Choose a reliable backend for Linux Desktop Environments.
# GTK is generally the most compatible on Ubuntu 22.04/24.04 and others.
# Valid values: 'gtk', 'appindicator', 'xorg', 'dummy' (fallback/test)
# os.environ.setdefault("PYSTRAY_BACKEND", "gtk")
# Trying to use the appindicator backend fails on Ubuntu 24.04 due to not finding the installed dependencies.  We could maybe try packaging it on conda-forge (see https://claude.ai/share/0786af55-4154-414b-bc74-1ede6d45e52a)
# GI_TYPELIB_PATH='/usr/lib/x86_64-linux-gnu/girepository-1.0' python
# pystray imports must happen after setting PYSTRAY_BACKEND
from PIL import Image, ImageDraw
from pystray import Menu
from pystray import MenuItem as Item


# --------------------------
# Icon/image helpers
# --------------------------
def make_icon(
    size: int = 64, color=(0, 128, 255), accent=(255, 255, 255)
) -> Image.Image:
    """
    Create a simple, crisp system tray icon programmatically.
    - A colored circle with a small checkered accent for visual interest.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer circle
    radius = size // 2 - 4
    center = (size // 2, size // 2)
    bbox = [
        center[0] - radius,
        center[1] - radius,
        center[0] + radius,
        center[1] + radius,
    ]
    draw.ellipse(bbox, fill=color, outline=(20, 20, 20, 255), width=3)

    # Small checkerboard accent
    grid = 4
    cell = size // 8
    start_x = size - grid * cell - 6
    start_y = 6
    for r in range(grid):
        for c in range(grid):
            if (r + c) % 2 == 0:
                x0 = start_x + c * cell
                y0 = start_y + r * cell
                draw.rectangle(
                    [x0, y0, x0 + cell - 1, y0 + cell - 1], fill=accent + (200,)
                )

    return img


# --------------------------
# Snapshot data class
# --------------------------
@dataclass
class StateSnapshot:
    enabled: bool
    theme: str
    counter: int
    icon_color: Tuple[int, int, int]


# --------------------------
# Tutorial state
# --------------------------
class TutorialState:
    def __init__(self):
        self.lock = threading.Lock()
        self.enabled = True  # for a checkbox/toggle item
        self.theme = "Blue"  # for a radio group
        self.counter = 0  # for demonstrating dynamic menus
        self.running = True  # for background worker
        self.icon_color = (0, 128, 255)  # current icon color

    def toggle_enabled(self):
        with self.lock:
            self.enabled = not self.enabled
            logger.info(f"Toggle 'enabled' -> {self.enabled}")

    def set_theme(self, theme: str):
        with self.lock:
            self.theme = theme
            logger.info(f"Theme changed -> {self.theme}")
            # Update the icon color to reflect theme
            if theme == "Blue":
                self.icon_color = (0, 128, 255)
            elif theme == "Green":
                self.icon_color = (0, 170, 0)
            elif theme == "Purple":
                self.icon_color = (128, 0, 200)

    def increment(self):
        with self.lock:
            self.counter += 1
            logger.info(f"Counter -> {self.counter}")

    def snapshot(self) -> StateSnapshot:
        with self.lock:
            return StateSnapshot(
                enabled=self.enabled,
                theme=self.theme,
                counter=self.counter,
                icon_color=self.icon_color,
            )


state = TutorialState()


# --------------------------
# Menu handlers (actions)
# --------------------------
def on_show_notification(icon: pystray._base.Icon, item: Item):
    """
    Show a desktop notification via pystray's notify (where supported).
    On some Linux DEs this uses libnotify over DBus.
    """
    try:
        icon.notify(
            title="pystray tutorial",
            message=f"Hello at {datetime.now().strftime('%H:%M:%S')}",
        )
        logger.info("Notification sent")
    except Exception as e:
        logger.exception(f"Failed to show notification: {e}")


def on_toggle_enabled(icon: pystray._base.Icon, item: Item):
    state.toggle_enabled()
    # Update title to reflect state
    snap = state.snapshot()
    icon.title = f"pystray tutorial (Enabled: {snap.enabled})"
    icon.update_menu()  # update checked state immediately


def on_open_url(icon: pystray._base.Icon, item: Item):
    url = "https://github.com/moses-palmer/pystray"
    webbrowser.open(url)
    logger.info(f"Opened {url}")


def on_change_theme(icon: pystray._base.Icon, item: Item, theme_name: str):
    state.set_theme(theme_name)
    # Update icon image to reflect theme color
    snap = state.snapshot()
    icon.icon = make_icon(64, snap.icon_color)
    icon.update_menu()


def on_increment(icon: pystray._base.Icon, item: Item):
    state.increment()
    # Dynamic menu reflects counter via callable menu
    icon.update_menu()


def on_refresh_menu(icon: pystray._base.Icon, item: Item):
    """
    Demonstrate rebuilding the entire menu at runtime.
    """
    logger.info("Rebuilding menu on demand")
    icon.menu = build_menu(dynamic=True)
    icon.update_menu()


def on_pause_background(icon: pystray._base.Icon, item: Item):
    """
    Pause/resume the background worker thread via the toggle.
    """
    state.toggle_enabled()
    icon.update_menu()


def on_quit(icon: pystray._base.Icon, item: Item):
    """
    Stop background work and remove the icon.
    Note: icon.stop removes the tray icon and ends the main loop.
    """
    logger.info("Quit requested")
    state.running = False
    # Allow background thread to observe running=False quickly
    icon.visible = False
    icon.stop()


# --------------------------
# Dynamic menu builder
# --------------------------
def dynamic_section() -> Iterable[Item]:
    """
    This is a callable menu section. It is re-evaluated when the menu is opened.
    Useful for showing live values, ephemeral actions, or refreshed sub-menus.
    """
    snap = state.snapshot()
    yield Item(f"Counter: {snap.counter}", lambda i, it: None, enabled=False)
    yield Item("Increment counter", on_increment)
    yield Item("---", None)  # separator example
    yield Item(
        f"Enabled is {'ON' if snap.enabled else 'OFF'}",
        lambda i, it: None,
        enabled=False,
    )
    yield Item("Refresh menu (rebuild)", on_refresh_menu)


def build_menu(dynamic: bool = False) -> Menu:
    """
    Compose a menu showcasing:
    - Simple action items
    - Toggle (checked/unchecked)
    - Radio group
    - Submenu
    - Dynamic items via callable
    - Separator lines
    """
    snap = state.snapshot()

    # Toggle item demonstrates checked state and on_click handler
    toggle_item = Item(
        "Enabled",
        on_toggle_enabled,
        checked=lambda item: state.snapshot().enabled,
    )

    # Radio group: only one selected. We bind closures with theme value captured.
    def radio_item(label: str) -> Item:
        def action(icon, item):
            on_change_theme(icon, item, label)

        def is_checked(item):
            return state.snapshot().theme == label

        return Item(
            label,
            action,
            radio=True,
            checked=is_checked,
        )

    theme_group = (
        radio_item("Blue"),
        radio_item("Green"),
        radio_item("Purple"),
    )

    # Submenu example
    submenu = Item(
        "More actions",
        Menu(
            Item("Open pystray docs", on_open_url),
            Item("Show notification", on_show_notification),
        ),
    )

    # Optional dynamic section
    # Make the dynamic section discoverable at startup by providing a submenu
    # that contains an action to rebuild the menu with dynamic=True.
    dyn = (
        Item("Live info", Menu(dynamic_section))
        if dynamic
        else Item(
            "Live info",
            Menu(
                Item("Enable live info (rebuild menu)", on_refresh_menu),
                Item("---", None),
                Item(
                    "Hint: After enabling, reopen this submenu to see live values.",
                    lambda i, it: None,
                    enabled=False,
                ),
            ),
        )
    )

    return Menu(
        Item("Increment counter", on_increment, default=True),
        toggle_item,
        Item("Theme", Menu(*theme_group)),
        submenu,
        dyn,
        Item("---", None),
        Item(
            "Pause/Resume background",
            on_pause_background,
            checked=lambda i: state.snapshot().enabled,
        ),
        Item("Quit", on_quit),
    )


# --------------------------
# Background worker (thread)
# --------------------------
def background_worker(icon: pystray._base.Icon):
    """
    Demonstrates interacting with the icon from a worker thread.
    Use icon.update to marshal UI changes safely across backends.
    """
    logger.info("Background worker started")
    dots = ""
    while state.running:
        time.sleep(1.0)
        snap = state.snapshot()
        if snap.enabled:
            dots = (dots + ".")[-3:]
            title = f"pystray tutorial{dots}"

            # Safe cross-thread updates: mutate within a single update call
            def apply_update(ic: pystray._base.Icon):
                ic.title = title

            try:
                icon.update(apply_update)
            except Exception as e:
                logger.debug(f"Icon update failed (may be closing): {e}")
    logger.info("Background worker stopped")


# --------------------------
# Main entry point
# --------------------------
def main():
    logger.remove()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.add(sys.stderr, level=log_level, enqueue=False)

    snap = state.snapshot()
    icon_image = make_icon(64, snap.icon_color)
    menu = build_menu(dynamic=False)

    icon = pystray.Icon(
        name="pystray_tutorial",
        title="pystray tutorial",
        icon=icon_image,
        menu=menu,
    )

    # Start a background thread that updates title and demonstrates thread-safe updates
    worker = threading.Thread(target=background_worker, args=(icon,), daemon=True)
    worker.start()

    # Run the icon event loop (blocking). Use Ctrl+C in terminal to interrupt.
    try:
        logger.info(
            "Starting tray icon (backend: {})".format(os.environ.get("PYSTRAY_BACKEND"))
        )
        icon.run()  # blocks until icon.stop() or app quit
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down...")
        state.running = False
        try:
            icon.visible = False
            icon.stop()
        except Exception:
            pass
    finally:
        # Ensure the worker terminates
        state.running = False
        worker.join(timeout=2.0)
        logger.info("Exited cleanly")


if __name__ == "__main__":
    main()
