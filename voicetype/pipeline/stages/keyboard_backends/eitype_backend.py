"""EIType keyboard backend for Wayland (GNOME/KDE with EI support).

This backend uses the eitype Python library to type text on Wayland compositors
that support the Extended Input (EI) protocol via the RemoteDesktop portal.
This includes GNOME 46+ and KDE Plasma 6+.
"""

from pathlib import Path

from loguru import logger

from voicetype.utils import get_app_data_dir


class EitypeNotFoundError(RuntimeError):
    """Raised when eitype library is not available."""

    pass


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
        """Lazily connect to the EI portal, using saved token if available."""
        if self._typer is None:
            saved_token = _load_token()
            logger.debug("EitypeKeyboard: connecting to RemoteDesktop portal")
            self._typer, new_token = self._EiType.connect_portal_with_token(saved_token)
            if new_token and new_token != saved_token:
                _save_token(new_token)
            logger.debug("EitypeKeyboard: connected to portal")
        return self._typer

    def type_text(self, text: str) -> None:
        """Type the given text using eitype.

        Args:
            text: The text to type

        Raises:
            RuntimeError: If eitype fails to type
        """
        logger.debug(f"EitypeKeyboard: typing {len(text)} characters")

        try:
            typer = self._get_typer()
            typer.type_text(text)
            logger.debug("EitypeKeyboard: typing complete")

        except Exception as e:
            raise RuntimeError(f"eitype failed to type text: {e}") from e
