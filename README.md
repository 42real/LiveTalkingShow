# LiveTalking

LiveTalking 是实时数字人服务：输入文字或音频，驱动 avatar 生成说话视频，可通过 WebRTC、alpha WebSocket、RTMP 或虚拟摄像头输出。

当前交接主链路：

```text
robottts 兼容 TTS
  -> LiveTalking wav2lip/musetalk/ultralight 推理
  -> /alpha/ws 视频输出
  -> Web 测试页或 Electron 透明 overlay 显示
```

## 快速入口

| 文档 | 内容 |
| --- | --- |
| [README-LOCAL.md](README-LOCAL.md) | 部署、配置、模型下载、avatar 制作、测试和排错。 |
| [docs/API-PROTOCOL.md](docs/API-PROTOCOL.md) | LiveTalking、alpha stream、WebRTC、robottts 的接口协议。 |
| [testclient/README.md](testclient/README.md) | 测试 TTS、Web 测试页、Electron overlay 的使用说明。 |

## 最小启动

```bash
cd /path/to/LiveTalking
uv sync --python 3.10 --inexact
cp .env.example .env
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
./entrypoint.sh
```

本地测试 TTS 和显示端：

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
./start-tts.sh
./start-web.sh
./start-overlay.sh
```

默认端口：

| 服务 | 端口 |
| --- | --- |
| LiveTalking | `8050` |
| 测试 TTS | `8036` |
| Web 测试页 | `8070` |

## 核心能力

- `wav2lip`、`musetalk`、`ultralight` avatar 运行。
- `robottts` 兼容外部 TTS 接入。
- `/alpha/speak` 文本驱动。
- `/alpha/input/audio` 外部 PCM 音频流驱动。
- `/alpha/ws` RGBA/JPEG/PNG/WebP 视频帧输出。
- Electron 透明置顶 overlay。
- avatar 制作任务接口和命令行制作工具。

## 资产边界

代码进 Git；运行资产单独准备：

```text
models/*
data/avatars/*
.env
logs/
testclient/**/node_modules/
```

默认示例资产可通过：

```bash
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
```
