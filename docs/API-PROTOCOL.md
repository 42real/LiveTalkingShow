# LiveTalking 接口协议

当前接口由 `aiohttp.web` 提供，协议包含 HTTP JSON、multipart、WebSocket 二进制流和 WebRTC SDP offer/answer。

默认地址：

```text
LiveTalking  http://127.0.0.1:8050
TTS          http://127.0.0.1:8036
```

LiveTalking JSON 响应：

```json
{"code": 0, "msg": "ok", "data": {}}
```

TTS 测试服务响应使用 `success`、`error`、`message` 等字段，见第 8 节。

## 1. 主服务接口

| 方法 | 路径 | 类型 | 作用 |
| --- | --- | --- | --- |
| `POST` | `/alpha/session` | JSON | 创建或复用 alpha session。 |
| `POST` | `/alpha/speak` | JSON | 输入文字，LiveTalking 调 TTS 后驱动数字人。 |
| `GET` | `/alpha/ws` | WebSocket binary | 输出 alpha 视频帧。 |
| `GET` | `/alpha/audio` | WebSocket binary | 输出音频 PCM16。 |
| `GET` | `/alpha/input/audio` | WebSocket JSON + binary | 接收外部 TTS 推来的 PCM 音频。 |
| `POST` | `/alpha/close` | JSON | 关闭 alpha session。 |
| `GET/POST` | `/alpha/tuning` | JSON | 查询或调整 Wav2Lip 贴回区域。 |
| `POST` | `/alpha/webrtc/packed_offer` | WebRTC JSON | 单视频轨 packed color+alpha 透明输出。 |
| `POST` | `/alpha/webrtc/offer` | WebRTC JSON | 双视频轨 color/alpha 输出。 |
| `POST` | `/offer` | WebRTC JSON | 普通 WebRTC 音视频输出。 |
| `POST` | `/human` | JSON | legacy 文本输入。 |
| `POST` | `/humanaudio` | multipart | legacy 音频文件输入。 |
| `POST` | `/interrupt_talk` | JSON | 打断朗读。 |
| `POST` | `/is_speaking` | JSON | 查询是否正在说话。 |
| `POST` | `/record` | JSON | 开始或结束录制。 |
| `GET` | `/record/{sessionid}` | file | 下载录制 MP4。 |
| `GET` | `/api/admin/config` | JSON | 查看运行配置。 |
| `GET` | `/api/admin/sessions` | JSON | 查看 session 状态。 |
| `POST` | `/api/avatar/task` | JSON/multipart | 创建 avatar 制作任务。 |
| `GET` | `/api/avatar/task/{task_id}` | JSON | 查询 avatar 任务。 |
| `DELETE` | `/api/avatar/task/{task_id}` | JSON | 删除 avatar 任务。 |
| `GET` | `/api/avatar/tasks` | JSON | 列出 avatar 任务。 |

## 2. alpha session

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

`session.avatar` 对应 `data/avatars/<avatar_id>`。也可以把 `avatar`、`refaudio`、`reftext`、`custom_config` 直接放在请求顶层。

## 3. 文本驱动

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

| 字段 | 说明 |
| --- | --- |
| `text` | 要朗读的文本，必填。 |
| `type` | `echo` 直接朗读；`chat` 走 `llm_response`。 |
| `interrupt` | 是否先打断当前朗读。 |
| `tts.voice_id` | TTS 音色 ID。 |
| `tts.mode` | TTS 模式，例如 `instruct2`。 |
| `tts.prompts` | TTS 指令或提示词。 |

链路：

```text
控制端 -> POST /alpha/speak
LiveTalking -> WS /tts/ws
TTS -> PCM16 chunks
LiveTalking -> /alpha/ws 视频
```

## 4. 外部音频流驱动

```http
GET /alpha/input/audio
Upgrade: websocket
```

流程：

```text
TTS -> LiveTalking TEXT JSON start
LiveTalking -> TTS TEXT JSON started
TTS -> LiveTalking BINARY PCM chunks
TTS -> LiveTalking TEXT JSON end
```

start：

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

started：

```json
{
  "type": "started",
  "task_id": "demo-001",
  "sessionid": "123456"
}
```

binary：

```text
PCM16 little-endian，推荐 16000 Hz / mono / signed 16-bit
```

end：

```json
{
  "type": "end",
  "task_id": "demo-001",
  "reason": "completed"
}
```

## 5. alpha 视频和音频输出

```text
WS /alpha/ws?max_height=720&fps=25&format=jpeg&quality=80
WS /alpha/audio
```

`/alpha/ws` query：

| 参数 | 取值 | 说明 |
| --- | --- | --- |
| `max_width` | `0-4096` | 当前客户端最大宽度，`0` 不限制。 |
| `max_height` | `0-4096` | 当前客户端最大高度，`0` 不限制。 |
| `fps` | `0-60` | 当前客户端帧率限制，`0` 不限制。 |
| `format` | `raw` / `jpeg` / `png` / `webp` | 视频帧编码。 |
| `quality` | `1-100` | `jpeg` / `webp` 质量。 |

每条视频 binary message：

```text
24 byte little-endian header + payload
```

header：

| 字节 | 类型 | 含义 |
| --- | --- | --- |
| `0-3` | `char[4]` | `LTAF` |
| `4` | `uint8` | version，当前 `1` |
| `5` | `uint8` | `1=raw RGBA8`，`2=JPEG`，`3=PNG`，`4=WebP` |
| `6-7` | `uint16` | flags，当前 `0` |
| `8-11` | `uint32` | width |
| `12-15` | `uint32` | height |
| `16-23` | `uint64` | seq |

payload：

| format | payload |
| --- | --- |
| `raw` | `RGBA8`，每像素 `R,G,B,A` 4 字节。 |
| `jpeg` | JPEG 图片字节，适合远程预览。 |
| `png` | PNG 图片字节，可保留透明。 |
| `webp` | WebP 图片字节，可保留透明。 |

`/alpha/audio` 输出：

```text
WebSocket binary PCM16 chunks，16000 Hz mono
```

## 6. WebRTC 输出

普通 WebRTC：

```http
POST /offer
```

请求：

```json
{"sdp": "v=0...", "type": "offer"}
```

返回：

```json
{"sdp": "v=0...", "type": "answer", "sessionid": "123456"}
```

packed alpha WebRTC：

```http
POST /alpha/webrtc/packed_offer
```

客户端 transceiver 顺序：

```text
audio recvonly
video recvonly
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

packed 视频一帧分左右两半：

```text
left  = color
right = alpha mask
```

双轨 alpha WebRTC：

```http
POST /alpha/webrtc/offer
```

客户端 transceiver 顺序：

```text
audio recvonly
video recvonly  color
video recvonly  alpha mask
```

## 7. avatar 任务

创建：

```http
POST /api/avatar/task
Content-Type: application/json
```

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

上传视频时使用 `multipart/form-data`，字段为 `video_file`。

常用参数：

| 参数 | 说明 |
| --- | --- |
| `model` | `wav2lip` / `musetalk` / `ultralight`。 |
| `avatar_id` | 输出目录名。 |
| `video_path` / `video_file` | 本地路径或上传文件。 |
| `img_size` | Wav2Lip 裁剪尺寸。 |
| `pads` | Wav2Lip 人脸框边距，顺序 `top bottom left right`。 |
| `bbox_shift` | MuseTalk 人脸框偏移。 |
| `extra_margin` | MuseTalk mask 额外边距。 |
| `parsing_mode` | MuseTalk mask 模式，例如 `jaw`。 |
| `version` | MuseTalk 版本，例如 `v15`。 |

查询：

```text
GET /api/avatar/task/{task_id}
GET /api/avatar/tasks
DELETE /api/avatar/task/{task_id}
```

## 8. robottts 兼容 TTS

LiveTalking `--tts robottts` 使用这组接口。

| 方法 | 路径 | 类型 | 作用 |
| --- | --- | --- | --- |
| `GET` | `/health` | JSON | 健康检查和音频格式。 |
| `GET` | `/tts/voices` | JSON | 音色列表。 |
| `POST` | `/tts` | JSON | 一次性合成 wav，测试用。 |
| `GET` | `/tts/ws` | WebSocket JSON + binary | LiveTalking 内部流式 TTS。 |
| `POST` | `/tts/task/start` | JSON | 创建任务并主动推音频到 LiveTalking。 |
| `POST` | `/tts/task/cancel` | JSON | 取消任务。 |
| `GET` | `/tts/task/status?task_id=...` | JSON | 查询任务。 |

`GET /health`：

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

`WS /tts/ws` 流程：

```text
LiveTalking -> {"action":"start","voice_id":0,"mode":"instruct2","prompts":"..."}
TTS -> {"action":"started"}
LiveTalking -> {"action":"text","text":"你好"}
TTS -> binary PCM16 chunks
TTS -> {"action":"result","type":"final","meta":{...}}
LiveTalking -> {"action":"end"}
```

`POST /tts/task/start`：

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
{"success": true, "task_id": "demo-001", "state": "submitted"}
```

## 9. 代码位置

| 功能 | 文件 |
| --- | --- |
| 主服务启动 | `app.py` |
| HTTP/alpha 路由 | `server/routes.py` |
| alpha WebSocket 输出 | `server/alpha_stream.py` |
| WebRTC | `server/rtc_manager.py`、`server/alpha_webrtc.py` |
| session 管理 | `server/session_manager.py` |
| robottts 插件 | `tts/robottts.py` |
| 测试 TTS | `testclient/backend/robottts_test_server.py` |
| Web 测试页 | `testclient/web/src/main.jsx` |
| Electron overlay | `testclient/overlay/` |
