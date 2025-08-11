import os
import subprocess
import sys
from typing import Tuple

from PIL import Image, ImageDraw

from voicetype import globals
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


def _desaturate_to_grayscale(img: Image.Image) -> Image.Image:
    """
    Convert an RGBA image to grayscale while preserving alpha channel.
    """
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    # Split channels
    r, g, b, a = img.split()
    # Luma conversion
    gray = Image.merge("RGB", (r, g, b)).convert("L")
    # Rebuild RGBA with gray in all RGB channels
    gray_rgb = Image.merge("RGBA", (gray, gray, gray, a))
    return gray_rgb


def _apply_enabled_icon():
    """
    Show normal icon when enabled: base mic with green status circle.
    """
    try:
        img = create_mic_icon_variant(circle_color="green", alpha=255)
        tray_icon.icon = img
        try:
            tray_icon.update_icon()
        except Exception:
            pass
    except Exception:
        pass


def _apply_disabled_icon():
    """
    Show disabled icon: grayscale base at full opacity with a gray status circle.
    """
    try:
        try:
            base = Image.open(YELLOW_BG_MIC).convert("RGBA")
        except Exception:
            base = _backup_mic_icon()
        base = _desaturate_to_grayscale(base)
        img = _add_status_circle(base, circle_color="gray", alpha=255)
        tray_icon.icon = img
        try:
            tray_icon.update_icon()
        except Exception:
            pass
    except Exception:
        pass


def _toggle_enabled(icon: pystray._base.Icon, item: Item):
    """
    Toggle the global enabled/disabled state and update icon + menu.
    """
    globals.is_enabled = not globals.is_enabled
    if globals.is_enabled:
        _apply_enabled_icon()
        globals.hotkey_listener.start_listening()
    else:
        _apply_disabled_icon()
        globals.hotkey_listener.stop_listening()
    # Rebuild and refresh menu so label is dynamic
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
    # First menu item: Enable/Disable (dynamic label)
    enable_label = "Disable" if globals.is_enabled else "Enable"
    # Keep listening control as a secondary item with dynamic label
    listen_label = "Stop Listening" if globals.is_listening else "Start Listening"

    return Menu(
        Item(enable_label, _toggle_enabled, default=True),
        # Item(listen_label, _toggle_listening),
        Item("Open Logs", _open_logs),
        Item("Quit", _quit),
    )


def set_error_icon():
    """
    Switch the tray icon to the YELLOW background microphone with a red X overlay
    to indicate an error occurred during initialization or processing.
    Safe to call from background threads.
    """
    try:
        img = Image.open(YELLOW_BG_MIC).convert("RGBA")
    except Exception:
        # If yellow asset missing, fall back to a yellow backup icon
        img = _backup_mic_icon(color=(180, 180, 0))

    # Draw a red 'X' overlay to clearly indicate error
    try:
        w, h = img.size
        draw = ImageDraw.Draw(img)
        # Stroke width scales with icon size, clamped to visible range
        stroke = max(2, min(w, h) // 10)
        margin = max(4, min(w, h) // 8)  # keep X away from edges
        color = (220, 30, 30, 255)  # solid red
        # Two diagonal lines
        draw.line(
            [(margin, margin), (w - margin, h - margin)], fill=color, width=stroke
        )
        draw.line(
            [(w - margin, margin), (margin, h - margin)], fill=color, width=stroke
        )
    except Exception:
        # If drawing fails for any reason, proceed without overlay
        pass

    try:
        tray_icon.icon = img
        try:
            tray_icon.update_icon()
        except Exception:
            pass
    except Exception:
        pass


def _add_status_circle(
    base_img: Image.Image, circle_color: str = "green", alpha: int = 255
) -> Image.Image:
    """
    Add a status circle in the bottom right corner of the icon.

    Args:
        base_img: The base icon image
        circle_color: "green", "yellow", "red", or "gray"
        alpha: Alpha transparency for the entire image (0-255)
    """
    img = base_img.copy()

    # Apply alpha transparency to the entire image if requested
    if alpha < 255:
        img.putalpha(alpha)

    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Circle size and position (bottom right corner)
    circle_size = max(12, min(w, h) // 3)  # 1/3 of the smaller dimension
    margin = max(2, min(w, h) // 25)

    circle_x = w - circle_size + margin  # Move right (partially out of bounds)
    circle_y = h - circle_size + margin  # Move down (partially out of bounds)

    # Color mapping
    color_map = {
        "green": (40, 200, 40, 255),
        "yellow": (255, 215, 0, 255),
        "red": (220, 30, 30, 255),
        "gray": (128, 128, 128, 255),
    }

    fill_color = color_map.get(circle_color, color_map["gray"])

    # Draw the status circle with a subtle border
    draw.ellipse(
        [circle_x, circle_y, circle_x + circle_size, circle_y + circle_size],
        fill=fill_color,
        outline=(0, 0, 0, 180),
        width=max(1, circle_size // 8),
    )

    return img


def create_mic_icon_variant(circle_color: str = None, alpha: int = 255) -> Image.Image:
    """
    Create a microphone icon variant with optional status circle and transparency.

    Args:
        circle_color: "green", "yellow", "red", "gray", or None for no circle
        alpha: Alpha transparency for the background (0-255, where 255 is opaque)
    """
    try:
        base_img = Image.open(YELLOW_BG_MIC).convert("RGBA")
    except Exception:
        base_img = _backup_mic_icon()

    # Apply transparency to background if requested
    if alpha < 255:
        # Create a new image with the desired alpha
        img_with_alpha = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        # Blend the base image with transparency
        img_with_alpha.paste(base_img, (0, 0))
        pixels = img_with_alpha.load()
        width, height = img_with_alpha.size

        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a > 0:  # Only modify non-transparent pixels
                    pixels[x, y] = (r, g, b, min(a, alpha))

        base_img = img_with_alpha

    # Add status circle if requested
    if circle_color:
        base_img = _add_status_circle(
            base_img, circle_color, 255
        )  # Circle alpha handled separately

    return base_img


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


tray_icon = pystray.Icon(
    name="voicetype_tray",
    title="VoiceType",
    icon=_load_tray_image(),
    menu=_build_menu(),
)

# Initialize icon appearance according to default enabled state
try:
    if globals.is_enabled:
        _apply_enabled_icon()
    else:
        _apply_disabled_icon()
except Exception:
    pass

# set_error_icon()
