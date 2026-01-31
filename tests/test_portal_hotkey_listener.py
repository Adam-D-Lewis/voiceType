"""Tests for the Portal hotkey listener (Wayland GlobalShortcuts)."""

from unittest.mock import MagicMock, patch

import pytest


class TestPortalHotkeyListener:
    """Tests for PortalHotkeyListener class."""

    def test_import_portal_listener(self):
        """Test that the portal listener can be imported."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
            is_portal_available,
        )

        assert PortalHotkeyListener is not None
        assert callable(is_portal_available)

    def test_portal_listener_initialization(self):
        """Test PortalHotkeyListener initializes correctly."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        press_callback = MagicMock()
        release_callback = MagicMock()

        listener = PortalHotkeyListener(
            on_hotkey_press=press_callback,
            on_hotkey_release=release_callback,
        )

        assert listener.on_hotkey_press is press_callback
        assert listener.on_hotkey_release is release_callback
        assert listener._running is False
        assert listener._session_handle is None

    def test_hotkey_format_conversion_single_key(self):
        """Test conversion of single special keys from pynput to portal format."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        listener = PortalHotkeyListener()

        # Test single key conversions
        assert listener._convert_hotkey_format("<pause>") == "Pause"
        assert listener._convert_hotkey_format("<ctrl>") == "Control"
        assert listener._convert_hotkey_format("<alt>") == "Alt"
        assert listener._convert_hotkey_format("<shift>") == "Shift"
        assert listener._convert_hotkey_format("<f1>") == "F1"
        assert listener._convert_hotkey_format("<f12>") == "F12"
        assert listener._convert_hotkey_format("<enter>") == "Return"
        assert listener._convert_hotkey_format("<esc>") == "Escape"

    def test_hotkey_format_conversion_combinations(self):
        """Test conversion of hotkey combinations from pynput to portal format."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        listener = PortalHotkeyListener()

        # Test combinations
        assert listener._convert_hotkey_format("<ctrl>+<alt>+r") == "Control+Alt+R"
        assert listener._convert_hotkey_format("<shift>+a") == "Shift+A"
        assert (
            listener._convert_hotkey_format("<ctrl>+<shift>+<alt>+x")
            == "Control+Shift+Alt+X"
        )

    def test_hotkey_format_passthrough(self):
        """Test that portal format hotkeys pass through unchanged."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        listener = PortalHotkeyListener()

        # Already in portal format - should pass through
        assert listener._convert_hotkey_format("Pause") == "Pause"
        assert listener._convert_hotkey_format("Control+Alt+R") == "Control+Alt+R"

    def test_set_hotkey(self):
        """Test set_hotkey stores the hotkey correctly."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        listener = PortalHotkeyListener()
        listener.set_hotkey("<pause>")

        assert "voicetype-0-pause" in listener._shortcut_id_to_hotkey
        assert listener._shortcut_id_to_hotkey["voicetype-0-pause"] == "<pause>"
        assert listener._hotkey_triggers["<pause>"] == "Pause"

    def test_add_multiple_hotkeys(self):
        """Test adding multiple hotkeys."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        listener = PortalHotkeyListener()
        listener.add_hotkey("<pause>")
        listener.add_hotkey("<f12>")

        assert len(listener._shortcut_id_to_hotkey) == 2
        assert listener._shortcut_id_to_hotkey["voicetype-0-pause"] == "<pause>"
        assert listener._shortcut_id_to_hotkey["voicetype-1-f12"] == "<f12>"

    def test_clear_hotkeys(self):
        """Test clearing all hotkeys."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        listener = PortalHotkeyListener()
        listener.add_hotkey("<pause>")
        listener.add_hotkey("<f12>")
        listener.clear_hotkeys()

        assert len(listener._shortcut_id_to_hotkey) == 0
        assert len(listener._hotkey_triggers) == 0

    def test_shortcut_activated_callback(self):
        """Test that shortcut activation triggers the press callback with hotkey string."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        press_callback = MagicMock()
        listener = PortalHotkeyListener(on_hotkey_press=press_callback)
        listener.add_hotkey("<pause>")

        # Simulate shortcut activation
        listener._on_shortcut_activated(
            session_handle="/test/session",
            shortcut_id="voicetype-0-pause",
            timestamp=12345,
            options={},
        )

        press_callback.assert_called_once_with("<pause>")

    def test_shortcut_deactivated_callback(self):
        """Test that shortcut deactivation triggers the release callback with hotkey string."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        release_callback = MagicMock()
        listener = PortalHotkeyListener(on_hotkey_release=release_callback)
        listener.add_hotkey("<pause>")

        # Must first simulate activation before deactivation
        listener._on_shortcut_activated(
            session_handle="/test/session",
            shortcut_id="voicetype-0-pause",
            timestamp=12345,
            options={},
        )

        listener._on_shortcut_deactivated(
            session_handle="/test/session",
            shortcut_id="voicetype-0-pause",
            timestamp=12346,
            options={},
        )

        release_callback.assert_called_once_with("<pause>")

    def test_multiple_hotkeys_activate_independently(self):
        """Test that multiple hotkeys fire independently."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        press_callback = MagicMock()
        listener = PortalHotkeyListener(on_hotkey_press=press_callback)
        listener.add_hotkey("<pause>")
        listener.add_hotkey("<f12>")

        listener._on_shortcut_activated(
            session_handle="/test/session",
            shortcut_id="voicetype-1-f12",
            timestamp=12345,
            options={},
        )

        press_callback.assert_called_once_with("<f12>")

    def test_wrong_shortcut_id_ignored(self):
        """Test that callbacks for wrong shortcut IDs are ignored."""
        from voicetype.hotkey_listener.portal_hotkey_listener import (
            PortalHotkeyListener,
        )

        press_callback = MagicMock()
        release_callback = MagicMock()
        listener = PortalHotkeyListener(
            on_hotkey_press=press_callback,
            on_hotkey_release=release_callback,
        )
        listener.add_hotkey("<pause>")

        # Simulate shortcut with wrong ID
        listener._on_shortcut_activated(
            session_handle="/test/session",
            shortcut_id="wrong-id",
            timestamp=12345,
            options={},
        )
        listener._on_shortcut_deactivated(
            session_handle="/test/session",
            shortcut_id="wrong-id",
            timestamp=12346,
            options={},
        )

        press_callback.assert_not_called()
        release_callback.assert_not_called()


class TestCreateHotkeyListener:
    """Tests for the create_hotkey_listener factory function."""

    def test_factory_function_import(self):
        """Test that the factory function can be imported."""
        from voicetype.hotkey_listener import create_hotkey_listener

        assert callable(create_hotkey_listener)

    @patch.dict("os.environ", {"WAYLAND_DISPLAY": ""}, clear=False)
    @patch("voicetype.hotkey_listener.portal_hotkey_listener.is_portal_available")
    def test_factory_returns_pynput_when_portal_unavailable(
        self, mock_portal_available
    ):
        """Test factory returns PynputHotkeyListener when portal is unavailable."""
        mock_portal_available.return_value = False

        import os

        from voicetype.hotkey_listener import create_hotkey_listener
        from voicetype.hotkey_listener.pynput_hotkey_listener import (
            PynputHotkeyListener,
        )

        original_wayland = os.environ.get("WAYLAND_DISPLAY")
        original_session = os.environ.get("XDG_SESSION_TYPE")

        try:
            os.environ.pop("WAYLAND_DISPLAY", None)
            os.environ["XDG_SESSION_TYPE"] = "x11"

            listener = create_hotkey_listener()
            assert isinstance(listener, PynputHotkeyListener)
        finally:
            if original_wayland:
                os.environ["WAYLAND_DISPLAY"] = original_wayland
            if original_session:
                os.environ["XDG_SESSION_TYPE"] = original_session


class TestIsPortalAvailable:
    """Tests for is_portal_available function."""

    def test_is_portal_available_returns_bool(self):
        """Test that is_portal_available returns a boolean."""
        from voicetype.hotkey_listener.portal_hotkey_listener import is_portal_available

        result = is_portal_available()
        assert isinstance(result, bool)
