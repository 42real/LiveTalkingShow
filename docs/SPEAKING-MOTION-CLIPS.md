# Motion Clips

这份文档说明 Wav2Lip avatar 的动作素材系统。它把数字人的画面分成两个状态：

- `speaking`：检测到语音时使用，Wav2Lip 会在对应动作帧上重新生成嘴部。
- `idle`：没有语音时使用，不做 Wav2Lip 推理，直接播放静息动作帧。

一个状态可以放多个动作素材。每个素材是一段“原子动作”，运行时可以固定选择某个动作，也可以选择 `auto` 自动素材池，让系统在同一状态下按规则轮换不同动作。

## 新版 avatar-local 目录结构

推荐把动作素材和动作播放配置都放到 avatar 自己的目录里。这样交接一个 avatar 时，只需要带走一个目录：

```text
data/avatars/<avatar_id>/
  full_imgs/
  face_imgs/
  coords.pkl
  metadata.json
  motion.json
  motions/
    speaking/
      <action_id>/
        full_imgs/
        face_imgs/
        coords.pkl
        metadata.json
        preview.png
    idle/
      <action_id>/
        full_imgs/
        face_imgs/
        coords.pkl
        metadata.json
        preview.png
```

`motion.json` 是新版 avatar 格式的开关和动作策略配置。没有这个文件时，avatar 按原有方式运行：使用自身 `full_imgs` 帧循环，并兼容旧的 `data/speaking_actions`、`data/idle_actions` 外置动作目录。

`motion.json` 示例：

```json
{
  "version": 1,
  "layout": "avatar-local-motion",
  "strategy": "weighted_no_repeat",
  "states": {
    "idle": {
      "path": "motions/idle",
      "selection": "auto",
      "strategy": "weighted_no_repeat",
      "default_play_mode": "forward",
      "clips": []
    },
    "speaking": {
      "path": "motions/speaking",
      "selection": "auto",
      "strategy": "weighted_no_repeat",
      "default_play_mode": "forward",
      "clips": []
    }
  }
}
```

字段说明：

| 字段 | 取值 | 说明 |
| --- | --- | --- |
| `layout` | `avatar-local-motion` | 标记该 avatar 使用内置动作格式。 |
| `strategy` | `sequence` / `random` / `weighted_random` / `no_repeat_random` / `weighted_no_repeat` | 全局默认素材池选择策略。 |
| `states.<kind>.path` | 相对 avatar 目录的路径 | 该状态动作素材目录。 |
| `states.<kind>.selection` | `auto`、具体 `action_id`、空字符串 | 默认选择。`auto` 表示自动素材池；空字符串表示回到 avatar 原始帧。 |
| `states.<kind>.default_play_mode` | `forward` / `pingpong` / `reverse` / `random_direction` | 制作或补全素材 metadata 时的默认播放方式。 |
| `states.<kind>.clips` | 列表 | 素材索引，工具会自动维护；同名素材在这里配置的播放字段会覆盖素材目录里的 `metadata.json`。 |

`motion.json` 是 avatar 级统一配置。运行时先读取每个素材目录里的 `metadata.json`，再用 `motion.json` 中同名 `clips[].action_id` 的字段覆盖。常用覆盖字段包括 `display_name`、`enabled`、`weight`、`play_mode`、`can_reverse`、`min_cycles`、`max_cycles`、`switch_at_boundary`、`tags`、`best_for`。如果 `motion.json` 中没有某个字段，才使用素材自己的 `metadata.json`。

## 旧版兼容目录结构

旧版外置动作目录仍可读取，主要用于兼容已经制作好的素材。

说话动作：

```text
data/speaking_actions/<avatar_id>/<action_id>/
  full_imgs/
  face_imgs/
  coords.pkl
  metadata.json
  preview.png
```

静息动作：

```text
data/idle_actions/<avatar_id>/<action_id>/
  full_imgs/
  face_imgs/
  coords.pkl
  metadata.json
  preview.png
```

`avatar_id` 必须和启动 LiveTalking 时的 `--avatar_id` 一致。`action_id` 是单个动作素材编号，只能使用英文、数字、下划线和短横线。

## 素材要求

每个视频片段建议只表达一个动作，例如普通讲解、强调、轻微点头、等待、呼吸。不要把多个意图很强的动作混在一个片段里。

同一状态下的多个素材建议满足：

- 分辨率和人物位置尽量一致。
- 首帧和尾帧回到同一个自然姿态，至少头部和肩部位置要接近。
- 说话动作可以是闭嘴或轻微张嘴素材，避免源视频本身有明显说话口型。
- 静息动作幅度要小，适合循环播放，例如呼吸、轻微站立晃动、等待。
- 素材越短，动作素材切换越及时；常用建议是 1-4 秒。
- 人脸不要大幅侧转，不要被手遮挡。

基础版本按“动作边界”切换素材。音频一来会立即做嘴型推理，不等当前动作结束；但身体动作素材不会立刻硬切。如果当前素材设置了 `switch_at_boundary=true`，系统会等当前原子动作播放完成后，再切到音频目标状态对应的素材池。

## 制作带多动作的 avatar-local avatar

avatar-local 动作格式用于制作“一个数字人有多段讲话动作和多段待机动作”的 avatar。一个 avatar 目录里既有基础帧，也有 `speaking` 和 `idle` 多段动作素材。

最小目录长这样：

```text
data/avatars/<avatar_id>/
  full_imgs/ face_imgs/ coords.pkl metadata.json
  motion.json
  motions/
    speaking/<action_id>/full_imgs/ face_imgs/ coords.pkl metadata.json
    idle/<action_id>/full_imgs/ face_imgs/ coords.pkl metadata.json
```

需要准备四类东西：

- 基础人物素材：一张图、PNG 序列或视频，用来生成顶层 `full_imgs`、`face_imgs`、`coords.pkl`，也是没有动作素材时的兜底画面。
- 讲话动作素材：多段 `speaking` 视频，每段只做一个原子动作。音频来时，Wav2Lip 会在这些帧上重新推嘴型。
- 待机动作素材：多段 `idle` 视频，没有音频时直接播放，不做嘴型推理。
- 模型和工具：`models/wav2lip.pth`、S3FD 人脸检测模型；长视频切片建议有 FFmpeg。

素材要求保持简单：同一个 avatar 的基础素材、讲话素材、待机素材尽量同人物、同分辨率、同构图；每段动作建议 1-4 秒；首尾回到接近的自然姿态；人脸不要大幅侧转或被遮挡。

制作步骤：

1. 准备模型。

```bash
cd /path/to/LiveTalking
HF_ENDPOINT=https://hf-mirror.com ./scripts/download-models.sh wav2lip
./scripts/download-models.sh s3fd
```

2. 先生成基础 avatar。

```bash
HF_ENDPOINT=https://hf-mirror.com uv run --python .venv/bin/python python -m avatars.wav2lip.genavatar \
  --video_path /path/to/base_or_idle01.mp4 \
  --img_size 256 \
  --avatar_id my_motion_avatar \
  --pads 0 10 0 0 \
  --face_det_batch_size 8
```

3. 用 manifest 批量加入动作素材。

这里的 `manifest` 是一个 YAML 清单文件，用来告诉制作脚本：要给哪个 avatar 加动作、默认参数是什么、每个动作视频分别是什么状态和编号。它不是模型文件，也不是运行时必须加载的文件；它只在批量制作动作素材时使用。

```yaml
avatar_id: my_motion_avatar
layout: avatar-local

defaults:
  fps: 25
  img_size: 256
  pads: [0, 10, 0, 0]
  face_det_batch_size: 8
  use_ffmpeg_cut: true
  switch_at_boundary: true

clips:
  - kind: speaking
    source: /path/to/talk01.mp4
    action_id: talk01
    play_mode: forward
    weight: 3

  - kind: idle
    source: /path/to/idle01.mp4
    action_id: idle01
    play_mode: forward
    weight: 3
```

执行：

```bash
uv run --python .venv/bin/python python tools/build_motion_clips.py \
  --manifest /path/to/motion-clips.yaml
```

`clips` 里继续追加视频，就能得到 `talk02`、`talk03`、`idle02` 等更多动作。工具会自动维护 `motion.json`，并把素材写到 `motions/speaking/` 或 `motions/idle/`。

运行和检查：

```bash
AVATAR_ID=my_motion_avatar ./entrypoint.sh
curl "http://127.0.0.1:8050/motion/clips?kind=speaking&reload=1"
curl "http://127.0.0.1:8050/motion/clips?kind=idle&reload=1"
```

启动日志应能看到 `loaded speaking motion clips`、`loaded idle motion clips`、`loaded avatar motion config`。也可以用测试客户端动作页制作或检查素材：`http://127.0.0.1:8070/motion.html`。

## 单个素材制作

从视频制作说话动作：

```bash
uv run --python .venv/bin/python python tools/build_speaking_motion_clip.py \
  --source /path/to/source.mp4 \
  --avatar-id avatar3d2 \
  --kind speaking \
  --action-id lecture_explain_01 \
  --display-name 普通讲解1 \
  --start 0 \
  --end 4 \
  --fps 25 \
  --img-size 256 \
  --pads 0 10 0 0 \
  --face-det-batch-size 8 \
  --play-mode forward \
  --weight 3 \
  --min-cycles 1 \
  --max-cycles 1 \
  --switch-at-boundary \
  --enabled \
  --use-ffmpeg-cut
```

从视频制作静息动作：

```bash
uv run --python .venv/bin/python python tools/build_speaking_motion_clip.py \
  --source /path/to/idle.mp4 \
  --avatar-id avatar3d2 \
  --kind idle \
  --action-id idle_breath_01 \
  --display-name 自然待机1 \
  --start 0 \
  --end 3 \
  --fps 25 \
  --img-size 256 \
  --pads 0 10 0 0 \
  --face-det-batch-size 8 \
  --play-mode pingpong \
  --can-reverse \
  --weight 2 \
  --min-cycles 1 \
  --max-cycles 2 \
  --switch-at-boundary \
  --enabled \
  --use-ffmpeg-cut
```

参数说明：

| 参数 | 范围/取值 | 说明 |
| --- | --- | --- |
| `--source` | 允许目录内的视频或图片目录 | 源素材。图片目录里的帧必须同尺寸、同通道。 |
| `--avatar-id` | 简单目录名 | 动作归属的 avatar。 |
| `--kind` | `speaking`、`idle` | 动作状态。新版 avatar-local 默认用这个决定输出到 `motions/<kind>`。 |
| `--action-id` | 英文、数字、`_`、`-` | 动作素材编号。 |
| `--display-name` | 文本 | 前端显示名。 |
| `--layout` | `avatar-local`、`legacy` | 默认 `avatar-local`，输出到 `data/avatars/<avatar_id>/motions/<kind>` 并维护 `motion.json`。 |
| `--out-root` | 空或旧外置目录 | 为空时用新版 avatar-local；显式填写 `data/speaking_actions` 或 `data/idle_actions` 时写旧版外置格式。 |
| `--start` / `--end` | 秒数，`end` 可省略 | 从源视频截取的时间段。 |
| `--fps` | 建议 15-30 | 输出帧率。帧率越高越顺，但素材更大、加载更慢。 |
| `--img-size` | 常用 256 | Wav2Lip 脸部输入尺寸。当前 256 版模型建议用 256。 |
| `--pads` | 4 个整数，建议 -300 到 300 | 人脸框调整，顺序是 `top bottom left right`。 |
| `--face-det-batch-size` | 正整数，常用 4-16 | 人脸检测批量。显存不够就调低。 |
| `--fixed-face-box` | `x1 y1 x2 y2` | 固定人脸框，适合自动检测不稳的素材。 |
| `--max-frames` | `0` 或正整数 | `0` 表示不限制；调试时可限制帧数。 |
| `--tags` | 逗号分隔 | 标签，例如 `speaking,teaching`。 |
| `--best-for` | 文本 | 适合场景说明。 |
| `--play-mode` | `forward`、`pingpong`、`reverse`、`random_direction` | 单个素材的播放方向。`forward` 只正放；`pingpong` 正放后倒放；`reverse` 只倒放；`random_direction` 每次选中时随机正放或倒放。 |
| `--can-reverse` | 开关 | 允许 `reverse` 或 `random_direction` 使用倒放；未开启时会回退为 `forward`。`pingpong` 本身会倒放，不受这个开关限制。 |
| `--weight` | `0-1000` | 自动素材池权重，越大越容易被选中；全为 0 时按等权重处理。 |
| `--min-cycles` / `--max-cycles` | `1-100` | 每次选中该素材后连续播放的循环次数。 |
| `--switch-at-boundary` | 默认开启 | 音频目标状态变化时，等当前素材播放完再切换动作素材。 |
| `--no-switch-at-boundary` | 开关 | 音频目标状态变化时立即切换动作素材。 |
| `--enabled` / `--disabled` | 默认 `enabled` | 是否加入 `auto` 自动素材池。 |
| `--chroma-key` | 开关 | 对绿幕源素材做扣色，输出带 alpha 的帧。 |
| `--use-ffmpeg-cut` | 开关 | 先用 FFmpeg 截出片段再处理，长视频建议开启。 |
| `--ffmpeg-path` | 路径 | FFmpeg 可执行文件路径。 |
| `--nosmooth` | 开关 | 关闭人脸框平滑。 |
| `--no-loop` | 开关 | 制作时不强制处理首尾循环。 |
| `--overwrite` | 开关 | 覆盖同名素材。 |

## 批量制作

同一个状态有多个素材时，建议写一个 YAML manifest：

```yaml
avatar_id: avatar3d2
layout: avatar-local

defaults:
  fps: 25
  img_size: 256
  pads: [0, 10, 0, 0]
  face_det_batch_size: 8
  use_ffmpeg_cut: true
  switch_at_boundary: true
  overwrite: false

clips:
  - kind: speaking
    source: /path/to/lecture.mp4
    action_id: lecture_explain_01
    display_name: 普通讲解1
    start: 0
    end: 3.5
    play_mode: forward
    weight: 4
    min_cycles: 1
    max_cycles: 1

  - kind: speaking
    source: /path/to/lecture.mp4
    action_id: lecture_emphasis_01
    display_name: 强调1
    start: 4
    end: 6
    play_mode: forward
    weight: 1

  - kind: idle
    source: /path/to/idle.mp4
    action_id: idle_breath_01
    display_name: 自然待机1
    start: 0
    end: 3
    play_mode: forward
    can_reverse: false
    weight: 3
    min_cycles: 1
    max_cycles: 2
```

执行：

```bash
uv run --python .venv/bin/python python tools/build_motion_clips.py \
  --manifest /path/to/motion-clips.yaml
```

如果希望某个素材失败后继续生成后面的素材，加 `--continue-on-error`。

批量制作完成后，目录会变成：

```text
data/avatars/avatar3d2/motion.json
data/avatars/avatar3d2/motions/speaking/lecture_explain_01/
data/avatars/avatar3d2/motions/speaking/lecture_emphasis_01/
data/avatars/avatar3d2/motions/idle/idle_breath_01/
```

## 运行时选择

启动 LiveTalking 后，可以在测试客户端主页面选择：

- `默认动作`：说话和静息都使用 avatar 原本帧循环。
- 某个具体素材：该状态固定播放这个素材。
- `自动素材池`：该状态从 `enabled=true` 的素材里自动选择。

接口选择自动素材池：

```bash
curl -X POST "http://127.0.0.1:8050/motion/select" \
  -H 'Content-Type: application/json' \
  -d '{
    "sessionid": "123456",
    "kind": "speaking",
    "action_id": "auto"
  }'
```

清空选择：

```bash
curl -X POST "http://127.0.0.1:8050/motion/select" \
  -H 'Content-Type: application/json' \
  -d '{
    "sessionid": "123456",
    "kind": "idle",
    "action_id": ""
  }'
```

自动素材池策略优先从 avatar 的 `motion.json` 读取，也可以用环境变量临时覆盖：

| 环境变量 | 说明 |
| --- | --- |
| `LIVETALKING_MOTION_STRATEGY` | speaking 和 idle 的默认策略。 |
| `LIVETALKING_SPEAKING_MOTION_STRATEGY` | 只控制说话动作。 |
| `LIVETALKING_IDLE_MOTION_STRATEGY` | 只控制静息动作。 |

策略取值：

| 策略 | 效果 |
| --- | --- |
| `sequence` | 按素材名称排序循环播放。 |
| `random` | 等概率随机。 |
| `weighted_random` | 按 `weight` 加权随机。 |
| `no_repeat_random` | 等概率随机，尽量不连续重复上一个素材。 |
| `weighted_no_repeat` | 默认值，按权重随机并尽量不连续重复。 |

选择策略只决定“下一段播放哪个素材”，不决定“素材怎么播放”。素材正放、倒放、正放再倒放由 `play_mode` 控制。也就是说，`weighted_no_repeat` 配合 `play_mode=pingpong` 时，系统仍然会对每个被选中的素材正放再倒放；如果要禁用倒放，把对应素材的 `play_mode` 设为 `forward`。

## 音频和动作逻辑

运行时有两个状态概念：

- 音频目标状态：有语音就是 `speaking`，全静音就是 `idle`。它决定当前这一帧是否立刻做嘴型推理。
- 动作素材状态：当前正在播放哪个动作素材。它决定身体动作来自 `speaking` 素材池还是 `idle` 素材池。

音频目标状态变化会立即生效。也就是说，哪怕当前还在播放 `idle` 原子动作，只要音频来了，Wav2Lip 会立刻在当前 `idle` 动作帧上做嘴型推理。

动作素材状态默认不立刻硬切。如果当前素材 `switch_at_boundary=true`，目标动作状态会先记为 pending，等当前素材播放到边界再切换。日志里会出现：

```text
motion scheduler pending motion=speaking audio_target=idle action=lecture_explain_01 cursor=42/75
motion scheduler boundary switch speaking/lecture_explain_01 -> idle
motion scheduler start motion=idle audio_target=idle action=idle_breath_01 mode=pool:weighted_no_repeat play_mode=forward cycles=1 frames=98
```

如果 `switch_at_boundary=false`，音频目标状态变化会立即打断当前动作并切换素材。这个适合非常短、无明显动作意图的素材，不适合挥手、指向、转身这类动作。

## 测试客户端

动作制作页：

```text
http://127.0.0.1:8070/motion.html
```

页面功能：

- 上传或填写源视频路径。
- 预览源视频，设置开始点和结束点。
- 检查人脸框，并调整 `pads`。
- 制作 `speaking` 或 `idle` 素材。
- 把多个片段加入队列后批量生成。
- 编辑已有素材的显示名、标签、播放模式、权重、循环次数和是否加入自动素材池。

主测试页：

```text
http://127.0.0.1:8070/
```

主测试页可以刷新素材、选择固定素材或 `auto` 自动素材池，并通过 TTS 驱动数字人说话。

## 接口

完整接口见 [API-PROTOCOL.md](API-PROTOCOL.md)。动作素材相关接口包括：

- `GET /motion/clips`
- `POST /motion/select`
- `POST /motion/source/upload`
- `POST /motion/source/probe`
- `POST /motion/source/detect`
- `GET /motion/source/video`
- `POST /motion/clips/create`
- `POST /motion/clips/update`
- `POST /motion/clips/delete`

## 调试建议

看运行日志时重点关注：

- `loaded speaking motion clips` / `loaded idle motion clips`：启动时是否加载到素材。
- `motion scheduler start`：当前选中了哪个动作素材状态、哪个动作、播放模式和循环次数。
- `motion scheduler pending`：音频目标状态已变化，但动作素材正在等待边界。
- `motion scheduler boundary switch`：动作播放完并切换到新的动作素材状态。
- `motion scheduler fallback`：没有选中素材或素材池为空，回到默认帧。
- `output metrics`：统一输出链路的发送情况，重点看 `video_fps`、`max_video_ms`、`buffer`。
- `packed alpha webrtc video`：packed alpha WebRTC 的编码前打包情况，重点看 `approx_fps`、`avg_pack_ms`、`dropped`。
- `avatar process metrics`：avatar 推理/输出线程情况，重点看 `fps`、`avg_output_ms`、`max_output_ms`、`res_queue`。
- `actual avg final fps`：普通 WebRTC track 消费侧统计。使用 packed alpha 输出时，优先参考 `packed alpha webrtc video` 和 `output metrics`。

如果日志中 `output metrics video_fps` 和 `packed alpha webrtc approx_fps` 稳定在 25 左右，但肉眼感觉节奏突然变化，通常不是输出帧率变了，而是选中了不同长度或不同 `play_mode` 的原子动作。例如 `pingpong` 会把一段 120 帧素材变成约 239 帧播放序列，动作观感会比只正放更慢、更长。需要统一观感时，应统一素材原始 fps、动作时长、首尾姿态和 `play_mode`。

画面不自然时优先检查：

- 源素材是否首尾姿态一致。
- `pads` 是否让嘴部贴回位置准确。
- `img_size` 是否和当前 Wav2Lip 模型匹配，256 版优先使用 `256`。
- 说话素材源视频是否本身已有明显口型。
- 单个素材是否太长，导致动作素材切换延迟明显。
