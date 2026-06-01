###############################################################################
#  Unified output router
###############################################################################

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

import registry
from streamout.base_output import BaseOutput
from utils.logger import logger

if TYPE_CHECKING:
    from avatars.base_avatar import BaseAvatar


_TRANSPORT_MODULES = {
    "webrtc": "streamout.webrtc",
    "rtcpush": "streamout.webrtc",
    "rtmp": "streamout.rtmp",
    "virtualcam": "streamout.virtualcam",
}


@dataclass
class OutputStats:
    video_frames: int = 0
    audio_chunks: int = 0
    audio_bytes: int = 0
    sink_video_ms: float = 0.0
    sink_audio_ms: float = 0.0
    max_sink_video_ms: float = 0.0
    max_sink_audio_ms: float = 0.0
    last_log_at: float = field(default_factory=time.perf_counter)
    last_video_frames: int = 0
    last_audio_chunks: int = 0
    last_audio_bytes: int = 0


class OutputRouter(BaseOutput):
    """One output boundary for avatar renderers.

    BaseAvatar pushes every video frame and audio chunk into this router. The
    router owns sink fan-out, latency metrics, and the compatibility hooks used
    by WebRTC/alpha/RTMP/virtualcam outputs.
    """

    def __init__(self, opt=None, parent: "BaseAvatar | None" = None, **kwargs):
        super().__init__(opt, parent)
        self.transport = getattr(opt, "transport", "webrtc")
        self.metrics_interval = float(getattr(opt, "output_metrics_interval", 5.0) or 0.0)
        self.sinks: list[BaseOutput] = []
        self.stats = OutputStats()
        self._load_primary_sink()

    def _load_primary_sink(self) -> None:
        module_name = _TRANSPORT_MODULES.get(self.transport)
        if not module_name:
            raise ValueError(f"Output transport {self.transport} not found in map.")

        importlib.import_module(module_name)
        sink = registry.create("streamout", self.transport, opt=self.opt, parent=self.parent)
        self.sinks.append(sink)
        logger.info(
            "output router initialized transport=%s sinks=%s metrics_interval=%.1f",
            self.transport,
            [sink.__class__.__name__ for sink in self.sinks],
            self.metrics_interval,
        )

    def start(self) -> None:
        for sink in self.sinks:
            sink.start()
        logger.info("output router started sinks=%d", len(self.sinks))

    def push_video_frame(self, frame: Any) -> None:
        start = time.perf_counter()
        for sink in self.sinks:
            sink_start = time.perf_counter()
            sink.push_video_frame(frame)
            elapsed_ms = (time.perf_counter() - sink_start) * 1000
            self.stats.sink_video_ms += elapsed_ms
            self.stats.max_sink_video_ms = max(self.stats.max_sink_video_ms, elapsed_ms)
        self.stats.video_frames += 1
        self._log_if_needed(frame=frame, elapsed_ms=(time.perf_counter() - start) * 1000)

    def push_audio_frame(self, frame: np.ndarray, eventpoint=None) -> None:
        start = time.perf_counter()
        for sink in self.sinks:
            sink_start = time.perf_counter()
            sink.push_audio_frame(frame, eventpoint)
            elapsed_ms = (time.perf_counter() - sink_start) * 1000
            self.stats.sink_audio_ms += elapsed_ms
            self.stats.max_sink_audio_ms = max(self.stats.max_sink_audio_ms, elapsed_ms)
        self.stats.audio_chunks += 1
        self.stats.audio_bytes += getattr(frame, "nbytes", 0)
        self._log_if_needed(elapsed_ms=(time.perf_counter() - start) * 1000)

    def get_buffer_size(self) -> int:
        return max((sink.get_buffer_size() for sink in self.sinks), default=0)

    def stop(self) -> None:
        for sink in self.sinks:
            sink.stop()
        logger.info("output router stopped")

    def _log_if_needed(self, frame=None, elapsed_ms: float = 0.0) -> None:
        if self.metrics_interval <= 0:
            return

        now = time.perf_counter()
        if now - self.stats.last_log_at < self.metrics_interval:
            return

        interval = now - self.stats.last_log_at
        video_delta = self.stats.video_frames - self.stats.last_video_frames
        audio_delta = self.stats.audio_chunks - self.stats.last_audio_chunks
        audio_bytes_delta = self.stats.audio_bytes - self.stats.last_audio_bytes
        avg_video_ms = self.stats.sink_video_ms / max(1, video_delta)
        avg_audio_ms = self.stats.sink_audio_ms / max(1, audio_delta)
        logger.info(
            "output metrics transport=%s sinks=%d video_fps=%.1f audio_chunks_s=%.1f "
            "audio_kbps=%.1f avg_video_ms=%.2f max_video_ms=%.2f "
            "avg_audio_ms=%.2f max_audio_ms=%.2f buffer=%d last_push_ms=%.2f shape=%s dtype=%s",
            self.transport,
            len(self.sinks),
            video_delta / interval if interval > 0 else 0.0,
            audio_delta / interval if interval > 0 else 0.0,
            (audio_bytes_delta * 8 / 1000) / interval if interval > 0 else 0.0,
            avg_video_ms,
            self.stats.max_sink_video_ms,
            avg_audio_ms,
            self.stats.max_sink_audio_ms,
            self.get_buffer_size(),
            elapsed_ms,
            getattr(frame, "shape", None),
            getattr(frame, "dtype", None),
        )
        self.stats.last_log_at = now
        self.stats.last_video_frames = self.stats.video_frames
        self.stats.last_audio_chunks = self.stats.audio_chunks
        self.stats.last_audio_bytes = self.stats.audio_bytes
        self.stats.sink_video_ms = 0.0
        self.stats.sink_audio_ms = 0.0
        self.stats.max_sink_video_ms = 0.0
        self.stats.max_sink_audio_ms = 0.0
