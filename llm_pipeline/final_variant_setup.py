"""Runtime setup and ground truth for the final (Phase 3) variants.

``configure_env`` is called by the pipeline right after the simulator env exists
and before the segmentation adapter is built. It installs the variant's labels
(``chicken`` -> ``raw_meat_1``), registers every variant object with the env and
the detector, and sets the placement areas the executor must place into.

``ground_truth_state`` reads the simulator directly (not the robot's
observations) and returns every variant object's region and which objects lie in
a placement area. The labeled evaluator uses it at the start and the end of a
trial; the planner never sees it.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from evaluation.final_variants import (
    GRILL_PLACEMENT_POSE_XY,
    PLACEMENT_AREAS,
    FinalVariant,
    get_final_variant,
    is_final_variant,
)
from llm_pipeline.object_aliases import set_variant_labels

# Executor region names (kitchen box sampler / grill GT slot poses).
EXECUTOR_PLACEMENT_POSES = {'grill': {'grill-top': GRILL_PLACEMENT_POSE_XY}}


def configure_env(env, variant_id: str) -> Optional[FinalVariant]:
    # Only explicit FINAL.<name> ids: get_final_variant('K1') would also match FINAL.K1.
    spec = get_final_variant(variant_id) if is_final_variant(variant_id) else None
    if spec is None or env is None:
        return None
    set_variant_labels(spec.labels)
    name_to_obj = getattr(env, 'name_to_obj', None)
    if name_to_obj is None:
        name_to_obj = env.name_to_obj = {}
    # Objects removed from the base scene leave None entries behind; drop them so
    # they never become planner symbols.
    for key in [key for key, obj in name_to_obj.items() if obj is None]:
        del name_to_obj[key]
    extra = {}
    for scene_name, label in spec.labels.items():
        obj = env.get_object(scene_name)
        if obj is None:
            raise RuntimeError(f'{spec.variant_id}: scene object {scene_name!r} is missing')
        name_to_obj[scene_name] = obj
        extra[label] = scene_name
    env.extra_task_objects = extra
    env.placement_areas = dict(PLACEMENT_AREAS[spec.scene])
    env.placement_poses = dict(EXECUTOR_PLACEMENT_POSES.get(spec.scene, {}))
    if spec.scene == 'grill':
        env.plate_slot_count = sum(1 for label in spec.labels.values() if 'meat' in label)
    env.final_variant = spec
    return spec


def _is_shape(obj) -> bool:
    try:
        from pyrep.const import ObjectType

        return obj.get_type() == ObjectType.SHAPE
    except Exception:
        return True


def world_aabb(obj) -> Tuple[np.ndarray, np.ndarray]:
    """World axis-aligned bounding box of an object and the shapes below it."""
    parts = [obj]
    try:
        parts += [child for child in obj.get_objects_in_tree() if _is_shape(child)]
    except Exception:
        pass
    lows, highs = [], []
    for part in parts:
        try:
            bb = part.get_bounding_box()
            matrix = part.get_matrix()
        except Exception:
            continue
        if max(abs(v) for v in bb) < 1e-6:
            continue
        corners = np.array([[x, y, z, 1.0] for x in bb[0:2] for y in bb[2:4] for z in bb[4:6]])
        world = (np.asarray(matrix) @ corners.T).T[:, :3]
        lows.append(world.min(axis=0))
        highs.append(world.max(axis=0))
    if not lows:
        pos = np.asarray(obj.get_position(), dtype=float)
        return pos - 0.005, pos + 0.005
    return np.min(lows, axis=0), np.max(highs, axis=0)


def footprint_overlaps(obj, area) -> bool:
    """True when the object's x/y footprint intersects the rectangle (x0, y0, x1, y1)."""
    low, high = world_aabb(obj)
    return bool(low[0] < area[2] and high[0] > area[0] and low[1] < area[3] and high[1] > area[1])


def placement_area_objects(env, spec: FinalVariant) -> Dict[str, List[str]]:
    result = {}
    for region, area in PLACEMENT_AREAS[spec.scene].items():
        result[region] = sorted(
            label for scene_name, label in spec.labels.items()
            if env.get_object(scene_name) is not None and footprint_overlaps(env.get_object(scene_name), area)
        )
    return result


def ground_truth_state(env, spec: FinalVariant, detector, supported_regions: Iterable[str]) -> Dict[str, object]:
    """Region of every variant object from simulator poses, and the placement-area contents."""
    from llm_pipeline.region_aliases import scene_object_for_region
    from llm_pipeline.region_geometry import resolve_object_regions

    region_map = {}
    for region_name in supported_regions:
        bb = detector.get_bounding_box(scene_object_for_region(region_name)) if detector is not None else None
        if bb:
            region_map[region_name] = (np.array(bb[0]), np.array(bb[1]))
    positions = {}
    for scene_name, label in spec.labels.items():
        obj = env.get_object(scene_name)
        if obj is not None:
            positions[label] = tuple(obj.get_position())
    object_region_map, _ = resolve_object_regions(positions, region_map, list(supported_regions))
    return {
        'object_region_map': dict(object_region_map),
        'placement_area_objects': placement_area_objects(env, spec),
        'positions': {label: [round(float(v), 4) for v in pos] for label, pos in positions.items()},
    }


__all__ = ['configure_env', 'footprint_overlaps', 'ground_truth_state', 'placement_area_objects', 'world_aabb']
