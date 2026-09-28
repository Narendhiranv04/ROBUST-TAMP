"""Report and completeness check for one model's run (all variants x seeds of one planner profile).

    python -m evaluation.model_run_report <run_dir> [--variants ...] [--seeds 0-9]

Reads every ``<run_dir>/<variant>/seed_<NN>/{trial_log.jsonl, record.json}`` and writes
``run_report.json`` and ``run_report.md``:

* the Table 2 row: SR_K (kitchen variants), SR_G (grill variants), SR and PGC over all trials
  (the paper's definition: ``paper_outcome``), Plan. (mean planner time per trial, s), and the
  trials with an insertion error (an ordering hard constraint violated; not part of SR or PGC);
* per variant: success, PGC, planner calls, replans, planner and trial time, output tokens,
  answers cut off at the token limit, plan-check rejections by code, termination reasons, and
  implicit non-target handling (G1, G3) where the record has it;
* per call: latency and token percentiles.

The exit code is 0 only when the run is complete: every expected variant and seed has a
``trial_end`` and no trial ended as ``infrastructure``. The model-queue runner deletes a model's
weights only after this passes.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

FINAL_VARIANTS = ['FINAL.K0', 'FINAL.G0', 'FINAL.K1', 'FINAL.K2', 'FINAL.K3', 'FINAL.K4', 'FINAL.G1', 'FINAL.G2',
                  'FINAL.G3', 'FINAL.K3-n2', 'FINAL.K3-n3', 'FINAL.G1-n1', 'FINAL.K1-w1', 'FINAL.K1-w2']


def _seeds(text: str) -> list:
    out = []
    for part in text.split(','):
        if '-' in part:
            a, b = part.split('-')
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def _pct(values, q):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(q * (len(values) - 1))))], 3)


def _mean(values):
    return round(statistics.mean(values), 4) if values else None


def paper_outcome(end: dict, variant: str) -> dict:
    """Success and PGC as the paper defines them, from a trial's ``trial_end``.

    R: every final object-region relation (each mug in the box, each grocery in the cupboard, the
    phone in no placement area; the plate in the serving area, each meat on the plate). P: each
    meat correctly cooked (grill only). The evaluator also checks ordering hard constraints
    (``HC-...``: no mug into the box before an overlapping object is cleared; no cooked meat in
    the grill at a close). They are not R or P conditions: a violation is an insertion error,
    reported separately, and does not change success or PGC.
    """
    relations, procedures = int(end.get('goal_relations_total') or 0), int(end.get('procedure_checks_total') or 0)
    missing = list(end.get('missing') or [])
    hc = [m for m in missing if m.startswith('HC-')]
    unmet = [m for m in missing if not m.startswith('HC-')]
    # Kitchen: every procedure check is an HC check. Grill: one cooking condition per meat
    # (meats = relations - 1, the plate relation), the rest are HC checks.
    cooking = 0 if variant.startswith('FINAL.K') else max(0, relations - 1)
    total = relations + cooking
    return {'success': not unmet, 'pgc': (total - len(unmet)) / total if total else 0.0,
            'conditions': total, 'unmet': unmet, 'hc_checks': procedures - cooking, 'hc_violations': len(hc),
            'hc_violated': hc}


def read_trial(trial_dir: Path) -> dict:
    events = []
    log = trial_dir / 'trial_log.jsonl'
    if log.exists():
        for line in log.read_text(encoding='utf-8').splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    end = next((e for e in reversed(events) if e.get('event') == 'trial_end'), None)
    calls = [e for e in events if e.get('event') == 'planning_event']
    rejections = Counter(code for e in events if e.get('event') == 'plan_check' and e.get('result') == 'fail'
                         for code in e.get('failure_codes') or [])
    record = {}
    if (trial_dir / 'record.json').exists():
        try:
            record = json.loads((trial_dir / 'record.json').read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            record = {}
    return {'end': end, 'calls': calls, 'rejections': rejections, 'record': record,
            'actions': [e.get('action') for e in events if e.get('event') == 'action_end' and e.get('outcome') == 'success']}


def build_report(run_dir: Path, variants, seeds) -> dict:
    per_variant, all_trials, problems = {}, [], []
    for variant in variants:
        rows = []
        for seed in seeds:
            trial = read_trial(run_dir / variant / f'seed_{seed:02d}')
            end = trial['end']
            if end is None:
                problems.append(f'{variant} seed {seed}: no trial_end')
                continue
            if end.get('termination_reason') == 'infrastructure':
                problems.append(f'{variant} seed {seed}: infrastructure')
            tokens = [c.get('completion_tokens') for c in trial['calls'] if c.get('completion_tokens') is not None]
            outcome = paper_outcome(end, variant)
            rows.append({
                'seed': seed, 'success': outcome['success'], 'pgc': outcome['pgc'],
                'hc_violations': outcome['hc_violations'], 'unmet': outcome['unmet'], 'hc_violated': outcome['hc_violated'],
                'evaluator_success_with_hc': bool(end.get('success')),
                'calls': int(end.get('planner_calls') or 0), 'planner_time_s': float(end.get('planner_time_s') or 0.0),
                'trial_time_s': float(end.get('trial_time_s') or 0.0), 'termination': end.get('termination_reason'),
                'tokens': tokens, 'cut_off': sum(1 for c in trial['calls'] if c.get('finish_reason') == 'length'),
                'latencies': [float(c.get('planner_call_latency_s') or 0.0) for c in trial['calls']],
                'rejections': trial['rejections'],
                'inh': trial['record'].get('implicit_non_target_handling_success'),
                'executed_actions': trial['actions'],
            })
        scored = [r for r in rows if r['termination'] != 'infrastructure']
        per_variant[variant] = {
            'trials': len(rows), 'scored_trials': len(scored),
            'success_rate': _mean([float(r['success']) for r in scored]),
            'pgc': _mean([r['pgc'] for r in scored]),
            'insertion_errors': sum(r['hc_violations'] for r in scored),
            'trials_with_insertion_errors': sum(1 for r in scored if r['hc_violations']),
            'mean_planner_calls': _mean([r['calls'] for r in scored]),
            'mean_replans': _mean([max(0, r['calls'] - 1) for r in scored]),
            'mean_planner_time_s': _mean([r['planner_time_s'] for r in scored]),
            'mean_trial_time_s': _mean([r['trial_time_s'] for r in scored]),
            'mean_output_tokens_per_trial': _mean([sum(r['tokens']) for r in scored]),
            'answers_cut_off': sum(r['cut_off'] for r in scored),
            'plan_check_rejections': dict(sum((r['rejections'] for r in scored), Counter())),
            'termination_reasons': dict(Counter(r['termination'] for r in rows)),
            'inh_rate': _mean([float(r['inh']) for r in scored if r['inh'] is not None]),
            'trials_detail': [{k: v for k, v in r.items() if k not in ('latencies', 'tokens', 'rejections')}
                              | {'tokens': r['tokens'], 'rejections': dict(r['rejections'])} for r in rows],
        }
        all_trials += [dict(r, variant=variant) for r in scored]

    def scene(prefix):
        rows = [r for r in all_trials if r['variant'].startswith(prefix)]
        return _mean([float(r['success']) for r in rows]), len(rows)

    sr_k, n_k = scene('FINAL.K')
    sr_g, n_g = scene('FINAL.G')
    latencies = [x for r in all_trials for x in r['latencies']]
    tokens = [x for r in all_trials for x in r['tokens']]
    return {
        'run_dir': str(run_dir), 'variants': list(variants), 'seeds': list(seeds),
        'complete': not problems, 'problems': problems,
        'table2_row': {
            'SR_K': sr_k, 'SR_G': sr_g, 'SR': _mean([float(r['success']) for r in all_trials]),
            'PGC': _mean([r['pgc'] for r in all_trials]),
            'Plan_s': _mean([r['planner_time_s'] for r in all_trials]),
            'insertion_error_trials': sum(1 for r in all_trials if r['hc_violations']),
            'kitchen_trials': n_k, 'grill_trials': n_g, 'trials': len(all_trials),
        },
        'overall': {
            'mean_planner_calls': _mean([r['calls'] for r in all_trials]),
            'mean_trial_time_s': _mean([r['trial_time_s'] for r in all_trials]),
            'planner_call_latency_s': {'mean': _mean(latencies), 'p50': _pct(latencies, 0.5), 'p90': _pct(latencies, 0.9),
                                       'max': max(latencies) if latencies else None, 'calls': len(latencies)},
            'output_tokens_per_call': {'mean': _mean(tokens), 'p50': _pct(tokens, 0.5), 'p90': _pct(tokens, 0.9),
                                       'max': max(tokens) if tokens else None},
            'answers_cut_off': sum(r['cut_off'] for r in all_trials),
            'termination_reasons': dict(Counter(r['termination'] for r in all_trials)),
        },
        'per_variant': per_variant,
    }


def to_markdown(report: dict) -> str:
    row = report['table2_row']
    f = lambda v, pct=True: '-' if v is None else (f'{100 * v:.1f}' if pct else f'{v:.1f}')  # noqa: E731
    lines = [f"# Run report: {report['run_dir']}", '',
             f"Complete: **{report['complete']}**" + ('' if report['complete'] else ' - ' + '; '.join(report['problems'][:20])), '',
             '| SR_K | SR_G | SR | PGC | Plan. (s) | trials |', '|---|---|---|---|---|---|',
             f"| {f(row['SR_K'])} | {f(row['SR_G'])} | {f(row['SR'])} | {f(row['PGC'])} | {f(row['Plan_s'], False)} | {row['trials']} |", '',
             '| Variant | Trials | SR | PGC | Insertion errors (trials) | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |',
             '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for variant, v in report['per_variant'].items():
        lines.append(f"| {variant} | {v['scored_trials']}/{v['trials']} | {f(v['success_rate'])} | {f(v['pgc'])} | {v['trials_with_insertion_errors']} | "
                     f"{f(v['mean_planner_calls'], False)} | {f(v['mean_planner_time_s'], False)} | {f(v['mean_trial_time_s'], False)} | "
                     f"{f(v['mean_output_tokens_per_trial'], False)} | {v['answers_cut_off']} | "
                     f"{', '.join(f'{k}: {n}' for k, n in v['plan_check_rejections'].items()) or '-'} | {f(v['inh_rate'])} | "
                     f"{', '.join(f'{k}: {n}' for k, n in v['termination_reasons'].items())} |")
    o = report['overall']
    lines += ['', f"Planner call latency (s): mean {o['planner_call_latency_s']['mean']}, p50 {o['planner_call_latency_s']['p50']}, "
              f"p90 {o['planner_call_latency_s']['p90']}, max {o['planner_call_latency_s']['max']} over {o['planner_call_latency_s']['calls']} calls",
              f"Output tokens per call: mean {o['output_tokens_per_call']['mean']}, p50 {o['output_tokens_per_call']['p50']}, "
              f"p90 {o['output_tokens_per_call']['p90']}, max {o['output_tokens_per_call']['max']}; cut off at the limit: {o['answers_cut_off']}"]
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('run_dir')
    parser.add_argument('--variants', nargs='+', default=FINAL_VARIANTS)
    parser.add_argument('--seeds', default='0-9')
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    report = build_report(run_dir, args.variants, _seeds(args.seeds))
    (run_dir / 'run_report.json').write_text(json.dumps(report, indent=1, default=str), encoding='utf-8')
    (run_dir / 'run_report.md').write_text(to_markdown(report), encoding='utf-8')
    print(json.dumps({'complete': report['complete'], 'problems': report['problems'][:10], **report['table2_row']}))
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
