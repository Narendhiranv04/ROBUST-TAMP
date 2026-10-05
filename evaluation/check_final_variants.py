"""Automated build checks for the 15 final variants (plan.md Phase 3, docs/VARIANTS.md B6).

    python -m evaluation.check_final_variants                 # all, one process each, 2 at a time
    python -m evaluation.check_final_variants K1 G1-n3        # selected ones
    python -m evaluation.check_final_variants --one K1        # in this process (used by the above)

For each variant: the scene loads through the trial pipeline (oracle planner, no
model); every variant object exists; after settling, every object the variant
adds or moves stays within 1 cm of its composed height (nothing falls or sinks); no hidden object is visible
at the first observation; every hidden object starts in its region; its overlap
with the region's placement area matches the spec; and every visible object
starts outside the placement areas. Results go to ``results/phase3/checks/``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.final_variants import FINAL_VARIANT_ORDER, PLACEMENT_AREAS, get_final_variant  # noqa: E402

OUT_DIR = ROOT_DIR / 'results' / 'phase3' / 'checks'
MAX_SETTLE_DROP_M = 0.01


def _composed_heights(spec):
    scene = json.loads((ROOT_DIR / 'mujoco_port' / 'extracted' / spec.scene_dir.name / 'scene.json').read_text())
    by_name = {obj['name']: obj for obj in scene['objects']}
    return {scene_name: float(by_name[scene_name]['world_pos'][2]) for scene_name in spec.labels if scene_name in by_name}


def check_one(name: str) -> dict:
    from llm_pipeline import trial_runner
    from llm_pipeline.final_variant_setup import footprint_overlaps, world_aabb
    from llm_pipeline.flags import PipelineFlags
    from llm_pipeline.oracle_trial_runner import OraclePlanner
    from llm_pipeline.pipeline import LLMOnlyReplanningPipeline, LLMPipelineConfig
    from evaluation.canonical_variants import get_variant_spec

    spec = get_final_variant(name)
    vspec = get_variant_spec(spec.variant_id)
    trial_runner._repo_setup(headless=True, variant_spec=vspec)
    env = trial_runner._load_variant_env(vspec, goal_text=vspec.goal_text, headless=True)
    config = LLMPipelineConfig(model_alias='gt_oracle', headless=True, live_segmentation_view=False,
                               enable_goal_check=False, task_family=vspec.task_family, scene_path=vspec.scene_path,
                               variant_id=vspec.variant_id, flags=PipelineFlags(scene_randomization='off'))
    holder = {}
    pipeline = LLMOnlyReplanningPipeline(config=config, planner=OraclePlanner(list(spec.gt_actions),
                                                                                lambda: holder['p'].executor))
    holder['p'] = pipeline
    checks, problems = {}, []
    if not pipeline.initialize(env=env):
        return {'variant': name, 'ok': False, 'problems': ['pipeline initialize failed']}
    env = pipeline.env
    snapshot = pipeline.segmentation_adapter.capture_snapshot(event='check')
    visible = set(snapshot.visible_objects)
    gt = pipeline.initial_ground_truth or {}
    regions = gt.get('object_region_map', {})
    heights = _composed_heights(spec)
    hidden = {h.label: h for h in spec.hidden}
    edited = {e.name for e in spec.edits if e.op in ('move', 'copy')}
    for scene_name, label in sorted(spec.labels.items()):
        obj = env.get_object(scene_name)
        entry = {'scene_name': scene_name}
        if obj is None:
            problems.append(f'{label}: missing')
            checks[label] = entry
            continue
        pos = [round(float(v), 4) for v in obj.get_position()]
        low, high = world_aabb(obj)
        entry.update(position=pos, footprint_xy=[round(float(low[0]), 4), round(float(low[1]), 4),
                                                 round(float(high[0]), 4), round(float(high[1]), 4)],
                     region=regions.get(label), visible_at_start=label in visible)
        drop = heights.get(scene_name, pos[2]) - pos[2]
        entry['settle_drop_m'] = round(drop, 4)
        # Only objects the variant adds or moves; the rest is the base scene as validated by the old ceiling.
        if abs(drop) > MAX_SETTLE_DROP_M and scene_name in edited:
            problems.append(f'{label}: height changed by {drop:+.3f} m after settling')
        overlaps = {region: footprint_overlaps(obj, area) for region, area in PLACEMENT_AREAS[spec.scene].items()}
        entry['overlaps'] = overlaps
        if label in hidden:
            h = hidden[label]
            if label in visible:
                problems.append(f'{label}: hidden object visible at the first observation')
            if regions.get(label) != h.region:
                problems.append(f'{label}: starts in {regions.get(label)}, spec says {h.region}')
            if overlaps.get(h.region) != h.overlapping:
                problems.append(f'{label}: overlap {overlaps.get(h.region)}, spec says {h.overlapping}')
        elif any(overlaps.values()):
            problems.append(f'{label}: visible object starts in a placement area {overlaps}')
        checks[label] = entry
    result = {'variant': name, 'variant_id': spec.variant_id, 'ok': not problems, 'problems': problems,
              'visible_at_start': sorted(visible), 'objects': checks}
    return result


def _run_subprocess(name: str) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f'{name}.json'
    log = OUT_DIR / f'{name}.log'
    pddl = ROOT_DIR / 'pddlstream'
    envvars = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(ROOT_DIR), str(pddl)]), 'SIM_BACKEND': os.environ.get('SIM_BACKEND', 'mujoco'), 'OMP_NUM_THREADS': '1',
               'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
    with open(log, 'w') as handle:
        subprocess.run(['nice', '-n', '10', sys.executable, '-u', '-m', 'evaluation.check_final_variants',
                        '--one', name, '--out', str(out)], cwd=tempfile.mkdtemp(prefix=f'check_{name}_'), env=envvars, stdout=handle,
                       stderr=subprocess.STDOUT, timeout=900)
    if not out.exists():
        return {'variant': name, 'ok': False, 'problems': [f'no result; see {log}']}
    return json.loads(out.read_text())


def main() -> None:
    global OUT_DIR
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('variants', nargs='*')
    parser.add_argument('--one')
    parser.add_argument('--out', help='Result file for --one, or new result directory for a suite')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if args.one:
        result = check_one(args.one)
        Path(args.out).write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        sys.stdout.flush()
        os._exit(0)
    if args.out:
        OUT_DIR = Path(args.out).resolve()
    names = args.variants or FINAL_VARIANT_ORDER
    with ThreadPoolExecutor(max_workers=max(1, min(args.jobs, 2))) as pool:
        results = list(pool.map(_run_subprocess, names))
    summary = {r['variant']: {'ok': r['ok'], 'problems': r['problems']} for r in results}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'summary.json').write_text(json.dumps(summary, indent=2))
    for r in results:
        print(f"{r['variant']:7s} {'OK ' if r['ok'] else 'FAIL'} {'; '.join(r['problems'])}")
    sys.exit(0 if all(r['ok'] for r in results) else 1)


if __name__ == '__main__':
    main()
