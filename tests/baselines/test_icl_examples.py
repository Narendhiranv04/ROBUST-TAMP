"""The baselines' in-context examples (baselines/icl_examples.py): only in the ICL condition and
the grill scene, in each baseline's own answer format, naming nothing of the grill scene."""

from types import SimpleNamespace

import pytest

from baselines import icl_examples
from baselines.inner_monologue import parse_final_actions
from baselines.llm_planner import LLMPlannerPipeline, parse_plan
from baselines.owl_tamp import parse_sketch

BASELINES = ('llm_planner', 'inner_monologue', 'vlm_tamp', 'owl_tamp', 'epog')


def fake(baseline, icl_mode, task_family):
    return SimpleNamespace(baseline_name=baseline, config=SimpleNamespace(icl_mode=icl_mode, task_family=task_family))


@pytest.mark.parametrize('baseline', BASELINES)
def test_examples_only_in_the_icl_condition_and_the_grill_scene(baseline):
    assert icl_examples.examples_for(fake(baseline, 'zero_shot', 'grill')) == ''
    assert icl_examples.examples_for(fake(baseline, 'examples_v2', 'kitchen')) == ''
    text = icl_examples.examples_for(fake(baseline, 'examples_v2', 'grill'))
    assert 'Example 1' in text and 'Example 2' in text
    assert text.startswith(icl_examples.HEADER) or baseline == 'epog'     # EPoG's follow the authors' example
    for word in ('grill', 'meat', 'plate', 'serving', 'cook'):
        assert word not in text.lower()


def test_epog_examples_are_resolve_examples_and_unknown_modes_are_refused():
    text = icl_examples.examples_for(fake('epog', 'examples_v2', 'grill'))
    assert 'action sequence: ["Place(1, 0)", "Open(3)"' in text and 'Close(3)' in text
    assert icl_examples.examples_for(fake('epog', 'examples_v2', 'kitchen')) == ''
    assert icl_examples.examples_for(fake('epog_language_goal', 'examples_v2', 'grill')) == ''
    with pytest.raises(ValueError):
        icl_examples.examples_for(fake('llm_planner', 'examples_v3', 'grill'))


def answers(text, marker):
    """The good and bad answer blocks of each example: the lines after ``marker`` up to the Outcome."""
    out = []
    for part in text.split(marker)[1:]:
        out.append(part.split('Outcome:')[0])
    return out


def test_llm_planner_examples_parse_as_its_plans():
    blocks = answers(icl_examples.llm_planner_examples(), 'answer:\n')
    assert len(blocks) == 4
    plans = [parse_plan(b)[0] for b in blocks]
    assert all(p for p in plans)
    assert plans[0][0] == ('pick', 'basket', 'shelf') and plans[0][5] == ('close', 'dryer_door')
    assert plans[2][:2] == [('pick', 'dry_towel_2', 'inside_dryer'), ('place', 'dry_towel_2', 'basket_top')]


def test_inner_monologue_examples_parse_as_final_actions():
    blocks = answers(icl_examples.inner_monologue_examples(), 'answer:\n')
    plans = [parse_final_actions(b)[0] for b in blocks]
    assert [len(p) for p in plans] == [9, 5, 8, 8]
    assert plans[2][0] == ('pick', 'dry_towel_2')


def test_owl_tamp_examples_parse_as_sketches_with_achieve_goal():
    text = icl_examples.owl_tamp_examples()
    grounded = {('pick', o) for o in ('basket', 'wet_towel_1', 'dry_towel_2')} | {
        ('open', 'dryer_door'), ('close', 'dryer_door'), ('place_ontop', 'basket', 'laundry_area'),
        ('place_inside', 'wet_towel_1', 'inside_dryer'), ('place_ontop', 'wet_towel_1', 'basket_top'),
        ('place_ontop', 'dry_towel_2', 'basket_top')}
    for block in answers(text, 'answer:\n'):
        sketch, achieve, rejected = parse_sketch(block, grounded)
        assert sketch and achieve is not None and not rejected, (block, rejected)


def test_llm_planner_system_prompt_unchanged_in_zero_shot():
    def system(icl_mode, task_family):
        p = LLMPlannerPipeline.__new__(LLMPlannerPipeline)
        p.config = SimpleNamespace(icl_mode=icl_mode, task_family=task_family)
        p.available_actions = lambda: ('pick', 'place', 'open', 'close')
        return p.system_prompt()
    zero = system('zero_shot', 'grill')
    assert system('examples_v2', 'kitchen') == zero
    assert system('examples_v2', 'grill') == zero + '\n' + icl_examples.llm_planner_examples() + '\n'


def test_epog_resolve_message_unchanged_without_examples_and_its_examples_parse():
    import json
    from baselines.epog import NodeIds, SceneGraph, resolve_user_message, simulate_step
    from tests.baselines.test_epog import place
    ids = NodeIds()
    for n in ['table_center_area', 'inside_box', 'mug1', 'phone']:
        ids[n]
    g = SceneGraph(parent={'phone': 'inside_box'}, hand='mug1', overlaps={'phone': ('inside_box',)})
    err = simulate_step(g, place('mug1', 'inside_box'), SceneGraph(parent={'mug1': 'inside_box'}), ids)
    err.parking_place = ids['table_center_area']
    zero = resolve_user_message(err, ids)
    assert resolve_user_message(err, ids, '') == zero
    with_ex = resolve_user_message(err, ids, 'EXAMPLES\n')
    assert with_ex.replace('EXAMPLES\n', '') == zero and with_ex.index('EXAMPLES') < with_ex.index('Your robot is trying')
    for line in icl_examples.epog_examples().splitlines():
        if line.startswith('action sequence: '):
            assert all(a.split('(')[0] in ('Pick', 'Place', 'Open', 'Close') for a in json.loads(line[17:]))
