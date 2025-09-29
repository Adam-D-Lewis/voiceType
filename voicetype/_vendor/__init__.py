"""Vendored packages used by voicetype."""

import sys
from pathlib import Path

__all__ = [
    "pynput",
]

# Add the lib directory to the path so we can import pynput
lib_path = str(Path(__file__).parent / "pynput/lib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

import pynput
