"""Table 2 (planner selection) and Figures 4-5 from the per-model runs.

    python -m evaluation.table2 --results ~/robust_tamp_infer/real_trials/table2 [--extra DIR ...] --out results/table2

Each run directory is ``<results>/<profile alias>/`` (server/run_model_queue.sh). A run's numbers
come from its trial logs (evaluation/model_run_report.py), so a run still in progress is shown
with the trials done so far (the ``trials`` column says how many of 140).

Writes to ``--out``:
* ``table2a.csv`` / ``table2b.csv`` and ``table2.md``: SR_K, SR_G, SR, PGC (%), Plan. (mean
  planner time per trial, s), plus trials, calls, failure-triggered replans per trial;
* ``table2_rows.tex``: the value cells of each row (``SR_K & SR_G & SR & PGC & Plan.``), in the
  paper's row order, to paste into the table;
* ``fig4_scale_modality.pdf/.png``: per scale, mean planner time per trial (x) vs task success
  (y), marker = modality (circle LLM, triangle VLM), label = prompting, colour = total
  failure-triggered replans;
* ``fig5_failure_modes.pdf/.png``: share of structured failure events per run by category;
* ``failure_modes.csv``.

Failure-triggered replans: planner calls after the first whose reason is not a trigger (object
discovery / IF rule). Failure categories (each failure counted once: plan-check rejections and
failed ``action_end`` events):
* parser / interface: plan check, insertion and merge checks (the model output is rejected);
* execution / geometry: pre-action checks and motion-level execution failures (no IK, no plan,
  empty trajectory, ...);
* goal validation: post-execution checks (placement or grasp not verified), goal and evaluator checks;
* other: anything else.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from evaluation.model_run_report import FINAL_VARIANTS, build_report

# (a) Qwen3 family: scale x modality x prompting -> profile alias; all FP8, on the second server (ICL runs: <alias>-icl).
TABLE2A = [
    ('4B', 'LLM', 'ZS', 'qwen3-4b-fp8'), ('4B', 'LLM', 'ICL', 'qwen3-4b-fp8-icl'),
    ('4B', 'VLM', 'ZS', 'qwen3-vl-4b-thinking-fp8'), ('4B', 'VLM', 'ICL', 'qwen3-vl-4b-thinking-fp8-icl'),
    ('8B', 'LLM', 'ZS', 'qwen3-8b-fp8'), ('8B', 'LLM', 'ICL', 'qwen3-8b-fp8-icl'),
    ('8B', 'VLM', 'ZS', 'qwen3-vl-8b-thinking-fp8'), ('8B', 'VLM', 'ICL', 'qwen3-vl-8b-thinking-fp8-icl'),
    ('32B', 'LLM', 'ZS', 'qwen3-32b-fp8'), ('32B', 'LLM', 'ICL', 'qwen3-32b-fp8-icl'),
    ('32B', 'VLM', 'ZS', 'qwen3-vl-32b-thinking-fp8'), ('32B', 'VLM', 'ICL', 'qwen3-vl-32b-thinking-fp8-icl'),
]
# (b) 8B-class models, in the paper's order: (modality, reasoning, label, alias).
TABLE2B = [
    ('VLM', False, 'Qwen3-VL-8B-Instruct', 'qwen3-vl-8b-instruct'),
    ('VLM', False, 'Ministral-3-8B-Instruct', 'ministral-3-8b-instruct'),
    ('VLM', False, 'InternVL3.5-8B', 'internvl3.5-8b'),
    ('VLM', True, 'Qwen3-VL-8B-Thinking', 'qwen3-vl-8b-thinking'),
    ('VLM', True, 'Ministral-3-8B-Reasoning', 'ministral-3-8b-reasoning'),
    ('VLM', True, 'Holo2-8B', 'holo2-8b'),
    ('LLM', False, 'Qwen3-8B (think off)', 'qwen3-8b-nothink'),
    ('LLM', False, 'Llama-3.1-8B-Instruct', 'llama-3.1-8b-instruct'),
    ('LLM', False, 'Qwen2.5-7B-Instruct', 'qwen2.5-7b-instruct'),
    ('LLM', True, 'Qwen3-8B (think on)', 'qwen3-8b'),
    ('LLM', True, 'R1-Distill-Llama-8B', 'r1-distill-llama-8b'),
    ('LLM', True, 'R1-Distill-Qwen-7B', 'r1-distill-qwen-7b'),
]
TRIGGER_REASONS = ('trigger:discovery', 'trigger:if_rule', 'if_rule', 'discovery')
CATEGORIES = ('parser / interface', 'execution / geometry', 'goal validation', 'other')


def failure_category(code: str) -> str:
    from llm_pipeline.failures import FAILURE_CODE_INFO, FailureCheck, FailureCode

    try:
        info = FAILURE_CODE_INFO[FailureCode(code)]
    except (ValueError, KeyError):
        return 'other'
    if info.check in (FailureCheck.PLAN_CHECK, FailureCheck.INSERTION, FailureCheck.PARALLEL):
        return 'parser / interface'
    if info.check == FailureCheck.PRE_ACTION_CHECK or (info.check == FailureCheck.EXECUTION_FAILURE and info.legacy_layer == 'layer_1'):
        return 'execution / geometry'
    if info.check in (FailureCheck.EXECUTION_FAILURE, FailureCheck.GOAL_CHECK, FailureCheck.EVALUATION):
        return 'goal validation'
    return 'other'


def run_events(run_dir: Path):
    """Failure-triggered replans and failure categories over every trial of a run."""
    replans, categories = 0, Counter()
    for log in run_dir.glob('*/seed_*/trial_log.jsonl'):
        for line in log.read_text(encoding='utf-8').splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = e.get('event')
            if kind == 'planning_event' and e.get('kind') == 'replan':
                reason = str(e.get('replan_reason') or '')
                if not any(reason.startswith(t) for t in TRIGGER_REASONS):
                    replans += 1
            elif kind == 'plan_check' and e.get('result') == 'fail':
                for code in e.get('failure_codes') or []:
                    categories[failure_category(code)] += 1
            elif kind == 'action_end' and e.get('outcome') == 'failure' and e.get('failure_code'):
                categories[failure_category(e['failure_code'])] += 1
    return replans, categories


def summarize(run_dir: Path) -> dict | None:
    if not run_dir.is_dir():
        return None
    report = build_report(run_dir, FINAL_VARIANTS, list(range(10)))
    row = report['table2_row']
    if not row['trials']:
        return None
    replans, categories = run_events(run_dir)
    return dict(row, calls=report['overall']['mean_planner_calls'], failure_replans=replans,
                insertion_error_trials=row.get('insertion_error_trials'),
                failure_replans_per_trial=round(replans / row['trials'], 3), complete=report['complete'],
                categories=dict(categories))


def _fmt(v, pct=True):
    return '--' if v is None else (f'{100 * v:.1f}' if pct else f'{v:.0f}')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--results', required=True, help='directory with one run directory per profile alias')
    parser.add_argument('--extra', nargs='*', default=[], help='more result directories (e.g. the 32B server)')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    roots = [Path(args.results)] + [Path(p) for p in args.extra]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    def find(alias):
        for root in roots:
            s = summarize(root / alias)
            if s is not None:
                return s
        return None

    cache = {}
    summary = lambda alias: cache.setdefault(alias, find(alias))  # noqa: E731
    cols = ['SR_K', 'SR_G', 'SR', 'PGC', 'Plan_s', 'trials', 'calls', 'failure_replans_per_trial', 'insertion_error_trials', 'complete']
    md = ['# Table 2', '', '(a) Scale, modality, and prompting', '',
          '| Scale | Mod. | Prompt | SR_K | SR_G | SR | PGC | Plan. (s) | trials | calls | fail. replans/trial |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    tex = ['% (a) Scale, modality, and prompting: SR_K & SR_G & SR & PGC & Plan.']
    with open(out / 'table2a.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['scale', 'modality', 'prompt', 'alias'] + cols)
        for scale, mod, prompt, alias in TABLE2A:
            s = summary(alias) or {}
            w.writerow([scale, mod, prompt, alias] + [s.get(c) for c in cols])
            md.append(f"| {scale} | {mod} | {prompt} | {_fmt(s.get('SR_K'))} | {_fmt(s.get('SR_G'))} | {_fmt(s.get('SR'))} | "
                      f"{_fmt(s.get('PGC'))} | {_fmt(s.get('Plan_s'), False)} | {s.get('trials', 0)} | {s.get('calls') or '--'} | "
                      f"{s.get('failure_replans_per_trial', '--')} |")
            tex.append(f"% {scale} {mod} {prompt} ({alias})\n{_fmt(s.get('SR_K'))} & {_fmt(s.get('SR_G'))} & {_fmt(s.get('SR'))} & "
                       f"{_fmt(s.get('PGC'))} & {_fmt(s.get('Plan_s'), False)}")
    md += ['', '(b) 8B-class models', '',
           '| Mod. | Reas. | Model | SR_K | SR_G | SR | PGC | Plan. (s) | trials | calls | fail. replans/trial |',
           '|---|---|---|---|---|---|---|---|---|---|---|']
    tex.append('% (b) 8B-class models: SR_K & SR_G & SR & PGC & Plan.')
    with open(out / 'table2b.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['modality', 'reasoning', 'model', 'alias'] + cols)
        for mod, reas, label, alias in TABLE2B:
            s = summary(alias) or {}
            w.writerow([mod, reas, label, alias] + [s.get(c) for c in cols])
            md.append(f"| {mod} | {'yes' if reas else 'no'} | {label} | {_fmt(s.get('SR_K'))} | {_fmt(s.get('SR_G'))} | "
                      f"{_fmt(s.get('SR'))} | {_fmt(s.get('PGC'))} | {_fmt(s.get('Plan_s'), False)} | {s.get('trials', 0)} | "
                      f"{s.get('calls') or '--'} | {s.get('failure_replans_per_trial', '--')} |")
            tex.append(f"% {label} ({alias})\n{_fmt(s.get('SR_K'))} & {_fmt(s.get('SR_G'))} & {_fmt(s.get('SR'))} & "
                       f"{_fmt(s.get('PGC'))} & {_fmt(s.get('Plan_s'), False)}")
    md += ['', 'SR_K / SR_G: success over the 9 kitchen / 5 grill variants; SR, PGC over all 14 (10 trials each), with the '
           "paper's R and P conditions (evaluation/model_run_report.paper_outcome); insertion errors (ordering hard constraints "
           'violated) are counted separately in table2a/b.csv and do not change SR or PGC. Plan.: mean planner time per trial. '
           '`trials` < 140: run in progress or incomplete.']
    (out / 'table2.md').write_text('\n'.join(md) + '\n')
    (out / 'table2_rows.tex').write_text('\n'.join(tex) + '\n')

    # Failure modes (every run found).
    runs = [(alias, summary(alias)) for alias in dict.fromkeys([a for *_, a in TABLE2A] + [a for *_, a in TABLE2B])]
    runs = [(a, s) for a, s in runs if s]
    with open(out / 'failure_modes.csv', 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['alias', 'trials'] + list(CATEGORIES))
        for alias, s in runs:
            w.writerow([alias, s['trials']] + [s['categories'].get(c, 0) for c in CATEGORIES])
    _figures(out, summary, runs)
    print((out / 'table2.md').read_text())
    return 0


def _figures(out: Path, summary, runs) -> None:
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('matplotlib not available: figures skipped')
        return
    # Figure 4: per scale, planner time vs success; colour = failure-triggered replans.
    scales = ['4B', '8B', '32B']
    points = [(scale, mod, prompt, summary(alias)) for scale, mod, prompt, alias in TABLE2A]
    points = [p for p in points if p[3]]
    if points:
        vmax = max(p[3]['failure_replans'] for p in points) or 1
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.2), sharey=True)
        for ax, scale in zip(axes, scales):
            for _, mod, prompt, s in [p for p in points if p[0] == scale]:
                sc = ax.scatter(s['Plan_s'], 100 * s['SR'], c=[s['failure_replans']], cmap='Reds', vmin=0, vmax=vmax,
                                marker='o' if mod == 'LLM' else '^', s=140, edgecolors='k', linewidths=0.6)
                ax.annotate(prompt, (s['Plan_s'], 100 * s['SR']), textcoords='offset points', xytext=(7, 5), fontsize=8)
            ax.set_title(scale)
            ax.set_xlabel('Mean planner time per trial (s)')
            ax.grid(alpha=0.3)
        axes[0].set_ylabel('Task success (%)')
        axes[0].set_ylim(0, 105)
        fig.colorbar(plt.cm.ScalarMappable(cmap='Reds', norm=plt.Normalize(0, vmax)), ax=axes, label='Total failure-triggered replans')
        for ext in ('pdf', 'png'):
            fig.savefig(out / f'fig4_scale_modality.{ext}', dpi=200, bbox_inches='tight')
        plt.close(fig)
    # Figure 5: failure-event shares per run.
    if runs:
        colors = {'parser / interface': '#8e6bb8', 'execution / geometry': '#e8892b', 'goal validation': '#4a9a4a', 'other': '#9e9e9e'}
        fig, ax = plt.subplots(figsize=(9, 0.42 * len(runs) + 1.2))
        for i, (alias, s) in enumerate(runs):
            total = sum(s['categories'].values()) or 1
            left = 0.0
            for c in CATEGORIES:
                share = 100.0 * s['categories'].get(c, 0) / total
                ax.barh(i, share, left=left, color=colors[c], label=c if i == 0 else None)
                if share >= 8:
                    ax.text(left + share / 2, i, f'{share:.0f}', ha='center', va='center', fontsize=7, color='white')
                left += share
        ax.set_yticks(range(len(runs)))
        ax.set_yticklabels([a for a, _ in runs], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xlabel('Share of structured failure events (%)')
        ax.legend(ncol=4, fontsize=8, loc='upper center', bbox_to_anchor=(0.5, 1.12))
        for ext in ('pdf', 'png'):
            fig.savefig(out / f'fig5_failure_modes.{ext}', dpi=200, bbox_inches='tight')
        plt.close(fig)


if __name__ == '__main__':
    raise SystemExit(main())
