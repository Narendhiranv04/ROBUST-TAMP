#!/usr/bin/env python3
"""Print a readable tree of an extracted scene bundle."""
import json, sys
from pathlib import Path
d = json.loads((Path(sys.argv[1]) / 'scene.json').read_text())
objs = {o['handle']: o for o in d['objects']}
kids = {}
for o in d['objects']:
    kids.setdefault(o['parent'], []).append(o['handle'])
def show(h, depth):
    o = objs[h]
    s = f"{'  '*depth}[{h}] {o['name']} <{o['type']}> w={[round(x,3) for x in o['world_pos']]}"
    if 'shape' in o:
        sh = o['shape']; gi = sh['geom_info']
        s += f" {'C' if gi['compound'] else ''}{'P%d'%gi['pure_type'] if gi['pure'] else ''}{'V' if gi['convex'] else ''} resp={int(sh['respondable'])} dyn={int(not sh['static'])} m={sh['mass_inertia']['mass'] if sh['mass_inertia'] else None:.3g} ncomp={len(sh.get('components',[]))} nviz={len(sh['viz'])} sp={o['special_property']} lay={o['visibility_layer']}"
    if 'joint' in o:
        j = o['joint']; s += f" jt={j['joint_type']} q={j['position']:.4f} int={[round(x,4) for x in j['interval']]} mode={j['mode']} f={j['max_force']} ctrl={j['ctrl_enabled']} mot={j['motor_enabled']}"
    if 'vision' in o:
        v = o['vision']; s += f" res={v['resolution']} fov={v['perspective_angle']} rm={v['render_mode']}"
    if 'proximity' in o:
        s += f" hits={o['proximity']['n_hits']}"
    print(s)
    for c in kids.get(h, []):
        show(c, depth + 1)
print('dt', d['dt'], 'gravity', d['gravity'], 'collections', {k: len(v) for k, v in d['collections'].items()})
for h in kids.get(-1, []):
    show(h, 0)
