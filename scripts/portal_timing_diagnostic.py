#!/usr/bin/env python3
"""Diagnostic script to measure XDG Portal GlobalShortcuts timing signatures.

This script captures the precise timing of Activated/Deactivated signals from
the portal to help determine optimal debounce thresholds for key repeat handling.

Usage:
    pixi run python scripts/portal_timing_diagnostic.py

Instructions:
    1. Run the script - it will bind a shortcut (you may see a system dialog)
    2. Press and HOLD your hotkey for various durations (1s, 2s, 3s)
    3. Do quick taps as well
    4. Press Ctrl+C to stop and see statistics

The script logs:
    - Timestamp of each Activated/Deactivated signal
    - Time delta from previous signal
    - Running statistics on key repeat intervals
"""

import asyncio
import secrets
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TimingStats:
    """Collected timing statistics."""

    # All deltas between consecutive signals (in ms)
    all_deltas_ms: list[float] = field(default_factory=list)

    # Deltas from Deactivated -> Activated (key repeat indicator)
    deactivated_to_activated_ms: list[float] = field(default_factory=list)

    # Deltas from Activated -> Deactivated
    activated_to_deactivated_ms: list[float] = field(default_factory=list)

    # Time from first Activated to first Deactivated in each press session
    initial_hold_durations_ms: list[float] = field(default_factory=list)

    # Number of key repeat cycles detected per press session
    repeat_counts: list[int] = field(default_factory=list)

    def summary(self) -> str:
        """Generate a summary of collected statistics."""
        lines = [
            "\n" + "=" * 60,
            "TIMING STATISTICS SUMMARY",
            "=" * 60,
        ]

        if self.deactivated_to_activated_ms:
            vals = self.deactivated_to_activated_ms
            lines.append(f"\nDeactivated -> Activated (key repeat gaps):")
            lines.append(f"  Count: {len(vals)}")
            lines.append(f"  Min:   {min(vals):.1f} ms")
            lines.append(f"  Max:   {max(vals):.1f} ms")
            lines.append(f"  Avg:   {sum(vals)/len(vals):.1f} ms")
            # Percentiles
            sorted_vals = sorted(vals)
            p50 = sorted_vals[len(sorted_vals) // 2]
            p90 = (
                sorted_vals[int(len(sorted_vals) * 0.9)]
                if len(sorted_vals) >= 10
                else sorted_vals[-1]
            )
            p99 = (
                sorted_vals[int(len(sorted_vals) * 0.99)]
                if len(sorted_vals) >= 100
                else sorted_vals[-1]
            )
            lines.append(f"  P50:   {p50:.1f} ms")
            lines.append(f"  P90:   {p90:.1f} ms")
            lines.append(f"  P99:   {p99:.1f} ms")
        else:
            lines.append("\nNo Deactivated -> Activated transitions recorded.")
            lines.append("(This happens with very short key presses or no key repeats)")

        if self.activated_to_deactivated_ms:
            vals = self.activated_to_deactivated_ms
            lines.append(f"\nActivated -> Deactivated gaps:")
            lines.append(f"  Count: {len(vals)}")
            lines.append(f"  Min:   {min(vals):.1f} ms")
            lines.append(f"  Max:   {max(vals):.1f} ms")
            lines.append(f"  Avg:   {sum(vals)/len(vals):.1f} ms")

        if self.repeat_counts:
            lines.append(f"\nKey repeat cycles per press session:")
            lines.append(f"  Sessions: {len(self.repeat_counts)}")
            lines.append(f"  Min repeats: {min(self.repeat_counts)}")
            lines.append(f"  Max repeats: {max(self.repeat_counts)}")
            lines.append(
                f"  Avg repeats: {sum(self.repeat_counts)/len(self.repeat_counts):.1f}"
            )

        lines.append("\n" + "=" * 60)
        lines.append("RECOMMENDATION")
        lines.append("=" * 60)

        if self.deactivated_to_activated_ms:
            max_gap = max(self.deactivated_to_activated_ms)
            # Recommend threshold that's 2x the max observed gap for safety
            recommended = max_gap * 2
            # But cap it at something reasonable
            recommended = min(recommended, 200)
            recommended = max(recommended, 50)  # Minimum 50ms
            lines.append(f"\nMax observed key repeat gap: {max_gap:.1f} ms")
            lines.append(f"Recommended debounce threshold: {recommended:.0f} ms")
            lines.append(f"  (This is 2x the max gap, capped at 50-200ms range)")
            lines.append(f"\nCurrent threshold in code: 600 ms")
            lines.append(f"Potential latency reduction: {600 - recommended:.0f} ms")
        else:
            lines.append("\nNot enough data to make a recommendation.")
            lines.append(
                "Try holding the key down for 1-2 seconds to trigger key repeat."
            )

        return "\n".join(lines)


class PortalTimingDiagnostic:
    """Diagnostic tool for measuring portal signal timing."""

    PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
    PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
    SHORTCUTS_INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
    REQUEST_INTERFACE = "org.freedesktop.portal.Request"

    def __init__(self):
        self._bus = None
        self._session_handle: Optional[str] = None
        self._shortcut_id = "timing-diagnostic"
        self._shortcuts_iface = None
        self._running = False

        # Timing tracking
        self._last_signal_time: Optional[float] = None
        self._last_signal_type: Optional[str] = None  # "activated" or "deactivated"
        self._session_start_time: Optional[float] = None
        self._session_repeat_count = 0
        self._in_press_session = False

        self.stats = TimingStats()

    def _on_activated(
        self, session_handle: str, shortcut_id: str, timestamp: int, options: dict
    ):
        """Handle Activated signal."""
        now = time.perf_counter() * 1000  # Convert to ms

        delta_str = ""
        if self._last_signal_time is not None:
            delta = now - self._last_signal_time
            self.stats.all_deltas_ms.append(delta)

            if self._last_signal_type == "deactivated":
                self.stats.deactivated_to_activated_ms.append(delta)
                self._session_repeat_count += 1
                delta_str = f" (delta from Deactivated: {delta:.1f} ms) [KEY REPEAT #{self._session_repeat_count}]"
            else:
                delta_str = f" (delta: {delta:.1f} ms)"

        if not self._in_press_session:
            self._in_press_session = True
            self._session_start_time = now
            self._session_repeat_count = 0
            print(f"\n--- NEW PRESS SESSION ---")

        print(f"[{now:.1f}] ACTIVATED{delta_str}")

        self._last_signal_time = now
        self._last_signal_type = "activated"

    def _on_deactivated(
        self, session_handle: str, shortcut_id: str, timestamp: int, options: dict
    ):
        """Handle Deactivated signal."""
        now = time.perf_counter() * 1000

        delta_str = ""
        if self._last_signal_time is not None:
            delta = now - self._last_signal_time
            self.stats.all_deltas_ms.append(delta)

            if self._last_signal_type == "activated":
                self.stats.activated_to_deactivated_ms.append(delta)
                delta_str = f" (delta from Activated: {delta:.1f} ms)"
            else:
                delta_str = f" (delta: {delta:.1f} ms)"

        print(f"[{now:.1f}] DEACTIVATED{delta_str}")

        # Check if this might be a real release (we'll know for sure if no Activated follows)
        # For now, just track that we're potentially ending a session
        if self._in_press_session and self._session_start_time:
            duration = now - self._session_start_time
            self.stats.initial_hold_durations_ms.append(duration)

        self._last_signal_time = now
        self._last_signal_type = "deactivated"

        # Schedule a check for real release
        asyncio.get_event_loop().call_later(0.7, self._check_session_end, now)

    def _check_session_end(self, deactivated_time: float):
        """Check if a press session has ended (no Activated after Deactivated)."""
        if (
            self._last_signal_type == "deactivated"
            and self._last_signal_time == deactivated_time
        ):
            # No Activated arrived after this Deactivated - it was a real release
            if self._in_press_session:
                self.stats.repeat_counts.append(self._session_repeat_count)
                print(f"--- SESSION END (repeats: {self._session_repeat_count}) ---\n")
                self._in_press_session = False
                self._session_repeat_count = 0

    async def setup(self) -> bool:
        """Set up the portal connection and bind shortcut."""
        try:
            from dbus_next import Variant
            from dbus_next import introspection as intr
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType

            print("Connecting to D-Bus session bus...")
            self._bus = await MessageBus(bus_type=BusType.SESSION).connect()

            # Define GlobalShortcuts interface
            shortcuts_introspection = intr.Node.parse(
                """
            <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
             "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
            <node>
              <interface name="org.freedesktop.portal.GlobalShortcuts">
                <method name="CreateSession">
                  <arg type="a{sv}" name="options" direction="in"/>
                  <arg type="o" name="handle" direction="out"/>
                </method>
                <method name="BindShortcuts">
                  <arg type="o" name="session_handle" direction="in"/>
                  <arg type="a(sa{sv})" name="shortcuts" direction="in"/>
                  <arg type="s" name="parent_window" direction="in"/>
                  <arg type="a{sv}" name="options" direction="in"/>
                  <arg type="o" name="handle" direction="out"/>
                </method>
                <signal name="Activated">
                  <arg type="o" name="session_handle"/>
                  <arg type="s" name="shortcut_id"/>
                  <arg type="t" name="timestamp"/>
                  <arg type="a{sv}" name="options"/>
                </signal>
                <signal name="Deactivated">
                  <arg type="o" name="session_handle"/>
                  <arg type="s" name="shortcut_id"/>
                  <arg type="t" name="timestamp"/>
                  <arg type="a{sv}" name="options"/>
                </signal>
              </interface>
            </node>
            """
            )

            proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, self.PORTAL_OBJECT_PATH, shortcuts_introspection
            )
            self._shortcuts_iface = proxy.get_interface(self.SHORTCUTS_INTERFACE)

            sender = self._bus.unique_name.replace(":", "").replace(".", "_")

            # Create session
            print("Creating GlobalShortcuts session...")
            session_handle = await self._create_session(sender)
            if not session_handle:
                return False
            self._session_handle = session_handle
            print(f"Session created: {session_handle}")

            # Bind shortcut
            print("Binding test shortcut (you may see a system dialog)...")
            success = await self._bind_shortcut(sender)
            if not success:
                return False

            # Subscribe to signals
            self._shortcuts_iface.on_activated(self._on_activated)
            self._shortcuts_iface.on_deactivated(self._on_deactivated)

            print("\n" + "=" * 60)
            print("READY - Press and hold your hotkey to measure timing")
            print("Try: quick taps, 1s holds, 2s holds, 3s holds")
            print("Press Ctrl+C to stop and see statistics")
            print("=" * 60 + "\n")

            return True

        except ImportError:
            print("ERROR: dbus-next not installed. Run: pip install dbus-next")
            return False
        except Exception as e:
            print(f"ERROR: Failed to setup portal: {e}")
            return False

    async def _create_session(self, sender: str) -> Optional[str]:
        """Create a GlobalShortcuts session."""
        from dbus_next import Variant
        from dbus_next import introspection as intr

        request_token = f"diag_{secrets.token_hex(8)}"
        expected_request_path = (
            f"/org/freedesktop/portal/desktop/request/{sender}/{request_token}"
        )

        response_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_response(response_code, results):
            if response_future.done():
                return
            if response_code == 0:
                session_handle = results.get("session_handle")
                if session_handle:
                    handle_value = (
                        session_handle.value
                        if hasattr(session_handle, "value")
                        else session_handle
                    )
                    response_future.set_result(handle_value)
                else:
                    response_future.set_exception(
                        Exception("No session_handle in response")
                    )
            else:
                response_future.set_exception(
                    Exception(f"CreateSession failed: {response_code}")
                )

        request_introspection = intr.Node.parse(
            """
        <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
         "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
        <node>
          <interface name="org.freedesktop.portal.Request">
            <signal name="Response">
              <arg type="u" name="response"/>
              <arg type="a{sv}" name="results"/>
            </signal>
          </interface>
        </node>
        """
        )

        try:
            request_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, expected_request_path, request_introspection
            )
            request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
            request_iface.on_response(on_response)
        except Exception:
            pass

        options = {
            "handle_token": Variant("s", request_token),
            "session_handle_token": Variant(
                "s", f"diag_session_{secrets.token_hex(4)}"
            ),
        }

        await self._shortcuts_iface.call_create_session(options)

        try:
            return await asyncio.wait_for(response_future, timeout=30.0)
        except asyncio.TimeoutError:
            print("Timeout waiting for CreateSession response")
            return None

    async def _bind_shortcut(self, sender: str) -> bool:
        """Bind a test shortcut."""
        from dbus_next import Variant
        from dbus_next import introspection as intr

        request_token = f"bind_{secrets.token_hex(8)}"
        expected_request_path = (
            f"/org/freedesktop/portal/desktop/request/{sender}/{request_token}"
        )

        response_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def on_response(response_code, results):
            if response_future.done():
                return
            if response_code in (0, 2):  # 0=success, 2=GNOME quirk
                shortcuts = results.get("shortcuts", [])
                if shortcuts:
                    try:
                        shortcuts_list = (
                            shortcuts.value
                            if hasattr(shortcuts, "value")
                            else shortcuts
                        )
                        for shortcut in shortcuts_list:
                            props = shortcut[1]
                            trigger = props.get("trigger_description")
                            if trigger:
                                trigger_val = (
                                    trigger.value
                                    if hasattr(trigger, "value")
                                    else trigger
                                )
                                print(f"Shortcut bound to: {trigger_val}")
                    except Exception:
                        pass
                response_future.set_result(True)
            elif response_code == 1:
                print("User cancelled shortcut binding")
                response_future.set_result(False)
            else:
                response_future.set_exception(
                    Exception(f"BindShortcuts failed: {response_code}")
                )

        request_introspection = intr.Node.parse(
            """
        <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
         "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
        <node>
          <interface name="org.freedesktop.portal.Request">
            <signal name="Response">
              <arg type="u" name="response"/>
              <arg type="a{sv}" name="results"/>
            </signal>
          </interface>
        </node>
        """
        )

        try:
            request_proxy = self._bus.get_proxy_object(
                self.PORTAL_BUS_NAME, expected_request_path, request_introspection
            )
            request_iface = request_proxy.get_interface(self.REQUEST_INTERFACE)
            request_iface.on_response(on_response)
        except Exception:
            pass

        shortcuts = [
            [
                self._shortcut_id,
                {
                    "description": Variant("s", "Timing diagnostic test shortcut"),
                    "preferred_trigger": Variant("s", "Pause"),
                },
            ]
        ]

        options = {"handle_token": Variant("s", request_token)}

        await self._shortcuts_iface.call_bind_shortcuts(
            self._session_handle, shortcuts, "", options
        )

        try:
            return await asyncio.wait_for(response_future, timeout=60.0)
        except asyncio.TimeoutError:
            print("Timeout waiting for BindShortcuts response")
            return False

    async def run(self):
        """Main run loop."""
        if not await self.setup():
            return

        self._running = True

        # Set up signal handler for clean exit
        def handle_signal(sig, frame):
            self._running = False
            print("\n\nStopping...")

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        # Run until interrupted
        while self._running:
            await asyncio.sleep(0.1)

        # Print statistics
        print(self.stats.summary())

        # Cleanup
        if self._bus:
            self._bus.disconnect()


async def main():
    diagnostic = PortalTimingDiagnostic()
    await diagnostic.run()


if __name__ == "__main__":
    asyncio.run(main())
