"""voiceType remote button for a Raspberry Pi Pico 2 W running CircuitPython.

Hold the button to dictate: the Pico asks voiceType (running on another
computer) to record, then types the transcription into the computer it's
plugged into, as a USB keyboard. See README.md for setup.
"""

import json
import os
import ssl
import time

import board
import digitalio
import hid_layouts
import keypad
import socketpool
import usb_hid
import wifi
from adafruit_hid.keyboard import Keyboard

try:
    import errno

    WOULD_BLOCK = (errno.EAGAIN, errno.ETIMEDOUT)
except (ImportError, AttributeError):
    WOULD_BLOCK = (11, 110)


def setting(name, default=None):
    value = os.getenv(name)
    return default if value is None or value == "" else value


WIFI_SSID = setting("CIRCUITPY_WIFI_SSID")
WIFI_PASSWORD = setting("CIRCUITPY_WIFI_PASSWORD")
HOST = setting("VOICETYPE_HOST")
PORT = int(setting("VOICETYPE_PORT", 8684))
TOKEN = setting("VOICETYPE_TOKEN")
LAYOUT = setting("VOICETYPE_LAYOUT", "us")
BUTTONS = setting("VOICETYPE_BUTTONS", "GP15=main")
DEVICE_NAME = setting("VOICETYPE_DEVICE_NAME", "pico2w")
CERT_FILE = setting("VOICETYPE_CERT_FILE", "/voicetype_cert.pem")
# Name checked against the certificate; `voicetype remote-setup` always adds it
TLS_NAME = setting("VOICETYPE_TLS_NAME", "voicetype")

# voiceType cancels a held button's recording after ~3 s without hearing from us
PING_INTERVAL_MS = 1000
SERVER_TIMEOUT_MS = 5000  # Reconnect if voiceType goes quiet this long
CONNECT_TIMEOUT_S = 15  # The TLS handshake takes a moment on a microcontroller
WAIT_FOR_TEXT_MS = 20000  # How long the LED shows "transcribing" after release
MAX_RETRY_DELAY_S = 10
MAX_MESSAGE_BYTES = 64 * 1024
TYPE_CHUNK = 16  # Characters typed between pings


def now_ms():
    return time.monotonic_ns() // 1000000


def error_code(error):
    code = getattr(error, "errno", None)
    if code is None and error.args:
        code = error.args[0]
    return code


class Disconnected(Exception):
    """The connection to voiceType is gone or unusable."""


class SetupProblem(Exception):
    """Something only a settings change can fix."""


class Led:
    """The onboard LED.

    on: recording | fast blink: transcribing | slow blink: connecting
    flicker: voiceType refused the press, or a setup problem | off: ready
    """

    HALF_PERIOD_MS = {"waiting": 150, "connecting": 500, "error": 50}

    def __init__(self):
        try:
            self._pin = digitalio.DigitalInOut(board.LED)
            self._pin.direction = digitalio.Direction.OUTPUT
        except (AttributeError, ValueError, RuntimeError):
            self._pin = None
        self._mode = "off"
        self._until = None

    def set(self, mode, duration_ms=None):
        """Show a mode, optionally only for a while before going off."""
        self._mode = mode
        self._until = now_ms() + duration_ms if duration_ms else None
        self.update()

    def update(self):
        if self._pin is None:
            return
        t = now_ms()
        if self._until is not None and t >= self._until:
            self._mode, self._until = "off", None
        half_period = self.HALF_PERIOD_MS.get(self._mode)
        if half_period:
            self._pin.value = (t // half_period) % 2 == 0
        else:
            self._pin.value = self._mode == "on"


class Typer:
    """Types text into the computer the Pico is plugged into."""

    def __init__(self, layout):
        self._keymap = hid_layouts.keymap(layout)
        self._keyboard = None

    def _open_keyboard(self):
        # The computer may still be setting up the USB connection at boot
        for attempt in range(10):
            try:
                return Keyboard(usb_hid.devices)
            except OSError:
                time.sleep(1)
        return Keyboard(usb_hid.devices)

    def type(self, text, between_chunks=None):
        if self._keyboard is None:
            self._keyboard = self._open_keyboard()
        skipped = 0
        for i, char in enumerate(text):
            key = self._keymap.get(char)
            if key is None:
                skipped += 1
                continue
            keycode, shift = key
            try:
                if shift:
                    self._keyboard.send(hid_layouts.LEFT_SHIFT, keycode)
                else:
                    self._keyboard.send(keycode)
            except OSError as e:  # Computer asleep or unplugged
                print("Typing stopped:", e)
                return
            if between_chunks is not None and i % TYPE_CHUNK == TYPE_CHUNK - 1:
                between_chunks()
        if skipped:
            print("Skipped", skipped, "characters the layout can't type")


class Connection:
    """One JSON message per line, over TLS, to voiceType's remote listener."""

    def __init__(self, sock):
        self._sock = sock
        self._buffer = b""
        self._chunk = bytearray(1024)
        self._pending = []
        self._closed = None  # Why the connection closed, once it has

    @classmethod
    def open(cls, pool, context):
        address = pool.getaddrinfo(HOST, PORT)[0][4]
        print("Connecting to", HOST, "at", address[0], "port", PORT)
        sock = context.wrap_socket(
            pool.socket(pool.AF_INET, pool.SOCK_STREAM), server_hostname=TLS_NAME
        )
        try:
            sock.settimeout(CONNECT_TIMEOUT_S)
            sock.connect(address)
            sock.settimeout(0)  # Non-blocking from here on
        except Exception:
            sock.close()
            raise
        return cls(sock)

    def send(self, message):
        data = (json.dumps(message) + "\n").encode()
        deadline = now_ms() + 5000
        while data:
            try:
                sent = self._sock.send(data)
            except OSError as e:
                if error_code(e) in WOULD_BLOCK and now_ms() < deadline:
                    time.sleep(0.005)
                    continue
                raise Disconnected("sending failed: {}".format(e))
            data = data[sent:]

    def receive(self):
        """Return the messages that have arrived, without waiting."""
        while self._closed is None:
            try:
                count = self._sock.recv_into(self._chunk)
            except OSError as e:
                if error_code(e) in WOULD_BLOCK:
                    break
                self._closed = "receiving failed: {}".format(e)
                break
            if count == 0:
                self._closed = "voiceType closed the connection"
                break
            self._buffer += bytes(self._chunk[:count])
            if len(self._buffer) > MAX_MESSAGE_BYTES:
                raise Disconnected("message too long")

        messages, self._pending = self._pending, []
        while True:
            end = self._buffer.find(b"\n")
            if end < 0:
                break
            line, self._buffer = self._buffer[:end], self._buffer[end + 1 :]
            if line.strip():
                try:
                    messages.append(json.loads(line.decode()))
                except ValueError:
                    raise Disconnected("voiceType sent something that isn't JSON")
        # Deliver what arrived before the connection closed (e.g. an error
        # explaining why) before reporting the disconnect
        if not messages and self._closed is not None:
            raise Disconnected(self._closed)
        return messages

    def wait_for_message(self, timeout_ms):
        deadline = now_ms() + timeout_ms
        while now_ms() < deadline:
            messages = self.receive()
            if messages:
                self._pending = messages[1:]
                return messages[0]
            time.sleep(0.01)
        raise Disconnected("voiceType didn't answer")

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


class Session:
    """A connection to voiceType: send button presses, type what comes back."""

    def __init__(self, connection, keys, buttons, typer, led):
        self.connection = connection
        self.keys = keys
        self.buttons = buttons  # Button name for each key number
        self.typer = typer
        self.led = led
        self.held = set()
        self.established = False
        self.last_ping = self.last_heard = now_ms()

    def run(self):
        """Serve the connection until it breaks (raises Disconnected or OSError)."""
        self.connection.send({"type": "hello", "token": TOKEN, "name": DEVICE_NAME})
        reply = self.connection.wait_for_message(10000)
        if reply.get("type") == "error":
            raise SetupProblem(
                "voiceType refused the connection ({}); check VOICETYPE_TOKEN".format(
                    reply.get("message")
                )
            )
        if reply.get("type") != "welcome":
            raise Disconnected(
                "voiceType refused the connection: {}".format(
                    reply.get("message", reply)
                )
            )
        self.established = True
        print("Connected to voiceType")
        self.led.set("off")
        self.keys.events.clear()  # Ignore presses from while we were connecting
        self.last_ping = self.last_heard = now_ms()

        while True:
            self.check_buttons()
            messages = self.connection.receive()
            if messages:
                self.last_heard = now_ms()
            for message in messages:
                self.handle(message)
            self.ping_if_due()
            if now_ms() - self.last_heard > SERVER_TIMEOUT_MS:
                raise Disconnected("voiceType stopped answering")
            self.led.update()
            time.sleep(0.005)

    def check_buttons(self):
        event = self.keys.events.get()
        while event:
            button = self.buttons[event.key_number]
            if event.pressed:
                self.connection.send({"type": "down", "button": button})
                self.held.add(button)
                self.led.set("on")
            elif button in self.held:
                self.held.discard(button)
                self.connection.send({"type": "up", "button": button})
                self.led.set("waiting", WAIT_FOR_TEXT_MS)
            event = self.keys.events.get()

    def handle(self, message):
        kind = message.get("type")
        if kind == "text":
            self.typer.type(message.get("text", ""), self.ping_while_typing)
            self.last_heard = now_ms()  # Typing a lot of text takes a while
            self.led.set("on" if self.held else "off")
        elif kind == "state" and message.get("state") == "rejected":
            print(
                "voiceType didn't start recording (disabled, busy, or button",
                repr(message.get("button")),
                "not bound to a pipeline)",
            )
            self.held.discard(message.get("button"))
            self.led.set("error", 1000)
        elif kind == "error":
            raise Disconnected("voiceType: {}".format(message.get("message")))

    def ping_if_due(self):
        if now_ms() - self.last_ping >= PING_INTERVAL_MS:
            self.connection.send({"type": "ping"})
            self.last_ping = now_ms()

    def ping_while_typing(self):
        try:
            self.ping_if_due()
        except Disconnected:
            pass  # Finish typing; the main loop notices the broken connection


def parse_buttons(spec):
    """Parse "GP15=main,GP14=other" into [(pin, button name), ...]."""
    buttons = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        pin_name, name = item.split("=", 1) if "=" in item else (item, "main")
        pin = getattr(board, pin_name.strip(), None)
        if pin is None:
            raise ValueError("VOICETYPE_BUTTONS: no pin named " + pin_name.strip())
        buttons.append((pin, name.strip() or "main"))
    if not buttons:
        raise ValueError("VOICETYPE_BUTTONS is empty")
    return buttons


def connect_wifi():
    if wifi.radio.ipv4_address is not None:
        return
    print("Joining WiFi network", WIFI_SSID)
    wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
    print("WiFi connected, IP address", wifi.radio.ipv4_address)


def pause(duration_ms, led):
    end = now_ms() + duration_ms
    while now_ms() < end:
        led.update()
        time.sleep(0.02)


def fail(message, led):
    """Report a setup problem forever (it needs a settings fix, not a retry)."""
    led.set("error")
    while True:
        print("Setup problem:", message)
        pause(5000, led)


def main():
    led = Led()
    missing = [
        name
        for name, value in (
            ("CIRCUITPY_WIFI_SSID", WIFI_SSID),
            ("VOICETYPE_HOST", HOST),
            ("VOICETYPE_TOKEN", TOKEN),
        )
        if not value
    ]
    if missing:
        fail("set " + ", ".join(missing) + " in settings.toml", led)
    try:
        buttons = parse_buttons(BUTTONS)
        typer = Typer(LAYOUT)
    except ValueError as e:
        fail(str(e), led)
    try:
        with open(CERT_FILE) as f:
            certificate = f.read()
    except OSError:
        fail(
            "copy voiceType's cert.pem to the CIRCUITPY drive as " + CERT_FILE,
            led,
        )

    keys = keypad.Keys([pin for pin, _ in buttons], value_when_pressed=False, pull=True)
    names = [name for _, name in buttons]
    context = ssl.create_default_context()
    context.load_verify_locations(cadata=certificate)
    print("Layout:", LAYOUT, "| buttons:", BUTTONS)

    pool = None
    delay_s = 1
    while True:
        led.set("connecting")
        connection = None
        session = None
        problem = None
        try:
            connect_wifi()
            if pool is None:
                pool = socketpool.SocketPool(wifi.radio)
            connection = Connection.open(pool, context)
            session = Session(connection, keys, names, typer, led)
            session.run()
        except SetupProblem as e:
            problem = str(e)
        except Exception as e:  # Disconnected, OSError, ConnectionError, ...
            print("Connection problem:", type(e).__name__, e)
        finally:
            if connection is not None:
                connection.close()
        if problem:
            fail(problem, led)
        if session is not None and session.established:
            delay_s = 1  # It was working; retry quickly
        led.set("connecting")
        print("Retrying in", delay_s, "s")
        pause(delay_s * 1000, led)
        delay_s = min(delay_s * 2, MAX_RETRY_DELAY_S)


main()
