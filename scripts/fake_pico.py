#!/usr/bin/env python3
"""Pretend to be the Pico: press voiceType's remote button from a terminal.

Tests the desktop side of the remote trigger (network, firewall, TLS, token,
transcription) without any hardware. Needs only Python 3.11+, so it can run on
any machine that can reach voiceType, e.g. the Chromebook's Linux terminal:

    python fake_pico.py --host nirvana --hold 3    # record 3 seconds, print the text
    python fake_pico.py --host nirvana             # Enter presses/releases the button

It needs voiceType's certificate and token (from `voicetype remote-setup`); pass
--cert and --token-file if they aren't in ~/.config/voicetype/remote/.
"""

import argparse
import asyncio
import json
import ssl
import sys
from pathlib import Path

DEFAULT_DIR = Path.home() / ".config" / "voicetype" / "remote"


async def run(args) -> int:
    token = args.token or args.token_file.read_text().strip()
    context = ssl.create_default_context(cafile=str(args.cert))
    reader, writer = await asyncio.open_connection(
        args.host, args.port, ssl=context, server_hostname=args.tls_name
    )

    async def send(**message):
        writer.write((json.dumps(message) + "\n").encode())
        await writer.drain()

    await send(type="hello", token=token, name="fake-pico")
    reply = json.loads(await reader.readline() or b"{}")
    if reply.get("type") != "welcome":
        print(f"voiceType refused the connection: {reply}", file=sys.stderr)
        return 1
    print(f"Connected to {args.host}:{args.port}")

    got_text = asyncio.Event()

    async def receive():
        while line := await reader.readline():
            message = json.loads(line)
            if message.get("type") == "text":
                print(f"Text: {message['text']!r}")
                got_text.set()
            elif message.get("type") == "state":
                print(f"Button {message.get('button')}: {message.get('state')}")
            elif message.get("type") == "error":
                print(f"Error from voiceType: {message.get('message')}")
        print("voiceType closed the connection")

    async def keep_alive():
        while True:
            await asyncio.sleep(1)
            await send(type="ping")

    async def one_dictation():
        await send(type="down", button=args.button)
        print(f"Recording for {args.hold:g}s, speak now...")
        await asyncio.sleep(args.hold)
        await send(type="up", button=args.button)
        print("Released, waiting for the transcription...")
        await asyncio.wait_for(got_text.wait(), args.wait)

    async def interactive():
        print("Enter presses the button, Enter again releases it. Ctrl+D quits.")
        loop = asyncio.get_running_loop()
        held = False
        while await loop.run_in_executor(None, sys.stdin.readline):
            held = not held
            await send(type="down" if held else "up", button=args.button)
            print("Button down, speak..." if held else "Button up")

    receiver = asyncio.create_task(receive())
    pinger = asyncio.create_task(keep_alive())
    action = asyncio.create_task(
        one_dictation() if args.hold is not None else interactive()
    )
    try:
        done, _ = await asyncio.wait(
            {receiver, action}, return_when=asyncio.FIRST_COMPLETED
        )
        if action in done:
            action.result()  # Raise any error (e.g. no text in time)
        return 0
    except TimeoutError:
        print(f"No text came back within {args.wait:g}s", file=sys.stderr)
        return 1
    finally:
        for task in (receiver, pinger, action):
            task.cancel()
        writer.close()


def main():
    parser = argparse.ArgumentParser(
        description="Act like the Pico: press voiceType's remote button."
    )
    parser.add_argument("--host", required=True, help="Where voiceType runs")
    parser.add_argument("--port", type=int, default=8684)
    parser.add_argument("--button", default="main", help="Button name (default main)")
    parser.add_argument(
        "--hold",
        type=float,
        metavar="SECONDS",
        help="Hold the button this long, print the text, and exit",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=30,
        metavar="SECONDS",
        help="With --hold: how long to wait for the text (default 30)",
    )
    parser.add_argument("--cert", type=Path, default=DEFAULT_DIR / "cert.pem")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_DIR / "token")
    parser.add_argument("--token", help="The token itself, instead of --token-file")
    parser.add_argument(
        "--tls-name",
        default="voicetype",
        help="Name to check the certificate against (default voicetype)",
    )
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
