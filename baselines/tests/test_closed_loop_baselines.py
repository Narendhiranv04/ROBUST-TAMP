"""Unit tests of LLM-Planner and Inner Monologue: replan triggers and output handling, with the mock
planner and a symbolic fake world in place of the simulator."""

from types import SimpleNamespace

from baselines.common import ModelChat, Observation
from baselines.inner_monologue import InnerMonologuePipeline, feedback_lines, parse_final_actions
from baselines.llm_planner import LLMPlannerPipeline, belief_description, parse_plan, split_bundles
from baselines.mock import MockPlanner
from llm_pipeline.failures import TerminationReason


class FakeWorld:
    """Objects in regions; box_lid hides the objects inside_box while closed; listed actions fail."""

    def __init__(self, objects, hidden=None, fail=(), fail_times=1):
        self.objects = dict(objects)
        self.hidden = dict(hidden or {})          # object -> region, visible once box_lid is open
        self.lid_open = False
        self.fail = {f: fail_times for f in fail}
        self.executed = []

    def observation(self):
        visible = dict(self.objects)
        if self.lid_open:
            visible.update(self.hidden)
        return Observation(objects=visible, lids={'box_lid': self.lid_open}, holding=None,
                           regions=['table', 'inside_box', 'cupboard_shelf', 'box_lid_top'])

    def execute(self, bundle):
        for a in bundle:
            text = f"{a[0]}({', '.join(a[1:])})"
            if self.fail.get(text, 0) > 0:
                self.fail[text] -= 1
                return {'success': False, 'failure': f'{text} failed', 'failure_code': 'placement_failed',
                        'failed_action': text}
            self.executed.append(text)
            if a[0] == 'open':
                self.lid_open = True
            elif a[0] == 'place':
                self.hidden.pop(a[1], None)
                self.objects[a[1]] = a[2]
        return {'success': True, 'failure': None, 'failure_code': None, 'failed_action': None}


def make(cls, world, respond, max_replans=10):
    """A baseline pipeline over the fake world, without a simulator or model server."""

    class Fake(cls):
        def observe_scene(self):
            return world.observation()

        def execute_bundle(self, bundle):
            return world.execute(bundle)

        def available_actions(self):
            return ('pick', 'place', 'open')

        def current_state_text(self, obs):
            return '## Current state\n' + belief_description(obs)

    pipeline = object.__new__(Fake)
    events = []
    pipeline.__dict__.update(
        config=SimpleNamespace(max_replans=max_replans, planner_max_new_tokens=100, icl_mode='zero_shot'),
        planner=MockPlanner(), step=0, cycles=[], termination_reason=None, _baseline_trace={}, events=events,
        executor=SimpleNamespace(completed_primitive_actions=[], remaining_actions=[]),
        trial_logger=SimpleNamespace(save_prompt=lambda *a, **k: 'prompt.txt', save_exchange=lambda *a, **k: {}),
        _log_event=lambda name, **record: events.append((name, record)))
    prompts = []

    def responder(purpose, turns):
        prompts.append((purpose, turns[-1][1]))
        return respond(purpose, turns[-1][1], len(prompts))

    pipeline._chat = ModelChat(pipeline.planner, pipeline, 100, responder=responder)
    return pipeline, prompts


# --- LLM-Planner ---------------------------------------------------------------------------------

def test_llm_planner_parses_the_reference_json_plan():
    text = ('<think>x</think>Sure.\n{"Plan": ["Pick(mug1, table)", "Place(mug1, inside_box)", "Open(box_lid)", '
            '"Walk(5)", "garbage"]}')
    plan, skipped = parse_plan(text)
    assert plan == [('pick', 'mug1', 'table'), ('place', 'mug1', 'inside_box'), ('open', 'box_lid')]
    assert skipped == ['Walk(5)', 'garbage']
    assert parse_plan('no json here')[0] is None
    assert parse_plan('{"plan": []}')[0] is None             # the reference reads the key "Plan"
    assert parse_plan('{"Plan": []}')[0] == []
    assert split_bundles(plan) == [[('pick', 'mug1', 'table'), ('place', 'mug1', 'inside_box')], [('open', 'box_lid')]]


def test_llm_planner_replans_the_full_plan_when_a_new_object_appears():
    world = FakeWorld({'mug1': 'table'}, hidden={'phone': 'inside_box'})

    def respond(purpose, prompt, n):
        if 'phone is in' in prompt:
            return '{"Plan": ["Pick(phone, inside_box)", "Place(phone, table)", "Pick(mug1, table)", ' \
                   '"Place(mug1, inside_box)"]}'
        return '{"Plan": ["Open(box_lid)", "Pick(mug1, table)", "Place(mug1, inside_box)"]}'

    pipeline, prompts = make(LLMPlannerPipeline, world, respond)
    assert pipeline.run_baseline('put the mug in the box and the phone on the table') is None
    # the open revealed the phone: the rest of the first plan was dropped and a full plan generated
    assert [p for p, _ in prompts] == ['llm_planner_plan', 'llm_planner_replan']
    assert world.executed == ['open(box_lid)', 'pick(phone)', 'place(phone, table)', 'pick(mug1)',
                              'place(mug1, inside_box)']
    assert 'box_lid is closed' in prompts[0][1] and 'phone is in inside_box' in prompts[1][1]
    assert pipeline._baseline_trace['queries'][1]['replan_reason'] == 'new objects observed: phone'


def test_llm_planner_replans_after_a_failed_step_and_stops_at_the_budget():
    world = FakeWorld({'mug1': 'table'}, fail=['place(mug1, cupboard_shelf)'], fail_times=99)
    pipeline, prompts = make(LLMPlannerPipeline, world,
                             lambda *_: '{"Plan": ["Pick(mug1, table)", "Place(mug1, cupboard_shelf)"]}', max_replans=3)
    reason = pipeline.run_baseline('put the mug on the shelf')
    assert 'budget exhausted' in reason and len(prompts) == 4          # the initial plan + 3 replans
    assert pipeline.termination_reason == TerminationReason.REPLAN_BUDGET_EXHAUSTED
    assert len(pipeline.cycles) == 4 and not pipeline.cycles[-1].success


def test_llm_planner_invalid_output_and_unknown_names_trigger_a_replan():
    world = FakeWorld({'mug1': 'table'})
    answers = ['I cannot do that.', '{"Plan": ["Pick(cup9, table)", "Place(cup9, inside_box)"]}',
               '{"Plan": ["Pick(mug1, table)", "Place(mug1, cupboard_shelf)"]}']
    pipeline, prompts = make(LLMPlannerPipeline, world, lambda p, t, n: answers[n - 1])
    assert pipeline.run_baseline('put the mug on the shelf') is None
    queries = pipeline._baseline_trace['queries']
    assert queries[1]['replan_reason'] == 'output_not_valid_json'
    assert queries[2]['replan_reason'].startswith('step failed: unknown name(s): cup9')
    assert world.executed == ['pick(mug1)', 'place(mug1, cupboard_shelf)']


def test_llm_planner_place_on_the_plate_object_is_its_top_surface():
    from baselines.llm_planner import resolve_supports

    obs = Observation(objects={'plate': 'serving_area', 'meat': 'grill'}, lids={}, holding=None,
                      regions=['serving_area', 'plate_top', 'grill'])
    assert resolve_supports([('pick', 'meat'), ('place', 'meat', 'plate')], obs)[1] == ('place', 'meat', 'plate_top')


# --- Inner Monologue -------------------------------------------------------------------------------

def test_inner_monologue_parses_final_actions():
    assert parse_final_actions('think\nFINAL ACTIONS:\n1. pick(mug1)\n- place(mug1, table)\n') == \
        ([('pick', 'mug1'), ('place', 'mug1', 'table')], [])
    assert parse_final_actions('FINAL ACTIONS:\nNO_ACTIONS') == ([], [])
    assert parse_final_actions('pick(mug1)')[0] is None                       # no marker
    assert parse_final_actions('FINAL ACTIONS:\nwave(hand)') == (None, ['wave(hand)'])


def test_inner_monologue_queries_after_every_bundle_with_feedback():
    world = FakeWorld({'mug1': 'table', 'mug2': 'table'}, hidden={'phone': 'inside_box'})

    def respond(purpose, prompt, n):
        plan = ['open(box_lid)', 'pick(mug1)', 'place(mug1, inside_box)', 'pick(mug2)', 'place(mug2, inside_box)']
        done = set(world.executed)
        rest = [a for a in plan if a not in done]
        return 'FINAL ACTIONS:\n' + ('\n'.join(rest) if rest else 'NO_ACTIONS')

    pipeline, prompts = make(InnerMonologuePipeline, world, respond)
    assert pipeline.run_baseline('put the mugs in the box') is None
    # one query per executed bundle (3), then NO_ACTIONS; only the first bundle of each plan ran
    assert len(prompts) == 4 and len(pipeline._baseline_trace['steps']) == 3
    assert world.executed == ['open(box_lid)', 'pick(mug1)', 'place(mug1, inside_box)', 'pick(mug2)',
                              'place(mug2, inside_box)']
    second = prompts[1][1]
    assert 'Robot action: open(box_lid)\nSuccess: True\nScene: newly visible objects: phone (inside_box).' in second
    assert 'Robot action: pick(mug1), place(mug1, inside_box)\nSuccess: True\nScene: no new objects.' in prompts[2][1]
    assert [p for p, _ in prompts] == ['inner_monologue_plan'] + ['inner_monologue_step'] * 3


def test_inner_monologue_failure_feedback_and_budget():
    world = FakeWorld({'mug1': 'table'}, fail=['place(mug1, cupboard_shelf)'], fail_times=99)
    pipeline, prompts = make(InnerMonologuePipeline, world,
                             lambda *_: 'FINAL ACTIONS:\npick(mug1)\nplace(mug1, cupboard_shelf)', max_replans=2)
    reason = pipeline.run_baseline('put the mug on the shelf')
    assert 'budget exhausted' in reason and len(prompts) == 3                 # failures 1, 2, then 3 > 2
    assert 'Success: False (place(mug1, cupboard_shelf) did not succeed)' in prompts[1][1]
    assert prompts[1][0] == 'inner_monologue_replan'
    assert pipeline.termination_reason == TerminationReason.REPLAN_BUDGET_EXHAUSTED


def test_inner_monologue_unusable_answer_is_a_failed_step():
    world = FakeWorld({'mug1': 'table'})
    answers = ['I am not sure.', 'FINAL ACTIONS:\npick(mug1)\nplace(mug1, cupboard_shelf)', 'FINAL ACTIONS:\nNO_ACTIONS']
    pipeline, prompts = make(InnerMonologuePipeline, world, lambda p, t, n: answers[n - 1])
    assert pipeline.run_baseline('put the mug on the shelf') is None
    assert 'Robot action: (none: the answer had no FINAL ACTIONS list of actions)\nSuccess: False' in prompts[1][1]
    assert world.executed == ['pick(mug1)', 'place(mug1, cupboard_shelf)']


def test_feedback_lines_text():
    step = {'bundle': ['pick(mug1)', 'place(mug1, inside_box)'], 'success': False,
            'failed_action': 'place(mug1, inside_box)', 'newly_observed': []}
    assert feedback_lines(step, {}) == ['Robot action: pick(mug1), place(mug1, inside_box)',
                                        'Success: False (place(mug1, inside_box) did not succeed)',
                                        'Scene: no new objects.']


def test_llm_planner_prompt_has_the_domain_definitions_and_grounds_containers():
    from baselines.llm_planner import LLMPlannerReferencePromptPipeline

    world = FakeWorld({'mug1': 'table', 'mug2': 'box_lid_top'})
    answers = ['{"Plan": ["Pick(mug2, box_lid_top)", "Place(mug2, table)", "Open(box)", "Pick(mug1, table)", '
               '"Place(mug1, inside_box)"]}']
    pipeline, prompts = make(LLMPlannerPipeline, world, lambda p, t, n: answers[0])
    assert pipeline.run_baseline('put mug1 in the box') is None
    assert world.executed == ['pick(mug2)', 'place(mug2, table)', 'open(box_lid)', 'pick(mug1)', 'place(mug1, inside_box)']
    system = pipeline.system_prompt()
    assert "'Open(x): Open container x'," in system
    assert 'no object is on the top surface of l' in system and 'close(l)' not in system   # the scene's actions only
    reference = make(LLMPlannerReferencePromptPipeline, FakeWorld({'mug1': 'table'}), lambda *_: '{"Plan": []}')[0]
    assert 'Preconditions' not in reference.system_prompt()
    world = FakeWorld({'mug1': 'table'})
    pipeline, _ = make(LLMPlannerReferencePromptPipeline, world,
                       lambda p, t, n: '{"Plan": ["Open(box)"]}' if n == 1 else '{"Plan": []}')
    assert pipeline.run_baseline('open the box') is None
    assert pipeline._baseline_trace['steps'][0]['failure'] == 'unknown name(s): box'     # verbatim: no grounding


def test_llm_planner_a_wrong_pick_source_fails_the_step():
    world = FakeWorld({'mug1': 'table', 'meat': 'plate_top'})
    answers = ['{"Plan": ["Pick(mug1, cupboard_shelf)", "Place(mug1, inside_box)"]}',
               '{"Plan": ["Pick(mug1, table)", "Place(mug1, inside_box)", "Pick(meat, plate)", "Place(meat, table)"]}']
    pipeline, prompts = make(LLMPlannerPipeline, world, lambda p, t, n: answers[min(n, 2) - 1])
    assert pipeline.run_baseline('put the mug in the box') is None
    steps = pipeline._baseline_trace['steps']
    assert steps[0]['failure_code'] == 'wrong_pick_source' and 'mug1 is in table, not cupboard_shelf' in steps[0]['failure']
    assert world.executed == ['pick(mug1)', 'place(mug1, inside_box)', 'pick(meat)', 'place(meat, table)']  # plate = plate_top
