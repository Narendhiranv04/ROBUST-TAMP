#!/usr/bin/env python3
"""Print per-camera visible task objects for a variant's initial scene (either backend)."""
import os, sys, json
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import sim_backend  # noqa
from llm_pipeline import debug_execution as de
variant = sys.argv[1]
seq = de._load_default_sequence(variant, de.DEFAULT_SEQUENCE_DIR)
de._configure_scene_env(seq, headless=True)
env = de._load_env_for_sequence(seq)
from segmentation_object_detector import SegmentationObjectDetector
det = SegmentationObjectDetector(env)
out = {}
for cam in det.cameras:
    mask = det._capture_mask(cam)
    objs = det._get_objects_from_mask(mask)
    out[cam] = {k: int(v) for k, v in sorted(objs.items())}
print('SEG ' + json.dumps({'backend': sim_backend.BACKEND, 'variant': variant, 'cameras': out}), flush=True)
os._exit(0)
