###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
# 
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  
#       http://www.apache.org/licenses/LICENSE-2.0
# 
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################
#
#  Wav2Lip 数字人 — 迁移自 lipreal.py + lipasr.py
#

import math
import json
import torch
import numpy as np

import os
import time
import cv2
import glob
import pickle
import copy
import random

import queue
from queue import Queue
from threading import Thread, Event, RLock
import torch.multiprocessing as mp

from avatars.audio_features.mel import MelASR
import asyncio
from av import AudioFrame, VideoFrame
from avatars.wav2lip.models import Wav2Lip
from avatars.base_avatar import BaseAvatar

from tqdm import tqdm
from utils.logger import logger
from utils.image import read_imgs, mirror_index
from utils.device import initialize_device
from registry import register

device = initialize_device()
logger.info('Using {} for inference.'.format(device))
WAV2LIP_FACE_SIZE = 256
MOTION_POOL_TOKENS = {"auto", "pool", "all", "*"}
MOTION_DEFAULT_TOKENS = {"", "default", "none", "null"}
MOTION_PLAY_MODES = {"forward", "pingpong", "reverse", "random_direction"}

def _parse_runtime_pads(default_pads):
    raw = os.getenv("LIVETALKING_RUNTIME_PADS", "").strip()
    if not raw:
        return list(default_pads)
    values = raw.replace("，", ",").replace(" ", ",").split(",")
    pads = []
    for value in values:
        if not value:
            continue
        pads.append(int(value))
        if len(pads) == 4:
            break
    while len(pads) < 4:
        pads.append(0)
    return [max(-300, min(300, value)) for value in pads]

def _bool_metadata(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

def _int_metadata(value, default=1, min_value=1, max_value=100):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))

def _float_metadata(value, default=1.0, min_value=0.0, max_value=1000.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))

def _normalize_play_mode(value, default="forward"):
    play_mode = str(value or default).strip().lower()
    return play_mode if play_mode in MOTION_PLAY_MODES else default

def _motion_frame_order(length, metadata, rng=None):
    if length <= 0:
        return []
    random_source = rng or random
    play_mode = _normalize_play_mode(metadata.get("play_mode"), "forward")
    if play_mode == "random_direction":
        can_reverse = _bool_metadata(metadata.get("can_reverse"), False)
        play_mode = random_source.choice(["forward", "reverse"]) if can_reverse else "forward"
    elif play_mode == "reverse" and not _bool_metadata(metadata.get("can_reverse"), False):
        play_mode = "forward"

    if length == 1:
        order = [0]
    elif play_mode == "pingpong":
        order = list(range(length)) + list(range(length - 2, -1, -1))
    elif play_mode == "reverse":
        order = list(range(length - 1, -1, -1))
    else:
        order = list(range(length))
    return order

def _load(checkpoint_path):
    if device == 'cuda':
        checkpoint = torch.load(checkpoint_path)
    else:
        checkpoint = torch.load(checkpoint_path,
                                map_location=lambda storage, loc: storage)
    return checkpoint

def load_model(path):
    model = Wav2Lip()
    logger.info("Load checkpoint from: {}".format(path))
    checkpoint = _load(path)
    s = checkpoint["state_dict"]
    new_s = {}
    for k, v in s.items():
        new_s[k.replace('module.', '')] = v
    model.load_state_dict(new_s)

    model = model.to(device)
    return model.eval()

def _load_avatar_bundle(avatar_path):
    full_imgs_path = f"{avatar_path}/full_imgs" 
    face_imgs_path = f"{avatar_path}/face_imgs" 
    coords_path = f"{avatar_path}/coords.pkl"
    metadata_path = f"{avatar_path}/metadata.json"
    
    with open(coords_path, 'rb') as f:
        coord_list_cycle = pickle.load(f)
    frame_list_cycle = None
    input_img_list = glob.glob(os.path.join(full_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_img_list = sorted(input_img_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    frame_list_cycle = read_imgs(input_img_list)
    input_face_list = glob.glob(os.path.join(face_imgs_path, '*.[jpJP][pnPN]*[gG]'))
    input_face_list = sorted(input_face_list, key=lambda x: int(os.path.splitext(os.path.basename(x))[0]))
    face_list_cycle = read_imgs(input_face_list)
    metadata = {}
    if os.path.exists(metadata_path):
        with open(metadata_path, 'r', encoding='utf-8-sig') as f:
            metadata = json.load(f)

    return frame_list_cycle,face_list_cycle,coord_list_cycle,metadata

def load_avatar(avatar_id):
    return _load_avatar_bundle(f"./data/avatars/{avatar_id}")

def load_motion_clips(avatar_id, root_name="speaking_actions"):
    root = f"./data/{root_name}/{avatar_id}"
    if not os.path.isdir(root):
        return {}

    clips = {}
    for action_id in sorted(os.listdir(root)):
        action_path = os.path.join(root, action_id)
        if not os.path.isdir(action_path):
            continue
        try:
            frames, faces, coords, metadata = _load_avatar_bundle(action_path)
        except Exception as exc:
            logger.warning("skip %s motion clip %s: %s", root_name, action_path, exc)
            continue
        kind = "idle" if root_name == "idle_actions" else "speaking"
        metadata["action_id"] = action_id
        metadata.setdefault("display_name", action_id)
        metadata.setdefault("kind", kind)
        metadata["play_mode"] = _normalize_play_mode(
            metadata.get("play_mode"),
            "pingpong" if kind == "idle" else "forward",
        )
        metadata["can_reverse"] = _bool_metadata(metadata.get("can_reverse"), False)
        metadata["weight"] = _float_metadata(metadata.get("weight"), 1.0, 0.0, 1000.0)
        metadata["min_cycles"] = _int_metadata(metadata.get("min_cycles"), 1, 1, 100)
        metadata["max_cycles"] = _int_metadata(metadata.get("max_cycles"), metadata["min_cycles"], 1, 100)
        if metadata["max_cycles"] < metadata["min_cycles"]:
            metadata["max_cycles"] = metadata["min_cycles"]
        metadata["switch_at_boundary"] = _bool_metadata(metadata.get("switch_at_boundary"), True)
        metadata["enabled"] = _bool_metadata(metadata.get("enabled"), True)
        clips[action_id] = {
            "frames": frames,
            "faces": faces,
            "coords": coords,
            "metadata": metadata,
        }
    return clips

def load_speaking_motion_clips(avatar_id):
    return load_motion_clips(avatar_id, "speaking_actions")

def load_idle_motion_clips(avatar_id):
    return load_motion_clips(avatar_id, "idle_actions")

@torch.no_grad()
def warm_up(batch_size,model,modelres):
    # 预热函数
    logger.info('warmup model...')
    img_batch = torch.ones(batch_size, 6, modelres, modelres).to(device)
    mel_batch = torch.ones(batch_size, 1, 80, 16).to(device)
    model(mel_batch, img_batch)

@register("avatar", "wav2lip")
class LipReal(BaseAvatar):
    @torch.no_grad()
    def __init__(self, opt, model, avatar):
        super().__init__(opt)

        #self.fps = opt.fps # 20 ms per frame
        
        # self.batch_size = opt.batch_size
        # self.idx = 0
        # self.res_frame_queue = Queue(self.batch_size*2)
        self.model = model
        self.face_input_size = WAV2LIP_FACE_SIZE
        self.frame_list_cycle,self.face_list_cycle,self.coord_list_cycle,self.metadata = avatar
        self.motion_clips = load_speaking_motion_clips(getattr(opt, "avatar_id", ""))
        self.idle_motion_clips = load_idle_motion_clips(getattr(opt, "avatar_id", ""))
        self.current_motion_clip_id = None
        self.current_idle_clip_id = None
        self._motion_lock = RLock()
        self._motion_rng = random.Random()
        self._motion_player = {
            "render_kind": "idle",
            "pending_kind": None,
            "current_clip": None,
            "current_action_id": "",
            "cursor": 0,
            "order": [],
            "total_frames": 0,
            "cycles": 1,
            "last_action": {"speaking": "", "idle": ""},
            "sequence_index": {"speaking": 0, "idle": 0},
        }
        if self.motion_clips:
            logger.info("loaded speaking motion clips: %s", sorted(self.motion_clips.keys()))
        if self.idle_motion_clips:
            logger.info("loaded idle motion clips: %s", sorted(self.idle_motion_clips.keys()))
        generation_pads = self.metadata.get("generation_pads", self.metadata.get("baked_pads", [0, 0, 0, 0]))
        self.generation_pads = self._normalize_pads(generation_pads)
        self.runtime_pads = _parse_runtime_pads(self.generation_pads)
        logger.info("wav2lip generation pads: %s", self.generation_pads)
        logger.info("wav2lip current pads: %s", self.runtime_pads)

        self.asr = MelASR(opt,self)
        self.asr.warm_up()

    def _normalize_pads(self, pads):
        values = [int(v) for v in pads[:4]]
        while len(values) < 4:
            values.append(0)
        return [max(-300, min(300, v)) for v in values]

    def set_runtime_pads(self, pads):
        self.runtime_pads = self._normalize_pads(pads)

    def reload_speaking_motions(self):
        with self._motion_lock:
            self.motion_clips = load_speaking_motion_clips(getattr(self.opt, "avatar_id", ""))
            if self.current_motion_clip_id not in self.motion_clips and not self._is_pool_selection(self.current_motion_clip_id):
                self.current_motion_clip_id = None
            self._stop_current_clip_if_kind("speaking")
        logger.info("reloaded speaking motion clips: %s", sorted(self.motion_clips.keys()))
        return self.list_speaking_motions()

    def reload_idle_motions(self):
        with self._motion_lock:
            self.idle_motion_clips = load_idle_motion_clips(getattr(self.opt, "avatar_id", ""))
            if self.current_idle_clip_id not in self.idle_motion_clips and not self._is_pool_selection(self.current_idle_clip_id):
                self.current_idle_clip_id = None
            self._stop_current_clip_if_kind("idle")
        logger.info("reloaded idle motion clips: %s", sorted(self.idle_motion_clips.keys()))
        return self.list_idle_motions()

    def list_speaking_motions(self):
        selection = self._selection_id("speaking")
        current_action = self._motion_player.get("current_action_id") if self._motion_player.get("render_kind") == "speaking" else ""
        return [
            {
                **clip["metadata"],
                "frame_count": len(clip["frames"]),
                "current": action_id == self.current_motion_clip_id or action_id == current_action,
                "selected": action_id == self.current_motion_clip_id,
                "pool_selected": self._is_pool_selection(selection),
            }
            for action_id, clip in sorted(self.motion_clips.items())
        ]

    def list_idle_motions(self):
        selection = self._selection_id("idle")
        current_action = self._motion_player.get("current_action_id") if self._motion_player.get("render_kind") == "idle" else ""
        return [
            {
                **clip["metadata"],
                "frame_count": len(clip["frames"]),
                "current": action_id == self.current_idle_clip_id or action_id == current_action,
                "selected": action_id == self.current_idle_clip_id,
                "pool_selected": self._is_pool_selection(selection),
            }
            for action_id, clip in sorted(self.idle_motion_clips.items())
        ]

    def set_speaking_motion(self, action_id):
        action_id = str(action_id or "").strip()
        if action_id.lower() in MOTION_DEFAULT_TOKENS:
            with self._motion_lock:
                self.current_motion_clip_id = None
                self._stop_current_clip_if_kind("speaking")
            logger.info("speaking motion clip cleared")
            return {"action_id": "", "display_name": "default", "current": True}
        if self._is_pool_selection(action_id):
            with self._motion_lock:
                self.current_motion_clip_id = "auto"
                self._stop_current_clip_if_kind("speaking")
            logger.info("speaking motion pool selected")
            return {"action_id": "auto", "display_name": "自动素材池", "current": True, "selection_mode": "pool"}
        if action_id not in self.motion_clips:
            raise ValueError(f"speaking motion clip not found: {action_id}")
        with self._motion_lock:
            self.current_motion_clip_id = action_id
            self._stop_current_clip_if_kind("speaking")
        clip = self.motion_clips[action_id]
        logger.info("speaking motion clip selected: %s", action_id)
        return {
            **clip["metadata"],
            "frame_count": len(clip["frames"]),
            "current": True,
            "selection_mode": "fixed",
        }

    def set_idle_motion(self, action_id):
        action_id = str(action_id or "").strip()
        if action_id.lower() in MOTION_DEFAULT_TOKENS:
            with self._motion_lock:
                self.current_idle_clip_id = None
                self._stop_current_clip_if_kind("idle")
            logger.info("idle motion clip cleared")
            return {"action_id": "", "display_name": "default", "current": True}
        if self._is_pool_selection(action_id):
            with self._motion_lock:
                self.current_idle_clip_id = "auto"
                self._stop_current_clip_if_kind("idle")
            logger.info("idle motion pool selected")
            return {"action_id": "auto", "display_name": "自动素材池", "current": True, "selection_mode": "pool"}
        if action_id not in self.idle_motion_clips:
            raise ValueError(f"idle motion clip not found: {action_id}")
        with self._motion_lock:
            self.current_idle_clip_id = action_id
            self._stop_current_clip_if_kind("idle")
        clip = self.idle_motion_clips[action_id]
        logger.info("idle motion clip selected: %s", action_id)
        return {
            **clip["metadata"],
            "frame_count": len(clip["frames"]),
            "current": True,
            "selection_mode": "fixed",
        }

    def _is_pool_selection(self, action_id):
        return str(action_id or "").strip().lower() in MOTION_POOL_TOKENS

    def _selection_id(self, kind):
        return self.current_idle_clip_id if kind == "idle" else self.current_motion_clip_id

    def _clip_pool(self, kind):
        return self.idle_motion_clips if kind == "idle" else self.motion_clips

    def _motion_strategy(self, kind):
        env_name = "LIVETALKING_IDLE_MOTION_STRATEGY" if kind == "idle" else "LIVETALKING_SPEAKING_MOTION_STRATEGY"
        strategy = os.getenv(env_name, os.getenv("LIVETALKING_MOTION_STRATEGY", "weighted_no_repeat")).strip().lower()
        allowed = {"sequence", "random", "weighted_random", "no_repeat_random", "weighted_no_repeat"}
        return strategy if strategy in allowed else "weighted_no_repeat"

    def _stop_current_clip_if_kind(self, kind):
        if self._motion_player.get("render_kind") == kind:
            self._motion_player["current_clip"] = None
            self._motion_player["current_action_id"] = ""
            self._motion_player["cursor"] = 0
            self._motion_player["order"] = []
            self._motion_player["total_frames"] = 0

    def _motion_enabled_clips(self, kind):
        clips = []
        for action_id, clip in sorted(self._clip_pool(kind).items()):
            if _bool_metadata(clip.get("metadata", {}).get("enabled"), True):
                clips.append((action_id, clip))
        return clips

    def _select_motion_clip(self, kind):
        selection = self._selection_id(kind)
        pool = self._clip_pool(kind)
        if not selection:
            return "", None, "default"
        if not self._is_pool_selection(selection):
            return selection, pool.get(selection), "fixed"

        candidates = self._motion_enabled_clips(kind)
        if not candidates:
            return "", None, "pool"

        strategy = self._motion_strategy(kind)
        last_action = self._motion_player["last_action"].get(kind, "")
        weighted_candidates = candidates
        if strategy in {"no_repeat_random", "weighted_no_repeat"} and len(candidates) > 1:
            weighted_candidates = [(action_id, clip) for action_id, clip in candidates if action_id != last_action]

        if strategy == "sequence":
            index = self._motion_player["sequence_index"].get(kind, 0) % len(candidates)
            self._motion_player["sequence_index"][kind] = index + 1
            action_id, clip = candidates[index]
        elif strategy in {"random", "no_repeat_random"}:
            action_id, clip = self._motion_rng.choice(weighted_candidates)
        else:
            weights = [max(0.0, _float_metadata(clip.get("metadata", {}).get("weight"), 1.0, 0.0, 1000.0)) for _, clip in weighted_candidates]
            if not any(weights):
                weights = [1.0 for _ in weighted_candidates]
            action_id, clip = self._motion_rng.choices(weighted_candidates, weights=weights, k=1)[0]
        return action_id, clip, f"pool:{strategy}"

    def _start_motion_clip(self, kind, target_kind):
        action_id, clip, mode = self._select_motion_clip(kind)
        if not clip:
            fallback_key = (kind, target_kind, mode)
            if self._motion_player.get("fallback_key") != fallback_key:
                logger.info("motion scheduler fallback motion=%s audio_target=%s mode=%s", kind, target_kind, mode)
            self._motion_player.update({
                "render_kind": kind,
                "current_clip": None,
                "current_action_id": "",
                "cursor": 0,
                "order": [],
                "total_frames": 0,
                "cycles": 1,
                "fallback_key": fallback_key,
            })
            return

        metadata = clip.get("metadata", {})
        order = _motion_frame_order(len(clip["frames"]), metadata, self._motion_rng)
        if not order:
            self._motion_player.update({
                "render_kind": kind,
                "current_clip": None,
                "current_action_id": "",
                "cursor": 0,
                "order": [],
                "total_frames": 0,
                "cycles": 1,
            })
            logger.warning("motion scheduler empty clip kind=%s action=%s", kind, action_id)
            return
        min_cycles = _int_metadata(metadata.get("min_cycles"), 1, 1, 100)
        max_cycles = _int_metadata(metadata.get("max_cycles"), min_cycles, 1, 100)
        if max_cycles < min_cycles:
            max_cycles = min_cycles
        cycles = self._motion_rng.randint(min_cycles, max_cycles)
        self._motion_player.update({
            "render_kind": kind,
            "current_clip": clip,
            "current_action_id": action_id,
            "cursor": 0,
            "order": order,
            "total_frames": len(order) * cycles,
            "cycles": cycles,
            "fallback_key": None,
        })
        self._motion_player["last_action"][kind] = action_id
        logger.info(
            "motion scheduler start motion=%s audio_target=%s action=%s mode=%s play_mode=%s cycles=%d frames=%d",
            kind,
            target_kind,
            action_id,
            mode,
            metadata.get("play_mode", "forward"),
            cycles,
            len(order) * cycles,
        )

    def _current_clip_complete(self):
        clip = self._motion_player.get("current_clip")
        if not clip:
            return True
        return self._motion_player.get("cursor", 0) >= self._motion_player.get("total_frames", 0)

    def _request_render_kind(self, target_kind):
        render_kind = self._motion_player.get("render_kind", "idle")
        current_clip = self._motion_player.get("current_clip")
        if target_kind == render_kind:
            if self._motion_player.get("pending_kind"):
                logger.info(
                    "motion scheduler clear pending motion=%s audio_target=%s pending_motion=%s",
                    render_kind,
                    target_kind,
                    self._motion_player.get("pending_kind"),
                )
            self._motion_player["pending_kind"] = None
            return
        if current_clip and _bool_metadata(current_clip.get("metadata", {}).get("switch_at_boundary"), True):
            if self._motion_player.get("pending_kind") != target_kind:
                self._motion_player["pending_kind"] = target_kind
                logger.info(
                    "motion scheduler pending motion=%s audio_target=%s action=%s cursor=%d/%d",
                    render_kind,
                    target_kind,
                    self._motion_player.get("current_action_id", ""),
                    self._motion_player.get("cursor", 0),
                    self._motion_player.get("total_frames", 0),
                )
            return
        logger.info("motion scheduler immediate motion switch motion=%s audio_target=%s", render_kind, target_kind)
        self._motion_player["render_kind"] = target_kind
        self._motion_player["pending_kind"] = None
        self._motion_player["current_clip"] = None
        self._motion_player["current_action_id"] = ""
        self._motion_player["cursor"] = 0

    def _next_motion_frame(self, target_kind, fallback_index):
        self._request_render_kind(target_kind)
        if self._current_clip_complete():
            previous_kind = self._motion_player.get("render_kind", target_kind)
            previous_action = self._motion_player.get("current_action_id", "")
            next_kind = self._motion_player.get("pending_kind") or target_kind
            if previous_action and next_kind != previous_kind:
                logger.info(
                    "motion scheduler boundary switch %s/%s -> %s",
                    previous_kind,
                    previous_action,
                    next_kind,
                )
            self._motion_player["pending_kind"] = None
            self._start_motion_clip(next_kind, target_kind)

        clip = self._motion_player.get("current_clip")
        render_kind = self._motion_player.get("render_kind", target_kind)
        if not clip:
            return self._default_frame_item(render_kind, target_kind, fallback_index)

        order = self._motion_player.get("order") or [0]
        cursor = self._motion_player.get("cursor", 0)
        frame_idx = order[cursor % len(order)]
        self._motion_player["cursor"] = cursor + 1
        return {
            "idx": frame_idx,
            "render_context": {
                "speaking": render_kind == "speaking",
                "motion_speaking": render_kind == "speaking",
                "audio_speaking": target_kind == "speaking",
                "motion_kind": render_kind,
                "audio_kind": target_kind,
                "render_kind": render_kind,
                "target_kind": target_kind,
                "action_id": self._motion_player.get("current_action_id", ""),
                "clip": clip,
                "cursor": cursor,
                "total_frames": self._motion_player.get("total_frames", 0),
            },
        }

    def _default_frame_item(self, render_kind, target_kind, fallback_index):
        length = len(self.frame_list_cycle)
        frame_idx = mirror_index(length, fallback_index)
        return {
            "idx": frame_idx,
            "render_context": {
                "speaking": render_kind == "speaking",
                "motion_speaking": render_kind == "speaking",
                "audio_speaking": target_kind == "speaking",
                "motion_kind": render_kind,
                "audio_kind": target_kind,
                "render_kind": render_kind,
                "target_kind": target_kind,
                "action_id": "",
                "clip": None,
                "cursor": fallback_index,
                "total_frames": 0,
            },
        }

    def prepare_render_batch(self, speaking: bool, batch_size: int, start_index: int):
        target_kind = "speaking" if speaking else "idle"
        frame_items = []
        with self._motion_lock:
            for i in range(batch_size):
                frame_items.append(self._next_motion_frame(target_kind, start_index + i))
        return frame_items, start_index + batch_size

    def _active_motion_clip(self):
        if self.current_motion_clip_id:
            return self.motion_clips.get(self.current_motion_clip_id)
        return None

    def _active_idle_clip(self):
        if self.current_idle_clip_id:
            return self.idle_motion_clips.get(self.current_idle_clip_id)
        return None

    def get_render_context(self, speaking: bool | None = None):
        if speaking:
            return {
                "speaking": True,
                "action_id": self.current_motion_clip_id,
                "clip": self._active_motion_clip(),
            }
        return {
            "speaking": False,
            "action_id": self.current_idle_clip_id,
            "clip": self._active_idle_clip(),
        }

    def _clip_from_context(self, speaking: bool | None = None, render_context=None):
        if isinstance(render_context, dict):
            return render_context.get("clip")
        return self._active_motion_clip() if speaking else self._active_idle_clip()

    def _batch_frame_item(self, render_context, batch_index, fallback_index, fallback_length):
        if isinstance(render_context, dict) and isinstance(render_context.get("frame_items"), list):
            frame_items = render_context["frame_items"]
            if batch_index < len(frame_items) and isinstance(frame_items[batch_index], dict):
                return frame_items[batch_index]
        idx = mirror_index(fallback_length, fallback_index + batch_index)
        return {
            "idx": idx,
            "render_context": render_context,
        }

    def get_avatar_length(self, speaking: bool | None = None, render_context=None):
        clip = self._clip_from_context(speaking=speaking, render_context=render_context)
        if clip:
            return len(clip["frames"])
        return len(self.frame_list_cycle)

    def get_silent_frame(self, idx: int, audiotype: int | None = None, render_context=None):
        clip = self._clip_from_context(speaking=False, render_context=render_context)
        if clip:
            return copy.deepcopy(clip["frames"][idx])
        return copy.deepcopy(self.frame_list_cycle[idx])

    def _paste_delta_pads(self):
        return [current - base for current, base in zip(self.runtime_pads, self.generation_pads)]

    def get_runtime_config(self):
        source_h, source_w = self.frame_list_cycle[0].shape[:2]
        base_bbox = self.coord_list_cycle[0]
        paste_delta_pads = self._paste_delta_pads()
        return {
            "pads": list(self.runtime_pads),
            "generation_pads": list(self.generation_pads),
            "baked_pads": list(self.generation_pads),
            "paste_delta_pads": paste_delta_pads,
            "effective_pads": list(self.runtime_pads),
            "source_width": source_w,
            "source_height": source_h,
            "base_bbox": self._bbox_to_xyxy(base_bbox, [0, 0, 0, 0], source_w, source_h),
            "padded_bbox": self._bbox_to_xyxy(base_bbox, paste_delta_pads, source_w, source_h),
        }

    def _bbox_to_xyxy(self, bbox, pads, source_w, source_h):
        y1, y2, x1, x2 = bbox
        top, bottom, left, right = pads
        y1 = max(0, min(source_h - 1, int(y1) - top))
        y2 = max(y1 + 1, min(source_h, int(y2) + bottom))
        x1 = max(0, min(source_w - 1, int(x1) - left))
        x2 = max(x1 + 1, min(source_w, int(x2) + right))
        return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
    
    def inference_batch(self, index, audiofeat_batch, render_context=None):
        # 这里的 index 是针对当前 avatar 的索引
        # 返回一个 batch 的推理结果，batch 大小由 self.batch_size 决定
        fallback_clip = self._clip_from_context(speaking=True, render_context=render_context)
        fallback_face_list = fallback_clip["faces"] if fallback_clip else self.face_list_cycle
        fallback_length = len(fallback_face_list)
        img_batch = []
        for i in range(self.batch_size):
            frame_item = self._batch_frame_item(render_context, i, index, fallback_length)
            item_context = frame_item.get("render_context")
            clip = self._clip_from_context(speaking=True, render_context=item_context)
            face_list_cycle = clip["faces"] if clip else self.face_list_cycle
            idx = int(frame_item.get("idx", mirror_index(len(face_list_cycle), index + i)))
            face = face_list_cycle[idx]
            if face.ndim == 3 and face.shape[2] == 4:
                face = cv2.cvtColor(face, cv2.COLOR_BGRA2BGR)
            if face.shape[:2] != (self.face_input_size, self.face_input_size):
                face = cv2.resize(face, (self.face_input_size, self.face_input_size))
            img_batch.append(face)
        img_batch, audiofeat_batch = np.asarray(img_batch), np.asarray(audiofeat_batch)

        img_masked = img_batch.copy()
        img_masked[:, self.face_input_size//2:] = 0

        img_batch = np.concatenate((img_masked, img_batch), axis=3) / 255.
        audiofeat_batch = np.reshape(audiofeat_batch, [len(audiofeat_batch), audiofeat_batch.shape[1], audiofeat_batch.shape[2], 1])
        
        img_batch = torch.FloatTensor(np.transpose(img_batch, (0, 3, 1, 2))).to(device)
        audiofeat_batch = torch.FloatTensor(np.transpose(audiofeat_batch, (0, 3, 1, 2))).to(device)

        with torch.no_grad():
            pred = self.model(audiofeat_batch, img_batch)
        pred = pred.cpu().numpy().transpose(0, 2, 3, 1) * 255.
        return pred

    def paste_back_frame(self,pred_frame,idx:int, render_context=None):
        clip = self._clip_from_context(speaking=True, render_context=render_context)
        if clip:
            bbox = clip["coords"][idx]
            combine_frame = copy.deepcopy(clip["frames"][idx])
            paste_pads = [0, 0, 0, 0]
        else:
            bbox = self.coord_list_cycle[idx]
            combine_frame = copy.deepcopy(self.frame_list_cycle[idx])
            paste_pads = self._paste_delta_pads()
        source_h, source_w = combine_frame.shape[:2]
        padded = self._bbox_to_xyxy(bbox, paste_pads, source_w, source_h)
        x1, y1, x2, y2 = padded["x1"], padded["y1"], padded["x2"], padded["y2"]
        res_frame = cv2.resize(pred_frame.astype(np.uint8),(x2-x1,y2-y1))
        if combine_frame.ndim == 3 and combine_frame.shape[2] == 4:
            combine_frame[y1:y2, x1:x2, :3] = res_frame
        else:
            combine_frame[y1:y2, x1:x2] = res_frame
        return combine_frame
