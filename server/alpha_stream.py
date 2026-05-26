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
    max_width: int = 0
    max_height: int = 0
    fps: float = 0.0
    next_send_at: float = 0.0


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

    def has_clients(self) -> bool:
        with self._lock:
            return bool(self._clients)

    async def add_client(self, ws: web.WebSocketResponse, max_width: int = 0, max_height: int = 0, fps: float = 0.0):
        queue = asyncio.Queue(maxsize=1)
        task = asyncio.create_task(self._pump(ws, queue))
        with self._lock:
            self._clients[ws] = _Client(
                ws=ws,
                queue=queue,
                task=task,
                max_width=max_width,
                max_height=max_height,
                fps=fps,
            )
            last_packet = self._last_packet if not max_width and not max_height else None
            client_count = len(self._clients)
        if last_packet:
            self._replace_latest(queue, last_packet)
        logger.info(
            "alpha raw video websocket registered clients=%d max_width=%d max_height=%d fps=%.1f",
            client_count,
            max_width,
            max_height,
            fps,
        )

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
        if frame.ndim != 3 or frame.shape[2] not in (3, 4):
            logger.warning(
                "alpha frame skipped: expected BGR/BGRA frame, got shape=%s dtype=%s",
                getattr(frame, "shape", None),
                getattr(frame, "dtype", None),
            )
            return

        height, width = frame.shape[:2]

        now = time.monotonic()
        with self._lock:
            self._seq += 1
            seq = self._seq
            clients = list(self._clients.values())
            loop = self._loop
            send_clients = []
            for client in clients:
                if client.fps > 0:
                    interval = 1.0 / client.fps
                    if client.next_send_at and now < client.next_send_at:
                        continue
                    if client.next_send_at:
                        missed_intervals = int((now - client.next_send_at) // interval)
                        client.next_send_at += (missed_intervals + 1) * interval
                    else:
                        client.next_send_at = now + interval
                send_clients.append(client)
            self._log_publish_locked(width, height, frame, len(clients))

        if not send_clients or loop is None:
            return

        full_packet = None
        for client in send_clients:
            if client.max_width or client.max_height:
                client_frame = self._resize_for_client(frame, client)
                client_packet = self._make_packet(self._to_rgba(client_frame), seq)
            else:
                if full_packet is None:
                    full_packet = self._make_packet(self._to_rgba(frame), seq)
                    with self._lock:
                        self._last_packet = full_packet
                client_packet = full_packet
            loop.call_soon_threadsafe(self._replace_latest, client.queue, client_packet)

    def _to_rgba(self, frame: np.ndarray) -> np.ndarray:
        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)
        if frame.shape[2] == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA)
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)

    def _make_packet(self, rgba: np.ndarray, seq: int) -> bytes:
        height, width = rgba.shape[:2]
        if not rgba.flags["C_CONTIGUOUS"]:
            rgba = np.ascontiguousarray(rgba)
        return FRAME_HEADER.pack(
            FRAME_MAGIC,
            FRAME_VERSION,
            FRAME_FORMAT_RGBA8,
            0,
            width,
            height,
            seq,
        ) + rgba.tobytes()

    def _resize_for_client(self, frame: np.ndarray, client: _Client) -> np.ndarray:
        height, width = frame.shape[:2]
        scale = 1.0
        if client.max_width > 0 and width > client.max_width:
            scale = min(scale, client.max_width / width)
        if client.max_height > 0 and height > client.max_height:
            scale = min(scale, client.max_height / height)
        if scale >= 1.0:
            return frame

        target_width = max(1, int(round(width * scale)))
        target_height = max(1, int(round(height * scale)))
        return cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)

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

    def _log_publish_locked(self, width: int, height: int, frame: np.ndarray, client_count: int):
        now = time.monotonic()
        shape = (height, width, frame.shape[2], str(frame.dtype))
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
            frame.dtype,
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

    def has_clients(self) -> bool:
        with self._lock:
            return bool(self._clients)

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


def _query_int(request: web.Request, name: str, default: int = 0, min_value: int = 0, max_value: int = 4096) -> int:
    raw = request.query.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


def _query_float(
    request: web.Request,
    name: str,
    default: float = 0.0,
    min_value: float = 0.0,
    max_value: float = 60.0,
) -> float:
    raw = request.query.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


async def alpha_ws(request):
    ws = web.WebSocketResponse(max_msg_size=0, compress=False)
    await ws.prepare(request)
    max_width = _query_int(request, "max_width")
    max_height = _query_int(request, "max_height")
    fps = _query_float(request, "fps")
    await alpha_frame_hub.add_client(ws, max_width=max_width, max_height=max_height, fps=fps)
    logger.info(
        "alpha raw video websocket connected peer=%s max_width=%d max_height=%d fps=%.1f",
        request.remote,
        max_width,
        max_height,
        fps,
    )
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
