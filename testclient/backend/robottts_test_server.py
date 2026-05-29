from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import platform
import subprocess
import tempfile
import uuid
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import edge_tts
import numpy as np
import resampy
import soundfile as sf
import websockets
from aiohttp import ClientSession, WSMsgType, web


logger = logging.getLogger("robottts_test_server")

DEFAULT_PORT = 8036
DEFAULT_EDGE_VOICES = [
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunxiaNeural",
    "zh-CN-YunjianNeural",
    "en-US-JennyNeural",
]
DEFAULT_BAILIAN_VOICES = [
    "longanyang",
    "longanhuan",
    "longhuhu_v3",
    "longpaopao_v3",
    "longjielidou_v3",
    "longxian_v3",
    "longling_v3",
    "longshanshan_v3",
    "longniuniu_v3",
    "longjiaxin_v3",
    "longjiayi_v3",
    "longanyue_v3",
    "longlaotie_v3",
]
BAILIAN_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
VALID_MODES = {"zero-shot", "instruct2"}


@dataclass
class StreamSession:
    state: str = "idle"
    voice_id: int = 0
    prompts: str = ""
    mode: str = "instruct2"


@dataclass
class TaskRecord:
    task_id: str
    voice_id: int
    prompts: str
    mode: str
    target_hardware: str
    text: str | None = None
    state: str = "started"
    runner: asyncio.Task | None = None
    cancel_event: asyncio.Event | None = None


def _get_host() -> str:
    return os.getenv("TTS_SERVICE_HOST", "0.0.0.0")


def _get_port() -> int:
    return int(os.getenv("TTS_SERVICE_PORT", DEFAULT_PORT))


def _get_sample_rate() -> int:
    return int(os.getenv("TTS_STREAM_SAMPLE_RATE", "16000"))


def _get_chunk_ms() -> int:
    return max(20, int(os.getenv("TTS_STREAM_CHUNK_MS", "40")))


def _get_default_mode() -> str:
    return os.getenv("TTS_DEFAULT_MODE", "instruct2")


def _get_provider() -> str:
    raw = os.getenv("TEST_TTS_PROVIDER", "edge").strip().lower()
    if raw in {"edge", "edgetts"}:
        return "edge"
    if raw in {"bailian", "cosyvoice", "cosyvoice3"}:
        return "bailian"
    raise ValueError("TEST_TTS_PROVIDER must be edge or bailian")


def _use_sapi_fallback() -> bool:
    enabled = os.getenv("TEST_TTS_SAPI_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "on"}
    return enabled and platform.system().lower() == "windows"


def _get_voices() -> list[str]:
    provider = _get_provider()
    env_name = "BAILIAN_VOICES" if provider == "bailian" else "ROBOT_TTS_EDGE_VOICES"
    raw = os.getenv(env_name, "")
    voices = [item.strip() for item in raw.split(",") if item.strip()]
    return voices or (DEFAULT_BAILIAN_VOICES if provider == "bailian" else DEFAULT_EDGE_VOICES)


def _get_voice_name(voice_id: int) -> str:
    voices = _get_voices()
    if voice_id < 0 or voice_id >= len(voices):
        raise ValueError(f"voice_id out of range: {voice_id}; max is {len(voices) - 1}")
    return voices[voice_id]


def _validate_text(text) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text cannot be empty")
    return text


def _validate_voice_id(voice_id) -> int:
    if not isinstance(voice_id, int):
        raise ValueError("voice_id must be an integer")
    _get_voice_name(voice_id)
    return voice_id


def _validate_mode(mode) -> str:
    resolved = mode or _get_default_mode()
    if not isinstance(resolved, str) or resolved not in VALID_MODES:
        raise ValueError("mode must be zero-shot or instruct2")
    return resolved


def _stream_meta() -> dict:
    provider = _get_provider()
    meta = {
        "sample_rate": _get_sample_rate(),
        "channels": 1,
        "sample_width": 2,
        "format": "pcm",
        "provider": provider,
    }
    if provider == "bailian":
        meta["model"] = _get_bailian_model()
    return meta


def _json_response(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _json_error(message: str, status: int = 400, error: str = "InvalidRequest") -> web.Response:
    return _json_response({"error": error, "message": message}, status=status)


def _cors_origin() -> str:
    return os.getenv("TEST_TTS_CORS_ORIGIN", "*")


def _add_cors_headers(response: web.StreamResponse) -> web.StreamResponse:
    response.headers["Access-Control-Allow-Origin"] = _cors_origin()
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


@web.middleware
async def cors_middleware(request: web.Request, handler):
    if request.method == "OPTIONS":
        return _add_cors_headers(web.Response(status=204))
    response = await handler(request)
    return _add_cors_headers(response)


def _iter_pcm_chunks(pcm: bytes):
    frame_bytes = max(1, int(_get_sample_rate() * _get_chunk_ms() / 1000)) * 2
    for offset in range(0, len(pcm), frame_bytes):
        chunk = pcm[offset : offset + frame_bytes]
        if chunk:
            yield chunk


async def _synthesize_edge_pcm(text: str, voice_id: int) -> bytes:
    voice = _get_voice_name(voice_id)
    buffer = BytesIO()
    communicate = edge_tts.Communicate(
        text,
        voice,
        rate=os.getenv("ROBOT_TTS_EDGE_RATE", "+0%"),
        volume=os.getenv("ROBOT_TTS_EDGE_VOLUME", "+0%"),
        pitch=os.getenv("ROBOT_TTS_EDGE_PITCH", "+0Hz"),
    )
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            buffer.write(chunk["data"])

    if buffer.getbuffer().nbytes <= 0:
        raise RuntimeError("edgetts returned empty audio")

    buffer.seek(0)
    stream, sample_rate = sf.read(buffer, dtype="float32")
    if stream.ndim > 1:
        stream = stream[:, 0]

    target_rate = _get_sample_rate()
    if sample_rate != target_rate and stream.size > 0:
        stream = resampy.resample(stream, sample_rate, target_rate)

    stream = np.clip(stream, -1.0, 1.0)
    return (stream * 32767.0).astype("<i2").tobytes()


async def _synthesize_sapi_pcm(text: str) -> bytes:
    def run_sapi():
        with tempfile.TemporaryDirectory(prefix="robottts-sapi-") as tmp_dir:
            wav_path = Path(tmp_dir) / "speech.wav"
            script = (
                "Add-Type -AssemblyName System.Speech; "
                f"$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.SetOutputToWaveFile('{wav_path}'); "
                f"$s.Speak({json.dumps(text, ensure_ascii=False)}); "
                "$s.Dispose();"
            )
            subprocess.run(
                ["pwsh", "-NoProfile", "-Command", script],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            stream, sample_rate = sf.read(str(wav_path), dtype="float32")

        if stream.ndim > 1:
            stream = stream[:, 0]

        target_rate = _get_sample_rate()
        if sample_rate != target_rate and stream.size > 0:
            stream = resampy.resample(stream, sample_rate, target_rate)

        stream = np.clip(stream, -1.0, 1.0)
        return (stream * 32767.0).astype("<i2").tobytes()

    return await asyncio.to_thread(run_sapi)


def _get_bailian_api_key() -> str:
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("BAILIAN_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY or BAILIAN_API_KEY is required when TEST_TTS_PROVIDER=bailian")
    return api_key


def _get_bailian_model() -> str:
    return os.getenv("BAILIAN_COSYVOICE_MODEL", "cosyvoice-v3-flash")


def _get_bailian_upstream_url() -> str:
    return os.getenv("BAILIAN_WS_URL", BAILIAN_WS_URL)


def _get_bailian_instruction_field() -> str:
    return os.getenv("BAILIAN_INSTRUCTION_FIELD", "instructions")


def _use_prompts_as_instructions() -> bool:
    return os.getenv("BAILIAN_USE_PROMPTS_AS_INSTRUCTIONS", "1").strip().lower() not in {"0", "false", "no", "off"}


def _build_bailian_run_task(task_id: str, voice: str, prompts: str, mode: str) -> dict:
    parameters = {
        "text_type": "PlainText",
        "voice": voice,
        "format": "pcm",
        "sample_rate": _get_sample_rate(),
        "volume": 50,
        "rate": 1,
        "pitch": 1,
        "enable_ssml": False,
    }
    if prompts and _use_prompts_as_instructions():
        parameters[_get_bailian_instruction_field()] = prompts
    return {
        "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
        "payload": {
            "task_group": "audio",
            "task": "tts",
            "function": "SpeechSynthesizer",
            "model": _get_bailian_model(),
            "parameters": parameters,
            "input": {},
        },
    }


def _build_bailian_continue_task(task_id: str, text: str) -> dict:
    return {
        "header": {"action": "continue-task", "task_id": task_id, "streaming": "duplex"},
        "payload": {"input": {"text": text}},
    }


def _build_bailian_finish_task(task_id: str) -> dict:
    return {
        "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
        "payload": {"input": {}},
    }


def _parse_json_text(message: str | bytes) -> dict | None:
    if isinstance(message, bytes):
        return None
    try:
        return json.loads(message)
    except json.JSONDecodeError:
        return None


async def _connect_bailian(headers: dict):
    kwargs = {
        "ping_interval": 20,
        "ping_timeout": 20,
        "max_size": None,
    }
    try:
        return websockets.connect(_get_bailian_upstream_url(), additional_headers=headers, **kwargs)
    except TypeError:
        return websockets.connect(_get_bailian_upstream_url(), extra_headers=headers, **kwargs)


async def _iter_bailian_chunks(text: str, voice_id: int, prompts: str, mode: str):
    task_id = str(uuid.uuid4())
    headers = {
        "Authorization": f"bearer {_get_bailian_api_key()}",
        "X-DashScope-DataInspection": os.getenv("BAILIAN_DATA_INSPECTION", "enable"),
    }
    voice = _get_voice_name(voice_id)

    connect_context = await _connect_bailian(headers)
    async with connect_context as upstream:
        await upstream.send(json.dumps(_build_bailian_run_task(task_id, voice, prompts, mode)))

        while True:
            payload = _parse_json_text(await upstream.recv())
            if not payload:
                continue
            header = payload.get("header", {})
            event = header.get("event")
            if event == "task-started":
                break
            if event == "task-failed":
                raise RuntimeError(header.get("error_message", "Bailian task failed"))

        await upstream.send(json.dumps(_build_bailian_continue_task(task_id, text)))
        await upstream.send(json.dumps(_build_bailian_finish_task(task_id)))

        while True:
            message = await upstream.recv()
            if isinstance(message, bytes):
                yield message
                continue

            payload = _parse_json_text(message) or {}
            header = payload.get("header", {})
            event = header.get("event")
            if event == "task-finished":
                return
            if event == "task-failed":
                raise RuntimeError(header.get("error_message", "Bailian task failed"))

            audio_b64 = payload.get("payload", {}).get("output", {}).get("audio")
            if audio_b64:
                yield base64.b64decode(audio_b64)


async def _iter_tts_chunks(text: str, voice_id: int, prompts: str, mode: str):
    if _get_provider() == "bailian":
        async for chunk in _iter_bailian_chunks(text, voice_id, prompts, mode):
            yield chunk
        return

    try:
        pcm = await _synthesize_edge_pcm(text, voice_id)
    except Exception:
        if not _use_sapi_fallback():
            raise
        logger.exception("edge synthesis failed; falling back to Windows SAPI")
        pcm = await _synthesize_sapi_pcm(text)
    for chunk in _iter_pcm_chunks(pcm):
        yield chunk


async def _synthesize_pcm(text: str, voice_id: int, prompts: str, mode: str) -> bytes:
    chunks = []
    async for chunk in _iter_tts_chunks(text, voice_id, prompts, mode):
        chunks.append(chunk)
    return b"".join(chunks)


def _write_wav(path: Path, pcm: bytes) -> float:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(_get_sample_rate())
        wav_file.writeframes(pcm)
    frame_count = len(pcm) // 2
    return frame_count / float(_get_sample_rate())


async def _push_audio_to_target(record: TaskRecord) -> None:
    async with ClientSession() as session:
        async with session.ws_connect(record.target_hardware, max_msg_size=0) as ws:
            start_payload = {
                "type": "start",
                "task_id": record.task_id,
                "stream_name": "tts",
                "text": record.text or "",
                **_stream_meta(),
            }
            await ws.send_str(json.dumps(start_payload))

            ack = await ws.receive(timeout=10)
            if ack.type != WSMsgType.TEXT:
                raise RuntimeError("target did not return a JSON start acknowledgement")
            ack_payload = json.loads(ack.data)
            if ack_payload.get("type") != "started":
                raise RuntimeError(f"unexpected target acknowledgement: {ack_payload}")

            async for chunk in _iter_tts_chunks(record.text or "", record.voice_id, record.prompts, record.mode):
                if record.cancel_event is not None and record.cancel_event.is_set():
                    break
                await ws.send_bytes(chunk)

            reason = "cancelled" if record.cancel_event and record.cancel_event.is_set() else "completed"
            await ws.send_str(json.dumps({"type": "end", "task_id": record.task_id, "reason": reason}))


def create_app() -> web.Application:
    app = web.Application(client_max_size=1024**2 * 100, middlewares=[cors_middleware])
    stream_lock = asyncio.Lock()
    task_lock = asyncio.Lock()
    tasks: dict[str, TaskRecord] = {}
    active_task_id: str | None = None

    async def health(request):
        return _json_response({"status": "ok", **_stream_meta()})

    async def voices(request):
        return _json_response(
            {
                "voices": [
                    {"id": index, "name": name, "description": name}
                    for index, name in enumerate(_get_voices())
                ]
            }
        )

    async def synthesize(request):
        try:
            payload = await request.json()
            text = _validate_text(payload.get("text"))
            voice_id = _validate_voice_id(payload.get("voice_id", 0))
            mode = _validate_mode(payload.get("mode"))
            prompts = str(payload.get("prompts", ""))
            output_path = Path(payload.get("output_path") or "/tmp/robottts-edge-output.wav")
            pcm = await _synthesize_pcm(text, voice_id, prompts, mode)
            duration = _write_wav(output_path, pcm)
            return _json_response({"success": True, "audio_path": str(output_path), "duration": round(duration, 2)})
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        except Exception as exc:
            logger.exception("synthesize failed")
            return _json_error(str(exc), status=500, error="InternalServerError")

    async def stream_tts(request):
        ws = web.WebSocketResponse(max_msg_size=0, compress=False)
        await ws.prepare(request)
        session = StreamSession()
        lock_acquired = False

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                    except json.JSONDecodeError:
                        await ws.send_json({"action": "error", "error": "InvalidRequest", "message": "message must be JSON"})
                        continue

                    action = payload.get("action")
                    if action == "start":
                        if stream_lock.locked():
                            await ws.send_json({"action": "error", "error": "Busy", "message": "another stream is active"})
                            await ws.close(code=1013)
                            break
                        try:
                            session.voice_id = _validate_voice_id(payload.get("voice_id", 0))
                            session.prompts = str(payload.get("prompts", ""))
                            session.mode = _validate_mode(payload.get("mode"))
                        except ValueError as exc:
                            await ws.send_json({"action": "error", "error": "InvalidRequest", "message": str(exc)})
                            continue
                        await stream_lock.acquire()
                        lock_acquired = True
                        session.state = "started"
                        await ws.send_json({"action": "started"})
                        continue

                    if action == "text":
                        if session.state != "started":
                            await ws.send_json({"action": "error", "error": "InvalidState", "message": "text is only allowed after start"})
                            continue
                        try:
                            text = _validate_text(payload.get("text"))
                        except Exception as exc:
                            logger.exception("stream text failed")
                            await ws.send_json({"action": "error", "error": "SynthesisError", "message": str(exc)})
                            continue
                        try:
                            async for chunk in _iter_tts_chunks(text, session.voice_id, session.prompts, session.mode):
                                await ws.send_bytes(chunk)
                        except Exception as exc:
                            logger.exception("stream synthesis failed")
                            await ws.send_json({"action": "error", "error": "SynthesisError", "message": str(exc)})
                            continue
                        meta = _stream_meta()
                        meta["voice"] = _get_voice_name(session.voice_id)
                        await ws.send_json({"action": "result", "type": "final", "meta": meta})
                        continue

                    if action == "end":
                        await ws.close(code=1000)
                        break

                    await ws.send_json({"action": "error", "error": "InvalidRequest", "message": "unknown action"})
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            if lock_acquired and stream_lock.locked():
                stream_lock.release()
        return ws

    async def _create_record(payload: dict):
        nonlocal active_task_id
        try:
            task_id = str(payload.get("task_id", "")).strip()
            if not task_id:
                raise ValueError("task_id cannot be empty")
            target_hardware = str(payload.get("target_hardware", "")).strip()
            if not target_hardware:
                raise ValueError("target_hardware cannot be empty")
            voice_id = _validate_voice_id(payload.get("voice_id", 0))
            prompts = str(payload.get("prompts", ""))
            mode = _validate_mode(payload.get("mode"))
        except ValueError as exc:
            return _json_error(str(exc), status=400)

        async with task_lock:
            if task_id in tasks:
                return _json_error("task_id already exists", status=400)
            if active_task_id is not None:
                return _json_error("another task is active", status=409, error="Busy")
            tasks[task_id] = TaskRecord(
                task_id=task_id,
                voice_id=voice_id,
                prompts=prompts,
                mode=mode,
                target_hardware=target_hardware,
                cancel_event=asyncio.Event(),
            )
            active_task_id = task_id
        return _json_response({"success": True, "task_id": task_id, "state": "started"})

    async def create_task(request):
        payload = await request.json()
        return await _create_record(payload)

    async def _submit_record(payload: dict):
        try:
            task_id = str(payload.get("task_id", "")).strip()
            text = _validate_text(payload.get("text"))
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        async with task_lock:
            record = tasks.get(task_id)
            if record is None:
                return _json_error("task_id not found", status=404, error="NotFound")
            if record.runner is not None:
                return _json_error("task already submitted", status=400, error="InvalidState")
            record.text = text
            record.runner = asyncio.create_task(_run_task(record))
        return _json_response({"success": True, "task_id": task_id, "state": "submitted"})

    async def _run_task(record: TaskRecord):
        nonlocal active_task_id
        record.state = "synthesizing"
        try:
            await _push_audio_to_target(record)
            record.state = "cancelled" if record.cancel_event and record.cancel_event.is_set() else "done"
        except Exception:
            logger.exception("task %s failed", record.task_id)
            record.state = "cancelled" if record.cancel_event and record.cancel_event.is_set() else "error"
        finally:
            async with task_lock:
                if active_task_id == record.task_id:
                    active_task_id = None

    async def submit_task(request):
        payload = await request.json()
        return await _submit_record(payload)

    async def start_task(request):
        payload = await request.json()
        task_id = str(payload.get("task_id") or uuid.uuid4())
        payload["task_id"] = task_id
        created = await _create_record({k: v for k, v in payload.items() if k != "text"})
        if created.status != 200:
            return created
        return await _submit_record({"task_id": task_id, "text": payload.get("text", "")})

    async def cancel_task(request):
        nonlocal active_task_id
        payload = await request.json()
        task_id = str(payload.get("task_id", "")).strip()
        async with task_lock:
            record = tasks.get(task_id)
            if record is None:
                return _json_error("task_id not found", status=404, error="NotFound")
            if record.cancel_event is not None:
                record.cancel_event.set()
            record.state = "cancelled"
            if active_task_id == task_id and record.runner is None:
                active_task_id = None
        return _json_response({"success": True, "task_id": task_id, "state": "cancelled"})

    async def task_status(request):
        task_id = str(request.query.get("task_id", "")).strip()
        record = tasks.get(task_id)
        if record is None:
            return _json_error("task_id not found", status=404, error="NotFound")
        return _json_response(
            {
                "task_id": task_id,
                "state": record.state,
                "owns_active_slot": active_task_id == task_id,
            }
        )

    app.router.add_get("/health", health)
    app.router.add_get("/tts/voices", voices)
    app.router.add_post("/tts", synthesize)
    app.router.add_get("/tts/ws", stream_tts)
    app.router.add_post("/tts/task/create", create_task)
    app.router.add_post("/tts/task/submit", submit_task)
    app.router.add_post("/tts/task/start", start_task)
    app.router.add_post("/tts/task/cancel", cancel_task)
    app.router.add_get("/tts/task/status", task_status)
    app.router.add_route("OPTIONS", "/{tail:.*}", lambda request: web.Response(status=204))
    return app


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    logger.info("starting robottts test server provider=%s on %s:%s", _get_provider(), _get_host(), _get_port())
    web.run_app(create_app(), host=_get_host(), port=_get_port())


if __name__ == "__main__":
    main()
