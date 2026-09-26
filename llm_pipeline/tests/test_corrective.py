"""Phase 5: corrective blocks, insertion modes, merge and the placement-conflict check."""

import itertools

import pytest

from evaluation.labeled_rules import validate_labeled_goal
from llm_pipeline.corrective import (
    CorrectivePlanError,
    apply_insertion_mode,
    merge_blocks,
    parse_blocks,
    placement_conflict,
)
from llm_pipeline.failures import FailureCode

REMAINING = [('a6', 'pick(spam)'), ('a7', 'place(spam, cupboard_shelf)'),
             ('a8', 'pick(mug1)'), ('a9', 'place(mug1, inside_box)')]
IDS = [action_id for action_id, _ in REMAINING]


def _block(objects, urgency, insert, actions, reason='r'):
    return '\n'.join(['BLOCK', f'objects: {objects}', f'urgency: {urgency}', f'insert: {insert}', f'reason: {reason}',
                      'actions:', *actions, 'END BLOCK'])


def _output(*blocks, reasoning='Some reasoning first.'):
    return reasoning + '\nFINAL BLOCKS:\n' + '\n'.join(blocks)


def _ids():
    counter = itertools.count(100)
    return lambda: f'a{next(counter)}'


PHONE_URGENT = _block('phone', 'urgent', 'front', ['pick(phone)', 'place(phone, table)'])


# ---------------------------------------------------------------- parser
def test_parser_accepts_valid_blocks_with_different_urgencies() -> None:
    raw = _output(_block('cooked_meat_1', 'urgent', 'front', ['pick(cooked_meat_1)', 'place(cooked_meat_1, table)']),
                  _block('raw_meat_2', 'deferred', 'after a7', ['pick(raw_meat_2)', 'place(raw_meat_2, plate_top)']),
                  _block('cooked_meat_1', 'deferred', 'end', ['pick(cooked_meat_1)', 'place(cooked_meat_1, plate_top)']))
    blocks = parse_blocks(raw, ['cooked_meat_1', 'raw_meat_2'], IDS)
    assert [(b.objects, b.urgency, b.insert) for b in blocks] == [
        (['cooked_meat_1'], 'urgent', 'front'), (['raw_meat_2'], 'deferred', 'after:a7'),
        (['cooked_meat_1'], 'deferred', 'end')]


@pytest.mark.parametrize('raw, fragment', [
    (_output(_block('phone', '', 'front', ['pick(phone)', 'place(phone, table)'])), 'no urgency'),
    (_output(_block('phone', 'urgent', 'end', ['pick(phone)', 'place(phone, table)'])), 'urgent but not inserted at the front'),
    (_output(_block('phone', 'deferred', 'after a42', ['pick(phone)', 'place(phone, table)'])), 'not in the remaining plan'),
    (_output(_block('phone', 'soon', 'front', ['pick(phone)', 'place(phone, table)'])), "urgency 'soon'"),
    (_output(_block('mug1', 'urgent', 'front', ['pick(mug1)', 'place(mug1, table)'])), 'not a listed object'),
    (_output(_block('phone', 'urgent', 'front', ['pick(mug1)', 'place(mug1, table)'])), 'does not handle'),
    (_output(_block('phone', 'urgent', 'front', [])), 'has no actions'),
    ('FINAL ACTIONS:\npick(phone)', 'no FINAL BLOCKS'),
    (_output('BLOCK\nobjects: phone\nurgency: urgent\ninsert: front\nactions:\npick(phone)'), 'no END BLOCK'),
    (_output(_block('can_of_beans', 'urgent', 'front', ['pick(can_of_beans)', 'place(can_of_beans, cupboard_shelf)'])),
     'no block handles phone'),
])
def test_parser_rejects_malformed_blocks(raw, fragment) -> None:
    triggers = ['phone'] if 'can_of_beans' not in raw else ['phone', 'can_of_beans']
    with pytest.raises(CorrectivePlanError) as error:
        parse_blocks(raw, triggers, IDS)
    assert error.value.failure_id == FailureCode.INVALID_CORRECTIVE_BLOCK
    assert fragment in error.value.fact


# ---------------------------------------------------------------- merge
def test_merge_front_after_and_end() -> None:
    blocks = parse_blocks(_output(
        _block('a_obj', 'urgent', 'front', ['pick(a_obj)', 'place(a_obj, table)']),
        _block('b_obj', 'deferred', 'after a7', ['pick(b_obj)', 'place(b_obj, table)']),
        _block('c_obj', 'deferred', 'end', ['pick(c_obj)', 'place(c_obj, table)']),
        _block('d_obj', 'urgent', 'front', ['pick(d_obj)', 'place(d_obj, table)'])),
        ['a_obj', 'b_obj', 'c_obj', 'd_obj'], IDS)
    merged = [action for _, action in merge_blocks(REMAINING, blocks, _ids()).merged]
    assert merged == ['pick(a_obj)', 'place(a_obj, table)', 'pick(d_obj)', 'place(d_obj, table)',
                      'pick(spam)', 'place(spam, cupboard_shelf)', 'pick(b_obj)', 'place(b_obj, table)',
                      'pick(mug1)', 'place(mug1, inside_box)', 'pick(c_obj)', 'place(c_obj, table)']


def test_merge_keeps_remaining_ids_and_moves_executed_anchor_to_front() -> None:
    blocks = parse_blocks(_output(_block('phone', 'deferred', 'after a7', ['pick(phone)', 'place(phone, table)'])),
                          ['phone'], IDS)
    result = merge_blocks(REMAINING[2:], blocks, _ids())      # a6, a7 were executed meanwhile
    assert result.anchors_already_executed == ['a7']
    assert result.merged[:2] == [('a100', 'pick(phone)'), ('a101', 'place(phone, table)')]
    assert result.merged[2:] == REMAINING[2:]


# ---------------------------------------------------------------- insertion modes
def test_always_front_and_always_end_override_the_model() -> None:
    blocks = parse_blocks(_output(_block('phone', 'deferred', 'end', ['pick(phone)', 'place(phone, table)'])), ['phone'], IDS)
    front = apply_insertion_mode(blocks, 'always_front')
    assert (front[0].urgency, front[0].insert, front[0].proposed_insert) == ('urgent', 'front', 'end')
    blocks = parse_blocks(_output(PHONE_URGENT), ['phone'], IDS)
    end = apply_insertion_mode(blocks, 'always_end')
    assert (end[0].urgency, end[0].insert, end[0].proposed_urgency) == ('deferred', 'end', 'urgent')
    assert apply_insertion_mode(blocks, 'planner')[0].insert == 'front'


# ---------------------------------------------------------------- placement conflicts
def test_deferring_the_box_block_past_the_next_box_placement_is_too_late() -> None:
    for trigger, dest in (('phone', 'table'), ('can_of_beans', 'cupboard_shelf')):     # K1 and K3
        blocks = parse_blocks(_output(_block(trigger, 'deferred', 'end', [f'pick({trigger})', f'place({trigger}, {dest})'])),
                              [trigger], IDS)
        merged = [a for _, a in merge_blocks(REMAINING, blocks, _ids()).merged]
        assert 'inside_box' in placement_conflict(merged, {trigger: ['inside_box']})
        front = apply_insertion_mode(blocks, 'always_front')
        merged = [a for _, a in merge_blocks(REMAINING, front, _ids()).merged]
        assert placement_conflict(merged, {trigger: ['inside_box']}) is None


def test_deferring_cooked_meat_past_the_close_is_not_blocked_but_is_overcooked() -> None:
    remaining = [('a4', 'pick(raw_meat_1)'), ('a5', 'place(raw_meat_1, inside_grill)'), ('a6', 'close(grill_lid)'),
                 ('a7', 'open(grill_lid)'), ('a8', 'pick(raw_meat_1)'), ('a9', 'place(raw_meat_1, plate_top)')]
    blocks = parse_blocks(_output(_block('cooked_meat_1', 'deferred', 'end',
                                         ['pick(cooked_meat_1)', 'place(cooked_meat_1, plate_top)'])),
                          ['cooked_meat_1'], [i for i, _ in remaining])
    merged = [a for _, a in merge_blocks(remaining, blocks, _ids()).merged]
    assert placement_conflict(merged, {'cooked_meat_1': []}) is None           # the system does not block it
    history = ['open(grill_lid)', 'pick(plate)', 'place(plate, serving_area)'] + merged
    result = validate_labeled_goal(
        'grill', 'FINAL.G1-n1', {'raw_meat_1': 'plate_top', 'cooked_meat_1': 'plate_top', 'plate': 'serving_area'},
        history, {'raw_meat_1': 'prep_area', 'cooked_meat_1': 'inside_grill', 'plate': 'dish_rack'})
    assert result['success'] is False and result['details']['procedures']['cooked_meat_1']['overcooked'] is True
