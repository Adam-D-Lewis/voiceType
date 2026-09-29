"""Run the Pico firmware (firmware/pico2w/code.py) against the real remote listener.

The firmware runs under CPython with small stand-ins for the CircuitPython
modules it uses: sockets that behave like CircuitPython's (the handshake happens
in connect(), and a non-blocking read with no data raises OSError(EAGAIN)), a
keypad whose button presses the test injects, and a USB keyboard that records
key presses so the typed text can be decoded with the layout tables.
"""

import builtins
import collections
import errno
import shutil
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from voicetype.hotkey_listener.remote_credentials import generate_credentials
from voicetype.hotkey_listener.remote_hotkey_listener import RemoteHotkeyListener
from voicetype.settings import RemoteConfig

FIRMWARE = Path(__file__).parent.parent / "firmware" / "pico2w"
sys.path.insert(0, str(FIRMWARE))

import hid_layouts  # noqa: E402


class StopFirmware(BaseException):
    """Ends the firmware's main loop (a BaseException, so it isn't caught)."""


class FakeCircuitPython:
    """Stand-ins for the CircuitPython modules code.py imports."""

    def __init__(self):
        self.stopping = False
        self.lines = []  # print() output
        self.key_reports = []  # keycodes sent per key press
        self._events = collections.deque()
        self._printed = threading.Condition()

        fakes = self

        class EventQueue:
            def get(self):
                fakes.check_stop()
                return fakes._events.popleft() if fakes._events else None

            def clear(self):
                fakes._events.clear()

        class Keys:
            def __init__(self, pins, value_when_pressed, pull):
                self.events = EventQueue()

        class DigitalInOut:
            def __init__(self, pin):
                self.direction = None
                self._value = False

            @property
            def value(self):
                return self._value

            @value.setter
            def value(self, value):
                fakes.check_stop()
                self._value = value

        class Keyboard:
            def __init__(self, devices):
                pass

            def send(self, *keycodes):
                fakes.key_reports.append(keycodes)

        class SSLSocket:
            """Like CircuitPython's: handshake in connect(), OSError(errno) when
            a non-blocking read or write can't proceed."""

            def __init__(self, raw, cadata, server_hostname):
                self._raw = raw
                self._cadata = cadata
                self._hostname = server_hostname
                self._tls = None
                self._timeout = None

            def settimeout(self, timeout):
                self._timeout = timeout
                (self._tls or self._raw).settimeout(timeout)

            def connect(self, address):
                self._raw.connect(address)
                context = ssl.create_default_context(cadata=self._cadata)
                self._tls = context.wrap_socket(
                    self._raw, server_hostname=self._hostname
                )
                self._tls.settimeout(self._timeout)

            def send(self, data):
                try:
                    return self._tls.send(data)
                except (ssl.SSLWantWriteError, BlockingIOError):
                    raise OSError(errno.EAGAIN, "EAGAIN") from None

            def recv_into(self, buffer):
                try:
                    return self._tls.recv_into(buffer)
                except (ssl.SSLWantReadError, BlockingIOError):
                    raise OSError(errno.EAGAIN, "EAGAIN") from None

            def close(self):
                (self._tls or self._raw).close()

        class SSLContext:
            def __init__(self):
                self._cadata = None

            def load_verify_locations(self, cadata=None):
                self._cadata = cadata

            def wrap_socket(self, sock, server_hostname=None):
                return SSLSocket(sock, self._cadata, server_hostname)

        class SocketPool:
            AF_INET = socket.AF_INET
            SOCK_STREAM = socket.SOCK_STREAM

            def __init__(self, radio):
                pass

            def getaddrinfo(self, host, port):
                return socket.getaddrinfo(
                    host, port, socket.AF_INET, socket.SOCK_STREAM
                )

            def socket(self, family, kind):
                return socket.socket(family, kind)

        self.modules = {
            "board": SimpleNamespace(GP14="GP14", GP15="GP15", LED="LED"),
            "digitalio": SimpleNamespace(
                DigitalInOut=DigitalInOut,
                Direction=SimpleNamespace(OUTPUT="output"),
                Pull=SimpleNamespace(UP="up"),
            ),
            "keypad": SimpleNamespace(Keys=Keys),
            "socketpool": SimpleNamespace(SocketPool=SocketPool),
            "ssl": SimpleNamespace(create_default_context=SSLContext),
            "usb_hid": SimpleNamespace(devices=[]),
            "wifi": SimpleNamespace(
                radio=SimpleNamespace(
                    ipv4_address="127.0.0.1", connect=lambda ssid, password: None
                )
            ),
            "adafruit_hid.keyboard": SimpleNamespace(Keyboard=Keyboard),
            "hid_layouts": hid_layouts,
        }

    def check_stop(self):
        if self.stopping:
            raise StopFirmware

    def press(self, key_number=0):
        self._events.append(SimpleNamespace(key_number=key_number, pressed=True))

    def release(self, key_number=0):
        self._events.append(SimpleNamespace(key_number=key_number, pressed=False))

    def print(self, *args, **kwargs):
        with self._printed:
            self.lines.append(" ".join(str(arg) for arg in args))
            self._printed.notify_all()

    def wait_for_line(self, text, count=1, timeout=10.0) -> bool:
        with self._printed:
            return self._printed.wait_for(
                lambda: sum(text in line for line in self.lines) >= count, timeout
            )

    def typed_text(self, layout) -> str:
        by_key = {key: char for char, key in hid_layouts.keymap(layout).items()}
        chars = []
        for keycodes in self.key_reports:
            shift = hid_layouts.LEFT_SHIFT in keycodes
            keycode = [k for k in keycodes if k != hid_layouts.LEFT_SHIFT][0]
            chars.append(by_key[(keycode, shift)])
        return "".join(chars)

    def run(self):
        """Start code.py on a background thread (settings come from env vars)."""

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in self.modules:
                return self.modules[name]
            return builtins.__import__(name, globals, locals, fromlist, level)

        fake_builtins = dict(vars(builtins), __import__=fake_import, print=self.print)
        namespace = {"__name__": "__main__", "__builtins__": fake_builtins}
        code = compile((FIRMWARE / "code.py").read_text(), "code.py", "exec")

        def target():
            try:
                exec(code, namespace)
            except StopFirmware:
                pass

        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self):
        self.stopping = True
        self._thread.join(timeout=10)


@pytest.fixture(scope="module")
def credentials(tmp_path_factory):
    if not shutil.which("openssl"):
        pytest.skip("needs the openssl command")
    directory = tmp_path_factory.mktemp("remote")
    paths = SimpleNamespace(
        cert=directory / "cert.pem",
        key=directory / "key.pem",
        token=directory / "token",
    )
    generate_credentials(paths.cert, paths.key, paths.token)
    return paths


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Callbacks:
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

    def wait_for(self, event, timeout=10.0) -> bool:
        with self._changed:
            return self._changed.wait_for(lambda: event in self.events, timeout)


@pytest.fixture
def setup(credentials, monkeypatch):
    port = free_port()
    callbacks = Callbacks()
    listeners = []

    def start_listener():
        listener = RemoteHotkeyListener(
            RemoteConfig(
                host="127.0.0.1",
                port=port,
                cert_file=credentials.cert,
                key_file=credentials.key,
                token_file=credentials.token,
                press_timeout=2.5,
            ),
            on_hotkey_press=callbacks.press,
            on_hotkey_release=callbacks.release,
            on_hotkey_cancel=callbacks.cancel,
        )
        listener.add_hotkey("remote:main")
        listener.start_listening()
        listeners.append(listener)
        return listener

    for name, value in {
        "CIRCUITPY_WIFI_SSID": "test-wifi",
        "VOICETYPE_HOST": "127.0.0.1",
        "VOICETYPE_PORT": str(port),
        "VOICETYPE_TOKEN": credentials.token.read_text().strip(),
        "VOICETYPE_LAYOUT": "dvp",
        "VOICETYPE_BUTTONS": "GP15=main",
        "VOICETYPE_CERT_FILE": str(credentials.cert),
    }.items():
        monkeypatch.setenv(name, value)

    pico = FakeCircuitPython()
    yield SimpleNamespace(
        pico=pico,
        callbacks=callbacks,
        start_listener=start_listener,
        listeners=listeners,
        monkeypatch=monkeypatch,
    )
    pico.stop()
    for listener in listeners:
        listener.stop_listening()


def test_dictation_round_trip(setup):
    listener = setup.start_listener()
    setup.pico.run()
    assert setup.pico.wait_for_line("Connected to voiceType")

    setup.pico.press()
    assert setup.callbacks.wait_for(("press", "remote:main"))
    time.sleep(3.5)  # Held longer than press_timeout: pings keep it alive
    setup.pico.release()
    assert setup.callbacks.wait_for(("release", "remote:main"))
    assert ("cancel", "remote:main") not in setup.callbacks.events

    text = 'Hello, World! 1234567890 $&[{}(=*)+]!# ~%`:<>?^|_"\n\tdone'
    listener.send_text(text)
    deadline = time.monotonic() + 10
    while len(setup.pico.key_reports) < len(text) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert setup.pico.typed_text("dvp") == text


def test_rejected_press_is_reported(setup):
    setup.callbacks.accept = False
    setup.start_listener()
    setup.pico.run()
    assert setup.pico.wait_for_line("Connected to voiceType")
    setup.pico.press()
    assert setup.pico.wait_for_line("voiceType didn't start recording")


def test_wrong_token_is_a_setup_problem(setup):
    setup.monkeypatch.setenv("VOICETYPE_TOKEN", "definitely-not-the-token")
    setup.start_listener()
    setup.pico.run()
    assert setup.pico.wait_for_line("Setup problem: voiceType refused the connection")


def test_reconnects_after_voicetype_restarts(setup):
    listener = setup.start_listener()
    setup.pico.run()
    assert setup.pico.wait_for_line("Connected to voiceType")

    listener.stop_listening()
    assert setup.pico.wait_for_line("Connection problem")
    setup.start_listener()
    assert setup.pico.wait_for_line("Connected to voiceType", count=2, timeout=15)
