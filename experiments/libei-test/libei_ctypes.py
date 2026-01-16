"""
Minimal ctypes wrapper for libei - sender mode only.

This bypasses snegg to avoid the "Invalid event type" debug messages
caused by snegg calling ei_event_get_time() on all events.
"""

import ctypes
import ctypes.util
from ctypes import c_bool, c_char_p, c_int, c_uint32, c_uint64, c_void_p
from enum import IntEnum
from typing import Iterator, Optional

# Find and load libei
_libei_path = ctypes.util.find_library("ei")
if not _libei_path:
    # Try common paths
    for path in ["libei.so.1", "libei.so.0", "libei.so"]:
        try:
            _libei = ctypes.CDLL(path)
            break
        except OSError:
            continue
    else:
        raise ImportError("Could not find libei library")
else:
    _libei = ctypes.CDLL(_libei_path)


class EventType(IntEnum):
    """libei event types - ei_event_type enum."""

    CONNECT = 1
    DISCONNECT = 2
    SEAT_ADDED = 3
    SEAT_REMOVED = 4
    DEVICE_ADDED = 5
    DEVICE_REMOVED = 6
    DEVICE_PAUSED = 7
    DEVICE_RESUMED = 8
    # Receiver-side events (we don't use these in sender mode)
    KEYBOARD_MODIFIERS = 100
    FRAME = 101
    DEVICE_START_EMULATING = 102
    DEVICE_STOP_EMULATING = 103
    POINTER_MOTION = 200
    POINTER_MOTION_ABSOLUTE = 201
    POINTER_BUTTON = 202
    POINTER_SCROLL = 300
    POINTER_SCROLL_STOP = 301
    POINTER_SCROLL_CANCEL = 302
    POINTER_SCROLL_DISCRETE = 303
    KEYBOARD_KEY = 400
    TOUCH_DOWN = 500
    TOUCH_UP = 501
    TOUCH_MOTION = 502


class DeviceCapability(IntEnum):
    """libei device capabilities - these are bit flags, not sequential!"""

    POINTER = 1 << 0  # 1
    POINTER_ABSOLUTE = 1 << 1  # 2
    KEYBOARD = 1 << 2  # 4
    TOUCH = 1 << 3  # 8
    SCROLL = 1 << 4  # 16
    BUTTON = 1 << 5  # 32


# Define opaque pointer types
class EiPtr(c_void_p):
    """Opaque pointer to ei context."""

    pass


class EiSeatPtr(c_void_p):
    """Opaque pointer to ei_seat."""

    pass


class EiDevicePtr(c_void_p):
    """Opaque pointer to ei_device."""

    pass


class EiEventPtr(c_void_p):
    """Opaque pointer to ei_event."""

    pass


# Function signatures
# Context creation/destruction
_libei.ei_new_sender.argtypes = [c_void_p]  # ei_log_handler, can be NULL
_libei.ei_new_sender.restype = EiPtr

_libei.ei_unref.argtypes = [EiPtr]
_libei.ei_unref.restype = EiPtr

_libei.ei_setup_backend_fd.argtypes = [EiPtr, c_int]
_libei.ei_setup_backend_fd.restype = c_int

_libei.ei_get_fd.argtypes = [EiPtr]
_libei.ei_get_fd.restype = c_int

_libei.ei_dispatch.argtypes = [EiPtr]
_libei.ei_dispatch.restype = c_int

_libei.ei_configure_name.argtypes = [EiPtr, c_char_p]
_libei.ei_configure_name.restype = None

# Event handling
_libei.ei_get_event.argtypes = [EiPtr]
_libei.ei_get_event.restype = EiEventPtr

_libei.ei_peek_event.argtypes = [EiPtr]
_libei.ei_peek_event.restype = EiEventPtr

_libei.ei_event_unref.argtypes = [EiEventPtr]
_libei.ei_event_unref.restype = EiEventPtr

_libei.ei_event_get_type.argtypes = [EiEventPtr]
_libei.ei_event_get_type.restype = c_int

_libei.ei_event_get_seat.argtypes = [EiEventPtr]
_libei.ei_event_get_seat.restype = EiSeatPtr

_libei.ei_event_get_device.argtypes = [EiEventPtr]
_libei.ei_event_get_device.restype = EiDevicePtr

# Seat functions
_libei.ei_seat_get_name.argtypes = [EiSeatPtr]
_libei.ei_seat_get_name.restype = c_char_p

_libei.ei_seat_ref.argtypes = [EiSeatPtr]
_libei.ei_seat_ref.restype = EiSeatPtr

_libei.ei_seat_unref.argtypes = [EiSeatPtr]
_libei.ei_seat_unref.restype = EiSeatPtr

# ei_seat_bind_capabilities is variadic: (seat, cap1, cap2, ..., 0)
# Don't set argtypes for variadic functions - let ctypes infer
_libei.ei_seat_bind_capabilities.restype = c_int

# Device functions
_libei.ei_device_get_name.argtypes = [EiDevicePtr]
_libei.ei_device_get_name.restype = c_char_p

_libei.ei_device_has_capability.argtypes = [c_void_p, c_uint32]
_libei.ei_device_has_capability.restype = c_bool  # Returns bool (1 byte)

_libei.ei_device_ref.argtypes = [EiDevicePtr]
_libei.ei_device_ref.restype = EiDevicePtr

_libei.ei_device_unref.argtypes = [EiDevicePtr]
_libei.ei_device_unref.restype = EiDevicePtr

# Emulation functions (sender mode)
_libei.ei_device_start_emulating.argtypes = [EiDevicePtr, c_uint32]
_libei.ei_device_start_emulating.restype = None

_libei.ei_device_stop_emulating.argtypes = [EiDevicePtr]
_libei.ei_device_stop_emulating.restype = None

_libei.ei_device_frame.argtypes = [EiDevicePtr, c_uint64]
_libei.ei_device_frame.restype = None

_libei.ei_device_keyboard_key.argtypes = [EiDevicePtr, c_uint32, c_bool]
_libei.ei_device_keyboard_key.restype = None


class Event:
    """Wrapper for ei_event."""

    def __init__(self, ptr: EiEventPtr):
        self._ptr = ptr
        self._type: Optional[EventType] = None

    @property
    def event_type(self) -> EventType:
        if self._type is None:
            self._type = EventType(_libei.ei_event_get_type(self._ptr))
        return self._type

    @property
    def seat(self) -> Optional["Seat"]:
        seat_ptr = _libei.ei_event_get_seat(self._ptr)
        if seat_ptr:
            # Ref it so it survives event unref
            _libei.ei_seat_ref(seat_ptr)
            return Seat(seat_ptr)
        return None

    @property
    def device(self) -> Optional["Device"]:
        dev_ptr = _libei.ei_event_get_device(self._ptr)
        if dev_ptr:
            # Ref it so it survives event unref
            _libei.ei_device_ref(dev_ptr)
            return Device(dev_ptr)
        return None

    def __del__(self):
        if self._ptr:
            _libei.ei_event_unref(self._ptr)


class Seat:
    """Wrapper for ei_seat."""

    def __init__(self, ptr: EiSeatPtr):
        self._ptr = ptr

    @property
    def name(self) -> str:
        name = _libei.ei_seat_get_name(self._ptr)
        return name.decode("utf-8") if name else ""

    def bind(self, capabilities: tuple[DeviceCapability, ...]):
        """Bind capabilities to the seat."""
        # The C function is variadic: ei_seat_bind_capabilities(seat, cap1, cap2, ..., 0)
        # Pass each capability separately with 0 terminator
        for cap in capabilities:
            _libei.ei_seat_bind_capabilities(self._ptr, int(cap), 0)

    def __del__(self):
        if self._ptr:
            _libei.ei_seat_unref(self._ptr)


class Device:
    """Wrapper for ei_device."""

    def __init__(self, ptr: EiDevicePtr):
        self._ptr = ptr
        self._sequence = 0

    @property
    def name(self) -> str:
        name = _libei.ei_device_get_name(self._ptr)
        return name.decode("utf-8") if name else ""

    def has_capability(self, cap: DeviceCapability) -> bool:
        # c_bool returns Python bool directly
        return _libei.ei_device_has_capability(self._ptr, int(cap))

    @property
    def capabilities(self) -> set[DeviceCapability]:
        """Return set of device capabilities."""
        caps = set()
        for cap in DeviceCapability:
            if _libei.ei_device_has_capability(self._ptr, int(cap)):
                caps.add(cap)
        return caps

    def is_keyboard(self) -> bool:
        """Check if this device is a keyboard (by capability or name)."""
        # Check capability
        if self.has_capability(DeviceCapability.KEYBOARD):
            # Double-check with name since has_capability can be unreliable
            name = self.name.lower()
            if "keyboard" in name:
                return True
            # If name doesn't contain keyboard but cap says yes, trust it
            # unless it clearly says pointer
            if "pointer" not in name:
                return True
        # Fallback: check name
        return "keyboard" in self.name.lower()

    def start_emulating(self):
        """Start emulating input on this device."""
        self._sequence += 1
        _libei.ei_device_start_emulating(self._ptr, self._sequence)

    def stop_emulating(self):
        """Stop emulating input on this device."""
        _libei.ei_device_stop_emulating(self._ptr)

    def frame(self):
        """Send a frame event (sync point)."""
        _libei.ei_device_frame(self._ptr, 0)

    def keyboard_key(self, keycode: int, pressed: bool):
        """Send a keyboard key event."""
        _libei.ei_device_keyboard_key(self._ptr, keycode, pressed)

    def __del__(self):
        if self._ptr:
            _libei.ei_device_unref(self._ptr)


class Sender:
    """EI sender context - for sending input events."""

    def __init__(self, ptr: EiPtr):
        self._ptr = ptr

    @classmethod
    def create_for_fd(cls, fd: int, name: str = "libei-client") -> "Sender":
        """Create a sender context from a file descriptor."""
        ptr = _libei.ei_new_sender(None)
        if not ptr:
            raise RuntimeError("Failed to create ei sender context")

        _libei.ei_configure_name(ptr, name.encode("utf-8"))

        ret = _libei.ei_setup_backend_fd(ptr, fd)
        if ret != 0:
            _libei.ei_unref(ptr)
            raise RuntimeError(f"Failed to setup backend fd: {ret}")

        return cls(ptr)

    @property
    def fd(self) -> int:
        """Get the file descriptor for polling."""
        return _libei.ei_get_fd(self._ptr)

    def dispatch(self):
        """Dispatch pending events."""
        _libei.ei_dispatch(self._ptr)

    @property
    def events(self) -> Iterator[Event]:
        """Iterate over pending events."""
        while True:
            event_ptr = _libei.ei_get_event(self._ptr)
            if not event_ptr:
                break
            yield Event(event_ptr)

    def __del__(self):
        if self._ptr:
            _libei.ei_unref(self._ptr)
