###############################################################################
#  Configuration loading
###############################################################################

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent


def str_or_int(value):
    """尝试转换为 int，失败则返回 str"""
    try:
        return int(value)
    except ValueError:
        return value


def _load_dotenv_defaults(dotenv_path: Path) -> None:
    """Load .env values only for keys that real ENV has not already set."""
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ[key] = value


def _deep_get(data: dict[str, Any], keys: list[str], default: Any) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _load_config() -> dict[str, Any]:
    env_file = Path(os.getenv("LIVETALKING_ENV_FILE", str(PROJECT_ROOT / ".env")))
    if not env_file.is_absolute():
        env_file = PROJECT_ROOT / env_file
    _load_dotenv_defaults(env_file)

    default_path = PROJECT_ROOT / "config.yaml"
    config_path = Path(os.getenv("LIVETALKING_CONFIG_PATH", os.getenv("LIVETALKING_CONFIG", str(default_path))))
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as file:
        parsed = yaml.safe_load(file) or {}
    if not isinstance(parsed, dict):
        raise ValueError(f"Invalid config structure in {config_path}")
    return parsed


def _env_value(name: str, default: Any) -> Any:
    value = os.getenv(name)
    return default if value is None else value


def _env_int(name: str, default: int) -> int:
    return int(_env_value(name, default))


def _env_float(name: str, default: float) -> float:
    return float(_env_value(name, default))


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_optional_value(name: str, default: Any) -> Any | None:
    value = os.getenv(name) if name in os.environ else default
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
        return None
    return value


def _apply_env_default(name: str, default: Any) -> None:
    if name in os.environ or default is None:
        return
    os.environ[name] = str(default)


_CONFIG = _load_config()
_apply_env_default("HF_ENDPOINT", _deep_get(_CONFIG, ["runtime", "hf_endpoint"], "https://hf-mirror.com"))
_apply_env_default("TTS_SERVER_URL", _deep_get(_CONFIG, ["tts", "server_url"], "http://127.0.0.1:8036"))


def parse_args():
    """解析命令行参数。部署配置优先级：ENV > .env > config.yaml。"""
    parser = argparse.ArgumentParser(description="LiveTalking Digital Human Server")

    # ─── 音频 ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--fps",
        type=int,
        default=_env_int("LIVETALKING_FPS", int(_deep_get(_CONFIG, ["avatar", "fps"], 25))),
        help="video fps, must be 25",
    )
    parser.add_argument("-l", type=int, default=_env_int("LIVETALKING_L", int(_deep_get(_CONFIG, ["avatar", "l"], 10))))
    parser.add_argument("-m", type=int, default=_env_int("LIVETALKING_M", int(_deep_get(_CONFIG, ["avatar", "m"], 8))))
    parser.add_argument("-r", type=int, default=_env_int("LIVETALKING_R", int(_deep_get(_CONFIG, ["avatar", "r"], 10))))

    # ─── 数字人模型 ────────────────────────────────────────────────────
    parser.add_argument(
        "--model",
        type=str,
        default=_env_value("LIVETALKING_MODEL", _deep_get(_CONFIG, ["avatar", "model"], "wav2lip")),
        help="avatar model: musetalk/wav2lip/ultralight",
    )
    parser.add_argument(
        "--avatar_id",
        type=str,
        default=_env_value("AVATAR_ID", _deep_get(_CONFIG, ["avatar", "avatar_id"], "wav2lip256_avatar1")),
        help="avatar id in data/avatars",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=_env_int("LIVETALKING_BATCH_SIZE", int(_deep_get(_CONFIG, ["avatar", "batch_size"], 16))),
        help="infer batch",
    )
    parser.add_argument(
        "--modelres",
        type=int,
        default=_env_int("LIVETALKING_MODELRES", int(_deep_get(_CONFIG, ["avatar", "modelres"], 192))),
    )
    parser.add_argument(
        "--modelfile",
        type=str,
        default=_env_value("LIVETALKING_MODELFILE", _deep_get(_CONFIG, ["avatar", "modelfile"], "")),
    )

    # ─── 自定义动作和多形象 ────────────────────────────────────────────
    parser.add_argument(
        "--customvideo_config",
        type=str,
        default=_env_value(
            "LIVETALKING_CUSTOMVIDEO_CONFIG",
            _deep_get(_CONFIG, ["avatar", "customvideo_config"], ""),
        ),
        help="custom action json",
    )

    # ─── TTS ───────────────────────────────────────────────────────────
    parser.add_argument(
        "--tts",
        type=str,
        default=_env_value("LIVETALKING_TTS", _deep_get(_CONFIG, ["tts", "provider"], "robottts")),
        help="tts plugin: robottts/gpt-sovits/cosyvoice/fishtts/tencent/doubao/indextts2/azuretts/qwentts/edgetts",
    )
    parser.add_argument(
        "--REF_FILE",
        type=str,
        default=_env_value("REF_FILE", _deep_get(_CONFIG, ["tts", "ref_file"], "zh-CN-YunxiaNeural")),
        help="参考文件名或语音模型ID",
    )
    parser.add_argument(
        "--REF_TEXT",
        type=str,
        default=_env_optional_value("REF_TEXT", _deep_get(_CONFIG, ["tts", "ref_text"], None)),
    )
    parser.add_argument(
        "--TTS_SERVER",
        type=str,
        default=_env_value("TTS_SERVER_URL", _deep_get(_CONFIG, ["tts", "server_url"], "http://127.0.0.1:8036")),
    )
    parser.add_argument(
        "--robottts_mode",
        type=str,
        default=_env_value("ROBOTTTS_MODE", _deep_get(_CONFIG, ["tts", "robottts_mode"], "instruct2")),
        help="robottts mode: instruct2/zero-shot",
    )
    parser.add_argument(
        "--robottts_connect_timeout",
        type=float,
        default=_env_float(
            "ROBOTTTS_CONNECT_TIMEOUT",
            float(_deep_get(_CONFIG, ["tts", "robottts_connect_timeout"], 10.0)),
        ),
        help="robottts websocket/http connect timeout",
    )
    parser.add_argument(
        "--robottts_receive_timeout",
        type=float,
        default=_env_float(
            "ROBOTTTS_RECEIVE_TIMEOUT",
            float(_deep_get(_CONFIG, ["tts", "robottts_receive_timeout"], 1.0)),
        ),
        help="robottts websocket receive timeout",
    )

    # ─── 传输 ─────────────────────────────────────────────────────────
    parser.add_argument(
        "--transport",
        type=str,
        default=_env_value("LIVETALKING_TRANSPORT", _deep_get(_CONFIG, ["output", "transport"], "webrtc")),
        help="output: rtcpush/webrtc/rtmp/virtualcam",
    )
    parser.add_argument(
        "--push_url",
        type=str,
        default=_env_value(
            "LIVETALKING_PUSH_URL",
            _deep_get(_CONFIG, ["output", "push_url"], "http://localhost:1985/rtc/v1/whip/?app=live&stream=livestream"),
        ),
    )
    parser.add_argument(
        "--max_session",
        type=int,
        default=_env_int("LIVETALKING_MAX_SESSION", int(_deep_get(_CONFIG, ["server", "max_session"], 1))),
    )
    parser.add_argument(
        "--listenhost",
        type=str,
        default=_env_value("LIVETALKING_HOST", _deep_get(_CONFIG, ["server", "host"], "0.0.0.0")),
        help="web listen host",
    )
    parser.add_argument(
        "--listenport",
        type=int,
        default=_env_int("LIVETALKING_PORT", int(_deep_get(_CONFIG, ["server", "port"], 8010))),
        help="web listen port",
    )
    parser.add_argument(
        "--alpha_output",
        action="store_true",
        default=_env_flag("LIVETALKING_ALPHA_OUTPUT", bool(_deep_get(_CONFIG, ["output", "alpha_output"], False))),
        help="enable transparent PNG frame websocket at /alpha/ws",
    )

    opt = parser.parse_args()

    # ─── 后处理 ────────────────────────────────────────────────────────
    opt.customopt = []
    if opt.customvideo_config:
        with open(opt.customvideo_config, "r") as f:
            opt.customopt = json.load(f)

    return opt
