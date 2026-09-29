"""Tests for the tray's "Keyboard backend" submenu and the runtime override."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from voicetype.app_context import AppContext
from voicetype.pipeline import PipelineConfig
from voicetype.pipeline.stages import keyboard_backends
from voicetype.pipeline.stages.keyboard_backends import RemoteKeyboard
from voicetype.pipeline.stages.type_text import TypeText
from voicetype.state import AppState
from voicetype.trayicon import _build_menu


@pytest.fixture(autouse=True)
def reset_override(monkeypatch):
    keyboard_backends.set_backend_override(None)
    monkeypatch.setattr(
        keyboard_backends, "detect_auto_backend", lambda: ("eitype", "test")
    )
    yield
    keyboard_backends.set_backend_override(None)


def make_context(remote_enabled=True):
    pipeline_manager = MagicMock()
    pipeline_manager.pipelines = {
        "default": PipelineConfig(
            name="default",
            enabled=True,
            hotkey="<pause>",
            stages=[{"stage": "RecordAudio"}, {"stage": "TypeText"}],
        ),
        "remote": PipelineConfig(
            name="remote",
            enabled=True,
            hotkey="remote:main",
            stages=[{"stage": "TypeText", "keyboard_backend": "remote"}],
        ),
    }
    return AppContext(
        state=AppState(),
        hotkey_listener=None,
        pipeline_manager=pipeline_manager,
        log_file_path=Path("/tmp/test.log"),
        remote_enabled=remote_enabled,
    )


def backend_submenu(menu):
    items = [item for item in menu if str(item.text).startswith("Keyboard backend")]
    assert len(items) == 1
    return items[0]


def labels(submenu_item):
    return [str(item.text) for item in submenu_item.submenu]


def test_submenu_shows_each_pipelines_backend():
    item = backend_submenu(_build_menu(make_context(), MagicMock()))
    assert str(item.text) == "Keyboard backend"
    assert labels(item) == [
        "default: auto (eitype)",
        "remote: remote",
        "- - - -",
        "From settings",
        "auto (eitype)",
        "eitype",
        "wtype",
        "pynput",
        "remote",
    ]
    info = list(item.submenu)[:2]
    assert not any(line.enabled for line in info)


def test_from_settings_is_selected_by_default():
    item = backend_submenu(_build_menu(make_context(), MagicMock()))
    checked = [str(i.text) for i in item.submenu if i.checked]
    assert checked == ["From settings"]


def test_choosing_a_backend_overrides_every_pipeline():
    ctx, icon = make_context(), MagicMock()
    item = backend_submenu(_build_menu(ctx, icon))
    pynput_item = [i for i in item.submenu if str(i.text) == "pynput"][0]

    pynput_item(icon)

    assert keyboard_backends.get_backend_override() == "pynput"
    icon.update_menu.assert_called_once()
    rebuilt = backend_submenu(_build_menu(ctx, icon))
    assert str(rebuilt.text) == "Keyboard backend: pynput"
    assert labels(rebuilt)[:2] == ["default: pynput", "remote: pynput"]
    assert [str(i.text) for i in rebuilt.submenu if i.checked] == ["pynput"]


def test_from_settings_removes_the_override():
    keyboard_backends.set_backend_override("remote")
    ctx, icon = make_context(), MagicMock()
    item = backend_submenu(_build_menu(ctx, icon))
    [i for i in item.submenu if str(i.text) == "From settings"][0](icon)
    assert keyboard_backends.get_backend_override() is None


def test_remote_option_needs_remote_configured():
    ctx = make_context(remote_enabled=False)
    del ctx.pipeline_manager.pipelines["remote"]
    item = backend_submenu(_build_menu(ctx, MagicMock()))
    assert "remote" not in labels(item)


def test_no_submenu_without_typing_pipelines():
    ctx = make_context()
    ctx.pipeline_manager.pipelines = {}
    menu_labels = [str(item.text) for item in _build_menu(ctx, MagicMock())]
    assert not any(label.startswith("Keyboard backend") for label in menu_labels)


def test_type_text_uses_the_override():
    assert isinstance(TypeText({"keyboard_backend": "remote"}).backend, RemoteKeyboard)
    keyboard_backends.set_backend_override("remote")
    assert isinstance(TypeText({"keyboard_backend": "pynput"}).backend, RemoteKeyboard)


def test_invalid_override_is_rejected():
    with pytest.raises(ValueError, match="Valid options"):
        keyboard_backends.set_backend_override("typewriter")
