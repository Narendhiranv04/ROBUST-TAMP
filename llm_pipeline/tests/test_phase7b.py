"""Phase 7b fixes (docs/AUDIT.md): corrective re-query (B1), one trigger path for both trigger
modes and explicit no-action output (B2), infrastructure classification (B4), planner-server
settings and job queue (B5), region resolution (B7), repeated-output detection (B8), memory
and the IF rule, and parallel log schema."""

import json
import time
from pathlib import Path

import pytest

from llm_pipeline import client as client_module
from llm_pipeline.client import RemoteTextLLMPlanner
from llm_pipeline.corrective import CorrectivePlanError, parse_blocks
from llm_pipeline.failures import FailureCode
from llm_pipeline.flags import PipelineFlags
from llm_pipeline.pipeline import LLMOnlyReplanningPipeline, LLMPipelineConfig
from llm_pipeline.pipeline_types import FailureEvent, FailureLayer, FailureSource, FailureStage, PlanResult
from llm_pipeline.tests.test_if_where_pipeline import INITIAL, _blocks, _run
from llm_pipeline.tests.test_remote_client import _FakeRequests
from llm_pipeline.trial_log import validate_trial_log

ROOT = Path(__file__).resolve().parents[2]
CORRECTIVE = {'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective'}
DISCOVERY_CORRECTIVE = {'replan.trigger_mode': 'discovery', 'replan.output_mode': 'corrective'}


def _block(actions, urgency='urgent', insert='front', objects='phone'):
    return ('FINAL BLOCKS:\nBLOCK\nobjects: ' + objects + f'\nurgency: {urgency}\ninsert: {insert}\n'
            'reason: r\nactions:\n' + '\n'.join(actions) + '\nEND BLOCK')


def _events(events, kind):
    return [e for e in events if e['event'] == kind]


# ------------------------------------------------------------------- corrective parser
def test_a_block_must_end_with_the_gripper_empty() -> None:
    with pytest.raises(CorrectivePlanError) as error:
        parse_blocks(_block(['pick(phone)']), ['phone'], ['a4'])
    assert error.value.failure_id == FailureCode.BLOCK_ENDS_HOLDING
    assert error.value.fact == 'block 1 ends with the gripper holding phone; a block must end with the gripper empty'


def test_no_action_output_forms() -> None:
    whole = parse_blocks('reasoning\nFINAL BLOCKS:\nNO_ACTIONS', ['phone', 'can_of_beans'], [])
    assert len(whole) == 1 and whole[0].no_action and whole[0].objects == ['phone', 'can_of_beans']
    mixed = parse_blocks('FINAL BLOCKS:\nBLOCK\nobjects: phone\nreason: not in the way\nactions:\nNO_ACTIONS\nEND BLOCK\n'
                         'BLOCK\nobjects: can_of_beans\nurgency: deferred\ninsert: end\nreason: r\nactions:\n'
                         'pick(can_of_beans)\nplace(can_of_beans, cupboard_shelf)\nEND BLOCK',
                         ['phone', 'can_of_beans'], [])
    assert [b.no_action for b in mixed] == [True, False]
    with pytest.raises(CorrectivePlanError, match='NO_ACTIONS'):
        parse_blocks('FINAL BLOCKS:\nBLOCK\nobjects: phone\nactions:\npick(phone)\nNO_ACTIONS\nEND BLOCK', ['phone'], [])


# ------------------------------------------------------------------- B1: no silent fallback
def test_an_unknown_region_in_a_block_requeries_for_blocks_with_the_error(tmp_path) -> None:
    bad = _block(['pick(phone)', 'place(phone, counter)'])
    pipeline, planner, summary, events = _run(tmp_path, [INITIAL, bad, _blocks('urgent', 'front')], **CORRECTIVE)
    insertion = _events(events, 'insertion')
    assert [e['accepted'] for e in insertion] == [False, True]
    assert insertion[0]['rejection_code'] == FailureCode.UNKNOWN_ACTION_TOKEN
    # The re-query asks for blocks again (never a full replan), with the specific error.
    assert 'FINAL BLOCKS:' in planner.bundles[2].system_prompt
    assert 'Your previous blocks were rejected (failure code unknown_action_token)' in planner.bundles[2].user_prompt
    assert "counter" in planner.bundles[2].user_prompt
    planning = _events(events, 'planning_event')
    assert [e['output_format'] for e in planning] == ['full', 'corrective', 'corrective']
    assert [e['replan_reason'] for e in planning] == ['initial', 'trigger:if_rule', 'corrective_requery']
    assert summary['success'] is True


def test_a_block_ending_while_holding_requeries_for_blocks(tmp_path) -> None:
    pipeline, planner, summary, events = _run(
        tmp_path, [INITIAL, _block(['pick(phone)']), _blocks('urgent', 'front')], **CORRECTIVE)
    insertion = _events(events, 'insertion')
    assert insertion[0]['rejection_code'] == FailureCode.BLOCK_ENDS_HOLDING
    assert 'a block must end with the gripper empty' in planner.bundles[2].user_prompt
    assert 'FINAL BLOCKS:' in planner.bundles[2].system_prompt and summary['success'] is True


def test_an_invalid_merged_plan_requeries_for_blocks(tmp_path) -> None:
    # A deferred block anchored between pick(mug2) and place(mug2, ...) makes the merged plan invalid.
    wedged = _block(['pick(phone)', 'place(phone, table)'], urgency='deferred', insert='after a4')
    pipeline, planner, summary, events = _run(tmp_path, [INITIAL, wedged, _blocks('urgent', 'front')], **CORRECTIVE)
    insertion = _events(events, 'insertion')
    assert insertion[0]['accepted'] is False and 'merged plan is invalid' in insertion[0]['rejection']
    assert 'FINAL BLOCKS:' in planner.bundles[2].system_prompt and summary['success'] is True


# ------------------------------------------------------------------- B2: one trigger path
def test_discovery_triggers_get_the_corrective_output_and_the_same_labels(tmp_path) -> None:
    pipeline, planner, summary, events = _run(tmp_path, [INITIAL, _blocks('urgent', 'front')], **DISCOVERY_CORRECTIVE)
    assert 'FINAL BLOCKS:' in planner.bundles[1].system_prompt
    assert ('phone (in inside_box): not relevant to the goal; lies where the remaining plan places objects into '
            'inside_box') in planner.bundles[1].user_prompt
    planning = _events(events, 'planning_event')
    assert planning[1]['trigger_code'] == 'new_object_discovered' and planning[1]['output_format'] == 'corrective'
    assert _events(events, 'insertion')[0]['accepted'] is True and summary['success'] is True


def _run_patched(tmp_path, outputs, pipeline_class, **flags):
    from llm_pipeline.tests.test_if_where_pipeline import PhoneBoxAdapter, TriggerExecutor
    from llm_pipeline.tests.test_phase1_pipeline import Checker, ScriptedPlanner
    from llm_pipeline.tests.test_pipeline import FakeEnv
    from llm_pipeline.trial_log import TrialLogger, read_trial_log

    adapter = PhoneBoxAdapter()
    planner = ScriptedPlanner(outputs)
    pipeline = pipeline_class(
        config=LLMPipelineConfig(model_alias='scripted', headless=True, live_segmentation_view=False,
                                 enable_goal_check=False, variant_id='K2', task_family='kitchen',
                                 flags=PipelineFlags().with_values(flags), max_replans=4),
        planner=planner, segmentation_adapter=adapter, failure_checker=Checker(adapter),
        executor=TriggerExecutor(adapter),
    )
    assert pipeline.initialize(env=FakeEnv())
    pipeline.symbol_registry = pipeline.symbol_registry.__class__(
        pipeline.symbol_registry.actions, tuple(pipeline.symbol_registry.objects) + ('phone',),
        pipeline.symbol_registry.regions)
    planner.parser = planner.parser.__class__(valid_actions=pipeline.symbol_registry.actions,
                                              valid_objects=pipeline.symbol_registry.objects,
                                              valid_regions=pipeline.symbol_registry.regions)
    pipeline.set_trial_logger(TrialLogger(tmp_path / 'log.jsonl', trial_id='K2'))
    summary = pipeline.run('move ALL THE MUGS inside the box')
    return pipeline, planner, summary, read_trial_log(tmp_path / 'log.jsonl')


class _NoOverlap(LLMOnlyReplanningPipeline):
    def _overlapping_regions(self, obj, regions):
        return []


def test_no_action_output_is_valid_and_logged_in_discovery_mode(tmp_path) -> None:
    pipeline, planner, summary, events = _run_patched(
        tmp_path, [INITIAL, 'The phone is not in the way.\nFINAL BLOCKS:\nNO_ACTIONS'], _NoOverlap,
        **DISCOVERY_CORRECTIVE)
    assert 'does not lie where the remaining plan places objects' in planner.bundles[1].user_prompt
    insertion = _events(events, 'insertion')
    assert len(insertion) == 1 and insertion[0]['accepted'] is True and insertion[0]['all_no_action'] is True
    assert insertion[0]['no_action_objects'] == ['phone'] and insertion[0]['urgency'] == {'phone': 'no_action'}
    assert insertion[0]['merged_plan'] == ['a4: pick(mug2)', 'a5: place(mug2, inside_box)']
    assert 'pick(phone)' not in summary['completed_actions'] and summary['success'] is True
    assert len(_events(events, 'planning_event')) == 2


def test_no_action_for_an_overlapping_object_is_still_insertion_too_late(tmp_path) -> None:
    pipeline, planner, summary, events = _run(
        tmp_path, [INITIAL, 'FINAL BLOCKS:\nNO_ACTIONS', _blocks('urgent', 'front')], **CORRECTIVE)
    insertion = _events(events, 'insertion')
    assert insertion[0]['rejection_code'] == FailureCode.INSERTION_TOO_LATE and insertion[1]['accepted'] is True


def test_discovery_triggers_use_the_parallel_path(tmp_path) -> None:
    from llm_pipeline.tests.test_parallel import INITIAL as PARALLEL_INITIAL, _parallel_run

    flags = dict(DISCOVERY_CORRECTIVE, **{'parallel.enabled': 'true'})
    pipeline, planner, summary, events = _parallel_run(tmp_path, [PARALLEL_INITIAL, _blocks('urgent', 'front')],
                                                       flags=flags)
    parallel = _events(events, 'parallel')
    assert len(parallel) == 1 and parallel[0]['merge_result'] == 'accepted'
    assert parallel[0]['independent_actions_executed']
    assert summary['success'] is True


def test_parallel_logs_pass_the_schema_check(tmp_path) -> None:
    from llm_pipeline.tests.test_parallel import INITIAL as PARALLEL_INITIAL, PARALLEL, _parallel_run

    pipeline, planner, summary, events = _parallel_run(tmp_path, [PARALLEL_INITIAL, _blocks('urgent', 'front')],
                                                       flags=PARALLEL)
    # The pipeline-only log has no trial_start/trial_end; every other schema rule must hold,
    # in particular non-decreasing steps (14 of 28 Phase 6 logs broke it before the fix).
    problems = [p for p in validate_trial_log(events) if 'trial_start' not in p and 'trial_end' not in p]
    assert problems == []
    planning = _events(events, 'planning_event')
    # Logged at the current step; the prompt was built at the (earlier) prompt_step.
    assert planning[1]['prompt_step'] <= planning[1]['step']


# ------------------------------------------------------------------- B8: repeated outputs
ORPHAN = 'FINAL ACTIONS:\nplace(mug2, inside_box)'


def test_a_repeated_output_is_requeried_once_then_the_trial_stops(tmp_path) -> None:
    # Phase 7c: repeats count per (state, output, failure answered); the initial call and the
    # plan-check re-query answer different failures, so the first repeat is the third call.
    pipeline, planner, summary, events = _run(tmp_path, [ORPHAN, ORPHAN, ORPHAN, ORPHAN])
    checks = [c['failure_codes'] for c in _events(events, 'plan_check')]
    assert checks == [['orphan_place'], ['orphan_place'], ['repeated_planner_output'], ['repeated_planner_output']]
    assert 'repeated_planner_output' in planner.bundles[3].user_prompt
    note = planner.bundles[3].user_prompt
    assert 'This output was already tried in the same state and it did not work.' in note
    assert 'Earlier it failed with:' in note and 'gripper is empty' in note     # the original reason is kept
    assert pipeline.termination_reason == 'replan_loop'
    assert [e['replan_reason'] for e in _events(events, 'planning_event')] == [
        'initial', 'plan_check_requery', 'plan_check_requery', 'repeated_output_requery']


def test_a_different_output_after_a_repeat_note_recovers(tmp_path) -> None:
    replan = 'FINAL ACTIONS:\npick(phone)\nplace(phone, table)\npick(mug2)\nplace(mug2, inside_box)'
    pipeline, planner, summary, events = _run(tmp_path, [ORPHAN, ORPHAN, INITIAL, replan])
    assert pipeline.termination_reason == 'plan_completed' and summary['success'] is True


# ------------------------------------------------------------------- memory and the IF rule
def _bare_pipeline(memory: bool) -> LLMOnlyReplanningPipeline:
    flags = PipelineFlags().with_values({'memory.enabled': 'true' if memory else 'false'})
    pipeline = LLMOnlyReplanningPipeline(config=LLMPipelineConfig(flags=flags))
    pipeline._last_object_regions = {'mug1': 'pantry_area', 'raw_meat_2': 'inside_grill'}
    pipeline._current_visible = {'mug1'}
    pipeline.step = 5
    pipeline.memory.update(4, ['mug1', 'raw_meat_2'], dict(pipeline._last_object_regions))
    pipeline.memory.update(5, ['mug1'], {'mug1': 'pantry_area'})
    return pipeline


def test_the_if_rule_evaluates_visible_objects_and_remembered_ones_only_with_memory() -> None:
    assert _bare_pipeline(memory=False)._if_rule_object_regions() == {'mug1': 'pantry_area'}
    assert _bare_pipeline(memory=True)._if_rule_object_regions() == {'mug1': 'pantry_area',
                                                                     'raw_meat_2': 'inside_grill'}


def test_overlap_of_a_remembered_object_never_reads_the_simulator() -> None:
    class NoSimulator:
        placement_areas = {'inside_box': (0, 0, 1, 1)}

        def get_object(self, name):
            raise AssertionError('hidden state must not be read')

    pipeline = _bare_pipeline(memory=True)
    pipeline.env = NoSimulator()
    pipeline._overlap_at_last_sight = {'raw_meat_2': ['inside_box']}
    assert pipeline._overlapping_regions('raw_meat_2', ['inside_box', 'cupboard_shelf']) == ['inside_box']
    assert pipeline._overlapping_regions('mug1', ['inside_box']) == []


# ------------------------------------------------------------------- B4: infrastructure
def _remote(fake, **env):
    old = client_module.requests, client_module.HAS_REQUESTS
    client_module.requests, client_module.HAS_REQUESTS = fake, True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner:8000')
        planner.connect_backoff_s, planner.poll_interval_s = 0.0, 0.0
        for key, value in env.items():
            setattr(planner, key, value)
        return planner, planner.generate_plan(system_prompt='s', user_prompt='u', icl_mode='zero_shot')
    finally:
        client_module.requests, client_module.HAS_REQUESTS = old


PLAN_OK = {'success': True, 'actions': [], 'raw_output': 'FINAL ACTIONS:\nNO_ACTIONS', 'inference_time': 1.0}


def test_a_server_error_is_infrastructure_not_a_planner_failure() -> None:
    fake = _FakeRequests({}, PLAN_OK, job_states=[{'job_id': 'job1', 'status': 'error', 'error': 'CUDA OOM',
                                                   'queue_wait_s': 0.0, 'running_for_s': 1.0}])
    _, result = _remote(fake)
    assert result.failure_event.failure_id == FailureCode.PLANNER_CALL_FAILED
    assert result.failure_event.should_replan is False and result.failure_event.evidence['kind'] == 'server_error'


def test_connection_errors_are_retried_and_model_outputs_are_not() -> None:
    fake = _FakeRequests({}, PLAN_OK, submit_failures=2)
    _, result = _remote(fake)
    assert result.success is True
    assert sum(url.endswith('/plan/submit') for url, _, _ in fake.post_calls) == 3
    fake = _FakeRequests({}, PLAN_OK, submit_failures=10)
    _, result = _remote(fake, connect_retries=3)
    assert result.failure_event.evidence['kind'] == 'connection'
    assert sum(url.endswith('/plan/submit') for url, _, _ in fake.post_calls) == 3


def test_the_timeout_covers_generation_only_and_timing_is_logged() -> None:
    queued = {'job_id': 'job1', 'status': 'queued', 'queue_wait_s': 500.0, 'running_for_s': 0.0}
    fake = _FakeRequests({}, PLAN_OK, job_states=[queued, queued])
    _, result = _remote(fake, request_timeout_s=10.0)
    assert result.success is True
    assert {k: result.timing[k] for k in ('queue_wait_s', 'generation_time_s')} == {'queue_wait_s': 1.5, 'generation_time_s': 2.5}
    running = {'job_id': 'job1', 'status': 'running', 'queue_wait_s': 0.5, 'running_for_s': 11.0}
    fake = _FakeRequests({}, PLAN_OK, job_states=[running])
    _, result = _remote(fake, request_timeout_s=10.0)
    assert result.failure_event.evidence['kind'] == 'generation_timeout'


def test_a_planner_call_failure_ends_the_trial_as_infrastructure(tmp_path) -> None:
    import llm_pipeline.tests.test_if_where_pipeline as base
    from llm_pipeline.tests.test_phase1_pipeline import ScriptedPlanner

    class FailingPlanner(ScriptedPlanner):
        def plan(self, bundle):
            self.bundles.append(bundle)
            event = FailureEvent(failure_id=FailureCode.PLANNER_CALL_FAILED, stage=FailureStage.BEFORE_EXECUTION,
                                 source=FailureSource.VALIDATION, action=None, evidence={'kind': 'connection'},
                                 failure_layer=FailureLayer.LAYER_1, should_replan=False, message='down')
            return PlanResult(False, [], '', 0.0, 'down', event)

    original = base.ScriptedPlanner
    base.ScriptedPlanner = FailingPlanner
    try:
        pipeline, planner, summary, events = _run(tmp_path, [INITIAL])
    finally:
        base.ScriptedPlanner = original
    assert pipeline.termination_reason == 'infrastructure'


def test_the_matrix_reruns_infrastructure_trials_at_most_twice(tmp_path, monkeypatch) -> None:
    from llm_pipeline import run_trial_matrix as matrix

    outcomes = ['infrastructure', 'infrastructure', 'plan_completed']
    attempts = []

    def fake_attempt(planner, variant, seed, directory, extra, timeout_s, attempt):
        attempts.append(attempt)
        reason = outcomes[attempt - 1]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'trial_log.jsonl').write_text(json.dumps(
            {'event': 'trial_end', 'termination_reason': reason, 'success': reason != 'infrastructure'}) + '\n')
        return {'attempt': attempt, 'exit_code': 0, 'termination_reason': reason,
                'infrastructure': reason == 'infrastructure'}

    monkeypatch.setattr(matrix, '_run_attempt', fake_attempt)
    result = matrix.run_one('oracle', 'FINAL.K1', 0, tmp_path, [], 60)
    assert attempts == [1, 2, 3] and result['termination_reason'] == 'plan_completed'
    assert sorted(p.name for p in (tmp_path / 'FINAL.K1').iterdir()) == [
        'seed_00', 'seed_00.infra_attempt1', 'seed_00.infra_attempt2']
    reruns = [json.loads(line) for line in (tmp_path / 'infrastructure_reruns.jsonl').read_text().splitlines()]
    assert [r['attempt'] for r in reruns] == [1, 2]

    outcomes[:] = ['infrastructure'] * 3
    attempts.clear()
    result = matrix.run_one('oracle', 'FINAL.K2', 0, tmp_path, [], 60)
    assert attempts == [1, 2, 3] and result['infrastructure'] is True


# ------------------------------------------------------------------- B5: server
def test_the_job_queue_is_serial_and_separates_queue_wait_from_generation() -> None:
    from llm_pipeline.server import PlanJobQueue

    jobs = PlanJobQueue()

    def slow(payload):
        time.sleep(0.2)
        if payload == 'boom':
            raise RuntimeError('model failed')
        return {'raw_output': payload}

    first, second, third = jobs.submit(slow, 'a'), jobs.submit(slow, 'b'), jobs.submit(slow, 'boom')
    assert jobs.status(second)['status'] == 'queued'
    done = [jobs.wait(job) for job in (first, second, third)]
    assert [d['status'] for d in done] == ['done', 'done', 'error']
    assert done[1]['result'] == {'raw_output': 'b'} and 'model failed' in done[2]['error']
    assert done[1]['queue_wait_s'] >= 0.15 and 0.15 <= done[1]['generation_time_s'] < 1.0


def test_the_server_reports_its_settings(monkeypatch) -> None:
    from types import SimpleNamespace

    from llm_pipeline.server import LLMServer

    server = LLMServer.__new__(LLMServer)
    server.model_spec = SimpleNamespace(path='Qwen/Qwen3-VL-8B-Thinking', alias='qwen3-vl', model_type='vlm')
    server.quantization, server.format_repair, server.loaded = 'none', False, True
    server.planner = SimpleNamespace(model=SimpleNamespace(config=SimpleNamespace(_commit_hash='deadbeef')))
    monkeypatch.delenv('QWEN_THINKING_MODE', raising=False)
    settings = server.settings()
    assert settings['thinking_mode'] == 'on' and settings['format_repair'] is False
    assert settings['model_revision'] == 'deadbeef' and settings['model_name'] == 'Qwen/Qwen3-VL-8B-Thinking'
    assert 'commit' in settings['server_git_commit'] and settings['serving'] == 'serial'
    monkeypatch.setenv('QWEN_THINKING_MODE', 'off')
    assert server.settings()['thinking_mode'] == 'off'


# ------------------------------------------------------------------- B7: regions
def _scene_boxes(scene: str):
    import numpy as np

    data = json.loads((ROOT / 'mujoco_port' / 'extracted' / scene / 'scene.json').read_text())
    objects = data['objects'].values() if isinstance(data['objects'], dict) else data['objects']

    def aabb(o):
        x, y, z, w = o['world_quat']
        rot = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        lo, hi = np.array(o['bbox'][:3]), np.array(o['bbox'][3:])
        corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1]) for c in (lo[2], hi[2])])
        world = corners @ rot.T + np.array(o['world_pos'])
        return world.min(0), world.max(0)

    names = {'groceries_boundary': 'pantry_area', 'placement_boundary': 'table_staging_area',
             'box_boundary': 'inside_box', 'cupboard_boundary': 'cupboard_shelf'}
    by_name = {o['name']: o for o in objects}
    return {region: aabb(by_name[name]) for name, region in names.items() if name in by_name}, by_name


def test_staging_placements_resolve_to_the_staging_area_and_pantry_objects_stay_in_the_pantry() -> None:
    import numpy as np

    from llm_pipeline.region_geometry import resolve_region

    boxes, objects = _scene_boxes('final_K0')
    lo, hi = boxes['table_staging_area']
    z = float(lo[2]) + 0.04
    # The executor samples the staging area 5 cm inside its edges (rlbench_kitchen_env.sample_stable_pose).
    for x in np.linspace(lo[0] + 0.05, hi[0] - 0.05, 7):
        for y in np.linspace(lo[1] + 0.05, hi[1] - 0.05, 7):
            assert resolve_region((x, y, z), boxes)[0] == 'table_staging_area', (x, y)
    # The table objects of the base layout, at their pose and at the +-3 cm jitter extremes.
    for name in ('mug1', 'spam', 'sugar'):
        x, y, oz = objects[name]['world_pos']
        for dx in (-0.03, 0.0, 0.03):
            for dy in (-0.03, 0.0, 0.03):
                assert resolve_region((x + dx, y + dy, oz), boxes)[0] == 'pantry_area', (name, dx, dy)


def test_every_successful_place_is_observed_in_its_target_region_in_all_14_variants() -> None:
    """B7: over the Phase 7b oracle reruns (all 14 final variants), after every successful
    place(o, r) the next observation reports o in r."""
    from evaluation.check_place_regions import check_dirs
    from evaluation.final_variants import FINAL_VARIANT_ORDER

    root = ROOT / 'results' / 'phase7b'
    if not root.exists():
        pytest.skip('results/phase7b has not been produced yet')
    results = check_dirs([root])
    variants = {r['variant'] for r in results}
    assert {f'FINAL.{name}' for name in FINAL_VARIANT_ORDER} <= variants
    mismatches = [m | {'trial': r['trial']} for r in results for m in r['mismatches']]
    assert sum(int(r['checked']) for r in results) > 0
    assert mismatches == []
