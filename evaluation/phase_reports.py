"""Per-phase result tables for plan.md Phases 4-6 (Definition of Done runs).

    python -m evaluation.phase_reports phase4 results/phase4/if_rule --discovery results/phase3/oracle_ceiling
    python -m evaluation.phase_reports phase5 results/phase5/corrective_planner results/phase5/always_front ...
    python -m evaluation.phase_reports phase6 --on results/phase6/parallel_on --off results/phase6/parallel_off

Each writes ``report.md`` (and ``report.json``) into the first results directory
(phase 6: into the ``--on`` directory's parent), from the trial logs only.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from diagnostics.report import _expected_triggers, _observed_triggers, _urgency_accuracy  # noqa: E402
from evaluation.final_variants import FINAL_VARIANT_ORDER, get_final_variant  # noqa: E402
from llm_pipeline.trial_log import read_trial_log  # noqa: E402


def _trials(root: Path, seeds: Optional[Iterable[int]] = None) -> Dict[str, List[List[dict]]]:
    wanted = None if seeds is None else {f'seed_{s:02d}' for s in seeds}
    out: Dict[str, List[List[dict]]] = defaultdict(list)
    for log in sorted(Path(root).rglob('trial_log.jsonl')):
        if wanted is not None and log.parent.name not in wanted:
            continue
        events = read_trial_log(log)
        start = next((e for e in events if e.get('event') == 'trial_start'), {})
        out[str(start.get('variant'))].append(events)
    return out


def _end(events) -> dict:
    return next((e for e in reversed(events) if e.get('event') == 'trial_end'), {})


def _ordered(variants: Iterable[str]) -> List[str]:
    order = {f'FINAL.{name}': i for i, name in enumerate(FINAL_VARIANT_ORDER)}
    return sorted(variants, key=lambda v: (order.get(v, 99), v))


def _pct(values: Sequence[bool]) -> str:
    return f'{100.0 * sum(values) / len(values):.0f}%' if values else '—'


def _mean(values: Sequence[float], digits=1) -> str:
    return f'{statistics.mean(values):.{digits}f}' if values else '—'


def _table(header: Sequence[str], rows: Sequence[Sequence[object]]) -> List[str]:
    return ['| ' + ' | '.join(header) + ' |', '|' + '---|' * len(header)] + [
        '| ' + ' | '.join(str(c) for c in row) + ' |' for row in rows]


# ---------------------------------------------------------------- Phase 4
def _replans(events, code) -> List[dict]:
    return [e for e in events if e.get('event') == 'planning_event' and e.get('trigger_code') == code
            and not e.get('plan_check_requery')]


def phase4(if_root: Path, discovery_root: Optional[Path], seeds=(0, 1)) -> List[str]:
    lines = ['# Phase 4: IF rule', '',
             'Oracle planner (ground-truth actions for observed objects). "Triggers" counts replans caused by a',
             'trigger (`if_rule_trigger` / `new_object_discovered`); "trigger objects" lists them in order.',
             '"Expected" is the variant spec (docs/VARIANTS.md). Trigger accuracy: triggered objects match the spec',
             '(every non-ignored object triggered, no ignored object triggered).', '']
    modes = [('if_rule', if_root, 'if_rule_trigger')]
    if discovery_root is not None:
        modes.insert(0, ('discovery', discovery_root, 'new_object_discovered'))
    rows = []
    data = {mode: _trials(root, seeds) for mode, root, _ in modes}
    variants = _ordered({v for d in data.values() for v in d})
    for variant in variants:
        spec = get_final_variant(variant)
        expected = sorted(o for o, k in (spec.expected_if.items() if spec else ()) if k != 'ignore')
        for mode, _, code in modes:
            trials = data[mode].get(variant, [])
            if not trials:
                continue
            triggers = [_replans(t, code) for t in trials]
            objects = ['; '.join(','.join(e.get('trigger_objects') or []) for e in ts) or '—' for ts in triggers]
            match = []
            for t in trials:
                exp = _expected_triggers(variant)
                if exp is not None:
                    should, ignore = exp
                    observed = _observed_triggers(t)
                    match.append(should <= observed and not (observed & ignore))
            rows.append([variant, mode, len(trials), ' / '.join(str(len(ts)) for ts in triggers),
                         ' / '.join(sorted(set(objects))), ', '.join(expected) or 'none', _pct(match),
                         _pct([bool(_end(t).get('success')) for t in trials])])
    lines += _table(['Variant', 'Mode', 'Trials', 'Triggers per trial', 'Trigger objects', 'Expected', 'Trigger accuracy',
                     'Success'], rows)
    return lines


# ---------------------------------------------------------------- Phase 5
def phase5(roots: Sequence[Path]) -> List[str]:
    lines = ['# Phase 5: WHERE (corrective sub-plans, urgency, insertion)', '',
             'First-proposal urgency accuracy: the first corrective proposal of a trial vs the variant spec (objects',
             'correct / judged). Re-queries: rejected proposals (`insertion_too_late`, `invalid_corrective_block`).',
             'Hard-constraint and procedure failures come from the evaluator (`trial_end.missing`).', '']
    rows = []
    for root in roots:
        data = _trials(root)
        for variant in _ordered(data):
            trials = data[variant]
            correct = total = 0
            for t in trials:
                c, n = _urgency_accuracy(variant, t)
                correct += c or 0
                total += n or 0
            insertions = [e for t in trials for e in t if e.get('event') == 'insertion']
            rejected = [e for e in insertions if e.get('accepted') is False]
            codes = sorted({str(e.get('rejection_code')) for e in rejected})
            missing = sorted({m for t in trials for m in (_end(t).get('missing') or [])})
            flags = next((e.get('flags') for e in trials[0] if e.get('event') == 'trial_start'), {}) if trials else {}
            rows.append([root.name, variant, len(trials),
                         f'{correct}/{total}' if total else '—',
                         f'{len(rejected)}' + (f' ({", ".join(codes)})' if codes else ''),
                         _pct([bool(_end(t).get('success')) for t in trials]),
                         '; '.join(missing)[:160] or '—'])
    lines += _table(['Run', 'Variant', 'Trials', 'First-proposal urgency', 'Re-queries', 'Success', 'Unmet (evaluator)'],
                    rows)
    return lines


# ---------------------------------------------------------------- Phase 6
def _parallel_stats(trials) -> Dict[str, List[float]]:
    stats = defaultdict(list)
    for t in trials:
        par = [e for e in t if e.get('event') == 'parallel']
        planning = [e for e in t if e.get('event') == 'planning_event' and e.get('kind') == 'replan']
        stats['trial_time'].append(float(_end(t).get('trial_time_s') or 0.0))
        stats['success'].append(float(bool(_end(t).get('success'))))
        stats['replan_latency'].append(sum(float(e.get('wall_latency_s') or 0.0) for e in planning))
        if par:
            stats['idle'].append(sum(float(e.get('robot_idle_time_s') or 0.0) for e in par))
            stats['busy'].append(sum(float(e.get('robot_busy_time_s') or 0.0) for e in par))
            stats['available'].append(sum(len(e.get('independent_actions_available') or []) / 2 for e in par))
            stats['executed'].append(sum(len(e.get('independent_actions_executed') or []) / 2 for e in par))
            stats['conflict'].append(float(any(e.get('merge_result') == 'merge_conflict' for e in par)))
        else:
            # Parallel off: the robot is idle for the whole replan.
            stats['idle'].append(sum(float(e.get('wall_latency_s') or 0.0) for e in planning
                                     if e.get('trigger_code') == 'if_rule_trigger'))
    return stats


def phase6(on_root: Path, off_root: Path, out_dir: Path) -> List[str]:
    on, off = _trials(on_root), _trials(off_root)
    lines = ['# Phase 6: WHEN (parallel planning and execution)', '',
             'Oracle planner with a simulated 20 s planner latency per call. Idle time: planner latency not covered by',
             'executing independent bundles (parallel off: the whole replan latency). Independent bundles: available',
             '/ executed during the wait, summed over replans. Trial time from `trial_end.trial_time_s`.', '']
    rows, c2 = [], []
    for variant in _ordered(set(on) | set(off)):
        s_on, s_off = _parallel_stats(on.get(variant, [])), _parallel_stats(off.get(variant, []))
        rows.append([variant, len(on.get(variant, [])),
                     _mean(s_on['available']), _mean(s_on['executed']),
                     _mean(s_off['idle']), _mean(s_on['idle']),
                     _mean(s_off['trial_time']), _mean(s_on['trial_time']),
                     _pct([bool(x) for x in s_on['conflict']]),
                     _pct([bool(x) for x in s_off['success']]), _pct([bool(x) for x in s_on['success']])])
        name = variant.split('.', 1)[-1]
        if name in ('K1', 'K1-w1', 'K1-w2') and s_on['executed'] and s_off['idle']:
            w = {'K1': 0, 'K1-w1': 1, 'K1-w2': 2}[name]
            c2.append((w, statistics.mean(s_on['executed']), statistics.mean(s_off['idle']) - statistics.mean(s_on['idle']),
                       statistics.mean(s_off['trial_time']) - statistics.mean(s_on['trial_time'])))
    lines += _table(['Variant', 'Trials', 'Indep. bundles available', 'Indep. bundles executed', 'Idle s (off)',
                     'Idle s (on)', 'Trial s (off)', 'Trial s (on)', 'Merge conflicts (on)', 'Success (off)',
                     'Success (on)'], rows)
    if c2:
        lines += ['', '## C2 sweep (K1, K1-w1, K1-w2): idle time saved vs independent work', '']
        lines += _table(['w', 'Independent bundles executed', 'Idle time saved s', 'Trial time saved s'],
                        [[w, f'{e:.1f}', f'{s:.1f}', f'{t:.1f}'] for w, e, s, t in sorted(c2)])
        import matplotlib

        matplotlib.use('Agg')
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(5.5, 4))
        xs = [e for _, e, _, _ in sorted(c2)]
        ax.plot(xs, [s for _, _, s, _ in sorted(c2)], 'o-', label='robot idle time saved')
        ax.plot(xs, [t for _, _, _, t in sorted(c2)], 's--', label='trial time saved')
        for w, e, s, _ in sorted(c2):
            ax.annotate(f'w={w}', (e, s), textcoords='offset points', xytext=(5, 5))
        ax.set_xlabel('independent bundles executed during the replan')
        ax.set_ylabel('seconds (parallel off − on)')
        ax.set_title('C2 sweep: parallel planning and execution')
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(out_dir / 'c2_idle_time_saved.png', dpi=150)
        plt.close(fig)
        lines += ['', '![C2](c2_idle_time_saved.png)']
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('phase', choices=['phase4', 'phase5', 'phase6'])
    parser.add_argument('roots', nargs='*')
    parser.add_argument('--discovery')
    parser.add_argument('--on')
    parser.add_argument('--off')
    args = parser.parse_args()
    if args.phase == 'phase4':
        out = Path(args.roots[0]).parent
        lines = phase4(Path(args.roots[0]), Path(args.discovery) if args.discovery else None)
    elif args.phase == 'phase5':
        out = Path(args.roots[0]).parent
        lines = phase5([Path(r) for r in args.roots])
    else:
        out = Path(args.on).parent
        lines = phase6(Path(args.on), Path(args.off), out)
    (out / 'report.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
