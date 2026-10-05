"""Phases 4-5 through the pipeline: IF-rule trigger, corrective blocks, re-query, insertion log."""

from llm_pipeline.executor import PrimitiveExecutionOutcome
from llm_pipeline.failures import FailureCode
from llm_pipeline.flags import PipelineFlags
from llm_pipeline.pipeline import LLMOnlyReplanningPipeline, LLMPipelineConfig
from llm_pipeline.tests.test_phase1_pipeline import Checker, HookedExecutor, ScriptedPlanner, SceneAdapter
from llm_pipeline.tests.test_pipeline import FakeEnv
from llm_pipeline.trial_log import TrialLogger, read_trial_log


class PhoneBoxAdapter(SceneAdapter):
    """The box opens to reveal a phone lying where the mugs go."""

    def visible(self):
        return ['mug2', 'box_lid'] + (['phone'] if self.box_open else [])

    def snapshot(self, newly=()):
        snap = super().snapshot(newly)
        snap.object_region_map.pop('can_of_beans', None)
        if self.box_open:
            snap.object_region_map.setdefault('phone', self.regions.get('phone', 'inside_box'))
        return snap


class TriggerExecutor(HookedExecutor):
    """HookedExecutor without discovery failures; calls the IF-rule hook after every bundle."""

    trigger_check = None

    def set_trigger_check(self, callback):
        self.trigger_check = callback

    def execute_actions(self, actions, failure_checker, pre_action_checks_enabled=True, post_action_checks_enabled=True):
        index = 0
        while index < len(actions):
            size = 2 if actions[index].action_name == 'pick' else 1
            bundle = actions[index:index + size]
            for action in bundle:
                self.event_sink('action_start', action=str(action), bundle_id=f'b{index}', adapter='fake')
                if action.action_name == 'place':
                    self.adapter.regions[action.args[0]] = action.args[1]
                if action.action_name == 'open':
                    self.adapter.box_open = True
                self.completed_primitive_actions.append(str(action))
                self.event_sink('action_end', action=str(action), bundle_id=f'b{index}', adapter='fake',
                                local_retries_used=None, outcome='success', failure_code=None, duration_s=0.0)
            index += size
            self.bundle_end_callback(bundle_id=f'b{index}', actions=[str(a) for a in bundle], success=True,
                                     failure_event=None, snapshot=self.adapter.snapshot())
            remaining = [str(a) for a in actions[index:]]
            event = self.trigger_check(remaining) if self.trigger_check else None
            if event is not None:
                self.remaining_actions = remaining
                return PrimitiveExecutionOutcome(False, list(self.completed_primitive_actions), remaining, None,
                                                 event, event.message)
        self.remaining_actions = []
        return PrimitiveExecutionOutcome(True, list(self.completed_primitive_actions), [], None, None, None)


INITIAL = 'FINAL ACTIONS:\npick(mug2)\nplace(mug2, table_staging_area)\nopen(box_lid)\npick(mug2)\nplace(mug2, inside_box)'


def _blocks(urgency, insert):
    return ('The phone is where the mug goes.\nFINAL BLOCKS:\nBLOCK\nobjects: phone\n'
            f'urgency: {urgency}\ninsert: {insert}\nreason: it lies in the placement area\n'
            'actions:\npick(phone)\nplace(phone, table)\nEND BLOCK')


def _run(tmp_path, outputs, **flags):
    adapter = PhoneBoxAdapter()
    planner = ScriptedPlanner(outputs)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(model_alias='scripted', headless=True, live_segmentation_view=False,
                                 enable_goal_check=False, variant_id='K1', task_family='kitchen',
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
    # System geometry stand-in: the phone overlaps the box placement area while it is in the box.
    pipeline._overlapping_regions = lambda obj, regions: (
        [r for r in regions if r == 'inside_box'] if obj == 'phone' and adapter.regions.get('phone', 'inside_box') == 'inside_box' else [])
    pipeline.set_trial_logger(TrialLogger(tmp_path / 'log.jsonl', trial_id='K1_if'))
    summary = pipeline.run('move ALL THE MUGS inside the box')
    return pipeline, planner, summary, read_trial_log(tmp_path / 'log.jsonl')


def test_if_rule_triggers_once_on_the_overlapping_phone_and_full_replan_still_works(tmp_path) -> None:
    replan = 'FINAL ACTIONS:\npick(phone)\nplace(phone, table)\npick(mug2)\nplace(mug2, inside_box)'
    pipeline, planner, summary, events = _run(tmp_path, [INITIAL, replan], **{'replan.trigger_mode': 'if_rule'})
    planning = [e for e in events if e['event'] == 'planning_event']
    assert [e['trigger_code'] for e in planning] == [None, 'if_rule_trigger']
    assert planning[1]['trigger_objects'] == ['phone']
    assert 'not relevant to the goal; lies where the remaining plan places objects into inside_box' in \
        planner.bundles[1].user_prompt
    checks = [e for e in events if e['event'] == 'if_check']
    assert len(checks) >= 3 and sum(bool(e['trigger_objects']) for e in checks) == 1
    assert summary['completed_actions'][-2:] == ['pick(mug2)', 'place(mug2, inside_box)']


def test_discovery_mode_triggers_through_the_same_hook_as_the_if_rule(tmp_path) -> None:
    # B2: discovery triggers come from the same post-bundle check as the IF rule; only the
    # choice of trigger objects differs (every newly visible object).
    replan = 'FINAL ACTIONS:\npick(phone)\nplace(phone, table)\npick(mug2)\nplace(mug2, inside_box)'
    pipeline, planner, summary, events = _run(tmp_path, [INITIAL, replan])
    checks = [e for e in events if e['event'] == 'if_check']
    assert checks and all(e['trigger_mode'] == 'discovery' for e in checks)
    assert sum(bool(e['trigger_objects']) for e in checks) == 1
    planning = [e for e in events if e['event'] == 'planning_event']
    assert [e['trigger_code'] for e in planning] == [None, 'new_object_discovered']
    assert planning[1]['trigger_objects'] == ['phone'] and planning[1]['output_format'] == 'full'
    assert planning[1]['replan_reason'] == 'trigger:discovery'
    # The full-replan prompt keeps the discovery wording.
    assert 'these objects became visible and had not been seen earlier in this trial: phone' in \
        planner.bundles[1].user_prompt
    assert summary['completed_actions'][-2:] == ['pick(mug2)', 'place(mug2, inside_box)']


def test_corrective_block_is_merged_into_the_remaining_plan_with_its_ids(tmp_path) -> None:
    pipeline, planner, summary, events = _run(
        tmp_path, [INITIAL, _blocks('urgent', 'front')],
        **{'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective'})
    assert 'FINAL BLOCKS:' in planner.bundles[1].system_prompt
    assert '- a4: pick(mug2)' in planner.bundles[1].user_prompt
    insertion = [e for e in events if e['event'] == 'insertion']
    assert len(insertion) == 1 and insertion[0]['first_proposal'] is True
    assert insertion[0]['urgency'] == {'phone': 'urgent'}
    assert insertion[0]['merged_plan'] == ['a6: pick(phone)', 'a7: place(phone, table)', 'a4: pick(mug2)',
                                           'a5: place(mug2, inside_box)']
    assert summary['completed_actions'][-4:] == ['pick(phone)', 'place(phone, table)', 'pick(mug2)',
                                                 'place(mug2, inside_box)']
    assert summary['success'] is True


def test_deferring_the_phone_past_the_box_placement_is_requeried(tmp_path) -> None:
    pipeline, planner, summary, events = _run(
        tmp_path, [INITIAL, _blocks('deferred', 'end'), _blocks('urgent', 'front')],
        **{'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective'})
    insertion = [e for e in events if e['event'] == 'insertion']
    assert [e['accepted'] for e in insertion] == [False, True]
    assert insertion[0]['rejection_code'] == FailureCode.INSERTION_TOO_LATE
    assert insertion[1]['first_proposal'] is False
    assert 'Your previous blocks were rejected (failure code insertion_too_late)' in planner.bundles[2].user_prompt
    planning = [e for e in events if e['event'] == 'planning_event']
    assert planning[2]['plan_check_requery'] is True and planning[2]['step'] == planning[1]['step']
    assert summary['success'] is True


def test_always_end_overrides_the_urgent_block_and_is_rejected(tmp_path) -> None:
    pipeline, planner, summary, events = _run(
        tmp_path, [INITIAL] + [_blocks('urgent', 'front')] * 5,
        **{'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective', 'replan.insertion_mode': 'always_end'})
    insertion = [e for e in events if e['event'] == 'insertion']
    assert insertion and not any(e['accepted'] for e in insertion)
    assert summary['success'] is False


def test_always_front_overrides_a_deferred_block(tmp_path) -> None:
    pipeline, planner, summary, events = _run(
        tmp_path, [INITIAL, _blocks('deferred', 'end')],
        **{'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective', 'replan.insertion_mode': 'always_front'})
    insertion = [e for e in events if e['event'] == 'insertion']
    assert insertion[0]['accepted'] and insertion[0]['urgency'] == {'phone': 'deferred'}
    assert insertion[0]['merged_plan'][0].endswith('pick(phone)')
    assert summary['success'] is True


def test_corrective_prompt_is_neutral_by_default_and_hinted_behind_the_flag(tmp_path) -> None:
    from llm_pipeline.corrective import URGENCY_HINTED, URGENCY_NEUTRAL

    flags = {'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective'}
    _, planner, _, _ = _run(tmp_path / 'neutral', [INITIAL, _blocks('urgent', 'front')], **flags)
    neutral = planner.bundles[1].user_prompt
    assert URGENCY_NEUTRAL in neutral
    for giveaway in ('where other objects will be placed', 'cooked again', 'for example'):
        assert giveaway not in neutral
    _, planner, _, _ = _run(tmp_path / 'hinted', [INITIAL, _blocks('urgent', 'front')],
                            **flags, **{'prompt.corrective_hints': 'on'})
    assert URGENCY_HINTED in planner.bundles[1].user_prompt
