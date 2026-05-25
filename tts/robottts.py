import json
import threading
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

import numpy as np

from utils.audio import pcm_to_float32
from utils.logger import logger
from .base_tts import BaseTTS, State
from registry import register

try:
    from websocket import create_connection, WebSocketConnectionClosedException, WebSocketTimeoutException
except ImportError:
    logger.error("RobotTTS requires websocket-client: pip install websocket-client")
    raise


@register("tts", "robottts")
class RobotTTS(BaseTTS):
    def __init__(self, opt, parent):
        super().__init__(opt, parent)
        self.ws_url, self.http_base = self._normalize_server_urls(opt.TTS_SERVER)
        self.default_mode = getattr(opt, "robottts_mode", "instruct2")
        self.connect_timeout = float(getattr(opt, "robottts_connect_timeout", 10))
        self.receive_timeout = float(getattr(opt, "robottts_receive_timeout", 1))
        self._active_ws = None
        self._active_ws_lock = threading.Lock()
        self._voice_cache = None

    def flush_talk(self):
        super().flush_talk()
        self._close_active_ws()

    def stop_tts(self):
        self._close_active_ws()

    def txt_to_audio(self, msg: tuple[str, dict]):
        text, textevent = msg
        ws = None
        try:
            start_payload = self._build_start_payload(textevent)
            ws = create_connection(self.ws_url, timeout=self.connect_timeout)
            ws.settimeout(self.receive_timeout)
            self._set_active_ws(ws)

            ws.send(json.dumps(start_payload))
            started = self._recv_json(ws, expect_action="started")
            if started.get("action") != "started":
                raise RuntimeError(f"unexpected robot-tts start response: {started}")

            ws.send(json.dumps({"action": "text", "text": text}))
            self._stream_audio(ws, text, textevent)
        except Exception as exc:
            logger.exception("robottts")
            logger.error("RobotTTS request failed: %s", exc)
        finally:
            self._close_ws(ws, send_end=self.state == State.RUNNING)
            self._clear_active_ws(ws)

    def _build_start_payload(self, textevent: dict) -> dict:
        tts_opts = textevent.get("tts", {}) if textevent else {}
        voice_value = tts_opts.get("voice_id", tts_opts.get("ref_file", self.opt.REF_FILE))
        prompts = tts_opts.get("prompts", tts_opts.get("ref_text", self.opt.REF_TEXT or ""))
        mode = tts_opts.get("mode", self.default_mode)

        payload = {
            "action": "start",
            "voice_id": self._resolve_voice_id(voice_value),
            "prompts": prompts or "",
        }
        if mode:
            payload["mode"] = mode
        return payload

    def _stream_audio(self, ws, text: str, textevent: dict):
        frame_bytes = self.chunk * 2
        pending = bytearray()
        first_chunk = True

        while self.state == State.RUNNING:
            try:
                message = ws.recv()
            except WebSocketTimeoutException:
                continue
            except WebSocketConnectionClosedException:
                break

            if isinstance(message, bytes):
                pending.extend(message)
                while len(pending) >= frame_bytes and self.state == State.RUNNING:
                    frame_pcm = bytes(pending[:frame_bytes])
                    del pending[:frame_bytes]
                    first_chunk = self._emit_frame(frame_pcm, text, textevent, first_chunk)
                continue

            payload = self._parse_json(message)
            if payload.get("action") == "error":
                raise RuntimeError(payload.get("message", "robot-tts returned an error"))
            if payload.get("action") == "result" and payload.get("type") == "final":
                break

        if self.state != State.RUNNING:
            return

        if pending:
            if len(pending) % 2 != 0:
                pending = pending[:-1]
            if pending:
                if len(pending) < frame_bytes:
                    pending.extend(b"\x00" * (frame_bytes - len(pending)))
                first_chunk = self._emit_frame(bytes(pending[:frame_bytes]), text, textevent, first_chunk)

        eventpoint = {"status": "end", "text": text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(np.zeros(self.chunk, np.float32), eventpoint)

    def _emit_frame(self, frame_pcm: bytes, text: str, textevent: dict, first_chunk: bool) -> bool:
        frame = pcm_to_float32(frame_pcm)
        eventpoint = {}
        if first_chunk:
            eventpoint = {"status": "start", "text": text}
            first_chunk = False
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(frame, eventpoint)
        return first_chunk

    def _recv_json(self, ws, expect_action: str | None = None) -> dict:
        while True:
            message = ws.recv()
            if isinstance(message, bytes):
                continue
            payload = self._parse_json(message)
            if payload.get("action") == "error":
                raise RuntimeError(payload.get("message", "robot-tts returned an error"))
            if expect_action is None or payload.get("action") == expect_action:
                return payload

    def _resolve_voice_id(self, voice_value) -> int:
        if isinstance(voice_value, int):
            return max(0, voice_value)

        raw = "" if voice_value is None else str(voice_value).strip()
        if not raw:
            return 0

        try:
            return max(0, int(raw))
        except ValueError:
            voice_map = self._load_voice_map()
            if raw in voice_map:
                return voice_map[raw]
            logger.warning("RobotTTS voice '%s' not found, fallback to voice_id 0", raw)
            return 0

    def _load_voice_map(self) -> dict[str, int]:
        if self._voice_cache is not None:
            return self._voice_cache

        voice_map = {}
        try:
            with urlopen(f"{self.http_base}/tts/voices", timeout=self.connect_timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            for item in payload.get("voices", []):
                name = str(item.get("name", "")).strip()
                voice_id = item.get("id")
                if name and isinstance(voice_id, int):
                    voice_map[name] = voice_id
        except Exception as exc:
            logger.warning("RobotTTS voice list lookup failed: %s", exc)

        self._voice_cache = voice_map
        return self._voice_cache

    def _set_active_ws(self, ws):
        with self._active_ws_lock:
            self._active_ws = ws

    def _clear_active_ws(self, ws):
        with self._active_ws_lock:
            if self._active_ws is ws:
                self._active_ws = None

    def _close_active_ws(self):
        with self._active_ws_lock:
            ws = self._active_ws
            self._active_ws = None
        self._close_ws(ws, send_end=False)

    def _close_ws(self, ws, send_end: bool):
        if ws is None:
            return
        try:
            if send_end:
                try:
                    ws.send(json.dumps({"action": "end"}))
                except Exception:
                    pass
            ws.close()
        except Exception:
            pass

    def _normalize_server_urls(self, raw_server: str) -> tuple[str, str]:
        server = (raw_server or "http://127.0.0.1:8036").strip()
        parsed = urlparse(server)
        if not parsed.scheme:
            parsed = urlparse(f"http://{server}")

        base_path = parsed.path.rstrip("/")
        if base_path.endswith("/tts/ws"):
            api_base_path = base_path[:-7]
            ws_path = base_path
        elif base_path.endswith("/tts"):
            api_base_path = base_path[:-4]
            ws_path = f"{base_path}/ws"
        else:
            api_base_path = base_path
            ws_path = f"{base_path}/tts/ws"

        if parsed.scheme in ("ws", "wss"):
            ws_scheme = parsed.scheme
            http_scheme = "https" if parsed.scheme == "wss" else "http"
        else:
            ws_scheme = "wss" if parsed.scheme == "https" else "ws"
            http_scheme = parsed.scheme or "http"

        ws_url = urlunparse((ws_scheme, parsed.netloc, ws_path or "/tts/ws", "", "", ""))
        http_base = urlunparse((http_scheme, parsed.netloc, api_base_path or "", "", "", ""))
        return ws_url.rstrip("/"), http_base.rstrip("/")

    @staticmethod
    def _parse_json(message: str) -> dict:
        try:
            return json.loads(message)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid robot-tts message: {message}") from exc
