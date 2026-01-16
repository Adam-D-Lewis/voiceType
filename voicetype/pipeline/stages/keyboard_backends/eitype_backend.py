"""EIType keyboard backend for Wayland (GNOME/KDE with EI support).

This backend uses the eitype Python library to type text on Wayland compositors
that support the Extended Input (EI) protocol via the RemoteDesktop portal.
This includes GNOME 46+ and KDE Plasma 6+.
"""

import time
from pathlib import Path

from loguru import logger

from voicetype.utils import get_app_data_dir

# Module-level cache for the eitype connection
# The RemoteDesktop portal connection is expensive and may not support
# multiple simultaneous connections, so we reuse a single typer instance.
_cached_typer = None


class EitypeNotFoundError(RuntimeError):
    """Raised when eitype library is not available."""

    pass


def clear_cached_connection() -> None:
    """Clear the cached eitype connection.

    Call this to force a new connection on the next type_text() call.
    Useful if the connection becomes stale or needs to be reset.

    Important: This explicitly closes the stale connection before clearing
    the cache. Without calling close(), the EI/DBus session remains open
    in a bad state and reconnection will hang or fail.
    """
    global _cached_typer
    if _cached_typer is not None:
        logger.debug("EitypeKeyboard: closing stale portal connection")
        try:
            _cached_typer.close()
        except Exception as e:
            logger.debug(
                f"EitypeKeyboard: error closing stale connection (ignored): {e}"
            )
        _cached_typer = None


def _get_token_path() -> Path:
    """Get the path to the eitype token file."""
    return get_app_data_dir() / "eitype_token"


def _load_token() -> str | None:
    """Load the saved eitype token if it exists."""
    token_path = _get_token_path()
    if token_path.exists():
        try:
            token = token_path.read_text().strip()
            if token:
                logger.debug(f"EitypeKeyboard: loaded token from {token_path}")
                return token
        except Exception as e:
            logger.warning(f"EitypeKeyboard: failed to load token: {e}")
    return None


def _save_token(token: str) -> None:
    """Save the eitype token for future sessions."""
    token_path = _get_token_path()
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token)
        logger.debug(f"EitypeKeyboard: saved token to {token_path}")
    except Exception as e:
        logger.warning(f"EitypeKeyboard: failed to save token: {e}")


class EitypeKeyboard:
    """Keyboard backend using eitype for Wayland GNOME/KDE.

    Uses the eitype Python library to type text via the Extended Input (EI)
    protocol. This provides native Wayland input support for compositors
    that implement the RemoteDesktop portal with EI support.
    """

    def __init__(self):
        """Initialize the eitype keyboard backend.

        Raises:
            EitypeNotFoundError: If eitype library is not installed
        """
        try:
            from eitype import EiType

            self._EiType = EiType
        except ImportError as e:
            raise EitypeNotFoundError(
                "eitype library is required for typing on Wayland with GNOME or KDE.\n\n"
                "eitype uses the Extended Input (EI) protocol via the RemoteDesktop portal "
                "for native Wayland keyboard input.\n\n"
                "Install eitype from: https://github.com/Adam-D-Lewis/eitype\n\n"
                "If using pixi: pixi install (eitype is included in Linux dependencies)"
            ) from e

        self._typer = None
        logger.debug("EitypeKeyboard: eitype library loaded")

    def _get_typer(self):
        """Lazily connect to the EI portal, using saved token if available.

        Uses a module-level cached connection to avoid hanging on subsequent calls.
        The RemoteDesktop portal may not support multiple simultaneous connections.
        """
        global _cached_typer

        if _cached_typer is not None:
            logger.debug("EitypeKeyboard: reusing cached portal connection")
            return _cached_typer

        saved_token = _load_token()
        logger.debug("EitypeKeyboard: connecting to RemoteDesktop portal")
        typer, new_token = self._EiType.connect_portal_with_token(saved_token)
        if new_token and new_token != saved_token:
            _save_token(new_token)
        logger.debug("EitypeKeyboard: connected to portal")

        # Cache for subsequent calls
        _cached_typer = typer
        return typer

    def type_text(self, text: str) -> None:
        """Type the given text using eitype.

        Args:
            text: The text to type

        Raises:
            RuntimeError: If eitype fails to type after retry
        """
        logger.debug(f"EitypeKeyboard: typing {len(text)} characters")

        try:
            typer = self._get_typer()
            typer.type_text(text)
            logger.debug("EitypeKeyboard: typing complete")

        except Exception as e:
            # Connection may be stale - close it properly and retry once
            logger.warning(
                f"EitypeKeyboard: typing failed, retrying with fresh connection: {e}"
            )
            clear_cached_connection()

            # Give the portal time to clean up the session before reconnecting.
            # Without this delay, the new connection may fail because the old
            # EI session state hasn't been fully released by the compositor.
            time.sleep(0.1)

            try:
                typer = self._get_typer()
                typer.type_text(text)
                logger.debug("EitypeKeyboard: typing complete (after retry)")
            except Exception as retry_e:
                raise RuntimeError(
                    f"eitype failed to type text: {retry_e}"
                ) from retry_e
