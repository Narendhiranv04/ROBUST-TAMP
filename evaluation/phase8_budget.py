"""Compute estimate for the Phase 8 run (plan.md 8.1) and a trimmed matrix for a time budget.

    # from smoke-test trial logs (planner latency, planner calls, simulator time per trial)
    python -m evaluation.phase8_budget --smoke results/phase1/smoke --budget-hours 72
    # or from assumed numbers
    python -m evaluation.phase8_budget --planner-call-s 90 --calls-per-trial 3 --sim-s 90 --budget-hours 72

Trial time = simulator time + planner calls x planner latency (the WHEN condition hides
part of the replan latency behind execution; the estimate ignores that, so it is an
upper bound). ``--parallel-sims`` trials run at once; the planner server is assumed to
serve them without queueing only if ``--server-concurrency`` is at least that number,
otherwise planner calls are serialized.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

FAMILY_AB = ['K0', 'G0', 'K1', 'K2', 'K3', 'K4', 'G1', 'G2', 'G3']
FAMILY_C1 = ['K3-n2', 'K3-n3', 'G1-n1']      # K3 and G1 are the n = 1 / n = 2 points, run in A/B
FAMILY_C2 = ['K1-w1', 'K1-w2']               # K1 is the w = 0 point
CONDITIONS = ['previous_system', 'full_system', 'ablation_if', 'ablation_where_front', 'ablation_where_end',
              'ablation_when', 'ablation_memory']
C1_CONDITIONS = {'full_system', 'ablation_where_front', 'ablation_where_end'}
C2_CONDITIONS = {'full_system', 'ablation_when'}


@dataclass
class Timing:
    planner_call_s: float
    calls_per_trial: float
    sim_s: float

    @property
    def trial_s(self) -> float:
        return self.sim_s + self.planner_call_s * self.calls_per_trial


def timing_from_smoke(root: Path) -> Tuple[Timing, List[Dict[str, object]]]:
    from llm_pipeline.trial_log import read_trial_log

    rows = []
    for log in sorted(Path(root).rglob('trial_log.jsonl')):
        events = read_trial_log(log)
        end = next((e for e in reversed(events) if e.get('event') == 'trial_end'), None)
        if end is None or end.get('termination_reason') == 'infrastructure':
            continue
        calls = [e for e in events if e.get('event') == 'planning_event']
        planner_s = sum(float(e.get('wall_latency_s') or 0.0) for e in calls)
        trial_s = float(end.get('trial_time_s') or 0.0)
        rows.append({'trial': str(log.parent), 'calls': len(calls), 'planner_s': round(planner_s, 1),
                     'trial_s': round(trial_s, 1), 'sim_s': round(max(0.0, trial_s - planner_s), 1),
                     'success': end.get('success')})
    if not rows:
        raise SystemExit(f'no finished trials under {root}')
    calls = [r['calls'] for r in rows]
    per_call = [r['planner_s'] / r['calls'] for r in rows if r['calls']]
    return Timing(statistics.mean(per_call), statistics.mean(calls), statistics.mean(r['sim_s'] for r in rows)), rows


def matrix(conditions: Sequence[str], trials_ab: int, trials_c: int) -> List[Tuple[str, str, int]]:
    cells = []
    for condition in conditions:
        cells += [(condition, v, trials_ab) for v in FAMILY_AB]
        if condition in C1_CONDITIONS:
            cells += [(condition, v, trials_c) for v in FAMILY_C1]
        if condition in C2_CONDITIONS:
            cells += [(condition, v, trials_c) for v in FAMILY_C2]
    return cells


def wall_hours(cells, timing: Timing, parallel_sims: int, server_concurrency: int) -> float:
    trials = sum(n for _, _, n in cells)
    lanes = max(1, parallel_sims)
    if server_concurrency >= lanes:
        return trials * timing.trial_s / lanes / 3600.0
    # Planner calls are serialized on the server; simulation overlaps across lanes.
    planner_total = trials * timing.planner_call_s * timing.calls_per_trial
    sim_total = trials * timing.sim_s / lanes
    return max(planner_total, sim_total) / 3600.0


PLANS = [
    ('full plan.md 8.1 (7 conditions incl. memory ablation, 10 trials)', CONDITIONS, 10, 10),
    ('without the optional memory ablation, 10 trials', CONDITIONS[:-1], 10, 10),
    ('no memory ablation; 10 trials A/B, 5 trials C1/C2', CONDITIONS[:-1], 10, 5),
    ('no memory ablation; 5 trials everywhere', CONDITIONS[:-1], 5, 5),
    ('full + previous + IF/WHERE-front/WHERE-end/WHEN ablations on A/B only, 5 trials', CONDITIONS[:-1], 5, 0),
    ('full + previous system only, 10 trials A/B, 5 trials C', ['previous_system', 'full_system'], 10, 5),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--smoke')
    parser.add_argument('--planner-call-s', type=float, default=90.0)
    parser.add_argument('--calls-per-trial', type=float, default=3.0)
    parser.add_argument('--sim-s', type=float, default=90.0)
    parser.add_argument('--parallel-sims', type=int, default=2)
    parser.add_argument('--server-concurrency', type=int, default=1)
    parser.add_argument('--budget-hours', type=float, default=72.0)
    parser.add_argument('--out')
    args = parser.parse_args()
    if args.smoke:
        timing, rows = timing_from_smoke(Path(args.smoke))
        source = f'smoke test ({len(rows)} trials, {args.smoke})'
    else:
        timing, rows = Timing(args.planner_call_s, args.calls_per_trial, args.sim_s), []
        source = 'assumed numbers'
    lines = ['# Phase 8 compute estimate', '',
             f'Source: {source}. Planner call {timing.planner_call_s:.0f} s, {timing.calls_per_trial:.1f} calls per trial, '
             f'simulator {timing.sim_s:.0f} s → {timing.trial_s / 60:.1f} min per trial. {args.parallel_sims} simulations '
             f'at once, server concurrency {args.server_concurrency}. Budget {args.budget_hours:.0f} h.', '',
             '| Matrix | Trials | Wall-clock h | Fits budget |', '|---|---|---|---|']
    best = None
    for name, conditions, n_ab, n_c in PLANS:
        cells = [c for c in matrix(conditions, n_ab, n_c) if c[2] > 0]
        hours = wall_hours(cells, timing, args.parallel_sims, args.server_concurrency)
        fits = hours <= args.budget_hours
        if fits and best is None:
            best = name
        lines.append(f'| {name} | {sum(n for *_, n in cells)} | {hours:.1f} | {"yes" if fits else "no"} |')
    lines += ['', f'Largest matrix that fits: {best or "none — reduce trials or conditions further"}.']
    if rows:
        lines += ['', '## Smoke-test trials', '', '| Trial | Planner calls | Planner s | Trial s | Success |',
                  '|---|---|---|---|---|']
        lines += [f'| {r["trial"]} | {r["calls"]} | {r["planner_s"]} | {r["trial_s"]} | {r["success"]} |' for r in rows]
    text = '\n'.join(lines) + '\n'
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == '__main__':
    main()
