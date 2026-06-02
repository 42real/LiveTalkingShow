# LiveTalking

LiveTalking is a real-time digital-human service. It accepts text or audio, drives an avatar, and outputs talking video through WebRTC, alpha WebSocket, RTMP, or virtual camera.

Current handoff path:

```text
robottts-compatible TTS
  -> LiveTalking wav2lip/musetalk/ultralight inference
  -> /alpha/ws video stream
  -> Web test client or Electron transparent overlay
```

## Documents

| Document | Content |
| --- | --- |
| [README-LOCAL.md](README-LOCAL.md) | Deployment, configuration, model download, avatar creation, tests, troubleshooting. |
| [docs/API-PROTOCOL.md](docs/API-PROTOCOL.md) | LiveTalking, alpha stream, WebRTC, and robottts API protocol. |
| [testclient/README.md](testclient/README.md) | Test TTS backend, Web test page, and Electron overlay. |

## Minimal Start

```bash
cd /path/to/LiveTalking
uv sync --python 3.10 --inexact
cp .env.example .env
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
./entrypoint.sh
```

Test TTS and display clients:

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
./start-tts.sh
./start-web.sh
./start-overlay.sh
```

Default ports:

| Service | Port |
| --- | --- |
| LiveTalking | `8050` |
| Test TTS | `8036` |
| Web test client | `8070` |

Runtime assets are prepared separately:

```text
models/*
data/avatars/*
.env
logs/
testclient/**/node_modules/
```
