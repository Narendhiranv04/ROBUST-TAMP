"""Run seeded trials for many variants, a few at a time, and summarize them.

    # executor ceiling: ground-truth oracle planner, no model
    python -m llm_pipeline.run_trial_matrix --planner oracle --seeds 0-9 --out results/executor_ceiling
    # baseline: remote planner model
    python -m llm_pipeline.run_trial_matrix --planner model --seeds 0-9 --out results/baseline -- \\
        --model qwen3-vl-8b-thinking --model-type vlm --vision --remote --remote-url http://localhost:8000

Each trial is a separate process (``oracle_trial_runner`` or ``trial_runner``)
in its own working directory (pddlstream writes ``./temp``), at low priority
with one BLAS thread. Trial ``i`` of a variant uses seed ``i`` and writes
``<out>/<variant>/seed_<NN>/{record.json, trial_log.jsonl, prompts/}``. Finished
trials are skipped, so an interrupted matrix can be resumed. A trial that ends as
``infrastructure`` (planner server error or timeout, simulator crash, no ``trial_end``)
is rerun up to ``MAX_INFRASTRUCTURE_RERUNS`` times: the failed attempt is moved to
``seed_<NN>.infra_attempt<k>/`` (never scored) and logged in
``infrastructure_reruns.jsonl``; the new attempt logs ``attempt`` in ``trial_start``.
A refused real-model run (exit code 2: dirty tree or planner settings) is not rerun. ``summary.json``
and ``summary.md`` report per-variant task success rate and partial goal
completion (evaluation/metric_definitions.py) from the ``trial_end`` events.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.metric_definitions import summarize  # noqa: E402
from llm_pipeline.trial_log import read_trial_log, validate_trial_log  # noqa: E402

DEFAULT_VARIANTS = ['K1', 'K2', 'K3', 'G1', 'G2', 'G3']
MAX_INFRASTRUCTURE_RERUNS = 2
REFUSED_EXIT_CODE = 2


def parse_seeds(text: str) -> List[int]:
    seeds: List[int] = []
    for part in text.split(','):
        part = part.strip()
        if '-' in part:
            lo, hi = part.split('-', 1)
            seeds.extend(range(int(lo), int(hi) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def trial_dir(out: Path, variant: str, seed: int) -> Path:
    return out / variant / f'seed_{seed:02d}'


def _trial_end(directory: Path) -> Dict:
    path = directory / 'trial_log.jsonl'
    if not path.exists():
        return {}
    events = read_trial_log(path)
    return dict(events[-1]) if events and events[-1].get('event') == 'trial_end' else {}


def _is_infrastructure(end: Dict) -> bool:
    return not end or end.get('termination_reason') == 'infrastructure'


def _previous_attempts(directory: Path) -> List[Path]:
    return sorted(directory.parent.glob(f'{directory.name}.infra_attempt*'))


def run_one(planner: str, variant: str, seed: int, out: Path, extra: List[str], timeout_s: int) -> Dict:
    directory = trial_dir(out, variant, seed)
    end = _trial_end(directory)
    if end and not _is_infrastructure(end):
        return {'variant': variant, 'seed': seed, 'skipped': True}
    attempt = len(_previous_attempts(directory)) + 1
    result: Dict = {}
    while True:
        if directory.exists() and any(directory.iterdir()):
            # A finished infrastructure attempt (from this run or a resumed one): move it aside.
            aside = directory.parent / f'{directory.name}.infra_attempt{attempt}'
            directory.rename(aside)
            attempt += 1
        if attempt > MAX_INFRASTRUCTURE_RERUNS + 1:
            result['infrastructure_reruns_exhausted'] = True
            return result
        result = _run_attempt(planner, variant, seed, directory, extra, timeout_s, attempt)
        if result.get('exit_code') == REFUSED_EXIT_CODE or not result.get('infrastructure'):
            return result
        with open(out / 'infrastructure_reruns.jsonl', 'a', encoding='utf-8') as handle:
            handle.write(json.dumps({'variant': variant, 'seed': seed, 'attempt': attempt,
                                     'exit_code': result.get('exit_code'),
                                     'termination_reason': result.get('termination_reason'),
                                     'rerun': attempt <= MAX_INFRASTRUCTURE_RERUNS}) + '\n')
        if attempt > MAX_INFRASTRUCTURE_RERUNS:
            return result


def _run_attempt(planner: str, variant: str, seed: int, directory: Path, extra: List[str], timeout_s: int,
                 attempt: int) -> Dict:
    directory.mkdir(parents=True, exist_ok=True)
    if planner == 'oracle':
        command = [sys.executable, '-m', 'llm_pipeline.oracle_trial_runner', '--variant', variant,
                   '--seed', str(seed), '--output-dir', str(directory), '--attempt', str(attempt), *extra]
    else:
        command = [sys.executable, '-m', 'llm_pipeline.trial_runner', '--variant', variant, '--seed', str(seed),
                   '--trial-index', str(seed + 1), '--output-dir', str(directory), '--headless',
                   '--no-live-masks', '--no-goal-check', '--attempt', str(attempt), *extra]
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [env.get('PYTHONPATH', ''), str(ROOT_DIR)]))
    for var in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env[var] = '1'
    started = time.time()
    with open(directory / 'stdout.log', 'w') as log:
        try:
            code = subprocess.run(['nice', '-n', '10', *command], cwd=tempfile.mkdtemp(prefix=f'trial_{variant}_{seed}_'),
                                  env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout_s).returncode
        except subprocess.TimeoutExpired:
            code = 'timeout'
    end = _trial_end(directory)
    return {'variant': variant, 'seed': seed, 'attempt': attempt, 'exit_code': code,
            'seconds': round(time.time() - started, 1), 'success': end.get('success'),
            'termination_reason': end.get('termination_reason'),
            'infrastructure': code != REFUSED_EXIT_CODE and _is_infrastructure(end)}


def summarize_matrix(out: Path, variants: List[str], seeds: List[int]) -> Dict:
    rows = {}
    for variant in variants:
        ends, problems, missing = [], [], []
        for seed in seeds:
            directory = trial_dir(out, variant, seed)
            path = directory / 'trial_log.jsonl'
            if not path.exists():
                missing.append(seed)
                continue
            events = read_trial_log(path)
            issues = validate_trial_log(events)
            if issues:
                problems.append({'seed': seed, 'problems': issues[:3]})
            if events and events[-1].get('event') == 'trial_end':
                ends.append(events[-1])
            else:
                missing.append(seed)
        summary = summarize(ends)
        summary['missing_seeds'] = missing
        summary['log_problems'] = problems
        summary['infrastructure_reruns'] = sum(
            len(_previous_attempts(trial_dir(out, variant, seed))) for seed in seeds)
        summary['mean_planner_calls'] = (
            sum(int(e.get('planner_calls') or 0) for e in ends) / len(ends) if ends else None
        )
        summary['mean_trial_time_s'] = (
            sum(float(e.get('trial_time_s') or 0.0) for e in ends) / len(ends) if ends else None
        )
        reasons: Dict[str, int] = {}
        for e in ends:
            reasons[str(e.get('termination_reason'))] = reasons.get(str(e.get('termination_reason')), 0) + 1
        summary['termination_reasons'] = reasons
        rows[variant] = summary
    return rows


def write_summary(out: Path, rows: Dict, title: str) -> None:
    (out / 'summary.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')

    def fmt(value, pct=False):
        if value is None:
            return '-'
        return f'{100 * value:.0f}%' if pct else f'{value:.1f}'

    lines = [f'# {title}', '', '| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |',
             '|---|---|---|---|---|---|---|']
    for variant, row in rows.items():
        reasons = ', '.join(f'{k}: {v}' for k, v in sorted(row['termination_reasons'].items()))
        lines.append(
            f"| {variant} | {row['evaluated_trials']}/{row['trials'] + len(row['missing_seeds'])} | "
            f"{fmt(row['task_success_rate'], True)} ({row['successful_trials']}) | "
            f"{fmt(row['partial_goal_completion'], True)} | {fmt(row['mean_planner_calls'])} | "
            f"{fmt(row['mean_trial_time_s'])} | {reasons} |"
        )
    (out / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


def main() -> None:
    argv = sys.argv[1:]
    extra: List[str] = []
    if '--' in argv:
        index = argv.index('--')
        argv, extra = argv[:index], argv[index + 1:]
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--planner', choices=['oracle', 'model'], required=True)
    parser.add_argument('--variants', nargs='+', default=DEFAULT_VARIANTS)
    parser.add_argument('--seeds', default='0-9')
    parser.add_argument('--jobs', type=int, default=2, help='Parallel simulations (keep small)')
    parser.add_argument('--timeout', type=int, default=7200, help='Per-trial timeout in seconds')
    parser.add_argument('--out', required=True)
    parser.add_argument('--title', default='')
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    seeds = parse_seeds(args.seeds)
    tasks = [(variant, seed) for seed in seeds for variant in args.variants]
    print(f'[matrix] planner={args.planner} trials={len(tasks)} jobs={args.jobs} -> {out}', flush=True)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_one, args.planner, v, s, out, extra, args.timeout) for v, s in tasks]
        for future in futures:
            result = future.result()
            print(f'[matrix] {json.dumps(result)}', flush=True)
    rows = summarize_matrix(out, args.variants, seeds)
    write_summary(out, rows, args.title or f'{args.planner} planner, seeds {args.seeds}')


if __name__ == '__main__':
    main()
