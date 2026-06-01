from llm_pipeline.metrics import collapse_actions_to_subtasks, parse_action_string, score_variant_completion


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
        'pick(spam)',
        'place(spam, table)',
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
    assert completion['bucket_breakdown']['meat_to_table']['matched'] == 1
