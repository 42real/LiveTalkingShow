#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

source "$SCRIPT_DIR/load-env-defaults.sh"
load_env_defaults "${LIVETALKING_ENV_FILE:-.env}"

ENV_DIR="${LIVETALKING_MUSETALK_ENV:-.venv-musetalk}"
PYTHON_VERSION="${LIVETALKING_MUSETALK_PYTHON_VERSION:-3.10}"
PYTHON_BIN="$ENV_DIR/bin/python"

TORCH_VERSION="${LIVETALKING_MUSETALK_TORCH_VERSION:-2.0.1+cu118}"
TORCHVISION_VERSION="${LIVETALKING_MUSETALK_TORCHVISION_VERSION:-0.15.2+cu118}"
PYTORCH_INDEX="${LIVETALKING_MUSETALK_PYTORCH_INDEX:-https://download.pytorch.org/whl/cu118}"
MMCV_FIND_LINKS="${LIVETALKING_MUSETALK_MMCV_FIND_LINKS:-https://download.openmmlab.com/mmcv/dist/cu118/torch2.0.0/index.html}"
MMCV_VERSION="${LIVETALKING_MUSETALK_MMCV_VERSION:-2.0.1}"
MMCV_WHEEL_URL="${LIVETALKING_MUSETALK_MMCV_WHEEL_URL:-https://download.openmmlab.com/mmcv/dist/cu118/torch2.0.0/mmcv-${MMCV_VERSION}-cp310-cp310-manylinux1_x86_64.whl}"
MMENGINE_VERSION="${LIVETALKING_MUSETALK_MMENGINE_VERSION:-0.10.7}"
MMDET_VERSION="${LIVETALKING_MUSETALK_MMDET_VERSION:-3.1.0}"
MMPOSE_VERSION="${LIVETALKING_MUSETALK_MMPOSE_VERSION:-1.1.0}"
DIFFUSERS_VERSION="${LIVETALKING_MUSETALK_DIFFUSERS_VERSION:-0.30.2}"
ACCELERATE_VERSION="${LIVETALKING_MUSETALK_ACCELERATE_VERSION:-0.28.0}"
TRANSFORMERS_VERSION="${LIVETALKING_MUSETALK_TRANSFORMERS_VERSION:-4.39.2}"
HUGGINGFACE_HUB_VERSION="${LIVETALKING_MUSETALK_HUGGINGFACE_HUB_VERSION:-0.30.2}"

uv venv --python "$PYTHON_VERSION" "$ENV_DIR"

uv pip install --python "$PYTHON_BIN" \
  "setuptools<81" \
  "wheel" \
  "pip" \
  "numpy<2"

uv pip install --python "$PYTHON_BIN" \
  --index-url "$PYTORCH_INDEX" \
  "torch==$TORCH_VERSION" \
  "torchvision==$TORCHVISION_VERSION" \
  "numpy<2"

uv pip install --python "$PYTHON_BIN" \
  --no-cache-dir \
  --no-build-isolation \
  "$MMCV_WHEEL_URL" \
  "mmengine==$MMENGINE_VERSION" \
  "mmdet==$MMDET_VERSION" \
  "mmpose==$MMPOSE_VERSION"

uv pip install --python "$PYTHON_BIN" \
  "numpy<2" \
  "opencv-python-headless" \
  "Pillow" \
  "tqdm" \
  "einops" \
  "omegaconf" \
  "diffusers==$DIFFUSERS_VERSION" \
  "accelerate==$ACCELERATE_VERSION" \
  "transformers==$TRANSFORMERS_VERSION" \
  "huggingface_hub==$HUGGINGFACE_HUB_VERSION" \
  "safetensors" \
  "face_alignment" \
  "xtcocotools" \
  "matplotlib" \
  "scipy" \
  "scikit-image" \
  "torch-ema" \
  "torchmetrics" \
  "imageio-ffmpeg" \
  "librosa" \
  "resampy" \
  "soundfile==0.12.1"

"$PYTHON_BIN" - <<'PY'
import torch
import mmcv
import mmcv._ext
from mmcv.ops import nms
import mmengine
import mmdet
import mmpose

print("MuseTalk avatar environment OK")
print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
print("mmcv", mmcv.__version__)
print("mmengine", mmengine.__version__)
print("mmdet", mmdet.__version__)
print("mmpose", mmpose.__version__)
print("mmcv._ext", mmcv._ext.__file__)
print("mmcv.ops.nms", nms)
PY
