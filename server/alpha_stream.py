import asyncio
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from aiohttp import WSMsgType, web

from utils.logger import logger


FRAME_MAGIC = b"LTAF"
FRAME_VERSION = 1
FRAME_FORMAT_RGBA8 = 1
FRAME_HEADER = struct.Struct("<4sBBHIIQ")


@dataclass
class _Client:
    ws: web.WebSocketResponse
    queue: asyncio.Queue
    task: asyncio.Task


class LatestFrameHub:
    """Low-latency raw RGBA video hub.

    Wire format per websocket message:
    - 24 byte little-endian header: magic, version, format, flags, width, height, seq
    - width * height * 4 bytes of RGBA8 pixels

    Every client owns a queue of size 1. If the renderer is slow, stale frames are
    replaced by the newest frame instead of accumulating latency.
    """

    def __init__(self):
        self._clients: dict[web.WebSocketResponse, _Client] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_packet: Optional[bytes] = None
        self._seq = 0
        self._lock = threading.Lock()
        self._last_shape: Optional[tuple[int, int, int, str]] = None
        self._last_log_time = 0.0
        self._last_log_seq = 0
        self._dropped_packets = 0

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        logger.info("alpha frame hub bound to event loop id=%s", id(loop))

    async def add_client(self, ws: web.WebSocketResponse):
        queue = asyncio.Queue(maxsize=1)
        task = asyncio.create_task(self._pump(ws, queue))
        with self._lock:
            self._clients[ws] = _Client(ws=ws, queue=queue, task=task)
            last_packet = self._last_packet
            client_count = len(self._clients)
        if last_packet:
            self._replace_latest(queue, last_packet)
        logger.info("alpha raw video websocket registered clients=%d", client_count)

    def remove_client(self, ws: web.WebSocketResponse):
        with self._lock:
            client = self._clients.pop(ws, None)
            client_count = len(self._clients)
        if client is not None:
            client.task.cancel()
            logger.info("alpha raw video websocket removed clients=%d", client_count)

    def publish_frame(self, frame: np.ndarray):
        if frame is None:
            logger.warning("alpha frame skipped: frame is None")
            return
        if frame.ndim != 3 or frame.shape[2] != 4:
            logger.warning(
                "alpha frame skipped: expected BGRA frame, got shape=%s dtype=%s",
                getattr(frame, "shape", None),
                getattr(frame, "dtype", None),
            )
            return

        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)

        # OpenCV keeps 4-channel images as BGRA, while Canvas ImageData expects RGBA.
        rgba = cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)
        height, width = rgba.shape[:2]
        payload = rgba.tobytes()

        with self._lock:
            self._seq += 1
            packet = FRAME_HEADER.pack(
                FRAME_MAGIC,
                FRAME_VERSION,
                FRAME_FORMAT_RGBA8,
                0,
                width,
                height,
                self._seq,
            ) + payload
            self._last_packet = packet
            clients = list(self._clients.values())
            loop = self._loop
            self._log_publish_locked(width, height, rgba, len(clients))

        if not clients or loop is None:
            return

        for client in clients:
            loop.call_soon_threadsafe(self._replace_latest, client.queue, packet)

    def _replace_latest(self, queue: asyncio.Queue, packet: bytes):
        dropped = 0
        while not queue.empty():
            try:
                queue.get_nowait()
                queue.task_done()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped:
            with self._lock:
                self._dropped_packets += dropped
        try:
            queue.put_nowait(packet)
        except asyncio.QueueFull:
            with self._lock:
                self._dropped_packets += 1

    async def _pump(self, ws: web.WebSocketResponse, queue: asyncio.Queue):
        try:
            while not ws.closed:
                packet = await queue.get()
                try:
                    await ws.send_bytes(packet)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, RuntimeError) as exc:
            logger.info("alpha raw video websocket send stopped: %s", exc)
            self.remove_client(ws)
        except Exception:
            logger.exception("alpha raw video websocket pump exception")
            self.remove_client(ws)

    def _log_publish_locked(self, width: int, height: int, rgba: np.ndarray, client_count: int):
        now = time.monotonic()
        shape = (height, width, rgba.shape[2], str(rgba.dtype))
        shape_changed = shape != self._last_shape
        first_frame = self._seq == 1
        periodic = now - self._last_log_time >= 5.0
        if not (first_frame or shape_changed or periodic):
            return

        interval = now - self._last_log_time if self._last_log_time else 0.0
        frame_delta = self._seq - self._last_log_seq
        fps = frame_delta / interval if interval > 0 else 0.0
        logger.info(
            "alpha frame publish seq=%d size=%dx%d dtype=%s clients=%d fps=%.1f queue_drop=%d",
            self._seq,
            width,
            height,
            rgba.dtype,
            client_count,
            fps,
            self._dropped_packets,
        )
        self._last_shape = shape
        self._last_log_time = now
        self._last_log_seq = self._seq
        self._dropped_packets = 0


class AudioHub:
    """PCM16 audio websocket hub with bounded per-client queues."""

    def __init__(self):
        self._clients: dict[web.WebSocketResponse, _Client] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._published_bytes = 0
        self._published_chunks = 0
        self._dropped_chunks = 0
        self._last_log_time = 0.0

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        logger.info("alpha audio hub bound to event loop id=%s", id(loop))

    async def add_client(self, ws: web.WebSocketResponse):
        queue = asyncio.Queue(maxsize=64)
        task = asyncio.create_task(self._pump(ws, queue))
        with self._lock:
            self._clients[ws] = _Client(ws=ws, queue=queue, task=task)
            client_count = len(self._clients)
        logger.info("alpha audio websocket registered clients=%d", client_count)

    def remove_client(self, ws: web.WebSocketResponse):
        with self._lock:
            client = self._clients.pop(ws, None)
            client_count = len(self._clients)
        if client is not None:
            client.task.cancel()
            logger.info("alpha audio websocket removed clients=%d", client_count)

    def publish_bytes(self, data: bytes):
        if not data:
            return

        with self._lock:
            clients = list(self._clients.values())
            loop = self._loop
            self._published_chunks += 1
            self._published_bytes += len(data)
            self._log_publish_locked(len(clients))

        if not clients or loop is None:
            return

        for client in clients:
            loop.call_soon_threadsafe(self._put_bounded, client.queue, data)

    def _put_bounded(self, queue: asyncio.Queue, data: bytes):
        if queue.full():
            # Keep latency bounded. If the browser cannot keep up, restart at the
            # freshest audio chunk instead of playing seconds-old speech.
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                    with self._lock:
                        self._dropped_chunks += 1
                except asyncio.QueueEmpty:
                    break
        try:
            queue.put_nowait(data)
        except asyncio.QueueFull:
            with self._lock:
                self._dropped_chunks += 1

    async def _pump(self, ws: web.WebSocketResponse, queue: asyncio.Queue):
        try:
            while not ws.closed:
                data = await queue.get()
                try:
                    await ws.send_bytes(data)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, RuntimeError) as exc:
            logger.info("alpha audio websocket send stopped: %s", exc)
            self.remove_client(ws)
        except Exception:
            logger.exception("alpha audio websocket pump exception")
            self.remove_client(ws)

    def _log_publish_locked(self, client_count: int):
        now = time.monotonic()
        if now - self._last_log_time < 5.0:
            return
        logger.info(
            "alpha audio publish chunks=%d bytes=%d clients=%d queue_drop=%d",
            self._published_chunks,
            self._published_bytes,
            client_count,
            self._dropped_chunks,
        )
        self._published_chunks = 0
        self._published_bytes = 0
        self._dropped_chunks = 0
        self._last_log_time = now


alpha_frame_hub = LatestFrameHub()
alpha_audio_hub = AudioHub()


async def alpha_ws(request):
    ws = web.WebSocketResponse(max_msg_size=0, compress=False)
    await ws.prepare(request)
    await alpha_frame_hub.add_client(ws)
    logger.info("alpha raw video websocket connected peer=%s", request.remote)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        alpha_frame_hub.remove_client(ws)
        logger.info("alpha raw video websocket disconnected peer=%s", request.remote)
    return ws


async def alpha_audio_ws(request):
    ws = web.WebSocketResponse(max_msg_size=0, compress=False)
    await ws.prepare(request)
    await alpha_audio_hub.add_client(ws)
    logger.info("alpha audio websocket connected peer=%s", request.remote)
    try:
        async for msg in ws:
            if msg.type == WSMsgType.ERROR:
                break
    finally:
        alpha_audio_hub.remove_client(ws)
        logger.info("alpha audio websocket disconnected peer=%s", request.remote)
    return ws
