"""EIType keyboard backend for Wayland (GNOME/KDE with EI support).

This backend uses the eitype Python library to type text on Wayland compositors
that support the Extended Input (EI) protocol via the RemoteDesktop portal.
This includes GNOME 46+ and KDE Plasma 6+.
"""

from loguru import logger


class EitypeNotFoundError(RuntimeError):
    """Raised when eitype library is not available."""

    pass


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
        """Lazily connect to the EI portal."""
        if self._typer is None:
            logger.debug("EitypeKeyboard: connecting to RemoteDesktop portal")
            self._typer = self._EiType.connect_portal()
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
