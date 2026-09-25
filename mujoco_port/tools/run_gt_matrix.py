#!/usr/bin/env python3
"""Run the ground-truth action sequences for many variants/trials in parallel.

    python mujoco_port/tools/run_gt_matrix.py --variants K1 K2 K3 G1 G2 G3 --trials 3 --jobs 2

Each run is `llm_pipeline/debug_execution.py --variant V --headless` in its own
working directory (pddlstream/FastDownward write to ./temp, so parallel runs
must not share a cwd). Uses whatever backend the environment selects
(`SIM_BACKEND=mujoco` + shim on PYTHONPATH, or CoppeliaSim).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_one(variant: str, trial: int, out_dir: Path, timeout: int) -> dict:
    work = Path(tempfile.mkdtemp(prefix=f'gt_{variant}_{trial}_'))
    # debug_execution writes progress into its sequence files; use a private copy.
    import shutil
    seq_dir = work / 'debug_sequences'
    shutil.copytree(ROOT / 'llm_pipeline' / 'debug_sequences', seq_dir)
    log = out_dir / f'{variant}_trial{trial:02d}.log'
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join(filter(None, [env.get('PYTHONPATH', ''), str(ROOT)]))
    # One BLAS/OpenMP thread per simulation so parallel runs don't oversubscribe the CPU.
    for var in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        env[var] = '1'
    t0 = time.time()
    with open(log, 'w') as fh:
        try:
            proc = subprocess.run(
                ['nice', '-n', '10', sys.executable, '-u', str(ROOT / 'llm_pipeline' / 'debug_execution.py'),
                 '--variant', variant, '--headless', '--sequence-dir', str(seq_dir)],
                cwd=work, env=env, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = 'timeout'
    text = log.read_text(errors='replace')
    success = re.search(r'^Success: True', text, re.M) is not None
    failure = re.search(r'^Failure Message: (.*)$', text, re.M)
    return {
        'variant': variant,
        'trial': trial,
        'success': success,
        'exit_code': code,
        'bundles_completed': len(re.findall(r'bundle complete', text)),
        'failure': failure.group(1).strip() if failure else ('timeout' if code == 'timeout' else None),
        'seconds': round(time.time() - t0, 1),
        'log': str(log),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variants', nargs='+', default=['K1', 'K2', 'K3', 'G1', 'G2', 'G3'])
    ap.add_argument('--trials', type=int, default=1)
    ap.add_argument('--jobs', type=int, default=2,
                    help='Parallel simulations (keep small; each run is a full physics+render process)')
    ap.add_argument('--timeout', type=int, default=3600)
    ap.add_argument('--out', default=str(ROOT / 'mujoco_port' / 'results' / time.strftime('gt_%Y%m%d_%H%M%S')))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tasks = [(v, t) for t in range(1, args.trials + 1) for v in args.variants]
    backend = os.environ.get('SIM_BACKEND', 'coppelia')
    # Fail fast on a misconfigured environment instead of reporting N failures.
    check = subprocess.run(
        [sys.executable, '-c', 'import pddlstream.language.generator, pyrep; print(pyrep.__file__)'],
        cwd=tempfile.gettempdir(), capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': os.pathsep.join(filter(None, [os.environ.get('PYTHONPATH', ''), str(ROOT)]))})
    if check.returncode != 0:
        raise SystemExit(f'[gt-matrix] environment check failed (pddlstream / pyrep not importable):\n{check.stderr.strip()}')
    print(f'[gt-matrix] pyrep from {check.stdout.strip()}', flush=True)
    print(f'[gt-matrix] backend={backend} runs={len(tasks)} jobs={args.jobs} -> {out}', flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(run_one, v, t, out, args.timeout) for v, t in tasks]
        for f in futs:
            r = f.result()
            results.append(r)
            status = 'PASS' if r['success'] else f"FAIL ({r['failure']})"
            print(f"[gt-matrix] {r['variant']} trial {r['trial']}: {status} "
                  f"bundles={r['bundles_completed']} {r['seconds']}s", flush=True)
    summary = {}
    for v in args.variants:
        rs = [r for r in results if r['variant'] == v]
        summary[v] = {'passed': sum(r['success'] for r in rs), 'runs': len(rs)}
    (out / 'summary.json').write_text(json.dumps({'backend': backend, 'summary': summary, 'results': results}, indent=1))
    print('[gt-matrix] summary: ' + ', '.join(f"{v} {s['passed']}/{s['runs']}" for v, s in summary.items()), flush=True)


if __name__ == '__main__':
    main()
