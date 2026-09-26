"""Phase 7c fixes (docs/AUDIT-3.md on branch audit): planner runtime errors are infrastructure
(B-1), the vLLM (OpenAI-compatible) planner client, real-model refusals and the settings
fingerprint, job cancellation, simulator errors, and (below) the replan-wait prompt, repeated
outputs per state and action, and the WHEN pick-source rule."""

import pytest

from llm_pipeline import client as client_module
from llm_pipeline import vllm_client as vllm_module
from llm_pipeline.failures import FailureCode
from llm_pipeline.pipeline_types import FailureEvent, FailureLayer, FailureSource, FailureStage, PlanResult, PromptBundle
from llm_pipeline.tests.test_if_where_pipeline import INITIAL, _blocks, _run
from llm_pipeline.tests.test_phase7b import _remote
from llm_pipeline.tests.test_remote_client import _FakeRequests, _FakeResponse

CORRECTIVE = {'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective'}
PARALLEL = dict(CORRECTIVE, **{'parallel.enabled': 'true'})
REVISION = vllm_module.PINNED_MODELS['qwen3-vl-8b-thinking']['revision']


def _events(events, kind):
    return [e for e in events if e['event'] == kind]


# ------------------------------------------------------------------- B-1: runtime errors
def test_a_planner_runtime_error_is_a_job_error_on_the_server() -> None:
    from llm_pipeline.planner import PlannerRuntimeError, TextLLMPlanner
    from llm_pipeline.server import PlanJobQueue

    planner = TextLLMPlanner(model_name='none', model_alias='none')
    with pytest.raises(PlannerRuntimeError, match='Model not loaded'):
        planner.generate_plan(system_prompt='s', user_prompt='u', icl_mode='zero_shot')
    queue = PlanJobQueue()
    state = queue.wait(queue.submit(lambda payload: planner.generate_plan('s', 'u', 'zero_shot'), None))
    assert state['status'] == 'error' and 'Model not loaded' in state['error']


def test_an_unsuccessful_empty_output_without_a_failure_event_is_infrastructure() -> None:
    oom = {'success': False, 'actions': [], 'raw_output': '', 'inference_time': 0.1,
           'error_message': 'CUDA out of memory', 'failure_event': None}
    _, result = _remote(_FakeRequests({}, oom))
    assert result.failure_event.failure_id == FailureCode.PLANNER_CALL_FAILED
    assert result.failure_event.evidence['kind'] == 'server_error' and 'out of memory' in result.failure_event.message
    # A genuinely unparseable model output stays a model failure (plan check), never infrastructure.
    bad = {'success': False, 'actions': [], 'raw_output': 'I think we should pick the mug.', 'inference_time': 0.1}
    _, result = _remote(_FakeRequests({}, bad))
    assert result.failure_event is None or result.failure_event.failure_id != FailureCode.PLANNER_CALL_FAILED


class _ServerErrorOnReplan:
    """Scripted initial plan; every later call goes through the real legacy client against a
    server whose job ended in error (the planner raised, e.g. out of memory)."""

    def __init__(self, base_cls, outputs):
        self.base = base_cls(outputs)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def plan(self, bundle):
        if not self.base.bundles:
            return self.base.plan(bundle)
        self.base.bundles.append(bundle)
        fake = _FakeRequests({}, {}, job_states=[{'job_id': 'job1', 'status': 'error', 'queue_wait_s': 0.0,
                                                  'running_for_s': 1.0, 'error': 'PlannerRuntimeError: CUDA OOM'}])
        return _remote(fake)[1]


@pytest.mark.parametrize('flags', [CORRECTIVE, PARALLEL], ids=['serial_corrective', 'parallel_corrective'])
def test_a_server_runtime_error_ends_the_trial_as_infrastructure(tmp_path, flags) -> None:
    import llm_pipeline.tests.test_if_where_pipeline as base

    original = base.ScriptedPlanner
    base.ScriptedPlanner = lambda outputs: _ServerErrorOnReplan(original, outputs)
    try:
        pipeline, planner, summary, events = _run(tmp_path, [INITIAL, _blocks('urgent', 'front')], **flags)
    finally:
        base.ScriptedPlanner = original
    assert pipeline.termination_reason == 'infrastructure'
    replan = [e for e in _events(events, 'planning_event') if e['kind'] == 'replan']
    assert len(replan) == 1 and replan[0]['output_format'] == 'corrective'
    assert _events(events, 'plan_check')[-1]['failure_codes'] == [str(FailureCode.PLANNER_CALL_FAILED)]


# ------------------------------------------------------------------- vLLM client
class _FakeVLLM:
    class ConnectionError(Exception):
        pass

    class Timeout(Exception):
        pass

    def __init__(self, completion=None, root=None, version='0.30.0', status=200, timeout=False, roots=None):
        self.completion = completion or {}
        self.roots = list(roots or [])
        self.root = root or f'/hf/hub/models--Qwen--Qwen3-VL-8B-Thinking/snapshots/{REVISION}'
        self.version, self.status, self.timeout = version, status, timeout
        self.posts = []

    def get(self, url, timeout=None):
        if url.endswith('/v1/models'):
            root = self.roots.pop(0) if self.roots else self.root
            return _FakeResponse(payload={'data': [{'id': 'qwen3-vl-8b-thinking', 'root': root, 'max_model_len': 32768}]})
        if url.endswith('/version'):
            return _FakeResponse(payload={'version': self.version})
        return _FakeResponse(status_code=404, text='not found')

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json, timeout))
        if self.timeout:
            raise self.Timeout('read timed out')
        if self.status != 200:
            return _FakeResponse(status_code=self.status, text='internal error')
        return _FakeResponse(payload=self.completion)


def _completion(content, reasoning='thinking...', finish='stop'):
    return {'model': 'qwen3-vl-8b-thinking', 'usage': {'prompt_tokens': 100, 'completion_tokens': 50},
            'choices': [{'finish_reason': finish, 'message': {'content': content, 'reasoning_content': reasoning}}]}


def _vllm(fake, metadata=None, images=None):
    old = vllm_module.requests
    vllm_module.requests = fake
    try:
        planner = vllm_module.VLLMChatPlanner(server_url='http://127.0.0.1:8000')
        planner.connect_backoff_s = 0.0
        assert planner.load_model()
        bundle = PromptBundle(goal_text='g', system_prompt='sys', user_prompt='user', visible_objects=[],
                              valid_regions=[], icl_mode='zero_shot', images=images,
                              metadata=dict(metadata or {'max_new_tokens': 4096}))
        return planner, planner.plan(bundle)
    finally:
        vllm_module.requests = old


def test_the_vllm_client_reports_settings_and_uses_the_recommended_sampling() -> None:
    fake = _FakeVLLM(_completion('FINAL ACTIONS:\nNO_ACTIONS'))
    planner, result = _vllm(fake)
    settings = planner.server_settings
    assert settings['model_revision'] == REVISION and settings['vllm_version'] == '0.30.0'
    assert settings['thinking_mode'] == 'on' and settings['format_repair'] is False and settings['fingerprint']
    body = fake.posts[0][1]
    assert body['chat_template_kwargs'] == {'enable_thinking': True} and body['model'] == 'qwen3-vl-8b-thinking'
    # Text-only request: the model card's text preset.
    assert (body['temperature'], body['top_p'], body['top_k'], body['presence_penalty']) == (1.0, 0.95, 20, 1.5)
    assert result.success is True and result.reasoning == 'thinking...'
    assert result.timing['finish_reason'] == 'stop' and result.timing['completion_tokens'] == 50


def test_an_image_request_uses_the_vl_preset() -> None:
    import numpy as np

    fake = _FakeVLLM(_completion('FINAL ACTIONS:\nNO_ACTIONS'))
    _vllm(fake, images=[np.zeros((8, 8, 3), dtype=np.uint8)])
    body = fake.posts[0][1]
    assert body['presence_penalty'] == 0.0 and body['messages'][-1]['content'][0]['type'] == 'image_url'


@pytest.mark.parametrize('fake,kind', [
    (_FakeVLLM(status=500), 'http_status'),
    (_FakeVLLM(timeout=True), 'generation_timeout'),
    (_FakeVLLM(_completion('x'), roots=[f'/hf/snapshots/{REVISION}', '/hf/snapshots/' + 'b' * 40]), 'settings_changed'),
], ids=['http_500', 'timeout', 'settings_changed_mid_trial'])
def test_server_side_problems_are_infrastructure(fake, kind) -> None:
    _, result = _vllm(fake)
    assert result.failure_event.failure_id == FailureCode.PLANNER_CALL_FAILED
    assert result.failure_event.should_replan is False and result.failure_event.evidence['kind'] == kind


def test_model_outputs_are_model_failures_even_when_cut_off() -> None:
    _, result = _vllm(_FakeVLLM(_completion('', finish='length')))
    assert result.failure_event is not None and result.failure_event.failure_id != FailureCode.PLANNER_CALL_FAILED
    assert result.timing['finish_reason'] == 'length'
    # Corrective blocks come back raw (parsed by the pipeline); an empty answer is not infrastructure.
    _, result = _vllm(_FakeVLLM(_completion('', finish='length')),
                      metadata={'max_new_tokens': 4096, 'output_format': 'corrective_blocks'})
    assert result.success is False and result.failure_event is None and 'cut off' in result.error_message


# ------------------------------------------------------------------- refusals (item 6)
GOOD_VLLM = {'planner': 'vllm', 'model_name': 'qwen3-vl-8b-thinking', 'model_revision': REVISION,
             'vllm_version': '0.30.0', 'thinking_mode': 'on', 'format_repair': False}
CLEAN = {'commit': 'abc', 'dirty': False}


@pytest.mark.parametrize('change,message', [
    ({'model_name': 'other-model'}, 'not the requested'),
    ({'model_revision': 'c' * 40}, 'differs from the pinned'),
    ({'model_revision': ''}, 'does not report the model revision'),
    ({'format_repair': None}, 'format repair is None'),
    ({'format_repair': 'false'}, "format repair is 'false'"),
    ({'vllm_version': None}, 'does not report its version'),
    ({'thinking_mode': 'off'}, 'thinking mode'),
])
def test_real_model_refusals_for_vllm(change, message) -> None:
    from llm_pipeline.trial_runner import real_model_refusals

    assert real_model_refusals(CLEAN, GOOD_VLLM, 'qwen3-vl-8b-thinking', REVISION) == []
    settings = dict(GOOD_VLLM, **change)
    if change.get('format_repair', 1) is None and 'format_repair' in change:
        settings.pop('format_repair')
    problems = real_model_refusals(CLEAN, settings, 'qwen3-vl-8b-thinking', REVISION)
    assert any(message in p for p in problems), problems


def test_real_model_refusals_for_the_legacy_server() -> None:
    from llm_pipeline.trial_runner import real_model_refusals

    good = {'planner': 'remote', 'model_name': 'm', 'model_revision': 'r', 'thinking_mode': 'on', 'format_repair': False,
            'server_git_commit': {'commit': 'abc', 'dirty': False}, 'model_loaded': True}
    assert real_model_refusals(CLEAN, good) == []
    assert any('dirty' in p for p in real_model_refusals(CLEAN, dict(good, server_git_commit={'commit': 'abc', 'dirty': True})))
    assert any('git commit' in p for p in real_model_refusals(CLEAN, dict(good, server_git_commit={'commit': None})))
    assert any('not loaded' in p for p in real_model_refusals(CLEAN, dict(good, model_loaded=False)))


def test_the_legacy_client_checks_the_fingerprint_on_every_call_and_cancels_on_timeout() -> None:
    changed = {'job_id': 'job1', 'status': 'queued', 'queue_wait_s': 0.1, 'running_for_s': 0.0,
               'settings_fingerprint': 'new'}
    fake = _FakeRequests({}, {}, job_states=[changed])
    _, result = _remote(fake, start_fingerprint='old')
    assert result.failure_event.evidence['kind'] == 'settings_changed'
    running = {'job_id': 'job1', 'status': 'running', 'queue_wait_s': 0.5, 'running_for_s': 11.0}
    fake = _FakeRequests({}, {}, job_states=[running])
    _, result = _remote(fake, request_timeout_s=10.0)
    assert result.failure_event.evidence['kind'] == 'generation_timeout'
    assert any(url.endswith('/plan/jobs/job1/cancel') for url, _, _ in fake.post_calls)


def test_a_cancelled_queued_job_never_runs() -> None:
    import threading
    from llm_pipeline.server import PlanJobQueue

    gate, ran = threading.Event(), []
    queue = PlanJobQueue()
    first = queue.submit(lambda p: gate.wait(5), None)
    second = queue.submit(lambda p: ran.append(p), 'x')
    assert queue.cancel(second) == 'cancelled'
    gate.set()
    queue.wait(first)
    assert queue.wait(second)['status'] == 'cancelled' and ran == []


# ------------------------------------------------------------------- simulator errors (item 7)
def test_simulator_exceptions_are_classified_apart_from_motion_failures() -> None:
    from llm_pipeline.executor import is_simulator_exception, simulator_error_event

    class FatalError(Exception):
        pass

    assert is_simulator_exception(FatalError('mj_step: simulation unstable'))
    assert is_simulator_exception(AttributeError("'NoneType' object has no attribute 'get_pose'"))
    assert not is_simulator_exception(RuntimeError('Could not find valid place configuration'))
    event = simulator_error_event('pick(mug1)', MemoryError('x'), {'object': 'mug1'})
    assert event.failure_id == FailureCode.SIMULATOR_ERROR and event.should_replan is False


def test_a_simulator_error_during_an_action_ends_the_trial_as_infrastructure(tmp_path) -> None:
    import llm_pipeline.tests.test_if_where_pipeline as base
    from llm_pipeline.executor import PrimitiveExecutionOutcome, simulator_error_event

    class CrashingExecutor(base.TriggerExecutor):
        def execute_actions(self, actions, failure_checker, **kwargs):
            event = simulator_error_event(actions[0], OSError('EGL context lost'), {})
            self.remaining_actions = [str(a) for a in actions]
            return PrimitiveExecutionOutcome(False, list(self.completed_primitive_actions), self.remaining_actions,
                                             None, event, event.message)

    original = base.TriggerExecutor
    base.TriggerExecutor = CrashingExecutor
    try:
        pipeline, planner, summary, events = _run(tmp_path, [INITIAL])
    finally:
        base.TriggerExecutor = original
    assert pipeline.termination_reason == 'infrastructure' and len(planner.bundles) == 1


# ------------------------------------------------------------------- replan-wait prompt (item 3)
def prompt_contradictions(prompt: str) -> list:
    """Contradictions between a replan prompt's Current state and its action lists: an object
    whose last completed place is not where the state shows it, a held object the state does
    not show, and an action listed twice (completed, scheduled or remaining)."""
    import re

    def section(title):
        part = prompt.split(title, 1)
        return part[1].split('\n## ', 1)[0] if len(part) == 2 else ''

    state = dict(re.findall(r'^- ([a-z0-9_]+): ([a-z_]+)$', section('## Current state\n'), re.M))
    holding = re.search(r'^Gripper: holding ([a-z0-9_]+)$', prompt, re.M)
    lists = {name: re.findall(r'^- (a\d+): (.+)$', section(title), re.M) for name, title in (
        ('completed', '## Completed actions\n'), ('scheduled', '## Scheduled to run'),
        ('remaining', '## Remaining plan (not executed yet)\n'))}
    problems = []
    ids = [action_id for items in lists.values() for action_id, _ in items]
    problems += [f'{i} listed twice' for i in sorted({i for i in ids if ids.count(i) > 1})]
    last_place, held = {}, None
    for _, action in lists['completed']:
        name, _, rest = action.partition('(')
        args = [a.strip() for a in rest.rstrip(')').split(',')]
        if name == 'pick':
            held = args[0]
        elif name == 'place':
            last_place[args[0]], held = args[1], None
    for obj, region in last_place.items():
        if obj in state and state[obj] != region:
            problems.append(f'{obj}: completed actions put it in {region}, the state shows {state[obj]}')
    if held and (not holding or holding.group(1) != held):
        problems.append(f'completed actions leave {held} held; the state does not')
    return problems


def test_the_parallel_replan_prompt_lists_scheduled_actions_and_cannot_contradict_the_state(tmp_path) -> None:
    from pathlib import Path
    from llm_pipeline.tests.test_parallel import INITIAL as PARALLEL_INITIAL, _parallel_run

    pipeline, planner, summary, events = _parallel_run(tmp_path, [PARALLEL_INITIAL, _blocks('urgent', 'front')])
    prompt = planner.bundles[1].user_prompt
    snapshot = Path(__file__).parent / 'snapshots' / 'prompt_v2_kitchen_parallel_corrective_user.txt'
    assert prompt == snapshot.read_text()
    assert prompt_contradictions(prompt) == []
    # The Phase 7b form (independent actions listed as completed) is caught by the check.
    old = prompt.replace('## Scheduled to run before your corrective block is applied (not executed yet)\n', '')
    assert any('spam' in p for p in prompt_contradictions(old))
    # The planner's metadata matches the prompt: remaining = not scheduled.
    metadata = planner.bundles[1].metadata
    assert [i for i, _ in metadata['remaining_plan']] == ['a8', 'a9']
    assert [i for i, _ in metadata['scheduled_actions']] == ['a4', 'a5', 'a6', 'a7']


# ------------------------------------------------------------------- repeated outputs (item 4)
def test_repeats_are_counted_per_state_output_and_failure_not_per_trial() -> None:
    from llm_pipeline.tests.test_phase7b import _bare_pipeline

    pipeline = _bare_pipeline(memory=False)
    pipeline.termination_reason = None
    exec_fail = FailureEvent(failure_id=FailureCode.PDDL_NO_PLAN, stage=FailureStage.AFTER_EXECUTION,
                             source=FailureSource.PDDL, action='pick(sugar)', evidence={}, message='no plan')
    output = PlanResult(False, [], 'FINAL ACTIONS:\npick(sugar)\nplace(sugar, cupboard_shelf)', 0.0)

    def call(state, event):
        return pipeline._repeated_output({'abstract_state': state, 'failure_event': event, 'corrective': None}, output)

    assert call('S1', exec_fail) is None                       # first time
    first = call('S1', exec_fail)                              # repeat 1 in S1: re-query with a note
    assert first.failure_event.should_replan is True
    assert call('S2', exec_fail) is None
    assert call('S2', exec_fail).failure_event.should_replan is True   # repeat 1 in S2: not a stop
    assert pipeline.termination_reason is None
    # The note re-query answers the same failure as the call it repeats: a second repeat stops.
    assert call('S1', first.failure_event).failure_event.should_replan is False
    assert pipeline.termination_reason == 'replan_loop'
    # A different failure in the same state is a different key.
    other = FailureEvent(failure_id=FailureCode.GRASP_FAILED, stage=FailureStage.AFTER_EXECUTION,
                         source=FailureSource.VALIDATION, action='pick(sugar)', evidence={}, message='grasp')
    assert call('S1', other) is None


# ------------------------------------------------------------------- WHEN rule (ii) (item 5)
def test_a_dependent_bundle_pick_source_blocks_later_places_into_it() -> None:
    """K1-w2 with mug3 left in the cupboard (audit 3, C2 case A1): the groceries must not fill
    the cupboard while the dependent mug3 bundle has not taken mug3 out of it."""
    from llm_pipeline.parallel import affected_set, independent_bundles, split_bundles

    remaining = [('a4', 'pick(mug1)'), ('a5', 'place(mug1, inside_box)'), ('a6', 'pick(mug2)'),
                 ('a7', 'place(mug2, inside_box)'), ('a8', 'pick(mug3)'), ('a9', 'place(mug3, inside_box)'),
                 ('a10', 'pick(spam)'), ('a11', 'place(spam, cupboard_shelf)'), ('a12', 'pick(sugar)'),
                 ('a13', 'place(sugar, cupboard_shelf)'), ('a14', 'pick(can_of_beans)'),
                 ('a15', 'place(can_of_beans, cupboard_shelf)'), ('a16', 'pick(can_of_beans_2)'),
                 ('a17', 'place(can_of_beans_2, cupboard_shelf)')]
    regions = {'mug1': 'pantry_area', 'mug2': 'table_staging_area', 'mug3': 'cupboard_shelf', 'spam': 'pantry_area',
               'sugar': 'pantry_area', 'can_of_beans': 'pantry_area', 'can_of_beans_2': 'pantry_area',
               'phone': 'inside_box'}
    affected = affected_set('kitchen', ['phone'], regions, overlapping={'phone': ['inside_box']})
    assert independent_bundles(split_bundles(remaining, regions), affected) == []
    # With mug3 already staged out of the cupboard (the oracle's order), the groceries run.
    staged = dict(regions, mug3='table_staging_area')
    independent = independent_bundles(split_bundles(remaining, staged), affected)
    assert [b.ids[0] for b in independent] == ['a10', 'a12', 'a14', 'a16']


def test_pick_sources_are_projected_along_the_plan() -> None:
    from llm_pipeline.parallel import split_bundles

    remaining = [('a4', 'pick(raw_meat_1)'), ('a5', 'place(raw_meat_1, inside_grill)'), ('a6', 'close(grill_lid)'),
                 ('a7', 'open(grill_lid)'), ('a8', 'pick(raw_meat_1)'), ('a9', 'place(raw_meat_1, plate_top)')]
    bundles = split_bundles(remaining, {'raw_meat_1': 'prep_area'})
    assert bundles[0].sources == {'prep_area'} and bundles[-1].sources == {'inside_grill'}


# ------------------------------------------------------------------- cupboard placement (item 2)
class _Box:
    """A shape stand-in: local bounding box, pose and a world bounding box."""

    def __init__(self, name, center, dims, yaw=0.0):
        import math
        self.name, self.center, self.dims, self.yaw = name, center, dims, yaw
        self.q = [0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2)]

    def get_name(self):
        return self.name

    def get_handle(self):
        return id(self)

    def get_bounding_box(self):
        dx, dy, dz = self.dims
        return [-dx / 2, dx / 2, -dy / 2, dy / 2, -dz / 2, dz / 2]

    def get_pose(self):
        return list(self.center) + self.q

    def world(self):
        import math
        dx, dy, dz = self.dims
        c, s = abs(math.cos(self.yaw)), abs(math.sin(self.yaw))
        hx, hy = 0.5 * (dx * c + dy * s), 0.5 * (dx * s + dy * c)
        x, y, z = self.center
        return [x - hx, x + hx, y - hy, y + hy, z - dz / 2, z + dz / 2]


def _kitchen_env(objects):
    import rlbench_kitchen_env as K

    env = object.__new__(K.RLBenchKitchenEnv)
    env.cupboard = _Box('cupboard', (0.5945, 0.0, 1.533), (0.321, 0.538, 0.644))
    env.name_to_obj = {o.name: o for o in objects}
    env._get_world_bounding_box = lambda o: o.world()
    return env


def test_the_side_grasp_quaternion_approaches_horizontally_and_closes_horizontally() -> None:
    import numpy as np
    import rlbench_kitchen_env as K

    for yaw in (0.0, 0.7):
        x, y, z, w = K.side_grasp_quat(yaw, np.pi / 2)
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                      [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                      [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
        approach, closing = R[:, 2], R[:, 0]
        assert np.allclose(approach, [np.cos(yaw), np.sin(yaw), 0.0], atol=1e-9)
        assert abs(closing[2]) < 1e-9 and abs(float(np.dot(closing, approach))) < 1e-9


def test_non_round_groceries_are_placed_thin_side_across_and_cans_keep_the_old_placement() -> None:
    import numpy as np

    sugar = _Box('sugar', (0.06, -0.40, 0.8375), (0.035, 0.09, 0.175), yaw=0.29)
    can = _Box('soup', (0.0, 0.26, 0.80), (0.055, 0.055, 0.10))
    env = _kitchen_env([sugar, can])
    spec = env.cupboard_placement_spec(sugar)
    assert spec['thin'] == pytest.approx(0.035) and spec['long'] == pytest.approx(0.09)
    # The pick closes across the thin side: the local x axis (0.035) rotated by the object yaw.
    assert np.isclose(np.cos(spec['closing_yaw'] - 0.29), 1.0) or np.isclose(np.cos(spec['closing_yaw'] - 0.29), -1.0)
    assert env.cupboard_placement_spec(can) is None
    interior = env.cupboard_interior()
    assert interior['min_y'] == pytest.approx(-0.258) and interior['max_y'] == pytest.approx(0.258)
    assert interior['shelf_z'] == pytest.approx(1.222)


def test_the_cupboard_sampler_only_returns_free_spots_packed_tightest_first() -> None:
    placed = [_Box('can_a', (0.48, -0.15, 1.25), (0.055, 0.055, 0.10)),
              _Box('can_b', (0.48, 0.05, 1.25), (0.055, 0.055, 0.10))]
    sugar = _Box('sugar', (0.06, -0.40, 0.8375), (0.035, 0.09, 0.175))
    env = _kitchen_env(placed + [sugar])
    interior = env.cupboard_interior()
    free = env._cupboard_free_candidates(sugar, 0.0175, interior)
    assert free, 'the shelf has room'
    for _, y in free:
        for box in placed:
            _, _, y0, y1, _, _ = box.world()
            assert y + 0.0175 + 0.01 <= y0 + 1e-9 or y - 0.0175 - 0.01 >= y1 - 1e-9
    gaps = [gap for gap, _ in free]
    assert gaps == sorted(gaps) and gaps[0] == pytest.approx(0.0, abs=0.006)
    # A shelf with no room gives no spot (the place then has no plan).
    row = [_Box(f'c{i}', (0.48, -0.21 + 0.068 * i, 1.25), (0.055, 0.055, 0.10)) for i in range(7)]
    full = _kitchen_env(row + [sugar])
    assert full._cupboard_free_candidates(sugar, 0.0175, full.cupboard_interior()) == []
