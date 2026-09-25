#!/usr/bin/env python3
"""Record movable-object poses over N steps in the real CoppeliaSim (reference data)."""
import json, os, sys
import numpy as np
from pyrep import PyRep
from pyrep.objects.shape import Shape
scene = sys.argv[1]; steps = int(sys.argv[2]) if len(sys.argv) > 2 else 100
pr = PyRep(); pr.launch(os.path.abspath(scene), headless=True); pr.start()
names = [n for n in ('mug1','mug2','mug3','mug4','spam','soup','sugar','mustard','crackers','chicken','steak','steak1','plate','phone','box_lid','lid') if Shape.exists(n)]
traj = {n: [] for n in names}
for k in range(steps + 1):
    if k: pr.step()
    for n in names:
        traj[n].append(Shape(n).get_pose().tolist())
out = {'scene': scene, 'steps': steps, 'traj': traj}
path = sys.argv[3]
json.dump(out, open(path, 'w'))
for n in names:
    p0, p1 = np.array(traj[n][0][:3]), np.array(traj[n][-1][:3])
    print(f'{n:8s} moved {np.linalg.norm(p1-p0):.4f} {np.round(p1-p0,4)}')
os._exit(0)
