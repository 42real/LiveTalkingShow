# LiveTalking RobotTTS 可视化测试客户端

这个目录只放测试客户端，用于验证：

- `robottts` 兼容 TTS 服务是否可用
- LiveTalking `/alpha/speak` 是否能驱动数字人
- TTS task API 是否能把 PCM 流推到 `/alpha/input/audio`
- `/alpha/ws` 输出的视频帧尺寸和画面是否正常

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

3. 打开测试客户端页面，先点健康检查，再点创建 alpha session，最后测试两种输入方式：

- 通过 `/alpha/speak`：LiveTalking 调用 `robottts` 兼容 TTS 服务。
- 通过 TTS task：TTS 服务直接把音频流推给 `/alpha/input/audio`。
