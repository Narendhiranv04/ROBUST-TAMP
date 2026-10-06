"""After every successful place(o, r), the next observation must report o in region r.

    python -m evaluation.check_place_regions results/phase7b/ceiling results/phase7b/if_rule ...

Reads every ``trial_log.jsonl`` under the given directories and pairs each successful
``place`` action (``action_end`` with ``outcome = success``) with the next ``observation``
event. A mismatch means the region resolver and the executor disagree about where the
object is (e.g. a staging-area placement observed in the pantry area), which makes the
planner's state contradict its own completed actions. Objects that are not visible in
that observation are skipped (nothing was observed).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List

ROOT_DIR = Path(__file__).resolve().parents[2] / "src"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm_pipeline.region_aliases import normalize_region_name  # noqa: E402


def _place_args(action: str):
    name, _, rest = str(action).partition('(')
    if name.strip() != 'place':
        return None
    args = [arg.strip() for arg in rest.rstrip(')').split(',')]
    return (args[0], args[1]) if len(args) >= 2 else None


def check_trial(path: Path) -> Dict[str, object]:
    """Placements checked, mismatches (with step), variant of one trial log."""
    events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    variant = next((e.get('variant') for e in events if e.get('event') == 'trial_start'), None)
    pending, checked, mismatches = None, 0, []
    for event in events:
        kind = event.get('event')
        if kind == 'action_end' and event.get('outcome') == 'success':
            pending = _place_args(event.get('action', ''))
        elif kind == 'observation' and pending is not None:
            obj, target = pending
            pending = None
            observed = (event.get('object_regions') or {}).get(obj)
            if observed is None:
                continue
            checked += 1
            if normalize_region_name(observed) != normalize_region_name(target):
                mismatches.append({'step': event.get('step'), 'object': obj, 'target': target, 'observed': observed})
    return {'trial': str(path.parent), 'variant': variant, 'checked': checked, 'mismatches': mismatches}


def check_dirs(roots: Iterable[Path]) -> List[Dict[str, object]]:
    results = []
    for root in roots:
        for path in sorted(Path(root).rglob('trial_log.jsonl')):
            if '.infra_attempt' in str(path):
                continue
            results.append(check_trial(path))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('dirs', nargs='+')
    args = parser.parse_args()
    results = check_dirs(Path(d) for d in args.dirs)
    checked = sum(int(r['checked']) for r in results)
    bad = [m | {'trial': r['trial']} for r in results for m in r['mismatches']]
    by_target = Counter((m['target'], m['observed']) for m in bad)
    print(f'{len(results)} trials, {checked} placements checked, {len(bad)} mismatches')
    for (target, observed), count in by_target.most_common():
        print(f'  {count} x place(.., {target}) observed in {observed}')
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
