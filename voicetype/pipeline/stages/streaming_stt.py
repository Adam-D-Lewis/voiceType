"""Streaming speech-to-text stage using Kyutai's delayed-streams-modeling server.

This stage captures audio from the microphone, streams it to a Kyutai DSM Rust
server via WebSocket, and types transcribed words in real-time as they arrive.
All three operations (capture, stream, type) run concurrently while the PTT
button is held.
"""

import asyncio
import threading
from typing import Optional

import msgpack
import numpy as np
import sounddevice as sd
import websockets
from loguru import logger
from pydantic import BaseModel, Field

from voicetype.pipeline import Resource
from voicetype.pipeline.context import PipelineContext
from voicetype.pipeline.stage_registry import STAGE_REGISTRY, PipelineStage
from voicetype.pipeline.stages.keyboard_backends import create_keyboard_backend


class StreamingSTTConfig(BaseModel):
    """Configuration for StreamingSTT stage."""

    server_url: str = Field(
        default="ws://127.0.0.1:8080",
        description="WebSocket URL of the Kyutai DSM Rust server (without /api/asr-streaming path)",
    )
    api_key: str = Field(
        default="public_token",
        description="API key for the Kyutai server",
    )
    sample_rate: int = Field(
        default=24000,
        gt=0,
        description="Audio sample rate in Hz (must match server expectation)",
    )
    block_size: int = Field(
        default=1920,
        gt=0,
        description="Audio block size in samples (1920 = 80ms at 24kHz)",
    )
    max_duration: float = Field(
        default=120.0,
        gt=0,
        description="Maximum streaming duration in seconds",
    )
    keyboard_backend: str = Field(
        default="auto",
        description="Keyboard backend to use: auto, pynput, wtype, or eitype",
    )
    char_delay: float = Field(
        default=0.001,
        ge=0,
        description="Delay in seconds between each character (pynput backend only)",
    )
    device_name: Optional[str] = Field(
        default=None,
        description="Optional audio device name (None for system default)",
    )


@STAGE_REGISTRY.register
class StreamingSTT(PipelineStage[None, None]):
    """Stream audio to Kyutai DSM server and type transcriptions in real-time.

    Captures audio from the microphone, streams it via WebSocket to the Kyutai
    delayed-streams-modeling Rust server, and types each transcribed word into
    the focused application as it arrives. Runs while PTT is held; stops on
    release.

    Type signature: PipelineStage[None, None]
    - Input: None (first stage)
    - Output: None (handles typing internally)

    Config parameters:
    - server_url: WebSocket URL of the Kyutai DSM server (default: "ws://127.0.0.1:8080")
    - api_key: API key for the server (default: "public_token")
    - sample_rate: Audio sample rate in Hz (default: 24000)
    - block_size: Audio block size in samples (default: 1920 = 80ms at 24kHz)
    - max_duration: Maximum streaming duration in seconds (default: 120)
    - keyboard_backend: Backend selection (default: "auto")
    - char_delay: Delay between characters for pynput (default: 0.001)
    - device_name: Optional audio input device name (default: system default)
    """

    required_resources = {Resource.KEYBOARD}

    def __init__(self, config: dict):
        self.cfg = StreamingSTTConfig(**config)
        self.backend = create_keyboard_backend(
            method=self.cfg.keyboard_backend,
            char_delay=self.cfg.char_delay,
        )
        self.device_id = self._find_device_id(self.cfg.device_name)

    def _find_device_id(self, device_name: Optional[str]) -> Optional[int]:
        """Find the input device ID by name or return None for default."""
        if not device_name:
            return None

        devices = sd.query_devices()
        input_devices = [
            (i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0
        ]
        for i, device in input_devices:
            if device_name.lower() in device["name"].lower():
                logger.debug(f"Found specified device: {device['name']} (ID: {i})")
                return i

        available_names = [d["name"] for _, d in input_devices]
        raise ValueError(
            f"Device '{device_name}' not found. Available input devices: {available_names}"
        )

    async def _send_audio(self, websocket, audio_queue: asyncio.Queue, stop: asyncio.Event):
        """Send audio chunks from the queue to the WebSocket server."""
        try:
            # Drain any stale audio buffered before the connection was ready
            while not audio_queue.empty():
                audio_queue.get_nowait()

            logger.debug("StreamingSTT: send loop started")
            while not stop.is_set():
                try:
                    audio_data = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue
                chunk = {"type": "Audio", "pcm": [float(x) for x in audio_data]}
                msg = msgpack.packb(chunk, use_bin_type=True, use_single_float=True)
                await websocket.send(msg)
        except websockets.ConnectionClosed:
            logger.warning("StreamingSTT: WebSocket closed while sending")
        except asyncio.CancelledError:
            pass

    async def _receive_and_type(self, websocket, stop: asyncio.Event):
        """Receive transcription messages and type words as they arrive."""
        try:
            logger.debug("StreamingSTT: receive loop started")
            async for message in websocket:
                if stop.is_set():
                    break
                data = msgpack.unpackb(message, raw=False)
                if data["type"] == "Word":
                    word = data["text"]
                    logger.debug(f"StreamingSTT: received word: {word}")
                    self.backend.type_text(word + " ")
        except websockets.ConnectionClosed:
            logger.warning("StreamingSTT: WebSocket closed while receiving")
        except asyncio.CancelledError:
            pass

    async def _watch_for_release(self, context: PipelineContext, stop: asyncio.Event):
        """Watch for PTT release or cancellation and signal stop."""
        loop = asyncio.get_event_loop()

        def _wait():
            if context.trigger_event:
                context.trigger_event.wait_for_completion(timeout=self.cfg.max_duration)
            else:
                context.cancel_requested.wait(timeout=self.cfg.max_duration)

        await loop.run_in_executor(None, _wait)
        stop.set()
        logger.debug("StreamingSTT: stop signal set (PTT released or timeout)")

    async def _run_streaming(self, context: PipelineContext):
        """Main async entry point that orchestrates audio streaming and typing."""
        stop = asyncio.Event()
        audio_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_event_loop()

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"StreamingSTT: audio callback status: {status}")
            loop.call_soon_threadsafe(
                audio_queue.put_nowait, indata[:, 0].astype(np.float32).copy()
            )

        url = f"{self.cfg.server_url}/api/asr-streaming"
        headers = {"kyutai-api-key": self.cfg.api_key}

        with sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=1,
            dtype="float32",
            callback=audio_callback,
            blocksize=self.cfg.block_size,
            device=self.device_id,
        ):
            async with websockets.connect(url, additional_headers=headers) as ws:
                logger.info("StreamingSTT: connected to server, streaming started")
                context.icon_controller.set_icon("recording")

                send_task = asyncio.create_task(self._send_audio(ws, audio_queue, stop))
                recv_task = asyncio.create_task(self._receive_and_type(ws, stop))
                watch_task = asyncio.create_task(self._watch_for_release(context, stop))

                # Wait for the release watcher to finish (PTT released or timeout)
                await watch_task

                # Cancel the send/receive tasks
                send_task.cancel()
                recv_task.cancel()

                # Wait for them to finish cancellation
                await asyncio.gather(send_task, recv_task, return_exceptions=True)

        logger.info("StreamingSTT: streaming stopped")

    def execute(self, input_data: None, context: PipelineContext) -> None:
        if context.cancel_requested.is_set():
            logger.info("StreamingSTT: cancelled before start")
            return

        try:
            asyncio.run(self._run_streaming(context))
        except Exception:
            logger.exception("StreamingSTT: error during streaming")
            context.icon_controller.set_icon("error")

        context.icon_controller.set_icon("idle")

    def cleanup(self):
        pass
