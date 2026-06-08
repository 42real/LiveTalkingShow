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
      "default_play_mode": "pingpong",
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
| `states.<kind>.clips` | 列表 | 素材索引，工具会自动维护；运行时仍以每个素材目录里的 `metadata.json` 为准。 |

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
| `--play-mode` | `forward`、`pingpong`、`reverse`、`random_direction` | 单个素材的播放方式。 |
| `--can-reverse` | 开关 | 允许 `reverse` 或 `random_direction` 使用倒放。 |
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
    play_mode: pingpong
    can_reverse: true
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

## 音频和动作逻辑

运行时有两个状态概念：

- 音频目标状态：有语音就是 `speaking`，全静音就是 `idle`。它决定当前这一帧是否立刻做嘴型推理。
- 动作素材状态：当前正在播放哪个动作素材。它决定身体动作来自 `speaking` 素材池还是 `idle` 素材池。

音频目标状态变化会立即生效。也就是说，哪怕当前还在播放 `idle` 原子动作，只要音频来了，Wav2Lip 会立刻在当前 `idle` 动作帧上做嘴型推理。

动作素材状态默认不立刻硬切。如果当前素材 `switch_at_boundary=true`，目标动作状态会先记为 pending，等当前素材播放到边界再切换。日志里会出现：

```text
motion scheduler pending motion=speaking audio_target=idle action=lecture_explain_01 cursor=42/75
motion scheduler boundary switch speaking/lecture_explain_01 -> idle
motion scheduler start motion=idle audio_target=idle action=idle_breath_01 mode=pool:weighted_no_repeat play_mode=pingpong cycles=1 frames=98
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

画面不自然时优先检查：

- 源素材是否首尾姿态一致。
- `pads` 是否让嘴部贴回位置准确。
- `img_size` 是否和当前 Wav2Lip 模型匹配，256 版优先使用 `256`。
- 说话素材源视频是否本身已有明显口型。
- 单个素材是否太长，导致动作素材切换延迟明显。
