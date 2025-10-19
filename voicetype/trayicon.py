import os
import subprocess
import sys
import threading
from typing import Optional, Tuple

from PIL import Image, ImageDraw

# Valid values: 'gtk', 'appindicator', 'xorg', 'dummy' (fallback/test)
if sys.platform == "linux":
    os.environ.setdefault("PYSTRAY_BACKEND", "gtk")

import pystray
from pystray import Menu
from pystray import MenuItem as Item

from voicetype.app_context import AppContext
from voicetype.assets.imgs import YELLOW_BG_MIC
from voicetype.state import State


def _load_tray_image() -> Image.Image:
    try:
        img = Image.open(YELLOW_BG_MIC).convert("RGBA")
        return img
    except Exception:
        return _backup_mic_icon()


def _desaturate_to_grayscale(img: Image.Image) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    r, g, b, a = img.split()
    gray = Image.merge("RGB", (r, g, b)).convert("L")
    gray_rgb = Image.merge("RGBA", (gray, gray, gray, a))
    return gray_rgb


def _apply_enabled_icon(icon: pystray.Icon):
    try:
        img = create_mic_icon_variant(circle_color="green", alpha=255)
        icon.icon = img
        try:
            icon.update_icon()
        except Exception:
            pass
    except Exception:
        pass


def _apply_disabled_icon(icon: pystray.Icon):
    try:
        try:
            base = Image.open(YELLOW_BG_MIC).convert("RGBA")
        except Exception:
            base = _backup_mic_icon()
        base = _desaturate_to_grayscale(base)
        img = _add_status_circle(base, circle_color="gray", alpha=255)
        icon.icon = img
        try:
            icon.update_icon()
        except Exception:
            pass
    except Exception:
        pass


def _open_logs(icon: pystray._base.Icon, item: Item):
    log_path = os.path.join(os.path.dirname(__file__), "error_log.txt")
    if not os.path.exists(log_path):
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
        pass


def _quit(icon: pystray._base.Icon, item: Item):
    icon.stop()


def _build_menu(ctx: AppContext, icon: pystray.Icon) -> Menu:
    def _toggle_enabled(_icon: pystray._base.Icon, _item: Item):
        # Thread-safe toggling via State
        is_enabled = ctx.state.state != State.IDLE
        if is_enabled:
            ctx.state.state = State.IDLE
            _apply_disabled_icon(icon)
        else:
            ctx.state.state = State.LISTENING
            _apply_enabled_icon(icon)
        _icon.menu = _build_menu(ctx, icon)
        _icon.update_menu()

    is_enabled = ctx.state.state != State.IDLE
    enable_label = "Disable" if is_enabled else "Enable"

    return Menu(
        Item(enable_label, _toggle_enabled, default=True),
        Item("Open Logs", _open_logs),
        Item("Quit", _quit),
    )


def set_error_icon(icon: pystray.Icon):
    try:
        img = Image.open(YELLOW_BG_MIC).convert("RGBA")
    except Exception:
        img = _backup_mic_icon(color=(180, 180, 0))

    try:
        w, h = img.size
        draw = ImageDraw.Draw(img)
        stroke = max(2, min(w, h) // 10)
        margin = max(4, min(w, h) // 8)
        color = (220, 30, 30, 255)
        draw.line(
            [(margin, margin), (w - margin, h - margin)], fill=color, width=stroke
        )
        draw.line(
            [(w - margin, margin), (margin, h - margin)], fill=color, width=stroke
        )
    except Exception:
        pass

    try:
        icon.icon = img
        try:
            icon.update_icon()
        except Exception:
            pass
    except Exception:
        pass


def _add_status_circle(
    base_img: Image.Image, circle_color: str = "green", alpha: int = 255
) -> Image.Image:
    img = base_img.copy()
    if alpha < 255:
        img.putalpha(alpha)

    w, h = img.size
    draw = ImageDraw.Draw(img)

    circle_size = max(12, min(w, h) // 3)
    margin = max(2, min(w, h) // 25)

    circle_x = w - circle_size + margin
    circle_y = h - circle_size + margin

    color_map = {
        "green": (40, 200, 40, 255),
        "yellow": (255, 215, 0, 255),
        "red": (220, 30, 30, 255),
        "gray": (128, 128, 128, 255),
    }
    fill_color = color_map.get(circle_color, color_map["gray"])

    draw.ellipse(
        [circle_x, circle_y, circle_x + circle_size, circle_y + circle_size],
        fill=fill_color,
        outline=(0, 0, 0, 180),
        width=max(1, circle_size // 8),
    )
    return img


def create_mic_icon_variant(circle_color: str = None, alpha: int = 255) -> Image.Image:
    try:
        base_img = Image.open(YELLOW_BG_MIC).convert("RGBA")
    except Exception:
        base_img = _backup_mic_icon()

    if alpha < 255:
        img_with_alpha = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
        img_with_alpha.paste(base_img, (0, 0))
        pixels = img_with_alpha.load()
        width, height = img_with_alpha.size
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if a > 0:
                    pixels[x, y] = (r, g, b, min(a, alpha))
        base_img = img_with_alpha

    if circle_color:
        base_img = _add_status_circle(base_img, circle_color, 255)

    return base_img


def _backup_mic_icon(
    size: int = 64,
    color: Tuple[int, int, int] = (0, 128, 255),
    fg: Tuple[int, int, int] = (255, 255, 255),
) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = max(2, size // 20)
    d.ellipse(
        [pad, pad, size - pad, size - pad],
        fill=color,
        outline=(20, 20, 20, 220),
        width=max(1, size // 36),
    )

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


class TrayIconController:
    """Wrapper for pystray.Icon that implements the IconController protocol.

    This class adapts the existing tray icon to the IconController interface
    required by the pipeline system.
    """

    def __init__(self, icon: pystray.Icon):
        """Initialize the controller with a pystray Icon instance.

        Args:
            icon: The pystray.Icon instance to control
        """
        self.icon = icon
        self._flashing = False
        self._flash_thread: Optional[threading.Thread] = None
        self._stop_flash = threading.Event()

    def set_icon(self, state: str, duration: Optional[float] = None) -> None:
        """Set the system tray icon to a specific state.

        Args:
            state: Icon state ("idle", "recording", "processing", "error")
            duration: Optional duration in seconds before reverting (not implemented)
        """
        # Stop any flashing when explicitly setting icon
        if self._flashing:
            self.stop_flashing()

        try:
            if state == "idle":
                _apply_enabled_icon(self.icon)
            elif state == "recording":
                img = create_mic_icon_variant(circle_color="red", alpha=255)
                self.icon.icon = img
                try:
                    self.icon.update_icon()
                except Exception:
                    pass
            elif state == "processing":
                img = create_mic_icon_variant(circle_color="yellow", alpha=255)
                self.icon.icon = img
                try:
                    self.icon.update_icon()
                except Exception:
                    pass
            elif state == "error":
                set_error_icon(self.icon)
            elif state == "disabled":
                _apply_disabled_icon(self.icon)
        except Exception:
            # Silently fail on icon updates to avoid breaking pipeline
            pass

    def start_flashing(self, state: str) -> None:
        """Start flashing the icon in the specified state.

        Args:
            state: Icon state to flash (e.g., "recording")
        """
        if self._flashing:
            self.stop_flashing()

        self._flashing = True
        self._stop_flash.clear()

        def flash_loop():
            """Toggle between state and dimmed version."""
            visible = True
            while not self._stop_flash.is_set():
                try:
                    if state == "recording":
                        if visible:
                            img = create_mic_icon_variant(circle_color="red", alpha=255)
                        else:
                            img = create_mic_icon_variant(circle_color="red", alpha=128)
                    elif state == "processing":
                        if visible:
                            img = create_mic_icon_variant(
                                circle_color="yellow", alpha=255
                            )
                        else:
                            img = create_mic_icon_variant(
                                circle_color="yellow", alpha=128
                            )
                    else:
                        # Default to idle for unknown states
                        if visible:
                            img = create_mic_icon_variant(
                                circle_color="green", alpha=255
                            )
                        else:
                            img = create_mic_icon_variant(
                                circle_color="green", alpha=128
                            )

                    self.icon.icon = img
                    try:
                        self.icon.update_icon()
                    except Exception:
                        pass

                    visible = not visible
                    self._stop_flash.wait(0.5)  # Flash every 0.5 seconds
                except Exception:
                    break

        self._flash_thread = threading.Thread(target=flash_loop, daemon=True)
        self._flash_thread.start()

    def stop_flashing(self) -> None:
        """Stop flashing and return to the current non-flashing state."""
        if self._flashing:
            self._flashing = False
            self._stop_flash.set()
            if self._flash_thread:
                self._flash_thread.join(timeout=1.0)
                self._flash_thread = None


def create_tray(ctx: AppContext) -> pystray.Icon:
    """
    Create a tray icon bound to the given AppContext. No import-time side effects.
    """
    icon = pystray.Icon(
        name="voicetype_tray",
        title="VoiceType",
        icon=_load_tray_image(),
        menu=_build_menu(ctx, icon=None),  # temporary, will be replaced below
    )
    # finalize menu with live icon reference
    icon.menu = _build_menu(ctx, icon)

    # Initialize icon appearance according to enabled state
    try:
        is_enabled = ctx.state.state != State.IDLE
        if is_enabled:
            _apply_enabled_icon(icon)
        else:
            _apply_disabled_icon(icon)
    except Exception:
        pass

    return icon
