"""The shim's resting-body sleep (MUJOCO_SHIM_SLEEP): mugs no longer creep, and a pushed or
teleported body still moves."""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'mujoco_port' / 'shim'))
mujoco = pytest.importorskip('mujoco')
try:
    from pyrep.backend import _world  # noqa: E402
except ImportError:  # another pyrep (CoppeliaSim) was imported first, e.g. by the pipeline tests
    pytest.skip('run `python -m pytest mujoco_port/tests` on its own', allow_module_level=True)

SCENE = ROOT / 'mujoco_port' / 'scenes' / 'final_K0'


def _world_with(sleep: bool):
    _world.SLEEP_RESTING = sleep
    world = _world.World(str(SCENE))
    world.running = True
    return world


def _body_xy(world, name):
    body = mujoco.mj_name2id(world.m, mujoco.mjtObj.mjOBJ_BODY, name)
    return np.array(world.d.xpos[body][:2])


def test_resting_mug_does_not_creep() -> None:
    drift = {}
    for sleep in (False, True):
        world = _world_with(sleep)
        start = _body_xy(world, 'mug1')
        for _ in range(1500):
            world.step()
        drift[sleep] = float(np.linalg.norm(_body_xy(world, 'mug1') - start))
    _world.SLEEP_RESTING = True
    assert drift[False] > 0.005          # MuJoCo alone: the mug creeps
    assert drift[True] < 0.001           # asleep: it stays


def test_sleeping_body_wakes_when_moved_from_outside() -> None:
    world = _world_with(True)
    for _ in range(50):
        world.step()
    joint = mujoco.mj_name2id(world.m, mujoco.mjtObj.mjOBJ_JOINT, 'mug1__free')
    qadr = world.m.jnt_qposadr[joint]
    world.d.qpos[qadr:qadr + 2] += 0.05     # teleport 5 cm, as set_pose does
    target = world.d.qpos[qadr:qadr + 2].copy()
    for _ in range(20):
        world.step()
    assert np.allclose(world.d.qpos[qadr:qadr + 2], target, atol=0.005)
