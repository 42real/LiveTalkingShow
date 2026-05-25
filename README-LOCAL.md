# LiveTalking 本地使用说明

本文档同时保留本机调试记录和迁移交接说明。命令默认从仓库根目录执行；迁移到新机器时先进入新的仓库目录即可，不需要额外设置项目 home 环境变量。

```bash
cd /path/to/LiveTalking
```

运行变量只保留服务地址、端口和 avatar 名称：

```bash
export TTS_SERVER_URL=http://127.0.0.1:8036
export LIVETALKING_URL=http://127.0.0.1:8050
export LIVETALKING_WS_URL=ws://127.0.0.1:8050
export LIVETALKING_PORT=8050
export AVATAR_ID=default_calm_1
```

适用场景：

- 使用 `uv` 虚拟环境
- 默认以 `wav2lip` 为稳定运行方案
- 真实 TTS 服务使用 `robottts` 兼容 API；百炼和 EdgeTTS 测试服务放在 `testclient` 内部单独管理
- 透明桌面助手通过 alpha raw RGBA 输出链路显示

## 1. 本地部署状态

本机已就位的关键资源相对仓库根目录如下：

- 虚拟环境：`.venv`
- 模型文件：`models/wav2lip.pth`
- 本机默认运行样例：`data/avatars/default_calm_1`，该目录不进 Git，需要单独准备
- 其他 avatar 目录：`data/avatars/<avatar_id>`
- 离线样片：`data/record.mp4`

说明：

- 当前运行样例使用 `AVATAR_ID=default_calm_1`，但 avatar 素材目录不进入 Git。
- 需要切换数字人时，用 `AVATAR_ID` 指定实际要加载的 avatar，不在命令里写死某个本机路径。
- 已修复朗读模式下 `face_imgs` 尺寸不一致导致的 batch 报错。
- 新环境交接时优先看第 19 节，前面章节包含模块说明和历史排错说明。

## 1.1 这套程序是什么

LiveTalking 不是单一模型，而是一个数字人实时播报服务：

- 输入文本或音频
- TTS 生成语音
- avatar 模型根据语音驱动嘴型
- 输出到浏览器、RTMP 或虚拟摄像头

核心特点是“插件化”：

- avatar 可换
- TTS 可换
- 输出方式可换
- 朗读、聊天、音频驱动都可以走同一套后端

## 2. 启动要求

建议在启动前确认：

- 机器有 NVIDIA GPU
- `uv` 可用
- `.venv` 已存在
- `models/wav2lip.pth` 已存在
- `data/avatars/$AVATAR_ID` 已存在
- 目标端口未被占用

推荐服务端口：

- `$LIVETALKING_PORT`，当前示例为 `8050`

说明：

- 原 README 默认是 `8010`
- 当前桌面助手链路统一建议使用 `8050` 或更高端口

## 3. 前台启动

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --listenport "$LIVETALKING_PORT"
```

如果你不需要 Hugging Face 下载，可保留这个环境变量不动；它对当前已经下好的模型没有副作用。

## 4. 后台启动

```bash
cd /path/to/LiveTalking
nohup env HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --listenport "$LIVETALKING_PORT" > "livetalking-${LIVETALKING_PORT}.log" 2>&1 &
```

## 5. 访问地址

启动成功后可访问：

- `$LIVETALKING_URL/webrtcapi.html`
- `$LIVETALKING_URL/dashboard.html`

推荐先试：

- `$LIVETALKING_URL/webrtcapi.html`

## 6. 页面使用方法

### 6.1 文本朗读

1. 打开 `webrtcapi.html`
2. 点击 `start`
3. 等待视频区域初始化
4. 在输入框中输入文本
5. 提交后让数字人播报

### 6.2 上传音频

如果页面或接口支持上传音频，可将音频直接提交给后端进行驱动。

当前项目中后端接口包含：

- `/offer`
- `/human`
- `/humanaudio`
- `/interrupt_talk`
- `/is_speaking`

### 6.3 运行模式

### echo

- 作用：直接朗读你输入的文本
- 需要：TTS、avatar、输出通道
- 效果：最快，适合测试播报链路

### chat

- 作用：先调用大模型生成回复，再让数字人说出来
- 需要：`DASHSCOPE_API_KEY`
- 当前实现：`llm.py` 里接的是 Qwen 的兼容 OpenAI 接口
- 效果：更像问答助手，但比 echo 多一层延迟

## 7. 停止服务

### 7.1 前台运行

直接按：

```bash
Ctrl+C
```

### 7.2 后台运行

先查进程：

```bash
pgrep -af 'python app.py.*--transport webrtc'
```

再结束：

```bash
kill <PID>
```

如果有外层 `uv` 进程，也可以一起结束。

## 8. 查看日志

后台日志文件：

- `livetalking-${LIVETALKING_PORT}.log`

实时查看：

```bash
tail -f "livetalking-${LIVETALKING_PORT}.log"
```

## 9. 常见问题

### 9.1 端口被占用

如果 `$LIVETALKING_PORT` 被占用，可以换端口，例如：

```bash
cd /path/to/LiveTalking
export LIVETALKING_PORT=8051
export LIVETALKING_URL=http://127.0.0.1:8051
export LIVETALKING_WS_URL=ws://127.0.0.1:8051
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --listenport "$LIVETALKING_PORT"
```

对应访问：

- `$LIVETALKING_URL/webrtcapi.html`

### 9.2 朗读模式报错：`ValueError: setting an array element with a sequence`

这个问题已经修复，根因是：

- 某些 avatar 的 `face_imgs` 尺寸不一致。
- `wav2lip` 在推理时直接将一批人脸图拼成 numpy 数组。
- 尺寸不一致会导致 batch 组装失败。

当前修复方式：

- 在 `avatars/wav2lip_avatar.py` 中，推理前统一缩放每张人脸图到固定尺寸 `256x256`


## 10. 模块说明

### 10.1 Avatar 模块

由 `--model` 指定，当前代码里可选：

#### `wav2lip`

- 入口文件：`avatars/wav2lip_avatar.py`
- 视觉效果：经典口型驱动，稳定、轻量
- 适合：实时播报、朗读模式
- 需要：
  - `models/wav2lip.pth`
  - `data/avatars/<avatar_id>/full_imgs`
  - `data/avatars/<avatar_id>/face_imgs`
  - `data/avatars/<avatar_id>/coords.pkl`
- 特点：
  - 对 avatar 素材要求比较固定
  - 速度相对快
  - 当前建议作为稳定迁移方案优先使用

#### `musetalk`

- 入口文件：`avatars/musetalk_avatar.py`
- 视觉效果：更偏“高质量嘴部融合”
- 适合：更自然的口型和贴图效果
- 需要：
  - `models/musetalkV15/unet.pth`
  - `models/whisper/*`
  - `data/avatars/<avatar_id>/full_imgs`
  - `data/avatars/<avatar_id>/mask`
  - `data/avatars/<avatar_id>/coords.pkl`
  - `data/avatars/<avatar_id>/mask_coords.pkl`
  - `data/avatars/<avatar_id>/latents.pt`
- 特点：
  - 资源要求更高
  - 预处理和素材要求更多
  - 生成质量通常比纯 `wav2lip` 更细

#### `ultralight`

- 入口文件：`avatars/ultralight_avatar.py`
- 视觉效果：轻量、快速
- 适合：低资源场景、快速测试
- 需要：
  - `data/avatars/<avatar_id>/face_imgs`
  - `data/avatars/<avatar_id>/coords.pkl`
  - `data/avatars/<avatar_id>/ultralight.pth`
  - `transformers` 里的 Hubert/Wav2Vec2 相关组件
- 特点：
  - 速度和资源占用更友好
  - 效果一般比高质量 musetalk 更轻

### 10.2 TTS 模块

由 `--tts` 指定，当前代码里可选：

#### `edgetts`

- 文件：`tts/edge.py`
- 作用：LiveTalking 上游自带的直接 Edge TTS 插件
- 当前定位：
  - 不作为迁移交接主链路
  - 测试时优先使用 `testclient/backend/robottts_test_server.py`，它把 EdgeTTS 包成 `robottts` 兼容服务
- 原因：
  - 生产和测试都统一走 `--tts robottts --TTS_SERVER "$TTS_SERVER_URL"`
  - 这样真实 `robot-tts`、百炼测试服务、EdgeTTS 测试服务可以互换，LiveTalking 启动命令不变

#### `gpt-sovits`

- 文件：`tts/sovits.py`
- 作用：请求外部 GPT-SoVITS 服务
- 需要：
  - `--TTS_SERVER` 指向可用的 GPT-SoVITS 服务
  - `--REF_FILE` / `--REF_TEXT` 提供参考音色信息
- 效果：
  - 可做音色克隆
  - 更适合有固定声音样本的场景

#### `cosyvoice`

- 文件：`tts/cosyvoice.py`
- 作用：请求外部 CosyVoice 服务
- 需要：
  - `--TTS_SERVER`
  - 参考音色/文本配置
- 效果：
  - 适合高自然度语音
  - 通常要配套自己的 CosyVoice 服务

#### `fishtts`

- 文件：`tts/fish.py`
- 作用：请求外部 FishSpeech/FishTTS 服务
- 需要：
  - `--TTS_SERVER`
  - 参考音色配置
- 效果：
  - 偏音色克隆路线

#### `xtts`

- 文件：`tts/xtts.py`
- 作用：请求外部 XTTS 服务
- 需要：
  - `--TTS_SERVER`
  - speaker/音色配置
- 效果：
  - 支持更偏克隆式的播报

#### `tencent`

- 文件：`tts/tencent.py`
- 作用：调用腾讯 TTS
- 需要：
  - 腾讯相关账号/密钥配置
  - 网络可用
- 效果：
  - 商业云 TTS 风格

#### `doubao`

- 文件：`tts/doubao.py`
- 作用：调用火山/豆包相关音频服务
- 需要：
  - 对应平台账号和配置
- 效果：
  - 云端语音合成

#### `azuretts`

- 文件：`tts/azure.py`
- 作用：调用 Azure Speech
- 需要：
  - Azure 语音服务配置
  - 相关 SDK
- 效果：
  - 云端 TTS

#### `indextts2`

- 文件：`tts/indextts2.py`
- 作用：外部 IndexTTS2 服务
- 需要：
  - `--TTS_SERVER`
  - 参考音频 `--REF_FILE`
- 效果：
  - 偏音色参考驱动

#### `qwentts`

- 文件：`tts/qwentts.py`
- 作用：调用通义千问 TTS
- 需要：
  - `DASHSCOPE_API_KEY`
  - 可选 `--qwen_tts_model`
  - `--REF_FILE` 作为音色名
- 效果：
  - 云端实时 TTS
  - 当前代码默认 voice 是 `REF_FILE`

#### `robottts`

- 文件：`tts/robottts.py`
- 作用：把 `LiveTalking` 接到外部 `robot-tts` WebSocket 流式语音服务
- 需要：
  - 一个 `robottts` 兼容服务已经启动
  - `--TTS_SERVER` 指向 `robottts` 兼容服务地址，建议用 `$TTS_SERVER_URL` 统一配置
  - 服务输出需保持为 `16kHz / mono / 16-bit PCM`
- 参数映射：
  - `tts.voice_id` 或 `tts.ref_file` -> `robottts` 协议的 `voice_id`
  - `tts.prompts` 或 `tts.ref_text` -> `robottts` 协议的 `prompts`
  - `tts.mode` -> `robottts` 协议的 `mode`
- 效果：
  - 真正按流式 PCM 驱动数字人说话
  - 不需要先生成整段 wav 再上传
  - 更适合接你现有的 TTS 服务
- 备注：
  - `ref_file` 如果传整数或可转成整数，会直接当 `voice_id`
  - `ref_file` 如果传的是 voice 名称，插件会尝试读取 `/tts/voices` 做名称到 `voice_id` 的映射
  - `LiveTalking` 内部推理仍按 `20ms` 一帧消费音频；`robot-tts` 默认 `40ms` 一块输出，插件会自动拆成两个 `20ms` 帧

### 10.3 输出模块

由 `--transport` 指定，当前代码里可选：

#### `webrtc`

- 文件：`streamout/webrtc.py`
- 作用：浏览器直接收音视频
- 需要：
  - 浏览器支持 WebRTC
  - 服务端 `$LIVETALKING_PORT` 或你指定端口可访问
- 效果：
  - 最适合交互式实时使用
  - 延迟最低

#### `rtmp`

- 文件：`streamout/rtmp.py`
- 作用：推到 RTMP/SRS 一类服务
- 需要：
  - 可用的 RTMP/WHIP 推流服务
  - `--push_url`
- 效果：
  - 适合直播平台转推

#### `rtcpush`

- 文件：`server/rtc_manager.py` + `streamout/webrtc.py`
- 作用：服务端主动推流到指定 `push_url`
- 需要：
  - `--push_url`
  - 目标 WHIP/RTC 接收端
- 效果：
  - 适合自动推流

#### `virtualcam`

- 文件：`streamout/virtualcam.py`
- 作用：输出到系统虚拟摄像头
- 需要：
  - `pyvirtualcam`
  - 通常还要配合音频输出
- 效果：
  - 能被其他软件当摄像头使用

### 10.4 聊天/LLM 模块

#### `chat`

- 文件：`llm.py`
- 作用：把用户文本发给大模型，再把回复切句送给 TTS
- 需要：
  - `DASHSCOPE_API_KEY`
  - 可访问 DashScope
- 效果：
  - 更像“会回答问题的数字人”
  - 比 `echo` 更慢

### 10.5 路由接口

后端接口在 `server/routes.py`，常用的是：

- `/human`：发文本
- `/humanaudio`：发音频文件
- `/interrupt_talk`：打断当前说话
- `/is_speaking`：查询是否在说话

## 11. 自定义数字人和模型制作

这里要先区分两个概念：

- 制作 avatar：把你自己的视频预处理成 LiveTalking 能加载的素材目录
- 训练模型权重：重新训练 `.pth` 这类模型文件

在当前这份本地代码里：

- `wav2lip`：通常只制作 avatar，不重新训练 `wav2lip.pth`
- `musetalk`：通常只制作 avatar，不重新训练 MuseTalk 主模型
- `ultralight`：需要你先训练自己的 `ultralight.pth`
- `ER-NeRF`：官方文档提到过，但当前本地代码没有接入 `ernerf` 入口，不能直接按当前 `app.py` 跑

### 11.1 制作 `wav2lip` avatar

`wav2lip` 是当前最容易做通的方式。它使用通用模型：

- `models/wav2lip.pth`

你要准备的是一段闭嘴、不说话的视频；当前本地 `avatars.wav2lip.genavatar`
也支持单张图片和图片目录，虽然参数名仍叫 `--video_path`。

建议素材条件：

- 单人
- 正脸或接近正脸
- 嘴部无遮挡
- 光线稳定
- 画面中脸部不要出框
- 尽量使用 25fps；30fps 也能处理，但项目默认推理节奏是 25fps
- 单张图片可以做 avatar，但只有嘴部变化，身体、头部和眨眼不会动

`--video_path` 可输入：

- 单张图片：`.png`、`.jpg`、`.jpeg`、`.webp`、`.bmp`
- 图片目录：目录内图片按文件名排序导入
- 视频：`.mp4`、`.mov`、`.avi`、`.mkv`、`.webm`

制作命令：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/source_silent_video.mp4 \
  --img_size 256 \
  --avatar_id my_avatar
```

用单张图片制作 avatar：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/person.png \
  --img_size 256 \
  --avatar_id my_image_avatar
```

生成目录结构：

```text
data/avatars/<avatar_id>/
  full_imgs/
  face_imgs/
  coords.pkl
```

运行：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --listenport "$LIVETALKING_PORT"
```

如果你要换名字，例如 `my_avatar`：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/your_silent_video.mp4 \
  --img_size 256 \
  --avatar_id my_avatar
```

然后启动时用：

```bash
--model wav2lip --avatar_id my_avatar
```

`wav2lip.genavatar` 参数说明：

```text
--video_path
  输入素材路径。可填单张图片、图片目录或视频文件。
  图片格式：png/jpg/jpeg/webp/bmp。
  视频格式：mp4/mov/avi/mkv/webm。
  必填；如果路径不存在或格式不支持会报错。

--avatar_id
  输出 avatar 名称，最终目录是 data/avatars/<avatar_id>。
  建议只用英文、数字、下划线、短横线。
  如果目录已存在，脚本不会自动清理旧文件，最好先备份或删除旧目录。

--img_size
  人脸裁剪图尺寸，生成 face_imgs/<frame>.png 时会 resize 成 img_size x img_size。
  它不是最终显示尺寸；最终显示尺寸来自 full_imgs 里的原图/视频帧。
  当前本地 wav2lip 推理按 256x256 人脸输入处理，推荐固定用 256。
  合理范围一般是 96 到 256；不要随意改成很大，显存和预处理耗时会上升，且模型不一定受益。

--pads top bottom left right
  人脸检测框的额外边距，单位是像素，顺序是上、下、左、右。
  默认是 0 10 0 0，也就是下方多保留 10 像素，通常用于包含下巴。
  常用范围是 0 到 50。图片越大可适当加大，过大可能把背景带进嘴部区域。
  如果嘴唇、下巴被裁掉，可尝试 --pads 0 20 0 0 或 --pads 10 30 10 10。

--nosmooth
  关闭人脸框平滑。默认不开启，即默认会对连续帧的人脸框做平滑。
  视频素材一般保持默认；单张图片开不开没有明显区别。

--face_det_batch_size
  人脸检测批大小，默认 16。
  显存够可以保持 16；如果人脸检测 OOM，脚本会自动降低，也可以手动设 8、4、1。
```

常用命令：

```bash
# 从单张透明 PNG 制作 avatar
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/person.png \
  --img_size 256 \
  --avatar_id my_image_avatar

# 从视频制作 avatar
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/your_silent_video.mp4 \
  --img_size 256 \
  --avatar_id my_video_avatar

# 下巴裁剪不完整时增加边距
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/person.png \
  --img_size 256 \
  --pads 0 20 0 0 \
  --avatar_id my_padded_avatar

# 启动 WebRTC 页面模式
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --listenport "$LIVETALKING_PORT"

# 启动透明 alpha 桌面助手模式
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
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

### 11.2 制作 `musetalk` avatar

`musetalk` 的视觉融合效果通常更好，但预处理更重。

你要准备：

- 一段闭嘴、不说话的视频，或一组图片
- MuseTalk 相关模型文件
- Whisper 模型文件
- 生成 avatar 时所需的人脸检测、姿态、分割依赖

当前本地代码加载时需要：

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
  --file /path/to/your_silent_video.mp4 \
  --avatar_id my_musetalk_avatar \
  --version v15 \
  --bbox_shift 0 \
  --extra_margin 10 \
  --parsing_mode jaw
```

运行：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model musetalk \
  --avatar_id my_musetalk_avatar \
  --listenport "$LIVETALKING_PORT"
```

常见调参：

- `--bbox_shift`：嘴部区域上下偏移，嘴型贴合不准时优先调它
- `--extra_margin`：脸部裁剪额外边距
- `--parsing_mode jaw`：偏下颌区域融合，适合说话口型

如果生成失败，优先检查：

- 人脸是否每一帧都能被检测到
- 视频中是否有遮挡、转头、低光
- MuseTalk、Whisper、face parsing 相关模型是否都在位

### 11.3 制作 `ultralight` avatar

`ultralight` 不是只靠素材预处理。当前本地代码会从 avatar 目录加载：

```text
data/avatars/<avatar_id>/ultralight.pth
```

也就是说，你需要先按上游 `Ultralight-Digital-Human` 项目训练出自己的 checkpoint。

典型流程：

1. 准备训练视频和音频
2. 用上游项目预处理数据
3. 训练 syncnet
4. 训练数字人模型
5. 拿到训练好的 checkpoint
6. 回到 LiveTalking 生成 avatar 目录

LiveTalking 侧生成目录的命令：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.ultralight.genavatar \
  --video_path /path/to/your_silent_video.mp4 \
  --avatar_id my_ultralight_avatar \
  --checkpoint /path/to/your_trained_ultralight_checkpoint.pth
```

生成目录：

```text
data/avatars/my_ultralight_avatar/
  full_imgs/
  face_imgs/
  coords.pkl
  ultralight.pth
```

运行：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model ultralight \
  --avatar_id my_ultralight_avatar \
  --listenport "$LIVETALKING_PORT"
```

训练数据建议：

- 语音干净，少噪声，少回音
- 正脸或小幅动作
- 嘴部无遮挡
- 视频里人脸稳定
- 训练和最终静默素材尽量同一个人、同一机位、同一画面风格

### 11.4 `ER-NeRF`

官方文档提到过 `ER-NeRF`，但当前本地代码没有：

- `avatars/ernerf_avatar.py`
- `app.py` 里的 `ernerf` 模型映射
- `config.py` 里的 `ernerf` 运行说明

所以当前这份本地部署不能直接用：

```bash
--model ernerf
```

如果后续要做 `ER-NeRF`，需要切到官方对应分支或单独集成该模型，再按 ER-NeRF 上游流程训练并导入数据。

## 12. 外接 TTS 服务方法

当前推荐的外接方式是使用 `--tts robottts`。

它不是特指某个本地项目目录，而是一个通用桥接插件。只要外部 TTS 服务实现相同协议，LiveTalking 就能接。

### 12.1 `robottts` 需要的服务协议

服务端需要提供：

- `GET /health`
- `GET /tts/voices`
- `WS /tts/ws`

`/tts/voices` 返回：

```json
{
  "voices": [
    {"id": 0, "name": "default", "description": "default"}
  ]
}
```

WebSocket 流程：

1. LiveTalking 连接：

```text
ws://<host>:<port>/tts/ws
```

2. LiveTalking 发送 start：

```json
{
  "action": "start",
  "voice_id": 0,
  "prompts": "请自然朗读，停顿清楚。",
  "mode": "instruct2"
}
```

3. TTS 服务返回：

```json
{"action": "started"}
```

4. LiveTalking 发送文本：

```json
{
  "action": "text",
  "text": "你好，这是数字人朗读测试。"
}
```

5. TTS 服务连续返回二进制 PCM 音频：

```text
16kHz / mono / signed 16-bit little-endian PCM
```

6. 结束时返回：

```json
{
  "action": "result",
  "type": "final",
  "meta": {
    "sample_rate": 16000,
    "channels": 1,
    "sample_width": 2
  }
}
```

LiveTalking 内部会把 PCM 拆成：

```text
20ms 一帧 = 320 samples = 640 bytes
```

如果外部 TTS 一次返回 40ms，也可以，`robottts` 插件会自动拆帧。

### 12.2 robottts 兼容服务

LiveTalking 的统一启动方式固定为：

```bash
--tts robottts --TTS_SERVER "$TTS_SERVER_URL"
```

后端 TTS 可以替换，只要符合下面接口：

- `WS /tts/ws`
- `GET /health`
- `GET /tts/voices`
- `POST /tts`
- `POST /tts/task/start`
- 输出 `16kHz / mono / signed 16-bit PCM`
- 推荐 `chunk_ms=40`，LiveTalking 内部会拆成 `20ms` 帧

可选实现：

- 真实业务服务：任意已经启动的 `robottts` 兼容 HTTP/WebSocket 服务
- testclient 后端 EdgeTTS 测试服务：`/path/to/LiveTalking/testclient/start-tts.sh`
- testclient 后端百炼测试服务：`TEST_TTS_PROVIDER=bailian /path/to/LiveTalking/testclient/start-tts.sh`

真实业务服务启动：

```bash
cd /path/to/robot-tts
HF_ENDPOINT=https://hf-mirror.com uv run python -m tts_service.main
```

testclient EdgeTTS 测试服务启动：

```bash
cd /path/to/LiveTalking/testclient
TEST_TTS_PROVIDER=edge ./start-tts.sh
```

LiveTalking 启动：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --tts robottts \
  --TTS_SERVER "$TTS_SERVER_URL" \
  --robottts_mode instruct2 \
  --listenport "$LIVETALKING_PORT"
```

如果 `robot-tts` 跑在另一台机器：

```bash
export TTS_SERVER_URL=http://<ip>:8036
```

### 12.3 百炼 CosyVoice 作为 robottts 测试实现

百炼不是另一条 LiveTalking 接入方式，而是 `testclient/backend` 的一个 provider：

```text
testclient/backend/robottts_test_server.py
```

它的作用是：

- 对外提供同样的 `robottts` 兼容协议
- `TEST_TTS_PROVIDER=bailian` 时内部调用阿里云百炼 CosyVoice v3 在线 WebSocket 服务
- 默认监听 `8036`
- 默认输出 `16kHz / mono / PCM`

启动：

```bash
cd /path/to/LiveTalking/testclient
TEST_TTS_PROVIDER=bailian DASHSCOPE_API_KEY=你的百炼APIKey ./start-tts.sh
```

检查：

```bash
curl "$TTS_SERVER_URL/health"
curl "$TTS_SERVER_URL/tts/voices"
```

LiveTalking 启动命令和其他 `robottts` 兼容服务完全相同：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --tts robottts \
  --TTS_SERVER "$TTS_SERVER_URL" \
  --robottts_mode instruct2 \
  --listenport "$LIVETALKING_PORT"
```

百炼服务参数：

- `DASHSCOPE_API_KEY`：百炼 API Key，必须设置
- `BAILIAN_COSYVOICE_MODEL`：默认 `cosyvoice-v3-flash`
- `BAILIAN_VOICES`：用逗号覆盖内置音色列表
- `BAILIAN_INSTRUCTION_FIELD`：默认 `instructions`，如果接口报字段问题可改为 `instruction`
- `BAILIAN_USE_PROMPTS_AS_INSTRUCTIONS=0`：关闭 `prompts` 到百炼指令字段的映射

### 12.4 LiveTalking 请求参数怎么传给外部 TTS

调用 `/human` 时可以带：

```json
{
  "tts": {
    "voice_id": 0,
    "prompts": "请自然朗读，停顿清楚。",
    "mode": "instruct2"
  }
}
```

也可以沿用 LiveTalking 老字段：

```json
{
  "tts": {
    "ref_file": "0",
    "ref_text": "请自然朗读，停顿清楚。",
    "mode": "instruct2"
  }
}
```

映射关系：

- `voice_id` 或 `ref_file` -> 外部服务的 `voice_id`
- `prompts` 或 `ref_text` -> 外部服务的 `prompts`
- `mode` -> 外部服务的 `mode`

示例：

```bash
curl -X POST "$LIVETALKING_URL/human" \
  -H 'Content-Type: application/json' \
  -d '{
    "sessionid": "0",
    "type": "echo",
    "interrupt": true,
    "text": "你好，这是通过外部 TTS 服务驱动的数字人朗读测试。",
    "tts": {
      "voice_id": 0,
      "prompts": "请自然朗读，停顿清楚。",
      "mode": "instruct2"
    }
  }'
```

注意：

- `webrtc` 模式下必须先打开页面并建立会话，否则 `/human` 会返回 `session not found`
- 自带 `dashboard.html` 目前没有 `voice_id/prompts/mode` 输入框
- 如果要在页面上切换音色和提示词，需要后续改前端表单

### 12.5 接其他 TTS 服务

如果你要接别的在线服务，例如 GPT-SoVITS、Fish、豆包、Azure、腾讯，原则上有两种做法：

1. 使用 LiveTalking 已有 TTS 插件
   例如 `--tts gpt-sovits`、`--tts fishtts`、`--tts doubao`。

2. 写一个小适配服务，实现 `robottts` 协议
   推荐这种方式，尤其是你想保持 LiveTalking 主程序少改代码时。

适配服务最关键的是：

- 输入 WebSocket JSON
- 调上游 TTS
- 把上游音频转成 `16kHz mono s16le PCM`
- 以二进制消息流式返回

只要做到这一点，LiveTalking 不关心后面到底是本地模型、百炼、火山、Azure，还是你自己的服务。

## 13. 各模块搭配建议

### 最省事

- `--model wav2lip`
- `--tts robottts`
- `--transport webrtc`
- 后端 TTS 用 `testclient` EdgeTTS 测试服务：`cd /path/to/LiveTalking/testclient && ./start-tts.sh`

特点：

- 安装最少
- 最快能看到效果
- 适合测试

### 更自然

- `--model musetalk`
- `--tts cosyvoice` 或 `gpt-sovits`
- `--transport webrtc`

特点：

- 画面和声音都更偏高质量
- 但需要更多模型和外部服务

### 更轻量

- `--model ultralight`
- `--tts robottts`
- `--transport webrtc`
- 后端 TTS 用 `testclient` EdgeTTS 测试服务

特点：

- 更省资源
- 适合轻量测试和快速响应

### 直播/推流

- `--transport rtmp` 或 `--transport rtcpush`

特点：

- 适合接 SRS、直播平台或转推链路

## 14. 推荐组合和常见问题

迁移交接时优先使用：

- `--model wav2lip`
- `--tts robottts`
- `--transport webrtc`
- `--avatar_id "$AVATAR_ID"`
- `--listenport "$LIVETALKING_PORT"`

如果只验证 LiveTalking 本体，也用 `--tts robottts`，后端启动 `testclient` EdgeTTS 测试服务。旧的 direct EdgeTTS 插件仍保留为上游能力，但不作为迁移交接推荐方式。

### 14.1 显存不足

如果启动或推理时报 CUDA OOM，先看：

```bash
nvidia-smi
```

同一台机器上如果有多个 Python/GPU 进程同时占显存，可能导致：

- 启动失败
- 推理线程中断
- 离线渲染失败

处理建议：

- 先停掉无关 GPU 任务
- 再重新启动 LiveTalking

### 14.2 页面能打开但没画面

这通常是 WebRTC 传输链路问题，不一定是后端没有启动。

优先检查：

- 日志文件
- 浏览器控制台
- 端口是否监听
- 本机或服务器的防火墙
- WebRTC/ICE/UDP 是否被限制

### 14.3 Hugging Face 访问失败

如果后续还要下载模型或素材，先执行：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

## 15. 当前修改说明

当前需要随仓库交接的本地改动包括：

1. 新增 `robottts` 外部 TTS 桥接。
2. 新增 alpha raw RGBA 输出链路。
3. `wav2lip` avatar 生成支持单张图片、图片目录和透明 PNG。
4. 修复 `wav2lip` 推理前 `face_imgs` 尺寸不一致导致的 batch 崩溃。
5. MuseTalk 预处理代码已还原为官方逻辑。

如果后续替换 avatar，最关键的一点是：

- `face_imgs` 最好一开始就生成为统一尺寸。

## 16. 建议的日常使用命令

### 启动 LiveTalking

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --tts robottts \
  --TTS_SERVER "$TTS_SERVER_URL" \
  --robottts_mode instruct2 \
  --listenport "$LIVETALKING_PORT"
```

上面命令假设已经有一个 `robottts` 兼容服务监听 `$TTS_SERVER_URL`。

### 使用真实 robot-tts 作为 robottts 兼容服务

先启动真实业务 TTS：

```bash
cd /path/to/robot-tts
HF_ENDPOINT=https://hf-mirror.com uv run python -m tts_service.main
```

再启动 `LiveTalking`：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --tts robottts \
  --TTS_SERVER "$TTS_SERVER_URL" \
  --robottts_mode instruct2 \
  --listenport "$LIVETALKING_PORT"
```

如果 `robot-tts` 跑在别的机器：

- `export TTS_SERVER_URL=http://<ip>:8036`

如果你想直接把 `TTS_SERVER` 写成 websocket 地址，也可以：

- `ws://127.0.0.1:8036/tts/ws`
- `wss://.../tts/ws`

插件会自动兼容 `http/https/ws/wss` 写法。

### 使用 testclient EdgeTTS 测试 robottts 流式语音源

先启动 `testclient` EdgeTTS 测试服务：

```bash
cd /path/to/LiveTalking/testclient
TEST_TTS_PROVIDER=edge ./start-tts.sh
```

再按上面的 LiveTalking 命令启动即可。

### 使用百炼 CosyVoice 测试 robottts 流式语音源

先启动百炼 `robottts` 兼容测试服务：

```bash
cd /path/to/LiveTalking/testclient
TEST_TTS_PROVIDER=bailian DASHSCOPE_API_KEY=你的百炼APIKey ./start-tts.sh
```

再启动 `LiveTalking`：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --tts robottts \
  --TTS_SERVER "$TTS_SERVER_URL" \
  --robottts_mode instruct2 \
  --listenport "$LIVETALKING_PORT"
```

### 后台启动

```bash
cd /path/to/LiveTalking
nohup env HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
  --transport webrtc \
  --model wav2lip \
  --avatar_id "$AVATAR_ID" \
  --listenport "$LIVETALKING_PORT" > "livetalking-${LIVETALKING_PORT}.log" 2>&1 &
```

### 看日志

```bash
tail -f "livetalking-${LIVETALKING_PORT}.log"
```

### 通过接口触发 robottts 朗读

最简单的文本朗读请求：

```bash
curl -X POST "$LIVETALKING_URL/human" \
  -H 'Content-Type: application/json' \
  -d '{
    "sessionid": "0",
    "type": "echo",
    "interrupt": true,
    "text": "这是通过 robottts 流式驱动的数字人朗读测试。"
  }'
```

注意：

- `webrtc` 模式下，`sessionid` 必须对应一个已经建立的 WebRTC 会话
- 也就是说，要先打开 `dashboard.html` 或 `webrtcapi.html` 并点“开始连接”
- 连接建立后，前端会创建对应的 `sessionid`
- 如果你直接在后端刚启动时就调用 `/human`，会得到 `session not found`

指定 `robottts` 参数：

```bash
curl -X POST "$LIVETALKING_URL/human" \
  -H 'Content-Type: application/json' \
  -d '{
    "sessionid": "0",
    "type": "echo",
    "interrupt": true,
    "text": "你好，这是新的音色和提示词测试。",
    "tts": {
      "voice_id": 1,
      "prompts": "请更自然一点，停顿明确一些。",
      "mode": "instruct2"
    }
  }'
```

如果你更习惯沿用当前 `LiveTalking` 里已有的字段名，也可以：

```json
{
  "tts": {
    "ref_file": "1",
    "ref_text": "请更自然一点，停顿明确一些。",
    "mode": "instruct2"
  }
}
```

其中：

- `ref_file = "1"` 会被当成 `voice_id = 1`
- `ref_file = "default"` 这类名称会尝试映射到 `/tts/voices` 里的 voice 名称
- `ref_text` 会映射到 `robottts` 协议的 `prompts`

### 浏览器页面怎么用

当前自带的 `dashboard.html` 朗读表单只会发：

- `text`
- `type=echo`
- `interrupt`
- `sessionid`

也就是说：

- 如果 `LiveTalking` 已经用 `--tts robottts` 启动，页面里直接点“朗读文本”也能说话
- 但页面默认没有输入 `voice_id/prompts/mode` 的控件
- 要切换 `robottts` 兼容服务的音色或提示词，当前需要你自己调 `/human` 接口，或者使用独立可视化测试客户端

### 停止

```bash
pgrep -af 'python app.py.*--transport webrtc'
kill <PID>
```

## 17. 备注

这份文档描述的是当前迁移交接方案，不是仓库 README 的纯官方默认路径。

如果后续要做更稳定的正式使用，建议优先补齐：

- `models/wav2lip.pth`
- `data/avatars/<avatar_id>` 对应的完整素材
- 真实 `robot-tts` 服务，或 `testclient` 内部百炼/EdgeTTS 测试 provider 的运行配置

## Alpha 透明输出与桌面置顶窗口

本地已增加一条透明输出链路：LiveTalking 内部保留 avatar PNG 的 alpha 通道，普通 WebRTC 页面仍按普通 BGR 视频输出；透明桌面助手走独立的 raw RGBA 帧 WebSocket，不再用 PNG 帧流，也不再建立隐藏 WebRTC 会话。

### 透明 avatar 制作

单张透明 PNG 可以直接生成 wav2lip avatar：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/transparent_person.png \
  --img_size 256 \
  --avatar_id my_alpha_avatar
```

也可以把 `--video_path` 指向一个图片目录，目录内 PNG/JPG 会按文件名顺序导入。

### 启动 LiveTalking alpha 模式

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
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

新增 alpha session 接口：

```text
POST $LIVETALKING_URL/alpha/session
```

新增透明帧流：

```text
$LIVETALKING_WS_URL/alpha/ws
```

该通道发送 raw RGBA8 二进制帧，消息格式是：

```text
24 byte header + width * height * 4 RGBA bytes
```

每个客户端只保留 1 帧队列；如果前端来不及画，会丢旧帧保留最新帧，避免延迟持续累积。

新增 alpha 桌面助手音频流：

```text
$LIVETALKING_WS_URL/alpha/audio
```

### 启动桌面置顶窗口

```bash
cd /path/to/LiveTalking/testclient
./start-overlay.sh
```

说明：

- 普通网页仍使用 WebRTC，不具备系统级透明窗口。
- 透明置顶输出窗由 Electron 窗口实现：无边框、透明、always-on-top。
- 输入和输出分离成两个窗口：`viewer.html` 只显示视频，`renderer.html` 只负责文字输入和朗读。
- 输出窗会按首帧尺寸自动调整内容大小，避免控制区把视频挤压变形。
- overlay 通过 `/alpha/session` 创建渲染会话，用 `/alpha/ws` 接收 raw RGBA 帧，用 `/alpha/audio` 接收 16kHz mono s16 PCM 音频。
- 前端优先使用 WebGL 上传 RGBA 纹理绘制，Canvas 2D 仅作为 fallback；音频使用 AudioWorklet 环形缓冲播放。
- 桌面助手建议把 `--batch_size` 设为 `4`。默认 `16` 吞吐高，但会按批次积累更多音频上下文，交互延迟更明显。
- “穿透”按钮只作用于输出窗，并让鼠标事件穿过窗口。

## 19. 迁移交接说明

本节用于把当前 LiveTalking 对接方案迁移给其他人或部署到新环境。`README.md`
保留官方说明，本文件前面章节保留本机完整调试记录；迁移时先进入新机器上的仓库根目录，不需要设置项目 home 环境变量。

进入仓库：

```bash
cd /path/to/LiveTalking
```

交接命令统一使用这些运行变量：

```bash
export TTS_SERVER_URL=http://127.0.0.1:8036
export LIVETALKING_URL=http://127.0.0.1:8050
export LIVETALKING_WS_URL=ws://127.0.0.1:8050
export LIVETALKING_PORT=8050
export AVATAR_ID=default_calm_1
```

说明：

- `TTS_SERVER_URL` 是 TTS HTTP/WebSocket 服务基地址。
- `LIVETALKING_URL` 是 LiveTalking 服务基地址。
- `LIVETALKING_WS_URL` 是 LiveTalking WebSocket 基地址，远程机器要改成 `ws://<服务器IP>:<端口>`。
- `LIVETALKING_PORT` 是 LiveTalking 服务监听端口，需要和 `LIVETALKING_URL` 保持一致。
- `AVATAR_ID` 是实际迁移的 avatar 名称，默认运行样例为 `default_calm_1`，但素材目录需要单独准备，必须能在 `data/avatars/<AVATAR_ID>` 找到。

### 19.1 当前方案定位

当前仓库基于 LiveTalking 增加了两类能力：

- `robottts`：把 LiveTalking 的文字输入接到兼容 TTS 服务。生产对接真实 `robot-tts`，本地测试可用 `testclient/backend` 内部的百炼或 EdgeTTS provider。
- `alpha_output`：输出 raw RGBA 视频帧，供 Electron 透明置顶 overlay 显示数字人。

主链路：

```text
业务/控制端
  -> LiveTalking /alpha/speak 或 /alpha/input/audio
  -> robottts-compatible /tts/ws
  -> LiveTalking wav2lip 推理
  -> /alpha/ws raw RGBA 视频
  -> testclient/overlay 透明置顶窗口
```

### 19.2 当前需要保留的本地代码改动

需要随仓库交接的改动：

- `tts/robottts.py`：外部 TTS websocket/http 插件。
- `server/alpha_stream.py`：RGBA 视频帧和 PCM 音频 websocket hub。
- `server/routes.py`：新增 `/alpha/session`、`/alpha/speak`、`/alpha/ws`、`/alpha/audio`、`/alpha/input/audio`。
- `streamout/webrtc.py`：WebRTC 输出同时发布 alpha raw 帧。
- `app.py`：绑定 alpha hub 到 aiohttp event loop。
- `config.py`：新增 `--tts robottts` 相关参数和 `--alpha_output`。
- `avatars/wav2lip/genavatar.py`：支持单张图片、图片目录、透明 PNG 生成 wav2lip avatar。
- `avatars/wav2lip_avatar.py`、`utils/image.py`、`avatars/base_avatar.py`：支持 alpha 通道和 256 人脸输入。
- `server/session_manager.py`、`server/rtc_manager.py`、`server/webrtc.py`：支持 alpha session 和字符串 session id。

MuseTalk 说明：

- `avatars/musetalk/utils/preprocessing.py` 已还原为官方原始逻辑。
- 这意味着 MuseTalk 仍依赖 MMPose/DWPose 相关环境和模型文件，不再带本地 fallback。

### 19.3 不进 Git 的文件

`.gitignore` 已明确忽略：

- `.venv/`、`__pycache__/`、`.pytest_cache/` 等环境和缓存。
- `*.log`、`logs/`、`log/`、`nohup.out`、`*.out`、`*.err` 等日志产物。
- `temp*.aac`、`temp*.mp4`、`temp*.wav`、`test_artifacts/` 等运行产物。
- `data/avatars/*`、`data/record.mp4` 等生成 avatar 和录制文件。所有 avatar 素材目录都不进 Git，包括 `data/avatars/default_calm_1/`。
- `models/*`、`hf_assets/`、`downloads/`、`pretrained/`、`checkpoints/`、`weights/`、`pretrained_models/` 等模型和下载缓存。
- `*.pth`、`*.pt`、`*.ckpt`、`*.safetensors`、`*.onnx`、`*.engine`、`*.bin`、`*.gguf` 等模型权重文件。
- `designtool_site_01.png` 等本地一次性测试素材。

需要提交的文档和代码不应被忽略，例如：

- `README-LOCAL.md`
- `server/alpha_stream.py`
- `tts/robottts.py`
- `testclient/`

交接前检查：

```bash
cd /path/to/LiveTalking
git status --short
```

正常情况下，不应该看到日志、临时音频、模型权重或 avatar 图片序列出现在未跟踪文件里。

### 19.4 新环境安装

建议 Python 3.10，继续使用 `uv`：

```bash
cd /path/to/LiveTalking
uv venv --python 3.10 .venv
uv pip install -r requirements.txt
```

注意：

- PyTorch/CUDA 版本要按目标机器 GPU 环境安装。
- `models/wav2lip.pth` 不进 Git，需要单独拷贝到 `models/wav2lip.pth`。
- avatar 数据不进 Git，需要单独拷贝到 `data/avatars/<avatar_id>/`。
- 如果使用 Hugging Face 镜像，运行前加：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

### 19.5 必须单独迁移的资产

最小可运行 wav2lip alpha 方案需要：

```text
models/wav2lip.pth
data/avatars/<avatar_id>/
  full_imgs/
  face_imgs/
  coords.pkl
```

实际迁移时按 `AVATAR_ID` 替换。包括默认样例 `default_calm_1` 在内，avatar 数据不进 Git，需要单独打包或通过对象存储/文件服务器分发。

如果要使用透明桌面数字人，`full_imgs` 建议为带 alpha 通道的 PNG。

### 19.6 启动 robottts 兼容 TTS

真实 TTS 服务：

```bash
cd /path/to/robot-tts
uv run python -m tts_service.main
```

testclient EdgeTTS 测试服务：

```bash
cd /path/to/LiveTalking/testclient
TEST_TTS_PROVIDER=edge ./start-tts.sh
```

百炼 CosyVoice 测试服务：

```bash
cd /path/to/LiveTalking/testclient
TEST_TTS_PROVIDER=bailian DASHSCOPE_API_KEY=你的百炼APIKey ./start-tts.sh
```

这些服务 API 对齐，默认端口都是 `8036`，不要同时占用同一端口。LiveTalking 只需要指向当前启动的那个：

```bash
export TTS_SERVER_URL=http://127.0.0.1:8036
```

检查：

```bash
curl "$TTS_SERVER_URL/health"
curl "$TTS_SERVER_URL/tts/voices"
```

### 19.6.1 可视化测试客户端

独立测试客户端目录：

```text
/path/to/LiveTalking/testclient
```

启动：

```bash
cd /path/to/LiveTalking/testclient
npm install
./start-web.sh
```

它用于可视化验证：

- `robottts` 兼容 TTS 服务健康检查和音色列表。
- `/alpha/speak` 文本输入链路。
- `/tts/task/start -> /alpha/input/audio` 音频流推送链路。
- `/alpha/ws` 视频帧宽高、帧号、fps 和透明画面。

### 19.7 启动 LiveTalking

透明 overlay 推荐启动命令：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python app.py \
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

换 avatar 时只改：

```bash
export AVATAR_ID=<new_avatar_id>
```

### 19.8 启动桌面 overlay

overlay 现在放在独立测试客户端内部。它不读取 LiveTalking 主仓库 `.env`，只读取 `testclient/.env` 和 `testclient/overlay/.env`：

```text
/path/to/LiveTalking/testclient/overlay
```

本机显示：

```bash
cd /path/to/LiveTalking/testclient
./start-overlay.sh
```

远程显示：

```bash
cd /path/to/LiveTalking/testclient
LIVETALKING_SERVER=http://<LiveTalking服务器IP>:<LiveTalking端口> ./start-overlay.sh
```

如果只要画面不要声音：

```bash
LIVETALKING_PLAY_AUDIO=0 LIVETALKING_SERVER=http://<LiveTalking服务器IP>:<LiveTalking端口> ./start-overlay.sh
```

overlay 日志：

```text
/path/to/LiveTalking/testclient/overlay/overlay-debug.log
```

### 19.9 常用 API

创建或复用 alpha session：

```bash
curl -X POST "$LIVETALKING_URL/alpha/session" \
  -H 'Content-Type: application/json' \
  -d '{"reuse": true}'
```

文字朗读：

```bash
curl -X POST "$LIVETALKING_URL/alpha/speak" \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "这是一段数字人朗读测试。",
    "type": "echo",
    "interrupt": true,
    "tts": {
      "voice_id": 0,
      "mode": "instruct2",
      "prompts": "请自然清晰地朗读。"
    }
  }'
```

查询是否正在说话：

```bash
curl -X POST "$LIVETALKING_URL/is_speaking" \
  -H 'Content-Type: application/json' \
  -d '{"sessionid": "<sessionid>"}'
```

### 19.10 制作 wav2lip avatar

单张图片：

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/person.png \
  --img_size 256 \
  --avatar_id my_avatar
```

视频：

```bash
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/silent_video.mp4 \
  --img_size 256 \
  --avatar_id my_video_avatar
```

如果嘴部或下巴裁剪不完整：

```bash
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/person.png \
  --img_size 256 \
  --pads 0 20 0 0 \
  --avatar_id my_padded_avatar
```

生成目录：

```text
data/avatars/<avatar_id>/
  full_imgs/
  face_imgs/
  coords.pkl
```

### 19.11 排错入口

LiveTalking 日志：

```text
livetalking.log
livetalking-${LIVETALKING_PORT}.log
```

overlay 日志：

```text
/path/to/LiveTalking/testclient/overlay/overlay-debug.log
```

常见检查：

```bash
ss -ltnp | grep -E ":8036|:${LIVETALKING_PORT:-8050}"
curl "$TTS_SERVER_URL/health"
curl -X POST "$LIVETALKING_URL/alpha/session" \
  -H 'Content-Type: application/json' \
  -d '{"reuse": true}'
```

如果 overlay 无画面，先确认：

- LiveTalking 启动时带了 `--alpha_output`。
- overlay 的 `LIVETALKING_SERVER` 指向正确 IP 和端口。
- `data/avatars/<avatar_id>` 存在且有 `full_imgs`、`face_imgs`、`coords.pkl`。
