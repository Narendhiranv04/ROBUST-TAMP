"""Tables 4 and 5 of the paper and the planner latency of the scale study, from the trial logs.

    python -m evaluation.paper_tables --out results/table2

Inputs (the local backups; see server/backup_from_server.sh):
* ``results/v2_runs/table2/qwen3-vl-8b-thinking``: the full system with the selected planner;
* ``results/v2_runs/ablations/<condition>``: the ablations (core variants);
* ``results/v2_runs/table2/qwen3-8b``: the LLM planner row (the Table 2 (b) run, same state);
* ``results/gt_fixed/full_system``: the oracle planner (Ceil.);
* ``results/scale_runs/<alias>``: the scale study (latency).

Definitions (every one computed per trial, then averaged over the scored trials of the cell):
* SR, PGC: the paper's R and P conditions (evaluation/model_run_report.paper_outcome);
* Calls: planner calls per trial; Plan.: planner time per trial (s); Time: trial time (s);
* Idle: robot idle time per trigger replan (s): the time the robot waits for the corrective
  answer (the parallel scheduler's ``robot_idle_time_s`` for the first call, plus every re-query
  of that replan; without parallel execution the whole replan);
* Urg.: first-proposal urgency accuracy (%): per trigger object, whether the first corrective
  proposal gives the urgency the variant expects (a rejected or missing proposal counts wrong);
* Unn.: unnecessary replans per trial: trigger replans none of whose trigger objects needs an
  action (every one is marked ``ignore`` in the variant spec, e.g. the phone outside the placement
  area in K2). A trigger on a visible object the model's plan left out (mug2 in K2, the visible raw
  meat in the grill) is necessary: that object still needs an action;
* Ins.: insertion errors (% of trials): a corrective block rejected as inserted too late, a
  violated ordering constraint (a mug into the box before an overlapping object is cleared, a
  cooked meat in the grill at a close), meat overcooked, or meat served before it was cooked.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from evaluation.final_variants import get_final_variant
from evaluation.model_run_report import paper_outcome

ROOT = Path(__file__).resolve().parents[2] / "src"
V2 = ROOT / 'results' / 'v2_runs'
KITCHEN = ['FINAL.K0', 'FINAL.K1', 'FINAL.K2', 'FINAL.K3', 'FINAL.K4', 'FINAL.K3-n2', 'FINAL.K3-n3', 'FINAL.K1-w1', 'FINAL.K1-w2']
GRILL = ['FINAL.G0', 'FINAL.G1', 'FINAL.G2', 'FINAL.G3', 'FINAL.G1-n1']
TABLE4_ORDER = [('A. Basic', ['FINAL.K0', 'FINAL.G0']),
                ('B. Core', ['FINAL.K1', 'FINAL.K2', 'FINAL.K3', 'FINAL.K4', 'FINAL.G1', 'FINAL.G2', 'FINAL.G3']),
                ('C. Cardinality', ['FINAL.K3-n2', 'FINAL.K3-n3', 'FINAL.G1-n1', 'FINAL.K1-w1', 'FINAL.K1-w2'])]
CORE = ['FINAL.K1', 'FINAL.K2', 'FINAL.K3', 'FINAL.K4', 'FINAL.G1', 'FINAL.G2', 'FINAL.G3']
ABLATIONS = [('Full system', V2 / 'table2' / 'qwen3-vl-8b-thinking'), ('−Memory', V2 / 'ablations' / 'no_memory'),
             ('−IF', V2 / 'ablations' / 'no_if'), ('−WHERE', V2 / 'ablations' / 'no_where'),
             ('Fixed front', V2 / 'ablations' / 'fixed_front'), ('Fixed end', V2 / 'ablations' / 'fixed_end'),
             ('−WHEN', V2 / 'ablations' / 'no_when'), ('LLM planner', V2 / 'table2' / 'qwen3-8b')]
# Table 5 with the grill in-context examples: the examples reach only the grill prompt, so each row
# takes its kitchen trials from the zero-shot run above and its grill trials from the ICL run.
CORE_K = [v for v in CORE if '.K' in v]
CORE_G = [v for v in CORE if '.G' in v]
ABLATIONS_ICL = [(label, zs, V2 / 'icl' / 'qwen3-vl-8b-thinking' if label == 'Full system'
                  else V2 / 'ablations_icl' / ('qwen3-8b-icl' if label == 'LLM planner' else zs.name))
                 for label, zs in ABLATIONS]
SCALE = [('4B', 'VLM', 'qwen3-vl-4b-thinking-fp8'), ('4B', 'LLM', 'qwen3-4b-fp8'), ('8B', 'VLM', 'qwen3-vl-8b-thinking-fp8'),
         ('8B', 'LLM', 'qwen3-8b-fp8'), ('32B', 'VLM', 'qwen3-vl-32b-thinking-fp8'), ('32B', 'LLM', 'qwen3-32b-fp8')]
REQUERY = ('plan_check_requery', 'corrective_requery', 'repeated_output_requery')


def trial_metrics(path: Path, variant: str) -> dict | None:
    events = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    end = next((e for e in events if e.get('event') == 'trial_end'), None)
    if end is None or end.get('termination_reason') == 'infrastructure':
        return None
    spec = get_final_variant(variant)
    expected_urgency, expected_if = dict(spec.expected_urgency or {}), dict(spec.expected_if or {})
    outcome = paper_outcome(end, variant)
    calls = [e for e in events if e.get('event') == 'planning_event']
    # replans started by a trigger, with their re-queries (the following calls until the next trigger / failure replan)
    groups, current = [], None
    for c in calls:
        reason = str(c.get('replan_reason') or '')
        if reason.startswith('trigger:'):
            current = {'first': c, 'requeries': [], 'parallel': None}
            groups.append(current)
        elif reason in REQUERY and current is not None:
            current['requeries'].append(c)
        else:
            current = None
    parallel = [e for e in events if e.get('event') == 'parallel']
    for g in groups:                         # a parallel event follows its trigger call
        g['parallel'] = next((p for p in parallel if p['seq'] > g['first']['seq']), None)
        if g['parallel'] is not None:
            parallel.remove(g['parallel'])
    idle = []
    for g in groups:
        first = g['parallel']['robot_idle_time_s'] if g['parallel'] is not None else float(g['first'].get('wall_latency_s') or 0.0)
        idle.append(float(first) + sum(float(r.get('wall_latency_s') or 0.0) for r in g['requeries']))
    unnecessary = sum(1 for g in groups
                      if g['first'].get('trigger_objects')
                      and all(expected_if.get(o) == 'ignore' for o in g['first']['trigger_objects']))
    # first-proposal urgency, per expected trigger object
    firsts = [e for e in events if e.get('event') == 'insertion' and e.get('first_proposal')]
    urg_hits = urg_total = 0
    for obj, want in expected_urgency.items():
        proposal = next((e for e in firsts if obj in json.dumps(e.get('corrective_sub_plans') or []) or obj in (e.get('urgency') or {})), None)
        if proposal is None and firsts:
            proposal = firsts[0]
        if proposal is None:
            continue                         # the object never triggered a corrective replan (e.g. -WHERE)
        urg_total += 1
        got = (proposal.get('urgency') or {}).get(obj)
        if got is None:
            got = next((sp.get('proposed_urgency') for sp in proposal.get('corrective_sub_plans') or [] if obj in (sp.get('objects') or [])), None)
        urg_hits += int(got == want)
    missing = ' '.join(end.get('missing') or [])
    too_late = any(e.get('event') == 'plan_check' and e.get('result') == 'fail' and 'insertion_too_late' in (e.get('failure_codes') or [])
                   for e in events)
    insertion_error = too_late or outcome['hc_violations'] > 0 or 'overcooked' in missing or 'before completing a cooking cycle' in missing
    return {'success': outcome['success'], 'pgc': outcome['pgc'], 'calls': int(end.get('planner_calls') or 0),
            'plan_s': float(end.get('planner_time_s') or 0.0), 'time_s': float(end.get('trial_time_s') or 0.0),
            'idle': idle, 'unnecessary': unnecessary, 'insertion_error': insertion_error,
            'urg_hits': urg_hits, 'urg_total': urg_total,
            'call_latencies': [float(c.get('planner_call_latency_s') or 0.0) for c in calls],
            'tokens': [c.get('completion_tokens') for c in calls if c.get('completion_tokens') is not None]}


def cell(run: Path, variants, *more) -> dict:
    """Metrics over the trials of ``variants`` in ``run`` (and of each further (run, variants) pair)."""
    trials = []
    for r, vs in ((run, variants),) + more:
        for v in vs:
            for p in sorted((r / v).glob('seed_*/trial_log.jsonl')):
                m = trial_metrics(p, v)
                if m:
                    trials.append(m)
    if not trials:
        return {'n': 0}
    mean = lambda xs: statistics.mean(xs) if xs else None  # noqa: E731
    idle = [x for t in trials for x in t['idle']]
    urg_total = sum(t['urg_total'] for t in trials)
    lat = [x for t in trials for x in t['call_latencies']]
    tok = [x for t in trials for x in t['tokens']]
    return {'n': len(trials), 'SR': mean([float(t['success']) for t in trials]), 'PGC': mean([t['pgc'] for t in trials]),
            'Calls': mean([t['calls'] for t in trials]), 'Plan': mean([t['plan_s'] for t in trials]),
            'Idle': mean(idle), 'Time': mean([t['time_s'] for t in trials]),
            'Urg': (sum(t['urg_hits'] for t in trials) / urg_total) if urg_total else None,
            'Unn': mean([t['unnecessary'] for t in trials]), 'Ins': mean([float(t['insertion_error']) for t in trials]),
            'lat_mean': mean(lat), 'lat_p50': statistics.median(lat) if lat else None,
            'lat_p90': sorted(lat)[int(0.9 * (len(lat) - 1))] if lat else None, 'lat_max': max(lat) if lat else None,
            'calls_total': len(lat), 'tok_mean': mean(tok)}


def pct(x):
    return '--' if x is None else f'{100 * x:.1f}'


def num(x, d=1):
    return '--' if x is None else f'{x:.{d}f}'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--out', default=str(ROOT / 'results' / 'table2'))
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ours, ceil = V2 / 'table2' / 'qwen3-vl-8b-thinking', ROOT / 'results' / 'gt_fixed' / 'full_system'
    md = ['# Table 4: main results (Qwen3-VL-8B-Thinking, full system, zero-shot)', '',
          '| Group | ID | Ceil. | SR | PGC | Calls | Plan. | Idle | Time | Urg. | trials |', '|---|---|---|---|---|---|---|---|---|---|---|']
    tex = ['% Table 4 value cells: Ceil. & SR & PGC & Calls & Plan. & Idle & Time & Urg.']
    rows = {}
    for group, variants in TABLE4_ORDER:
        for v in variants:
            c, g = cell(ours, [v]), cell(ceil, [v])
            rows[v] = c
            no_replan = not get_final_variant(v).expected_urgency
            idle = '–' if no_replan or c.get('Idle') is None else num(c.get('Idle'), 0)
            urg = '–' if no_replan else pct(c.get('Urg'))
            vals = [pct(g.get('SR')), pct(c.get('SR')), pct(c.get('PGC')), num(c.get('Calls')), num(c.get('Plan'), 0), idle,
                    num(c.get('Time'), 0), urg]
            md.append(f"| {group} | {v.replace('FINAL.', '')} | " + ' | '.join(vals) + f" | {c.get('n', 0)} |")
            tex.append(f"% {v}\n" + ' & '.join(vals))
    for label, vs in (('Mean (kitchen)', KITCHEN), ('Mean (grill)', GRILL), ('Mean (all)', KITCHEN + GRILL)):
        c, g = cell(ours, vs), cell(ceil, vs)
        vals = [pct(g.get('SR')), pct(c.get('SR')), pct(c.get('PGC')), num(c.get('Calls')), num(c.get('Plan'), 0),
                num(c.get('Idle'), 0), num(c.get('Time'), 0), pct(c.get('Urg'))]
        md.append(f'| | {label} | ' + ' | '.join(vals) + f" | {c.get('n', 0)} |")
        tex.append(f'% {label}\n' + ' & '.join(vals))
    md += ['', 'Ceil.: the oracle planner, full system (GT, same code). Idle and Urg. only for variants with an expected replan; '
           'means over all trials of the group.', '',
           '# Table 5: ablations (core variants K1-K4, G1-G3; 10 trials each)', '',
           '| Condition | SR (%) | Calls | Unn. | Ins. (%) | Idle | Time (s) | trials |', '|---|---|---|---|---|---|---|---|']
    tex.append('% Table 5 value cells: SR & Calls & Unn. & Ins. & Idle & Time')
    for label, run in ABLATIONS:
        c = cell(run, CORE)
        ins = '–' if label == '−WHERE' else pct(c.get('Ins'))
        vals = [pct(c.get('SR')), num(c.get('Calls')), num(c.get('Unn')), ins, num(c.get('Idle'), 0), num(c.get('Time'), 0)]
        md.append(f'| {label} | ' + ' | '.join(vals) + f" | {c.get('n', 0)}/70 |")
        tex.append(f'% {label}\n' + ' & '.join(vals))
    md += ['', '# Table 5 with the grill ICL (kitchen trials: zero-shot runs above; grill G1-G3: icl_mode examples_v2)', '',
           '| Condition | SR (%) | Calls | Unn. | Ins. (%) | Idle | Time (s) | SR grill (%) | trials |',
           '|---|---|---|---|---|---|---|---|---|']
    tex.append('% Table 5 with the grill ICL, value cells: SR & Calls & Unn. & Ins. & Idle & Time')
    for label, zs, icl in ABLATIONS_ICL:
        c, g = cell(zs, CORE_K, (icl, CORE_G)), cell(icl, CORE_G)
        ins = '–' if label == '−WHERE' else pct(c.get('Ins'))
        vals = [pct(c.get('SR')), num(c.get('Calls')), num(c.get('Unn')), ins, num(c.get('Idle'), 0), num(c.get('Time'), 0)]
        md.append(f'| {label} | ' + ' | '.join(vals) + f" | {pct(g.get('SR'))} | {c.get('n', 0)}/70 |")
        tex.append(f'% {label} (ICL)\n' + ' & '.join(vals))
    md += ['', '# Planner latency by scale (Qwen3 family, FP8, full system, zero-shot; all 14 variants)', '',
           '| Scale | Mod. | Model | Calls/trial | Plan. (s/trial) | Call latency mean | p50 | p90 | max (s) | Output tokens/call | SR | trials |',
           '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for scale, mod, alias in SCALE:
        c = cell(ROOT / 'results' / 'scale_runs' / alias, KITCHEN + GRILL)
        md.append(f"| {scale} | {mod} | {alias} | {num(c.get('Calls'))} | {num(c.get('Plan'), 0)} | {num(c.get('lat_mean'))} | "
                  f"{num(c.get('lat_p50'))} | {num(c.get('lat_p90'))} | {num(c.get('lat_max'))} | {num(c.get('tok_mean'), 0)} | "
                  f"{pct(c.get('SR'))} | {c.get('n', 0)}/140 |")
    md += ['', 'Call latency: one planner call, request to answer (s). All scales on the same GPU (RTX PRO 5000, 48 GB), '
           'vLLM 0.30.0, 6 trials at a time.']
    (out / 'paper_tables.md').write_text('\n'.join(md) + '\n')
    (out / 'paper_tables_cells.tex').write_text('\n'.join(tex) + '\n')
    print('\n'.join(md))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
