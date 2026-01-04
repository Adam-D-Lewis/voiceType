#!/usr/bin/env python3
"""Privileged keyboard listener that runs as a separate process.

On Linux, pynput requires root access to read from /dev/input, but pystray
(the system tray library) needs access to the user's D-Bus session. Running
the entire app as root breaks pystray.

Solution: Run this listener as a separate process with sudo, while the main
application (with the tray icon) runs as the regular user. Communication
happens over Unix domain sockets.

Note: This is only needed on Linux. On Windows and macOS, pynput works
without elevated privileges.

Usage (Linux only):
    sudo python -m voicetype.hotkey_listener.privileged_listener \\
        --socket /run/user/1000/voicetype-hotkey.sock --hotkey "<pause>"
"""

import argparse
import json
import os
import platform
import signal
import socket
import sys
import threading
from pathlib import Path
from typing import Optional

# Add the project root to the path so we can import voicetype modules
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger

# Use uinput backend for pynput on Linux - works better when running as root
# Must be set before importing pynput
if platform.system() == "Linux":
    os.environ["PYNPUT_BACKEND_KEYBOARD"] = "uinput"
    os.environ["PYNPUT_BACKEND_MOUSE"] = "dummy"


def is_tcp_address(address: str) -> bool:
    """Check if the address is a TCP address (host:port format)."""
    return ":" in address and not address.startswith("/")


class PrivilegedListener:
    """Keyboard listener that communicates over sockets (Unix or TCP)."""

    def __init__(self, socket_address: str, hotkey: str):
        """Initialize the listener.

        Args:
            socket_address: Socket address (Unix path or host:port for TCP)
            hotkey: Initial hotkey to listen for
        """
        self.socket_address = socket_address
        self.is_tcp = is_tcp_address(socket_address)
        self.hotkey = hotkey
        self._socket: Optional[socket.socket] = None
        self._conn: Optional[socket.socket] = None
        self._listener = None
        self._running = False
        self._hotkey_combination: Optional[set] = None
        self._pressed_keys: set = set()
        self._hotkey_pressed: bool = False
        self._lock = threading.Lock()

    def _setup_socket(self) -> None:
        """Set up the socket server (Unix domain or TCP)."""
        if self.is_tcp:
            # TCP socket
            host, port = self.socket_address.rsplit(":", 1)
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((host, int(port)))
            logger.info(f"Listening on TCP: {self.socket_address}")
        else:
            # Unix domain socket
            socket_path = Path(self.socket_address)
            if socket_path.exists():
                socket_path.unlink()

            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.bind(self.socket_address)

            # Make socket accessible by non-root user
            # Get the original user who ran sudo
            sudo_uid = os.environ.get("SUDO_UID")
            sudo_gid = os.environ.get("SUDO_GID")
            if sudo_uid and sudo_gid:
                os.chown(self.socket_address, int(sudo_uid), int(sudo_gid))

            # Allow user to connect
            os.chmod(self.socket_address, 0o660)
            logger.info(f"Listening on Unix socket: {self.socket_address}")

        self._socket.listen(1)

    def _parse_hotkey(self, hotkey: str) -> None:
        """Parse the hotkey string into a key combination."""
        import pynput

        keyboard = pynput.keyboard
        try:
            self._hotkey_combination = set(keyboard.HotKey.parse(hotkey))
            self.hotkey = hotkey
            logger.info(f"Hotkey set to: {hotkey} -> {self._hotkey_combination}")
        except ValueError as e:
            logger.error(f"Error parsing hotkey: {e}")

    def _on_press(self, key) -> None:
        """Handle key press events."""
        logger.debug(f"Key press detected: {key}")
        if key is None or self._hotkey_combination is None or self._listener is None:
            return

        with self._lock:
            canonical_key = self._listener.canonical(key)
            logger.debug(
                f"Canonical key: {canonical_key}, hotkey combo: {self._hotkey_combination}"
            )
            self._pressed_keys.add(canonical_key)

            if not self._hotkey_pressed and self._hotkey_combination.issubset(
                self._pressed_keys
            ):
                self._hotkey_pressed = True
                self._send_message({"type": "press"})

    def _on_release(self, key) -> None:
        """Handle key release events."""
        if key is None or self._hotkey_combination is None or self._listener is None:
            return

        canonical_key = self._listener.canonical(key)

        with self._lock:
            if self._hotkey_pressed and canonical_key in self._hotkey_combination:
                any_hotkey_key_pressed = any(
                    k in self._pressed_keys
                    for k in self._hotkey_combination
                    if k != canonical_key
                )
                if not any_hotkey_key_pressed:
                    self._hotkey_pressed = False
                    self._send_message({"type": "release"})

            if canonical_key in self._pressed_keys:
                self._pressed_keys.remove(canonical_key)

    def _send_message(self, msg: dict) -> None:
        """Send a JSON message to the connected client."""
        if self._conn:
            try:
                data = json.dumps(msg) + "\n"
                self._conn.sendall(data.encode("utf-8"))
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    def _handle_client(self) -> None:
        """Handle messages from the connected client."""
        buffer = ""
        while self._running and self._conn:
            try:
                data = self._conn.recv(1024)
                if not data:
                    logger.info("Client disconnected")
                    break

                buffer += data.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line:
                        try:
                            msg = json.loads(line)
                            self._handle_message(msg)
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON: {e}")
            except Exception as e:
                if self._running:
                    logger.error(f"Error receiving: {e}")
                break

    def _handle_message(self, msg: dict) -> None:
        """Handle a message from the client."""
        msg_type = msg.get("type")
        if msg_type == "set_hotkey":
            hotkey = msg.get("hotkey")
            if hotkey:
                self._parse_hotkey(hotkey)
                self._send_message({"type": "ack"})
        elif msg_type == "stop":
            logger.info("Received stop command")
            self._running = False
        elif msg_type == "ping":
            self._send_message({"type": "pong"})

    def run(self) -> None:
        """Run the privileged listener."""
        import pynput

        keyboard = pynput.keyboard

        # Set up signal handlers
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Parse initial hotkey
        self._parse_hotkey(self.hotkey)

        # Set up socket
        self._setup_socket()

        # Start keyboard listener
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        logger.info("Keyboard listener started")

        self._running = True

        try:
            while self._running:
                # Wait for client connection (with timeout so we can check _running)
                self._socket.settimeout(1.0)
                try:
                    self._conn, addr = self._socket.accept()
                    logger.info("Client connected")
                    self._send_message({"type": "ready"})
                    self._handle_client()
                    self._conn.close()
                    self._conn = None
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error(f"Socket error: {e}")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources."""
        self._running = False

        if self._listener:
            self._listener.stop()
            self._listener.join()
            logger.info("Keyboard listener stopped")

        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass

        # Remove Unix socket file (TCP sockets don't need cleanup)
        if not self.is_tcp:
            try:
                Path(self.socket_address).unlink(missing_ok=True)
            except Exception:
                pass

        logger.info("Cleanup complete")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Privileged keyboard listener for VoiceType"
    )
    parser.add_argument(
        "--socket",
        type=str,
        required=True,
        help="Path to Unix socket for communication",
    )
    parser.add_argument(
        "--hotkey",
        type=str,
        required=True,
        help="Initial hotkey to listen for (e.g., '<pause>')",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )
    args = parser.parse_args()

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        level=args.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>privileged_listener</cyan> - {message}",
    )

    # Verify we have root privileges
    if os.geteuid() != 0:
        logger.warning(
            "Running without root privileges - keyboard capture may not work"
        )

    listener = PrivilegedListener(args.socket, args.hotkey)
    listener.run()


if __name__ == "__main__":
    main()
