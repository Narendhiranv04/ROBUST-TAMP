"""Phase 7: one hand-made log per failure area, and the first-unrecovered-error rule."""

import pytest

from diagnostics.report import AREAS, collect_errors, diagnose, load_trials, write_report

START = {'event': 'trial_start', 'variant': 'FINAL.K1', 'seq': 0,
         'condition': {'planner_model': 'mock'}, 'flags': {'replan.trigger_mode': 'if_rule'}}


def _end(success, reason='plan_completed', missing=()):
    return {'event': 'trial_end', 'seq': 999, 'success': success, 'termination_reason': reason, 'missing': list(missing)}


def _trial(*events, success=False, reason='plan_completed', missing=(), variant='FINAL.K1'):
    start = dict(START, variant=variant)
    items = [start] + [dict(e, seq=i + 1) for i, e in enumerate(events)] + [_end(success, reason, missing)]
    return diagnose('t', items)


def plan_check(result, *codes):
    return {'event': 'plan_check', 'result': result, 'failure_codes': list(codes)}


def action_end(action, outcome, code=None):
    return {'event': 'action_end', 'action': action, 'outcome': outcome, 'failure_code': code}


REPLAN = {'event': 'planning_event', 'kind': 'replan', 'trigger_objects': ['phone'], 'trigger_code': 'if_rule_trigger'}
TRIGGER = {'event': 'if_check', 'trigger_objects': ['phone']}


def test_area_1_plan_format_error() -> None:
    assert _trial(plan_check('fail', 'planner_output_not_parseable')).primary == AREAS[1]


def test_area_2_plan_rule_error() -> None:
    assert _trial(plan_check('fail', 'orphan_place')).primary == AREAS[2]


def test_area_3_corrective_sub_plan_error() -> None:
    d = _trial(TRIGGER, REPLAN, {'event': 'insertion', 'accepted': True, 'first_proposal': True, 'urgency': {'phone': 'urgent'}},
               missing=['phone is in the inside_box placement area'])
    assert d.primary == AREAS[3]


def test_area_4_insertion_error_too_late_and_overcooked() -> None:
    too_late = _trial(REPLAN, {'event': 'insertion', 'accepted': False, 'rejection_code': 'insertion_too_late'},
                      reason='replan_budget_exhausted')
    assert too_late.primary == AREAS[4]
    overcooked = _trial(REPLAN, {'event': 'insertion', 'accepted': True},
                        missing=['cooked_meat_1 overcooked: inside the grill during a close->reopen cycle'],
                        variant='FINAL.G1')
    assert overcooked.primary == AREAS[4]


def test_area_5_task_plan_error() -> None:
    d = _trial(plan_check('pass'), action_end('pick(mug1)', 'success'), missing=['mug2 is in table, expected inside_box'])
    assert d.primary == AREAS[5]


def test_area_6_motion_grasp_error() -> None:
    assert _trial(action_end('pick(mug1)', 'failure', 'grasp_failed')).primary == AREAS[6]


def test_area_7_merge_conflict() -> None:
    d = _trial(REPLAN, {'event': 'parallel', 'merge_result': 'merge_conflict'}, reason='replan_budget_exhausted')
    assert d.primary == AREAS[7]


def test_area_8_replan_budget_exhausted() -> None:
    d = _trial(REPLAN, plan_check('pass'), reason='replan_budget_exhausted')
    assert d.primary == AREAS[8]


def test_first_unrecovered_error_is_the_primary_cause() -> None:
    d = _trial(
        plan_check('fail', 'planner_output_not_parseable'),        # recovered by the next pass
        plan_check('pass'),
        action_end('pick(mug1)', 'failure', 'grasp_failed'),        # recovered: the same pick later succeeds
        action_end('pick(mug1)', 'success'),
        action_end('place(mug1, inside_box)', 'failure', 'placement_failed'),   # never recovered -> primary
        plan_check('fail', 'orphan_place'),                         # later and unrecovered
    )
    assert d.primary == AREAS[6]
    assert d.occurrences == {AREAS[1], AREAS[2], AREAS[6]}
    assert [e.recovered for e in d.errors] == [True, True, False, False]


def test_success_infrastructure_and_trigger_accuracy() -> None:
    ok = _trial(TRIGGER, success=True)
    assert ok.primary == 'success' and ok.trigger_match is True
    k2 = _trial({'event': 'if_check', 'trigger_objects': ['phone']}, success=True, variant='FINAL.K2')
    assert k2.trigger_match is False                               # K2's phone must be ignored
    infra = diagnose('t', [START, dict(_end(None, 'infrastructure'), seq=1)])
    assert infra.primary == 'infrastructure' and infra.trigger_match is None


def test_report_writes_tables(tmp_path) -> None:
    import json

    trial = tmp_path / 'runs' / 'FINAL.K1' / 'seed_00'
    trial.mkdir(parents=True)
    events = [dict(START, trial_id='x', t=0, wall_time='w'), dict(_end(True), seq=1, trial_id='x', t=1, wall_time='w')]
    (trial / 'trial_log.jsonl').write_text('\n'.join(json.dumps(e) for e in events) + '\n')
    summary = write_report(load_trials([tmp_path / 'runs']), tmp_path / 'out')
    assert summary['trials'] == 1 and not summary['unassigned']
    assert (tmp_path / 'out' / 'diagnostics_primary.csv').read_text().count('\n') >= 2
    assert (tmp_path / 'out' / 'primary_causes.png').exists()
