"""Phase 1 behavior of the pipeline: JSONL trial log, step counting, action ids,
completed-actions fix, partial observability and termination.mode."""

import json

import pytest

from llm_pipeline import client as client_module
from llm_pipeline import pipeline as pipeline_module
from llm_pipeline.client import RemoteTextLLMPlanner
from llm_pipeline.executable_symbols import RuntimeSymbolRegistry
from llm_pipeline.executor import PrimitiveExecutionOutcome
from llm_pipeline.failures import FailureCode
from llm_pipeline.flags import PipelineFlags
from llm_pipeline.pipeline import LLMOnlyReplanningPipeline, LLMPipelineConfig
from llm_pipeline.pipeline_types import (
    FailureEvent,
    FailureSource,
    FailureStage,
    GoalCheckResult,
    PlanResult,
    SegmentationObjectEvidence,
    SegmentationSnapshot,
)
from llm_pipeline.strict_parser import StrictActionParser, StrictParseError
from llm_pipeline.tests.test_pipeline import FakeEnv
from llm_pipeline.tests.test_remote_client import _FakeRequests
from llm_pipeline.trial_log import TrialLogger, read_trial_log, validate_trial_log

UNSEEN = 'spam'  # in the scene's symbol registry, never visible to the robot
REVEALED = 'can_of_beans'  # becomes visible when the box opens
REGIONS = ['table', 'table_staging_area', 'cupboard_shelf', 'inside_box']


def _snapshot(visible, regions, newly=()):
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=list(visible),
        newly_visible_objects=list(newly),
        object_evidence={name: SegmentationObjectEvidence(name=name, visible=True) for name in visible},
        gripper_evidence={},
        supported_regions=list(REGIONS),
        visible_regions=['inside_box'],
        object_region_map=dict(regions),
        object_region_descriptions={},
    )


class SceneAdapter:
    """Segmentation adapter whose snapshot changes when the box opens."""

    def __init__(self):
        self.box_open = False
        self.regions = {'mug2': 'table'}
        self.known_visible = set()

    def visible(self):
        return ['mug2', 'box_lid'] + ([REVEALED] if self.box_open else [])

    def snapshot(self, newly=()):
        regions = dict(self.regions)
        if self.box_open:
            regions.setdefault(REVEALED, 'inside_box')
        snap = _snapshot(self.visible(), regions, newly)
        self.known_visible.update(snap.visible_objects)
        return snap

    def capture_snapshot(self, event=''):
        del event
        return self.snapshot()

    def refresh_visibility(self, event=''):
        return {'visible_objects': self.visible(), 'newly_visible_objects': [], 'visible_regions': []}

    def is_lid_open(self, snapshot, lid_name='box_lid'):
        del snapshot, lid_name
        return self.box_open

    def reset_tracking(self):
        self.known_visible = set()

    def set_env(self, env):
        self.env = env

    def set_symbol_registry(self, registry):
        self.symbol_registry = registry


class Checker:
    def __init__(self, adapter):
        self.adapter = adapter
        self.env = None
        self.prechecks = []

    def capture_snapshot(self, event=''):
        return self.adapter.capture_snapshot(event)

    def precheck(self, action, held_object, snapshot, last_action_name=None):
        del held_object, snapshot, last_action_name
        self.prechecks.append(str(action))
        return None


class HookedExecutor:
    """Executes bundles instantly and drives the executor trial-log hooks like DirectPrimitiveExecutor."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.completed_primitive_actions = []
        self.remaining_actions = []
        self.held_object = None
        self.event_sink = None
        self.bundle_end_callback = None

    def set_env(self, env):
        self.env = env

    def set_event_sink(self, sink):
        self.event_sink = sink

    def set_bundle_end_callback(self, callback):
        self.bundle_end_callback = callback

    def reset_episode(self):
        self.completed_primitive_actions = []
        self.remaining_actions = []
        self.held_object = None

    def execute_actions(self, actions, failure_checker, pre_action_checks_enabled=True, post_action_checks_enabled=True):
        del pre_action_checks_enabled, post_action_checks_enabled
        index = 0
        bundle_number = len(self.completed_primitive_actions)
        while index < len(actions):
            size = 2 if actions[index].action_name == 'pick' else 1
            bundle = actions[index:index + size]
            bundle_number += 1
            bundle_id = f'b{bundle_number}'
            for action in bundle:
                failure_checker.precheck(action, self.held_object, self.adapter.snapshot())
                self.event_sink('action_start', action=str(action), bundle_id=bundle_id, adapter='fake')
                if action.action_name == 'place':
                    self.adapter.regions[action.args[0]] = action.args[1]
                if action.action_name == 'open':
                    self.adapter.box_open = True
                self.completed_primitive_actions.append(str(action))
                self.event_sink('action_end', action=str(action), bundle_id=bundle_id, adapter='fake',
                                local_retries_used=None, outcome='success', failure_code=None, duration_s=0.0)
            index += size
            failure = None
            if bundle[0].action_name == 'open':
                failure = FailureEvent(
                    failure_id=FailureCode.NEW_OBJECT_DISCOVERED,
                    stage=FailureStage.AFTER_EXECUTION,
                    source=FailureSource.SEGMENTATION,
                    action=str(bundle[0]),
                    evidence={'newly_visible_objects': [REVEALED]},
                    message=f'Newly visible objects require replanning: {REVEALED}',
                )
            self.bundle_end_callback(bundle_id=bundle_id, actions=[str(a) for a in bundle], success=failure is None,
                                     failure_event=failure, snapshot=self.adapter.snapshot())
            if failure is not None and index < len(actions):
                self.remaining_actions = [str(a) for a in actions[index:]]
                return PrimitiveExecutionOutcome(False, list(self.completed_primitive_actions),
                                                 list(self.remaining_actions), None, failure, failure.message)
        self.remaining_actions = []
        return PrimitiveExecutionOutcome(True, list(self.completed_primitive_actions), [], None, None, None)


class ScriptedPlanner:
    """Returns scripted outputs; parse failures are replannable like the real planners."""

    def __init__(self, outputs, goal_check_outputs=()):
        self.outputs = list(outputs)
        self.goal_check_outputs = list(goal_check_outputs)
        self.model_alias = self.model_name = 'scripted'
        self.loaded = True
        self.parser = StrictActionParser()
        self.bundles = []
        self.goal_check_prompts = []

    def load_model(self):
        return True

    def plan(self, bundle):
        self.bundles.append(bundle)
        raw = self.outputs.pop(0)
        try:
            actions = self.parser.parse(raw, held_object=bundle.metadata.get('held_object'))
        except StrictParseError as exc:
            return PlanResult(False, [], raw, 0.5, str(exc), FailureEvent(
                failure_id=exc.failure_id, stage=FailureStage.BEFORE_EXECUTION, source=FailureSource.VALIDATION,
                action=None, evidence={'fact': exc.fact, 'raw_output': raw}, should_replan=True, message=str(exc),
            ))
        return PlanResult(True, actions, raw, 0.5)

    def check_goal_completion(self, system_prompt, user_prompt, icl_mode, max_new_tokens=64, temperature=0.0,
                              held_object=None):
        del icl_mode, max_new_tokens, temperature, held_object
        self.goal_check_prompts.append(system_prompt + '\n' + user_prompt)
        raw = self.goal_check_outputs.pop(0) if self.goal_check_outputs else 'GOAL_COMPLETE'
        return GoalCheckResult(True, raw.startswith('GOAL_COMPLETE'), raw, 0.1)


PLAN_1 = 'FINAL ACTIONS:\npick(mug2)\nplace(mug2, table_staging_area)\nopen(box_lid)\npick(mug2)\nplace(mug2, inside_box)'
PLAN_UNSEEN = f'FINAL ACTIONS:\npick({UNSEEN})\nplace({UNSEEN}, cupboard_shelf)'
PLAN_3 = (f'FINAL ACTIONS:\npick({REVEALED})\nplace({REVEALED}, cupboard_shelf)\n'
          'pick(mug2)\nplace(mug2, inside_box)')


def _pipeline(outputs, flags=None, goal_check=False, goal_check_outputs=()):
    adapter = SceneAdapter()
    planner = ScriptedPlanner(outputs, goal_check_outputs)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(model_alias='scripted', icl_mode='zero_shot', headless=True,
                                 live_segmentation_view=False, enable_goal_check=goal_check,
                                 variant_id='K1', flags=flags or PipelineFlags()),
        planner=planner,
        segmentation_adapter=adapter,
        failure_checker=Checker(adapter),
        executor=HookedExecutor(adapter),
    )
    assert pipeline.initialize(env=FakeEnv())
    assert UNSEEN in pipeline.symbol_registry.objects
    return pipeline, planner, adapter


def _run_logged(tmp_path, outputs, **kwargs):
    pipeline, planner, adapter = _pipeline(outputs, **kwargs)
    logger = TrialLogger(tmp_path / 'trial_log.jsonl', trial_id='K1_test')
    pipeline.set_trial_logger(logger)
    logger.emit('trial_start', scene='kitchen', variant='K1', condition={}, seed=1,
                flags=pipeline.config.flags.to_dict(), git_commit={'commit': None})
    summary = pipeline.run('move ALL THE MUGS inside the box')
    logger.emit('trial_end', success=summary['success'], goal_relations_satisfied=0, goal_relations_total=0,
                procedure_checks_satisfied=0, procedure_checks_total=0, planner_calls=summary['planner_invocations'],
                planner_time_s=summary['total_planner_time_s'], trial_time_s=0.0,
                termination_reason=pipeline.termination_reason)
    return pipeline, planner, summary, read_trial_log(tmp_path / 'trial_log.jsonl')


def test_trial_log_is_complete_and_valid(tmp_path) -> None:
    pipeline, planner, summary, events = _run_logged(tmp_path, [PLAN_1, PLAN_UNSEEN, PLAN_3])

    assert validate_trial_log(events) == []
    kinds = [event['event'] for event in events]
    for required in ('trial_start', 'observation', 'planning_event', 'plan_check', 'pre_action_check',
                     'action_start', 'action_end', 'trial_end'):
        assert required in kinds
    assert summary['success'] is True
    assert pipeline.termination_reason == 'plan_completed'

    planning = [event for event in events if event['event'] == 'planning_event']
    assert [event['kind'] for event in planning] == ['initial', 'replan', 'replan']
    assert planning[1]['trigger_objects'] == [REVEALED]
    assert planning[2]['plan_check_requery'] is True
    assert all((tmp_path / event['prompt_path']).exists() for event in planning)
    assert [event['result'] for event in events if event['event'] == 'plan_check'] == ['pass', 'fail', 'pass']
    rejected = [event for event in events if event['event'] == 'plan_check' and event['result'] == 'fail'][0]
    assert rejected['failure_codes'] == ['unobserved_object']


def test_steps_count_observations_and_plan_check_requeries_share_a_step(tmp_path) -> None:
    _, _, _, events = _run_logged(tmp_path, [PLAN_1, PLAN_UNSEEN, PLAN_3])
    observations = [event for event in events if event['event'] == 'observation']
    # initial planning, 2 bundles (the open interrupts), replan planning, 2 bundles
    assert [event['step'] for event in observations] == [1, 2, 3, 4, 5, 6]
    planning = [event for event in events if event['event'] == 'planning_event']
    assert [event['step'] for event in planning] == [1, 4, 4]
    revealed = [event for event in observations if REVEALED in event['newly_visible_objects']]
    assert len(revealed) == 1 and revealed[0]['step'] == 3
    assert revealed[0]['object_regions'][REVEALED] == 'inside_box'
    assert revealed[0]['articulation_states'] == {'box_lid': 'open'}


def test_replan_prompt_has_completed_and_remaining_plan_with_ids(tmp_path) -> None:
    _, planner, _, _ = _run_logged(tmp_path, [PLAN_1, PLAN_UNSEEN, PLAN_3])
    replan_prompt = planner.bundles[1].user_prompt
    assert '## Completed actions\n- a1: pick(mug2)\n- a2: place(mug2, table_staging_area)\n- a3: open(box_lid)' in replan_prompt
    assert '## Remaining plan (not executed yet)\n- a4: pick(mug2)\n- a5: place(mug2, inside_box)' in replan_prompt
    assert f'After open(box_lid), these objects became visible and had not been seen earlier in this trial: {REVEALED} (inside_box).' in replan_prompt
    requery = planner.bundles[2].user_prompt
    # The planner sees the same code as for a name that does not exist (unobserved_object is logged only).
    assert 'rejected before execution (failure code unknown_action_token)' in requery
    assert 'unobserved' not in requery


def test_completed_actions_are_not_duplicated_in_later_replans() -> None:
    legacy = PipelineFlags(prompt_version='legacy')
    pipeline, planner, _ = _pipeline([PLAN_1, PLAN_3], flags=legacy)
    pipeline.run('move ALL THE MUGS inside the box')
    assert list(planner.bundles[1].previous_actions) == [
        'pick(mug2)', 'place(mug2, table_staging_area)', 'open(box_lid)',
    ]
    completed_section = planner.bundles[1].user_prompt.split('### Completed Actions')[1].split('###')[0]
    assert completed_section.count('pick(mug2)') == 1


def _prompts_for(prompt_version, unseen_in_scene):
    flags = PipelineFlags(prompt_version=prompt_version)
    pipeline, planner, _ = _pipeline([PLAN_1, PLAN_UNSEEN, PLAN_3], flags=flags, goal_check=True)
    if not unseen_in_scene:
        registry = pipeline.symbol_registry
        objects = tuple(name for name in registry.objects if name != UNSEEN)
        pipeline.symbol_registry = RuntimeSymbolRegistry(registry.actions, objects, registry.regions)
        planner.parser = StrictActionParser(valid_actions=registry.actions, valid_objects=objects,
                                            valid_regions=registry.regions)
        if hasattr(pipeline.context_builder, 'set_symbol_registry'):
            pipeline.context_builder.set_symbol_registry(pipeline.symbol_registry)
    pipeline.run('move ALL THE MUGS inside the box')
    prompts = [(bundle.system_prompt, bundle.user_prompt) for bundle in planner.bundles]
    return prompts + [('goal_check', text) for text in planner.goal_check_prompts], planner


@pytest.mark.parametrize('prompt_version', ['v2', 'legacy'])
def test_unseen_object_cannot_appear_in_any_prompt(prompt_version) -> None:
    """Prompts are identical whether or not the never-observed object exists in the scene."""
    hidden, hidden_planner = _prompts_for(prompt_version, unseen_in_scene=True)
    absent, absent_planner = _prompts_for(prompt_version, unseen_in_scene=False)
    assert len(hidden) == 4  # initial plan, replan, plan-check re-query, goal check
    assert hidden == absent
    for system_prompt, user_prompt in hidden[:1] + hidden[-1:]:
        assert UNSEEN not in system_prompt + user_prompt  # never mentioned unless the planner wrote it
    assert UNSEEN not in hidden_planner.parser.planner_visible_objects()
    assert hidden_planner.parser.planner_visible_objects() == absent_planner.parser.planner_visible_objects()


def test_plan_check_rejects_actions_on_unobserved_objects() -> None:
    parser = StrictActionParser(valid_objects=['mug2', UNSEEN, 'box_lid'], valid_regions=REGIONS)
    parser.set_observed_objects({'mug2', 'box_lid'})
    with pytest.raises(StrictParseError) as error:
        parser.parse(f'pick({UNSEEN})\nplace({UNSEEN}, table)')
    assert error.value.failure_id == FailureCode.UNOBSERVED_OBJECT
    assert error.value.fact == f"Line 1 (pick({UNSEEN})) picks '{UNSEEN}', which is not a pickable object in the state."
    with pytest.raises(StrictParseError) as unknown:
        parser.parse('pick(teapot)\nplace(teapot, table)')
    assert (unknown.value.message, unknown.value.fact) == (
        error.value.message.replace(UNSEEN, 'teapot'), error.value.fact.replace(UNSEEN, 'teapot'),
    )
    assert parser.parse('pick(mug2)\nplace(mug2, table)')[0].args == ('mug2',)
    parser.set_observed_objects(None)
    assert len(parser.parse(f'pick({UNSEEN})\nplace({UNSEEN}, table)')) == 2


def test_remote_request_never_contains_unobserved_objects() -> None:
    fake = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen', 'model_name': 'qwen',
                        'model_type': 'llm', 'gpu_available': True},
        plan_payload={'success': False, 'actions': [], 'raw_output': f'FINAL ACTIONS:\npick({UNSEEN})\n'
                      f'place({UNSEEN}, table)', 'inference_time': 0.1,
                      'failure_event': {'failure_id': 'unknown_action_token', 'failure_layer': 'layer_1',
                                        'stage': 'before_execution', 'source': 'validation', 'action': None,
                                        'evidence': {}, 'should_replan': True, 'message': 'unknown'}},
    )
    old_requests, old_has = client_module.requests, client_module.HAS_REQUESTS
    client_module.requests, client_module.HAS_REQUESTS = fake, True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner:8000')
        planner.parser = StrictActionParser(valid_objects=['mug2', UNSEEN, 'box_lid'], valid_regions=REGIONS)
        planner.parser.set_observed_objects({'mug2', 'box_lid'})
        result = planner.generate_plan(system_prompt='s', user_prompt='u', icl_mode='zero_shot')
    finally:
        client_module.requests, client_module.HAS_REQUESTS = old_requests, old_has
    payload = fake.post_calls[-1][1]
    assert UNSEEN not in json.dumps(payload)
    assert result.failure_event.failure_id == FailureCode.UNOBSERVED_OBJECT


def test_agent_termination_never_consults_the_evaluator(monkeypatch) -> None:
    def _forbidden(*args, **kwargs):
        raise AssertionError('the evaluator must not run inside the loop in termination.mode=agent')

    monkeypatch.setattr(pipeline_module, 'validate_variant_success', _forbidden)
    pipeline, planner, _ = _pipeline([PLAN_1, PLAN_3], goal_check=True, goal_check_outputs=['GOAL_COMPLETE'])
    summary = pipeline.run('move ALL THE MUGS inside the box')
    assert summary['success'] is True
    assert pipeline.termination_reason == 'goal_check_satisfied'


def test_evaluator_termination_reproduces_the_previous_override(monkeypatch) -> None:
    calls = []

    def _validate(variant_id, object_region_map, completed_actions):
        calls.append(variant_id)
        return {'success': False, 'missing': ['mug3 is in unknown, expected inside_box']}

    monkeypatch.setattr(pipeline_module, 'validate_variant_success', _validate)
    flags = PipelineFlags(termination_mode='evaluator', prompt_version='legacy')
    pipeline, planner, _ = _pipeline([PLAN_1, PLAN_3, 'NO_ACTIONS'], flags=flags, goal_check=True,
                                     goal_check_outputs=['GOAL_COMPLETE', 'GOAL_COMPLETE'])
    pipeline.config.max_replans = 2
    pipeline.run('move ALL THE MUGS inside the box')
    assert calls, 'evaluator mode keeps the evaluator override'
