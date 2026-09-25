#!/usr/bin/env python3
"""Run the first N GT actions of a variant through DirectPrimitiveExecutor (either backend).

    python mujoco_port/tools/run_partial.py K1 7
Prints one 'PARTIAL {json}' line with success, completed actions and failure.
"""
import json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(tempfile.mkdtemp(prefix='partial_'))  # pddlstream writes ./temp
import sim_backend  # noqa
from llm_pipeline import debug_execution as de
variant, n = sys.argv[1], int(sys.argv[2])
seq = de._load_default_sequence(variant, de.DEFAULT_SEQUENCE_DIR)
de._configure_scene_env(seq, headless=True)
env = de._load_env_for_sequence(seq)
from llm_pipeline.executor import DirectPrimitiveExecutor
ex = DirectPrimitiveExecutor(env=env)
ex.reset_episode()
r = ex.execute_actions(list(seq.actions[:n]), failure_checker=None,
                       pre_action_checks_enabled=False, post_action_checks_enabled=False)
print('PARTIAL ' + json.dumps({'variant': variant, 'n': n, 'success': bool(r.success),
                               'completed': len(r.completed_actions), 'error': r.error_message}), flush=True)
os._exit(0)
