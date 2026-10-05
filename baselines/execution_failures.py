"""Unsuccessful trials of a baseline run in which an executed action failed.

Runs of server/run_baseline_comparison.sh before each trial had its own working directory shared
FastDownward's temp/ between the parallel trials. That can fail only an executed action (the motion
plan of an action reads another trial's problem, or the directory vanishes), so these are the trials
to re-run; a success, or a failure of the baseline's own planning, is unaffected.

    python3 -m baselines.execution_failures <run_dir>/<baseline>     prints "<variant> <seed>" lines
"""

import json
import sys
from pathlib import Path
from typing import List, Tuple


def execution_failed(events: List[dict]) -> bool:
    end = [e for e in events if e.get('event') == 'trial_end']
    if not end or end[-1].get('success'):
        return False
    trace = next((e for e in events if e.get('event') == 'baseline_trace'), {})
    if any(s.get('result') == 'failed' for r in trace.get('rounds', []) for s in r.get('subgoal_results', [])):
        return True                                             # VLM-TAMP: a subgoal's refinement failed
    execution = trace.get('execution')
    return isinstance(execution, dict) and not execution.get('success')     # OWL-TAMP: the open-loop plan


def execution_failures(run_dir: Path) -> List[Tuple[str, int]]:
    out = []
    for log in sorted(run_dir.glob('*/seed_[0-9][0-9]/trial_log.jsonl')):
        events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        if execution_failed(events):
            out.append((log.parent.parent.name, int(log.parent.name[5:])))
    return out


if __name__ == '__main__':
    for variant, seed in execution_failures(Path(sys.argv[1])):
        print(variant, seed)
