from llm_pipeline.metrics import (
    build_trial_metric_events,
    collapse_actions_to_subtasks,
    implicit_non_target_handling_success,
    parse_action_string,
    score_variant_completion,
    validate_grill_goal_from_scene_and_history,
    validate_kitchen_goal_from_scene,
)


def test_open_action_counts_in_completion_metrics() -> None:
    actions = [
        'pick(mug2)',
        'place(mug2, table_target_area)',
        'open(box_lid)',
    ]
    assert collapse_actions_to_subtasks(actions) == ['mug_to_placement', 'open_lid']

    completion = score_variant_completion('K1', actions)
    assert completion['completed_gt_subtasks'] == 2
    assert completion['bucket_breakdown']['open_lid']['matched'] == 1


def test_legacy_and_canonical_box_regions_count_as_mug_to_box() -> None:
    assert collapse_actions_to_subtasks([
        'pick(mug2)',
        'place(mug2, box_boundary)',
        'pick(mug3)',
        'place(mug3, inside_box)',
    ]) == ['mug_to_box', 'mug_to_box']


def test_grill_actions_count_in_completion_metrics() -> None:
    actions = [
        'open(grill_lid)',
        'pick(phone)',
        'place(phone, table)',
        'pick(chicken)',
        'place(chicken, inside_grill)',
        'close(grill_lid)',
        'pick(plate)',
        'place(plate, serving_area)',
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, plate_top)',
    ]

    completion = score_variant_completion('G1', actions)

    assert completion['completed_gt_subtasks'] == 7
    assert completion['bucket_breakdown']['open_grill']['matched'] == 2
    assert completion['bucket_breakdown']['close_grill']['matched'] == 1
    assert completion['bucket_breakdown']['non_target_to_table']['matched'] == 1
    assert completion['bucket_breakdown']['plate_to_boundary']['matched'] == 1
    assert completion['bucket_breakdown']['meat_to_plate']['matched'] == 1


def test_k3_partial_grocery_completion_stays_incomplete() -> None:
    actions = [
        'pick(mug2)',
        'place(mug2, table_target_area)',
        'open(box_lid)',
        'pick(mug3)',
        'place(mug3, inside_box)',
        'pick(soup)',
        'place(soup, cupboard_shelf)',
        'pick(mug2)',
        'place(mug2, inside_box)',
        'pick(mug1)',
        'place(mug1, inside_box)',
    ]

    completion = score_variant_completion('K3', actions)

    assert completion['completed_gt_subtasks'] == 6
    assert completion['gt_total_subtasks'] == 7
    assert completion['bucket_breakdown']['grocery_to_cupboard'] == {
        'expected': 2,
        'observed': 1,
        'matched': 1,
    }


def test_kitchen_validator_uses_scene_object_names() -> None:
    result = validate_kitchen_goal_from_scene(
        'K1',
        {
            'mug2': 'inside_box',
            'mug3': 'box_boundary',
            'soup': 'cupboard_shelf',
            'spam': 'cupboard_boundary',
            'can_of_beans': 'table',
        },
    )

    assert result['success'] is True
    assert 'soup in cupboard_shelf' in result['satisfied']


def test_kitchen_validator_reports_missing_scene_object() -> None:
    result = validate_kitchen_goal_from_scene(
        'K2',
        {
            'mug2': 'inside_box',
            'mug3': 'inside_box',
            'sugar': 'cupboard_shelf',
            'can_of_beans': 'cupboard_shelf',
        },
    )

    assert result['success'] is False
    assert 'soup is in unknown, expected cupboard_shelf' in result['missing']


def test_grill_g1_validator_requires_final_state_and_cooking_sequence() -> None:
    actions = [
        'open(grill_lid)',
        'pick(phone)',
        'place(phone, table)',
        'pick(chicken)',
        'place(chicken, inside_grill)',
        'close(grill_lid)',
        'pick(plate)',
        'place(plate, serving_area)',
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, plate_top)',
    ]
    result = validate_grill_goal_from_scene_and_history(
        'G1',
        {
            'phone': 'table',
            'plate': 'serving_area',
            'chicken': 'plate_top',
        },
        actions,
    )

    assert result['success'] is True
    assert result['details']['cooking_sequences']['chicken'] is True
    assert result['partial_goal_completion'] == 1.0
    assert result['required_relation_count'] == 3
    assert result['satisfied_relation_count'] == 3
    assert result['required_procedure_count'] == 1
    assert result['satisfied_procedure_count'] == 1


def test_grill_validator_rejects_plating_without_cooking_sequence() -> None:
    actions = [
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, plate_top)',
    ]
    result = validate_grill_goal_from_scene_and_history(
        'G1',
        {
            'phone': 'table',
            'plate': 'serving_area',
            'chicken': 'plate_top',
        },
        actions,
    )

    assert result['success'] is False
    assert result['details']['cooking_sequences']['chicken'] is False
    assert 0.0 < result['partial_goal_completion'] < 1.0
    assert result['required_relation_count'] == 3
    assert result['required_procedure_count'] == 1
    assert result['missing_procedure_count'] == 1


def test_grill_validator_rejects_close_before_meat_enters_grill() -> None:
    actions = [
        'close(grill_lid)',
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, inside_grill)',
        'pick(chicken)',
        'place(chicken, plate_top)',
    ]
    result = validate_grill_goal_from_scene_and_history(
        'G1',
        {
            'phone': 'table',
            'plate': 'serving_area',
            'chicken': 'plate_top',
        },
        actions,
    )

    assert result['success'] is False
    assert result['details']['cooking_sequences']['chicken'] is False


def test_grill_g2_validator_treats_initial_inside_steak_as_final_only() -> None:
    actions = [
        'open(grill_lid)',
        'pick(plate)',
        'place(plate, serving_area)',
        'pick(steak)',
        'place(steak, plate_top)',
        'pick(chicken)',
        'place(chicken, inside_grill)',
        'pick(steak1)',
        'place(steak1, inside_grill)',
        'close(grill_lid)',
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, plate_top)',
        'pick(steak1)',
        'place(steak1, plate_top)',
    ]
    result = validate_grill_goal_from_scene_and_history(
        'G2',
        {
            'plate': 'serving_area',
            'steak': 'plate_top',
            'chicken': 'plate_top',
            'steak1': 'plate_top',
        },
        actions,
    )

    assert result['success'] is True
    assert 'steak cooked before plating' not in result['satisfied']
    assert result['details']['cooking_sequences'] == {'chicken': True, 'steak1': True}
    assert result['required_relation_count'] == 4
    assert result['required_procedure_count'] == 2


def test_grill_g3_validator_requires_phone_on_table() -> None:
    actions = [
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, inside_grill)',
        'pick(steak1)',
        'place(steak1, inside_grill)',
        'close(grill_lid)',
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, plate_top)',
        'pick(steak1)',
        'place(steak1, plate_top)',
    ]
    result = validate_grill_goal_from_scene_and_history(
        'G3',
        {
            'plate': 'serving_area',
            'steak': 'plate_top',
            'chicken': 'plate_top',
            'steak1': 'plate_top',
            'phone': 'inside_grill',
        },
        actions,
    )

    assert result['success'] is False
    assert 'phone is in inside_grill, expected table' in result['missing']
    assert result['required_relation_count'] == 5
    assert result['required_procedure_count'] == 2


def test_grill_validator_requires_plate_in_serving_area() -> None:
    actions = [
        'pick(chicken)',
        'place(chicken, inside_grill)',
        'close(grill_lid)',
        'open(grill_lid)',
        'pick(chicken)',
        'place(chicken, plate_top)',
    ]
    result = validate_grill_goal_from_scene_and_history(
        'G1',
        {
            'phone': 'table',
            'plate': 'dish_rack',
            'chicken': 'plate_top',
        },
        actions,
    )

    assert result['success'] is False
    assert 'plate is in dish_rack, expected serving_area' in result['missing']


def test_structured_events_treat_discovery_as_replan_not_failure() -> None:
    metrics = build_trial_metric_events(
        cycles=[
            {
                'cycle_number': 1,
                'failure_event': {
                    'failure_id': 'new_object_discovered',
                    'failure_layer': 'layer_2',
                    'stage': 'after_execution',
                    'source': 'segmentation',
                    'action': 'open(grill_lid)',
                    'should_replan': True,
                    'message': 'phone became visible',
                    'evidence': {'newly_visible_objects': ['phone']},
                },
            },
            {
                'cycle_number': 2,
                'failure_event': {
                    'failure_id': 'unknown_action_token',
                    'failure_layer': 'layer_1',
                    'stage': 'before_execution',
                    'source': 'validation',
                    'action': None,
                    'should_replan': True,
                    'message': 'bad action',
                    'evidence': {},
                },
            },
            {
                'cycle_number': 3,
                'failure_event': None,
            },
        ],
        success_validation={'success': True},
        total_replans=2,
    )

    assert metrics['discovery_triggered_replans'] == 1
    assert metrics['failure_triggered_replans'] == 1
    assert metrics['other_triggered_replans'] == 0
    assert metrics['structured_events'][0]['event_type'] == 'discovery'
    assert metrics['structured_events'][0]['is_failure'] is False
    assert metrics['structured_events'][1]['event_type'] == 'structural_failure'
    assert metrics['failure_event_counts']['total_real_failures'] == 1


def test_goal_validation_failure_becomes_structured_real_failure() -> None:
    metrics = build_trial_metric_events(
        cycles=[],
        success_validation={
            'success': False,
            'missing': ['phone is in inside_grill, expected table'],
            'satisfied': [],
            'validator': 'grill_scene_state_temporal',
        },
        total_replans=0,
    )

    assert metrics['structured_events'][0]['event_type'] == 'goal_validation_failure'
    assert metrics['structured_events'][0]['is_failure'] is True
    assert metrics['failure_event_counts']['by_event_type'] == {'goal_validation_failure': 1}


def test_implicit_non_target_handling_success_requires_hidden_phone_relocated_to_table() -> None:
    events = [
        {
            'event_type': 'discovery',
            'is_failure': False,
            'is_replan_trigger': True,
            'evidence': {'newly_visible_objects': ['phone']},
        }
    ]
    actions = [
        'open(grill_lid)',
        'pick(phone)',
        'place(phone, table)',
    ]

    assert implicit_non_target_handling_success(
        'G1',
        events,
        actions,
        {'phone': 'table'},
        'Cook all raw meat using the grill and serve all cooked meat on the plate in the serving area.',
    ) is True
    assert implicit_non_target_handling_success('G2', events, actions, {'phone': 'table'}, 'same goal') is None
    assert implicit_non_target_handling_success('G3', events, actions, {'phone': 'inside_grill'}, 'same goal') is False
