import os
import subprocess
import sys
from typing import Tuple

from PIL import Image, ImageDraw

from voicetype.assets.imgs import GREEN_BG_MIC, YELLOW_BG_MIC

# Valid values: 'gtk', 'appindicator', 'xorg', 'dummy' (fallback/test)
os.environ.setdefault("PYSTRAY_BACKEND", "gtk")

import pystray
from pystray import Menu
from pystray import MenuItem as Item


def _load_tray_image() -> Image.Image:
    """
    Load the mic.png asset for the tray icon. Falls back to the drawn icon if
    the asset is missing or fails to load.
    """
    try:
        img = Image.open(YELLOW_BG_MIC).convert("RGBA")
        return img
    except Exception:
        # Fallback to the programmatic icon to avoid crashing the tray.
        return _backup_mic_icon()


# State and callbacks
_is_listening = False


def _toggle_listening(icon: pystray._base.Icon, item: Item):
    global _is_listening
    _is_listening = not _is_listening
    # TODO: Wire these into your actual start/stop logic if available.
    # For now these are stubs to be connected to your hotkey/listener controller.
    if _is_listening:
        # start_listening()
        pass
    else:
        # stop_listening()
        pass
    # Update menu text dynamically by rebuilding menu
    icon.menu = _build_menu()
    icon.update_menu()


def _open_logs(icon: pystray._base.Icon, item: Item):
    # Attempt to open the error log in the system editor/viewer
    log_path = os.path.join(os.path.dirname(__file__), "error_log.txt")
    if not os.path.exists(log_path):
        # If absent, create empty file so the opener still works
        try:
            with open(log_path, "a", encoding="utf-8"):
                pass
        except Exception:
            return
    try:
        if sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", log_path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", log_path])
        elif os.name == "nt":
            os.startfile(log_path)  # type: ignore[attr-defined]
    except Exception:
        # Silently ignore open errors in tray context
        pass


def _quit(icon: pystray._base.Icon, item: Item):
    icon.stop()


def _build_menu() -> Menu:
    label = "Stop Listening" if _is_listening else "Start Listening"
    return Menu(
        Item(label, _toggle_listening, default=True),
        Item("Open Logs", _open_logs),
        Item("Quit", _quit),
    )


tray_icon = pystray.Icon(
    name="voicetype_tray",
    title="VoiceType",
    icon=_load_tray_image(),
    menu=_build_menu(),
)


def set_ready_icon():
    """
    Switch the tray icon to the GREEN background microphone to indicate
    the local model has loaded and the app is ready.
    Safe to call from background threads.
    """
    try:
        img = Image.open(GREEN_BG_MIC).convert("RGBA")
    except Exception:
        # If green asset missing, fall back to a green backup icon
        img = _backup_mic_icon(color=(0, 180, 0))

    try:
        tray_icon.icon = img
        try:
            tray_icon.update_icon()
        except Exception:
            pass
    except Exception:
        pass


def _backup_mic_icon(
    size: int = 64,
    color: Tuple[int, int, int] = (0, 128, 255),
    fg: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    """
    Render a crisp, scalable microphone icon suitable for a tray.
    - Circular badge background
    - Larger, high-contrast microphone glyph that fills more of the badge
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Badge background (slightly thinner padding to give more room to the glyph)
    pad = max(2, size // 20)
    d.ellipse(
        [pad, pad, size - pad, size - pad],
        fill=color,
        outline=(20, 20, 20, 220),
        width=max(1, size // 36),
    )

    # Microphone body proportions (increase relative size)
    cx, cy = size // 2, size // 2
    mic_w = max(6, (size * 3) // 10)
    mic_h = max(10, (size * 11) // 20)
    body_top = cy - (mic_h * 4) // 7
    body_bottom = cy + (mic_h * 1) // 5
    body_left = cx - mic_w // 2
    body_right = cx + mic_w // 2
    radius = mic_w // 2

    top_ellipse = [body_left, body_top, body_right, body_top + mic_w]
    d.ellipse(top_ellipse, fill=fg + (255,), outline=fg + (255,))
    d.rectangle(
        [body_left, body_top + radius, body_right, body_bottom],
        fill=fg + (255,),
        outline=fg + (255,),
    )

    holder_w = mic_w + max(6, size // 16)
    holder_top = body_bottom + max(1, size // 80)
    arc_box = [
        cx - holder_w // 2,
        holder_top - holder_w // 2,
        cx + holder_w // 2,
        holder_top + holder_w // 2,
    ]
    d.arc(arc_box, start=200, end=340, fill=fg + (255,), width=max(2, size // 18))

    stem_h = max(4, size // 10)
    stem_w = max(3, size // 20)
    stem_top = holder_top + max(1, size // 80)
    d.rectangle(
        [cx - stem_w // 2, stem_top, cx + stem_w // 2, stem_top + stem_h],
        fill=fg + (255,),
    )
    base_w = max(mic_w, (size * 2) // 5)
    base_h = max(3, size // 22)
    base_top = stem_top + stem_h + max(1, size // 80)
    d.rectangle(
        [cx - base_w // 2, base_top, cx + base_w // 2, base_top + base_h],
        fill=fg + (255,),
    )

    return img
