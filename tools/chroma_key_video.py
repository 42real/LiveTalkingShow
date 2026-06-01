import argparse
from pathlib import Path

import cv2
import numpy as np


def _write_png(path, image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError(f"Failed to encode PNG: {path}")
    encoded.tofile(str(path))


def _key_frame(bgr):
    h, w = bgr.shape[:2]
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    green = (
        (hsv[:, :, 0] >= 35)
        & (hsv[:, :, 0] <= 95)
        & (hsv[:, :, 1] >= 35)
        & (hsv[:, :, 2] >= 45)
    ).astype(np.uint8)

    kernel = np.ones((5, 5), np.uint8)
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, kernel, iterations=2)
    green = cv2.dilate(green, kernel, iterations=1)

    _, labels = cv2.connectedComponents(green, connectivity=8)
    border_labels = np.unique(
        np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
    )
    bg = (np.isin(labels, border_labels) & (green > 0)).astype(np.uint8) * 255
    bg = cv2.morphologyEx(bg, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8), iterations=1)
    bg = cv2.GaussianBlur(bg, (9, 9), 0)

    alpha = 255 - bg
    alpha[alpha < 18] = 0
    alpha[alpha > 245] = 255

    keyed_bgr = bgr.copy().astype(np.float32)
    b = keyed_bgr[:, :, 0]
    g = keyed_bgr[:, :, 1]
    r = keyed_bgr[:, :, 2]
    max_rb = np.maximum(r, b)
    spill = np.clip(g - max_rb * 1.05, 0, 80)
    edge = ((alpha > 0) & (alpha < 255)).astype(np.float32)
    keyed_bgr[:, :, 1] = g - spill * (0.55 + 0.35 * edge)
    keyed_bgr = np.clip(keyed_bgr, 0, 255).astype(np.uint8)

    bgra = cv2.cvtColor(keyed_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = alpha
    return bgra


def _preview_tile(bgra, frame_index):
    h, w = bgra.shape[:2]
    bgr = bgra[:, :, :3]
    alpha = bgra[:, :, 3]
    fg = (alpha.astype(np.float32) / 255.0)[..., None]

    checker = np.indices((h, w)).sum(axis=0) // 32 % 2
    checker = np.where(checker[..., None] == 0, 210, 160).astype(np.uint8)
    checker = np.repeat(checker, 3, axis=2)
    comp = (bgr.astype(np.float32) * fg + checker.astype(np.float32) * (1 - fg)).astype(np.uint8)
    mask_vis = cv2.cvtColor(alpha, cv2.COLOR_GRAY2BGR)
    tile = cv2.resize(np.hstack([comp, mask_vis]), (720, 640), interpolation=cv2.INTER_AREA)
    cv2.putText(tile, f"frame {frame_index}", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (30, 30, 30), 3, cv2.LINE_AA)
    cv2.putText(tile, f"frame {frame_index}", (18, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (245, 245, 245), 1, cv2.LINE_AA)
    return tile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--preview", required=True)
    parser.add_argument("--preview-frames", default="0,60,120,180,240")
    args = parser.parse_args()

    video_path = Path(args.input)
    out_dir = Path(args.out_dir)
    preview_path = Path(args.preview)
    preview_frames = {int(x) for x in args.preview_frames.split(",") if x.strip()}

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video: {video_path}")

    count = 0
    tiles = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        bgra = _key_frame(bgr)
        _write_png(out_dir / f"{count:08d}.png", bgra)
        if count in preview_frames:
            tiles.append(_preview_tile(bgra, count))
        count += 1
    cap.release()

    if tiles:
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        _write_png(preview_path, np.vstack(tiles))

    print(f"frames={count}")
    print(f"out_dir={out_dir}")
    print(f"preview={preview_path}")


if __name__ == "__main__":
    main()
