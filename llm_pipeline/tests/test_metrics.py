from llm_pipeline.metrics import (
    collapse_actions_to_subtasks,
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
