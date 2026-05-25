#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

MODE="${1:-wav2lip-demo}"

case "$MODE" in
  wav2lip|wav2lip-demo|s3fd|musetalk|all)
    ;;
  -h|--help|help)
    cat <<'EOF'
Usage:
  ./scripts/download-models.sh [wav2lip-demo|wav2lip|s3fd|musetalk|all]

Modes:
  wav2lip-demo  Download models/wav2lip.pth and a demo wav2lip avatar.
  wav2lip       Download models/wav2lip.pth only.
  s3fd          Download the Wav2Lip avatar-generation face detector.
  musetalk      Download MuseTalk runtime/avatar-generation model assets.
  all           Download wav2lip-demo, s3fd, and musetalk assets.

Useful environment variables:
  HF_ENDPOINT=https://hf-mirror.com
  LIVETALKING_WAV2LIP_REPO=shibing624/ai-avatar-wav2lip
  LIVETALKING_WAV2LIP_AVATAR_ZIP=wav2lip_avatar_female_model.zip
  LIVETALKING_WAV2LIP_AVATAR_ID=wav2lip_avatar_female_model
  LIVETALKING_MODEL_OVERWRITE=1
EOF
    exit 0
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    echo "Run ./scripts/download-models.sh --help for usage." >&2
    exit 2
    ;;
esac

[ -d ".venv" ] || uv sync --python 3.10 --inexact
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
export DOWNLOAD_MODE="$MODE"

uv run --no-sync --python "${LIVETALKING_PYTHON:-.venv/bin/python}" python - <<'PY'
from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download


ROOT = Path.cwd()
MODE = os.environ["DOWNLOAD_MODE"]
OVERWRITE = os.getenv("LIVETALKING_MODEL_OVERWRITE", "0").strip().lower() in {"1", "true", "yes", "on"}


def log(message: str) -> None:
    print(f"[download-models] {message}", flush=True)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_file(src: str | Path, dst: str | Path) -> None:
    src_path = Path(src)
    dst_path = Path(dst)
    if dst_path.exists() and not OVERWRITE:
        log(f"skip existing {dst_path}")
        return
    ensure_parent(dst_path)
    shutil.copy2(src_path, dst_path)
    log(f"ready {dst_path}")


def copy_tree(src: str | Path, dst: str | Path) -> None:
    src_path = Path(src)
    dst_path = Path(dst)
    if dst_path.exists() and not OVERWRITE:
        log(f"skip existing {dst_path}")
        return
    if dst_path.exists():
        shutil.rmtree(dst_path)
    ensure_parent(dst_path)
    shutil.copytree(src_path, dst_path)
    log(f"ready {dst_path}")


def hf_file(repo_id: str, filename: str, local_dir: str) -> str:
    log(f"download {repo_id}/{filename}")
    return hf_hub_download(repo_id=repo_id, filename=filename, local_dir=local_dir)


def install_wav2lip_model() -> None:
    target = ROOT / "models" / "wav2lip.pth"
    if target.exists() and not OVERWRITE:
        log(f"skip existing {target}")
        return
    repo = os.getenv("LIVETALKING_WAV2LIP_REPO", "shibing624/ai-avatar-wav2lip")
    downloaded = hf_file(repo, "wav2lip.pth", "downloads/wav2lip")
    copy_file(downloaded, target)


def install_wav2lip_demo_avatar() -> None:
    repo = os.getenv("LIVETALKING_WAV2LIP_REPO", "shibing624/ai-avatar-wav2lip")
    avatar_zip = os.getenv("LIVETALKING_WAV2LIP_AVATAR_ZIP", "wav2lip_avatar_female_model.zip")
    avatar_id = os.getenv("LIVETALKING_WAV2LIP_AVATAR_ID", Path(avatar_zip).stem)
    target = ROOT / "data" / "avatars" / avatar_id
    if target.exists() and not OVERWRITE:
        log(f"skip existing {target}")
        return

    archive = Path(hf_file(repo, avatar_zip, "downloads/wav2lip"))
    with tempfile.TemporaryDirectory(prefix="livetalking-avatar-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp_path)

        candidates = [p for p in tmp_path.rglob("*") if p.is_dir() and (p / "full_imgs").exists()]
        if candidates:
            source = candidates[0]
        elif (tmp_path / "full_imgs").exists():
            source = tmp_path
        else:
            raise RuntimeError(f"cannot find avatar directory in {archive}")

        copy_tree(source, target)


def install_s3fd() -> None:
    target = ROOT / "avatars" / "wav2lip" / "face_detection" / "detection" / "sfd" / "s3fd.pth"
    if target.exists() and not OVERWRITE:
        log(f"skip existing {target}")
        return
    url = "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth"
    ensure_parent(target)
    log(f"download {url}")
    urllib.request.urlretrieve(url, target)
    log(f"ready {target}")


def install_musetalk() -> None:
    # MuseTalk itself.
    repo = os.getenv("LIVETALKING_MUSETALK_REPO", "TMElyralab/MuseTalk")
    for filename in ["musetalkV15/musetalk.json", "musetalkV15/unet.pth"]:
        target = ROOT / "models" / filename
        if target.exists() and not OVERWRITE:
            log(f"skip existing {target}")
            continue
        downloaded = hf_file(repo, filename, "downloads/musetalk")
        copy_file(downloaded, target)

    # DWPose and face parsing checkpoints used by the avatar generator.
    support_repo = os.getenv("LIVETALKING_MUSETALK_SUPPORT_REPO", "camenduru/MuseTalk")
    for filename in [
        "dwpose/dw-ll_ucoco_384.pth",
        "face-parse-bisent/79999_iter.pth",
        "face-parse-bisent/resnet18-5c106cde.pth",
    ]:
        target = ROOT / "models" / filename
        if target.exists() and not OVERWRITE:
            log(f"skip existing {target}")
            continue
        downloaded = hf_file(support_repo, filename, "downloads/musetalk-support")
        copy_file(downloaded, target)

    # Transformers-format Whisper and diffusers-format VAE directories.
    whisper_dir = ROOT / "models" / "whisper"
    if not whisper_dir.exists() or OVERWRITE:
        log("download openai/whisper-tiny -> models/whisper")
        snapshot_download(repo_id="openai/whisper-tiny", local_dir=str(whisper_dir))
    else:
        log(f"skip existing {whisper_dir}")

    vae_dir = ROOT / "models" / "sd-vae"
    if not vae_dir.exists() or OVERWRITE:
        log("download stabilityai/sd-vae-ft-mse -> models/sd-vae")
        snapshot_download(repo_id="stabilityai/sd-vae-ft-mse", local_dir=str(vae_dir))
    else:
        log(f"skip existing {vae_dir}")


if MODE in {"wav2lip", "wav2lip-demo", "all"}:
    install_wav2lip_model()

if MODE in {"wav2lip-demo", "all"}:
    install_wav2lip_demo_avatar()

if MODE in {"s3fd", "all"}:
    install_s3fd()

if MODE in {"musetalk", "all"}:
    install_musetalk()

log("done")
PY
