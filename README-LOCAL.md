# LiveTalking 本地交接说明

这份文档说明当前仓库里的本地改造、运行方式、可调参数、服务协议和迁移边界。命令默认从仓库根目录执行。

本地交接以这份文档为准：当前部署规范使用 `uv`，不使用 conda。上游 `README.md` 里的 conda 安装命令只作为官方历史说明，不作为本地运行方式。

克隆后先跑最小闭环：

```bash
cd /path/to/LiveTalking
uv sync --python 3.10 --inexact
cp .env.example .env
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
```

这里使用 `--inexact` 是为了保留本机已有的 CUDA、MuseTalk/MMPose 等额外运行依赖；仓库锁文件负责同步主链路依赖。`download-models.sh wav2lip-demo` 会准备默认启动必需的 `models/wav2lip.pth` 和 `data/avatars/wav2lip_avatar_female_model/`。

启动方式参考 `robot-asr`：`entrypoint.sh` 只负责进入仓库并启动服务，配置由 Python 侧读取，不需要手动 `source .env`。运行只依赖接口地址和运行参数，不需要配置项目 home 目录。

配置优先级：

```text
ENV > .env > config.yaml
```

`config.yaml` 使用和 `robot-asr` 类似的分组结构，例如 `server.port`、`avatar.avatar_id`、`tts.server_url`。`.env` 使用环境变量名，例如 `LIVETALKING_PORT=8050`、`AVATAR_ID=wav2lip_avatar_female_model`。

也就是说，临时覆盖某项配置时直接在命令前加环境变量即可。CLI 参数只保留给本地临时调试，不作为部署配置层：

```bash
LIVETALKING_PORT=8051 AVATAR_ID=my_avatar ./entrypoint.sh
```

配置文件分工：

| 文件 | 谁读取 | 用途 | 是否提交 |
| --- | --- | --- | --- |
| `config.yaml` | LiveTalking 主服务 | 默认部署配置，适合写团队共享默认值。 | 提交。 |
| `.env.example` | 人看，复制成 `.env` | LiveTalking 主服务的环境变量模板。 | 提交。 |
| `.env` | LiveTalking 主服务 | 当前机器的真实配置，优先级高于 `config.yaml`。 | 不提交。 |
| `testclient/.env.example` | 人看，复制成 `testclient/.env` | 测试 TTS、Web、overlay 的统一模板。 | 提交。 |
| `testclient/.env` | `testclient/start-*.sh` | 当前机器的测试客户端配置。 | 不提交。 |

LiveTalking 主服务最常用配置：

| 变量 | config.yaml 路径 | 默认 | 谁使用 | 说明 |
| --- | --- | --- | --- | --- |
| `HF_ENDPOINT` | `runtime.hf_endpoint` | `https://hf-mirror.com` | 下载脚本、运行时依赖下载 | Hugging Face 镜像。能直连官方时可不设；国内网络建议保留。 |
| `LIVETALKING_HOST` | `server.host` | `0.0.0.0` | LiveTalking | 服务监听地址。部署给其他机器访问时保持 `0.0.0.0`。 |
| `LIVETALKING_PORT` | `server.port` | `8050` | LiveTalking | HTTP/WebSocket 端口。改它后，所有客户端里的 LiveTalking URL 都要同步。 |
| `LIVETALKING_MODEL` | `avatar.model` | `wav2lip` | LiveTalking | avatar 推理模型：`wav2lip` / `musetalk` / `ultralight`。当前交接主链路用 `wav2lip`。 |
| `AVATAR_ID` | `avatar.avatar_id` | `wav2lip_avatar_female_model` | LiveTalking | `data/avatars/<avatar_id>` 目录名。目录本身不进 Git，需要单独下载或拷贝。 |
| `LIVETALKING_BATCH_SIZE` | `avatar.batch_size` | `4` | LiveTalking | 推理批大小。低延迟建议 `2-4`；吞吐优先可调大；显存不足调小。 |
| `LIVETALKING_FPS` | `avatar.fps` | `25` | LiveTalking | 内部视频节奏。当前按 25fps 设计，通常不要改。 |
| `LIVETALKING_TTS` | `tts.provider` | `robottts` | LiveTalking | TTS 插件。交接方案统一用 `robottts`。 |
| `TTS_SERVER_URL` | `tts.server_url` | `http://127.0.0.1:8036` | LiveTalking | robottts 兼容 TTS 服务地址。LiveTalking 会连接它的 `/tts/ws`。 |
| `ROBOTTTS_MODE` | `tts.robottts_mode` | `instruct2` | LiveTalking -> TTS | 透传给 TTS 服务的模式。测试后端支持 `instruct2` / `zero-shot`。 |
| `LIVETALKING_TRANSPORT` | `output.transport` | `webrtc` | LiveTalking | 输出模块名。必须是 `webrtc` / `rtmp` / `rtcpush` / `virtualcam`；`alpha` 不是合法 transport。 |
| `LIVETALKING_ALPHA_OUTPUT` | `output.alpha_output` | `1` | LiveTalking | 是否发布 `/alpha/ws`、`/alpha/audio`、`/alpha/input/audio`。桌面助手必须开启。 |
| `LIVETALKING_OUTPUT_METRICS_INTERVAL` | `output.metrics_interval` | `5` | LiveTalking | 统一输出链路性能日志间隔，单位秒；设为 `0` 可关闭。日志包含输出 fps、贴图耗时、sink 耗时、alpha 转换/打包耗时、队列情况。 |

端口联动规则：

| 如果改了 | 同步修改 |
| --- | --- |
| `LIVETALKING_PORT` | `LIVETALKING_URL`、`LIVETALKING_WS_URL`、`testclient/.env` 的 `LIVETALKING_URL`、`LIVETALKING_WS_URL`、`LIVETALKING_SERVER`、`VITE_LIVETALKING_URL`、`VITE_ALPHA_INPUT_WS`。 |
| `TTS_SERVICE_PORT` 或真实 TTS 端口 | LiveTalking `.env` 的 `TTS_SERVER_URL`、`testclient/.env` 的 `TTS_SERVER_URL`、`VITE_TTS_SERVER_URL`。 |
| 远程机器访问地址 | 不要继续用 `127.0.0.1`；改成服务所在机器 IP，或确认 VS Code/SSH 端口转发已经把对应端口映射到本机。 |

`LIVETALKING_URL` 和 `LIVETALKING_WS_URL` 主要给脚本、页面和人查看使用；LiveTalking 监听实际以 `LIVETALKING_HOST` / `LIVETALKING_PORT` 为准。浏览器里的 `VITE_*` 变量只在 `testclient/start-web.sh` 启动时注入，改完 `.env` 后必须重启 Web 测试页。

所有 `data/avatars/*` 都被忽略，不进 Git。默认示例 avatar 由 `./scripts/download-models.sh wav2lip-demo` 下载；部署自己的数字人时，把 avatar 目录放到 `data/avatars/<avatar_id>/`，再设置 `AVATAR_ID=<avatar_id>`。

## 0. 服务边界和链路

完整方案不是一个单进程，而是三个角色通过 HTTP/WebSocket 连接：

```text
服务 A：LiveTalking 主服务，默认 8050
  - 加载 avatar 和 wav2lip/musetalk/ultralight 模型
  - 接收文本或外部 PCM 音频
  - 做口型推理和画面合成
  - 输出 WebRTC 页面、alpha RGBA 视频流、alpha PCM 音频流

服务 B：robottts 兼容 TTS 服务，默认 8036
  - 生产环境接真实 robot-tts 或同协议服务
  - 测试环境可用 testclient/backend 的 edge/bailian provider
  - 输入文本，输出 16kHz 单声道 PCM16 流

服务 C：显示/测试客户端，默认 Web 8070，overlay 本机 Electron
  - testclient/web 用浏览器测试 API、视频、音频
  - testclient/overlay 用透明置顶窗口显示 /alpha/ws 视频
  - 业务系统也可以自己实现这个角色
```

运行顺序：

```text
1. 准备 LiveTalking uv 环境和模型资产
2. 启动 robottts 兼容 TTS 服务
3. 启动 LiveTalking 主服务，并让 TTS_SERVER_URL 指向 TTS 服务
4. 启动 testclient/web 或 overlay，连接 LiveTalking 的 8050
5. 通过 /alpha/speak 或 /alpha/input/audio 触发数字人说话
```

两种输入链路的区别：

| 链路 | 谁合成 TTS | 适合场景 | 数据流 |
| --- | --- | --- | --- |
| `/alpha/speak` | LiveTalking 内部的 `robottts` 插件主动调用 TTS 服务 | 最简单的文本驱动数字人 | 控制端把文本发给 LiveTalking，LiveTalking 再连 TTS `/tts/ws` 拉 PCM。 |
| `/tts/task/start -> /alpha/input/audio` | 外部 TTS 服务主动生成并推送音频 | 现有 robot-tts、ASR/LLM/TTS 编排系统已经掌握任务流 | 控制端把任务发给 TTS，TTS 通过 WebSocket 把 PCM 推给 LiveTalking。 |

视频输出链路独立于文本输入链路：

```text
LiveTalking 推理线程
  -> streamout/webrtc.py 发布帧
  -> server/alpha_stream.py 打包 RGBA
  -> ws://<host>:8050/alpha/ws
  -> testclient/web canvas 或 testclient/overlay Electron 窗口显示
```

如果你要接入自己的系统，最少要实现：

- 一个 `robottts` 兼容 TTS 服务，或直接把 PCM 推到 LiveTalking `/alpha/input/audio`。
- 一个显示端，消费 LiveTalking `/alpha/ws` 的 RGBA 帧；需要声音时再消费 `/alpha/audio`。

## 1. 当前方案

当前仓库基于官方 LiveTalking 增加了两条能力：

- `robottts`：LiveTalking 通过统一 HTTP/WebSocket 接口接外部 TTS。生产接真实 `robot-tts`，本地测试可用 `testclient/backend` 的 EdgeTTS 或百炼 provider。
- `alpha_output`：LiveTalking 输出 raw RGBA 视频帧，给 Electron 透明置顶窗口显示数字人。

主链路：

```text
业务端 / testclient / FastAPI docs
  -> LiveTalking /alpha/speak 或 /alpha/input/audio
  -> robottts-compatible TTS service
  -> LiveTalking wav2lip 推理
  -> /alpha/ws raw RGBA 视频
  -> testclient/overlay 透明置顶窗口
```

当前跑通链路方案：

- avatar 模型：`wav2lip`
- TTS：`robottts`
- 默认显示输出：alpha stream，也就是 `LIVETALKING_ALPHA_OUTPUT=1` + `/alpha/ws`。Web 测试页和 overlay 默认都连接 alpha stream。
- 兼容输出：官方 WebRTC 页面仍保留，但本地交接和桌面助手不以 WebRTC 作为默认显示链路。
- 端口：TTS `8036`，LiveTalking `8050`，Web 测试页 `8070`

功能和必需资产：

| 功能 | 必需模型/资产 | 下载或准备方式 |
| --- | --- | --- |
| wav2lip 数字人运行 | `models/wav2lip.pth`、`data/avatars/<avatar_id>/` | `./scripts/download-models.sh wav2lip-demo` 准备默认示例；自定义 avatar 见第 6 节。 |
| alpha 透明帧输出 | 同 wav2lip 运行资产，且开启 `LIVETALKING_ALPHA_OUTPUT=1` | `.env.example` 和 `config.yaml` 默认已开启；也可用 `LIVETALKING_ALPHA_OUTPUT=1 ./entrypoint.sh`。 |
| 测试 TTS | 无本地模型；EdgeTTS 需要能访问微软在线服务，百炼需要 API Key | 第 2.2 节启动 `testclient/backend`。 |
| Web 测试页 | Node 依赖 | `./start-web.sh` 首次会自动 `npm install`。 |
| 桌面 overlay | Electron 依赖，且本机要有图形桌面环境 | `./start-overlay.sh` 首次会自动安装依赖；远程机器显示见第 2.5 节。 |
| wav2lip avatar 制作 | `models/wav2lip.pth`；人脸检测模型 `s3fd.pth` 可自动下载，也可提前下载 | 分别执行 `./scripts/download-models.sh wav2lip` 和 `./scripts/download-models.sh s3fd`，或执行 `./scripts/download-models.sh all`。 |
| MuseTalk 运行/制作 | MuseTalk、Whisper、VAE、DWPose、FaceParsing 模型，另需 MMPose/MMCV 环境 | `./scripts/download-models.sh musetalk` 下载模型；依赖安装见第 6.2 节。 |
| Ultralight 运行/制作 | 自己训练或拿到的 `ultralight.pth` | 当前仓库不提供通用 checkpoint，需要按第 6.3 节放入 avatar 目录。 |

## 2. 快速启动

### 2.1 准备模型和默认 avatar

默认运行 `wav2lip`。克隆仓库后必须先准备：

```text
models/wav2lip.pth
data/avatars/wav2lip_avatar_female_model/
```

一条命令下载默认示例：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
```

脚本支持的模式：

| 命令 | 效果 |
| --- | --- |
| `./scripts/download-models.sh wav2lip-demo` | 下载 `models/wav2lip.pth` 和默认示例 avatar。首次跑通推荐用这个。 |
| `./scripts/download-models.sh wav2lip` | 只下载 `models/wav2lip.pth`。适合已有 avatar 的部署。 |
| `./scripts/download-models.sh s3fd` | 下载 wav2lip 制作 avatar 时使用的人脸检测模型。 |
| `./scripts/download-models.sh musetalk` | 下载 MuseTalk 运行/制作所需的主要模型资产。体积较大。 |
| `./scripts/download-models.sh all` | 下载 wav2lip demo、s3fd 和 MuseTalk 资产。 |

默认下载源：

| 资产 | 默认来源 | 本地位置 |
| --- | --- | --- |
| Wav2Lip checkpoint | `shibing624/ai-avatar-wav2lip` 的 `wav2lip.pth` | `models/wav2lip.pth` |
| Wav2Lip 示例 avatar | `shibing624/ai-avatar-wav2lip` 的 `wav2lip_avatar_female_model.zip` | `data/avatars/wav2lip_avatar_female_model/` |
| S3FD 人脸检测 | `https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth` | `avatars/wav2lip/face_detection/detection/sfd/s3fd.pth` |
| MuseTalk V15 | `TMElyralab/MuseTalk` | `models/musetalkV15/` |
| DWPose/FaceParsing | `camenduru/MuseTalk` | `models/dwpose/`、`models/face-parse-bisent/` |
| Whisper tiny | `openai/whisper-tiny` | `models/whisper/` |
| SD VAE | `stabilityai/sd-vae-ft-mse` | `models/sd-vae/` |

可覆盖的下载变量：

```bash
HF_ENDPOINT=https://hf-mirror.com
LIVETALKING_WAV2LIP_REPO=shibing624/ai-avatar-wav2lip
LIVETALKING_WAV2LIP_AVATAR_ZIP=wav2lip_avatar_female_model.zip
LIVETALKING_WAV2LIP_AVATAR_ID=wav2lip_avatar_female_model
LIVETALKING_MODEL_OVERWRITE=1
```

如果已经有自己的模型和 avatar，可以不运行下载脚本，手动放入：

```text
models/wav2lip.pth
data/avatars/<avatar_id>/
```

然后修改 `.env`：

```bash
AVATAR_ID=<avatar_id>
```

### 2.2 启动 TTS 服务

生产环境：只要有一个服务实现第 4 节的 `robottts` 协议即可，LiveTalking 只关心 `TTS_SERVER_URL`。

本地 EdgeTTS 测试：

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
TEST_TTS_PROVIDER=edge ./start-tts.sh
```

本地百炼测试：

```bash
cd /path/to/LiveTalking/testclient
cp .env.example .env
TEST_TTS_PROVIDER=bailian DASHSCOPE_API_KEY=你的百炼APIKey ./start-tts.sh
```

检查：

```bash
curl http://127.0.0.1:8036/health
curl http://127.0.0.1:8036/tts/voices
```

### 2.3 启动 LiveTalking

```bash
cd /path/to/LiveTalking
./entrypoint.sh
```

默认 `.env.example` 和 `config.yaml` 已经启用 alpha 输出：

```bash
LIVETALKING_ALPHA_OUTPUT=1
```

也可以临时覆盖：

```bash
LIVETALKING_ALPHA_OUTPUT=1 ./entrypoint.sh
```

如果绕过配置直接用 CLI，显式加 `--alpha_output`：

```bash
uv run --no-sync --python .venv/bin/python python app.py --alpha_output
```

开启后会提供：

```text
ws://127.0.0.1:8050/alpha/ws
ws://127.0.0.1:8050/alpha/audio
ws://127.0.0.1:8050/alpha/input/audio
```

其中 `/alpha/ws` 是 raw RGBA 视频帧，overlay 和测试 Web 都依赖它。

启动后常用地址：

- `http://127.0.0.1:8050/index.html`
- `http://127.0.0.1:8070`，testclient Web，默认自动连接 alpha stream。
- `http://127.0.0.1:8050/admin.html`
- `http://127.0.0.1:8050/avatar.html`
- `http://127.0.0.1:8050/webrtcapi.html`，官方兼容 WebRTC 测试页，不是本地默认显示方式。

如果绕过脚本直接运行 `python app.py`，不要在命令里写未加载的 `$AVATAR_ID`、`$TTS_SERVER_URL`、`$LIVETALKING_PORT`。直接用 `uv run --python .venv/bin/python python app.py` 时，程序会自己读取 `.env` 和 `config.yaml`；临时覆盖参数用 `LIVETALKING_PORT=8051 AVATAR_ID=my_avatar ./entrypoint.sh` 这种 ENV 前缀。

### 2.4 启动测试页面

```bash
cd /path/to/LiveTalking/testclient
./start-web.sh
```

默认访问：

```text
http://127.0.0.1:8070
```

测试页面可验证：

- 打开页面后默认自动创建 alpha session，并连接 `/alpha/ws?max_height=720&fps=8`。
- TTS `/health` 和 `/tts/voices`
- `/alpha/speak` 文本驱动
- `/tts/task/start -> /alpha/input/audio` 音频流驱动
- `/alpha/ws` 视频帧尺寸、帧号、fps 和透明画面

### 2.5 启动桌面 overlay

```bash
cd /path/to/LiveTalking/testclient
./start-overlay.sh
```

远程显示时只改 LiveTalking 地址：

```bash
cd /path/to/LiveTalking/testclient
LIVETALKING_SERVER=http://<LiveTalking服务器IP>:8050 ./start-overlay.sh
```

## 3. LiveTalking 启动参数

| 参数 | 可选/范围 | 默认 | 说明和调参建议 |
| --- | --- | --- | --- |
| `--model` | `wav2lip` / `musetalk` / `ultralight` | `wav2lip` | avatar 推理模型。当前稳定交接优先 `wav2lip`。 |
| `--avatar_id` | `data/avatars/<id>` 目录名 | `wav2lip_avatar_female_model` | 要加载的数字人。默认示例由 `./scripts/download-models.sh wav2lip-demo` 下载，素材不进 Git。 |
| `--batch_size` | 正整数 | `16` | 推理批大小。吞吐越高延迟越大；桌面助手建议 `4`，显存不足可降到 `1-2`。 |
| `--tts` | `robottts`、`edgetts`、`gpt-sovits`、`cosyvoice`、`fishtts`、`tencent`、`doubao`、`indextts2`、`azuretts`、`qwentts` | `robottts` | TTS 插件。交接方案统一用 `robottts`。 |
| `--TTS_SERVER` | `http(s)://host:port` 或 `ws(s)://.../tts/ws` | `http://127.0.0.1:8036` | `robottts` 服务地址。插件会自动把 HTTP 地址转换到 `/tts/ws`。 |
| `--robottts_mode` | `instruct2` / `zero-shot` | `instruct2` | 透传给 TTS 后端的模式。是否生效取决于后端。 |
| `--robottts_connect_timeout` | 秒，建议 `3-30` | `10` | 连接 TTS 超时。远程服务慢可调大。 |
| `--robottts_receive_timeout` | 秒，建议 `0.5-5` | `1` | WebSocket 收包等待。过小可能误判超时；过大中断响应会慢。 |
| `--transport` | `webrtc` / `rtmp` / `rtcpush` / `virtualcam` | `webrtc` | 输出方式。浏览器和 overlay 推荐 `webrtc`。 |
| `--listenhost` | IP/主机名 | `0.0.0.0` | HTTP/WebSocket 监听地址。通常保持默认。 |
| `--listenport` | `1-65535` | `8010` | LiveTalking HTTP/WebSocket 端口。当前建议 `8050` 或更高。 |
| `--alpha_output` | 开关 | `.env.example` 默认开启 | 打开 raw RGBA 透明帧流 `/alpha/ws`。桌面透明 overlay 必须开启；不用透明输出时可设 `LIVETALKING_ALPHA_OUTPUT=0`。 |
| `--customvideo_config` | JSON 文件路径 | 空 | 自定义动作/状态视频配置，用于空闲、说话等状态切换。 |
| `--fps` | 必须 `25` | `25` | 当前音视频节奏按 25fps 设计，不建议修改。 |

## 4. API 和模块传输协议

LiveTalking、TTS 和显示端只通过接口通信，不依赖彼此的代码目录或存储路径。生产环境把接口地址配对即可。

### 4.1 robottts 兼容 TTS 服务

LiveTalking 的 `tts/robottts.py` 只依赖这些接口。真实 `robot-tts` 和 `testclient/backend` 都应保持同一协议。

| 方法 | 路径 | 方向 | 作用 |
| --- | --- | --- | --- |
| `GET` | `/health` | 控制端 -> TTS | 健康检查，同时返回音频格式等元信息。 |
| `GET` | `/tts/voices` | 控制端/LiveTalking -> TTS | 查询音色列表，`voice_id` 从这里选。 |
| `POST` | `/tts` | 控制端 -> TTS | 一次性合成 wav 文件，主要用于单独测试。 |
| `WS` | `/tts/ws` | LiveTalking -> TTS | LiveTalking 内部 `robottts` 插件使用的流式合成接口。 |
| `POST` | `/tts/task/create` | 控制端 -> TTS | 创建外部推流任务，可选。 |
| `POST` | `/tts/task/submit` | 控制端 -> TTS | 提交任务文本，可选。 |
| `POST` | `/tts/task/start` | 控制端 -> TTS | 创建并提交任务，测试客户端常用。 |
| `POST` | `/tts/task/cancel` | 控制端 -> TTS | 取消任务。 |
| `GET` | `/tts/task/status?task_id=...` | 控制端 -> TTS | 查询任务状态。 |

推荐音频格式：

```text
16kHz / mono / signed 16-bit PCM
```

`GET /health` 典型返回：

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

`GET /tts/voices` 典型返回：

```json
{
  "voices": [
    {"id": 0, "name": "zh-CN-XiaoxiaoNeural", "description": "zh-CN-XiaoxiaoNeural"}
  ]
}
```

`POST /tts` 典型请求：

```json
{
  "text": "你好，我是数字人。",
  "voice_id": 0,
  "mode": "instruct2",
  "prompts": "请自然清晰地朗读。",
  "output_path": "/tmp/robottts-output.wav"
}
```

`WS /tts/ws` 消息流程：

```text
client -> {"action":"start","voice_id":0,"mode":"instruct2","prompts":"..."}
server -> {"action":"started"}
client -> {"action":"text","text":"要朗读的文本"}
server -> binary PCM chunks
server -> {"action":"result","type":"final","meta":{...}}
client -> {"action":"end"}
```

其中 binary PCM chunks 是原始 PCM16 字节流，不是 wav 文件，不带 wav header。

### 4.2 LiveTalking 主服务 API

LiveTalking 默认监听：

```text
http://127.0.0.1:8050
```

主要接口：

| 方法 | 路径 | 方向 | 作用 |
| --- | --- | --- | --- |
| `POST` | `/alpha/session` | 显示端/控制端 -> LiveTalking | 创建或复用桌面 alpha session。overlay 启动时会调用。 |
| `POST` | `/alpha/speak` | 控制端 -> LiveTalking | 输入文本，由 LiveTalking 调 TTS，再驱动 avatar。 |
| `WS` | `/alpha/input/audio` | 外部 TTS -> LiveTalking | 输入外部 PCM 音频流，绕过 LiveTalking 内部 TTS。 |
| `WS` | `/alpha/ws` | 显示端 <- LiveTalking | 输出 raw RGBA 视频帧。 |
| `WS` | `/alpha/audio` | 显示端 <- LiveTalking | 输出 LiveTalking 侧音频 PCM16。 |
| `POST` | `/alpha/close` | 显示端/控制端 -> LiveTalking | 关闭 alpha session。 |
| `POST` | `/interrupt_talk` | 控制端 -> LiveTalking | 打断当前朗读。 |
| `POST` | `/is_speaking` | 控制端 -> LiveTalking | 查询 session 是否正在说话。 |
| `GET` | `/api/admin/config` | 控制端 -> LiveTalking | 查看当前配置。 |
| `GET` | `/api/admin/sessions` | 控制端 -> LiveTalking | 查看当前 session。 |

`POST /alpha/session` 请求：

```json
{
  "reuse": true,
  "sessionid": ""
}
```

返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {"sessionid": "0"}
}
```

可以在请求体里带 `avatar_id`、`batch_size`、`tts`、`TTS_SERVER` 等 session 参数，只有 avatar 构造需要的字段会被使用。大多数场景保持空请求即可，由 `.env` 和 `config.yaml` 控制。

### 4.3 文本驱动数字人

推荐通过 LiveTalking 统一入口：

```bash
curl -X POST http://127.0.0.1:8050/alpha/speak \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "你好，我是桌面数字人。",
    "type": "echo",
    "interrupt": true,
    "tts": {
      "voice_id": 0,
      "mode": "instruct2",
      "prompts": "请自然清晰地朗读。"
    }
  }'
```

`tts` 字段说明：

| 字段 | 类型/范围 | 说明 |
| --- | --- | --- |
| `voice_id` | 非负整数 | 后端音色编号。可通过 `/tts/voices` 查询。 |
| `mode` | `instruct2` / `zero-shot` | TTS 模式。EdgeTTS 测试服务会接受但不做强语义区分；百炼会映射到在线服务参数。 |
| `prompts` | 字符串 | 指令或提示词，例如语气、停顿、风格。 |
| `ref_file` | 字符串/整数 | 兼容 LiveTalking 旧字段，会映射到 `voice_id`。 |
| `ref_text` | 字符串 | 兼容旧字段，会映射到 `prompts`。 |

这条链路内部实际发生：

```text
控制端 POST /alpha/speak
  -> LiveTalking 创建/复用 alpha session
  -> avatar_session.put_msg_txt(text, {"tts": ...})
  -> tts/robottts.py 连接 ws://<TTS_SERVER>/tts/ws
  -> TTS 返回 PCM16 binary chunks
  -> LiveTalking 转 float32 audio frame
  -> wav2lip ASR/audio feature
  -> avatar 推理生成视频帧
  -> /alpha/ws 输出 RGBA
```

### 4.4 外部音频流驱动数字人

如果指令和音频来自其他组件，用 TTS task API 直接推音频到 LiveTalking：

```bash
curl -X POST http://127.0.0.1:8036/tts/task/start \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "demo-001",
    "text": "这段音频由外部 TTS 生成，再推给 LiveTalking。",
    "voice_id": 0,
    "mode": "instruct2",
    "prompts": "请自然清晰地朗读。",
    "target_hardware": "ws://127.0.0.1:8050/alpha/input/audio"
  }'
```

`target_hardware` 要指向 LiveTalking：

```text
ws://<LiveTalking服务器IP>:<LiveTalking端口>/alpha/input/audio
```

这条链路内部实际发生：

```text
控制端 POST /tts/task/start 到 TTS 服务
  -> TTS 服务连接 ws://<LiveTalking>/alpha/input/audio
  -> TTS 先发 start JSON，LiveTalking 回 started
  -> TTS 持续发 PCM16 binary chunks
  -> TTS 发 end JSON
  -> LiveTalking 把 PCM 转成内部 float32 audio frame
  -> wav2lip 推理并输出 /alpha/ws 视频
```

`/alpha/input/audio` WebSocket 消息格式：

```text
TTS -> LiveTalking JSON:
{
  "type": "start",
  "task_id": "demo-001",
  "stream_name": "tts",
  "text": "这段音频由外部 TTS 生成。",
  "sample_rate": 16000,
  "channels": 1,
  "sample_width": 2,
  "format": "pcm",
  "provider": "edge"
}

LiveTalking -> TTS JSON:
{
  "type": "started",
  "task_id": "demo-001",
  "sessionid": "0"
}

TTS -> LiveTalking binary:
PCM16 chunk bytes

TTS -> LiveTalking JSON:
{
  "type": "end",
  "task_id": "demo-001",
  "reason": "completed"
}
```

LiveTalking 支持输入端声明不同采样率或多声道，会在 `/alpha/input/audio` 内部重采样并取第一声道；为了低延迟和少出错，仍建议直接发 `16000/mono/PCM16`。

### 4.5 alpha 视频和音频输出

`/alpha/ws` 是桌面透明输出的核心接口，只有 `LIVETALKING_ALPHA_OUTPUT=1` 或 CLI `--alpha_output` 开启后才有意义。

WebSocket 每条 binary message 格式：

```text
24 byte little-endian header + width * height * 4 RGBA bytes
```

header 字段：

| 字节 | 类型 | 含义 |
| --- | --- | --- |
| `0-3` | `char[4]` | magic，固定 `LTAF`。 |
| `4` | `uint8` | version，当前为 `1`。 |
| `5` | `uint8` | format，当前 `1` 表示 `RGBA8`。 |
| `6-7` | `uint16` | flags，当前为 `0`。 |
| `8-11` | `uint32` | width。 |
| `12-15` | `uint32` | height。 |
| `16-23` | `uint64` | seq，自增帧号。 |

像素数据是 `RGBA8`，每个像素 4 字节，顺序为 `R,G,B,A`。`width/height` 来自当前 avatar 的 `full_imgs` 画布尺寸；如果 avatar 是普通 BGR/BGRA 图，服务端会统一转换成 RGBA。没有透明通道的 avatar 会补全不透明 alpha。

`/alpha/ws` 支持预览参数：

| 参数 | 示例 | 说明 |
| --- | --- | --- |
| `max_width` | `/alpha/ws?max_width=720` | 只对当前客户端缩小输出宽度，不改变服务端原始 avatar。 |
| `max_height` | `/alpha/ws?max_height=720` | 只对当前客户端缩小输出高度。 |
| `fps` | `/alpha/ws?fps=8` | 限制当前客户端收到的帧率。 |

高分辨率 avatar 会产生很大的 raw RGBA 帧，例如 `1920x1080x4` 每帧约 `7.9MB`。Web 调试页建议用：

```text
ws://127.0.0.1:8050/alpha/ws?max_height=720&fps=8
```

overlay 默认也走 alpha stream。为了避免高分辨率 raw RGBA 卡顿，`testclient/.env.example` 默认让 overlay 连接 `/alpha/ws?max_height=1080&fps=15`；如果必须无损原始帧，把 `LIVETALKING_VIDEO_MAX_HEIGHT` 和 `LIVETALKING_VIDEO_FPS` 设为 `0`。

`/alpha/audio` 输出 LiveTalking 侧音频：

```text
WebSocket binary PCM16 chunks，16kHz mono
```

通常只让一个地方播放声音。如果 TTS 服务或业务组件已经播放音频，overlay 和 Web 页应关闭 `/alpha/audio` 播放，避免重复声音。

## 5. 测试客户端

`testclient/` 是独立测试包，不参与 LiveTalking 主配置。

```text
testclient/
  backend/   robottts 兼容 TTS 测试服务，uv 独立环境
  web/       浏览器可视化测试页面，npm 独立依赖
  overlay/   Electron 透明置顶窗口，npm 独立依赖
```

### 5.0 配置分工

`testclient/.env` 同时给 `start-tts.sh`、`start-web.sh`、`start-overlay.sh` 读取，但每类变量的使用者不同：

| 变量前缀/名称 | 谁读取 | 作用 |
| --- | --- | --- |
| `TEST_TTS_*`、`TTS_SERVICE_*`、`ROBOT_TTS_EDGE_*`、`BAILIAN_*`、`DASHSCOPE_API_KEY` | `testclient/backend` | 控制测试 TTS 服务。生产接真实 robot-tts 时不需要启动这个后端。 |
| `LIVETALKING_URL`、`LIVETALKING_WS_URL` | 测试脚本和部分客户端逻辑 | LiveTalking 主服务 HTTP/WS 地址。 |
| `VITE_*` | `testclient/web` | 浏览器页面编译期环境变量。改完必须重启 `./start-web.sh`。 |
| `LIVETALKING_SERVER`、`LIVETALKING_VIDEO_*`、`LIVETALKING_PLAY_AUDIO` | `testclient/overlay` | Electron 透明窗口连接和显示参数。 |
| `TTS_SERVER_URL` | 测试后端、也可复制给 LiveTalking 主服务 | robottts 兼容 TTS HTTP 基地址。 |

默认单机配置应保持这几组地址一致：

```bash
TTS_SERVICE_PORT=8036
TTS_SERVER_URL=http://127.0.0.1:8036
VITE_TTS_SERVER_URL=http://127.0.0.1:8036

LIVETALKING_PORT=8050
LIVETALKING_URL=http://127.0.0.1:8050
LIVETALKING_WS_URL=ws://127.0.0.1:8050
LIVETALKING_SERVER=http://127.0.0.1:8050
VITE_LIVETALKING_URL=http://127.0.0.1:8050
VITE_ALPHA_INPUT_WS=ws://127.0.0.1:8050/alpha/input/audio
```

如果 Web 页面、TTS 服务、LiveTalking 不在同一台机器，浏览器里的 `127.0.0.1` 指的是浏览器所在机器，不是 GPU 服务器。此时 `VITE_LIVETALKING_URL`、`VITE_TTS_SERVER_URL`、`VITE_ALPHA_INPUT_WS` 要写成浏览器能访问到的 IP、域名或端口转发地址。

### 5.1 backend 参数

| 变量 | 可选/范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `TEST_TTS_PROVIDER` | `edge` / `bailian` | `edge` | 选择测试 TTS provider。 |
| `TTS_SERVICE_HOST` | IP | `0.0.0.0` | 监听地址。 |
| `TTS_SERVICE_PORT` | `1-65535` | `8036` | TTS 测试服务端口。 |
| `TTS_STREAM_SAMPLE_RATE` | 正整数 | `16000` | 输出采样率。LiveTalking 当前推荐 16kHz。 |
| `TTS_STREAM_CHUNK_MS` | `>=20` | `40` | PCM 输出块大小。LiveTalking 内部会拆成 20ms 帧。 |
| `TEST_TTS_CORS_ORIGIN` | CORS origin | `*` | Web 测试页跨域访问用。 |
| `ROBOT_TTS_EDGE_VOICES` | 逗号分隔音色名 | 常用中文/英文音色 | EdgeTTS 音色列表。 |
| `ROBOT_TTS_EDGE_RATE` | EdgeTTS rate，如 `+0%` | `+0%` | 语速。 |
| `ROBOT_TTS_EDGE_VOLUME` | EdgeTTS volume，如 `+0%` | `+0%` | 音量。 |
| `ROBOT_TTS_EDGE_PITCH` | EdgeTTS pitch，如 `+0Hz` | `+0Hz` | 音高。 |
| `DASHSCOPE_API_KEY` | 字符串 | 空 | 百炼 provider 必填。 |
| `BAILIAN_COSYVOICE_MODEL` | 模型名 | `cosyvoice-v3-flash` | 百炼 CosyVoice 模型。 |
| `BAILIAN_VOICES` | 逗号分隔音色名 | `longanyang,longanhuan,longhuhu_v3` | 百炼音色列表。 |
| `BAILIAN_INSTRUCTION_FIELD` | 字段名 | `instructions` | 百炼指令字段名。 |
| `BAILIAN_USE_PROMPTS_AS_INSTRUCTIONS` | `1/0` | `1` | 是否把 `prompts` 作为指令传给百炼。 |

### 5.2 Web 参数

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

### 5.3 overlay 参数

| 变量 | 可选/范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `LIVETALKING_SERVER` | HTTP 地址 | `http://127.0.0.1:8050` | overlay 连接的 LiveTalking 服务。远程显示时改这里。 |
| `LIVETALKING_CLICK_THROUGH` | `1/0` | `1` | 视频窗口是否鼠标穿透。控制条不穿透。 |
| `LIVETALKING_PLAY_AUDIO` | `1/0` | `0` | 是否由 overlay 播放 `/alpha/audio`。通常保持 0，避免重复声音。 |
| `LIVETALKING_AUTO_SESSION` | `1/0` | `1` | 启动后自动创建 alpha session。 |
| `LIVETALKING_CLOSE_SESSION_ON_EXIT` | `1/0` | `0` | 退出 overlay 时是否关闭 LiveTalking session。 |
| `LIVETALKING_SCALE` | `0.25-3.0` | `1` | 启动显示倍率。控制条可运行时调整。 |
| `LIVETALKING_RENDERER` | `webgl` / `2d` | `webgl` | 渲染方式。GPU 进程异常时可用 `2d`。 |
| `LIVETALKING_CONTROL_WIDTH` | 正整数 px | `340` | 控制条宽度。 |
| `LIVETALKING_CONTROL_HEIGHT` | 正整数 px | `38` | 控制条高度。 |
| `LIVETALKING_VIDEO_MAX_WIDTH` | 非负整数 px | `0` | overlay 请求 alpha stream 的最大宽度，`0` 表示不限制。 |
| `LIVETALKING_VIDEO_MAX_HEIGHT` | 非负整数 px | `1080` | overlay 请求 alpha stream 的最大高度，用于降低 raw RGBA 传输压力。 |
| `LIVETALKING_VIDEO_FPS` | 非负数 | `15` | overlay 请求 alpha stream 的帧率，`0` 表示不限制。 |
| `LIVETALKING_X` / `LIVETALKING_Y` | 屏幕坐标 | 空 | 初始窗口位置。 |

overlay 显示尺寸来自 `/alpha/ws` 帧头的 `width/height`，也就是 avatar `full_imgs` 原始画布尺寸。缩放只影响桌面显示大小，不裁剪原始帧。

## 6. avatar 制作和导入

所有 avatar 存放在：

```text
data/avatars/<avatar_id>/
```

该目录不进 Git，需要单独分发。切换数字人只改 `.env` 里的 `AVATAR_ID`，或临时用环境变量覆盖：

```bash
AVATAR_ID=<avatar_id> ./entrypoint.sh
```

### 6.1 wav2lip

当前稳定推荐。适合桌面助手、透明 PNG、单图或短视频快速制作。

必要文件：

```text
data/avatars/<avatar_id>/
  full_imgs/
  face_imgs/
  coords.pkl
```

模型文件：

```text
models/wav2lip.pth
```

下载默认 wav2lip 运行模型：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip
```

如果要制作 wav2lip avatar，建议提前下载人脸检测模型，避免生成时临时联网失败：

```bash
cd /path/to/LiveTalking
./scripts/download-models.sh s3fd
```

制作命令：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/person.png \
  --img_size 256 \
  --avatar_id my_avatar
```

`--video_path` 支持：

- 单张图片：`.png`、`.jpg`、`.jpeg`、`.webp`、`.bmp`
- 图片目录：目录内图片按文件名排序导入
- 视频：`.mp4`、`.mov`、`.avi`、`.mkv`、`.webm`

wav2lip 制作参数：

| 参数 | 可选/范围 | 默认 | 说明和调参建议 |
| --- | --- | --- | --- |
| `--video_path` | 文件或目录 | 空 | 输入素材。透明桌面助手建议用带 alpha 的 PNG 或 PNG 序列。 |
| `--avatar_id` | 目录名 | `wav2lip_avatar1` | 输出到 `data/avatars/<avatar_id>`。 |
| `--save_path` | 目录 | `data/avatars` | avatar 根目录，一般不改。 |
| `--img_size` | 正整数 | `96` | `face_imgs` 裁剪尺寸。普通 wav2lip 可用 96；`wav2lip256` 模型建议 256。 |
| `--pads top bottom left right` | 4 个整数，常用 `-50` 到 `100` | `0 10 0 0` | 扩大或缩小人脸框。下巴缺失增大 `bottom`；嘴部太小可适当加左右。负数会缩小。 |
| `--nosmooth` | 开关 | 关闭 | 关闭 bbox 平滑。画面抖动时不要开；裁剪跟不上脸时可试。 |
| `--face_det_batch_size` | 正整数 | `16` | 人脸检测 batch。显存不足或 OOM 降到 `8/4/1`。 |

透明 PNG 说明：

- 普通 3 通道 avatar 也可以走 `/alpha/ws`，LiveTalking 会自动补一个全不透明 alpha 通道。
- `full_imgs` 可以是 RGBA PNG。
- `face_imgs` 可保留 alpha，但最终透明效果主要由 `full_imgs` 画布 alpha 决定。
- `/alpha/ws` 输出 raw RGBA；普通 WebRTC 页面仍按普通视频显示。

### 6.2 MuseTalk

MuseTalk 质量潜力更高，但依赖和模型更复杂。当前已还原官方预处理逻辑，不带本地 fallback；需要准备 MuseTalk、VAE、Whisper、FaceParsing、DWPose/MMPose 等相关模型和环境。

先下载模型资产：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh musetalk
```

下载后应存在：

```text
models/musetalkV15/musetalk.json
models/musetalkV15/unet.pth
models/sd-vae/
models/whisper/
models/dwpose/dw-ll_ucoco_384.pth
models/face-parse-bisent/resnet18-5c106cde.pth
models/face-parse-bisent/79999_iter.pth
```

MuseTalk 生成 avatar 还会用到 `mmpose` / `mmcv` / `mmengine`。这几个依赖和 CUDA、PyTorch 版本耦合较强，默认 `uv sync` 不强行安装。需要制作 MuseTalk avatar 的机器先按本机 CUDA 版本安装 MMPose 环境，例如：

```bash
uv run --python .venv/bin/python pip install -U openmim
uv run --python .venv/bin/python mim install "mmengine" "mmcv" "mmdet" "mmpose"
```

如果这一步失败，不要继续调 MuseTalk 参数，先解决 MMPose/MMCV 与本机 CUDA、PyTorch 的兼容。

必要文件：

```text
data/avatars/<avatar_id>/
  full_imgs/
  mask/
  coords.pkl
  mask_coords.pkl
  latents.pt
```

制作命令：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.musetalk.genavatar \
  --file /path/to/person.mp4 \
  --avatar_id my_musetalk_avatar \
  --version v15 \
  --bbox_shift 0 \
  --extra_margin 10 \
  --parsing_mode jaw
```

MuseTalk 制作参数：

| 参数 | 可选/范围 | 默认 | 说明和调参建议 |
| --- | --- | --- | --- |
| `--file` | 图片、PNG 目录或视频 | 示例路径 | 输入素材。目录目前优先 PNG。 |
| `--avatar_id` | 目录名 | `musetalk_avatar1` | 输出 avatar 名称。 |
| `--save_path` | 目录 | `data/avatars` | avatar 根目录，一般不改。 |
| `--version` | `v1` / `v15` | `v15` | `v15` 使用新版裁剪和 parsing，推荐；`v1` 走旧逻辑。 |
| `--bbox_shift` | 整数，常用 `-50` 到 `50` | `0` | 人脸框整体偏移。嘴部位置不准时小步调。 |
| `--extra_margin` | 非负整数，常用 `0-40` | `10` | v15 下给下边界额外留白，嘴巴/下巴被截断时调大。 |
| `--parsing_mode` | `jaw` / `neck` / `raw` | `jaw` | 融合 mask 范围。`jaw` 适合下颌，`neck` 范围更大，`raw` 更接近原始区域。 |
| `--gpu_id` | GPU 编号 | `0` | 当前函数内部主要看 CUDA 可用性，保留为兼容参数。 |
| `--left_cheek_width` / `--right_cheek_width` | 正整数 | `90` | CLI 保留参数，当前生成函数未实际传入，通常不用调。 |

### 6.3 Ultralight

轻量方案，资源占用低，但效果通常不如 wav2lip/MuseTalk。需要已有训练 checkpoint。

必要文件：

```text
data/avatars/<avatar_id>/
  full_imgs/
  face_imgs/
  coords.pkl
  ultralight.pth
```

制作命令：

```bash
cd /path/to/LiveTalking
uv run --python .venv/bin/python python -m avatars.ultralight.genavatar \
  --video_path /path/to/person.mp4 \
  --img_size 168 \
  --checkpoint /path/to/ultralight.pth \
  --avatar_id my_ultralight_avatar
```

参数：

| 参数 | 可选/范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `--video_path` | 视频路径 | 空 | 输入视频。 |
| `--img_size` | 正整数 | `168` | 裁剪后 face 图片尺寸，需和 checkpoint 训练尺寸匹配。 |
| `--checkpoint` | `.pth` 文件 | 空 | 要复制到 avatar 目录的 `ultralight.pth`。 |
| `--avatar_id` | 目录名 | `ultralight_avatar1` | 输出 avatar 名称。 |

## 7. 状态和动作

查询是否正在说话：

```bash
curl -X POST http://127.0.0.1:8050/is_speaking \
  -H 'Content-Type: application/json' \
  -d '{"sessionid":"<sessionid>"}'
```

打断当前朗读：

```bash
curl -X POST http://127.0.0.1:8050/interrupt_talk \
  -H 'Content-Type: application/json' \
  -d '{"sessionid":"<sessionid>"}'
```

自定义动作走官方 `customvideo_config` 和 `/set_audiotype`。常见用法是：

- 不说话时播放 idle 视频。
- 说话或指定状态时播放对应动作视频。
- 外部控制端根据 `/is_speaking` 或业务状态切换 `audiotype`。

## 8. 文件和迁移边界

需要随代码提交：

- `start-livetalking.sh`
- `entrypoint.sh`
- `config.py`
- `config.yaml`
- `pyproject.toml`
- `uv.lock`
- `requirements.txt`
- `tts/robottts.py`
- `server/alpha_stream.py`
- `server/routes.py` 中 alpha、admin、avatar 路由整合
- `streamout/webrtc.py` 中 alpha 帧发布
- `app.py` 中相关启动参数
- `avatars/wav2lip/genavatar.py`、`avatars/wav2lip_avatar.py`、`utils/image.py` 中透明 PNG/单图支持
- `testclient/`
- `.env.example`
- `.gitignore`
- `README-LOCAL.md`

不进 Git，需要单独准备：

- `.venv/`
- `.env`
- `models/*`
- `hf_assets/`、`downloads/`、`pretrained/`、`checkpoints/`、`weights/`
- `data/avatars/*`
- `*.log`、`logs/`、`nohup.out`
- `testclient/**/node_modules/`、`testclient/web/dist/`

最小迁移资产：

```text
models/wav2lip.pth
data/avatars/<avatar_id>/
```

如果迁移环境可访问 Hugging Face 或 `HF_ENDPOINT=https://hf-mirror.com`，可以不手工拷贝默认示例资产，直接在新环境执行：

```bash
./scripts/download-models.sh wav2lip-demo
```

## 9. 排错

端口检查：

```bash
ss -ltnp | grep -E ':8036|:8050|:8070'
```

TTS 检查：

```bash
curl http://127.0.0.1:8036/health
curl http://127.0.0.1:8036/tts/voices
```

alpha session 检查：

```bash
curl -X POST http://127.0.0.1:8050/alpha/session \
  -H 'Content-Type: application/json' \
  -d '{"reuse":true}'
```

常见问题：

- 网页打不开：确认 `--listenport`、防火墙、VS Code 端口转发。
- overlay 没画面：确认 `LIVETALKING_ALPHA_OUTPUT=1` 或启动参数带 `--alpha_output`，并且 `LIVETALKING_SERVER` 指向正确地址。
- overlay 画面尺寸不对：检查 `data/avatars/<avatar_id>/full_imgs` 原图宽高，控制条缩放只改显示倍率。
- 声音重复：保持 `LIVETALKING_PLAY_AUDIO=0`，让 TTS 或业务组件播放声音。
- 推理卡顿：先把 `--batch_size` 降到 `4` 或 `2`；确认 GPU 推理 fps 和最终输出 fps 都接近 25。
- 人脸裁剪不准：wav2lip 调 `--pads`；MuseTalk 调 `--bbox_shift`、`--extra_margin`、`--parsing_mode`。
- Hugging Face 访问失败：启动前加 `HF_ENDPOINT=https://hf-mirror.com`。

## 10. 推荐交接顺序

1. 克隆仓库，执行 `uv sync --python 3.10 --inexact`。
2. 执行 `cp .env.example .env`。
3. 执行 `HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo`。
4. 启动真实 `robottts` 兼容 TTS，或用 `testclient/backend` 先测。
5. 执行 `./entrypoint.sh` 启动 LiveTalking；默认已经开启 `LIVETALKING_ALPHA_OUTPUT=1`。
6. 用 `testclient/web` 验证接口、TTS 和 alpha 视频。
7. 用 `testclient/overlay` 验证透明置顶显示。
8. 要换自己的数字人时，先按第 6 节制作或导入 avatar，再改 `.env` 里的 `AVATAR_ID`。
