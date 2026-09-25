#!/usr/bin/env python3
"""Reference: which objects does Panda_gripper_attachProxSensor detect when placed inside it?"""
import os, sys, json
from pyrep import PyRep
from pyrep.objects.shape import Shape
from pyrep.objects.proximity_sensor import ProximitySensor
from pyrep.backend import sim
scene = sys.argv[1]
pr = PyRep(); pr.launch(os.path.abspath(scene), headless=True); pr.start()
sens = ProximitySensor('Panda_gripper_attachProxSensor')
out = {}
for n in ('mug1','mug2','mug3','spam','soup','sugar','chicken','steak','steak1','plate','phone','box_lid','lid','handle_visual','chicken_visual'):
    if not Shape.exists(n): continue
    s = Shape(n); pose = s.get_pose()
    s.set_position(sens.get_position())
    det = sens.is_detected(s)
    out[n] = {'detected': bool(det), 'sp': sim.simGetObjectSpecialProperty(s.get_handle())}
    s.set_pose(pose)
print(json.dumps(out))
os._exit(0)
