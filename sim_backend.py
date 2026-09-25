"""Simulator backend selection for TAMP-PDDL.

Import this module before anything imports ``pyrep`` to choose the backend:

    SIM_BACKEND=mujoco   -> MuJoCo port (mujoco_port/shim provides a drop-in `pyrep`)
    SIM_BACKEND=coppelia -> original CoppeliaSim + PyRep (default when unset)

Entry points (debug_execution, trial_runner, run_10_trials_and_aggregate, ...)
import this first, so `SIM_BACKEND=mujoco python -m llm_pipeline.trial_runner ...`
runs the whole pipeline on MuJoCo with no other changes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SHIM_DIR = ROOT_DIR / 'mujoco_port' / 'shim'


def selected_backend() -> str:
    return os.environ.get('SIM_BACKEND', 'coppelia').strip().lower()


def activate(backend: str | None = None) -> str:
    backend = (backend or selected_backend()).lower()
    if backend in ('mujoco', 'mj'):
        os.environ['SIM_BACKEND'] = 'mujoco'
        loaded = sys.modules.get('pyrep')
        if loaded is not None and not getattr(loaded, '__file__', '').startswith(str(SHIM_DIR)):
            raise RuntimeError('pyrep (CoppeliaSim) was imported before sim_backend.activate("mujoco").')
        shim = str(SHIM_DIR)
        if shim not in sys.path:
            sys.path.insert(0, shim)
        # Child processes (e.g. per-variant subprocess runs) inherit the shim.
        pp = os.environ.get('PYTHONPATH', '')
        if shim not in pp.split(os.pathsep):
            os.environ['PYTHONPATH'] = shim + (os.pathsep + pp if pp else '')
        os.environ.setdefault('COPPELIASIM_ROOT', str(ROOT_DIR))
        return 'mujoco'
    return 'coppelia'


BACKEND = activate()
