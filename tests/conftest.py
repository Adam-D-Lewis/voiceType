"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture(scope="function", autouse=True)
def cleanup_sounddevice():
    """Cleanup sounddevice/PortAudio after each test to prevent thread corruption.

    This fixture ensures that PortAudio threads are properly terminated after tests
    that use sounddevice, preventing segfaults in subsequent tests that use threading.
    This is particularly important with Python 3.13 which has stricter thread safety.
    """
    yield
    # Cleanup after test
    try:
        import sounddevice as sd

        # Terminate PortAudio to cleanup all threads
        sd._terminate()
        sd._initialize()
    except Exception:
        # Silently ignore if sounddevice wasn't imported or already terminated
        pass
