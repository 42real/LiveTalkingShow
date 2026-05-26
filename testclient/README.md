# LiveTalking Test Client

这个目录是独立测试包，用来模拟生产里的 TTS 服务、控制端和显示端，不参与 LiveTalking 主服务配置。

LiveTalking 主服务使用仓库根目录的 `uv` 环境；`testclient/backend` 也使用自己的 `uv` 环境。Web 和 overlay 是 Node/npm 项目，只用于显示和交互测试，不使用 conda。

它包含三部分：

- `backend/`：自带 `robottts` 兼容 TTS 测试服务，可选 `edge` 或 `bailian` provider。
- `web/`：浏览器可视化测试页面，可发文本、启动 TTS task、查看 alpha 视频帧并播放 alpha 音频输出。
- `overlay/`：Electron 透明置顶显示窗口，用于模拟桌面助手显示。

默认显示链路是 alpha stream。LiveTalking 主服务默认开启 `LIVETALKING_ALPHA_OUTPUT=1`，Web 测试页打开后会自动创建 alpha session 并连接 `/alpha/ws`，overlay 也只连接 `/alpha/ws` 显示视频。官方 WebRTC 页面仍可用，但不是 testclient 的默认显示方式。

根目录 `.env.example` 只用于 `testclient`，不要把这里的变量混到 LiveTalking 主仓库 `.env.example`。

独立性边界：

- `backend/` 使用自己的 `pyproject.toml` 和 `uv.lock`，不依赖 LiveTalking 的 `.venv`。
- `web/` 使用自己的 `package.json` 和 `package-lock.json`。
- `overlay/` 使用自己的 `package.json` 和 `package-lock.json`。
- `testclient/.env` 只影响测试客户端脚本；LiveTalking 主服务仍只读取主仓库自己的启动参数和环境变量。

## 0. 整体运行关系

```text
testclient/backend，默认 8036
  提供 robottts 兼容 TTS API
  输入文本，输出 16kHz mono PCM16

LiveTalking 主服务，默认 8050
  TTS_SERVER_URL=http://127.0.0.1:8036
  接收 /alpha/speak 文本或 /alpha/input/audio 音频
  输出 /alpha/ws 视频和 /alpha/audio 音频

testclient/web，默认 8070
  浏览器控制台
  调 TTS health/voices/task
  默认自动调 LiveTalking alpha/session 并连接 alpha/ws
  可手动测试 alpha/speak、alpha/audio 和 TTS task

testclient/overlay，本机 Electron
  只负责显示透明置顶窗口
  默认连接 LiveTalking /alpha/session 和 /alpha/ws
```

最常用启动顺序：

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
./start-tts.sh
```

另开终端：

```bash
cd /path/to/LiveTalking
cp .env.example .env
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
./entrypoint.sh
```

再另开终端：

```bash
cd /path/to/LiveTalking/testclient
./start-web.sh
```

需要桌面透明窗口时：

```bash
cd /path/to/LiveTalking/testclient
./start-overlay.sh
```

每个服务只需要知道接口地址：

| 服务 | 需要配置 | 默认值 | 说明 |
| --- | --- | --- | --- |
| LiveTalking | `TTS_SERVER_URL` | `http://127.0.0.1:8036` | 指向 `robottts` 兼容 TTS 服务。 |
| testclient/backend | `TTS_SERVICE_PORT` | `8036` | 自己监听的 TTS 端口。 |
| testclient/web | `VITE_LIVETALKING_URL`、`VITE_TTS_SERVER_URL`、`VITE_ALPHA_INPUT_WS` | `8050/8036` | 浏览器要同时访问 LiveTalking 和 TTS。 |
| testclient/overlay | `LIVETALKING_SERVER` | `http://127.0.0.1:8050` | 只连接 LiveTalking，不直接连 TTS。 |

关键规则：

- LiveTalking 主服务的 `LIVETALKING_TRANSPORT` 保持 `webrtc`。alpha 透明输出不是 transport，而是 `LIVETALKING_ALPHA_OUTPUT=1`。
- 改 LiveTalking 端口时，同时改 `LIVETALKING_URL`、`LIVETALKING_WS_URL`、`LIVETALKING_SERVER`、`VITE_LIVETALKING_URL`、`VITE_ALPHA_INPUT_WS`。
- 改 TTS 端口时，同时改 `TTS_SERVER_URL` 和 `VITE_TTS_SERVER_URL`。
- `VITE_*` 变量只在 Web 客户端启动时读取；改完 `testclient/.env` 后要重启 `./start-web.sh`。
- 远程浏览器访问时不要写 `127.0.0.1`，除非已经做了对应端口转发。

## 1. 准备

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
```

`start-tts.sh`、`start-web.sh`、`start-overlay.sh` 会自动读取 `testclient/.env`。

## 2. 启动测试 TTS 后端

默认用 EdgeTTS：

```bash
./start-tts.sh
```

如果要用百炼：

```bash
TEST_TTS_PROVIDER=bailian DASHSCOPE_API_KEY=你的百炼APIKey ./start-tts.sh
```

该后端提供：

- `GET /health`
- `GET /tts/voices`
- `POST /tts`
- `WS /tts/ws`
- `POST /tts/task/create`
- `POST /tts/task/submit`
- `POST /tts/task/start`
- `POST /tts/task/cancel`
- `GET /tts/task/status?task_id=...`

### 2.1 后端 TTS API 数据格式

`GET /health` 返回当前 provider 和音频格式：

```json
{
  "status": "ok",
  "sample_rate": 16000,
  "channels": 1,
  "sample_width": 2,
  "format": "pcm",
  "provider": "edge"
}
```

`GET /tts/voices` 返回音色：

```json
{
  "voices": [
    {"id": 0, "name": "zh-CN-XiaoxiaoNeural", "description": "zh-CN-XiaoxiaoNeural"}
  ]
}
```

`WS /tts/ws` 是 LiveTalking 的 `robottts` 插件使用的接口：

```text
LiveTalking -> TTS JSON:
{"action":"start","voice_id":0,"mode":"instruct2","prompts":"请自然清晰地朗读。"}

TTS -> LiveTalking JSON:
{"action":"started"}

LiveTalking -> TTS JSON:
{"action":"text","text":"要朗读的文字"}

TTS -> LiveTalking binary:
PCM16 chunk bytes

TTS -> LiveTalking JSON:
{"action":"result","type":"final","meta":{"sample_rate":16000,"channels":1,"sample_width":2,"format":"pcm","provider":"edge"}}
```

`POST /tts/task/start` 是外部 TTS 主动推流到 LiveTalking 的接口：

```json
{
  "task_id": "demo-001",
  "text": "这段话由 TTS 服务生成音频，再推给 LiveTalking。",
  "voice_id": 0,
  "mode": "instruct2",
  "prompts": "请自然清晰地朗读。",
  "target_hardware": "ws://127.0.0.1:8050/alpha/input/audio"
}
```

调用后 `testclient/backend` 会连接 `target_hardware`，先发 `start` JSON，再发 PCM16 binary chunks，最后发 `end` JSON。

### 2.2 TTS 后端配置

| 变量 | 可选/范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `TEST_TTS_PROVIDER` | `edge` / `bailian` | `edge` | 选择测试 provider。生产环境接真实 robot-tts 时不需要启动这个后端。 |
| `TTS_SERVICE_HOST` | IP | `0.0.0.0` | TTS 测试服务监听地址。 |
| `TTS_SERVICE_PORT` | `1-65535` | `8036` | TTS 测试服务端口。改动后同步 `TTS_SERVER_URL` 和 `VITE_TTS_SERVER_URL`。 |
| `TTS_SERVER_URL` | HTTP 地址 | `http://127.0.0.1:8036` | 给 LiveTalking 或测试脚本使用的 TTS HTTP 基地址。 |
| `TTS_DEFAULT_MODE` | `instruct2` / `zero-shot` | `instruct2` | 未显式传 mode 时使用的默认模式。 |
| `TTS_STREAM_SAMPLE_RATE` | 正整数 | `16000` | 输出 PCM 采样率。LiveTalking 推荐 16kHz。 |
| `TTS_STREAM_CHUNK_MS` | 正整数，建议 `20-100` | `40` | 每个 PCM chunk 的时长。越小延迟越低，但包更多。 |
| `TEST_TTS_CORS_ORIGIN` | CORS origin | `*` | 浏览器测试页跨域访问 TTS 时使用。 |
| `ROBOT_TTS_EDGE_VOICES` | 逗号分隔音色名 | 常用中文/英文音色 | EdgeTTS 可选音色列表，`voice_id` 按列表顺序编号。 |
| `ROBOT_TTS_EDGE_RATE` | EdgeTTS rate | `+0%` | EdgeTTS 语速，如 `+10%`、`-10%`。 |
| `ROBOT_TTS_EDGE_VOLUME` | EdgeTTS volume | `+0%` | EdgeTTS 音量。 |
| `ROBOT_TTS_EDGE_PITCH` | EdgeTTS pitch | `+0Hz` | EdgeTTS 音高。 |
| `DASHSCOPE_API_KEY` | 字符串 | 空 | 百炼 provider 必填。不要提交到 Git。 |
| `BAILIAN_COSYVOICE_MODEL` | 模型名 | `cosyvoice-v3-flash` | 百炼 CosyVoice 模型名。 |
| `BAILIAN_VOICES` | 逗号分隔音色名 | `longanyang,longanhuan,longhuhu_v3` | 百炼音色列表，`voice_id` 按列表顺序编号。 |
| `BAILIAN_INSTRUCTION_FIELD` | 字段名 | `instructions` | 百炼请求里用于提示词/指令的字段名。 |
| `BAILIAN_USE_PROMPTS_AS_INSTRUCTIONS` | `1/0` | `1` | 是否把页面或 API 的 `prompts` 透传给百炼指令字段。 |

## 3. 启动 LiveTalking

LiveTalking 仍然从仓库根目录启动，统一使用 `robottts`：

```bash
cd /path/to/LiveTalking
cp .env.example .env
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
./entrypoint.sh
```

主服务配置在仓库根目录的 `.env` 或 `config.yaml`，优先级是：

```text
ENV > .env > config.yaml
```

最关键配置：

```bash
LIVETALKING_PORT=8050
LIVETALKING_MODEL=wav2lip
AVATAR_ID=wav2lip_avatar_female_model
LIVETALKING_TTS=robottts
TTS_SERVER_URL=http://127.0.0.1:8036
LIVETALKING_ALPHA_OUTPUT=1
```

`LIVETALKING_ALPHA_OUTPUT=1` 会打开这些输出/输入接口：

```text
POST /alpha/session
POST /alpha/speak
WS   /alpha/ws
WS   /alpha/audio
WS   /alpha/input/audio
POST /alpha/close
```

LiveTalking 接到文本后如何连 TTS：

```text
testclient/web 或控制端
  -> POST http://127.0.0.1:8050/alpha/speak
  -> LiveTalking tts/robottts.py
  -> WS ws://127.0.0.1:8036/tts/ws
  -> TTS 返回 PCM16 binary chunks
  -> LiveTalking 驱动 avatar 推理
  -> /alpha/ws 输出 RGBA 视频
```

外部 TTS 主动推音频时：

```text
testclient/web 或控制端
  -> POST http://127.0.0.1:8036/tts/task/start
  -> testclient/backend 连接 ws://127.0.0.1:8050/alpha/input/audio
  -> 推送 PCM16 binary chunks
  -> LiveTalking 驱动 avatar 推理
  -> /alpha/ws 输出 RGBA 视频
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

Web 页面按钮和接口对应关系：

| 页面动作 | 调用接口 | 传输内容 |
| --- | --- | --- |
| 健康检查 | `GET <TTS>/health`、`GET <LiveTalking>/api/admin/config` | JSON。 |
| 音色 | `GET <TTS>/tts/voices` | JSON 音色列表。 |
| 创建 session | `POST <LiveTalking>/alpha/session` | JSON，通常 `{ "reuse": true }`。 |
| `alpha/speak` | `POST <LiveTalking>/alpha/speak` | JSON 文本和 TTS 参数。 |
| TTS task | `POST <TTS>/tts/task/start` | JSON task，包含 `target_hardware`。 |
| 视频 | `WS <LiveTalking>/alpha/ws?max_height=720&fps=8` | binary，24 字节 header + RGBA8。 |
| 音频 | `WS <LiveTalking>/alpha/audio` | binary，PCM16。 |
| 中断 | `POST <LiveTalking>/interrupt_talk` | JSON sessionid。 |
| 关闭 | `POST <LiveTalking>/alpha/close` | JSON sessionid。 |

`alpha/speak` 请求示例：

```json
{
  "text": "你好，我是桌面数字人。",
  "type": "echo",
  "interrupt": true,
  "tts": {
    "voice_id": 0,
    "mode": "instruct2",
    "prompts": "请自然清晰地朗读。"
  }
}
```

Web 预览默认连接：

```text
ws://127.0.0.1:8050/alpha/ws?max_height=720&fps=8
```

打开 Web 页面时会自动创建 alpha session 并连接上面的 alpha stream。`VITE_ALPHA_AUTO_CONNECT=0` 可关闭自动连接。

这是为了避免浏览器直接处理高分辨率 raw RGBA 帧导致卡顿。这个缩放只影响当前 Web 客户端，不改变 LiveTalking 原始输出，也不改变 overlay 的显示尺寸。

### 4.1 Web 配置

| 变量 | 可选/范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `TEST_CLIENT_HOST` | IP | `0.0.0.0` | Vite Web 测试页监听地址。 |
| `TEST_CLIENT_PORT` | `1-65535` | `8070` | Vite Web 测试页端口。 |
| `VITE_LIVETALKING_URL` | HTTP 地址 | `http://127.0.0.1:8050` | 浏览器访问 LiveTalking 的 HTTP 基地址。 |
| `VITE_TTS_SERVER_URL` | HTTP 地址 | `http://127.0.0.1:8036` | 浏览器访问 robottts 兼容 TTS 的 HTTP 基地址。 |
| `VITE_ALPHA_INPUT_WS` | WebSocket 地址 | `ws://127.0.0.1:8050/alpha/input/audio` | TTS task 推流目标。端口必须和 LiveTalking 一致。 |
| `VITE_ALPHA_AUDIO_SAMPLE_RATE` | 正整数 | `16000` | 浏览器播放 `/alpha/audio` 时使用的采样率。 |
| `VITE_ALPHA_VIDEO_MAX_HEIGHT` | 非负整数 px | `720` | Web 预览请求 `/alpha/ws` 的最大高度，`0` 表示不限制。 |
| `VITE_ALPHA_VIDEO_FPS` | 非负数 | `8` | Web 预览请求 `/alpha/ws` 的帧率，`0` 表示不限制。 |
| `VITE_VIDEO_RENDER_INTERVAL_MS` | 非负整数 ms | `125` | 浏览器 canvas 渲染限频。按钮卡顿时可调大。 |
| `VITE_ALPHA_AUTO_CONNECT` | `1/0` | `1` | 页面打开后是否自动创建 alpha session 并连接视频。 |
| `VITE_DEFAULT_TEXT` | 字符串 | 示例文本 | 页面输入框默认文本。 |
| `VITE_DEFAULT_PROMPTS` | 字符串 | 示例提示词 | 页面 TTS prompts 默认值。 |
| `VITE_DEFAULT_VOICE_ID` | 非负整数 | `0` | 页面默认音色编号。 |
| `VITE_DEFAULT_MODE` | `instruct2` / `zero-shot` | `instruct2` | 页面默认 TTS 模式。 |

Web 页面只用于测试和控制，不负责真正的桌面置顶显示。要叠在 PPT 上显示数字人，使用 overlay 或自研显示端消费 `/alpha/ws`。

## 5. 启动桌面 Overlay

```bash
cd /path/to/LiveTalking/testclient
./start-overlay.sh
```

这个 overlay 是测试客户端自带的一份，依赖和配置都在 `testclient/overlay` 内部管理。

overlay 不负责文字输入，也不直接连接 TTS。它只做显示：

```text
overlay
  -> POST http://127.0.0.1:8050/alpha/session
  -> WS ws://127.0.0.1:8050/alpha/ws
  -> 根据帧头 width/height 建立透明窗口画布
  -> 用 RGBA alpha 通道实现透明桌面数字人
```

`/alpha/ws` 每条 binary message：

```text
24 byte header + width * height * 4 RGBA bytes
```

header 字段：

```text
magic:   4 bytes, 固定 LTAF
version: 1 byte, 当前 1
format:  1 byte, 当前 1 表示 RGBA8
flags:   2 bytes, 当前 0
width:   uint32 little-endian
height:  uint32 little-endian
seq:     uint64 little-endian
```

overlay 显示尺寸来自 `width/height`，也就是当前 avatar 的 `full_imgs` 原始画布。控制条里的缩放只改变桌面显示比例，不裁剪、不改 LiveTalking 输出帧。

默认 `LIVETALKING_PLAY_AUDIO=0`，因为通常由 TTS 服务、浏览器或业务端播放声音。若 overlay 也播放 `/alpha/audio`，可能听到重复声音。

高分辨率 avatar 不建议让 overlay 永远拉满 raw RGBA。`testclient/.env` 默认：

```bash
LIVETALKING_VIDEO_MAX_HEIGHT=1080
LIVETALKING_VIDEO_FPS=15
```

这会让 overlay 连接 `/alpha/ws?max_height=1080&fps=15`。它只降低传输和显示压力，不会改 avatar 原图；如果仍卡，可以降到 `720/12`。如果必须无损显示原始帧，把这两个值设为 `0`。

### 5.1 Overlay 配置

| 变量 | 可选/范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `LIVETALKING_SERVER` | HTTP 地址 | `http://127.0.0.1:8050` | overlay 连接的 LiveTalking 服务。远程显示时改成 LiveTalking 机器 IP 或端口转发地址。 |
| `LIVETALKING_CLICK_THROUGH` | `1/0` | `1` | 视频窗口是否鼠标穿透。控制条窗口不穿透。 |
| `LIVETALKING_PLAY_AUDIO` | `1/0` | `0` | 是否由 overlay 播放 `/alpha/audio`。通常保持 `0`，避免和 TTS/业务端重复播放。 |
| `LIVETALKING_AUTO_SESSION` | `1/0` | `1` | 启动后自动调用 `/alpha/session`。 |
| `LIVETALKING_CLOSE_SESSION_ON_EXIT` | `1/0` | `0` | 退出 overlay 时是否关闭 LiveTalking session。多人测试时建议保持 `0`。 |
| `LIVETALKING_SCALE` | `0.25-3.0` | `1` | 初始显示倍率。控制条的 `- / +` 会运行时调整它。 |
| `LIVETALKING_RENDERER` | `webgl` / `2d` | `webgl` | 视频渲染方式。图形环境不稳定时可切 `2d`。 |
| `LIVETALKING_CONTROL_WIDTH` | 正整数 px | `340` | 控制条窗口宽度。 |
| `LIVETALKING_CONTROL_HEIGHT` | 正整数 px | `38` | 控制条窗口高度。 |
| `LIVETALKING_VIDEO_MAX_WIDTH` | 非负整数 px | `0` | overlay 请求 alpha stream 的最大宽度，`0` 表示不限制。 |
| `LIVETALKING_VIDEO_MAX_HEIGHT` | 非负整数 px | `1080` | overlay 请求 alpha stream 的最大高度，`0` 表示不限制。 |
| `LIVETALKING_VIDEO_FPS` | 非负数 | `15` | overlay 请求 alpha stream 的帧率，`0` 表示不限制。 |
| `LIVETALKING_X` / `LIVETALKING_Y` | 屏幕坐标 | 空 | 初始窗口位置。 |
| `LIVETALKING_EXTRA_PATH` | PATH 片段 | 空 | 需要指定额外 node/npm/electron 路径时使用。 |

## 6. 每台服务器该做什么

部署到多台机器时按角色拆：

| 角色 | 必须运行 | 必须开放 | 必须配置 |
| --- | --- | --- | --- |
| GPU 推理机 | LiveTalking `./entrypoint.sh` | `8050` HTTP/WebSocket | `AVATAR_ID`、`TTS_SERVER_URL`、`LIVETALKING_ALPHA_OUTPUT=1`。 |
| TTS 机器 | 真实 `robot-tts` 或 `testclient/backend ./start-tts.sh` | `8036` HTTP/WebSocket | provider、音色、API Key；保证输出 PCM16。 |
| 控制端 | 业务服务或 `testclient/web` | 能访问 8050 和 8036 | 决定走 `/alpha/speak` 还是 `/tts/task/start`。 |
| 显示端 | `testclient/overlay` 或自研显示程序 | 能访问 8050 | `LIVETALKING_SERVER=http://<LiveTalkingIP>:8050`。 |

网络方向要点：

- `/alpha/speak` 模式：控制端访问 LiveTalking；LiveTalking 主动访问 TTS。
- `/tts/task/start` 模式：控制端访问 TTS；TTS 主动访问 LiveTalking `/alpha/input/audio`。
- 视频显示：显示端主动连接 LiveTalking `/alpha/ws`。
- 音频播放：需要谁播放，谁连接 `/alpha/audio`；不要多个地方同时播放同一段声音。
