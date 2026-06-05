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
GRILL_NON_TARGET_OBJECTS = {'phone'}
PLATE_OBJECTS = {'plate'}
BOX_REGIONS = {'inside_box', 'box_storage', 'box_boundary', 'box_top', 'box_inside', 'box-top', 'box-inside'}
PLACEMENT_REGIONS = {'table_target_area', 'placement_boundary'}
CUPBOARD_REGIONS = {'cupboard_shelf', 'cupboard_lower', 'cupboard_boundary', 'cupboard_boundary_top', 'cupboard'}
PLATE_TOP_REGIONS = {'plate', 'plate-top', 'plate_top'}
SERVING_REGIONS = {'plate_boundary', 'plate-boundary', 'serving_area'}
GRILL_REGIONS = {'inside_grill', 'grill', 'grill-top', 'grill_top', 'grill_boundary'}
TABLE_REGIONS = {'table', 'prep_area'}

KITCHEN_FINAL_GOALS = {
    'K1': {
        'inside_box': ('mug2', 'mug3'),
        'cupboard_shelf': ('soup', 'spam'),
    },
    'K2': {
        'inside_box': ('mug2', 'mug3'),
        'cupboard_shelf': ('sugar', 'soup'),
    },
    'K3': {
        'inside_box': ('mug1', 'mug2', 'mug3'),
        'cupboard_shelf': ('sugar', 'soup'),
    },
}

GRILL_FINAL_GOALS = {
    'G1': {
        'plate_top': ('chicken',),
        'serving_area': ('plate',),
        'table': ('phone',),
    },
    'G2': {
        'plate_top': ('steak', 'chicken', 'steak1'),
        'serving_area': ('plate',),
    },
    'G3': {
        'plate_top': ('steak', 'chicken', 'steak1'),
        'serving_area': ('plate',),
        'table': ('phone',),
    },
}

GRILL_OUTSIDE_COOKED_MEATS = {
    'G1': ('chicken',),
    'G2': ('chicken', 'steak1'),
    'G3': ('chicken', 'steak1'),
}


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


def _normalized_object_region_map(object_region_map: Optional[Dict[str, Any]]) -> Dict[str, str]:
    return {
        _normalize_token(obj_name): _normalize_region(str(region_name))
        for obj_name, region_name in (object_region_map or {}).items()
        if str(obj_name).strip()
    }


def _validator_result(
    variant_id: str,
    validator: str,
    details: Optional[Dict[str, Any]] = None,
    missing: Optional[List[str]] = None,
    satisfied: Optional[List[str]] = None,
    missing_relations: Optional[List[str]] = None,
    satisfied_relations: Optional[List[str]] = None,
    missing_procedures: Optional[List[str]] = None,
    satisfied_procedures: Optional[List[str]] = None,
) -> Dict[str, Any]:
    details = dict(details or {})
    if missing_relations is None and missing_procedures is None:
        missing_relations = list(missing or [])
        missing_procedures = []
    if satisfied_relations is None and satisfied_procedures is None:
        satisfied_relations = list(satisfied or [])
        satisfied_procedures = []

    missing_relations = list(missing_relations or [])
    satisfied_relations = list(satisfied_relations or [])
    missing_procedures = list(missing_procedures or [])
    satisfied_procedures = list(satisfied_procedures or [])
    missing = missing_relations + missing_procedures
    satisfied = satisfied_relations + satisfied_procedures

    satisfied_count = len(satisfied)
    missing_count = len(missing)
    required_count = satisfied_count + missing_count
    satisfied_relation_count = len(satisfied_relations)
    missing_relation_count = len(missing_relations)
    required_relation_count = satisfied_relation_count + missing_relation_count
    satisfied_procedure_count = len(satisfied_procedures)
    missing_procedure_count = len(missing_procedures)
    required_procedure_count = satisfied_procedure_count + missing_procedure_count
    return {
        'success': not missing,
        'variant_id': variant_id,
        'validator': validator,
        'missing': missing,
        'satisfied': satisfied,
        'missing_relations': missing_relations,
        'satisfied_relations': satisfied_relations,
        'missing_procedures': missing_procedures,
        'satisfied_procedures': satisfied_procedures,
        'required_relation_count': required_relation_count,
        'satisfied_relation_count': satisfied_relation_count,
        'missing_relation_count': missing_relation_count,
        'required_procedure_count': required_procedure_count,
        'satisfied_procedure_count': satisfied_procedure_count,
        'missing_procedure_count': missing_procedure_count,
        'required_condition_count': required_count,
        'satisfied_condition_count': satisfied_count,
        'missing_condition_count': missing_count,
        'partial_goal_completion': float(satisfied_count / required_count) if required_count else 0.0,
        'details': details,
    }


def validate_kitchen_goal_from_scene(
    variant_id: str,
    object_region_map: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    variant = str(variant_id or '').strip().upper()
    goals = KITCHEN_FINAL_GOALS.get(variant)
    if goals is None:
        return _validator_result(
            variant,
            'kitchen_scene_state',
            {'object_region_map': dict(object_region_map or {})},
            missing=[f'No kitchen validator configured for variant {variant or "(none)"}'],
            satisfied=[],
        )

    normalized = _normalized_object_region_map(object_region_map)
    missing_relations: List[str] = []
    satisfied_relations: List[str] = []
    for expected_region, objects in goals.items():
        target_region = _normalize_region(expected_region)
        for obj_name in objects:
            obj = _normalize_token(obj_name)
            observed_region = normalized.get(obj)
            check = f'{obj} in {target_region}'
            if observed_region == target_region:
                satisfied_relations.append(check)
            else:
                missing_relations.append(f'{obj} is in {observed_region or "unknown"}, expected {target_region}')

    return _validator_result(
        variant,
        'kitchen_scene_state',
        {
            'object_region_map': normalized,
            'expected_regions': goals,
        },
        missing_relations=missing_relations,
        satisfied_relations=satisfied_relations,
    )


def _action_after(actions: Sequence[Dict[str, Any]], start_index: int, action_name: str, arg0: Optional[str] = None) -> Optional[int]:
    for index in range(max(0, int(start_index)), len(actions)):
        action = actions[index]
        if action.get('action') != action_name:
            continue
        args = action.get('args') or []
        if arg0 is not None and (not args or args[0] != arg0):
            continue
        return index
    return None


def _place_to_region_after(
    actions: Sequence[Dict[str, Any]],
    start_index: int,
    object_name: str,
    region_name: str,
) -> Optional[int]:
    obj = _normalize_token(object_name)
    target_region = _normalize_region(region_name)
    for index in range(max(0, int(start_index)), len(actions)):
        action = actions[index]
        if action.get('action') != 'place':
            continue
        args = action.get('args') or []
        if len(args) < 2:
            continue
        if args[0] == obj and _normalize_region(args[1]) == target_region:
            return index
    return None


def _has_cooking_sequence(actions: Sequence[Dict[str, Any]], meat_name: str) -> bool:
    inside_index = _place_to_region_after(actions, 0, meat_name, 'inside_grill')
    if inside_index is None:
        return False
    close_index = _action_after(actions, inside_index + 1, 'close_lid', 'grill_lid')
    if close_index is None:
        return False
    open_index = _action_after(actions, close_index + 1, 'open_lid', 'grill_lid')
    if open_index is None:
        return False
    plate_index = _place_to_region_after(actions, open_index + 1, meat_name, 'plate_top')
    return plate_index is not None


def validate_grill_goal_from_scene_and_history(
    variant_id: str,
    object_region_map: Optional[Dict[str, Any]],
    completed_actions: Sequence[Any],
) -> Dict[str, Any]:
    variant = str(variant_id or '').strip().upper()
    final_goals = GRILL_FINAL_GOALS.get(variant)
    cooked_meats = GRILL_OUTSIDE_COOKED_MEATS.get(variant)
    if final_goals is None or cooked_meats is None:
        return _validator_result(
            variant,
            'grill_scene_state_temporal',
            {
                'object_region_map': dict(object_region_map or {}),
                'completed_actions': [str(action) for action in completed_actions],
            },
            missing=[f'No grill validator configured for variant {variant or "(none)"}'],
            satisfied=[],
        )

    normalized = _normalized_object_region_map(object_region_map)
    parsed_actions = [parse_action_string(action) for action in completed_actions]
    parsed_actions = [action for action in parsed_actions if action is not None]

    missing_relations: List[str] = []
    satisfied_relations: List[str] = []
    for expected_region, objects in final_goals.items():
        target_region = _normalize_region(expected_region)
        for obj_name in objects:
            obj = _normalize_token(obj_name)
            observed_region = normalized.get(obj)
            check = f'{obj} in {target_region}'
            if observed_region == target_region:
                satisfied_relations.append(check)
            else:
                missing_relations.append(f'{obj} is in {observed_region or "unknown"}, expected {target_region}')

    cooking_details: Dict[str, bool] = {}
    missing_procedures: List[str] = []
    satisfied_procedures: List[str] = []
    for meat_name in cooked_meats:
        meat = _normalize_token(meat_name)
        cooked = _has_cooking_sequence(parsed_actions, meat)
        cooking_details[meat] = cooked
        check = f'{meat} cooked before plating'
        if cooked:
            satisfied_procedures.append(check)
        else:
            missing_procedures.append(
                f'{meat} missing ordered cooking sequence: '
                'place inside_grill -> close grill_lid -> open grill_lid -> place plate_top'
            )

    return _validator_result(
        variant,
        'grill_scene_state_temporal',
        {
            'object_region_map': normalized,
            'expected_regions': final_goals,
            'outside_cooked_meats': tuple(cooked_meats),
            'cooking_sequences': cooking_details,
            'parsed_actions': parsed_actions,
        },
        missing_relations=missing_relations,
        satisfied_relations=satisfied_relations,
        missing_procedures=missing_procedures,
        satisfied_procedures=satisfied_procedures,
    )


def _event_type_for_failure_event(event: Dict[str, Any]) -> str:
    failure_id = str(event.get('failure_id') or '')
    stage = str(event.get('stage') or '')
    source = str(event.get('source') or '')
    if failure_id == 'new_object_discovered':
        return 'discovery'
    if source == 'goal_check' or failure_id == 'goal_not_satisfied':
        return 'goal_validation_failure'
    if stage == 'before_execution' and source in {'validation', 'parser'}:
        return 'structural_failure'
    if stage == 'before_execution':
        return 'pre_execution_failure'
    if stage == 'after_execution' and source in {'executor', 'geometry', 'pddl'}:
        return 'runtime_failure'
    if stage == 'after_execution':
        return 'post_execution_failure'
    return 'runtime_failure'


def _structured_event_from_failure_event(event: Dict[str, Any], cycle_number: int) -> Dict[str, Any]:
    event_type = _event_type_for_failure_event(event)
    is_discovery = event_type == 'discovery'
    should_replan = bool(event.get('should_replan', False))
    failure_id = str(event.get('failure_id') or '')
    return {
        'event_id': f'cycle_{int(cycle_number)}:{failure_id or event_type}',
        'event_type': event_type,
        'cycle_number': int(cycle_number),
        'is_failure': not is_discovery,
        'is_replan_trigger': bool(should_replan),
        'failure_id': failure_id,
        'failure_layer': event.get('failure_layer'),
        'stage': event.get('stage'),
        'source': event.get('source'),
        'action': event.get('action'),
        'should_replan': should_replan,
        'message': event.get('message'),
        'evidence': dict(event.get('evidence') or {}),
    }


def extract_structured_events(
    cycles: Sequence[Dict[str, Any]],
    success_validation: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for index, cycle in enumerate(cycles or [], start=1):
        event = (cycle or {}).get('failure_event') or {}
        if event:
            cycle_number = int((cycle or {}).get('cycle_number') or index)
            events.append(_structured_event_from_failure_event(dict(event), cycle_number))

    validation = success_validation or {}
    if validation and not bool(validation.get('success', False)):
        missing = list(validation.get('missing') or [])
        events.append({
            'event_id': 'final:goal_validation_failure',
            'event_type': 'goal_validation_failure',
            'cycle_number': int(len(cycles or [])),
            'is_failure': True,
            'is_replan_trigger': False,
            'failure_id': 'goal_validation_failed',
            'failure_layer': 'layer_2',
            'stage': 'after_execution',
            'source': 'validation',
            'action': None,
            'should_replan': False,
            'message': '; '.join(str(item) for item in missing) or 'deterministic goal validation failed',
            'evidence': {
                'missing': missing,
                'satisfied': list(validation.get('satisfied') or []),
                'validator': validation.get('validator'),
            },
        })
    return events


def summarize_replanning_events(structured_events: Sequence[Dict[str, Any]], total_replans: int) -> Dict[str, int]:
    discovery = 0
    failure = 0
    for event in structured_events or []:
        if not event.get('is_replan_trigger'):
            continue
        if event.get('event_type') == 'discovery':
            discovery += 1
        elif event.get('is_failure'):
            failure += 1
    other = max(0, int(total_replans or 0) - discovery - failure)
    return {
        'discovery_triggered_replans': int(discovery),
        'failure_triggered_replans': int(failure),
        'other_triggered_replans': int(other),
    }


def summarize_failure_events(structured_events: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total_occurrences: Counter = Counter()
    by_type: Counter = Counter()
    by_id: Counter = Counter()
    by_layer: Counter = Counter()
    by_stage: Counter = Counter()
    by_source: Counter = Counter()
    by_should_replan: Counter = Counter()
    for event in structured_events or []:
        if not event.get('is_failure'):
            continue
        total_occurrences['all'] += 1
        by_type[str(event.get('event_type') or 'unknown')] += 1
        by_id[str(event.get('failure_id') or 'unknown')] += 1
        by_layer[str(event.get('failure_layer') or 'unknown')] += 1
        by_stage[str(event.get('stage') or 'unknown')] += 1
        by_source[str(event.get('source') or 'unknown')] += 1
        by_should_replan[str(bool(event.get('should_replan', False)))] += 1
    return {
        'total_real_failures': int(total_occurrences.get('all', 0)),
        'by_event_type': dict(by_type),
        'by_failure_id': dict(by_id),
        'by_failure_layer': dict(by_layer),
        'by_stage': dict(by_stage),
        'by_source': dict(by_source),
        'by_should_replan': dict(by_should_replan),
    }


def implicit_non_target_handling_success(
    variant_id: str,
    structured_events: Sequence[Dict[str, Any]],
    completed_actions: Sequence[Any],
    final_object_region_map: Optional[Dict[str, Any]],
    goal_text: str,
) -> Optional[bool]:
    variant = str(variant_id or '').strip().upper()
    if variant not in {'G1', 'G3'}:
        return None
    if 'phone' in (goal_text or '').lower():
        return False
    discovered_phone = any(
        event.get('event_type') == 'discovery'
        and 'phone' in {
            _normalize_token(item)
            for value in (event.get('evidence') or {}).values()
            for item in (value if isinstance(value, list) else [value])
        }
        for event in structured_events or []
    )
    normalized_map = _normalized_object_region_map(final_object_region_map)
    phone_on_table = normalized_map.get('phone') == 'table'

    parsed = [parse_action_string(action) for action in completed_actions]
    parsed = [action for action in parsed if action is not None]
    phone_to_table = False
    for index, action in enumerate(parsed):
        if action.get('action') != 'pick' or action.get('args') != ['phone']:
            continue
        place_index = _place_to_region_after(parsed, index + 1, 'phone', 'table')
        if place_index is not None:
            phone_to_table = True
            break
    return bool(discovered_phone and phone_to_table and phone_on_table)


def build_trial_metric_events(
    cycles: Sequence[Dict[str, Any]],
    success_validation: Optional[Dict[str, Any]],
    total_replans: int,
) -> Dict[str, Any]:
    """Return structured event and replan/failure summaries for one trial."""
    structured_events = extract_structured_events(cycles, success_validation=success_validation)
    cycle_count = len(cycles or [])
    for event in structured_events:
        if event.get('is_replan_trigger') and int(event.get('cycle_number') or 0) >= cycle_count:
            event['is_replan_trigger'] = False
    replan_counts = summarize_replanning_events(structured_events, total_replans=total_replans)
    failure_event_counts = summarize_failure_events(structured_events)
    summed_replans = (
        replan_counts['discovery_triggered_replans']
        + replan_counts['failure_triggered_replans']
        + replan_counts['other_triggered_replans']
    )
    if summed_replans != int(total_replans or 0):
        raise ValueError(
            'structured replan counts do not sum to total_replans: '
            f'{summed_replans} != {int(total_replans or 0)}'
        )
    return {
        'structured_events': structured_events,
        'failure_event_counts': failure_event_counts,
        **replan_counts,
    }


def validate_variant_success(
    variant_id: str,
    object_region_map: Optional[Dict[str, Any]],
    completed_actions: Sequence[Any],
) -> Dict[str, Any]:
    variant = str(variant_id or '').strip().upper()
    if variant.startswith('K'):
        return validate_kitchen_goal_from_scene(variant, object_region_map)
    if variant.startswith('G'):
        return validate_grill_goal_from_scene_and_history(variant, object_region_map, completed_actions)
    return _validator_result(
        variant,
        'unknown_variant',
        {
            'object_region_map': dict(object_region_map or {}),
            'completed_actions': [str(action) for action in completed_actions],
        },
        missing=[f'No validator configured for variant {variant or "(none)"}'],
        satisfied=[],
    )


__all__ = [
    'aggregate_model_records',
    'collect_failure_occurrences',
    'collapse_actions_to_subtasks',
    'parse_action_string',
    'score_variant_completion',
    'build_trial_metric_events',
    'extract_structured_events',
    'implicit_non_target_handling_success',
    'summarize_failure_events',
    'summarize_replanning_events',
    'validate_grill_goal_from_scene_and_history',
    'validate_kitchen_goal_from_scene',
    'validate_variant_success',
]
