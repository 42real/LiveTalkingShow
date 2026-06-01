# LiveTalking Test Overlay

这个目录是 `testclient` 的桌面显示窗口，只负责透明、无边框、置顶显示 LiveTalking 的 alpha stream 视频。文字输入、TTS provider 和音频推送由 `testclient/backend`、真实 `robot-tts` 或其他外部组件完成。

## 链路

```text
外部组件 / testclient web / FastAPI docs
  -> LiveTalking /alpha/speak 或 /alpha/input/audio
  -> robottts-compatible TTS service
  -> LiveTalking wav2lip alpha RGBA 视频
  -> testclient/overlay Electron 透明置顶窗口
```

LiveTalking 只需要把 `--TTS_SERVER` 指向当前 `robottts` 兼容服务。百炼和 EdgeTTS 是 `testclient/backend` 的测试 provider，不需要写进 LiveTalking 主仓库环境。

## 启动

推荐从 `testclient` 根目录启动，这样会自动加载 `testclient/.env`：

```bash
cd /path/to/LiveTalking/testclient
./start-overlay.sh
```

也可以只启动 overlay：

```bash
cd /path/to/LiveTalking/testclient/overlay
npm install
LIVETALKING_SERVER=http://127.0.0.1:8050 ./start.sh
```

远程显示时把 `LIVETALKING_SERVER` 改成 LiveTalking 所在机器地址：

```bash
LIVETALKING_SERVER=http://<LiveTalking服务器IP>:8050 ./start.sh
```

## 窗口行为

- 视频窗口透明、无边框、置顶。
- 默认 `LIVETALKING_CLICK_THROUGH=1`，鼠标可穿透视频窗口，不挡 PPT、浏览器或 FastAPI docs。
- 控制条是独立窗口，不穿透鼠标，按钮可以点击。
- `- / 100% / +` 调整桌面显示倍率，范围为 `25%` 到 `300%`。
- `穿透 / 管理` 切换视频窗口是否接收鼠标事件。
- `Ctrl+Alt+R` 重连视频流。
- `Ctrl+Alt+Q` 退出窗口。

## 视频尺寸

overlay 从 `/alpha/ws` 的帧头读取原始 `width/height`。这个尺寸来自当前 avatar 的 `full_imgs` 原图尺寸；overlay 只按比例缩放显示，不裁剪、不压缩原始画布。

默认会按 `LIVETALKING_VIDEO_MAX_HEIGHT=1080`、`LIVETALKING_VIDEO_FPS=15`、`LIVETALKING_VIDEO_FORMAT=raw` 请求 alpha stream，以降低 raw RGBA 传输压力且保留透明通道。要拉取原始无损尺寸时，把尺寸和帧率限制设为 `0`。如果 overlay 和 LiveTalking 不在同一台机器，优先降低 `MAX_HEIGHT/FPS`；确实需要透明压缩时可尝试 `LIVETALKING_VIDEO_FORMAT=webp`。

如果画面尺寸不对，优先检查：

- 当前 LiveTalking 启动的 `--avatar_id` 是否正确。
- `data/avatars/<avatar_id>/full_imgs/` 图片宽高是否符合预期。
- LiveTalking 是否带 `--alpha_output` 启动。
- 控制条缩放倍率是否被调过。

## 环境变量

`start.sh` 支持这些变量，也可以写到 `testclient/.env` 或 `testclient/overlay/.env`：

```bash
ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
LIVETALKING_SERVER=http://127.0.0.1:8050
LIVETALKING_CLICK_THROUGH=1
LIVETALKING_PLAY_AUDIO=0
LIVETALKING_AUTO_SESSION=1
LIVETALKING_CLOSE_SESSION_ON_EXIT=0
LIVETALKING_WIDTH=360
LIVETALKING_HEIGHT=640
LIVETALKING_SCALE=1
LIVETALKING_RENDERER=webgl
LIVETALKING_CONTROL_WIDTH=340
LIVETALKING_CONTROL_HEIGHT=38
LIVETALKING_VIDEO_MAX_WIDTH=0
LIVETALKING_VIDEO_MAX_HEIGHT=1080
LIVETALKING_VIDEO_FPS=15
LIVETALKING_VIDEO_FORMAT=raw
LIVETALKING_VIDEO_QUALITY=80
LIVETALKING_X=1200
LIVETALKING_Y=200
LIVETALKING_EXTRA_PATH=/optional/bin/path
```

建议保持 `LIVETALKING_PLAY_AUDIO=0`。桌面窗口只显示视频，音频由 TTS 服务或主控组件播放，可以避免重复声音。

`LIVETALKING_VIDEO_MAX_WIDTH`、`LIVETALKING_VIDEO_MAX_HEIGHT`、`LIVETALKING_VIDEO_FPS` 和 `LIVETALKING_VIDEO_FORMAT` 只影响 overlay 从 `/alpha/ws` 请求的传输尺寸、帧率和编码格式，不会修改 avatar 文件。高分辨率 avatar 建议先用 `1080/15/raw`，仍卡再降到 `720/12/raw`。`jpeg` 最轻但没有透明；`webp` 保留透明但编码更吃 CPU。

## 调试

日志文件：

```text
overlay-debug.log
```

显示窗口连接：

```text
ws://<LiveTalking地址>/alpha/ws
```

视频格式：

```text
24 byte header + width * height * 4 RGBA bytes
```

客户端只保留最新一帧，慢了直接丢旧帧，避免延迟持续累积。默认使用 WebGL 上传 RGBA 纹理绘制；如果当前桌面环境下 GPU 进程不稳定，可以用 `LIVETALKING_RENDERER=2d ./start.sh` 切换到 Canvas 2D fallback。
