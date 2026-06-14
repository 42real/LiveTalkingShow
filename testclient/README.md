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
  提供 /alpha/speak、/alpha/input/audio、/alpha/webrtc/packed_offer

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

配置优先级：

```text
ENV > testclient/.env > code defaults
```

`testclient/` 是独立测试包，不读取 LiveTalking 主服务的 `.env`，也没有自己的 `config.yaml`。`testclient/.env.example` 只放常用测试覆盖项；显示帧率、编码格式、渲染器等排障参数由代码默认值提供，需要时可以临时用 ENV 覆盖。

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

| 变量 | 默认 | 取值/范围 | 说明 |
| --- | --- | --- | --- |
| `TEST_TTS_PROVIDER` | `edge` | `edge` / `bailian` | 测试 TTS provider；`edge` 走 EdgeTTS，`bailian` 走百炼 CosyVoice。 |
| `TTS_SERVICE_HOST` | `0.0.0.0` | IP/hostname | 测试 TTS 监听地址；`0.0.0.0` 允许远程访问。 |
| `TTS_SERVICE_PORT` | `8036` | `1-65535` | 测试 TTS 端口。 |
| `TTS_SERVER_URL` | `http://127.0.0.1:8036` | `http/https` URL | 脚本和本机联调用的 TTS 地址。 |
| `VITE_TTS_SERVER_URL` | `http://127.0.0.1:8036` | `http/https` URL | 浏览器页面访问 TTS 的地址。 |
| `TTS_STREAM_SAMPLE_RATE` | `16000` | int，建议 `16000` | 输出给 LiveTalking 的 PCM 采样率，单位 Hz。 |
| `TTS_STREAM_CHUNK_MS` | `40` | int，代码下限 `20`，常用 `20-80` | PCM chunk 时长；越小延迟越低但包更多，越大越稳但响应更慢。 |
| `ROBOT_TTS_EDGE_VOICES` | 常用中文/英文音色 | 逗号分隔音色列表 | EdgeTTS 音色列表；请求里的 `voice_id` 是从 0 开始的下标。 |
| `DASHSCOPE_API_KEY` | 空 | secret | 百炼 provider 必填；也兼容 `BAILIAN_API_KEY`。 |
| `BAILIAN_COSYVOICE_MODEL` | `cosyvoice-v3-flash` | 百炼模型名 | 百炼 CosyVoice 模型。 |
| `BAILIAN_VOICES` | 常用百炼音色 | 逗号分隔音色列表 | 百炼音色列表；请求里的 `voice_id` 是从 0 开始的下标。 |

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
| 视频预览 | 默认 `POST <LiveTalking>/alpha/webrtc/packed_offer`；`VITE_ALPHA_OUTPUT=ws` 时使用 `WS <LiveTalking>/alpha/ws` |
| 音频播放 | 默认 WebRTC audio track；`VITE_ALPHA_OUTPUT=ws` 时使用 `WS <LiveTalking>/alpha/audio` |
| 中断 | `POST <LiveTalking>/interrupt_talk` |

Web 常用配置：

| 变量 | 默认 | 取值/范围 | 说明 |
| --- | --- | --- | --- |
| `TEST_CLIENT_HOST` | `0.0.0.0` | IP/hostname | Web 测试页监听地址。 |
| `TEST_CLIENT_PORT` | `8070` | `1-65535` | Web 测试页端口。 |
| `VITE_LIVETALKING_URL` | `http://127.0.0.1:8050` | `http/https` URL | 浏览器访问 LiveTalking 的地址。 |
| `VITE_AVATAR_ID` | 空 | `data/avatars/` 下目录名或空 | 动作素材所属 avatar；为空时主测试页优先按当前 session 查询。 |
| `VITE_TTS_SERVER_URL` | `http://127.0.0.1:8036` | `http/https` URL | 浏览器访问 TTS 的地址。 |
| `VITE_ALPHA_INPUT_WS` | `ws://127.0.0.1:8050/alpha/input/audio` | `ws/wss` URL | TTS task 推流目标，必须指向 LiveTalking `/alpha/input/audio`。 |
| `VITE_ALPHA_OUTPUT` | `webrtc-packed` | `webrtc-packed` / `ws` | Web 视频输出链路；`webrtc-packed` 走 `/alpha/webrtc/packed_offer`，`ws` 走旧 `/alpha/ws` 调试预览。 |
| `VITE_ALPHA_PLAY_AUDIO` | `0` | bool：`0/1` | Web 是否播放 LiveTalking 输出音频；只开一个播放端，避免重复声音。 |

改 `TEST_CLIENT_*` 或 `VITE_*` 后要重启 `./start-web.sh`。如果直接进入 `testclient/web` 运行 `npm run start`，Vite 也会读取 `testclient/web/.env` 中的 `TEST_CLIENT_HOST`、`TEST_CLIENT_PORT`。

远程浏览器访问时，`VITE_LIVETALKING_URL`、`VITE_TTS_SERVER_URL`、`VITE_ALPHA_INPUT_WS` 都要写成浏览器所在机器能访问到的地址。比如通过 VS Code 端口转发到本机，就继续用 `127.0.0.1:8050`；如果直接访问服务器 IP，就写 `http://<服务器IP>:8050` 和 `ws://<服务器IP>:8050/alpha/input/audio`。

Web 高级排障参数按需临时设置即可：

| 变量 | 默认 | 取值/范围 | 说明 |
| --- | --- | --- | --- |
| `VITE_ALPHA_RENDERER` | `webgl` | `webgl` / `2d` | packed WebRTC 浏览器渲染器；`webgl` 性能更好，失败时页面会自动回退到 `2d`。 |
| `VITE_ALPHA_FORCE_OPAQUE` | `0` | bool：`0/1` | 设 `1` 时忽略 alpha，用于判断黑屏是否来自 alpha 解包。 |
| `VITE_ALPHA_VIDEO_MAX_HEIGHT` | `0` | int，`0` 或 `>0` | 最大逻辑高度；`0` 表示服务端不额外限制，远程卡顿时可试 `540` 或 `720`。 |
| `VITE_ALPHA_VIDEO_FPS` | `0` | float，`0` 或 `>0` | 目标预览帧率；`0` 表示使用 avatar 原始输出节奏。远程带宽不足时可试 `12-15`。 |
| `VITE_ALPHA_VIDEO_FORMAT` | `bgra` | `bgra` / `raw` / `jpeg` / `png` / `webp` | 仅 `VITE_ALPHA_OUTPUT=ws` 使用；`bgra` 避免服务端整帧转色。 |
| `VITE_ALPHA_VIDEO_QUALITY` | `80` | int，`1-100` | 仅 `jpeg/webp` 使用。 |

## 5. 启动 overlay

```bash
./start-overlay.sh
```

远程显示：

```bash
LIVETALKING_SERVER=http://<LiveTalking机器IP>:8050 \
LIVETALKING_OUTPUT=webrtc-packed \
./start-overlay.sh
```

overlay 默认本机链路：

```text
WS /alpha/ws
WS /alpha/audio
raw BGRA/RGBA video + PCM audio
```

本机 overlay 默认使用 `ws`，不经过 WebRTC/H264 编码，适合桌面助手叠加显示。远程显示时使用 packed WebRTC：

```text
POST /alpha/webrtc/packed_offer
WebRTC audio track
WebRTC packed video track，left=color，right=alpha
```

overlay 常用配置：

| 变量 | 默认 | 取值/范围 | 说明 |
| --- | --- | --- | --- |
| `LIVETALKING_SERVER` | `http://127.0.0.1:8050` | `http/https` URL | overlay 访问 LiveTalking 的地址。 |
| `LIVETALKING_CLICK_THROUGH` | `1` | bool：`0/1` | 视频窗口是否鼠标穿透；`1` 适合叠在 PPT 上，`0` 便于调试拖动。 |
| `LIVETALKING_OUTPUT` | `ws` | `ws` / `webrtc-packed` | overlay 视频输出链路；本机显示用 `ws` 更顺，远程显示用 `webrtc-packed`。 |
| `LIVETALKING_PLAY_AUDIO` | `0` | bool：`0/1` | 是否播放 LiveTalking 输出音频；通常保持关闭，避免重复声音。 |
| `LIVETALKING_SCALE` | `1` | float，`>0`，常用 `0.5-2.0` | 初始显示倍率，只影响窗口显示大小，不改变 avatar 推理尺寸。 |

overlay 高级排障参数：

| 变量 | 默认 | 取值/范围 | 说明 |
| --- | --- | --- | --- |
| `LIVETALKING_RENDERER` | `webgl` | `webgl` | packed alpha 渲染器。 |
| `LIVETALKING_VIDEO_MAX_HEIGHT` | `0` | int，`0` 或 `>0` | packed WebRTC 输出最大逻辑高度；`0` 表示不限制。 |
| `LIVETALKING_VIDEO_FPS` | `0` | float，`0` 或 `>0` | packed WebRTC 目标帧率；`0` 表示使用服务端默认。 |
| `LIVETALKING_VIDEO_FORMAT` | `bgra` | `bgra` / `raw` / `jpeg` / `png` / `webp` | 仅 `LIVETALKING_OUTPUT=ws` 使用；本机 overlay 推荐 `bgra`。 |

## 6. 多机配置

| 角色 | 运行内容 | 关键地址 |
| --- | --- | --- |
| GPU 推理机 | LiveTalking `./entrypoint.sh` | 开放 `8050`。 |
| TTS 机器 | 真实 robot-tts 或 `./start-tts.sh` | 开放 `8036`。 |
| 控制端 | 业务服务或 `testclient/web` | 能访问 LiveTalking 和 TTS。 |
| 显示端 | `testclient/overlay` 或自研显示程序 | 本机访问 `/alpha/ws`；远程访问 `/alpha/webrtc/packed_offer`。 |

地址规则：

- `/alpha/speak` 模式：控制端访问 LiveTalking，LiveTalking 访问 TTS。
- `/tts/task/start` 模式：控制端访问 TTS，TTS 访问 LiveTalking `/alpha/input/audio`。
- 视频显示：本机 overlay 访问 `/alpha/ws`；远程显示访问 `/alpha/webrtc/packed_offer`，收到单个 packed video track 后在本地 shader 解包透明度。
- 声音播放：只选择一个组件播放，避免重复声音。
