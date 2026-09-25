"""Canonical kitchen region names and compatibility aliases."""

from __future__ import annotations

import re
from typing import Iterable, Mapping, MutableMapping, TypeVar


KITCHEN_REGION_ALIASES = {
    "box_boundary": "inside_box",
    "box-top": "box_lid_top",
    "box_top": "box_lid_top",
    "box-inside": "inside_box",
    "box_inside": "inside_box",
    "box_storage": "inside_box",
    "cupboard_boundary": "cupboard_shelf",
    "cupboard_boundary_top": "cupboard_shelf",
    "cupboard_lower": "cupboard_shelf",
    "shelf-lower": "cupboard_shelf",
    "shelf_lower": "cupboard_shelf",
    "groceries_boundary": "pantry_area",
    "table_target_area": "table_staging_area",
    "placement_boundary": "table_staging_area",
    # Neutral planner-facing names (prompt v2, docs/PROMPTS.md section 5).
    "table_center_area": "table_staging_area",
    "table_right_area": "pantry_area",
}

GRILL_REGION_ALIASES = {
    "grill-top": "inside_grill",
    "grill_top": "inside_grill",
    "plate-top": "plate_top",
    "plate-boundary": "serving_area",
    "plate_boundary": "serving_area",
    "prep-area": "prep_area",
    "grill_side_area": "prep_area",
}

CANONICAL_KITCHEN_REGION_ORDER = (
    "table",
    "table_staging_area",
    "cupboard_shelf",
    "inside_box",
    "pantry_area",
    "box_lid_top",
)

CANONICAL_GRILL_REGION_ORDER = (
    "table",
    "prep_area",
    "inside_grill",
    "plate_top",
    "serving_area",
    "dish_rack",
)

BOX_STORAGE_REGION = "inside_box"
BOX_LID_TOP_REGION = "box_lid_top"
CUPBOARD_TARGET_REGIONS = ("cupboard_shelf",)
PLANNER_HIDDEN_REGIONS = ()
CANONICAL_REGION_SCENE_OBJECTS = {
    "inside_box": "box_boundary",
    "box_lid_top": "box_lid",
    "cupboard_shelf": "cupboard_boundary",
    "pantry_area": "groceries_boundary",
    "table_staging_area": "placement_boundary",
    "inside_grill": "grill_boundary",
    "plate_top": "plate",
    "serving_area": "plate_boundary",
}

REGION_SEMANTICS = {
    "table": "broad table surface; DO NOT place objects here (use table_staging_area instead)",
    "table_staging_area": "specific staging area on the table for objects that should be temporarily placed on the table",
    "cupboard_shelf": "shelf inside the cupboard for storing groceries",
    "inside_box": "interior storage area of the box for objects that should be put inside the box",
    "pantry_area": "source area on the table where groceries start",
    "box_lid_top": "support surface on top of the box lid for objects resting on the lid",
    "inside_grill": "inside-grill containment area represented by the scene object grill_boundary",
    "prep_area": "preparation area where uncooked meat starts",
    "plate_top": "top surface of the plate for placing cooked meat",
    "serving_area": "serving destination area where the plate should be placed",
    "dish_rack": "rack area where the plate starts",
}


# prompt.version=v2 shows these neutral names instead of purpose-named regions;
# everything else (logs, evaluator, executor) keeps the canonical names.
PLANNER_REGION_NAMES = {
    "table_staging_area": "table_center_area",
    "pantry_area": "table_right_area",
    "prep_area": "grill_side_area",
}


def planner_region_name(region_name: str | None) -> str:
    canonical = normalize_region_name(region_name)
    return PLANNER_REGION_NAMES.get(canonical, canonical)


def planner_action_text(action: str) -> str:
    """Render an action string with planner-facing region names."""
    text = str(action)
    match = re.match(r"^(\s*place\(\s*[^,]+,\s*)([^)]+?)(\s*\)\s*)$", text)
    if not match:
        return text
    return f"{match.group(1)}{planner_region_name(match.group(2))}{match.group(3)}"


def normalize_region_name(region_name: str | None) -> str:
    token = str(region_name or "").strip()
    canonical = KITCHEN_REGION_ALIASES.get(token, token)
    return GRILL_REGION_ALIASES.get(canonical, canonical)


def regions_match_for_target(observed_region: str | None, target_region: str | None) -> bool:
    """Return whether an observed region satisfies the requested target region."""
    observed = normalize_region_name(observed_region)
    target = normalize_region_name(target_region)
    if observed == target:
        return True
    if target == "table_staging_area" and observed in {"table", "pantry_area"}:
        return True
    return False


def region_semantics(region_name: str | None) -> str:
    canonical = normalize_region_name(region_name)
    return REGION_SEMANTICS.get(canonical, "")


def normalize_region_names(region_names: Iterable[str]) -> list[str]:
    seen = set()
    ordered = []
    for region_name in region_names:
        canonical = normalize_region_name(region_name)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        ordered.append(canonical)
    return ordered


def scene_object_for_region(region_name: str) -> str:
    canonical = normalize_region_name(region_name)
    return CANONICAL_REGION_SCENE_OBJECTS.get(canonical, canonical)


_T = TypeVar("_T")


class RegionAliasMap(dict):
    """Dict that stores canonical keys but accepts legacy kitchen region aliases."""

    def __init__(self, values: Mapping[str, _T] | None = None):
        super().__init__()
        if values:
            for key, value in values.items():
                self[key] = value

    def __setitem__(self, key: str, value: _T) -> None:
        super().__setitem__(normalize_region_name(key), value)

    def __getitem__(self, key: str) -> _T:
        return super().__getitem__(normalize_region_name(key))

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            return super().__contains__(normalize_region_name(key))
        return super().__contains__(key)

    def get(self, key: str, default: _T | None = None) -> _T | None:
        return super().get(normalize_region_name(key), default)

    def pop(self, key: str, default=None):
        return super().pop(normalize_region_name(key), default)

    def update(self, values: Mapping[str, _T] | MutableMapping[str, _T], **kwargs) -> None:
        for key, value in dict(values, **kwargs).items():
            self[key] = value
