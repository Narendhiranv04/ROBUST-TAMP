"""Diagnostics: where things go wrong (plan.md Phase 7).

    python -m diagnostics.report results/phase3/oracle_ceiling results/phase5/... --out results/diagnostics

Reads every ``trial_log.jsonl`` (and the ``record.json`` next to it) under the given
directories and writes:

* ``diagnostics_primary.csv``: per condition and variant, the share of trials whose
  primary cause is each failure area (successes included, so rows sum to 100%);
* ``diagnostics_occurrences.csv``: the share of trials in which each area happened at
  least once, recovered or not;
* ``diagnostics_trials.csv``: one row per trial (primary area, occurrences, trigger match);
* ``summary.md`` and ``primary_causes.png`` (stacked bars of primary causes per condition).

Definitions and counting rules: docs/DIAGNOSTICS.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm_pipeline.failures import (  # noqa: E402
    INFRASTRUCTURE_FAILURE_CODES, FailureCheck, FailureCode, TerminationReason, failure_check_for,
)

AREAS: Dict[int, str] = {
    1: 'plan_format_error',
    2: 'plan_rule_error',
    3: 'corrective_sub_plan_error',
    4: 'insertion_error',
    5: 'task_plan_error',
    6: 'motion_grasp_error',
    7: 'merge_conflict',
    8: 'replan_budget_exhausted',
}
AREA_TITLES: Dict[int, str] = {
    1: 'Plan format error', 2: 'Plan rule error', 3: 'Corrective sub-plan error', 4: 'Insertion error',
    5: 'Task plan error', 6: 'Motion/grasp error', 7: 'Merge conflict', 8: 'Replan budget exhausted',
}
SUCCESS = 'success'
INFRASTRUCTURE = 'infrastructure'

# Plan-check codes about the form of the output (area 1); the rest of the plan check is area 2.
FORMAT_CODES = frozenset({
    FailureCode.UNKNOWN_ACTION_TOKEN, FailureCode.PLANNER_OUTPUT_NOT_PARSEABLE, FailureCode.PLANNER_OUTPUT_TOO_VERBOSE,
    FailureCode.UNOBSERVED_OBJECT, FailureCode.INVALID_CORRECTIVE_BLOCK, FailureCode.UNSUPPORTED_ACTION,
})
INFRASTRUCTURE_CODES = INFRASTRUCTURE_FAILURE_CODES
# Termination reasons of failure area 8.
LOOP_TERMINATIONS = frozenset({TerminationReason.REPLAN_BUDGET_EXHAUSTED, TerminationReason.REPLAN_LOOP})


@dataclass
class ErrorEvent:
    seq: int
    area: int
    code: str
    detail: str = ''
    action: Optional[str] = None
    recovered: bool = False


@dataclass
class TrialDiagnosis:
    trial_dir: str
    variant: str
    condition: str
    success: Optional[bool]
    infrastructure: bool
    primary: str                               # success / infrastructure / an AREAS value
    occurrences: Set[str] = field(default_factory=set)
    errors: List[ErrorEvent] = field(default_factory=list)
    trigger_match: Optional[bool] = None
    urgency_correct: Optional[int] = None      # first-proposal urgency, objects correct
    urgency_total: Optional[int] = None


def _code(value) -> str:
    return str(value or '')


def _area_for_code(code: str) -> Optional[int]:
    if not code or code in INFRASTRUCTURE_CODES:
        return None
    if code == FailureCode.INSERTION_TOO_LATE:
        return 4
    if code == FailureCode.MERGE_CONFLICT:
        return 7
    if code in (FailureCode.REPLAN_BUDGET_EXHAUSTED, FailureCode.REPEATED_PLANNER_OUTPUT):
        return 8
    if code in FORMAT_CODES:
        return 1
    check = failure_check_for(code)
    if check == FailureCheck.PLAN_CHECK:
        return 2
    if check == FailureCheck.PRE_ACTION_CHECK:
        return 2
    if check == FailureCheck.EXECUTION_FAILURE:
        return 6
    return None


def condition_key(trial_start: Mapping) -> str:
    """Planner model plus every logged setting that changes behavior: the Section 0.7 flags
    that differ between conditions, the prompt version and hints, the replan budget and the
    simulated planner delay (absent in logs before Phase 7b)."""
    condition = dict(trial_start.get('condition') or {})
    flags = dict(trial_start.get('flags') or condition.get('flags') or {})
    model = condition.get('planner_model') or 'unknown'
    parts = [model]
    for name, short in (('memory.enabled', 'mem'), ('replan.trigger_mode', 'trig'), ('replan.output_mode', 'out'),
                        ('replan.insertion_mode', 'ins'), ('parallel.enabled', 'par')):
        if name in flags:
            parts.append(f'{short}={flags[name]}')
    for name, short in (('prompt.version', 'prompt'), ('prompt.corrective_hints', 'hints')):
        if flags.get(name) not in (None, 'v2', 'off'):
            parts.append(f'{short}={flags[name]}')
    max_replans = trial_start.get('max_replans', condition.get('max_replans'))
    if max_replans is not None:
        parts.append(f'budget={max_replans}')
    delay = trial_start.get('simulated_planner_delay_s', condition.get('simulated_planner_delay_s'))
    if delay:
        parts.append(f'delay={float(delay):g}s')
    return ' '.join(parts)


def _expected_triggers(variant: str) -> Optional[Tuple[Set[str], Set[str]]]:
    from evaluation.final_variants import get_final_variant, is_final_variant

    if not is_final_variant(variant):
        return None
    spec = get_final_variant(variant)
    should = {obj for obj, kind in spec.expected_if.items() if kind != 'ignore'}
    ignore = {obj for obj, kind in spec.expected_if.items() if kind == 'ignore'}
    return should, ignore


def _observed_triggers(events: Sequence[Mapping]) -> Set[str]:
    """Objects that triggered a replan: the trigger objects of the trigger checks (both modes
    from Phase 7b) and, for older discovery logs, of new_object_discovered replans."""
    observed = set()
    for event in events:
        if event.get('event') == 'if_check':
            observed.update(event.get('trigger_objects') or [])
        elif event.get('event') == 'planning_event' and event.get('trigger_code') == FailureCode.NEW_OBJECT_DISCOVERED:
            observed.update(event.get('trigger_objects') or [])
    return observed


def _urgency_accuracy(variant: str, events: Sequence[Mapping]) -> Tuple[Optional[int], Optional[int]]:
    from evaluation.final_variants import get_final_variant, is_final_variant

    if not is_final_variant(variant):
        return None, None
    expected = get_final_variant(variant).expected_urgency
    first = next((e for e in events if e.get('event') == 'insertion' and e.get('first_proposal')), None)
    if first is None or not expected:
        return None, None
    proposed = dict(first.get('urgency') or {})
    judged = [obj for obj in expected if obj in proposed]
    if not judged:
        return None, None
    return sum(proposed[obj] == expected[obj] for obj in judged), len(judged)


def collect_errors(events: Sequence[Mapping]) -> List[ErrorEvent]:
    """Errors in time order, each marked recovered or not."""
    errors: List[ErrorEvent] = []
    for event in events:
        kind, seq = event.get('event'), int(event.get('seq', 0))
        if kind == 'plan_check' and event.get('result') == 'fail':
            for code in event.get('failure_codes') or []:
                if code == FailureCode.INSERTION_TOO_LATE:
                    continue          # counted from the insertion event
                area = _area_for_code(code)
                if area:
                    errors.append(ErrorEvent(seq, area, code, event.get('fact') or ''))
        elif kind == 'insertion' and event.get('accepted') is False:
            code = _code(event.get('rejection_code'))
            area = _area_for_code(code)
            if area and area != 1 and area != 2:
                errors.append(ErrorEvent(seq, area, code, event.get('rejection') or ''))
        elif kind == 'pre_action_check' and event.get('result') == 'fail':
            for code in event.get('failure_codes') or []:
                errors.append(ErrorEvent(seq, 2, code, action=event.get('action')))
        elif kind == 'action_end' and event.get('outcome') == 'failure':
            code = _code(event.get('failure_code'))
            area = _area_for_code(code)
            if area in (2, 6) or (area is None and code and code not in INFRASTRUCTURE_CODES):
                errors.append(ErrorEvent(seq, area or 6, code, action=event.get('action')))
        elif kind == 'parallel' and event.get('merge_result') == 'merge_conflict':
            errors.append(ErrorEvent(seq, 7, FailureCode.MERGE_CONFLICT))
    # Recovery.
    for error in errors:
        later = [e for e in events if int(e.get('seq', 0)) > error.seq]
        if error.area in (1, 2) and error.action is None:
            error.recovered = any(e.get('event') == 'plan_check' and e.get('result') == 'pass' for e in later)
        elif error.area in (4, 7):
            error.recovered = any(e.get('event') == 'insertion' and e.get('accepted') for e in later)
        else:  # action-level failures: the same action later succeeds
            error.recovered = any(e.get('event') == 'action_end' and e.get('outcome') == 'success'
                                  and e.get('action') == error.action for e in later)
    return errors


def diagnose(trial_dir: Path, events: Sequence[Mapping], record: Optional[Mapping] = None) -> TrialDiagnosis:
    start = next((e for e in events if e.get('event') == 'trial_start'), {})
    end = next((e for e in reversed(events) if e.get('event') == 'trial_end'), {})
    variant = str(start.get('variant') or (record or {}).get('variant_id') or '')
    termination = end.get('termination_reason')
    success = end.get('success') if end else (record or {}).get('episode_success')
    infrastructure = termination == INFRASTRUCTURE or not end
    errors = collect_errors(events)
    occurrences = {AREAS[e.area] for e in errors}
    if termination in LOOP_TERMINATIONS or any(
            e.get('event') == 'plan_check' and FailureCode.REPEATED_PLANNER_OUTPUT in (e.get('failure_codes') or [])
            for e in events):
        occurrences.add(AREAS[8])

    replanned = any(e.get('event') == 'planning_event' and e.get('kind') == 'replan' for e in events)
    corrective = any(e.get('event') == 'insertion' and e.get('accepted') for e in events)
    missing = list(end.get('missing') or ((record or {}).get('success_validation') or {}).get('missing') or [])
    procedure_missing = [m for m in missing if 'overcooked' in m or 'before completing a cooking cycle' in m
                         or 'HC-grill violated' in m or 'HC-box violated' in m]
    trigger_objects = set()
    for e in events:
        if e.get('event') == 'planning_event' and e.get('kind') == 'replan':
            trigger_objects.update(e.get('trigger_objects') or [])
    if procedure_missing:
        occurrences.add(AREAS[4] if replanned else AREAS[5])

    if infrastructure:
        primary = INFRASTRUCTURE
    elif success:
        primary = SUCCESS
    elif termination == TerminationReason.REPLAN_LOOP and not (procedure_missing and replanned):
        # The same output for the same state after a repeat note stopped the trial.
        primary = AREAS[8]
    else:
        # A loop that follows an irreversible procedure violation (raw meat plated early,
        # overcooked meat) is its consequence: the violation stays the primary cause (area 4)
        # and the loop is counted as an occurrence (e.g. always_front on G2/G3).
        consequence_of_violation = bool(procedure_missing and replanned)
        unrecovered = [e for e in errors if not e.recovered and not (consequence_of_violation and e.area == 8)]
        if unrecovered:
            primary = AREAS[unrecovered[0].area]
        elif procedure_missing:
            primary = AREAS[4] if replanned else AREAS[5]
        elif corrective and any(obj in m for m in missing for obj in trigger_objects):
            primary = AREAS[3]
        elif termination == FailureCode.REPLAN_BUDGET_EXHAUSTED:
            primary = AREAS[8]
        else:
            primary = AREAS[5]
        if primary == AREAS[3]:
            occurrences.add(AREAS[3])
        if primary == AREAS[5]:
            occurrences.add(AREAS[5])

    expected = _expected_triggers(variant)
    trigger_match = None
    if expected is not None and not infrastructure:
        should, ignore = expected
        observed = _observed_triggers(events)
        trigger_match = should <= observed and not (observed & ignore)
    correct, total = _urgency_accuracy(variant, events)
    return TrialDiagnosis(str(trial_dir), variant, condition_key(start), success, infrastructure, primary,
                          occurrences, errors, trigger_match, correct, total)


def load_trials(roots: Iterable[Path]) -> List[TrialDiagnosis]:
    from llm_pipeline.trial_log import read_trial_log

    diagnoses = []
    for root in roots:
        for log in sorted(Path(root).rglob('trial_log.jsonl')):
            events = read_trial_log(log)
            record_path = log.parent / 'record.json'
            record = json.loads(record_path.read_text()) if record_path.exists() else None
            diagnoses.append(diagnose(log.parent, events, record))
    return diagnoses


def _rows(diagnoses: Sequence[TrialDiagnosis], by_variant: bool, primary: bool) -> List[Dict[str, object]]:
    groups: Dict[Tuple[str, str], List[TrialDiagnosis]] = defaultdict(list)
    for d in diagnoses:
        groups[(d.condition, d.variant if by_variant else 'ALL')].append(d)
    rows = []
    for (condition, variant), items in sorted(groups.items()):
        evaluated = [d for d in items if not d.infrastructure]
        row: Dict[str, object] = {'condition': condition, 'variant': variant, 'trials': len(evaluated),
                                  'infrastructure_trials': len(items) - len(evaluated)}
        n = max(1, len(evaluated))
        if primary:
            counts = Counter(d.primary for d in evaluated)
            row['success_pct'] = round(100.0 * counts.get(SUCCESS, 0) / n, 1)
        for area in AREAS.values():
            if primary:
                row[f'{area}_pct'] = round(100.0 * sum(d.primary == area for d in evaluated) / n, 1)
            else:
                row[f'{area}_pct'] = round(100.0 * sum(area in d.occurrences for d in evaluated) / n, 1)
        matches = [d.trigger_match for d in evaluated if d.trigger_match is not None]
        row['trigger_accuracy_pct'] = round(100.0 * sum(matches) / len(matches), 1) if matches else ''
        correct = sum(d.urgency_correct or 0 for d in evaluated if d.urgency_total)
        total = sum(d.urgency_total or 0 for d in evaluated if d.urgency_total)
        row['first_proposal_urgency_accuracy_pct'] = round(100.0 * correct / total, 1) if total else ''
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(rows: Sequence[Mapping[str, object]], columns: Sequence[str]) -> List[str]:
    lines = ['| ' + ' | '.join(columns) + ' |', '|' + '---|' * len(columns)]
    for row in rows:
        lines.append('| ' + ' | '.join(str(row.get(column, '')) for column in columns) + ' |')
    return lines


def _chart(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    import matplotlib

    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    labels = [str(row['condition']) for row in rows]
    series = [('success_pct', 'Success', '#4c9a5a')] + [
        (f'{area}_pct', AREA_TITLES[number], color) for (number, area), color in zip(
            AREAS.items(), ['#d95f02', '#e6ab02', '#7570b3', '#e7298a', '#a6761d', '#1b9e77', '#666666', '#b2182b'])]
    fig, ax = plt.subplots(figsize=(max(7, 1.6 * len(labels) + 4), 5.5))
    bottom = [0.0] * len(labels)
    for key, title, color in series:
        values = [float(row.get(key) or 0) for row in rows]
        if not any(values):
            continue
        ax.bar(labels, values, bottom=bottom, label=title, color=color)
        bottom = [b + v for b, v in zip(bottom, values)]
    ax.set_ylabel('% of trials (primary cause)')
    ax.set_ylim(0, 100)
    ax.legend(loc='upper left', bbox_to_anchor=(1.0, 1.0), frameon=False)
    ax.set_title('Primary cause per condition')
    plt.setp(ax.get_xticklabels(), rotation=20, ha='right')
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def write_report(diagnoses: Sequence[TrialDiagnosis], out: Path) -> Dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    primary_rows = _rows(diagnoses, by_variant=True, primary=True)
    occurrence_rows = _rows(diagnoses, by_variant=True, primary=False)
    primary_by_condition = _rows(diagnoses, by_variant=False, primary=True)
    occurrence_by_condition = _rows(diagnoses, by_variant=False, primary=False)
    _write_csv(out / 'diagnostics_primary.csv', primary_by_condition + primary_rows)
    _write_csv(out / 'diagnostics_occurrences.csv', occurrence_by_condition + occurrence_rows)
    _write_csv(out / 'diagnostics_trials.csv', [{
        'trial_dir': d.trial_dir, 'condition': d.condition, 'variant': d.variant, 'success': d.success,
        'primary': d.primary, 'occurrences': ';'.join(sorted(d.occurrences)), 'trigger_match': d.trigger_match,
        'unrecovered_errors': ';'.join(f'{e.code}@{e.seq}' for e in d.errors if not e.recovered),
    } for d in diagnoses])
    if primary_by_condition:
        _chart(out / 'primary_causes.png', primary_by_condition)
    area_columns = [f'{area}_pct' for area in AREAS.values()]
    lines = ['# Diagnostics', '', f'{len(diagnoses)} trials '
             f'({sum(d.infrastructure for d in diagnoses)} infrastructure, excluded). Definitions: docs/DIAGNOSTICS.md.',
             '', '## Primary cause (sums to 100% with successes), per condition', '']
    lines += _markdown_table(primary_by_condition, ['condition', 'trials', 'success_pct'] + area_columns
                             + ['trigger_accuracy_pct', 'first_proposal_urgency_accuracy_pct'])
    lines += ['', '## Occurrences (at least once, recovered or not), per condition', '']
    lines += _markdown_table(occurrence_by_condition, ['condition', 'trials'] + area_columns)
    lines += ['', '## Primary cause per variant', '']
    lines += _markdown_table(primary_rows, ['condition', 'variant', 'trials', 'success_pct'] + area_columns
                             + ['trigger_accuracy_pct', 'first_proposal_urgency_accuracy_pct'])
    unassigned = [d for d in diagnoses if not d.infrastructure and not d.success and d.primary not in AREAS.values()]
    lines += ['', f'Failed trials without a primary area: {len(unassigned)}']
    (out / 'summary.md').write_text('\n'.join(lines) + '\n')
    return {'trials': len(diagnoses), 'unassigned': [d.trial_dir for d in unassigned]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('roots', nargs='+')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    summary = write_report(load_trials(Path(root) for root in args.roots), Path(args.out))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
