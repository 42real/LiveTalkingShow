import queue
import threading
import time
from typing import Optional, Set

import cv2
import numpy as np
from aiortc import MediaStreamTrack
from av import AudioFrame, VideoFrame

from server.webrtc import PlayerStreamTrack, player_worker_thread
from utils.logger import logger


class AlphaWebRTCPlayer:
    """Three-track WebRTC player for transparent remote display.

    The browser receives:
    - audio track: PCM audio encoded by WebRTC
    - color video track: normal BGR/RGB avatar image
    - alpha video track: grayscale alpha mask encoded as a video stream

    The display client composites color + alpha locally. This avoids shipping raw
    RGBA over a websocket for remote display while preserving transparency.
    """

    def __init__(self, avatar_session, manage_worker: bool = True):
        self.__thread: Optional[threading.Thread] = None
        self.__thread_quit: Optional[threading.Event] = None
        self.__started: Set[PlayerStreamTrack] = set()
        self.__audio = PlayerStreamTrack(self, kind="audio")
        self.__color_video = PlayerStreamTrack(self, kind="video")
        self.__alpha_video = PlayerStreamTrack(self, kind="video")
        self.__container = avatar_session
        self.__manage_worker = manage_worker
        self.__video_count = 0
        self.__last_log_video_count = 0
        self.__last_log_audio_count = 0
        self.__audio_count = 0
        self.__last_log = 0.0
        self.__split_ms = 0.0
        self.__next_frame_at: Optional[float] = None
        self.__pace_sleep_ms = 0.0

        if hasattr(self.__container, "output"):
            output = self.__container.output
            if hasattr(output, "attach_alpha_player"):
                output.attach_alpha_player(self)
            else:
                output._alpha_player = self

    @property
    def audio(self) -> MediaStreamTrack:
        return self.__audio

    @property
    def color_video(self) -> MediaStreamTrack:
        return self.__color_video

    @property
    def alpha_video(self) -> MediaStreamTrack:
        return self.__alpha_video

    def start(self) -> None:
        if not self.__manage_worker:
            return
        if self.__thread is None:
            logger.info("alpha webrtc player starting render worker")
            self.__thread_quit = threading.Event()
            self.__thread = threading.Thread(
                name="alpha-webrtc-player",
                target=player_worker_thread,
                args=(self.__thread_quit, self.__container),
            )
            self.__thread.start()

    def stop_worker(self) -> None:
        container = self.__container
        if self.__thread is not None and self.__thread_quit is not None:
            logger.info("alpha webrtc player stopping render worker")
            self.__thread_quit.set()
            self.__thread.join(timeout=3)
            self.__thread = None
            self.__thread_quit = None
        if container is not None and hasattr(container, "output"):
            output = container.output
            if hasattr(output, "detach_alpha_player"):
                output.detach_alpha_player(self)
            elif getattr(output, "_alpha_player", None) is self:
                output._alpha_player = None
        self.__container = None

    def push_video(self, frame) -> None:
        self._pace_video()
        start = time.perf_counter()
        color_frame, alpha_frame = self._split_frame(frame)
        self.__split_ms += (time.perf_counter() - start) * 1000
        self.__video_count += 1

        color_video = VideoFrame.from_ndarray(color_frame, format="bgr24")
        alpha_video = VideoFrame.from_ndarray(alpha_frame, format="bgr24")
        self._replace_latest(self.__color_video._queue, color_video)
        self._replace_latest(self.__alpha_video._queue, alpha_video)
        self._log_video(frame)

    def push_audio(self, frame, eventpoint=None) -> None:
        audio_frame = AudioFrame(format="s16", layout="mono", samples=frame.shape[0])
        audio_frame.planes[0].update(frame.tobytes())
        audio_frame.sample_rate = 16000
        self.__audio_count += 1
        try:
            self.__audio._queue.put((audio_frame, eventpoint), timeout=0.02)
        except queue.Full:
            try:
                self.__audio._queue.get_nowait()
                self.__audio._dropped += 1
            except queue.Empty:
                pass
            self.__audio._queue.put((audio_frame, eventpoint))

    def get_buffer_size(self) -> int:
        return max(
            self.__color_video._queue.qsize(),
            self.__alpha_video._queue.qsize(),
        )

    def notify(self, eventpoint):
        if self.__container is not None:
            self.__container.notify(eventpoint)

    def _start(self, track: PlayerStreamTrack) -> None:
        self.__started.add(track)
        self.start()

    def _stop(self, track: PlayerStreamTrack) -> None:
        self.__started.discard(track)
        if not self.__started:
            self.stop_worker()

    def _split_frame(self, frame) -> tuple[np.ndarray, np.ndarray]:
        if frame is None:
            color = np.zeros((16, 16, 3), dtype=np.uint8)
            alpha = np.zeros((16, 16, 3), dtype=np.uint8)
            return color, alpha

        if not frame.flags["C_CONTIGUOUS"]:
            frame = np.ascontiguousarray(frame)

        if frame.ndim != 3 or frame.shape[2] not in (3, 4):
            logger.warning(
                "alpha webrtc frame expects BGR/BGRA, got shape=%s dtype=%s",
                getattr(frame, "shape", None),
                getattr(frame, "dtype", None),
            )
            color = np.zeros((16, 16, 3), dtype=np.uint8)
            alpha = np.zeros((16, 16, 3), dtype=np.uint8)
            return color, alpha

        if frame.shape[2] == 4:
            color = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            alpha_plane = frame[:, :, 3]
        else:
            color = frame
            alpha_plane = np.full(frame.shape[:2], 255, dtype=np.uint8)

        if color.dtype != np.uint8:
            color = np.clip(color, 0, 255).astype(np.uint8)
        if alpha_plane.dtype != np.uint8:
            alpha_plane = np.clip(alpha_plane, 0, 255).astype(np.uint8)

        alpha = cv2.cvtColor(alpha_plane, cv2.COLOR_GRAY2BGR)
        if not color.flags["C_CONTIGUOUS"]:
            color = np.ascontiguousarray(color)
        if not alpha.flags["C_CONTIGUOUS"]:
            alpha = np.ascontiguousarray(alpha)
        return color, alpha

    def _replace_latest(self, target_queue: queue.Queue, frame: VideoFrame) -> None:
        while target_queue.full():
            try:
                target_queue.get_nowait()
            except queue.Empty:
                break
        target_queue.put((frame, None))

    def _log_video(self, source_frame) -> None:
        now = time.perf_counter()
        if self.__video_count != 1 and now - self.__last_log < 5.0:
            return
        interval = now - self.__last_log if self.__last_log else 0.0
        video_delta = self.__video_count - self.__last_log_video_count
        audio_delta = self.__audio_count - self.__last_log_audio_count
        fps = 0.0 if interval <= 0 else video_delta / interval
        logger.info(
            "alpha webrtc player video frames=%d approx_fps=%.1f shape=%s dtype=%s "
            "color_q=%d alpha_q=%d avg_split_ms=%.2f avg_pace_sleep_ms=%.2f "
            "audio_chunks=%d manage_worker=%s",
            video_delta,
            fps,
            getattr(source_frame, "shape", None),
            getattr(source_frame, "dtype", None),
            self.__color_video._queue.qsize(),
            self.__alpha_video._queue.qsize(),
            self.__split_ms / max(1, video_delta),
            self.__pace_sleep_ms / max(1, video_delta),
            audio_delta,
            self.__manage_worker,
        )
        self.__last_log_video_count = self.__video_count
        self.__last_log_audio_count = self.__audio_count
        self.__split_ms = 0.0
        self.__pace_sleep_ms = 0.0
        self.__last_log = now

    def _pace_video(self) -> None:
        fps = max(1, int(getattr(getattr(self.__container, "opt", None), "fps", 25) or 25))
        interval = 1.0 / fps
        now = time.perf_counter()
        if self.__next_frame_at is None:
            self.__next_frame_at = now + interval
            return
        if self.__next_frame_at > now:
            sleep_seconds = self.__next_frame_at - now
            time.sleep(sleep_seconds)
            self.__pace_sleep_ms += sleep_seconds * 1000
            now = time.perf_counter()
        elif now - self.__next_frame_at > interval:
            self.__next_frame_at = now
        self.__next_frame_at += interval
