"""Base protocol for keyboard backends.

This module defines the protocol that all keyboard backend implementations
must follow for typing text on different platforms.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class KeyboardBackend(Protocol):
    """Protocol for platform-specific keyboard typing implementations.

    All keyboard backends must implement this protocol to provide
    text typing functionality.
    """

    def type_text(self, text: str) -> None:
        """Type the given text.

        Args:
            text: The text to type
        """
        ...
