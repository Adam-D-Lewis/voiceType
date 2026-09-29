"""Remote hotkey listener: button presses from a device on the network.

A remote device (e.g. a Raspberry Pi Pico 2 W plugged into another computer as
a USB keyboard) connects over TLS, authenticates with a shared token, and sends
button press/release events. These trigger pipelines exactly like local
hotkeys, and a pipeline whose TypeText stage uses keyboard_backend = "remote"
sends its text back for the device to type.

Protocol: one JSON object per line, over TLS.

    device -> voiceType                   voiceType -> device
    {"type": "hello", "token": "..."}     {"type": "welcome", "version": 1}
    {"type": "down", "button": "main"}    {"type": "state", "button": "main",
                                           "state": "recording" | "rejected"}
    {"type": "up", "button": "main"}
    {"type": "ping"}                      {"type": "pong"}
                                          {"type": "text", "text": "..."}
                                          {"type": "error", "message": "..."}

Button "main" triggers the pipeline whose hotkey is "remote:main". If the
device disconnects, or goes silent for press_timeout seconds while holding a
button, that recording is cancelled rather than transcribed.
"""

import asyncio
import concurrent.futures
import hmac
import json
import threading
from typing import TYPE_CHECKING, Any, Callable, Optional

from loguru import logger

from .hotkey_listener import HotkeyListener
from .remote_credentials import create_server_ssl_context, load_token

if TYPE_CHECKING:
    from voicetype.settings import RemoteConfig

REMOTE_HOTKEY_PREFIX = "remote:"
PROTOCOL_VERSION = 1

# Seconds a new connection has to finish the TLS handshake, and then to say hello
AUTH_TIMEOUT = 10.0
WRITE_TIMEOUT = 5.0
MAX_MESSAGE_BYTES = 64 * 1024


def is_remote_hotkey(hotkey: str) -> bool:
    """Whether a pipeline hotkey refers to a remote button ("remote:<button>")."""
    return hotkey.startswith(REMOTE_HOTKEY_PREFIX)


class RemoteNotConnectedError(RuntimeError):
    """Text can't be sent because no remote device is connected."""


class _ProtocolError(Exception):
    """The device sent something that isn't a protocol message."""


_active_listener: Optional["RemoteHotkeyListener"] = None


def get_active_remote_listener() -> Optional["RemoteHotkeyListener"]:
    """Return the running remote listener, if any."""
    return _active_listener


def _encode(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, separators=(",", ":")) + "\n").encode()


def _format_peer(peername: Any) -> str:
    if isinstance(peername, tuple) and len(peername) >= 2:
        return f"{peername[0]}:{peername[1]}"
    return str(peername)


class _Session:
    """An authenticated connection from a remote device."""

    def __init__(self, writer: asyncio.StreamWriter, name: str):
        self.writer = writer
        self.name = name
        self.held: set[str] = set()  # hotkeys currently pressed
        self.closed = False


class RemoteHotkeyListener(HotkeyListener):
    """Listens for button presses from a remote device over TLS.

    Only one device is connected at a time: a newly authenticated connection
    replaces the previous one (e.g. when the device reconnects after a WiFi
    drop), and text from the remote keyboard backend goes to it.
    """

    def __init__(
        self,
        config: "RemoteConfig",
        on_hotkey_press: Optional[Callable[[str], Any]] = None,
        on_hotkey_release: Optional[Callable[[str], Any]] = None,
        on_hotkey_cancel: Optional[Callable[[str], Any]] = None,
    ):
        """Initialize the listener.

        Args:
            config: Remote listener settings
            on_hotkey_press: Called with the hotkey when a button is pressed.
                Returning False reports the press as rejected to the device.
            on_hotkey_release: Called with the hotkey when a button is released.
            on_hotkey_cancel: Called with the hotkey when the device goes away
                while holding a button. Falls back to on_hotkey_release.
        """
        super().__init__(
            on_hotkey_press=on_hotkey_press, on_hotkey_release=on_hotkey_release
        )
        self.on_hotkey_cancel = on_hotkey_cancel
        self.config = config
        self.port: Optional[int] = None  # Actual port, once listening
        self._buttons: dict[str, str] = {}  # button name -> hotkey
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server: Optional[asyncio.Server] = None
        self._stopping = False
        # Only touched on the event loop thread
        self._session: Optional[_Session] = None
        self._client_tasks: set[asyncio.Task] = set()
        # Callbacks run on a single worker thread: in order (a release never
        # overtakes its press) and without blocking the event loop
        self._callbacks: Optional[concurrent.futures.ThreadPoolExecutor] = None

    def add_hotkey(self, hotkey: str, name: str = "") -> None:
        """Bind a remote button, given as "remote:<button>"."""
        button = hotkey[len(REMOTE_HOTKEY_PREFIX) :]
        if not is_remote_hotkey(hotkey) or not button:
            raise ValueError(
                f"Remote hotkeys look like '{REMOTE_HOTKEY_PREFIX}<button>', "
                f"got '{hotkey}'"
            )
        self._buttons[button] = hotkey
        logger.debug(f"Remote button '{button}' -> {name or hotkey}")

    def clear_hotkeys(self) -> None:
        self._buttons.clear()

    def start_listening(self) -> None:
        """Start the TLS server on a background thread.

        Raises:
            RemoteCredentialsError: If the certificate, key, or token is missing.
            RuntimeError: If the server can't listen (e.g. port in use).
        """
        global _active_listener
        if self._thread is not None and self._thread.is_alive():
            return

        token = load_token(self.config.token_file)
        ssl_context = create_server_ssl_context(
            self.config.cert_file, self.config.key_file
        )

        self._stopping = False
        self._callbacks = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="remote-callbacks"
        )
        started = threading.Event()
        startup_errors: list[Exception] = []
        self._thread = threading.Thread(
            target=self._run,
            args=(ssl_context, token, started, startup_errors),
            name="remote-listener",
            daemon=True,
        )
        self._thread.start()
        started.wait()

        if startup_errors:
            self._thread.join()
            self._thread = None
            self._callbacks.shutdown(wait=False)
            error = startup_errors[0]
            raise RuntimeError(
                f"Remote listener can't listen on "
                f"{self.config.host}:{self.config.port}: {error}"
            ) from error

        _active_listener = self
        logger.info(
            f"Remote listener on {self.config.host}:{self.port} (TLS), "
            f"buttons: {', '.join(sorted(self._buttons)) or 'none'}"
        )

    def stop_listening(self) -> None:
        """Disconnect the device and stop the server."""
        global _active_listener
        if _active_listener is self:
            _active_listener = None

        loop, thread = self._loop, self._thread
        if loop is None or thread is None:
            return
        self._stopping = True
        try:
            loop.call_soon_threadsafe(lambda: loop.create_task(self._shutdown()))
        except RuntimeError:
            pass  # Loop already closed
        thread.join(timeout=5.0)
        if self._callbacks is not None:
            self._callbacks.shutdown(wait=False)
        self._thread = None
        logger.info("Remote listener stopped")

    def send_text(self, text: str) -> None:
        """Send text for the connected device to type (thread-safe).

        Raises:
            RemoteNotConnectedError: If no device is connected, or sending fails.
        """
        loop = self._loop
        if loop is None or not loop.is_running():
            raise RemoteNotConnectedError("The remote listener isn't running")
        future = asyncio.run_coroutine_threadsafe(self._send_text(text), loop)
        try:
            future.result(timeout=WRITE_TIMEOUT + 1.0)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise RemoteNotConnectedError(
                "Timed out sending text to the remote device"
            ) from None

    # ------------------------------------------------------------------
    # Event loop thread
    # ------------------------------------------------------------------

    def _run(
        self,
        ssl_context,
        token: str,
        started: threading.Event,
        startup_errors: list[Exception],
    ) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            try:
                self._server = loop.run_until_complete(
                    asyncio.start_server(
                        lambda reader, writer: self._on_connection(
                            reader, writer, token
                        ),
                        host=self.config.host,
                        port=self.config.port,
                        ssl=ssl_context,
                        ssl_handshake_timeout=AUTH_TIMEOUT,
                        limit=MAX_MESSAGE_BYTES,
                    )
                )
                self.port = self._server.sockets[0].getsockname()[1]
            except Exception as e:
                startup_errors.append(e)
                return
            finally:
                started.set()
            loop.run_forever()
        finally:
            self._close_loop(loop)

    def _close_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            loop.close()
            self._loop = None

    async def _shutdown(self) -> None:
        if self._server is not None:
            self._server.close()
        if self._session is not None:
            await self._end_session(self._session, "voiceType is shutting down")
        for task in list(self._client_tasks):
            task.cancel()
        asyncio.get_running_loop().stop()

    async def _on_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, token: str
    ) -> None:
        task = asyncio.current_task()
        self._client_tasks.add(task)
        peer = _format_peer(writer.get_extra_info("peername"))
        session = None
        reason = "closed the connection"
        try:
            session = await self._authenticate(reader, writer, token, peer)
            if session is not None:
                await self._send(
                    writer, {"type": "welcome", "version": PROTOCOL_VERSION}
                )
                logger.info(f"Remote device connected: {session.name}")
                reason = await self._serve(session, reader)
        except _ProtocolError as e:
            logger.warning(f"Remote device {peer} sent an invalid message: {e}")
            reason = "sent an invalid message"
        except OSError as e:  # Includes connection resets, TLS errors, timeouts
            reason = f"lost the connection ({e})"
        finally:
            if session is not None:
                await self._end_session(session, reason)
            else:
                writer.close()
            self._client_tasks.discard(task)

    async def _authenticate(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        token: str,
        peer: str,
    ) -> Optional[_Session]:
        """Check the device's hello and make it the connected device."""
        try:
            message = await asyncio.wait_for(self._read_message(reader), AUTH_TIMEOUT)
        except TimeoutError:
            logger.warning(f"Remote device {peer} didn't say hello; disconnecting")
            return None
        if message is None:
            return None

        supplied = message.get("token")
        if (
            message.get("type") != "hello"
            or not isinstance(supplied, str)
            or not hmac.compare_digest(supplied.encode(), token.encode())
        ):
            logger.warning(f"Rejected remote device {peer}: authentication failed")
            await self._send(writer, {"type": "error", "message": "bad token"})
            return None

        name = message.get("name")
        session = _Session(writer, f"{name} ({peer})" if name else peer)
        previous, self._session = self._session, session
        if previous is not None:
            await self._end_session(previous, "was replaced by a new connection")
        return session

    async def _serve(self, session: _Session, reader: asyncio.StreamReader) -> str:
        """Handle messages until the device goes away; returns why it did."""
        while not session.closed:
            timeout = (
                self.config.press_timeout if session.held else self.config.idle_timeout
            )
            try:
                message = await asyncio.wait_for(self._read_message(reader), timeout)
            except TimeoutError:
                return f"went silent for {timeout:g}s"
            if message is None:
                break
            await self._handle_message(session, message)
        return "closed the connection"

    async def _read_message(
        self, reader: asyncio.StreamReader
    ) -> Optional[dict[str, Any]]:
        """Read the next message, or None when the connection closes."""
        while True:
            try:
                line = await reader.readline()
            except ValueError as e:  # Longer than MAX_MESSAGE_BYTES
                raise _ProtocolError("message too long") from e
            if not line.endswith(b"\n"):
                return None
            if line.strip():
                break
        try:
            message = json.loads(line)
        except ValueError as e:  # Includes JSON and UTF-8 decoding errors
            raise _ProtocolError("not JSON") from e
        if not isinstance(message, dict):
            raise _ProtocolError("not a JSON object")
        return message

    async def _handle_message(self, session: _Session, message: dict[str, Any]):
        kind = message.get("type")
        if kind == "ping":
            await self._send(session.writer, {"type": "pong"})
        elif kind in ("down", "up"):
            button = message.get("button", "main")
            if not isinstance(button, str):
                raise _ProtocolError("button must be a string")
            if kind == "down":
                await self._press(session, button)
            else:
                await self._release(session, button)
        else:
            logger.debug(f"Ignoring message type {kind!r} from {session.name}")

    async def _press(self, session: _Session, button: str) -> None:
        hotkey = self._buttons.get(button)
        if hotkey is None:
            logger.warning(
                f"Remote button '{button}' isn't bound to a pipeline (use "
                f'hotkey = "{REMOTE_HOTKEY_PREFIX}{button}")'
            )
            await self._send_state(session, button, "rejected")
            return
        if hotkey in session.held:
            return  # Already pressed

        session.held.add(hotkey)
        started = await self._run_callback(self.on_hotkey_press, hotkey)
        if started is False:
            session.held.discard(hotkey)
        await self._send_state(
            session, button, "rejected" if started is False else "recording"
        )

    async def _release(self, session: _Session, button: str) -> None:
        hotkey = self._buttons.get(button)
        if hotkey is None or hotkey not in session.held:
            return
        session.held.discard(hotkey)
        await self._run_callback(self.on_hotkey_release, hotkey)

    async def _end_session(self, session: _Session, reason: str) -> None:
        if session.closed:
            return
        session.closed = True
        if self._session is session:
            self._session = None

        logger.info(f"Remote device {session.name} {reason}")
        held, session.held = session.held, set()
        if not self._stopping:
            for hotkey in held:
                logger.warning(f"Cancelling the recording for {hotkey}")
                await self._run_callback(
                    self.on_hotkey_cancel or self.on_hotkey_release, hotkey
                )

        session.writer.close()
        try:
            await asyncio.wait_for(session.writer.wait_closed(), 2.0)
        except Exception:
            pass  # Already gone; nothing left to clean up

    async def _run_callback(self, callback: Optional[Callable], hotkey: str) -> Any:
        if callback is None:
            return None
        try:
            return await asyncio.get_running_loop().run_in_executor(
                self._callbacks, callback, hotkey
            )
        except Exception:
            logger.exception(f"Hotkey callback failed for {hotkey}")
            return False

    async def _send(
        self, writer: asyncio.StreamWriter, message: dict[str, Any]
    ) -> None:
        if writer.is_closing():
            raise ConnectionResetError("connection is closed")
        writer.write(_encode(message))
        await asyncio.wait_for(writer.drain(), WRITE_TIMEOUT)

    async def _send_state(self, session: _Session, button: str, state: str) -> None:
        await self._send(
            session.writer, {"type": "state", "button": button, "state": state}
        )

    async def _send_text(self, text: str) -> None:
        session = self._session
        if session is None or session.closed:
            raise RemoteNotConnectedError("No remote device is connected")
        try:
            await self._send(session.writer, {"type": "text", "text": text})
        except OSError as e:
            raise RemoteNotConnectedError(
                f"Lost the connection to {session.name}: {e}"
            ) from e
        logger.debug(f"Sent {len(text)} characters to {session.name}")
