"""Trigger event types for pipeline execution.

Trigger events represent different ways a pipeline can be triggered and provide
a uniform interface for waiting for trigger completion.
"""

import threading
import time
from typing import Optional


class TriggerEvent:
    """Base class for different trigger types."""

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for trigger to complete (e.g., key release).

        Args:
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True if trigger completed normally, False if timeout occurred
        """
        raise NotImplementedError


class HotkeyTriggerEvent(TriggerEvent):
    """Hotkey-specific trigger that waits for key release.

    This trigger is activated when a hotkey is pressed and completes when
    the key is released. Used for press-and-hold style interactions.
    """

    def __init__(self):
        """Initialize a new hotkey trigger event."""
        self.press_time = time.time()
        self.release_event = threading.Event()

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Block until key is released or timeout.

        Args:
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True if key was released, False if timeout occurred
        """
        return self.release_event.wait(timeout)

    def signal_release(self):
        """Signal that the hotkey has been released.

        Called by the hotkey manager when the key is released.
        """
        self.release_event.set()


class TimerTriggerEvent(TriggerEvent):
    """Timer-based trigger that waits for fixed duration.

    This trigger completes after a predetermined amount of time. Used for
    time-based recording or processing.
    """

    def __init__(self, duration: float):
        """Initialize a new timer trigger event.

        Args:
            duration: Duration to wait in seconds
        """
        self.duration = duration

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for configured duration (or timeout, whichever is less).

        Args:
            timeout: Maximum time to wait in seconds, or None for no timeout

        Returns:
            True (always completes successfully unless interrupted)
        """
        wait_time = self.duration
        if timeout is not None:
            wait_time = min(self.duration, timeout)
        time.sleep(wait_time)
        return True


class ProgrammaticTriggerEvent(TriggerEvent):
    """Programmatic trigger with no automatic completion.

    This trigger is used when pipelines are invoked programmatically (e.g., from
    tests or API calls) and don't have an inherent completion signal.
    """

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Return immediately (no wait).

        Args:
            timeout: Ignored for programmatic triggers

        Returns:
            True (always)
        """
        return True
