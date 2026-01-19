"""Tests for the platform_detection module."""

from unittest.mock import MagicMock, patch

import pytest

from voicetype.platform_detection import (
    WLROOTS_COMPOSITORS,
    CompositorType,
    clear_cache,
    get_compositor_name,
    get_compositor_type,
    get_display_server,
    get_platform_info,
    is_remote_desktop_portal_available,
    is_wayland,
    is_x11,
    supports_is,
)


@pytest.fixture(autouse=True)
def clear_detection_cache():
    """Clear detection caches before and after each test."""
    clear_cache()
    yield
    clear_cache()


class TestDisplayServerDetection:
    """Tests for display server detection functions."""

    def test_wayland_via_xdg_session_type(self):
        """Test Wayland detection via XDG_SESSION_TYPE."""
        with patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}, clear=True):
            clear_cache()
            assert get_display_server() == "wayland"
            assert is_wayland() is True
            assert is_x11() is False

    def test_x11_via_xdg_session_type(self):
        """Test X11 detection via XDG_SESSION_TYPE."""
        with patch.dict("os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=True):
            clear_cache()
            assert get_display_server() == "x11"
            assert is_wayland() is False
            assert is_x11() is True

    def test_wayland_via_wayland_display(self):
        """Test Wayland detection via WAYLAND_DISPLAY environment variable."""
        with patch.dict("os.environ", {"WAYLAND_DISPLAY": "wayland-0"}, clear=True):
            clear_cache()
            assert get_display_server() == "wayland"
            assert is_wayland() is True

    def test_x11_via_display(self):
        """Test X11 detection via DISPLAY environment variable."""
        with patch.dict("os.environ", {"DISPLAY": ":0"}, clear=True):
            clear_cache()
            assert get_display_server() == "x11"
            assert is_x11() is True

    def test_xdg_session_type_takes_priority(self):
        """Test that XDG_SESSION_TYPE takes priority over other variables."""
        env = {
            "XDG_SESSION_TYPE": "x11",
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": ":0",
        }
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            # XDG_SESSION_TYPE should win even though WAYLAND_DISPLAY is set
            assert get_display_server() == "x11"

    def test_unknown_when_no_env_vars(self):
        """Test unknown when no relevant environment variables are set."""
        with patch.dict("os.environ", {}, clear=True):
            clear_cache()
            assert get_display_server() == "unknown"
            assert is_wayland() is False
            assert is_x11() is False


class TestCompositorDetection:
    """Tests for compositor detection functions."""

    def test_gnome_detection(self):
        """Test GNOME compositor detection."""
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "GNOME"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "gnome"
            assert get_compositor_type() == CompositorType.GNOME

    def test_gnome_detection_with_prefix(self):
        """Test GNOME detection when XDG_CURRENT_DESKTOP has prefix (e.g., ubuntu:GNOME)."""
        with patch.dict(
            "os.environ", {"XDG_CURRENT_DESKTOP": "ubuntu:GNOME"}, clear=True
        ):
            clear_cache()
            assert get_compositor_name() == "gnome"
            assert get_compositor_type() == CompositorType.GNOME

    def test_kde_detection(self):
        """Test KDE/Plasma compositor detection."""
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "KDE"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "kde"
            assert get_compositor_type() == CompositorType.KDE

    def test_plasma_detection(self):
        """Test Plasma variant detection."""
        with patch.dict(
            "os.environ", {"XDG_CURRENT_DESKTOP": "KDE:Plasma"}, clear=True
        ):
            clear_cache()
            assert get_compositor_name() == "plasma"
            assert get_compositor_type() == CompositorType.KDE

    def test_sway_detection_via_xdg(self):
        """Test Sway detection via XDG_CURRENT_DESKTOP."""
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "sway"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "sway"
            assert get_compositor_type() == CompositorType.WLROOTS

    def test_sway_detection_via_swaysock(self):
        """Test Sway detection via SWAYSOCK environment variable."""
        with patch.dict(
            "os.environ", {"SWAYSOCK": "/run/user/1000/sway-ipc.sock"}, clear=True
        ):
            clear_cache()
            assert get_compositor_name() == "sway"
            assert get_compositor_type() == CompositorType.WLROOTS

    def test_hyprland_detection_via_xdg(self):
        """Test Hyprland detection via XDG_CURRENT_DESKTOP."""
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "Hyprland"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "hyprland"
            assert get_compositor_type() == CompositorType.WLROOTS

    def test_hyprland_detection_via_signature(self):
        """Test Hyprland detection via HYPRLAND_INSTANCE_SIGNATURE."""
        with patch.dict(
            "os.environ", {"HYPRLAND_INSTANCE_SIGNATURE": "12345abc"}, clear=True
        ):
            clear_cache()
            assert get_compositor_name() == "hyprland"
            assert get_compositor_type() == CompositorType.WLROOTS

    def test_wayfire_detection(self):
        """Test Wayfire (wlroots) detection."""
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "wayfire"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "wayfire"
            assert get_compositor_type() == CompositorType.WLROOTS

    def test_river_detection(self):
        """Test River (wlroots) detection."""
        with patch.dict("os.environ", {"XDG_CURRENT_DESKTOP": "river"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "river"
            assert get_compositor_type() == CompositorType.WLROOTS

    def test_xdg_session_desktop_fallback(self):
        """Test fallback to XDG_SESSION_DESKTOP."""
        with patch.dict("os.environ", {"XDG_SESSION_DESKTOP": "gnome"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "gnome"
            assert get_compositor_type() == CompositorType.GNOME

    def test_desktop_session_fallback(self):
        """Test fallback to DESKTOP_SESSION."""
        with patch.dict("os.environ", {"DESKTOP_SESSION": "plasma"}, clear=True):
            clear_cache()
            assert get_compositor_name() == "plasma"
            assert get_compositor_type() == CompositorType.KDE

    def test_unknown_compositor(self):
        """Test unknown compositor when no env vars are set."""
        with patch.dict("os.environ", {}, clear=True):
            clear_cache()
            assert get_compositor_name() == ""
            assert get_compositor_type() == CompositorType.UNKNOWN

    def test_other_compositor(self):
        """Test OTHER type for unknown but present compositor."""
        with patch.dict(
            "os.environ", {"XDG_CURRENT_DESKTOP": "some-other-de"}, clear=True
        ):
            clear_cache()
            assert get_compositor_name() == "some-other-de"
            assert get_compositor_type() == CompositorType.OTHER


class TestWlrootsCompositorsList:
    """Tests for the wlroots compositors list."""

    def test_known_wlroots_compositors_in_list(self):
        """Test that known wlroots compositors are in the list."""
        known = ["sway", "hyprland", "wayfire", "river", "labwc", "dwl", "cage", "phoc"]
        for compositor in known:
            assert compositor in WLROOTS_COMPOSITORS, f"{compositor} should be in list"

    def test_gnome_not_in_wlroots_list(self):
        """Test that GNOME is not in wlroots list."""
        assert "gnome" not in WLROOTS_COMPOSITORS

    def test_kde_not_in_wlroots_list(self):
        """Test that KDE is not in wlroots list."""
        assert "kde" not in WLROOTS_COMPOSITORS
        assert "plasma" not in WLROOTS_COMPOSITORS


class TestISSupport:
    """Tests for IS (Extended Input Simulation) support detection."""

    def test_is_not_supported_on_x11(self):
        """Test that IS is not supported on X11."""
        with patch.dict("os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=True):
            clear_cache()
            assert supports_is() is False

    def test_is_not_supported_on_wlroots(self):
        """Test that IS is not supported on wlroots compositors."""
        env = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "sway"}
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            assert supports_is() is False

    def test_is_not_supported_on_hyprland(self):
        """Test that IS is not supported on Hyprland."""
        env = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"}
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            assert supports_is() is False

    @patch("voicetype.platform_detection.is_remote_desktop_portal_available")
    def test_is_supported_on_gnome_with_portal(self, mock_portal):
        """Test that IS is supported on GNOME when portal is available."""
        mock_portal.return_value = True
        env = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"}
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            # Need to clear the supports_is cache separately since we mocked the dep
            supports_is.cache_clear()
            assert supports_is() is True

    @patch("voicetype.platform_detection.is_remote_desktop_portal_available")
    def test_is_supported_on_kde_with_portal(self, mock_portal):
        """Test that IS is supported on KDE when portal is available."""
        mock_portal.return_value = True
        env = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "KDE"}
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            supports_is.cache_clear()
            assert supports_is() is True

    @patch("voicetype.platform_detection.is_remote_desktop_portal_available")
    def test_is_not_supported_on_gnome_without_portal(self, mock_portal):
        """Test that IS is not supported on GNOME when portal is unavailable."""
        mock_portal.return_value = False
        env = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"}
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            supports_is.cache_clear()
            assert supports_is() is False


class TestRemoteDesktopPortalDetection:
    """Tests for RemoteDesktop portal detection."""

    @patch("subprocess.run")
    def test_portal_available_via_dbus_send(self, mock_run):
        """Test portal detection via dbus-send."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"RemoteDesktop CreateSession"
        mock_run.return_value = mock_result

        clear_cache()
        result = is_remote_desktop_portal_available()
        assert result is True

    @patch("subprocess.run")
    def test_portal_not_available(self, mock_run):
        """Test portal not available."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = b"GlobalShortcuts"  # No RemoteDesktop
        mock_run.return_value = mock_result

        clear_cache()
        result = is_remote_desktop_portal_available()
        assert result is False

    @patch("subprocess.run")
    def test_portal_detection_handles_missing_tools(self, mock_run):
        """Test graceful handling when dbus-send and busctl are missing."""
        mock_run.side_effect = FileNotFoundError("dbus-send not found")

        clear_cache()
        result = is_remote_desktop_portal_available()
        assert result is False


class TestPlatformInfo:
    """Tests for the get_platform_info function."""

    def test_platform_info_returns_dict(self):
        """Test that get_platform_info returns a dictionary with expected keys."""
        env = {"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"}
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            info = get_platform_info()

            assert isinstance(info, dict)
            assert "display_server" in info
            assert "compositor_name" in info
            assert "compositor_type" in info
            assert "supports_is" in info
            assert "is_wayland" in info
            assert "is_x11" in info

    def test_platform_info_values(self):
        """Test that get_platform_info returns correct values."""
        env = {"XDG_SESSION_TYPE": "x11", "XDG_CURRENT_DESKTOP": "GNOME"}
        with patch.dict("os.environ", env, clear=True):
            clear_cache()
            info = get_platform_info()

            assert info["display_server"] == "x11"
            assert info["compositor_name"] == "gnome"
            assert info["compositor_type"] == "gnome"
            assert info["is_wayland"] is False
            assert info["is_x11"] is True


class TestCaching:
    """Tests for caching behavior."""

    def test_detection_is_cached(self):
        """Test that detection results are cached."""
        with patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}, clear=True):
            clear_cache()
            result1 = get_display_server()
            result2 = get_display_server()
            assert result1 == result2 == "wayland"

    def test_clear_cache_resets_detection(self):
        """Test that clear_cache allows re-detection."""
        with patch.dict("os.environ", {"XDG_SESSION_TYPE": "wayland"}, clear=True):
            clear_cache()
            result1 = get_display_server()
            assert result1 == "wayland"

        with patch.dict("os.environ", {"XDG_SESSION_TYPE": "x11"}, clear=True):
            # Without clearing cache, would still return wayland
            clear_cache()
            result2 = get_display_server()
            assert result2 == "x11"
