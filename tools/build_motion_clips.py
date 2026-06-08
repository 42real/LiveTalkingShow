from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.build_speaking_motion_clip import DEFAULT_FFMPEG, build_clip


def read_manifest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise RuntimeError("manifest root must be an object")
    return data


def as_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_value(clip: dict, defaults: dict, key: str, fallback=None):
    if key in clip:
        return clip[key]
    if key in defaults:
        return defaults[key]
    return fallback


def out_root_for_kind(kind: str) -> str:
    return "data/idle_actions" if kind == "idle" else "data/speaking_actions"


def namespace_from_clip(manifest: dict, defaults: dict, clip: dict) -> SimpleNamespace:
    kind = str(get_value(clip, defaults, "kind", get_value(clip, defaults, "state", "speaking"))).strip().lower()
    if kind in {"idle", "silent", "silence", "rest"}:
        kind = "idle"
    else:
        kind = "speaking"

    avatar_id = str(get_value(clip, defaults, "avatar_id", manifest.get("avatar_id", ""))).strip()
    action_id = str(clip.get("action_id", "")).strip()
    if not avatar_id:
        raise RuntimeError(f"avatar_id is required for clip: {clip}")
    if not action_id:
        raise RuntimeError(f"action_id is required for clip: {clip}")

    return SimpleNamespace(
        source=str(clip.get("source", "")).strip(),
        avatar_id=avatar_id,
        action_id=action_id,
        display_name=str(clip.get("display_name", "")).strip(),
        out_root=str(get_value(clip, defaults, "out_root", out_root_for_kind(kind))),
        start=float(get_value(clip, defaults, "start", 0) or 0),
        end=float(get_value(clip, defaults, "end")) if get_value(clip, defaults, "end") not in (None, "") else None,
        fps=float(get_value(clip, defaults, "fps", 25) or 25),
        img_size=int(get_value(clip, defaults, "img_size", 256) or 256),
        pads=list(get_value(clip, defaults, "pads", [0, 10, 0, 0])),
        face_det_batch_size=int(get_value(clip, defaults, "face_det_batch_size", 8) or 8),
        fixed_face_box=get_value(clip, defaults, "fixed_face_box", None),
        max_frames=int(get_value(clip, defaults, "max_frames", 0) or 0),
        tags=str(get_value(clip, defaults, "tags", "idle,teaching" if kind == "idle" else "speaking,teaching")),
        best_for=str(get_value(clip, defaults, "best_for", "")),
        play_mode=str(get_value(clip, defaults, "play_mode", "pingpong" if kind == "idle" else "forward")),
        can_reverse=as_bool(get_value(clip, defaults, "can_reverse", False)),
        weight=float(get_value(clip, defaults, "weight", 1.0) or 1.0),
        min_cycles=int(get_value(clip, defaults, "min_cycles", 1) or 1),
        max_cycles=int(get_value(clip, defaults, "max_cycles", get_value(clip, defaults, "min_cycles", 1)) or 1),
        switch_at_boundary=as_bool(get_value(clip, defaults, "switch_at_boundary", True), True),
        enabled=as_bool(get_value(clip, defaults, "enabled", True), True),
        chroma_key=as_bool(get_value(clip, defaults, "chroma_key", False)),
        use_ffmpeg_cut=as_bool(get_value(clip, defaults, "use_ffmpeg_cut", False)),
        ffmpeg_path=str(get_value(clip, defaults, "ffmpeg_path", DEFAULT_FFMPEG)),
        nosmooth=as_bool(get_value(clip, defaults, "nosmooth", False)),
        no_loop=as_bool(get_value(clip, defaults, "no_loop", False)),
        overwrite=as_bool(get_value(clip, defaults, "overwrite", False)),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build multiple LiveTalking motion clips from a YAML/JSON manifest.")
    parser.add_argument("--manifest", required=True, help="YAML or JSON manifest path.")
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = read_manifest(Path(args.manifest))
    defaults = manifest.get("defaults") or {}
    clips = manifest.get("clips") or []
    if not isinstance(defaults, dict):
        raise RuntimeError("manifest defaults must be an object")
    if not isinstance(clips, list) or not clips:
        raise RuntimeError("manifest clips must be a non-empty list")

    failures = []
    for index, clip in enumerate(clips, start=1):
        if not isinstance(clip, dict):
            failures.append((index, "clip item must be an object"))
            if args.continue_on_error:
                continue
            raise RuntimeError(f"clip {index} must be an object")
        build_args = namespace_from_clip(manifest, defaults, clip)
        print(f"[{index}/{len(clips)}] build {build_args.out_root}/{build_args.avatar_id}/{build_args.action_id}")
        try:
            build_clip(build_args)
        except Exception as exc:
            failures.append((index, str(exc)))
            if not args.continue_on_error:
                raise

    if failures:
        for index, error in failures:
            print(f"clip {index} failed: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
