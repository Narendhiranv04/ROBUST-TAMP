"""Scoring and aggregation helpers for evaluation runs."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from evaluation.canonical_variants import VARIANTS, get_variant_spec
from evaluation.metric_definitions import summarize as summarize_metric_definitions
from llm_pipeline.failures import LegacyMessageCategory


ACTION_PATTERN = re.compile(r'^\s*([A-Za-z0-9_-]+)\((.*?)\)\s*$')
MUG_OBJECTS = {
    'mug_box', 'mug_inside_box', 'mug_table', 'mug_cupboard',
    'mug1', 'mug2', 'mug3', 'mug4',
}
GROCERY_OBJECTS = {'can_of_beans', 'mustard', 'spam', 'sugar', 'crackers'}
MEAT_OBJECTS = {'steak', 'steak1', 'steak2', 'chicken', 'chicken1', 'chicken2'}
GRILL_NON_TARGET_OBJECTS = {'phone'}
PLATE_OBJECTS = {'plate'}
BOX_REGIONS = {'box_boundary', 'box_top', 'box_inside', 'box-top', 'box-inside'}
PLACEMENT_REGIONS = {'placement_boundary'}
CUPBOARD_REGIONS = {'cupboard_boundary', 'cupboard_boundary_top', 'cupboard', 'groceries_boundary'}
PLATE_TOP_REGIONS = {'plate', 'plate-top', 'plate_top'}
SERVING_REGIONS = {'plate_boundary', 'plate-boundary', 'plate_boundary_top', 'serving_area'}
GRILL_REGIONS = {'inside_grill', 'grill', 'grill_top', 'grill-top', 'grill_boundary'}
TABLE_REGIONS = {'table', 'prep_area'}
GENERIC_TERMINAL_REASONS = {
    'max replans exceeded',
    'replan failed',
    'initial planning failed',
    'unexpected exit',
}


def _safe_mean(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    return float(sum(values) / len(values))


def _safe_std(values: Sequence[float]) -> Optional[float]:
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    mean_val = _safe_mean(values)
    variance = sum((float(v) - mean_val) ** 2 for v in values) / (len(values) - 1)
    return float(math.sqrt(max(0.0, variance)))


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
    if token in {'close', 'close_lid', 'closelid', 'close_box', 'close_grill'}:
        return 'close_lid'
    if token in {'open_grill'}:
        return 'open_grill'
    if token in {'close_grill_lid'}:
        return 'close_grill'
    return token


def _normalize_region(region: Optional[str]) -> str:
    token = _normalize_token(region)
    if token in BOX_REGIONS:
        return 'box_boundary'
    if token in PLACEMENT_REGIONS:
        return 'placement_boundary'
    if token in CUPBOARD_REGIONS:
        return 'cupboard_boundary'
    if token in PLATE_TOP_REGIONS:
        return 'plate_top'
    if token in SERVING_REGIONS:
        return 'serving_area'
    if token in GRILL_REGIONS:
        return 'grill'
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
    if obj in MUG_OBJECTS and region in {'placement_boundary', 'table'}:
        return 'mug_to_placement'
    if obj in MUG_OBJECTS and region == 'box_boundary':
        return 'mug_to_box'
    if obj in GROCERY_OBJECTS and region == 'cupboard_boundary':
        return 'grocery_to_cupboard'
    if obj in PLATE_OBJECTS and region == 'serving_area':
        return 'plate_to_boundary'
    if obj in MEAT_OBJECTS and region == 'plate_top':
        return 'meat_to_plate'
    if obj in MEAT_OBJECTS and region == 'grill':
        return 'meat_to_grill'
    if obj in GRILL_NON_TARGET_OBJECTS and region == 'table':
        return 'non_target_to_table'
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
        if name in {'open_lid', 'open_grill'}:
            target = args[0] if args else ''
            subtasks.append('open_grill' if name == 'open_grill' or target == 'grill_lid' else 'open_lid')
            idx += 1
            continue
        if name in {'close_lid', 'close_grill'}:
            target = args[0] if args else ''
            if name == 'close_grill' or target == 'grill_lid':
                subtasks.append('close_grill')
            idx += 1
            continue
        if name == 'pick' and idx + 1 < len(parsed):
            next_idx = idx + 1
            while next_idx < len(parsed) and parsed[next_idx]['action'] == 'move':
                next_idx += 1
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


def classify_failure_message(message: Optional[str]) -> str:
    text = (message or '').strip().lower()
    if not text:
        return LegacyMessageCategory.UNKNOWN
    if 'new_object_introduced_in_scene' in text or 'newly visible object' in text:
        return LegacyMessageCategory.NEW_OBJECT_INTRODUCED_IN_SCENE
    if 'cannot open lid' in text or 'on top' in text or 'blocked by' in text or 'object_blocked' in text:
        return LegacyMessageCategory.OBJECT_BLOCKED
    if 'lid is closed' in text or 'lid_closed' in text or 'cannot pick' in text and 'closed' in text:
        return LegacyMessageCategory.LID_CLOSED
    if 'not found' in text or 'object_not_found' in text:
        return LegacyMessageCategory.OBJECT_NOT_FOUND
    if 'orphaned' in text and 'place' in text:
        return LegacyMessageCategory.ORPHAN_PLACE
    if 'pick/place different objects' in text or 'pick mismatch' in text or 'pick_place_mismatch' in text:
        return LegacyMessageCategory.PICK_MISMATCH
    if 'grasp failed' in text or "didn't move" in text or 'not grasped' in text:
        return LegacyMessageCategory.GRASP_FAILED
    if 'placement failed' in text or 'not in target region' in text:
        return LegacyMessageCategory.PLACEMENT_FAILED
    if 'valid joint configuration' in text or 'inverse kinematics' in text or 'ik solution' in text:
        return LegacyMessageCategory.NO_IK_SOLUTION
    if 'motion planner failed' in text or 'no motion plan' in text:
        return LegacyMessageCategory.NO_MOTION_PLAN
    if 'no valid grasp' in text or 'no grasp found' in text:
        return LegacyMessageCategory.NO_GRASP_FOUND
    if 'pddl' in text and 'no plan' in text:
        return LegacyMessageCategory.PDDL_NO_PLAN
    if 'collision' in text:
        return LegacyMessageCategory.COLLISION_DETECTED
    if 'dropped' in text or 'fell during transport' in text or 'object fell' in text:
        return LegacyMessageCategory.OBJECT_DROPPED
    if text in GENERIC_TERMINAL_REASONS:
        return LegacyMessageCategory.UNKNOWN
    return LegacyMessageCategory.UNKNOWN


def collect_failure_occurrences(cycles: Sequence[Dict[str, Any]], failure_reason: Optional[str]) -> Dict[str, Any]:
    messages: List[str] = []
    for cycle in cycles or []:
        error_message = (cycle or {}).get('error_message')
        if error_message:
            messages.append(str(error_message))
    normalized_failure_reason = (failure_reason or '').strip()
    if normalized_failure_reason and normalized_failure_reason.lower() not in GENERIC_TERMINAL_REASONS:
        messages.append(normalized_failure_reason)
    categories = [classify_failure_message(message) for message in messages]
    counts = Counter(categories)
    return {
        'messages': messages,
        'categories': categories,
        'counts': dict(counts),
    }


def _aggregate_failure_counts(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total_occurrences: Counter = Counter()
    trials_affected: Counter = Counter()
    for record in records:
        structured_events = list(record.get('structured_events') or [])
        if structured_events:
            categories = [
                str(event.get('event_type') or event.get('failure_id') or 'unknown')
                for event in structured_events
                if bool(event.get('is_failure'))
            ]
        else:
            failure_info = record.get('failure_occurrences', {}) or {}
            categories = [str(cat) for cat in failure_info.get('categories', [])]
            categories = [cat for cat in categories if cat != 'new_object_introduced_in_scene']
        total_occurrences.update(categories)
        trials_affected.update(set(categories))
    categories = sorted(set(total_occurrences) | set(trials_affected))
    return {
        'categories': categories,
        'total_occurrences': {name: int(total_occurrences.get(name, 0)) for name in categories},
        'trials_affected': {name: int(trials_affected.get(name, 0)) for name in categories},
    }


def _sum_record_field(records: Sequence[Dict[str, Any]], field_name: str) -> int:
    return int(sum(int(record.get(field_name) or 0) for record in records))


def _implicit_non_target_rate(records: Sequence[Dict[str, Any]]) -> Optional[float]:
    values = [
        1.0 if record.get('implicit_non_target_handling_success') else 0.0
        for record in records
        if record.get('implicit_non_target_handling_success') is not None
    ]
    return _safe_mean(values)


def aggregate_gt_records(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_variant: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_variant[str(record.get('variant_id'))].append(record)

    variant_summaries: Dict[str, Dict[str, Any]] = {}
    success_values: List[float] = []
    completion_values: List[float] = []
    partial_goal_values: List[float] = []
    execution_times: List[float] = []
    for variant_id in sorted(by_variant):
        rows = by_variant[variant_id]
        success = [1.0 if row.get('episode_success') else 0.0 for row in rows]
        completion = [float(row.get('subtask_completion_rate', 0.0)) for row in rows]
        partial_goal_completion = [
            float(row.get('partial_goal_completion', 0.0))
            for row in rows
            if row.get('partial_goal_completion') is not None
        ]
        times = [float(row.get('execution_time_s', 0.0)) for row in rows if row.get('execution_time_s') is not None]
        variant_summaries[variant_id] = {
            'trials': len(rows),
            'success_rate': _safe_mean(success),
            'mean_subtask_completion_rate': _safe_mean(completion),
            'mean_partial_goal_completion': _safe_mean(partial_goal_completion),
            'mean_execution_time_s': _safe_mean(times),
            'std_execution_time_s': _safe_std(times),
            'gt_total_subtasks': rows[0].get('gt_total_subtasks'),
            'action_sequence_length': rows[0].get('action_sequence_length'),
        }
        success_values.extend(success)
        completion_values.extend(completion)
        partial_goal_values.extend(partial_goal_completion)
        execution_times.extend(times)

    return {
        'record_count': len(records),
        'supported_variants': sorted(by_variant),
        'variants': variant_summaries,
        'overall': {
            'success_rate': _safe_mean(success_values),
            'mean_subtask_completion_rate': _safe_mean(completion_values),
            'mean_partial_goal_completion': _safe_mean(partial_goal_values),
            'mean_execution_time_s': _safe_mean(execution_times),
            'std_execution_time_s': _safe_std(execution_times),
        },
    }


def aggregate_model_records(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    by_variant: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_variant[str(record.get('variant_id'))].append(record)

    variant_summaries: Dict[str, Dict[str, Any]] = {}
    success_values: List[float] = []
    raw_success_values: List[float] = []
    completion_values: List[float] = []
    partial_goal_values: List[float] = []
    replans_values: List[float] = []
    planner_invocations: List[float] = []
    planner_times: List[float] = []
    mean_planner_times: List[float] = []
    episode_times: List[float] = []

    for variant_id in sorted(by_variant):
        rows = by_variant[variant_id]
        success = [1.0 if row.get('episode_success') else 0.0 for row in rows]
        raw_success = [1.0 if row.get('raw_episode_success') else 0.0 for row in rows]
        completion = [float(row.get('subtask_completion_rate', 0.0)) for row in rows]
        partial_goal_completion = [
            float(row.get('partial_goal_completion', 0.0))
            for row in rows
            if row.get('partial_goal_completion') is not None
        ]
        replans = [float(row.get('total_replans', 0)) for row in rows]
        invocations = [float(row.get('planner_invocations', 0)) for row in rows]
        total_planner_times = [
            float(row.get('total_planner_time_s', 0.0))
            for row in rows
            if row.get('total_planner_time_s') is not None
        ]
        per_invocation_times = [
            float(row.get('mean_planner_time_per_invocation_s', 0.0))
            for row in rows
            if row.get('mean_planner_time_per_invocation_s') is not None
        ]
        times = [float(row.get('episode_time_s', 0.0)) for row in rows if row.get('episode_time_s') is not None]
        definitions = summarize_metric_definitions(rows)
        variant_summaries[variant_id] = {
            'trials': len(rows),
            # plan.md Phase 1, step 5 (evaluation/metric_definitions.py)
            'task_success_rate': definitions['task_success_rate'],
            'partial_goal_completion': definitions['partial_goal_completion'],
            'evaluated_trials': definitions['evaluated_trials'],
            'infrastructure_trials': definitions['infrastructure_trials'],
            'episode_success_rate': _safe_mean(success),
            'raw_execution_success_rate': _safe_mean(raw_success),
            'mean_subtask_completion_rate': _safe_mean(completion),
            'mean_partial_goal_completion': _safe_mean(partial_goal_completion),
            'std_partial_goal_completion': _safe_std(partial_goal_completion),
            'mean_completed_gt_subtasks': _safe_mean([float(row.get('completed_gt_subtasks', 0)) for row in rows]),
            'mean_replans': _safe_mean(replans),
            'discovery_triggered_replans': _sum_record_field(rows, 'discovery_triggered_replans'),
            'failure_triggered_replans': _sum_record_field(rows, 'failure_triggered_replans'),
            'other_triggered_replans': _sum_record_field(rows, 'other_triggered_replans'),
            'mean_planner_invocations': _safe_mean(invocations),
            'mean_total_planner_time_s': _safe_mean(total_planner_times),
            'std_total_planner_time_s': _safe_std(total_planner_times),
            'mean_planner_time_per_invocation_s': _safe_mean(per_invocation_times),
            'std_planner_time_per_invocation_s': _safe_std(per_invocation_times),
            'mean_episode_time_s': _safe_mean(times),
            'std_episode_time_s': _safe_std(times),
            'implicit_non_target_handling_rate': _implicit_non_target_rate(rows),
            'failure_counts': _aggregate_failure_counts(rows),
            'gt_total_subtasks': rows[0].get('gt_total_subtasks'),
            'action_sequence_length': rows[0].get('action_sequence_length'),
            'model_alias': rows[0].get('model_alias'),
            'model_type': rows[0].get('model_type'),
            'prompt_mode': rows[0].get('prompt_mode'),
        }
        success_values.extend(success)
        raw_success_values.extend(raw_success)
        completion_values.extend(completion)
        partial_goal_values.extend(partial_goal_completion)
        replans_values.extend(replans)
        planner_invocations.extend(invocations)
        planner_times.extend(total_planner_times)
        mean_planner_times.extend(per_invocation_times)
        episode_times.extend(times)

    return {
        'record_count': len(records),
        'supported_variants': sorted(by_variant),
        'variants': variant_summaries,
        'overall': {
            **{
                key: value
                for key, value in summarize_metric_definitions(records).items()
                if key in ('task_success_rate', 'partial_goal_completion', 'evaluated_trials', 'infrastructure_trials')
            },
            'episode_success_rate': _safe_mean(success_values),
            'raw_execution_success_rate': _safe_mean(raw_success_values),
            'mean_subtask_completion_rate': _safe_mean(completion_values),
            'mean_partial_goal_completion': _safe_mean(partial_goal_values),
            'std_partial_goal_completion': _safe_std(partial_goal_values),
            'mean_replans': _safe_mean(replans_values),
            'discovery_triggered_replans': _sum_record_field(records, 'discovery_triggered_replans'),
            'failure_triggered_replans': _sum_record_field(records, 'failure_triggered_replans'),
            'other_triggered_replans': _sum_record_field(records, 'other_triggered_replans'),
            'mean_planner_invocations': _safe_mean(planner_invocations),
            'mean_total_planner_time_s': _safe_mean(planner_times),
            'std_total_planner_time_s': _safe_std(planner_times),
            'mean_planner_time_per_invocation_s': _safe_mean(mean_planner_times),
            'std_planner_time_per_invocation_s': _safe_std(mean_planner_times),
            'mean_episode_time_s': _safe_mean(episode_times),
            'std_episode_time_s': _safe_std(episode_times),
            'implicit_non_target_handling_rate': _implicit_non_target_rate(records),
        },
        'failure_counts': _aggregate_failure_counts(records),
    }
