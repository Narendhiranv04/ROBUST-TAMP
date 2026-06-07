"""Canonical geometric object-to-region resolution."""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Tuple

import numpy as np

from llm_pipeline.region_aliases import (
    PLANNER_HIDDEN_REGIONS,
    normalize_region_name,
)


RegionBounds = Tuple[np.ndarray, np.ndarray]

NON_REGION_OBJECTS = frozenset({"box_lid", "grill_lid", "lid"})

PRIMARY_REGION_PRIORITY = (
    "cupboard_shelf",
    "box_lid_top",
    "inside_box",
    "inside_grill",
    "prep_area",
    "plate_top",
    "serving_area",
    "dish_rack",
    "pantry_area",
    "table_target_area",
    "table",
)
FALLBACK_REGION_PRIORITY = tuple(PLANNER_HIDDEN_REGIONS)

REGION_DESCRIPTIONS = {
    "cupboard_shelf": "on lower cupboard shelf",
    "box_lid_top": "on top of the box lid",
    "inside_box": "inside the box",
    "pantry_area": "in pantry area",
    "table_target_area": "in placement area",
    "table": "on table",
    "inside_grill": "inside grill",
    "prep_area": "in prep area",
    "plate_top": "on plate",
    "serving_area": "in serving area",
    "dish_rack": "at dish rack",
}

OBJECT_REGION_EXCLUSIONS = {
    # plate_top is the live surface of the plate. The plate object itself should
    # never be classified as being "on plate"; it must resolve against external
    # regions such as serving_area or dish_rack.
    ("plate", "plate_top"),
}

REGION_PADDING = {
    "cupboard_shelf": 0.20,
    "box_lid_top": 0.06,
    "inside_box": 0.20,
    "pantry_area": 0.05,
    "table_target_area": 0.05,
    "table": 0.04,
    "inside_grill": 0.08,
    "prep_area": 0.06,
    "plate_top": 0.05,
    "serving_area": 0.05,
    "dish_rack": 0.06,
}

REGION_Z_MARGIN = {
    "cupboard_shelf": (0.20, 0.30),
    "box_lid_top": (0.05, 0.15),
    "inside_box": (0.20, 0.30),
    "pantry_area": (0.15, 0.20),
    "table_target_area": (0.15, 0.20),
    "table": (0.05, 0.12),
    "inside_grill": (0.08, 0.18),
    "prep_area": (0.05, 0.15),
    "plate_top": (0.05, 0.12),
    "serving_area": (0.05, 0.12),
    "dish_rack": (0.10, 0.18),
}


def is_inside_xy(point: Tuple[float, float, float], world_min: np.ndarray, world_max: np.ndarray, padding: float = 0.04) -> bool:
    """Check whether a point lies inside a region footprint."""
    return (
        point[0] >= float(world_min[0]) - padding
        and point[0] <= float(world_max[0]) + padding
        and point[1] >= float(world_min[1]) - padding
        and point[1] <= float(world_max[1]) + padding
    )


def _normalize_region_map(region_map: Mapping[str, RegionBounds]) -> Dict[str, RegionBounds]:
    normalized = {}
    for region_name, bounds in (region_map or {}).items():
        canonical = normalize_region_name(region_name)
        if not canonical:
            continue
        w_min, w_max = bounds
        normalized[canonical] = (np.array(w_min, dtype=float), np.array(w_max, dtype=float))
    return normalized


def _ordered_regions(valid_regions: Iterable[str], region_map: Mapping[str, RegionBounds]) -> list[str]:
    available = set(_normalize_region_map(region_map).keys())
    valid = {normalize_region_name(region) for region in (valid_regions or [])}
    if valid:
        available &= valid

    primary = [region for region in PRIMARY_REGION_PRIORITY if region in available]
    fallback = [region for region in FALLBACK_REGION_PRIORITY if region in available and region not in primary]
    extras = sorted(region for region in available if region not in set(primary + fallback))
    return primary + fallback + extras


def point_matches_region(point: Tuple[float, float, float], region_name: str, bounds: RegionBounds) -> bool:
    """Return whether an object center is geometrically compatible with a region."""
    canonical = normalize_region_name(region_name)
    w_min, w_max = bounds
    if not is_inside_xy(point, w_min, w_max, padding=REGION_PADDING.get(canonical, 0.04)):
        return False

    z_min = float(w_min[2])
    z_max = float(w_max[2])
    below, above = REGION_Z_MARGIN.get(canonical, (0.10, 0.15))
    z = float(point[2])

    if (z_max - z_min) < 0.01:
        return z >= z_min - below and z <= z_min + above
    return z >= z_min - below and z <= z_max + above


def resolve_region(
    obj_pos: Tuple[float, float, float],
    region_map: Mapping[str, RegionBounds],
    valid_regions: Iterable[str] | None = None,
) -> Tuple[str, str]:
    """Resolve one object pose to a canonical region id and description."""
    normalized_map = _normalize_region_map(region_map)
    for region_name in _ordered_regions(valid_regions or normalized_map.keys(), normalized_map):
        if point_matches_region(obj_pos, region_name, normalized_map[region_name]):
            return region_name, REGION_DESCRIPTIONS.get(region_name, region_name)
    return "table", REGION_DESCRIPTIONS["table"]


def resolve_object_regions(
    pose_map: Mapping[str, Tuple[float, float, float]],
    region_map: Mapping[str, RegionBounds],
    valid_regions: Iterable[str] | None = None,
) -> tuple[Dict[str, str], Dict[str, str]]:
    """Resolve every object pose to canonical object-region maps."""
    normalized_map = _normalize_region_map(region_map)
    ordered_regions = _ordered_regions(valid_regions or normalized_map.keys(), normalized_map)
    object_region_map = {}
    object_region_descriptions = {}
    for object_name, pose in (pose_map or {}).items():
        if object_name in NON_REGION_OBJECTS:
            continue
        region_name = None
        description = None
        for candidate in ordered_regions:
            if (object_name, candidate) in OBJECT_REGION_EXCLUSIONS:
                continue
            if point_matches_region(tuple(pose[:3]), candidate, normalized_map[candidate]):
                region_name = candidate
                description = REGION_DESCRIPTIONS.get(candidate, candidate)
                break
        if region_name is None:
            region_name = "table"
            description = REGION_DESCRIPTIONS["table"]
        object_region_map[object_name] = region_name
        object_region_descriptions[object_name] = description
    return object_region_map, object_region_descriptions
