"""Phase 6: parallel planning and execution (parallel.enabled = true)."""

import time

from llm_pipeline.failures import FailureCode
from llm_pipeline.parallel import affected_set, independent_bundles, split_bundles
from llm_pipeline.strict_parser import StrictParseError
from llm_pipeline.tests.test_if_where_pipeline import PhoneBoxAdapter, _blocks, _run
from llm_pipeline.tests.test_phase1_pipeline import ScriptedPlanner

INITIAL = ('FINAL ACTIONS:\npick(mug2)\nplace(mug2, table_staging_area)\nopen(box_lid)\n'
           'pick(spam)\nplace(spam, cupboard_shelf)\npick(sugar)\nplace(sugar, cupboard_shelf)\n'
           'pick(mug2)\nplace(mug2, inside_box)')
CORRECTIVE = {'replan.trigger_mode': 'if_rule', 'replan.output_mode': 'corrective'}
PARALLEL = dict(CORRECTIVE, **{'parallel.enabled': 'true'})


# ---------------------------------------------------------------- scheduling logic
def test_affected_set_and_independent_bundles_for_the_kitchen_phone() -> None:
    remaining = [('a4', 'pick(spam)'), ('a5', 'place(spam, cupboard_shelf)'), ('a6', 'pick(mug1)'),
                 ('a7', 'place(mug1, inside_box)'), ('a8', 'pick(sugar)'), ('a9', 'place(sugar, cupboard_shelf)'),
                 ('a10', 'pick(mug2)'), ('a11', 'place(mug2, inside_box)')]
    regions = {'phone': 'inside_box', 'spam': 'pantry_area', 'mug1': 'pantry_area', 'sugar': 'pantry_area',
               'mug2': 'table_staging_area'}
    affected = affected_set('kitchen', ['phone'], regions, overlapping={'phone': ['inside_box']})
    assert affected == {'objects': ['box_lid', 'phone'], 'regions': ['inside_box', 'table_staging_area'],
                        'parking_regions': ['table_staging_area']}
    independent = independent_bundles(split_bundles(remaining, regions), affected)
    # mug1 places into the overlapped box and waits; sugar only shares mug1's pick source
    # (pantry_area), which is not a dependency, so it runs during the replan (Phase 7b).
    assert [b.ids for b in independent] == [['a4', 'a5'], ['a8', 'a9']]


def test_grill_plate_move_is_independent_of_cooked_meat_in_the_grill() -> None:
    remaining = [('a2', 'pick(plate)'), ('a3', 'place(plate, serving_area)'), ('a4', 'pick(raw_meat_1)'),
                 ('a5', 'place(raw_meat_1, inside_grill)'), ('a6', 'close(grill_lid)')]
    regions = {'plate': 'dish_rack', 'raw_meat_1': 'prep_area', 'cooked_meat_1': 'inside_grill'}
    affected = affected_set('grill', ['cooked_meat_1'], regions)
    assert 'grill_lid' in affected['objects'] and 'plate_top' in affected['regions']
    assert [b.ids for b in independent_bundles(split_bundles(remaining, regions), affected)] == [['a2', 'a3']]


# ---------------------------------------------------------------- through the pipeline
class DelayedPlanner(ScriptedPlanner):
    def __init__(self, outputs, delay_s=0.3):
        super().__init__(outputs)
        self.delay_s = delay_s
        self.calls_started = []

    def plan(self, bundle):
        self.calls_started.append(time.monotonic())
        if bundle.metadata.get('output_format') == 'corrective_blocks':
            time.sleep(self.delay_s)
        return super().plan(bundle)


class PantryAdapter(PhoneBoxAdapter):
    """Adds spam and sugar on the table (pantry area) to the phone-in-the-box scene."""

    def __init__(self):
        super().__init__()
        self.regions.update({'spam': 'pantry_area', 'sugar': 'pantry_area'})

    def visible(self):
        return super().visible() + ['spam', 'sugar']


def _parallel_run(tmp_path, outputs, flags=PARALLEL, delay_s=0.3, patch=None):
    import llm_pipeline.tests.test_if_where_pipeline as base

    originals = base.ScriptedPlanner, base.PhoneBoxAdapter
    base.ScriptedPlanner = lambda outs: DelayedPlanner(outs, delay_s)
    base.PhoneBoxAdapter = PantryAdapter
    try:
        return _run(tmp_path, outputs, **flags) if patch is None else patch(tmp_path, outputs, flags)
    finally:
        base.ScriptedPlanner, base.PhoneBoxAdapter = originals


def test_independent_actions_run_during_the_replan_and_affected_ones_do_not(tmp_path) -> None:
    pipeline, planner, summary, events = _parallel_run(tmp_path, [INITIAL, _blocks('urgent', 'front')])
    parallel = [e for e in events if e['event'] == 'parallel']
    assert len(parallel) == 1
    assert parallel[0]['independent_actions_executed'] == ['pick(spam)', 'place(spam, cupboard_shelf)',
                                                           'pick(sugar)', 'place(sugar, cupboard_shelf)']
    assert parallel[0]['merge_result'] == 'accepted'
    assert parallel[0]['planner_call_latency_s'] >= 0.3
    # The prompt already lists the independent actions as completed.
    prompt = planner.bundles[1].user_prompt
    assert 'place(spam, cupboard_shelf)' in prompt.split('## Remaining plan')[0]
    # The urgent block runs right after the wait, before the affected mug2 bundle.
    assert summary['completed_actions'][3:] == [
        'pick(spam)', 'place(spam, cupboard_shelf)', 'pick(sugar)', 'place(sugar, cupboard_shelf)',
        'pick(phone)', 'place(phone, table)', 'pick(mug2)', 'place(mug2, inside_box)']
    assert summary['success'] is True


def test_anchor_executed_during_the_wait_moves_the_block_to_the_front(tmp_path) -> None:
    # a7 = place(sugar, cupboard_shelf), executed while the planner works.
    pipeline, planner, summary, events = _parallel_run(tmp_path, [INITIAL, _blocks('deferred', 'after a7')])
    insertion = [e for e in events if e['event'] == 'insertion'][0]
    assert insertion['anchors_already_executed'] == ['a7']
    assert insertion['failure_codes'] == [FailureCode.ANCHOR_ALREADY_EXECUTED]
    assert insertion['merged_plan'][0].endswith('pick(phone)')
    assert summary['success'] is True


def test_injected_conflict_is_a_merge_conflict_and_requeried(tmp_path) -> None:
    def patch(tmp_path, outputs, flags):
        import llm_pipeline.tests.test_if_where_pipeline as base

        original_run = base._run
        state = {'rejected': False}

        def run_with_conflict(tmp_path, outputs, **flags):
            from llm_pipeline.pipeline import LLMOnlyReplanningPipeline

            original_merge = LLMOnlyReplanningPipeline._merge_corrective

            def merge(self, result, trigger_event, held_object=None):
                parser = self.planner.parser
                original_parse = parser.parse

                def parse(text, held_object=None):
                    if not state['rejected'] and 'pick(phone)' in text and 'pick(mug2)' in text:
                        state['rejected'] = True
                        raise StrictParseError('region filled during the wait', failure_id=FailureCode.ORPHAN_PLACE,
                                               fact='inside_box was filled during the wait')
                    return original_parse(text, held_object=held_object)

                parser.parse = parse
                try:
                    return original_merge(self, result, trigger_event, held_object)
                finally:
                    parser.parse = original_parse

            LLMOnlyReplanningPipeline._merge_corrective = merge
            try:
                return original_run(tmp_path, outputs, **flags)
            finally:
                LLMOnlyReplanningPipeline._merge_corrective = original_merge

        return run_with_conflict(tmp_path, outputs, **flags)

    pipeline, planner, summary, events = _parallel_run(
        tmp_path, [INITIAL, _blocks('urgent', 'front'), _blocks('urgent', 'front')], patch=patch)
    parallel = [e for e in events if e['event'] == 'parallel']
    assert parallel[0]['merge_result'] == 'merge_conflict'
    planning = [e for e in events if e['event'] == 'planning_event']
    assert planning[2]['trigger_code'] == FailureCode.MERGE_CONFLICT
    assert summary['success'] is True


def test_trigger_is_never_evaluated_while_holding_an_object() -> None:
    from llm_pipeline.executor import DirectPrimitiveExecutor

    executor = DirectPrimitiveExecutor.__new__(DirectPrimitiveExecutor)
    calls = []
    executor.trigger_check = lambda remaining: calls.append(remaining)
    executor.held_object = 'mug2'
    assert executor._check_trigger([], 0) is None and calls == []
    executor.held_object = None
    assert executor._check_trigger([], 0) is None and calls == [[]]


def test_parallel_off_matches_phase_5(tmp_path) -> None:
    _, _, summary_off, events_off = _parallel_run(tmp_path / 'off', [INITIAL, _blocks('urgent', 'front')], CORRECTIVE)
    _, _, summary_on, events_on = _parallel_run(tmp_path / 'on', [INITIAL, _blocks('urgent', 'front')], PARALLEL)
    assert not [e for e in events_off if e['event'] == 'parallel']
    assert summary_off['completed_actions'] == [
        'pick(mug2)', 'place(mug2, table_staging_area)', 'open(box_lid)', 'pick(phone)', 'place(phone, table)',
        'pick(spam)', 'place(spam, cupboard_shelf)', 'pick(sugar)', 'place(sugar, cupboard_shelf)',
        'pick(mug2)', 'place(mug2, inside_box)']
    assert sorted(summary_off['completed_actions']) == sorted(summary_on['completed_actions'])
    assert summary_off['success'] is summary_on['success'] is True


# ---------------------------------------------------------------- Phase 7b: container only if overlapping
_K_REMAINING = [('a6', 'pick(spam)'), ('a7', 'place(spam, cupboard_shelf)'), ('a8', 'pick(sugar)'),
                ('a9', 'place(sugar, cupboard_shelf)'), ('a10', 'pick(mug1)'), ('a11', 'place(mug1, inside_box)'),
                ('a12', 'pick(mug2)'), ('a13', 'place(mug2, inside_box)'), ('a14', 'pick(mug3)'),
                ('a15', 'place(mug3, inside_box)')]            # the K3/K4 remaining plan when the box opens
_K_REGIONS = {'can_of_beans': 'inside_box', 'spam': 'pantry_area', 'sugar': 'pantry_area', 'mug1': 'pantry_area',
              'mug2': 'table_staging_area', 'mug3': 'table_staging_area'}


def _mug_ids(independent):
    return [b.ids for b in independent if any('mug' in action for _, action in b.actions)]


def test_k4_mug_placements_into_the_box_are_independent_during_the_replan() -> None:
    # K4: the can lies in the box's far half, outside the placement area, so the box is not affected.
    affected = affected_set('kitchen', ['can_of_beans'], _K_REGIONS, overlapping={'can_of_beans': []})
    assert 'inside_box' not in affected['regions'] and 'cupboard_shelf' in affected['regions']
    independent = independent_bundles(split_bundles(_K_REMAINING, _K_REGIONS), affected)
    assert _mug_ids(independent) == [['a10', 'a11'], ['a12', 'a13'], ['a14', 'a15']]
    # The groceries go to the can's goal region (cupboard) and wait for the replan.
    assert not any('spam' in a or 'sugar' in a for b in independent for _, a in b.actions)


def test_k3_mug_placements_into_the_box_wait_for_the_replan() -> None:
    # K3: the can overlaps the box placement area; every place into the box is dependent.
    affected = affected_set('kitchen', ['can_of_beans'], _K_REGIONS, overlapping={'can_of_beans': ['inside_box']})
    assert 'inside_box' in affected['regions']
    assert _mug_ids(independent_bundles(split_bundles(_K_REMAINING, _K_REGIONS), affected)) == []


def test_the_lid_of_a_non_overlapping_trigger_objects_container_stays_affected() -> None:
    # G1: cooked meat in the grill's far slots (not overlapping). Placing raw meat in the placement
    # slot may run, but closing the grill during the wait would overcook the cooked meat.
    remaining = [('a2', 'pick(plate)'), ('a3', 'place(plate, serving_area)'), ('a4', 'pick(raw_meat_1)'),
                 ('a5', 'place(raw_meat_1, inside_grill)'), ('a6', 'close(grill_lid)'), ('a7', 'open(grill_lid)')]
    regions = {'plate': 'dish_rack', 'raw_meat_1': 'prep_area', 'cooked_meat_1': 'inside_grill'}
    affected = affected_set('grill', ['cooked_meat_1'], regions, overlapping={'cooked_meat_1': []})
    assert 'grill_lid' in affected['objects'] and 'inside_grill' not in affected['regions']
    ids = [b.ids for b in independent_bundles(split_bundles(remaining, regions), affected)]
    assert ['a6'] not in ids and ['a7'] not in ids
    assert ['a2', 'a3'] in ids
