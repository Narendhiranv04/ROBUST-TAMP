"""Metrics helpers for direct-action LLM pipeline evaluation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from evaluation.canonical_variants import get_variant_spec
from evaluation.metrics import aggregate_model_records, collect_failure_occurrences
from llm_pipeline.region_aliases import BOX_STORAGE_REGION, normalize_region_name


ACTION_PATTERN = re.compile(r'^\s*([A-Za-z0-9_-]+)\((.*?)\)\s*$')
MUG_OBJECTS = {'mug1', 'mug2', 'mug3', 'mug4'}
GROCERY_OBJECTS = {'soup', 'can_of_beans', 'mustard', 'spam', 'sugar', 'crackers'}
MEAT_OBJECTS = {'steak', 'steak1', 'steak2', 'chicken', 'chicken1', 'chicken2'}
GRILL_TABLE_OBJECTS = MEAT_OBJECTS | {'spam'}
PLATE_OBJECTS = {'plate'}
BOX_REGIONS = {'inside_box', 'box_storage', 'box_boundary', 'box_top', 'box_inside', 'box-top', 'box-inside'}
PLACEMENT_REGIONS = {'table_target_area', 'placement_boundary'}
CUPBOARD_REGIONS = {'cupboard_shelf', 'cupboard_lower', 'cupboard_boundary', 'cupboard_boundary_top', 'cupboard'}
PLATE_TOP_REGIONS = {'plate', 'plate-top', 'plate_top'}
SERVING_REGIONS = {'plate_boundary', 'plate-boundary', 'serving_area'}
GRILL_REGIONS = {'inside_grill', 'grill', 'grill-top', 'grill_top', 'grill_boundary'}
TABLE_REGIONS = {'table', 'prep_area'}


def _normalize_token(token: Optional[str]) -> str:
    return (token or '').strip().lower().replace(' ', '_')


def _normalize_action_name(name: str) -> str:
    token = _normalize_token(name).replace('-', '_')
    if token in {'pick', 'pickup', 'pick_up', 'grasp'}:
        return 'pick'
    if token in {'place', 'put', 'put_down', 'putdown'}:
        return 'place'
    if token in {'open', 'open_lid', 'openlid', 'open_box', 'open_box_lid'}:
        return 'open_lid'
    if token in {'open_grill'}:
        return 'open_grill'
    if token in {'close', 'close_lid', 'closelid', 'close_grill', 'close_grill_lid'}:
        return 'close_lid'
    return token


def _normalize_region(region: Optional[str]) -> str:
    token = normalize_region_name(_normalize_token(region))
    if token in BOX_REGIONS:
        return BOX_STORAGE_REGION
    if token in PLACEMENT_REGIONS:
        return 'table_target_area'
    if token in CUPBOARD_REGIONS:
        return 'cupboard_shelf'
    if token in PLATE_TOP_REGIONS:
        return 'plate_top'
    if token in SERVING_REGIONS:
        return 'serving_area'
    if token in GRILL_REGIONS:
        return 'inside_grill'
    if token in TABLE_REGIONS:
        return 'table'
    return token


def parse_action_string(action: Any) -> Optional[Dict[str, Any]]:
    text = str(action).strip()

    match = ACTION_PATTERN.match(text)
    if not match:
        return None
    name = _normalize_action_name(match.group(1))
    raw_args = match.group(2).strip()
    args = []
    if raw_args:
        args = [_normalize_token(part) for part in raw_args.split(',') if part.strip()]
    return {'action': name, 'args': args, 'raw': text}


def _bucket_for_transfer(object_name: str, region_name: str) -> Optional[str]:
    obj = _normalize_token(object_name)
    region = _normalize_region(region_name)
    if obj in MUG_OBJECTS and region in {'table_target_area', 'table'}:
        return 'mug_to_placement'
    if obj in MUG_OBJECTS and region == BOX_STORAGE_REGION:
        return 'mug_to_box'
    if obj in GROCERY_OBJECTS and region == 'cupboard_shelf':
        return 'grocery_to_cupboard'
    if obj in PLATE_OBJECTS and region == 'serving_area':
        return 'plate_to_boundary'
    if obj in MEAT_OBJECTS and region == 'plate_top':
        return 'meat_to_plate'
    if obj in MEAT_OBJECTS and region == 'inside_grill':
        return 'meat_to_grill'
    if obj in GRILL_TABLE_OBJECTS and region == 'table':
        return 'meat_to_table'
    return None


def collapse_actions_to_subtasks(actions: Sequence[Any]) -> List[str]:
    parsed = [parse_action_string(action) for action in actions]
    parsed = [item for item in parsed if item is not None]
    subtasks: List[str] = []
    idx = 0
    while idx < len(parsed):
        current = parsed[idx]
        name = current['action']
        args = current['args']

        if name in {'open', 'open_lid', 'open_grill'}:
            target = args[0] if args else ''
            subtasks.append('open_grill' if name == 'open_grill' or target == 'grill_lid' else 'open_lid')
            idx += 1
            continue
        if name in {'close', 'close_lid', 'close_grill'}:
            target = args[0] if args else ''
            if name == 'close_grill' or target == 'grill_lid':
                subtasks.append('close_grill')
            idx += 1
            continue
        if name == 'pick' and idx + 1 < len(parsed):
            next_idx = idx + 1
            nxt = parsed[next_idx] if next_idx < len(parsed) else None
            if nxt and nxt['action'] == 'place' and len(args) == 1 and len(nxt['args']) >= 2:
                obj = args[0]
                place_obj = nxt['args'][0]
                region = nxt['args'][1]
                if obj == place_obj:
                    bucket = _bucket_for_transfer(obj, region)
                    if bucket:
                        subtasks.append(bucket)
                        idx = next_idx + 1
                        continue
        idx += 1
    return subtasks


def score_variant_completion(variant_id: str, completed_actions: Sequence[Any]) -> Dict[str, Any]:
    spec = get_variant_spec(variant_id)
    expected = dict(spec.expected_subtask_buckets)
    observed_buckets = collapse_actions_to_subtasks(completed_actions)
    observed_counts = Counter(observed_buckets)
    bucket_breakdown: Dict[str, Dict[str, int]] = {}
    matched_total = 0
    for bucket_name, expected_count in expected.items():
        observed_count = int(observed_counts.get(bucket_name, 0))
        matched_count = min(observed_count, int(expected_count))
        matched_total += matched_count
        bucket_breakdown[bucket_name] = {
            'expected': int(expected_count),
            'observed': observed_count,
            'matched': matched_count,
        }

    extras = {
        bucket_name: int(count)
        for bucket_name, count in observed_counts.items()
        if bucket_name not in expected or count > expected.get(bucket_name, 0)
    }
    gt_total = int(spec.gt_total_subtasks or 0)
    completion_rate = float(matched_total / gt_total) if gt_total else 0.0
    return {
        'variant_id': spec.variant_id,
        'gt_total_subtasks': gt_total,
        'completed_gt_subtasks': int(matched_total),
        'subtask_completion_rate': completion_rate,
        'observed_subtasks': observed_buckets,
        'observed_subtask_counts': dict(observed_counts),
        'bucket_breakdown': bucket_breakdown,
        'extra_observed_subtasks': extras,
    }


__all__ = [
    'aggregate_model_records',
    'collect_failure_occurrences',
    'collapse_actions_to_subtasks',
    'parse_action_string',
    'score_variant_completion',
]
