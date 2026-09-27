"""Failure analysis in the paper's Table 1 areas, per model and variant, from the trial logs.

    python -m evaluation.failure_breakdown --results results/table2_runs --out results/table2/failures

For every run directory (one profile alias) and every variant, counts each surfaced failure event
by Table 1 area (every plan-check / merge-check rejection, pre-action refusal, execution failure),
and gives each failed trial one decisive cause (why it ended unsuccessfully). Writes
``failure_breakdown.md`` (one table per model, a combined table), ``failure_breakdown.csv`` and
``failed_trials.csv`` (one row per failed trial: model, variant, seed, termination, decisive
cause, the evaluator's missing conditions, the rejection codes it met).

Table 1 areas (detected by -> response):
* Model output
  - Plan format (plan check -> re-query): unknown action/object/region, unparseable, too verbose;
  - Plan rules (plan check -> re-query): place without pick, pick while holding, pick/place mismatch;
* Model reasoning
  - Corrective block (merge check -> re-query): invalid block (misses a trigger object, lists an
    object that is not one, bad block syntax, urgent not at the front, ...);
  - Insertion (merge check / evaluator -> re-query / fail): too late (blocked, overcooked), too early;
  - Scene precondition (pre-action check -> replan): e.g. open while an object is on the lid, place
    into a closed box. Not a Table 1 row: it is listed separately here;
  - Task plan (evaluator -> fail): the plan completed but the goal is not met;
* Robot and system
  - Motion / grasp (executor -> local retry, then replan): no IK, no motion plan, grasp or placement failed;
  - Merge conflict (merge check -> re-query): the replan clashes with actions run during the wait;
  - Replan budget (loop monitor -> stop): limit reached, repeated output loop.
Infrastructure trials are excluded (never scored).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

VARIANTS = ['FINAL.K0', 'FINAL.K1', 'FINAL.K2', 'FINAL.K3', 'FINAL.K4', 'FINAL.K3-n2', 'FINAL.K3-n3', 'FINAL.K1-w1',
            'FINAL.K1-w2', 'FINAL.G0', 'FINAL.G1', 'FINAL.G2', 'FINAL.G3', 'FINAL.G1-n1']
AREAS = ['Plan format', 'Plan rules', 'Corrective block', 'Insertion', 'Scene precondition', 'Task plan',
         'Motion / grasp', 'Merge conflict', 'Replan budget', 'Other']
GROUP = {'Plan format': 'Model output', 'Plan rules': 'Model output', 'Corrective block': 'Model reasoning',
         'Insertion': 'Model reasoning', 'Scene precondition': 'Model reasoning', 'Task plan': 'Model reasoning',
         'Motion / grasp': 'Robot and system', 'Merge conflict': 'Robot and system', 'Replan budget': 'Robot and system',
         'Other': 'Other'}
CODE_AREA = {
    'unknown_action_token': 'Plan format', 'unobserved_object': 'Plan format', 'planner_output_not_parseable': 'Plan format',
    'planner_output_too_verbose': 'Plan format', 'unsupported_action': 'Plan format',
    'orphan_place': 'Plan rules', 'missing_post_pick_place': 'Plan rules', 'pick_place_mismatch': 'Plan rules',
    'block_ends_holding': 'Plan rules',
    'invalid_corrective_block': 'Corrective block',
    'insertion_too_late': 'Insertion',
    'box_lid_obstructed': 'Scene precondition', 'box_lid_closed': 'Scene precondition', 'grill_lid_closed': 'Scene precondition',
    'pick_object_missing': 'Scene precondition', 'lid_missing': 'Scene precondition', 'invalid_executor_state': 'Scene precondition',
    'remembered_object_inaccessible': 'Scene precondition',
    'merge_conflict': 'Merge conflict', 'anchor_already_executed': 'Merge conflict',
    'repeated_planner_output': 'Replan budget', 'replan_budget_exhausted': 'Replan budget',
}
MOTION = ('pddl_no_plan', 'no_ik_solution', 'no_motion_plan', 'no_grasp_found', 'empty_pick_trajectory', 'empty_place_trajectory',
          'lid_hover_planning_fail', 'lid_slide_planning_fail', 'executor_failure', 'grasp_failed', 'object_dropped',
          'object_did_not_move', 'object_missing_after_place', 'placement_failed', 'geometric_placement_failed',
          'lid_not_open_enough', 'lid_not_closed_enough')


def area_of(code: str) -> str:
    if code in CODE_AREA:
        return CODE_AREA[code]
    if code in MOTION:
        return 'Motion / grasp'
    return 'Other'


def insertion_or_task(missing) -> str:
    """Evaluator: procedure / ordering violations are insertion errors, the rest task-plan errors."""
    text = ' '.join(missing or [])
    if any(k in text for k in ('HC-', 'overcooked', 'before completing a cooking cycle', 'before', 'cleared')):
        return 'Insertion'
    return 'Task plan'


def analyse_trial(path: Path):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    end = next((e for e in events if e.get('event') == 'trial_end'), None)
    if end is None or end.get('termination_reason') == 'infrastructure':
        return None
    counts, codes = Counter(), Counter()
    for e in events:
        kind = e.get('event')
        if kind == 'plan_check' and e.get('result') == 'fail':
            for c in e.get('failure_codes') or []:
                counts[area_of(c)] += 1
                codes[c] += 1
        elif kind == 'action_end' and e.get('outcome') == 'failure' and e.get('failure_code'):
            counts[area_of(e['failure_code'])] += 1
            codes[e['failure_code']] += 1
    decisive = None
    if not end.get('success'):
        term = end.get('termination_reason')
        if term in ('replan_budget_exhausted', 'replan_loop'):
            model_codes = Counter({c: n for c, n in codes.items() if area_of(c) not in ('Replan budget',)})
            top = model_codes.most_common(1)
            decisive = f"{'loop' if term == 'replan_loop' else 'budget'} <- {area_of(top[0][0]) + ': ' + top[0][0] if top else 'none'}"
        elif term in ('plan_completed', 'planner_returned_no_actions', 'goal_check_satisfied'):
            decisive = insertion_or_task(end.get('missing'))
        else:
            decisive = f'Other ({term})'
    return {'success': bool(end.get('success')), 'termination': end.get('termination_reason'), 'counts': counts,
            'codes': codes, 'decisive': decisive, 'missing': end.get('missing') or [], 'calls': end.get('planner_calls')}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--results', default='results/table2_runs')
    parser.add_argument('--out', default='results/table2/failures')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md = ['# Failure analysis (Table 1 areas)', '',
          'Counts are surfaced failure events (every rejection, refusal and execution failure) summed over the trials of a '
          'variant; "failed" is failed trials / scored trials; "decisive" is the cause each failed trial ended with: '
          '"budget <- X" / "loop <- X" = the trial ran out of replans / repeated an output, X being its most frequent '
          'failure before that; "Task plan" / "Insertion" = the plan completed but the evaluator found the goal unmet / '
          'a procedure or ordering violation.', '']
    rows_csv, failed_csv = [], []
    for run in sorted(p for p in Path(args.results).iterdir() if p.is_dir()):
        per_variant = {}
        for v in VARIANTS:
            trials = [t for t in (analyse_trial(p) for p in sorted((run / v).glob('seed_*/trial_log.jsonl'))) if t]
            if not trials:
                continue
            per_variant[v] = trials
        if not per_variant:
            continue
        md += [f'## {run.name}', '', '| Variant | failed | ' + ' | '.join(AREAS[:-1]) + ' | decisive causes of the failed trials |',
               '|---|---|' + '---|' * (len(AREAS) - 1) + '---|']
        total = Counter()
        for v, trials in per_variant.items():
            counts = sum((t['counts'] for t in trials), Counter())
            total += counts
            fails = [t for t in trials if not t['success']]
            dec = Counter(t['decisive'] for t in fails)
            md.append(f"| {v} | {len(fails)}/{len(trials)} | " + ' | '.join(str(counts.get(a, 0) or '') for a in AREAS[:-1])
                      + ' | ' + '; '.join(f'{n}x {d}' for d, n in dec.most_common()) + ' |')
            rows_csv.append([run.name, v, len(trials), len(fails)] + [counts.get(a, 0) for a in AREAS])
            for seed, t in enumerate(trials):
                if not t['success']:
                    failed_csv.append([run.name, v, seed, t['termination'], t['decisive'], t['calls'],
                                       ' | '.join(t['missing']), ' '.join(f'{c}:{n}' for c, n in t['codes'].most_common())])
        md.append('| **all** | | ' + ' | '.join(str(total.get(a, 0) or '') for a in AREAS[:-1]) + ' | |')
        md.append('')
    with open(out / 'failure_breakdown.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['model', 'variant', 'trials', 'failed'] + AREAS)
        w.writerows(rows_csv)
    with open(out / 'failed_trials.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['model', 'variant', 'seed_index', 'termination', 'decisive_cause', 'planner_calls', 'missing_conditions', 'failure_codes'])
        w.writerows(failed_csv)
    (out / 'failure_breakdown.md').write_text('\n'.join(md) + '\n')
    print('\n'.join(md))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
