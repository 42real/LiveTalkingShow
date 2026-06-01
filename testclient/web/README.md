# LiveTalking RobotTTS 可视化测试客户端

这个目录只放测试客户端，用于验证：

- `robottts` 兼容 TTS 服务是否可用
- LiveTalking `/alpha/speak` 是否能驱动数字人
- TTS task API 是否能把 PCM 流推到 `/alpha/input/audio`
- `/alpha/ws` 输出的视频帧尺寸和画面是否正常
- `/alpha/audio` 是否能在浏览器里播放音频输出

默认显示链路就是 alpha stream。页面启动后会自动创建 alpha session 并连接 `/alpha/ws?max_height=720&fps=25&format=jpeg&quality=80`；不需要先打开官方 WebRTC 页面。Web 测试页默认使用 JPEG 压缩预览，适合浏览器、远程桌面和 VSCode 端口转发，不用于透明桌面合成。

## 启动

推荐从 `testclient` 根目录启动：

```bash
cd /path/to/LiveTalking/testclient
./start-web.sh
```

也可以只启动 Web 页面：

```bash
cd /path/to/LiveTalking/testclient/web
npm install
npm run start -- --port 8070
```

复制 `.env.example` 为 `.env` 后可以改默认服务地址。

如果当前系统 inotify watcher 数量不足，`vite.config.js` 已默认使用 polling watcher。也可以用静态预览方式：

```bash
npm run build
npm run preview -- --port 8070
```

## 推荐测试链路

1. 启动 testclient 自带的 `robottts` 兼容 TTS 服务：

```bash
cd /path/to/LiveTalking/testclient
./start-tts.sh
```

2. 启动 LiveTalking：

```bash
cd /path/to/LiveTalking
cp .env.example .env
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip-demo
./entrypoint.sh
```

3. 打开测试客户端页面，页面会自动创建 alpha session 并连接 alpha 视频流。再点健康检查，最后测试两种输入方式：

- 通过 `/alpha/speak`：LiveTalking 调用 `robottts` 兼容 TTS 服务。
- 通过 TTS task：TTS 服务直接把音频流推给 `/alpha/input/audio`。
- 点“视频”可手动重连 `/alpha/ws` 预览画面；点“音频”连接 `/alpha/audio` 播放 LiveTalking 输出的 PCM 音频。

高分辨率 avatar 的 raw RGBA 帧很大。页面默认请求 `format=jpeg` 并按 `VITE_VIDEO_RENDER_INTERVAL_MS=40` 渲染预览，避免测试页面阻塞按钮操作。这些设置只影响测试页面显示，不影响 LiveTalking 服务端原始输出帧率。`VITE_ALPHA_AUTO_CONNECT=0` 可关闭自动连接。需要检查透明通道时可把 `VITE_ALPHA_VIDEO_FORMAT=raw` 或 `webp` 后重启 Web 客户端。
