#!/usr/bin/env python3
"""Distance between two shapes at a given arm config / lid angle (runs on either backend)."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import sim_backend  # noqa
from pyrep import PyRep
from pyrep.robots.arms.panda import Panda
from pyrep.objects.shape import Shape
from pyrep.objects.joint import Joint
from pyrep.backend import sim
scene, q, lid_angle = sys.argv[1], json.loads(sys.argv[2]), float(sys.argv[3])
pairs = [p.split(':') for p in sys.argv[4:]]
pr = PyRep(); pr.launch(os.path.abspath(scene), headless=True)
arm = Panda(); arm.set_joint_positions(q)
Joint('lid_joint').set_joint_position(lid_angle)
for a, b in pairs:
    d = sim.simCheckDistance(Shape(a).get_handle(), Shape(b).get_handle(), -1)
    print(f'RESULT {a} {b} dist={d[6]:.5f} pa={[round(x,4) for x in d[:3]]}', flush=True)
print('RESULT tip', [round(x, 4) for x in arm.get_tip().get_position()], flush=True)
os._exit(0)
