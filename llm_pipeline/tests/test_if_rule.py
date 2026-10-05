"""Phase 4: the IF rule (replan.trigger_mode = if_rule)."""

import pytest

from llm_pipeline.if_rule import (
    IRRELEVANT_OVERLAPPING,
    RELEVANT_NOT_GOAL_ATTAINED,
    assess_objects,
    trigger_objects,
)

KITCHEN_PLAN = ['pick(mug1)', 'place(mug1, inside_box)', 'pick(spam)', 'place(spam, cupboard_shelf)']


def _overlap(table):
    """table: object -> regions whose placement area it overlaps."""
    return lambda obj, regions: [r for r in regions if r in table.get(obj, ())]


def _assess(scene, regions, plan, completed=(), initial=None, overlap=None, **kw):
    return {a.object_id: a for a in assess_objects(
        scene, regions, plan, list(completed), initial or dict(regions), _overlap(overlap or {}), **kw)}


# ---------------------------------------------------------------- the four rows, kitchen
def test_kitchen_irrelevant_overlapping_triggers() -> None:
    result = _assess('kitchen', {'phone': 'inside_box'}, KITCHEN_PLAN, overlap={'phone': ['inside_box']})
    assert result['phone'].trigger_kind == IRRELEVANT_OVERLAPPING
    assert result['phone'].overlapping_regions == ('inside_box',)


def test_kitchen_irrelevant_not_overlapping_is_ignored() -> None:
    result = _assess('kitchen', {'phone': 'inside_box'}, KITCHEN_PLAN)
    assert result['phone'].decision == 'ignore' and not result['phone'].relevant


def test_kitchen_relevant_not_goal_attained_triggers_overlapping_or_not() -> None:
    for overlap in ({}, {'can_of_beans': ['inside_box']}):
        result = _assess('kitchen', {'can_of_beans': 'inside_box'}, KITCHEN_PLAN, overlap=overlap)
        assert result['can_of_beans'].trigger_kind == RELEVANT_NOT_GOAL_ATTAINED


def test_kitchen_goal_attained_object_is_ignored() -> None:
    result = _assess('kitchen', {'mug4': 'inside_box', 'sugar': 'cupboard_shelf'}, KITCHEN_PLAN,
                     overlap={'mug4': ['inside_box']})
    assert result['mug4'].goal_attained and result['mug4'].decision == 'ignore'
    assert result['sugar'].goal_attained and result['sugar'].decision == 'ignore'


def test_overlap_only_counts_for_regions_the_remaining_plan_places_into() -> None:
    result = _assess('kitchen', {'phone': 'inside_box'}, ['pick(spam)', 'place(spam, cupboard_shelf)'],
                     overlap={'phone': ['inside_box']})
    assert result['phone'].decision == 'ignore' and not result['phone'].overlapping


# ---------------------------------------------------------------- the four rows, grill
GRILL_PLAN = ['pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)', 'close(grill_lid)', 'open(grill_lid)',
              'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)']


def test_grill_cooked_and_raw_meat_in_the_grill_trigger() -> None:
    result = _assess('grill', {'cooked_meat_1': 'inside_grill', 'raw_meat_2': 'inside_grill', 'raw_meat_1': 'prep_area'},
                     GRILL_PLAN, completed=['open(grill_lid)'])
    assert result['cooked_meat_1'].trigger_kind == RELEVANT_NOT_GOAL_ATTAINED
    assert result['raw_meat_2'].trigger_kind == RELEVANT_NOT_GOAL_ATTAINED
    assert result['raw_meat_1'].decision == 'ignore' and result['raw_meat_1'].accounted_for


def test_grill_irrelevant_rows() -> None:
    plan = GRILL_PLAN
    assert _assess('grill', {'phone': 'inside_grill'}, plan, overlap={'phone': ['inside_grill']})['phone'].trigger_kind \
        == IRRELEVANT_OVERLAPPING
    assert _assess('grill', {'phone': 'inside_grill'}, plan)['phone'].decision == 'ignore'
    assert _assess('grill', {'plate': 'serving_area'}, plan)['plate'].decision == 'ignore'


def test_grill_goal_attained_meat_needs_its_procedure() -> None:
    history = ['open(grill_lid)', 'pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)', 'close(grill_lid)',
               'open(grill_lid)', 'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)']
    cooked = _assess('grill', {'raw_meat_1': 'plate_top'}, [], completed=history, initial={'raw_meat_1': 'prep_area'})
    assert cooked['raw_meat_1'].goal_attained and cooked['raw_meat_1'].decision == 'ignore'
    served_raw = _assess('grill', {'raw_meat_1': 'plate_top'}, [], completed=history[:2] + ['place(raw_meat_1, plate_top)'],
                         initial={'raw_meat_1': 'prep_area'})
    assert served_raw['raw_meat_1'].trigger_kind == RELEVANT_NOT_GOAL_ATTAINED
    assert _assess('grill', {'cooked_meat_1': 'plate_top'}, [], initial={'cooked_meat_1': 'inside_grill'})[
        'cooked_meat_1'].goal_attained


# ---------------------------------------------------------------- accounting, batching
def test_objects_the_robot_placed_itself_are_accounted_for() -> None:
    # raw meat the robot put into the grill: the remaining plan still picks it later.
    remaining = ['close(grill_lid)', 'open(grill_lid)', 'pick(raw_meat_1)', 'place(raw_meat_1, plate_top)']
    result = _assess('grill', {'raw_meat_1': 'inside_grill'}, remaining,
                     completed=['pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)'], initial={'raw_meat_1': 'prep_area'})
    assert result['raw_meat_1'].accounted_for and result['raw_meat_1'].decision == 'ignore'


def test_all_trigger_objects_of_one_observation_are_returned_together() -> None:
    regions = {'can_of_beans': 'inside_box', 'can_of_beans_2': 'inside_box', 'can_of_beans_3': 'inside_box'}
    assessments = assess_objects('kitchen', regions, KITCHEN_PLAN, [], regions, _overlap({}))
    assert [a.object_id for a in trigger_objects(assessments)] == sorted(regions)


def test_pending_replan_and_held_objects_do_not_trigger() -> None:
    result = _assess('kitchen', {'can_of_beans': 'inside_box', 'phone': 'table'}, KITCHEN_PLAN,
                     pending_objects=['can_of_beans'], held_object='phone')
    assert result['can_of_beans'].decision == 'ignore' and 'phone' not in result


@pytest.mark.parametrize('lid', ['box_lid', 'grill_lid'])
def test_lids_are_never_trigger_objects(lid) -> None:
    assert lid not in _assess('kitchen', {lid: None}, KITCHEN_PLAN)


def test_an_overcooked_meat_on_the_plate_does_not_trigger_again() -> None:
    history = ['open(grill_lid)', 'close(grill_lid)', 'open(grill_lid)', 'pick(cooked_meat_1)',
               'place(cooked_meat_1, plate_top)']
    result = _assess('grill', {'cooked_meat_1': 'plate_top'}, [], completed=history,
                     initial={'cooked_meat_1': 'inside_grill'})
    assert result['cooked_meat_1'].goal_attained and result['cooked_meat_1'].decision == 'ignore'
