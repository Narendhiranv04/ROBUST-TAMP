"""A final marker the model repeats at the very end with nothing after it does not hide its answer."""

from llm_pipeline.corrective import parse_blocks
from llm_pipeline.strict_parser import StrictActionParser, split_reasoning

BLOCK_ANSWER = """thinking...
FINAL BLOCKS:
BLOCK
objects: cooked_meat_1
urgency: urgent
insert: front
reason: it is already cooked.
actions:
pick(cooked_meat_1)
place(cooked_meat_1, plate_top)
END BLOCK
FINAL BLOCKS:
"""


def test_blocks_with_a_trailing_empty_marker():
    blocks = parse_blocks(BLOCK_ANSWER, ['cooked_meat_1'], ['a6', 'a7'])
    assert len(blocks) == 1 and blocks[0].actions == ['pick(cooked_meat_1)', 'place(cooked_meat_1, plate_top)']
    assert blocks[0].urgency == 'urgent'


def test_blocks_last_marker_with_content_still_wins():
    text = BLOCK_ANSWER.replace('FINAL BLOCKS:\n\n', '') + 'BLOCK\nobjects: cooked_meat_1\nurgency: deferred\ninsert: end\n' \
        'reason: later.\nactions:\npick(cooked_meat_1)\nplace(cooked_meat_1, plate_top)\nEND BLOCK\n'
    assert parse_blocks(text, ['cooked_meat_1'], ['a6'])[0].urgency == 'deferred'


def test_actions_with_a_trailing_empty_marker():
    text = 'reasoning\nFINAL ACTIONS:\npick(mug1)\nplace(mug1, inside_box)\nFINAL ACTIONS:\n'
    reasoning, answer = split_reasoning(text)
    assert reasoning == 'reasoning' and answer.splitlines() == ['pick(mug1)', 'place(mug1, inside_box)']
    parser = StrictActionParser(valid_objects={'mug1'}, valid_regions={'inside_box'})
    parser.require_final_marker = True
    assert [str(a) for a in parser.parse(text)] == ['pick(mug1)', 'place(mug1, inside_box)']


def test_empty_answer_is_still_empty():
    assert split_reasoning('reasoning\nFINAL ACTIONS:\n') == ('reasoning', '')


def test_icl_examples_v3_adds_the_deferred_example_for_the_grill_only():
    from llm_pipeline.icl_examples import examples_for

    v2, v3 = examples_for({'grill_lid', 'plate'}, 'examples_v2'), examples_for({'grill_lid', 'plate'}, 'examples_v3')
    assert 'Example 3' not in v2 and 'Example 3' in v3 and 'urgency: deferred' in v3
    assert v3.count('Good answer:') == 3 and v3.count('Bad answer:') == 3
    assert examples_for({'box_lid', 'mug1'}, 'examples_v3') == ''
    for word in ('grill', 'meat', 'plate', 'cook', 'towel_3'):
        assert word not in v3.split('Example 3', 1)[1].lower() or word == 'towel_3'
