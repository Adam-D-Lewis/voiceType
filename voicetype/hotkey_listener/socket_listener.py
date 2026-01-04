"""Cross-platform socket-based client for the privileged keyboard service.

This module provides a client that communicates over sockets with a privileged
service, allowing keyboard capture and typing to run in a separate process
with elevated privileges while the main application runs as a regular user.

Features:
- Receives hotkey press/release events from the privileged service
- Sends text to be typed by the privileged service (works on Wayland)

On Linux: Uses Unix domain sockets (faster, more secure)
On Windows/macOS: Uses TCP localhost sockets
"""

import json
import os
import platform
import socket
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from .hotkey_listener import HotkeyListener

# Module-level reference to the active socket listener for text typing
_active_socket_listener: Optional["SocketHotkeyListener"] = None


def get_active_socket_listener() -> Optional["SocketHotkeyListener"]:
    """Get the currently active socket listener.

    This is used by the TypeText stage to send text for typing on Linux.

    Returns:
        The active SocketHotkeyListener instance, or None if not available.
    """
    return _active_socket_listener


def get_socket_path() -> str:
    """Get the appropriate socket path/address for the current platform.

    Returns:
        On Linux: Path to Unix socket
        On Windows/macOS: "localhost:PORT" style address
    """
    if platform.system() == "Linux":
        # Use XDG_RUNTIME_DIR if available (user-specific temp dir)
        runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
        if runtime_dir:
            return os.path.join(runtime_dir, "voicetype-hotkey.sock")
        else:
            # Fallback to temp directory
            return os.path.join(
                tempfile.gettempdir(), f"voicetype-hotkey-{os.getuid()}.sock"
            )
    else:
        # Windows/macOS: use a fixed port
        return "127.0.0.1:47391"


class SocketHotkeyListener(HotkeyListener):
    """Client for the privileged keyboard service.

    This client connects to a privileged service running with elevated
    permissions and:
    - Receives hotkey press/release events
    - Sends text to be typed (for reliable Wayland support)
    """

    def __init__(
        self,
        on_hotkey_press: Optional[Callable[[], None]] = None,
        on_hotkey_release: Optional[Callable[[], None]] = None,
        socket_address: Optional[str] = None,
    ):
        """Initialize the socket listener.

        Args:
            on_hotkey_press: Callback when hotkey is pressed
            on_hotkey_release: Callback when hotkey is released
            socket_address: Socket address (path for Unix, host:port for TCP)
        """
        super().__init__(on_hotkey_press, on_hotkey_release)
        self._socket_address = socket_address or get_socket_path()
        self._hotkey: Optional[str] = None
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._connected = threading.Event()

    def set_hotkey(self, hotkey: str) -> None:
        """Set the hotkey combination.

        Args:
            hotkey: Hotkey string (e.g., "<pause>", "<ctrl>+<alt>+r")
        """
        self._hotkey = hotkey
        logger.info(f"Hotkey set to: {hotkey}")

        # If connected, send update to privileged listener
        if self._socket and self._connected.is_set():
            self._send_message({"type": "set_hotkey", "hotkey": hotkey})

    def _create_socket(self) -> socket.socket:
        """Create and connect to the appropriate socket type."""
        if ":" in self._socket_address:
            # TCP socket (Windows/macOS)
            host, port = self._socket_address.rsplit(":", 1)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, int(port)))
        else:
            # Unix socket (Linux)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(self._socket_address)
        return sock

    def _send_message(self, msg: dict) -> None:
        """Send a JSON message to the privileged listener."""
        if self._socket:
            try:
                data = json.dumps(msg) + "\n"
                with self._lock:
                    self._socket.sendall(data.encode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    def _recv_loop(self) -> None:
        """Receive loop for messages from the privileged listener."""
        buffer = ""
        while self._running and self._socket:
            try:
                data = self._socket.recv(1024)
                if not data:
                    logger.warning("Privileged listener disconnected")
                    break

                buffer += data.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line:
                        try:
                            msg = json.loads(line)
                            self._handle_message(msg)
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON from listener: {e}")
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Error receiving from listener: {e}")
                break

    def _handle_message(self, msg: dict) -> None:
        """Handle a message from the privileged service."""
        msg_type = msg.get("type")
        if msg_type == "ready":
            logger.info("Privileged service ready")
            self._connected.set()
        elif msg_type == "press":
            self._trigger_hotkey_press()
        elif msg_type == "release":
            self._trigger_hotkey_release()
        elif msg_type == "ack":
            logger.debug("Received ack from service")
        elif msg_type == "pong":
            logger.debug("Received pong from service")
        elif msg_type == "type_complete":
            logger.debug("Text typing completed by privileged service")
        elif msg_type == "error":
            logger.error(f"Error from service: {msg.get('message')}")

    def start_listening(self) -> None:
        """Start listening for hotkey events.

        This connects to the privileged listener process and starts
        receiving hotkey events.

        Raises:
            ValueError: If hotkey is not set
            ConnectionRefusedError: If privileged listener is not running
        """
        if self._running:
            logger.warning("Already listening")
            return

        if not self._hotkey:
            raise ValueError("Hotkey must be set before starting listener")

        # Connect to the privileged listener
        try:
            self._socket = self._create_socket()
            self._socket.settimeout(0.5)  # 500ms timeout for recv
        except FileNotFoundError:
            raise ConnectionRefusedError(
                f"Privileged listener not running. Socket not found: {self._socket_address}"
            )
        except ConnectionRefusedError:
            raise ConnectionRefusedError(
                "Privileged listener not running. Start it with: "
                f"sudo python -m voicetype.hotkey_listener.privileged_service "
                f'--socket {self._socket_address} --hotkey "{self._hotkey}"'
            )

        self._running = True
        self._connected.clear()

        # Start receive thread
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

        # Wait for ready message
        if not self._connected.wait(timeout=5.0):
            self.stop_listening()
            raise RuntimeError("Timeout waiting for privileged listener to be ready")

        # Send initial hotkey
        if self._hotkey:
            self._send_message({"type": "set_hotkey", "hotkey": self._hotkey})

        logger.info("Connected to privileged service")

        # Send display environment info for X11 typing support
        self._send_display_info()

        # Register as the active socket listener for text typing
        global _active_socket_listener
        _active_socket_listener = self

    def _send_display_info(self) -> None:
        """Send display environment info to the privileged service.

        This allows the privileged service to set up X11 access for pynput
        keyboard typing on X11 systems.
        """
        display = os.environ.get("DISPLAY", "")
        xauthority = os.environ.get("XAUTHORITY", "")
        wayland_display = os.environ.get("WAYLAND_DISPLAY", "")

        if display or xauthority or wayland_display:
            self._send_message(
                {
                    "type": "set_display",
                    "display": display,
                    "xauthority": xauthority,
                    "wayland_display": wayland_display,
                }
            )
            logger.debug(
                f"Sent display info: DISPLAY={display}, "
                f"XAUTHORITY={xauthority}, WAYLAND_DISPLAY={wayland_display}"
            )

    def stop_listening(self) -> None:
        """Stop listening for hotkey events."""
        # Unregister as the active socket listener
        global _active_socket_listener
        if _active_socket_listener is self:
            _active_socket_listener = None

        self._running = False

        if self._socket:
            try:
                self._send_message({"type": "stop"})
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=2.0)
        self._recv_thread = None

        self._connected.clear()
        logger.info("Socket listener stopped")

    def is_connected(self) -> bool:
        """Check if connected to the privileged service.

        Returns:
            True if connected and ready, False otherwise.
        """
        return self._connected.is_set() and self._socket is not None

    def type_text(self, text: str, char_delay: float = 0.001) -> None:
        """Send text to the privileged service for typing.

        This sends the text over the socket to be typed by the privileged
        service using pynput, which works reliably on both X11 and Wayland.

        Args:
            text: The text to type.
            char_delay: Delay in seconds between each character.

        Raises:
            RuntimeError: If not connected to the privileged service.
        """
        if not self.is_connected():
            raise RuntimeError("Not connected to privileged service")

        self._send_message(
            {
                "type": "type_text",
                "text": text,
                "char_delay": char_delay,
            }
        )
