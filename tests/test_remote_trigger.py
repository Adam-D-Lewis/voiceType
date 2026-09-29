"""Tests for the remote trigger: TLS listener, remote keyboard backend, cancellation."""

import json
import shutil
import socket
import ssl
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest

from voicetype.hotkey_listener.remote_credentials import (
    TLS_NAME,
    RemoteCredentialsError,
    generate_credentials,
    load_token,
)
from voicetype.hotkey_listener.remote_hotkey_listener import (
    RemoteHotkeyListener,
    RemoteNotConnectedError,
    get_active_remote_listener,
    is_remote_hotkey,
)
from voicetype.install import _remote_pipeline_stages
from voicetype.pipeline import (
    STAGE_REGISTRY,
    HotkeyDispatcher,
    PipelineContext,
    PipelineManager,
    ResourceManager,
)
from voicetype.pipeline.stages.keyboard_backends.remote_backend import (
    RemoteKeyboard,
    to_hid_text,
)
from voicetype.settings import RemoteConfig, Settings


class MockIconController:
    def set_icon(self, state: str, duration: float = None):
        pass

    def start_flashing(self, state: str):
        pass

    def stop_flashing(self):
        pass


class Recorder:
    """Records hotkey callbacks; press returns `accept`."""

    def __init__(self):
        self.events = []
        self.accept = True
        self._changed = threading.Condition()

    def press(self, hotkey):
        self._add(("press", hotkey))
        return self.accept

    def release(self, hotkey):
        self._add(("release", hotkey))

    def cancel(self, hotkey):
        self._add(("cancel", hotkey))

    def _add(self, event):
        with self._changed:
            self.events.append(event)
            self._changed.notify_all()

    def wait_for(self, event, timeout=5.0) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: event in self.events, timeout)


class Client:
    """A minimal stand-in for the Pico."""

    def __init__(self, port: int, cert_file: Path):
        context = ssl.create_default_context(cafile=str(cert_file))
        raw = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.sock = context.wrap_socket(raw, server_hostname=TLS_NAME)
        self.reader = self.sock.makefile("rb")

    def send(self, **message):
        self.sock.sendall((json.dumps(message) + "\n").encode())

    def receive(self) -> Optional[dict]:
        """Next message, or None once the connection is closed."""
        try:
            line = self.reader.readline()
        except (ConnectionError, ssl.SSLError):
            return None
        return json.loads(line) if line else None

    def close(self):
        self.reader.close()
        self.sock.close()


@pytest.fixture(scope="module")
def credentials(tmp_path_factory):
    if shutil.which("openssl") is None:
        pytest.skip("needs the openssl command")
    directory = tmp_path_factory.mktemp("remote")
    cert, key, token = (
        directory / "cert.pem",
        directory / "key.pem",
        directory / "token",
    )
    generate_credentials(cert, key, token)
    return SimpleNamespace(cert=cert, key=key, token=token)


def make_config(credentials, **overrides) -> RemoteConfig:
    options = dict(
        enabled=True,
        host="127.0.0.1",
        port=0,
        cert_file=credentials.cert,
        key_file=credentials.key,
        token_file=credentials.token,
        press_timeout=0.5,
        idle_timeout=5.0,
    )
    options.update(overrides)
    return RemoteConfig(**options)


@pytest.fixture
def recorder():
    return Recorder()


@pytest.fixture
def listener(credentials, recorder):
    listener = RemoteHotkeyListener(
        make_config(credentials),
        on_hotkey_press=recorder.press,
        on_hotkey_release=recorder.release,
        on_hotkey_cancel=recorder.cancel,
    )
    listener.add_hotkey("remote:main", name="test")
    listener.start_listening()
    yield listener
    listener.stop_listening()


@pytest.fixture
def connect(credentials):
    """Connect clients to a listener, saying hello unless authenticate=False."""
    clients = []

    def _connect(listener, authenticate=True) -> Client:
        client = Client(listener.port, credentials.cert)
        clients.append(client)
        if authenticate:
            client.send(type="hello", token=load_token(credentials.token), name="t")
            assert client.receive() == {"type": "welcome", "version": 1}
        return client

    yield _connect
    for client in clients:
        client.close()


class TestRemoteHotkeyListener:
    def test_press_and_release_trigger_callbacks(self, listener, connect, recorder):
        client = connect(listener)
        client.send(type="down", button="main")
        assert client.receive() == {
            "type": "state",
            "button": "main",
            "state": "recording",
        }
        client.send(type="up", button="main")
        assert recorder.wait_for(("release", "remote:main"))
        assert recorder.events == [("press", "remote:main"), ("release", "remote:main")]

    def test_rejected_press_is_reported(self, listener, connect, recorder):
        recorder.accept = False
        client = connect(listener)
        client.send(type="down", button="main")
        assert client.receive()["state"] == "rejected"

    def test_unbound_button_is_rejected(self, listener, connect, recorder):
        client = connect(listener)
        client.send(type="down", button="other")
        assert client.receive() == {
            "type": "state",
            "button": "other",
            "state": "rejected",
        }
        assert recorder.events == []

    def test_ping(self, listener, connect):
        client = connect(listener)
        client.send(type="ping")
        assert client.receive() == {"type": "pong"}

    def test_bad_token_is_rejected(self, listener, connect, recorder):
        client = connect(listener, authenticate=False)
        client.send(type="hello", token="not-the-token")
        assert client.receive() == {"type": "error", "message": "bad token"}
        assert client.receive() is None

    def test_must_say_hello_first(self, listener, connect, recorder):
        client = connect(listener, authenticate=False)
        client.send(type="down", button="main")
        assert client.receive()["type"] == "error"
        assert recorder.events == []

    def test_untrusted_certificate_is_refused(self, listener, tmp_path):
        other = SimpleNamespace(
            cert=tmp_path / "c.pem", key=tmp_path / "k.pem", token=tmp_path / "t"
        )
        generate_credentials(other.cert, other.key, other.token)
        with pytest.raises(ssl.SSLCertVerificationError):
            Client(listener.port, other.cert)

    def test_send_text_reaches_device(self, listener, connect):
        client = connect(listener)
        listener.send_text("hello world")
        assert client.receive() == {"type": "text", "text": "hello world"}

    def test_send_text_without_device_raises(self, listener):
        with pytest.raises(RemoteNotConnectedError):
            listener.send_text("hello")

    def test_disconnect_while_held_cancels(self, listener, connect, recorder):
        client = connect(listener)
        client.send(type="down", button="main")
        client.receive()
        client.close()
        assert recorder.wait_for(("cancel", "remote:main"))
        assert ("release", "remote:main") not in recorder.events

    def test_silence_while_held_cancels(self, listener, connect, recorder):
        client = connect(listener)
        client.send(type="down", button="main")
        client.receive()
        # No pings: press_timeout (0.5s) passes
        assert recorder.wait_for(("cancel", "remote:main"))
        assert client.receive() is None

    def test_new_connection_replaces_old(self, listener, connect, recorder):
        first = connect(listener)
        first.send(type="down", button="main")
        first.receive()
        second = connect(listener)
        assert recorder.wait_for(("cancel", "remote:main"))
        assert first.receive() is None
        listener.send_text("hi")
        assert second.receive() == {"type": "text", "text": "hi"}

    def test_repeated_down_is_ignored(self, listener, connect, recorder):
        client = connect(listener)
        client.send(type="down", button="main")
        client.receive()
        client.send(type="down", button="main")
        client.send(type="ping")
        assert client.receive() == {"type": "pong"}
        assert recorder.events == [("press", "remote:main")]

    def test_invalid_json_disconnects(self, listener, connect):
        client = connect(listener)
        client.sock.sendall(b"not json\n")
        assert client.receive() is None

    def test_registers_as_active_listener(self, listener):
        assert get_active_remote_listener() is listener
        listener.stop_listening()
        assert get_active_remote_listener() is None

    def test_missing_credentials_mention_setup(self, tmp_path):
        config = RemoteConfig(
            cert_file=tmp_path / "cert.pem",
            key_file=tmp_path / "key.pem",
            token_file=tmp_path / "token",
        )
        with pytest.raises(RemoteCredentialsError, match="remote-setup"):
            RemoteHotkeyListener(config).start_listening()

    def test_add_hotkey_needs_remote_prefix(self):
        listener = RemoteHotkeyListener(RemoteConfig())
        for hotkey in ("<pause>", "remote:"):
            with pytest.raises(ValueError):
                listener.add_hotkey(hotkey)

    def test_is_remote_hotkey(self):
        assert is_remote_hotkey("remote:main")
        assert not is_remote_hotkey("<pause>")


class TestRemoteCredentials:
    def test_existing_credentials_are_kept(self, credentials):
        token = load_token(credentials.token)
        assert (
            generate_credentials(credentials.cert, credentials.key, credentials.token)
            == []
        )
        assert load_token(credentials.token) == token

    def test_short_token_is_refused(self, tmp_path):
        token_file = tmp_path / "token"
        token_file.write_text("short\n")
        with pytest.raises(RemoteCredentialsError, match="too short"):
            load_token(token_file)


class TestRemoteKeyboard:
    def test_types_on_connected_device(self, listener, connect):
        client = connect(listener)
        RemoteKeyboard().type_text("“Café” — naïve…")
        assert client.receive() == {"type": "text", "text": '"Cafe" -- naive...'}

    def test_needs_running_listener(self):
        with pytest.raises(RemoteNotConnectedError, match=r"\[remote\]"):
            RemoteKeyboard().type_text("hello")

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("plain text", "plain text"),
            ("it’s “quoted”", 'it\'s "quoted"'),
            ("2010–2020 — done…", "2010-2020 -- done..."),
            ("café naïve Ærø straße", "cafe naive AEro strasse"),
            ("one\ntwo\tthree\r\n", "one\ntwo\tthree\n"),
            ("emoji \U0001f389 gone", "emoji  gone"),
            ("non breaking", "non breaking"),
        ],
    )
    def test_to_hid_text(self, text, expected):
        assert to_hid_text(text) == expected


class TestHotkeyDispatcherCancel:
    @staticmethod
    def make_dispatcher(pipeline_id="pipeline-1"):
        manager = MagicMock()
        manager.get_pipeline_by_hotkey.return_value = SimpleNamespace(name="remote")
        manager.trigger_pipeline.return_value = pipeline_id
        return HotkeyDispatcher(manager), manager

    def test_press_reports_whether_pipeline_started(self):
        dispatcher, _ = self.make_dispatcher()
        assert dispatcher._on_press("remote:main") is True

        busy, _ = self.make_dispatcher(pipeline_id=None)
        assert busy._on_press("remote:main") is False

    def test_press_without_pipeline(self):
        dispatcher, manager = self.make_dispatcher()
        manager.get_pipeline_by_hotkey.return_value = None
        assert dispatcher._on_press("remote:main") is False

    def test_cancel_stops_pipeline_and_wakes_recording(self):
        dispatcher, manager = self.make_dispatcher()
        dispatcher._on_press("remote:main")
        trigger_event = dispatcher.active_events["remote:main"]

        assert dispatcher._on_cancel("remote:main") is True
        manager.cancel_pipeline.assert_called_once_with("pipeline-1")
        assert trigger_event.release_event.is_set()
        assert dispatcher._on_cancel("remote:main") is False

    def test_cancel_after_release_does_nothing(self):
        dispatcher, manager = self.make_dispatcher()
        dispatcher._on_press("remote:main")
        dispatcher._on_release("remote:main")
        assert dispatcher._on_cancel("remote:main") is False
        manager.cancel_pipeline.assert_not_called()


class _RemoteTestDictation:
    """Stands in for RecordAudio + Transcribe: returns fixed text on release."""

    outcomes = []

    def __init__(self, config: dict):
        self.text = config.get("text", "hello")

    def execute(self, input_data: None, context: PipelineContext) -> Optional[str]:
        context.trigger_event.wait_for_completion(timeout=5)
        if context.cancel_requested.is_set():
            self.outcomes.append("cancelled")
            return None
        self.outcomes.append("dictated")
        return self.text


if "_RemoteTestDictation" not in STAGE_REGISTRY.list_stages():
    STAGE_REGISTRY.register(_RemoteTestDictation)


class TestRemotePipelineEndToEnd:
    """Device button -> listener -> dispatcher -> pipeline -> remote keyboard -> device."""

    @pytest.fixture
    def app(self, credentials):
        manager = PipelineManager(ResourceManager(), MockIconController())
        manager.load_pipelines(
            [
                {
                    "name": "remote",
                    "hotkey": "remote:main",
                    "stages": ["Dictation", "TypeText_remote"],
                }
            ],
            stage_definitions={
                "Dictation": {
                    "stage_class": "_RemoteTestDictation",
                    "text": "“Hi” from the Pico",
                },
                "TypeText_remote": {
                    "stage_class": "TypeText",
                    "keyboard_backend": "remote",
                },
            },
        )
        dispatcher = HotkeyDispatcher(manager)
        listener = RemoteHotkeyListener(
            make_config(credentials),
            on_hotkey_press=dispatcher._on_press,
            on_hotkey_release=dispatcher._on_release,
            on_hotkey_cancel=dispatcher._on_cancel,
        )
        listener.add_hotkey("remote:main")
        listener.start_listening()
        _RemoteTestDictation.outcomes.clear()
        yield SimpleNamespace(listener=listener, manager=manager)
        listener.stop_listening()
        manager.shutdown(timeout=5)

    def test_dictation_is_typed_on_device(self, app, connect):
        client = connect(app.listener)
        client.send(type="down", button="main")
        assert client.receive()["state"] == "recording"
        client.send(type="up", button="main")
        assert client.receive() == {"type": "text", "text": '"Hi" from the Pico'}
        assert _RemoteTestDictation.outcomes == ["dictated"]

    def test_disconnect_mid_dictation_discards_it(self, app, connect):
        client = connect(app.listener)
        client.send(type="down", button="main")
        client.receive()
        client.close()

        deadline = time.monotonic() + 5
        while not _RemoteTestDictation.outcomes and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _RemoteTestDictation.outcomes == ["cancelled"]


class TestRemoteSettings:
    def test_defaults(self):
        config = RemoteConfig()
        assert config.enabled is False
        assert config.port == 8684
        assert config.cert_file.parent.name == "remote"

    def test_paths_expand_user(self):
        config = RemoteConfig(cert_file="~/cert.pem")
        assert config.cert_file == Path.home() / "cert.pem"

    def test_remote_setup_reuses_local_pipeline_stages(self):
        settings = Settings(
            stage_configs={
                "Transcribe_local": {"stage_class": "Transcribe"},
                "TypeText_default": {"stage_class": "TypeText"},
            },
            pipelines=[
                {
                    "name": "default",
                    "hotkey": "<pause>",
                    "stages": ["RecordAudio", "Transcribe_local", "TypeText_default"],
                }
            ],
        )
        assert _remote_pipeline_stages(settings) == [
            "RecordAudio",
            "Transcribe_local",
            "TypeText_remote",
        ]
