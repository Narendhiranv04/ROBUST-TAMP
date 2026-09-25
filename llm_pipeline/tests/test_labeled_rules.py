import pytest

from evaluation.labeled_rules import (
    LABELED_RULE_VARIANTS,
    meat_procedure_status,
    object_category,
    validate_labeled_goal,
)
from evaluation.metric_definitions import partial_goal_completion, summarize, task_success_rate, trial_scores

OPEN, CLOSE = 'open(grill_lid)', 'close(grill_lid)'


def _cook_and_serve(meat):
    return [OPEN, f'pick({meat})', f'place({meat}, inside_grill)', CLOSE, OPEN,
            f'pick({meat})', f'place({meat}, plate_top)']


def test_categories_come_from_labels() -> None:
    assert object_category('raw_meat') == 'raw_meat'
    assert object_category('raw_meat_2') == 'raw_meat'
    assert object_category('cooked_meat1') == 'cooked_meat'
    assert object_category('mug3') == 'mug'
    assert object_category('spam') == 'grocery'
    assert object_category('phone') == 'phone'
    assert object_category('chicken') is None  # today's names are not labels


def test_raw_meat_correct_cycle_is_cooked() -> None:
    status = meat_procedure_status('raw_meat_1', 'raw_meat', 'prep_area', _cook_and_serve('raw_meat_1'))
    assert (status.cooking_cycles, status.cooked, status.overcooked, status.served_raw) == (1, True, False, False)
    assert status.satisfied


def test_raw_meat_served_before_cooking_fails() -> None:
    history = ['pick(raw_meat_1)', 'place(raw_meat_1, plate_top)', 'pick(raw_meat_1)',
               'place(raw_meat_1, inside_grill)', CLOSE, OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)']
    status = meat_procedure_status('raw_meat_1', 'raw_meat', 'prep_area', history)
    assert status.served_raw and status.cooked and not status.satisfied
    assert 'before completing a cooking cycle' in status.failure_reason()


def test_raw_meat_two_cycles_is_overcooked() -> None:
    history = [OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)', CLOSE, OPEN, CLOSE, OPEN,
               'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)']
    status = meat_procedure_status('raw_meat_1', 'raw_meat', 'prep_area', history)
    assert status.cooking_cycles == 2 and status.overcooked and not status.satisfied


def test_cooked_meat_left_in_grill_is_overcooked_by_the_first_cycle() -> None:
    history = [OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)', CLOSE, OPEN,
               'pick(cooked_meat_1)', 'place(cooked_meat_1, plate_top)']
    cooked = meat_procedure_status('cooked_meat_1', 'cooked_meat', 'inside_grill', history)
    assert cooked.overcooked and not cooked.satisfied
    raw = meat_procedure_status('raw_meat_1', 'raw_meat', 'prep_area', history)
    assert raw.cooked and not raw.overcooked


def test_cooked_meat_removed_before_the_cycle_is_fine() -> None:
    history = [OPEN, 'pick(cooked_meat_1)', 'place(cooked_meat_1, plate_top)', 'pick(raw_meat_1)',
               'place(raw_meat_1, inside_grill)', CLOSE, OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)']
    cooked = meat_procedure_status('cooked_meat_1', 'cooked_meat', 'inside_grill', history)
    assert cooked.satisfied and cooked.cooking_cycles == 0


def test_meat_removed_before_closing_is_not_cooked() -> None:
    history = [OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)', 'pick(raw_meat_1)',
               'place(raw_meat_1, table)', CLOSE, OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)']
    status = meat_procedure_status('raw_meat_1', 'raw_meat', 'prep_area', history)
    assert not status.cooked and status.served_raw


def test_grill_goal_counts_relations_and_procedures_per_meat() -> None:
    history = [OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)', CLOSE, OPEN,
               'pick(cooked_meat_1)', 'place(cooked_meat_1, plate_top)', 'pick(raw_meat_1)',
               'place(raw_meat_1, plate_top)', 'pick(plate)', 'place(plate, serving_area)']
    result = validate_labeled_goal(
        'grill', 'G2',
        object_region_map={'raw_meat_1': 'plate_top', 'cooked_meat_1': 'plate_top', 'plate': 'serving_area'},
        completed_actions=history,
        initial_object_region_map={'raw_meat_1': 'prep_area', 'cooked_meat_1': 'inside_grill', 'plate': 'dish_rack'},
    )
    assert result['success'] is False
    assert result['required_relation_count'] == 3 and result['satisfied_relation_count'] == 3
    # procedures: raw_meat_1 ok; cooked_meat_1 overcooked; HC-grill for cooked_meat_1 violated
    assert result['required_procedure_count'] == 3 and result['satisfied_procedure_count'] == 1
    assert result['partial_goal_completion'] == pytest.approx(4 / 6)
    assert result['details']['procedures']['cooked_meat_1']['overcooked'] is True
    assert any(m.startswith('HC-grill violated: cooked_meat_1') for m in result['missing_procedures'])


def test_cooked_meat_may_leave_the_grill_to_any_region_before_the_close() -> None:
    history = [OPEN, 'pick(cooked_meat_1)', 'place(cooked_meat_1, table)', 'pick(raw_meat_1)',
               'place(raw_meat_1, inside_grill)', CLOSE, OPEN, 'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)',
               'pick(cooked_meat_1)', 'place(cooked_meat_1, plate_top)', 'pick(plate)', 'place(plate, serving_area)']
    result = validate_labeled_goal(
        'grill', 'FINAL.G1-n1',
        object_region_map={'raw_meat_1': 'plate_top', 'cooked_meat_1': 'plate_top', 'plate': 'serving_area'},
        completed_actions=history,
        initial_object_region_map={'raw_meat_1': 'prep_area', 'cooked_meat_1': 'inside_grill', 'plate': 'dish_rack'},
    )
    assert result['success'] is True, result['missing']


def test_box_constraint_requires_the_trigger_cleared_before_any_other_place_into_the_box() -> None:
    final = {'mug1': 'inside_box', 'can_of_beans': 'cupboard_shelf'}
    initial = {'mug1': 'table', 'can_of_beans': 'inside_box'}
    good = ['open(box_lid)', 'pick(can_of_beans)', 'place(can_of_beans, cupboard_shelf)',
            'pick(mug1)', 'place(mug1, inside_box)']
    bad = ['open(box_lid)', 'pick(mug1)', 'place(mug1, inside_box)',
           'pick(can_of_beans)', 'place(can_of_beans, cupboard_shelf)']
    ok = validate_labeled_goal('kitchen', 'FINAL.K3', final, good, initial, box_trigger_objects=['can_of_beans'])
    assert ok['success'] is True
    violated = validate_labeled_goal('kitchen', 'FINAL.K3', final, bad, initial, box_trigger_objects=['can_of_beans'])
    assert violated['success'] is False and violated['missing_relation_count'] == 0
    assert violated['missing_procedures'] == ['HC-box violated: mug1 placed into the box before can_of_beans was cleared']


def test_phone_must_not_end_in_any_placement_area() -> None:
    final = {'mug1': 'inside_box', 'phone': 'inside_grill'}
    result = validate_labeled_goal('kitchen', 'FINAL.K1', final, [], {'phone': 'inside_box'},
                                   {'inside_box': ['mug1'], 'inside_grill': ['phone']})
    assert 'phone is in the inside_grill placement area' in result['missing_relations']


def test_kitchen_phone_must_not_be_in_the_box_placement_area() -> None:
    final = {'mug1': 'inside_box', 'spam': 'cupboard_shelf', 'phone': 'inside_box'}
    initial = {'mug1': 'table', 'spam': 'table', 'phone': 'inside_box'}
    blocked = validate_labeled_goal('kitchen', 'K1', final, [], initial, {'inside_box': ['phone']})
    assert blocked['success'] is False
    assert 'phone is in the inside_box placement area' in blocked['missing_relations']
    cleared = validate_labeled_goal('kitchen', 'K1', final, [], initial, {'inside_box': ['mug1']})
    assert cleared['success'] is True
    with pytest.raises(ValueError):
        validate_labeled_goal('kitchen', 'K1', final, [], initial, None)


def test_labeled_rules_are_used_for_the_final_variants_only() -> None:
    assert not LABELED_RULE_VARIANTS & {'K1', 'K2', 'K3', 'G1', 'G2', 'G3'}
    assert len(LABELED_RULE_VARIANTS) == 14 and 'FINAL.G1-N1' in LABELED_RULE_VARIANTS


def test_metric_definitions_follow_plan_formulas() -> None:
    items = [
        {'event': 'trial_end', 'success': True, 'goal_relations_satisfied': 4, 'goal_relations_total': 4,
         'procedure_checks_satisfied': 1, 'procedure_checks_total': 1, 'termination_reason': 'plan_completed'},
        {'event': 'trial_end', 'success': False, 'goal_relations_satisfied': 1, 'goal_relations_total': 4,
         'procedure_checks_satisfied': 0, 'procedure_checks_total': 1, 'termination_reason': 'plan_completed'},
        {'event': 'trial_end', 'success': None, 'goal_relations_satisfied': None, 'goal_relations_total': None,
         'procedure_checks_satisfied': None, 'procedure_checks_total': None, 'termination_reason': 'infrastructure'},
    ]
    scores = trial_scores(items)
    assert task_success_rate(scores) == pytest.approx(1 / 2)
    assert partial_goal_completion(scores) == pytest.approx((5 / 5 + 1 / 5) / 2)
    summary = summarize(items)
    assert (summary['trials'], summary['evaluated_trials'], summary['infrastructure_trials']) == (3, 2, 1)


def test_metric_definitions_read_record_json() -> None:
    records = [
        {'episode_success': True, 'satisfied_relation_count': 3, 'required_relation_count': 3,
         'satisfied_procedure_count': 1, 'required_procedure_count': 1},
        {'episode_success': None, 'satisfied_relation_count': None, 'required_relation_count': None,
         'satisfied_procedure_count': None, 'required_procedure_count': None},
    ]
    summary = summarize(records)
    assert summary['task_success_rate'] == pytest.approx(0.5)
    assert summary['partial_goal_completion'] == pytest.approx(0.5)
