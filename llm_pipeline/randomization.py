"""Seeded initial-pose randomization (``scene.randomization = pose_jitter``).

Each trial jitters the free objects of its variant by up to +/-3 cm in x and y
and +/-20 degrees in yaw, drawn from ``numpy.random.default_rng(seed)``.
Objects are fixed when the executor or the variant depends on their exact pose:
the plate, lids and containers (their motions replay recorded paths), the
scripted cupboard mug (``mug3``), objects inside the cupboard, and the hidden
contents of the box and the grill. A sample is rejected when the object touches
another movable object or does not stay on its support (height change after
settling of more than 1 cm); after ``MAX_ATTEMPTS`` rejections the object keeps
its original pose. Works through the PyRep object API, so it applies to both
simulator backends.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional

import numpy as np

XY_RANGE_M = 0.03
YAW_RANGE_DEG = 20.0
MAX_ATTEMPTS = 30
SETTLE_STEPS = 40
MAX_HEIGHT_CHANGE_M = 0.01

# Free (jittered) objects per variant, by scene object name.
FREE_OBJECTS: Dict[str, tuple] = {
    'K1': ('spam', 'mug2'),
    'K2': ('sugar', 'mug2'),
    'K3': ('mug1', 'sugar', 'mug2'),
    'G1': ('chicken',),
    'G2': ('chicken', 'steak1'),
    'G3': ('chicken', 'steak1'),
}
# Every movable object per variant (free and fixed), used for the overlap check.
MOVABLE_OBJECTS: Dict[str, tuple] = {
    'K1': ('spam', 'soup', 'mug2', 'mug3'),
    'K2': ('soup', 'mug2', 'mug3', 'sugar', 'mug1'),
    'K3': ('spam', 'soup', 'mug2', 'mug3', 'sugar', 'mug1'),
    'G1': ('chicken', 'plate', 'phone'),
    'G2': ('chicken', 'steak', 'steak1', 'plate'),
    'G3': ('chicken', 'steak', 'plate', 'steak1', 'phone'),
}


# Final variants (evaluation/final_variants.py): the table objects are free; the
# cupboard mug, the plate and every hidden object keep their pose.
FINAL_KITCHEN_FREE = ('spam', 'sugar', 'mug1', 'mug2')


def _variant_objects(variant: str):
    from evaluation.final_variants import get_final_variant, is_final_variant

    if not is_final_variant(variant):
        return FREE_OBJECTS.get(variant, ()), MOVABLE_OBJECTS.get(variant, ())
    spec = get_final_variant(variant)
    hidden = {scene for scene, label in spec.labels.items() if label in {h.label for h in spec.hidden}}
    movable = tuple(sorted(set(spec.labels) | ({'plate'} if spec.scene == 'grill' else set())))
    if spec.scene == 'grill':
        free = ('chicken',)
    else:
        free = FINAL_KITCHEN_FREE + tuple(sorted(s for s in spec.labels if s.startswith('soup') and s not in hidden))
    return free, movable


def _lookup(env, name):
    return (getattr(env, 'name_to_obj', {}) or {}).get(name)


def _tree_handles(obj) -> set:
    handles = {int(obj.get_handle())}
    try:
        handles.update(int(child.get_handle()) for child in obj.get_objects_in_tree())
    except Exception:
        pass
    return handles


def _tree(obj) -> List:
    items = [obj]
    try:
        items.extend(obj.get_objects_in_tree())
    except Exception:
        pass
    return items


def _touches(obj, others: Iterable) -> Optional[str]:
    own = _tree_handles(obj)
    for other_name, other in others:
        if int(other.get_handle()) in own:
            continue
        for part in _tree(obj):
            for other_part in _tree(other):
                if int(other_part.get_handle()) in own:
                    continue
                try:
                    if part.check_collision(other_part):
                        return other_name
                except Exception:
                    continue
    return None


def _settle(env, steps: int = SETTLE_STEPS) -> None:
    for _ in range(steps):
        env.pr.step()


def apply_pose_jitter(env, variant_id: str, seed: int, xy_range: float = XY_RANGE_M,
                      yaw_range_deg: float = YAW_RANGE_DEG) -> Dict[str, object]:
    """Jitter the variant's free objects; return a record for the trial log."""
    variant = str(variant_id).strip().upper()
    rng = np.random.default_rng(int(seed))
    record: Dict[str, object] = {
        'mode': 'pose_jitter', 'seed': int(seed), 'xy_range_m': xy_range, 'yaw_range_deg': yaw_range_deg,
        'objects': {}, 'fixed': [],
    }
    free_names, movable_names = _variant_objects(variant)
    movable = [(name, _lookup(env, name)) for name in movable_names]
    movable = [(name, obj) for name, obj in movable if obj is not None]
    free = list(free_names)
    record['fixed'] = [name for name, _ in movable if name not in free]
    for name in free:
        obj = _lookup(env, name)
        if obj is None:
            record['objects'][name] = {'status': 'missing'}
            continue
        base_pos = np.array(obj.get_position(), dtype=float)
        base_ori = np.array(obj.get_orientation(), dtype=float)
        others = [(other_name, other) for other_name, other in movable if other_name != name]
        entry = {'status': 'kept_original', 'attempts': 0}
        for attempt in range(1, MAX_ATTEMPTS + 1):
            dx, dy = rng.uniform(-xy_range, xy_range, size=2)
            dyaw = rng.uniform(-yaw_range_deg, yaw_range_deg)
            obj.set_position([base_pos[0] + dx, base_pos[1] + dy, base_pos[2] + 0.002])
            obj.set_orientation([base_ori[0], base_ori[1], base_ori[2] + math.radians(dyaw)])
            _settle(env)
            pos = np.array(obj.get_position(), dtype=float)
            touching = _touches(obj, others)
            dropped = abs(pos[2] - base_pos[2]) > MAX_HEIGHT_CHANGE_M
            if touching is None and not dropped:
                entry = {
                    'status': 'jittered', 'attempts': attempt, 'dx': round(float(dx), 4), 'dy': round(float(dy), 4),
                    'dyaw_deg': round(float(dyaw), 2), 'position': [round(float(v), 4) for v in pos],
                }
                break
            entry['attempts'] = attempt
            entry['last_rejection'] = f'touches {touching}' if touching else 'left its support'
            obj.set_position(base_pos.tolist())
            obj.set_orientation(base_ori.tolist())
            _settle(env)
        record['objects'][name] = entry
    return record


__all__ = ['FREE_OBJECTS', 'MOVABLE_OBJECTS', 'apply_pose_jitter']
