"""Tests for the system tray traces menu item."""

from pathlib import Path
from unittest.mock import MagicMock

from voicetype.app_context import AppContext
from voicetype.state import AppState
from voicetype.trayicon import _build_menu


def test_traces_menu_item_appears_when_telemetry_enabled():
    """Test that 'Open Traces' menu item appears when telemetry is enabled."""
    ctx = AppContext(
        state=AppState(),
        hotkey_listener=None,
        log_file_path=Path("/tmp/test.log"),
        telemetry_enabled=True,
        trace_file_path=Path("/tmp/traces.jsonl"),
    )

    # Create a mock icon
    icon = MagicMock()

    # Build the menu
    menu = _build_menu(ctx, icon)

    # Get menu item labels
    menu_labels = [str(item.text) for item in menu]

    # Verify that "Open Traces" is in the menu
    assert "Open Traces" in menu_labels
    # Verify menu structure
    assert len(menu_labels) == 4  # Enable/Disable, Open Logs, Open Traces, Quit


def test_traces_menu_item_absent_when_telemetry_disabled():
    """Test that 'Open Traces' menu item does not appear when telemetry is disabled."""
    ctx = AppContext(
        state=AppState(),
        hotkey_listener=None,
        log_file_path=Path("/tmp/test.log"),
        telemetry_enabled=False,
        trace_file_path=None,
    )

    # Create a mock icon
    icon = MagicMock()

    # Build the menu
    menu = _build_menu(ctx, icon)

    # Get menu item labels
    menu_labels = [str(item.text) for item in menu]

    # Verify that "Open Traces" is NOT in the menu
    assert "Open Traces" not in menu_labels
    # Verify menu structure
    assert len(menu_labels) == 3  # Enable/Disable, Open Logs, Quit


def test_traces_menu_item_absent_when_no_telemetry_field():
    """Test backward compatibility - menu works without telemetry_enabled field."""
    ctx = AppContext(
        state=AppState(),
        hotkey_listener=None,
        log_file_path=Path("/tmp/test.log"),
    )

    # Create a mock icon
    icon = MagicMock()

    # Build the menu
    menu = _build_menu(ctx, icon)

    # Get menu item labels
    menu_labels = [str(item.text) for item in menu]

    # Verify that "Open Traces" is NOT in the menu
    assert "Open Traces" not in menu_labels
    # Verify menu structure
    assert len(menu_labels) == 3  # Enable/Disable, Open Logs, Quit
