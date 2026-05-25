# LiveTalking Test Client

这个目录是独立测试包，不参与 LiveTalking 主服务配置。

它包含三部分：

- `backend/`：自带 `robottts` 兼容 TTS 测试服务，可选 `edge` 或 `bailian` provider。
- `web/`：浏览器可视化测试页面，可发文本、启动 TTS task、查看 alpha 视频帧。
- `overlay/`：Electron 透明置顶显示窗口，用于模拟桌面助手显示。

根目录 `.env.example` 只用于 `testclient`，不要把这里的变量混到 LiveTalking 主仓库 `.env.example`。

独立性边界：

- `backend/` 使用自己的 `pyproject.toml` 和 `uv.lock`，不依赖 LiveTalking 的 `.venv`。
- `web/` 使用自己的 `package.json` 和 `package-lock.json`。
- `overlay/` 使用自己的 `package.json` 和 `package-lock.json`。
- `testclient/.env` 只影响测试客户端脚本；LiveTalking 主服务仍只读取主仓库自己的启动参数和环境变量。

## 1. 准备

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
set -a
source .env
set +a
```

## 2. 启动测试 TTS 后端

默认用 EdgeTTS：

```bash
./start-tts.sh
```

如果要用百炼：

```bash
export TEST_TTS_PROVIDER=bailian
export DASHSCOPE_API_KEY=你的百炼APIKey
./start-tts.sh
```

该后端提供：

- `GET /health`
- `GET /tts/voices`
- `POST /tts`
- `WS /tts/ws`
- `POST /tts/task/start`

## 3. 启动 LiveTalking

LiveTalking 仍然从仓库根目录启动，统一使用 `robottts`：

```bash
cd /path/to/LiveTalking
export AVATAR_ID=default_calm_1
export LIVETALKING_PORT=8050
export TTS_SERVER_URL=http://127.0.0.1:8036
uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --batch_size 4 \
  --tts robottts \
  --TTS_SERVER "$TTS_SERVER_URL" \
  --robottts_mode instruct2 \
  --listenport "$LIVETALKING_PORT" \
  --alpha_output
```

## 4. 启动可视化 Web 客户端

```bash
cd /path/to/LiveTalking/testclient
./start-web.sh
```

默认地址：

```text
http://127.0.0.1:8070
```

## 5. 启动桌面 Overlay

```bash
cd /path/to/LiveTalking/testclient
./start-overlay.sh
```

这个 overlay 是测试客户端自带的一份，依赖和配置都在 `testclient/overlay` 内部管理。
