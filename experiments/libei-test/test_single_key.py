#!/usr/bin/env python3
"""
Minimal test - just press and release the 'a' key once.
"""

import select
import time

import snegg.ei as ei
import snegg.oeffis as oeffis

KEY_A = 30  # evdev keycode for 'a'


def main():
    print("Connecting to RemoteDesktop portal...")
    portal = oeffis.Oeffis.create(devices=oeffis.DeviceType.KEYBOARD)

    poll = select.poll()
    poll.register(portal.fd)

    while poll.poll():
        try:
            if portal.dispatch():
                print("Connected to IS!")
                break
        except oeffis.SessionClosedError as e:
            print(f"Session closed: {e.message}")
            return
        except oeffis.DisconnectedError as e:
            print(f"Disconnected: {e.message}")
            return

    # Create sender context
    ctx = ei.Sender.create_for_fd(fd=portal.is_fd, name="test-single-key")

    print("Waiting for device... Click on target window now!")
    print("Will type 'a' in 3 seconds...")
    time.sleep(3)

    poll2 = select.poll()
    poll2.register(ctx.fd)

    while poll2.poll(1000):
        ctx.dispatch()
        for event in ctx.events:
            print(f"Event: {event.event_type.name}")

            if event.event_type == ei.EventType.SEAT_ADDED:
                seat = event.seat
                if seat:
                    print(f"Binding to seat: {seat.name}")
                    seat.bind((ei.DeviceCapability.KEYBOARD,))

            elif event.event_type == ei.EventType.DEVICE_RESUMED:
                device = event.device
                if device and ei.DeviceCapability.KEYBOARD in device.capabilities:
                    print(f"Device resumed: {device.name}")
                    print("Pressing 'a' key...")

                    # Exactly like the snegg example
                    device.start_emulating().keyboard_key(
                        KEY_A, True
                    ).frame().keyboard_key(KEY_A, False).frame().stop_emulating()

                    print("Done!")
                    return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted")
