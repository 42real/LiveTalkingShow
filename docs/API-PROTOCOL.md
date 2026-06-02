# LiveTalking 接口协议文档

本文档描述当前本地交接版 LiveTalking 的接口协议。它覆盖 LiveTalking 主服务、`robottts` 兼容 TTS 服务，以及测试客户端/overlay 需要对接的主要传输格式。

## 1. 协议性质

当前服务不是 FastAPI。

实际运行入口是 `app.py` 里的 `aiohttp.web.Application`：

```text
app.py
  -> aiohttp.web.Application
  -> server/routes.py 注册 HTTP / WebSocket 路由
  -> server/rtc_manager.py 处理 WebRTC offer/answer
  -> server/alpha_stream.py 输出 alpha 视频/音频 WebSocket
```

仓库里仍能看到 Flask 相关 import，这是上游历史遗留，不是当前本地服务的主要 HTTP 入口。因此：

| 项目 | 当前状态 |
| --- | --- |
| Web 框架 | `aiohttp.web` |
| 是否 FastAPI | 否 |
| 是否有自动 Swagger/OpenAPI `/docs` | 否 |
| 是否有自动 OpenAPI schema | 否 |
| CORS | 当前对主服务所有路由开放 |
| 协议类型 | HTTP JSON、multipart/form-data、WebSocket、WebRTC SDP offer/answer |

如果后续接入方习惯 FastAPI，可以单独写 FastAPI 网关或 OpenAPI 描述文件，但当前代码本身不会生成 FastAPI 文档。

## 2. 基础地址

默认本地地址：

```text
LiveTalking: http://127.0.0.1:8050
测试 TTS:    http://127.0.0.1:8036
```

生产环境只需要把地址替换成对应机器 IP：

```text
LiveTalking: http://<LiveTalking机器IP>:<端口>
TTS:         http://<TTS机器IP>:<端口>
```

服务之间不依赖彼此的磁盘目录。LiveTalking、TTS、显示端只通过接口通信。

## 3. 通用 JSON 规范

LiveTalking 主服务的 JSON 响应大多使用统一格式：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {}
}
```

错误格式：

```json
{
  "code": -1,
  "msg": "error message"
}
```

注意：

- 不要只用 HTTP status 判断业务成功。LiveTalking 多数业务错误仍可能返回 HTTP 200，但 `code != 0`。
- WebRTC offer 参数错误可能返回 HTTP 400。
- 测试 TTS 服务不是 LiveTalking 主服务，它的 JSON 结构使用 `success`、`error`、`message` 等字段，见第 13 节。

## 4. Session 概念

LiveTalking 的一次数字人运行实例叫 session。

常见字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sessionid` | string | 会话 ID。为空时部分接口会创建或使用默认 alpha session。 |
| `avatar` | string | 可选，指定要加载的 avatar ID。对应 `data/avatars/<avatar>`。 |
| `refaudio` | string | 可选，兼容旧 TTS 音色字段。 |
| `reftext` | string | 可选，兼容旧 TTS 提示文本字段。 |
| `custom_config` | string | 可选，自定义动作配置 JSON 字符串。 |

桌面透明显示推荐使用 alpha session：

```text
POST /alpha/session
POST /alpha/speak
WS   /alpha/ws
WS   /alpha/input/audio
```

## 5. LiveTalking 主服务接口总览

| 方法 | 路径 | 类型 | 作用 |
| --- | --- | --- | --- |
| `POST` | `/offer` | WebRTC JSON | 官方兼容 WebRTC 数字人输出。 |
| `POST` | `/human` | JSON | legacy 文本输入，驱动指定 session。 |
| `POST` | `/humanaudio` | multipart | 上传音频文件驱动指定 session。 |
| `POST` | `/set_audiotype` | JSON | 设置自定义动作/状态。 |
| `POST` | `/record` | JSON | 开始或结束录制。 |
| `GET` | `/record/{sessionid}` | file | 下载录制文件。 |
| `POST` | `/interrupt_talk` | JSON | 打断当前 session 朗读。 |
| `POST` | `/is_speaking` | JSON | 查询 session 是否正在说话。 |
| `POST` | `/close_session` | JSON | 关闭指定 session。 |
| `GET` | `/api/admin/config` | JSON | 查看当前运行配置。 |
| `GET` | `/api/admin/sessions` | JSON | 查看当前活跃 session。 |
| `POST` | `/alpha/session` | JSON | 创建或复用 alpha 桌面显示 session。 |
| `POST` | `/alpha/speak` | JSON | 输入文字，由 LiveTalking 内部 TTS 驱动数字人。 |
| `POST` | `/alpha/close` | JSON | 关闭 alpha session。 |
| `GET` | `/alpha/tuning` | JSON | 查询 alpha 贴回区域调试参数。 |
| `POST` | `/alpha/tuning` | JSON | 更新 alpha 贴回区域调试参数。 |
| `GET` | `/alpha/ws` | WebSocket binary | 输出 alpha 视频帧。 |
| `GET` | `/alpha/audio` | WebSocket binary | 输出 LiveTalking 侧音频。 |
| `GET` | `/alpha/input/audio` | WebSocket JSON + binary | 接收外部 TTS 生成的 PCM 音频流。 |
| `POST` | `/alpha/webrtc/packed_offer` | WebRTC JSON | 推荐的远程透明 WebRTC 输出，单视频轨 packed color+alpha。 |
| `POST` | `/alpha/webrtc/offer` | WebRTC JSON | 实验性双视频轨透明 WebRTC 输出。 |
| `POST` | `/api/avatar/task` | JSON 或 multipart | 创建 avatar 制作任务。 |
| `GET` | `/api/avatar/task/{task_id}` | JSON | 查询 avatar 任务状态。 |
| `DELETE` | `/api/avatar/task/{task_id}` | JSON | 删除 avatar 任务。 |
| `GET` | `/api/avatar/tasks` | JSON | 列出 avatar 任务。 |

## 6. alpha 文本驱动协议

### 6.1 创建或复用 alpha session

```http
POST /alpha/session
Content-Type: application/json
```

请求：

```json
{
  "reuse": true,
  "sessionid": "",
  "session": {
    "avatar": "avatar3d2"
  }
}
```

字段：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `reuse` | boolean | `true` | 是否复用默认 alpha session。 |
| `sessionid` | string | 空 | 指定 session ID；为空时服务端自动生成或复用默认值。 |
| `session` | object | `{}` | 可选，avatar 构造参数。 |

也可以把 `avatar`、`refaudio`、`reftext`、`custom_config` 直接放在顶层。

返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "sessionid": "123456"
  }
}
```

### 6.2 输入文字朗读

```http
POST /alpha/speak
Content-Type: application/json
```

请求：

```json
{
  "sessionid": "123456",
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

字段：

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `sessionid` | string | 默认 alpha session | 目标 session。 |
| `text` | string | 必填 | 要朗读的文本。 |
| `type` | `echo` / `chat` | `echo` | `echo` 直接朗读；`chat` 先走 `llm_response`。 |
| `interrupt` | boolean | `true` | 是否先打断当前朗读。 |
| `tts.voice_id` | integer | `0` | TTS 音色 ID。 |
| `tts.mode` | string | `ROBOTTTS_MODE` | TTS 模式，例如 `instruct2`。 |
| `tts.prompts` | string | 空 | TTS 指令/提示词。 |
| `tts.ref_file` | string/integer | 可选 | 兼容旧字段，会映射到音色。 |
| `tts.ref_text` | string | 可选 | 兼容旧字段，会映射到提示词。 |

返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "sessionid": "123456"
  }
}
```

内部链路：

```text
POST /alpha/speak
  -> avatar_session.put_msg_txt()
  -> tts/robottts.py 连接 ws://<TTS_SERVER>/tts/ws
  -> TTS 返回 PCM16 chunks
  -> LiveTalking 推理生成视频帧
  -> /alpha/ws 输出视频
  -> /alpha/audio 输出音频
```

## 7. alpha 外部音频输入协议

这个接口用于把已有 TTS 或业务组件生成的音频流推给 LiveTalking，绕过 LiveTalking 内部 TTS。

```http
GET /alpha/input/audio
Upgrade: websocket
```

可选 query：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `sessionid` | 默认 alpha session | 指定接收音频的 session。 |
| `interrupt` | `1` | `1` 表示 start 时打断当前朗读；`0` 不打断。 |

消息流程：

```text
TTS -> LiveTalking TEXT JSON start
LiveTalking -> TTS TEXT JSON started
TTS -> LiveTalking BINARY PCM chunks
TTS -> LiveTalking TEXT JSON end
```

start 消息：

```json
{
  "type": "start",
  "task_id": "demo-001",
  "stream_name": "tts",
  "text": "这段音频由外部 TTS 生成。",
  "sample_rate": 16000,
  "channels": 1,
  "sample_width": 2,
  "format": "pcm",
  "provider": "robottts"
}
```

started 响应：

```json
{
  "type": "started",
  "task_id": "demo-001",
  "sessionid": "123456"
}
```

binary 音频：

```text
PCM16 little-endian, mono 推荐, 16000 Hz 推荐
```

end 消息：

```json
{
  "type": "end",
  "task_id": "demo-001",
  "reason": "completed"
}
```

LiveTalking 会处理非 16kHz 或多声道输入，但为了低延迟和少出错，推荐直接发：

```text
16000 Hz / mono / signed 16-bit PCM / little-endian
```

## 8. alpha 视频和音频输出协议

### 8.1 alpha 视频 WebSocket

```http
GET /alpha/ws?max_height=720&fps=25&format=raw&quality=80
Upgrade: websocket
```

query 参数：

| 参数 | 范围 | 默认 | 说明 |
| --- | --- | --- | --- |
| `max_width` | `0-4096` | `0` | 只对当前客户端缩小宽度，`0` 表示不限制。 |
| `max_height` | `0-4096` | `0` | 只对当前客户端缩小高度，`0` 表示不限制。 |
| `fps` | `0-60` | `0` | 当前客户端输出帧率限制，`0` 表示不限制。 |
| `format` / `frame_format` | `raw` / `jpeg` / `png` / `webp` | `raw` | 输出帧编码。 |
| `quality` | `1-100` | `80` | `jpeg` / `webp` 质量。 |

每条 WebSocket binary message：

```text
24 byte little-endian header + payload
```

header：

| 字节 | 类型 | 含义 |
| --- | --- | --- |
| `0-3` | `char[4]` | magic，固定 `LTAF`。 |
| `4` | `uint8` | version，当前 `1`。 |
| `5` | `uint8` | format：`1=raw RGBA8`，`2=JPEG`，`3=PNG`，`4=WebP`。 |
| `6-7` | `uint16` | flags，当前 `0`。 |
| `8-11` | `uint32` | width。 |
| `12-15` | `uint32` | height。 |
| `16-23` | `uint64` | seq，自增帧号。 |

payload：

| format | payload |
| --- | --- |
| `raw` | `RGBA8`，每像素 `R,G,B,A` 4 字节。 |
| `jpeg` | JPEG 图片字节，不保留透明。 |
| `png` | PNG 图片字节，可保留透明。 |
| `webp` | WebP 图片字节，可保留透明。 |

推荐：

| 场景 | 推荐参数 |
| --- | --- |
| 同机 Electron 透明 overlay | `format=raw&max_height=1080&fps=15` |
| 浏览器调试/VSCode 转发预览 | `format=jpeg&max_height=720&fps=25&quality=80` |
| 临时远程透明检查 | `format=webp&max_height=720&fps=12&quality=80` |

### 8.2 alpha 音频 WebSocket

```http
GET /alpha/audio
Upgrade: websocket
```

输出：

```text
WebSocket binary PCM16 chunks
16000 Hz / mono / signed 16-bit PCM
```

注意：通常只让一个地方播放声音。如果 TTS 服务或业务组件已经播放音频，显示端应关闭 `/alpha/audio` 播放，避免重复声音。

## 9. WebRTC 输出协议

### 9.1 普通 WebRTC

```http
POST /offer
Content-Type: application/json
```

请求：

```json
{
  "sdp": "v=0...",
  "type": "offer"
}
```

返回：

```json
{
  "sdp": "v=0...",
  "type": "answer",
  "sessionid": "123456"
}
```

这个接口输出普通音频轨 + 视频轨，不带透明 alpha。

### 9.2 packed alpha WebRTC

```http
POST /alpha/webrtc/packed_offer
Content-Type: application/json
```

客户端 PeerConnection 要按顺序创建：

```text
audio recvonly
video recvonly
```

推荐配置：

```js
const pc = new RTCPeerConnection({ bundlePolicy: "max-bundle" });
pc.addTransceiver("audio", { direction: "recvonly" });
pc.addTransceiver("video", { direction: "recvonly" });
```

请求：

```json
{
  "sdp": "v=0...",
  "type": "offer",
  "session": {
    "avatar": "avatar3d2"
  }
}
```

返回：

```json
{
  "sdp": "v=0...",
  "type": "answer",
  "sessionid": "123456",
  "tracks": {
    "audio": "audio",
    "packed": "video-0",
    "packing": "left=color,right=alpha"
  }
}
```

packed video 规则：

```text
一条普通视频轨，画面宽度是合成宽度的 2 倍
左半边 = color
右半边 = alpha mask
```

显示端需要把同一帧左右两半拆开，再用 WebGL/canvas 合成透明画面。这个方案可以避免双视频轨的 color/alpha 不同步问题。

### 9.3 双轨 alpha WebRTC

```http
POST /alpha/webrtc/offer
Content-Type: application/json
```

客户端 PeerConnection 要按顺序创建：

```text
audio recvonly
video recvonly  color
video recvonly  alpha mask
```

返回：

```json
{
  "sdp": "v=0...",
  "type": "answer",
  "sessionid": "123456",
  "tracks": {
    "audio": "audio",
    "color": "video-0",
    "alpha": "video-1"
  }
}
```

该方案只作为对照测试。两条视频轨可能在浏览器解码层发生不同步，不建议作为生产透明显示方案。

## 10. legacy 控制接口

### 10.1 `/human`

```http
POST /human
Content-Type: application/json
```

请求：

```json
{
  "sessionid": "123456",
  "text": "你好",
  "type": "echo",
  "interrupt": true,
  "tts": {
    "voice_id": 0
  }
}
```

说明：

- `type=echo`：直接朗读。
- `type=chat`：调用 `llm_response` 生成回复后再朗读。
- 需要已有 session，通常由 `/offer` 创建。
- alpha 桌面助手优先用 `/alpha/speak`。

### 10.2 `/humanaudio`

```http
POST /humanaudio
Content-Type: multipart/form-data
```

表单字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sessionid` | string | 目标 session。 |
| `file` | file | 音频文件字节。 |

### 10.3 `/interrupt_talk`

```json
{
  "sessionid": "123456"
}
```

返回：

```json
{
  "code": 0,
  "msg": "ok"
}
```

### 10.4 `/is_speaking`

请求：

```json
{
  "sessionid": "123456"
}
```

返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": true
}
```

### 10.5 `/record`

请求：

```json
{
  "sessionid": "123456",
  "type": "start_record"
}
```

或：

```json
{
  "sessionid": "123456",
  "type": "end_record"
}
```

录制文件下载：

```text
GET /record/{sessionid}
```

## 11. alpha 贴回区域调试协议

```http
GET /alpha/tuning?sessionid=123456
```

返回示例：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "sessionid": "123456",
    "pads": [0, 20, 0, 0],
    "source_width": 405,
    "source_height": 720,
    "base_bbox": {"x1": 100, "y1": 120, "x2": 220, "y2": 260},
    "padded_bbox": {"x1": 100, "y1": 120, "x2": 220, "y2": 280}
  }
}
```

更新：

```http
POST /alpha/tuning
Content-Type: application/json
```

```json
{
  "sessionid": "123456",
  "pads": [0, 20, 0, 0]
}
```

也支持用字段方式传：

```json
{
  "top": 0,
  "bottom": 20,
  "left": 0,
  "right": 0
}
```

`pads` 顺序：

```text
[top, bottom, left, right]
```

当前实现会把每个值限制在 `-300` 到 `300`。实际调试建议从 `-50` 到 `100` 小步调整。

## 12. avatar 制作任务接口

### 12.1 创建任务

```http
POST /api/avatar/task
Content-Type: application/json
```

请求：

```json
{
  "model": "wav2lip",
  "avatar_id": "my_avatar",
  "video_path": "/path/to/input.mp4",
  "img_size": 256,
  "pads": "0 10 0 0",
  "nosmooth": false
}
```

也支持 `multipart/form-data` 上传：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `model` | string | `wav2lip` / `musetalk` / `ultralight`。 |
| `avatar_id` | string | 输出 avatar ID。 |
| `video_file` | file | 上传的视频文件。 |
| `video_path` | string | 本地视频路径。`video_file` 和 `video_path` 二选一。 |
| `img_size` | integer | Wav2Lip 常用 `256`。 |
| `pads` | string/list | Wav2Lip 人脸裁剪边距，顺序 `top bottom left right`。 |
| `bbox_shift` | integer | MuseTalk 人脸框偏移。 |
| `extra_margin` | integer | MuseTalk mask 额外边距。 |
| `parsing_mode` | string | MuseTalk 解析模式，例如 `jaw`。 |
| `version` | string | MuseTalk 版本，例如 `v15`。 |
| `face_det_batch_size` | integer | 人脸检测 batch。 |
| `notifyurl` | string | 可选，任务完成通知 URL。 |

返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "task_id": "task-id"
  }
}
```

### 12.2 查询任务

```text
GET /api/avatar/task/{task_id}
GET /api/avatar/tasks
DELETE /api/avatar/task/{task_id}
```

## 13. robottts 兼容 TTS 协议

LiveTalking 的 `--tts robottts` 插件只要求 TTS 服务实现本节协议。真实 `/home/szh/projects/robot-tts` 和 `testclient/backend` 应保持兼容。

### 13.1 总览

| 方法 | 路径 | 类型 | 作用 |
| --- | --- | --- | --- |
| `GET` | `/health` | JSON | 健康检查和音频格式元信息。 |
| `GET` | `/tts/voices` | JSON | 查询可用音色。 |
| `POST` | `/tts` | JSON | 一次性合成 wav 文件，测试用。 |
| `GET` | `/tts/ws` | WebSocket JSON + binary | LiveTalking 内部 TTS 插件使用的流式合成接口。 |
| `POST` | `/tts/task/create` | JSON | 创建外部推流任务。 |
| `POST` | `/tts/task/submit` | JSON | 提交任务文本并开始推流。 |
| `POST` | `/tts/task/start` | JSON | 创建并提交任务，测试客户端常用。 |
| `POST` | `/tts/task/cancel` | JSON | 取消任务。 |
| `GET` | `/tts/task/status?task_id=...` | JSON | 查询任务状态。 |

### 13.2 健康检查

```http
GET /health
```

返回：

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

### 13.3 音色列表

```http
GET /tts/voices
```

返回：

```json
{
  "voices": [
    {
      "id": 0,
      "name": "zh-CN-XiaoxiaoNeural",
      "description": "zh-CN-XiaoxiaoNeural"
    }
  ]
}
```

### 13.4 LiveTalking 内部流式 TTS

```http
GET /tts/ws
Upgrade: websocket
```

消息流程：

```text
LiveTalking -> TTS TEXT JSON start
TTS -> LiveTalking TEXT JSON started
LiveTalking -> TTS TEXT JSON text
TTS -> LiveTalking BINARY PCM chunks
TTS -> LiveTalking TEXT JSON result final
LiveTalking -> TTS TEXT JSON end
```

start：

```json
{
  "action": "start",
  "voice_id": 0,
  "mode": "instruct2",
  "prompts": "请自然清晰地朗读。"
}
```

started：

```json
{
  "action": "started"
}
```

text：

```json
{
  "action": "text",
  "text": "你好，我是数字人。"
}
```

binary audio：

```text
PCM16 little-endian chunks, 16000 Hz mono recommended
```

final：

```json
{
  "action": "result",
  "type": "final",
  "meta": {
    "sample_rate": 16000,
    "channels": 1,
    "sample_width": 2,
    "format": "pcm"
  }
}
```

error：

```json
{
  "action": "error",
  "error": "SynthesisError",
  "message": "error message"
}
```

### 13.5 外部 TTS task 推流

这个接口用于“控制端调用 TTS，TTS 主动把音频推给 LiveTalking `/alpha/input/audio`”。

```http
POST /tts/task/start
Content-Type: application/json
```

请求：

```json
{
  "task_id": "demo-001",
  "text": "这段话由 TTS 生成音频，再推给 LiveTalking。",
  "voice_id": 0,
  "mode": "instruct2",
  "prompts": "请自然清晰地朗读。",
  "target_hardware": "ws://127.0.0.1:8050/alpha/input/audio"
}
```

返回：

```json
{
  "success": true,
  "task_id": "demo-001",
  "state": "submitted"
}
```

任务状态：

```text
GET /tts/task/status?task_id=demo-001
```

返回：

```json
{
  "task_id": "demo-001",
  "state": "done",
  "owns_active_slot": false
}
```

## 14. 推荐对接方式

### 14.1 输入文字，让 LiveTalking 自己调用 TTS

```text
控制端
  -> POST /alpha/speak
LiveTalking
  -> WS /tts/ws
TTS
  -> binary PCM chunks
LiveTalking
  -> WS /alpha/ws 输出视频
显示端
  -> 渲染 RGBA/压缩帧
```

适合：业务侧只想发文字。

### 14.2 外部 TTS 直接推音频驱动数字人

```text
控制端
  -> POST /tts/task/start
TTS
  -> WS /alpha/input/audio
LiveTalking
  -> WS /alpha/ws 输出视频
显示端
  -> 渲染视频
```

适合：业务侧已有 TTS 流，或者 TTS 和指令由其他模块统一管理。

### 14.3 本机 PPT 透明置顶显示

```text
LiveTalking 机器
  -> 开启 --alpha_output
PPT/显示机器
  -> Electron overlay 连接 ws://<LiveTalking>/alpha/ws
```

同机推荐 `format=raw`；跨机器可根据带宽改用 `jpeg` 预览或 `webp` 透明压缩。

### 14.4 远程浏览器透明显示

```text
浏览器
  -> POST /alpha/webrtc/packed_offer
LiveTalking
  -> WebRTC audio + packed video
浏览器
  -> 拆 packed frame 并合成透明画面
```

VSCode 单端口转发更适合 `/alpha/ws`，WebRTC 远程通常需要可达网络、正确 ICE，必要时要 TURN。

## 15. 代码位置对照

| 功能 | 文件 |
| --- | --- |
| 主服务启动、路由注册 | `app.py` |
| HTTP JSON / alpha WebSocket 输入路由 | `server/routes.py` |
| alpha 视频/音频输出 WebSocket | `server/alpha_stream.py` |
| WebRTC offer/answer | `server/rtc_manager.py` |
| packed/double-track alpha WebRTC track | `server/alpha_webrtc.py` |
| session 管理 | `server/session_manager.py` |
| robottts 插件 | `tts/robottts.py` |
| 测试 TTS 服务 | `testclient/backend/robottts_test_server.py` |
| Web 测试客户端 | `testclient/web/src/main.jsx` |
| Electron overlay | `testclient/overlay/` |
