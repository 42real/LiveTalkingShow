# LiveTalking Test Client

`testclient/` 是独立测试包，用来模拟生产中的 TTS、控制端和显示端。它不参与 LiveTalking 主服务配置。

组成：

| 目录 | 作用 |
| --- | --- |
| `backend/` | `robottts` 兼容 TTS 测试服务，支持 EdgeTTS 和百炼 provider。 |
| `web/` | 浏览器测试页，可发文字、启动 TTS task、查看 alpha 视频和音频。 |
| `overlay/` | Electron 透明置顶窗口，用来模拟 PPT/桌面数字人显示。 |

接口细节见 [../docs/API-PROTOCOL.md](../docs/API-PROTOCOL.md)。

## 1. 运行关系

```text
testclient/backend，默认 8036
  提供 /health、/tts/ws、/tts/task/start

LiveTalking，默认 8050
  使用 TTS_SERVER_URL=http://127.0.0.1:8036
  提供 /alpha/speak、/alpha/input/audio、/alpha/ws

testclient/web，默认 8070
  浏览器控制和预览

testclient/overlay
  本机透明置顶显示窗口
```

## 2. 准备

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
```

`start-tts.sh`、`start-web.sh`、`start-overlay.sh` 会读取 `testclient/.env`。

## 3. 启动 TTS 测试后端

EdgeTTS：

```bash
./start-tts.sh
```

百炼：

```bash
TEST_TTS_PROVIDER=bailian DASHSCOPE_API_KEY=你的Key ./start-tts.sh
```

检查：

```bash
curl http://127.0.0.1:8036/health
curl http://127.0.0.1:8036/tts/voices
```

常用 TTS 配置：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `TEST_TTS_PROVIDER` | `edge` | `edge` / `bailian`。 |
| `TTS_SERVICE_HOST` | `0.0.0.0` | 测试 TTS 监听地址。 |
| `TTS_SERVICE_PORT` | `8036` | 测试 TTS 端口。 |
| `TTS_STREAM_SAMPLE_RATE` | `16000` | 输出 PCM 采样率。 |
| `TTS_STREAM_CHUNK_MS` | `40` | PCM chunk 时长，越小延迟越低。 |
| `ROBOT_TTS_EDGE_VOICES` | 常用中文/英文音色 | EdgeTTS 音色列表，`voice_id` 按顺序编号。 |
| `DASHSCOPE_API_KEY` | 空 | 百炼 provider 必填。 |
| `BAILIAN_COSYVOICE_MODEL` | `cosyvoice-v3-flash` | 百炼模型名。 |
| `BAILIAN_VOICES` | 常用百炼音色 | 百炼音色列表，`voice_id` 按顺序编号。 |

## 4. 启动 Web 测试页

```bash
./start-web.sh
```

访问：

```text
http://127.0.0.1:8070
```

Web 页面按钮对应：

| 页面动作 | 接口 |
| --- | --- |
| 健康检查 | `GET <TTS>/health`、`GET <LiveTalking>/api/admin/config` |
| 音色列表 | `GET <TTS>/tts/voices` |
| 创建 session | `POST <LiveTalking>/alpha/session` |
| 文本朗读 | `POST <LiveTalking>/alpha/speak` |
| TTS task | `POST <TTS>/tts/task/start`，其中 `target_hardware` 指向 `/alpha/input/audio` |
| 视频预览 | `WS <LiveTalking>/alpha/ws` |
| 音频播放 | `WS <LiveTalking>/alpha/audio` |
| 中断 | `POST <LiveTalking>/interrupt_talk` |

Web 常用配置：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `TEST_CLIENT_PORT` | `8070` | Web 端口。 |
| `VITE_LIVETALKING_URL` | `http://127.0.0.1:8050` | 浏览器访问 LiveTalking 的地址。 |
| `VITE_TTS_SERVER_URL` | `http://127.0.0.1:8036` | 浏览器访问 TTS 的地址。 |
| `VITE_ALPHA_INPUT_WS` | `ws://127.0.0.1:8050/alpha/input/audio` | TTS task 推流目标。 |
| `VITE_ALPHA_VIDEO_MAX_HEIGHT` | `720` | Web 预览最大高度。 |
| `VITE_ALPHA_VIDEO_FPS` | `25` | Web 预览帧率。 |
| `VITE_ALPHA_VIDEO_FORMAT` | `jpeg` | Web 预览编码。 |
| `VITE_ALPHA_VIDEO_QUALITY` | `80` | JPEG/WebP 质量。 |

改 `VITE_*` 后要重启 `./start-web.sh`。

## 5. 启动 overlay

```bash
./start-overlay.sh
```

远程显示：

```bash
LIVETALKING_SERVER=http://<LiveTalking机器IP>:8050 ./start-overlay.sh
```

overlay 链路：

```text
POST /alpha/session
WS   /alpha/ws
可选 WS /alpha/audio
```

overlay 常用配置：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LIVETALKING_SERVER` | `http://127.0.0.1:8050` | LiveTalking 地址。 |
| `LIVETALKING_CLICK_THROUGH` | `1` | 视频窗口鼠标穿透。 |
| `LIVETALKING_PLAY_AUDIO` | `0` | 是否播放 `/alpha/audio`。通常保持关闭。 |
| `LIVETALKING_VIDEO_FORMAT` | `raw` | 透明显示推荐 `raw`。 |
| `LIVETALKING_VIDEO_MAX_HEIGHT` | `1080` | 拉流最大高度。 |
| `LIVETALKING_VIDEO_FPS` | `15` | 拉流帧率。 |
| `LIVETALKING_SCALE` | `1` | 初始显示倍率。 |

## 6. 多机配置

| 角色 | 运行内容 | 关键地址 |
| --- | --- | --- |
| GPU 推理机 | LiveTalking `./entrypoint.sh` | 开放 `8050`。 |
| TTS 机器 | 真实 robot-tts 或 `./start-tts.sh` | 开放 `8036`。 |
| 控制端 | 业务服务或 `testclient/web` | 能访问 LiveTalking 和 TTS。 |
| 显示端 | `testclient/overlay` 或自研显示程序 | 能访问 LiveTalking `/alpha/ws`。 |

地址规则：

- `/alpha/speak` 模式：控制端访问 LiveTalking，LiveTalking 访问 TTS。
- `/tts/task/start` 模式：控制端访问 TTS，TTS 访问 LiveTalking `/alpha/input/audio`。
- 视频显示：显示端访问 LiveTalking `/alpha/ws`。
- 声音播放：只选择一个组件播放，避免重复声音。
