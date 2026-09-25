#!/usr/bin/env python3
"""Compare Panda tip poses in the MuJoCo scene against CoppeliaSim FK samples."""
import json, sys
import numpy as np
import mujoco
from pathlib import Path
from scipy.spatial.transform import Rotation as R

ROOT = Path(__file__).resolve().parents[2]
for name in sys.argv[1:]:
    d = ROOT / 'mujoco_port' / 'scenes' / name
    meta = json.loads((d / 'scene_meta.json').read_text())
    m = mujoco.MjModel.from_xml_path(str(d / 'scene.xml'))
    data = mujoco.MjData(m)
    jadr = [m.jnt_qposadr[m.joint(f'Panda_joint{i}').id] for i in range(1, 8)]
    tip = m.body('Panda_tip').id
    worst_p = worst_r = 0.0
    for s in meta['fk_samples']:
        data.qpos[:] = m.qpos0
        data.qpos[jadr] = s['q']
        mujoco.mj_kinematics(m, data)
        p = data.xpos[tip]
        q = data.xquat[tip]  # wxyz
        rq = R.from_quat([q[1], q[2], q[3], q[0]])
        ep = np.linalg.norm(p - s['tip_pos'])
        er = (rq.inv() * R.from_quat(s['tip_quat'])).magnitude()
        worst_p, worst_r = max(worst_p, ep), max(worst_r, er)
    print(f'{name}: {len(meta["fk_samples"])} samples, max pos err {worst_p*1000:.4f} mm, max rot err {np.degrees(worst_r):.4f} deg')
