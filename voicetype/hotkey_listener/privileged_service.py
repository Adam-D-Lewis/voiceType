#!/usr/bin/env python3
"""Privileged service that runs as a separate process for keyboard I/O.

On Linux, keyboard capture requires root access to read from /dev/input, and
reliable keyboard typing (especially on Wayland) benefits from running with
elevated privileges. However, pystray (the system tray library) needs access
to the user's D-Bus session. Running the entire app as root breaks pystray.

Solution: Run this service as a separate process with sudo, while the main
application (with the tray icon) runs as the regular user. Communication
happens over Unix domain sockets.

This service:
- Uses direct evdev access for keyboard capture (works on X11 and Wayland)
- Uses pynput for keyboard typing (works reliably as root on all platforms)

Note: This is only needed on Linux. On Windows and macOS, pynput works
without elevated privileges for both capture and typing.

Usage (Linux only):
    sudo python -m voicetype.hotkey_listener.privileged_service \\
        --socket /run/user/1000/voicetype-hotkey.sock --hotkey "<pause>"
"""

import argparse
import json
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Add the project root to the path so we can import voicetype modules
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from loguru import logger

from voicetype.hotkey_listener.evdev_listener import (
    EvdevKeyboardListener,
    parse_hotkey,
)


def is_tcp_address(address: str) -> bool:
    """Check if the address is a TCP address (host:port format)."""
    return ":" in address and not address.startswith("/")


class PrivilegedService:
    """Privileged service for keyboard capture and typing over sockets.

    Uses direct evdev access for keyboard capture (works on both X11 and
    Wayland without requiring dumpkeys) and pynput for keyboard typing
    (works reliably as root).
    """

    def __init__(self, socket_address: str, hotkey: str):
        """Initialize the service.

        Args:
            socket_address: Socket address (Unix path or host:port for TCP)
            hotkey: Initial hotkey to listen for
        """
        self.socket_address = socket_address
        self.is_tcp = is_tcp_address(socket_address)
        self.hotkey = hotkey
        self._socket: Optional[socket.socket] = None
        self._conn: Optional[socket.socket] = None
        self._evdev_listener: Optional[EvdevKeyboardListener] = None
        self._running = False
        self._hotkey_codes: set[int] = set()
        self._pressed_keys: set[int] = set()
        self._hotkey_pressed: bool = False
        self._lock = threading.Lock()
        # Display environment for X11 typing
        self._display: str = ""
        self._xauthority: str = ""
        self._wayland_display: str = ""

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
        """Parse the hotkey string into a set of evdev key codes."""
        try:
            self._hotkey_codes = parse_hotkey(hotkey)
            self.hotkey = hotkey
            logger.info(f"Hotkey set to: {hotkey} -> codes {self._hotkey_codes}")
        except ValueError as e:
            logger.error(f"Error parsing hotkey: {e}")

    def _on_press(self, key_code: int) -> None:
        """Handle key press events.

        Args:
            key_code: The evdev key code that was pressed.
        """
        logger.debug(f"Key press detected: code={key_code}")
        if not self._hotkey_codes:
            return

        with self._lock:
            self._pressed_keys.add(key_code)
            logger.debug(
                f"Pressed keys: {self._pressed_keys}, hotkey codes: {self._hotkey_codes}"
            )

            if not self._hotkey_pressed and self._hotkey_codes.issubset(
                self._pressed_keys
            ):
                self._hotkey_pressed = True
                logger.info("Hotkey pressed!")
                self._send_message({"type": "press"})

    def _on_release(self, key_code: int) -> None:
        """Handle key release events.

        Args:
            key_code: The evdev key code that was released.
        """
        if not self._hotkey_codes:
            return

        with self._lock:
            if self._hotkey_pressed and key_code in self._hotkey_codes:
                # Check if any other hotkey keys are still pressed
                remaining_hotkey_keys = self._hotkey_codes - {key_code}
                still_pressed = remaining_hotkey_keys & self._pressed_keys
                if not still_pressed:
                    self._hotkey_pressed = False
                    logger.info("Hotkey released!")
                    self._send_message({"type": "release"})

            self._pressed_keys.discard(key_code)

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
        elif msg_type == "set_display":
            # Store display environment for X11 typing
            self._display = msg.get("display", "")
            self._xauthority = msg.get("xauthority", "")
            self._wayland_display = msg.get("wayland_display", "")
            logger.info(
                f"Display info received: DISPLAY={self._display}, "
                f"XAUTHORITY={self._xauthority}, WAYLAND_DISPLAY={self._wayland_display}"
            )
        elif msg_type == "type_text":
            text = msg.get("text", "")
            char_delay = msg.get("char_delay", 0.001)
            self._type_text(text, char_delay)
        elif msg_type == "stop":
            logger.info("Received stop command")
            self._running = False
        elif msg_type == "ping":
            self._send_message({"type": "pong"})

    def _type_text(self, text: str, char_delay: float) -> None:
        """Type text using pynput keyboard controller.

        Args:
            text: The text to type.
            char_delay: Delay in seconds between each character.
        """
        if not text:
            logger.debug("No text to type")
            self._send_message({"type": "type_complete"})
            return

        logger.debug(f"Typing text: {text[:50]}{'...' if len(text) > 50 else ''}")

        # Set up display environment for X11 access
        # This is needed because the privileged service runs as root and
        # doesn't have the user's display environment by default
        if self._display:
            os.environ["DISPLAY"] = self._display
            logger.debug(f"Set DISPLAY={self._display}")
        if self._xauthority:
            os.environ["XAUTHORITY"] = self._xauthority
            logger.debug(f"Set XAUTHORITY={self._xauthority}")

        try:
            import pynput.keyboard

            keyboard = pynput.keyboard.Controller()
            for i, char in enumerate(text):
                keyboard.type(char)
                if char_delay > 0 and i < len(text) - 1:
                    time.sleep(char_delay)
            logger.debug("Typing complete")
            self._send_message({"type": "type_complete"})
        except Exception as e:
            logger.error(f"Error typing text: {e}")
            self._send_message({"type": "error", "message": f"Typing failed: {e}"})

    def run(self) -> None:
        """Run the privileged service."""

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

        # Start evdev keyboard listener
        self._evdev_listener = EvdevKeyboardListener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._evdev_listener.start()
        logger.info("Evdev keyboard listener started")

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

        if self._evdev_listener:
            self._evdev_listener.stop()
            logger.info("Evdev keyboard listener stopped")

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
        description="Privileged keyboard service for VoiceType"
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
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>privileged_service</cyan> - {message}",
    )

    # Verify we have root privileges
    if os.geteuid() != 0:
        logger.warning(
            "Running without root privileges - keyboard capture and typing may not work"
        )

    service = PrivilegedService(args.socket, args.hotkey)
    service.run()


if __name__ == "__main__":
    main()
