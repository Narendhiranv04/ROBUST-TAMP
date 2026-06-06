"""Grill-specific semantic facts derived from geometric scene state."""

from __future__ import annotations

import re
from typing import Iterable, Mapping, Sequence


MEAT_PREFIXES = ("steak", "chicken")
ACTION_PATTERN = re.compile(r"^\s*([A-Za-z0-9_-]+)\((.*?)\)\s*$")
MEAT_STATUS_PATTERN = re.compile(r"^(raw|cooked)\(([A-Za-z0-9_-]+)\)$")


def _is_grill_meat(object_name: str) -> bool:
    for prefix in MEAT_PREFIXES:
        suffix = object_name.removeprefix(prefix)
        if suffix != object_name and (not suffix or suffix.isdigit()):
            return True
    return False


def _normalize_token(token: object) -> str:
    return str(token or "").strip().lower().replace(" ", "_").replace("-", "_")


def _normalize_region(region_name: object) -> str:
    token = _normalize_token(region_name)
    if token in {"grill", "grill_top", "grill_boundary"}:
        return "inside_grill"
    if token in {"plate", "plate_top", "plate_boundary"}:
        return "plate_top"
    return token


def _normalize_action(action_name: object) -> str:
    token = _normalize_token(action_name)
    if token in {"open", "open_lid", "open_grill"}:
        return "open_lid"
    if token in {"close", "close_lid", "close_grill"}:
        return "close_lid"
    return token


def _parse_action(action: object) -> dict[str, object] | None:
    match = ACTION_PATTERN.match(str(action or "").strip())
    if not match:
        return None
    args = [
        _normalize_token(part)
        for part in match.group(2).split(",")
        if str(part).strip()
    ]
    return {"action": _normalize_action(match.group(1)), "args": args}


def _parsed_actions(completed_actions: Iterable[object] | None) -> list[dict[str, object]]:
    return [
        parsed
        for parsed in (_parse_action(action) for action in (completed_actions or ()))
        if parsed is not None
    ]


def _place_to_region_after(
    actions: Sequence[dict[str, object]],
    start_index: int,
    object_name: str,
    region_name: str,
) -> int | None:
    target_obj = _normalize_token(object_name)
    target_region = _normalize_region(region_name)
    for index in range(max(0, int(start_index)), len(actions)):
        action = actions[index]
        if action.get("action") != "place":
            continue
        args = list(action.get("args") or [])
        if len(args) >= 2 and args[0] == target_obj and _normalize_region(args[1]) == target_region:
            return index
    return None


def _action_after(
    actions: Sequence[dict[str, object]],
    start_index: int,
    action_name: str,
    object_name: str,
) -> int | None:
    target_action = _normalize_action(action_name)
    target_obj = _normalize_token(object_name)
    for index in range(max(0, int(start_index)), len(actions)):
        action = actions[index]
        args = list(action.get("args") or [])
        if action.get("action") == target_action and args and args[0] == target_obj:
            return index
    return None


def _has_completed_cooking_cycle(actions: Sequence[dict[str, object]], meat_name: str) -> bool:
    inside_index = _place_to_region_after(actions, 0, meat_name, "inside_grill")
    if inside_index is None:
        return False
    close_index = _action_after(actions, inside_index + 1, "close_lid", "grill_lid")
    if close_index is None:
        return False
    open_index = _action_after(actions, close_index + 1, "open_lid", "grill_lid")
    return open_index is not None


def initially_cooked_meats_from_regions(object_region_map: Mapping[str, str]) -> set[str]:
    return {
        _normalize_token(object_name)
        for object_name, region_name in (object_region_map or {}).items()
        if _is_grill_meat(_normalize_token(object_name))
        and _normalize_region(region_name) == "inside_grill"
    }


def unplaced_inside_grill_meats_from_regions(
    object_region_map: Mapping[str, str],
    completed_actions: Iterable[object] | None = None,
) -> set[str]:
    """Return meats found inside the grill that the robot did not place there."""
    parsed_actions = _parsed_actions(completed_actions)
    meats = set()
    for object_name, region_name in (object_region_map or {}).items():
        object_name = _normalize_token(object_name)
        if (
            _is_grill_meat(object_name)
            and _normalize_region(region_name) == "inside_grill"
            and _place_to_region_after(parsed_actions, 0, object_name, "inside_grill") is None
        ):
            meats.add(object_name)
    return meats


def derive_grill_semantic_facts(
    object_region_map: Mapping[str, str],
    *,
    lid_open: bool | None = None,
    completed_actions: Iterable[object] | None = None,
    initially_cooked_meats: Iterable[str] | None = None,
) -> list[str]:
    """Return grill facts using inside_grill geometry from grill_boundary."""
    facts = []
    parsed_actions = _parsed_actions(completed_actions)
    initially_cooked = {_normalize_token(meat) for meat in (initially_cooked_meats or ())}
    if lid_open is True:
        facts.append("grill_lid_open")
    elif lid_open is False:
        facts.append("grill_lid_closed")

    for object_name, region_name in sorted((object_region_map or {}).items()):
        object_name = _normalize_token(object_name)
        region_name = _normalize_region(region_name)
        if _is_grill_meat(object_name):
            if region_name == "inside_grill":
                facts.append(f"inside_grill({object_name})")
            elif region_name == "prep_area":
                facts.append(f"in_prep_area({object_name})")
            elif region_name == "plate_top":
                facts.append(f"on_plate({object_name})")
            elif region_name == "table":
                facts.append(f"on_table({object_name})")
            was_placed_inside = _place_to_region_after(parsed_actions, 0, object_name, "inside_grill") is not None
            cooked = (
                object_name in initially_cooked
                or _has_completed_cooking_cycle(parsed_actions, object_name)
                or (region_name == "inside_grill" and not was_placed_inside)
            )
            facts.append(f'{"cooked" if cooked else "raw"}({object_name})')
        elif object_name == "plate":
            if region_name == "dish_rack":
                facts.append("plate_at_dish_rack")
            elif region_name == "serving_area":
                facts.append("plate_at_boundary")

    return facts


def grill_meat_status_from_facts(facts: Iterable[str]) -> dict[str, str]:
    """Return a compact debug view like {'chicken': 'cooked'} from semantic facts."""
    status_by_object: dict[str, str] = {}
    for fact in facts or ():
        match = MEAT_STATUS_PATTERN.match(str(fact).strip())
        if not match:
            continue
        status, object_name = match.groups()
        status_by_object[_normalize_token(object_name)] = status
    return dict(sorted(status_by_object.items()))


def infer_grill_lid_open(env) -> bool | None:
    """Best-effort lid-open check for grill scenes."""
    lid_joint = getattr(env, "lid_joint", None)
    if lid_joint is None:
        return None
    try:
        current = float(lid_joint.get_joint_position())
    except Exception:
        return None

    closed = float(getattr(env, "_closed_lid_angle", 0.0))
    return abs(current - closed) > 0.25
