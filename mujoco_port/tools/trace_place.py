#!/usr/bin/env python3
"""Trace an object's pose/contacts every step while running the first N GT actions (MuJoCo)."""
import json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(tempfile.mkdtemp(prefix='trace_'))
import sim_backend  # noqa
import numpy as np
from llm_pipeline import debug_execution as de
variant, n, obj_name, start_action = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
seq = de._load_default_sequence(variant, de.DEFAULT_SEQUENCE_DIR)
de._configure_scene_env(seq, headless=True)
env = de._load_env_for_sequence(seq)
from pyrep.objects.shape import Shape
from llm_pipeline.executor import DirectPrimitiveExecutor
obj = Shape(obj_name); pr = env.pr; w = pr._world; o = w.objs[obj.get_handle()]
ex = DirectPrimitiveExecutor(env=env); ex.reset_episode()
acts = list(seq.actions[:n])
r = ex.execute_actions(acts[:start_action], failure_checker=None, pre_action_checks_enabled=False, post_action_checks_enabled=False)
print('PRE', r.success, flush=True)
orig = pr.step; cnt = [0]; last = [None]
def step():
    orig(); cnt[0] += 1
    p = obj.get_position()
    mv = last[0] is None or np.linalg.norm(p - last[0]) > 0.003
    if mv or o.mode != getattr(step, 'mode', None):
        cons = sorted({(w.m.geom(w.d.contact[i].geom1).name.split('__')[0], w.m.geom(w.d.contact[i].geom2).name.split('__')[0], round(float(w.d.contact[i].dist), 4))
                       for i in range(w.d.ncon) if o.body in (w.m.geom_bodyid[w.d.contact[i].geom1], w.m.geom_bodyid[w.d.contact[i].geom2])})[:5]
        tip = env.robot.get_tip().get_position()
        print(f'[t] {cnt[0]} pos={np.round(p,3)} mode={o.mode} par={(obj.get_parent().get_name() if obj.get_parent() else None)} tip={np.round(tip,3)} fingers={np.round(env.gripper.get_open_amount(),2)} c={cons}', flush=True)
        last[0] = p.copy(); step.mode = o.mode
_prev_f = [None]
_inner = step
def step():
    _inner()
    f = np.array(env.gripper.get_open_amount())
    if _prev_f[0] is not None and np.max(np.abs(f - _prev_f[0])) > 0.05:
        fb = {w.objs[w.by_name[n]].body for n in ('Panda_leftfinger_respondable', 'Panda_rightfinger_respondable', 'Panda_leftfinger_force_contact', 'Panda_rightfinger_force_contact')}
        cons = sorted({(w.m.geom(w.d.contact[i].geom1).name.split('__')[0], w.m.geom(w.d.contact[i].geom2).name.split('__')[0], round(float(w.d.contact[i].dist), 4))
                       for i in range(w.d.ncon) if w.m.geom_bodyid[w.d.contact[i].geom1] in fb or w.m.geom_bodyid[w.d.contact[i].geom2] in fb})
        js = [w.objs[w.by_name[n]].jstate for n in ('Panda_gripper_joint1', 'Panda_gripper_joint2')]
        print(f'[f] {cnt[0]} fingers {np.round(_prev_f[0],2)}->{np.round(f,2)} tv={[j.target_vel for j in js]} stalled={[getattr(j,"stalled",False) for j in js]} ref={[round(j.lock_q,4) for j in js]} contacts={cons[:8]}', flush=True)
    _prev_f[0] = f
pr.step = step
_orig_grasp = env.gripper.grasp
def _grasp(target):
    import mujoco
    det = _orig_grasp(target)
    t = w.objs[target.get_handle()]
    sens = w.objs[w.by_name['Panda_gripper_attachProxSensor']]
    w._fresh()
    dmin = min(mujoco.mj_geomDistance(w.m, w.d, int(sens.vol_geom), int(g), 0.2, None) for g in t.col_geoms)
    print(f'[grasp] target={target.get_name()} detected={det} sensor_pos={np.round(w.obj_T(sens.handle)[:3,3],3)} '
          f'sensor_z={np.round(w.obj_T(sens.handle)[:3,2],3)} obj={np.round(target.get_position(),3)} min_vol_dist={dmin:.4f} '
          f'arm_q={np.round(env.get_robot_conf(),3)}', flush=True)
    return det
env.gripper.grasp = _grasp
r = ex.execute_actions(acts[start_action:], failure_checker=None, pre_action_checks_enabled=False, post_action_checks_enabled=False)
print('RESULT', r.success, r.error_message, flush=True)
os._exit(0)
