###############################################################################
#  Output — WebRTC 输出
###############################################################################

from streamout.base_output import BaseOutput
from registry import register
from utils.logger import logger
from typing import TYPE_CHECKING, Optional
from server.alpha_stream import alpha_audio_hub, alpha_frame_hub
import cv2
import time

if TYPE_CHECKING:
    from avatars.base_avatar import BaseAvatar


@register("streamout", "webrtc")
@register("streamout", "rtcpush")
class WebRTCOutput(BaseOutput):
    """WebRTC 输出模式 — 通过 aiortc 推送音视频"""

    def __init__(self, opt=None, parent: Optional['BaseAvatar'] = None, **kwargs):
        super().__init__(opt, parent)
        self._player = None
        self._alpha_player = None
        self._alpha_next_frame_time = None
        self._alpha_video_count = 0
        self._alpha_audio_count = 0
        self._alpha_audio_bytes = 0
        self._alpha_video_pace_sleep_ms = 0.0
        self._alpha_last_video_shape = None
        self._alpha_last_video_log = 0.0
        self._alpha_last_video_count = 0
        self._alpha_last_audio_log = 0.0

    def start(self) -> None:
        """WebRTC 输出由 rtc_manager 管理，此处无需额外启动"""
        logger.info(
            "streamout/webrtc start alpha_output=%s has_player=%s fps=%s",
            getattr(self.opt, "alpha_output", False),
            self._player is not None,
            getattr(self.opt, "fps", None),
        )

    def attach_player(self, player) -> None:
        self._player = player
        logger.info("streamout/webrtc attached player=%s", player.__class__.__name__)

    def detach_player(self, player) -> None:
        if self._player is player:
            self._player = None
            logger.info("streamout/webrtc detached player=%s", player.__class__.__name__)

    def attach_alpha_player(self, player) -> None:
        self._alpha_player = player
        logger.info("streamout/webrtc attached alpha player=%s", player.__class__.__name__)

    def detach_alpha_player(self, player) -> None:
        if self._alpha_player is player:
            self._alpha_player = None
            logger.info("streamout/webrtc detached alpha player=%s", player.__class__.__name__)

    def push_video_frame(self, frame) -> None:
        if getattr(self.opt, "alpha_output", False):
            self._pace_alpha_frame()
            if alpha_frame_hub.has_clients():
                self._log_alpha_video_frame(frame)
                alpha_frame_hub.publish_frame(frame)
        if self._alpha_player:
            self._alpha_player.push_video(frame)
        if self._player:
            if getattr(frame, "ndim", 0) == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            self._player.push_video(frame)

    def push_audio_frame(self, frame, eventpoint=None) -> None:
        if getattr(self.opt, "alpha_output", False):
            if alpha_audio_hub.has_clients():
                self._log_alpha_audio_frame(frame, eventpoint)
                alpha_audio_hub.publish_bytes(frame.tobytes())
        if self._alpha_player:
            self._alpha_player.push_audio(frame, eventpoint)
        if self._player:
            self._player.push_audio(frame, eventpoint)



    def get_buffer_size(self) -> int:
        sizes = []
        if self._player and hasattr(self._player, 'get_buffer_size'):
            sizes.append(self._player.get_buffer_size())
        if self._alpha_player and hasattr(self._alpha_player, 'get_buffer_size'):
            sizes.append(self._alpha_player.get_buffer_size())
        return max(sizes, default=0)

    def _pace_alpha_frame(self) -> None:
        if self._player is not None or self._alpha_player is not None:
            return

        fps = max(1, int(getattr(self.opt, "fps", 25)))
        frame_interval = 1.0 / fps
        now = time.perf_counter()
        if self._alpha_next_frame_time is None:
            self._alpha_next_frame_time = now
        elif self._alpha_next_frame_time > now:
            sleep_seconds = self._alpha_next_frame_time - now
            time.sleep(sleep_seconds)
            self._alpha_video_pace_sleep_ms += sleep_seconds * 1000
            now = time.perf_counter()
        elif now - self._alpha_next_frame_time > frame_interval:
            self._alpha_next_frame_time = now

        self._alpha_next_frame_time += frame_interval

    def _log_alpha_video_frame(self, frame) -> None:
        self._alpha_video_count += 1
        now = time.perf_counter()
        shape = getattr(frame, "shape", None)
        dtype = str(getattr(frame, "dtype", ""))
        shape_key = (tuple(shape) if shape is not None else None, dtype)
        shape_changed = shape_key != self._alpha_last_video_shape
        periodic = now - self._alpha_last_video_log >= 5.0
        if not (self._alpha_video_count == 1 or shape_changed or periodic):
            return

        interval = now - self._alpha_last_video_log if self._alpha_last_video_log else 0.0
        frame_delta = self._alpha_video_count - self._alpha_last_video_count
        fps = frame_delta / interval if interval > 0 else 0.0
        logger.info(
            "streamout alpha video frame count=%d shape=%s dtype=%s fps=%.1f avg_pace_sleep_ms=%.2f",
            self._alpha_video_count,
            shape,
            dtype,
            fps,
            self._alpha_video_pace_sleep_ms / max(1, frame_delta),
        )
        self._alpha_video_pace_sleep_ms = 0.0
        self._alpha_last_video_shape = shape_key
        self._alpha_last_video_log = now
        self._alpha_last_video_count = self._alpha_video_count

    def _log_alpha_audio_frame(self, frame, eventpoint=None) -> None:
        self._alpha_audio_count += 1
        self._alpha_audio_bytes += frame.nbytes
        now = time.perf_counter()
        status = eventpoint.get("status") if isinstance(eventpoint, dict) else None
        if not status and now - self._alpha_last_audio_log < 5.0:
            return
        logger.info(
            "streamout alpha audio chunks=%d bytes=%d shape=%s dtype=%s status=%s text_len=%d tts_keys=%s",
            self._alpha_audio_count,
            self._alpha_audio_bytes,
            getattr(frame, "shape", None),
            getattr(frame, "dtype", None),
            status or "",
            len(str(eventpoint.get("text", ""))) if isinstance(eventpoint, dict) else 0,
            sorted(eventpoint.get("tts", {}).keys()) if isinstance(eventpoint, dict) and isinstance(eventpoint.get("tts"), dict) else [],
        )
        self._alpha_audio_count = 0
        self._alpha_audio_bytes = 0
        self._alpha_last_audio_log = now

    def stop(self) -> None:
        logger.info("streamout/webrtc stop")
