"""Integration checks for installed modules and relocated scientific resources."""
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

from robust_tamp.paths import ASSETS, CONFIGS, ROOT


def test_installed_entry_points_outside_checkout(tmp_path):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', SIM_BACKEND='mujoco')
    env.pop('PYTHONPATH', None)
    script = '''
from robust_tamp.__main__ import PRESETS
from evaluation.final_variants import SCENES_DIR
from baselines import vlm_tamp, owl_tamp, inner_monologue, epog
from vlm_pipeline.constraints.constraint_engine import load_domain_file
from llm_pipeline.trial_runner import git_commit_info
from pathlib import Path
assert len(list(SCENES_DIR.glob('final_*/scene.xml'))) >= 14
assert '(define' in load_domain_file()
assert 'no_where' in PRESETS
assert git_commit_info()['commit'].startswith('release-sha256:')
'''
    subprocess.run([sys.executable, '-c', script], cwd=tmp_path, env=env, check=True)
    subprocess.run([sys.executable, '-m', 'robust_tamp', '--help'], cwd=tmp_path, env=env, check=True, capture_output=True)


def test_all_retained_scene_models_compile():
    import mujoco
    scenes = sorted((ASSETS/'scenes').glob('*/scene.xml'))
    assert len(scenes) == 24
    for scene in scenes:
        model = mujoco.MjModel.from_xml_path(str(scene))
        assert model.nbody > 1
    from evaluation.check_final_variants import _composed_heights
    from evaluation.final_variants import FINAL_VARIANT_ORDER, get_final_variant
    for name in FINAL_VARIANT_ORDER:
        assert _composed_heights(get_final_variant(name))


def test_task_domains_and_trajectory_records():
    import json
    for family in ('kitchen', 'grill'):
        records = list((ASSETS/family/'precomputed_paths').glob('*.json'))
        assert records
        for record in records:
            data = json.loads(record.read_text())
            assert isinstance(data, dict) and data
    for name in ('kitchen/rlbench_kitchen_domain.pddl', 'kitchen/rlbench_kitchen_domain_constrained.pddl', 'kitchen/rlbench_kitchen_streams.pddl', 'grill/grill_task_domain.pddl', 'grill/grill_task_streams.pddl'):
        assert '(define' in (CONFIGS/'pddl'/name).read_text()
