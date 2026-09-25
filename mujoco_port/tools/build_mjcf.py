#!/usr/bin/env python3
"""Convert an extracted CoppeliaSim scene bundle into a MuJoCo MJCF scene.

    python mujoco_port/tools/build_mjcf.py task1_variation1       # one scene
    python mujoco_port/tools/build_mjcf.py --all                  # every bundle

Reads   mujoco_port/extracted/<scene>/{scene.json, geometry.npz, textures/}
Writes  mujoco_port/scenes/<scene>/{scene.xml, scene_meta.json, meshes/, textures/}

Object mapping (CoppeliaSim -> MuJoCo)
  * Every CoppeliaSim object becomes an MJCF body with the same name, so
    poses of shapes, dummies, joints and sensors can all be queried.
  * Robot tree and scene-joint trees are nested exactly as in CoppeliaSim;
    each joint object becomes a body carrying a hinge/slide along its local z,
    with ``ref`` equal to the scene joint value.
  * Movable task objects (mugs, groceries, meats, plate, phone, ...) become
    free bodies; their static children (visuals, grasp points, waypoints,
    sensors) are nested inside them.
  * Everything else is a static body welded to the world at its world pose.
  * Collision geometry comes from CoppeliaSim's respondable/collidable shapes
    (pure primitives map to exact MuJoCo primitives, convex meshes to meshes,
    compounds to one geom per component, concave respondables to V-HACD
    hulls). Visuals come from the renderable shapes' viz meshes + textures.

The sidecar ``scene_meta.json`` keeps CoppeliaSim handles, the logical
parent tree, dynamics/visibility flags, joint modes, sensor parameters and
the geom lists per object; the MuJoCo PyRep shim is driven entirely by it.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from pathlib import Path
from xml.sax.saxutils import quoteattr

import numpy as np
from scipy.spatial.transform import Rotation as R

ROOT = Path(__file__).resolve().parents[2]
EXTRACTED = ROOT / 'mujoco_port' / 'extracted'
SCENES = ROOT / 'mujoco_port' / 'scenes'

ROBOT_ROOT = 'Panda'
ARM_JOINTS = [f'Panda_joint{i}' for i in range(1, 8)]
GRIPPER_JOINTS = ['Panda_gripper_joint1', 'Panda_gripper_joint2']

# Task objects that the GT/LLM executors pick, carry, re-parent or drop.
MOVABLE_PATTERNS = [
    r'^mug\d*$',
    r'^(spam|soup|sugar|mustard|crackers|tuna|coffee|strawberry_jello|chocolate_jello)$',
    r'^(steak|chicken)\d*$',
    r'^plate$',
    r'^phone$',
]
# Dynamic shapes hanging on passive scene joints that the GT grasps (and so
# re-parents onto the gripper). They become free bodies whose hinge to the
# joint is emulated with runtime-reconfigurable constraints.
DETACHABLE_JOINT_CHILDREN = {'box_lid'}
# Static shapes that the GT re-parents at runtime (e.g. grill handle grasp).
REPARENTABLE_EXTRAS = {'handle_visual'}
# Marker shapes that are drawn by CoppeliaSim but carry no scene content; they are
# not rendered (cameras, segmentation, viewer). Their collision geometry is kept.
HIDDEN_FROM_CAMERAS = {'plate_target'}

# CoppeliaSim constants
SP_COLLIDABLE = 1
SP_RENDERABLE = 512
JOINT_REVOLUTE = 10
JOINT_PRISMATIC = 11
JOINT_SPHERICAL = 12
PURE_PLANE, PURE_DISC, PURE_CUBOID, PURE_SPHEROID, PURE_CYLINDER, PURE_CONE = 1, 2, 3, 4, 5, 6

# Contact bitmasks: robot geoms never collide with each other.
ROBOT_CONTYPE, ROBOT_CONAFF = 2, 1
WORLD_CONTYPE, WORLD_CONAFF = 1, 3

MIN_MASS = 0.01
ROBOT_SOLREF = '0.004 1'
ROBOT_SOLIMP = '0.95 0.99 0.001'
MIN_INERTIA = 1e-6


def fmt(v, prec=7):
    return ' '.join(f'{float(x):.{prec}g}' for x in v)


def quat_xyzw_to_wxyz(q):
    return [q[3], q[0], q[1], q[2]]


def pose_matrix(pos, quat_xyzw):
    T = np.eye(4)
    T[:3, :3] = R.from_quat(quat_xyzw).as_matrix()
    T[:3, 3] = pos
    return T


def matrix_to_pos_quat(T):
    q = R.from_matrix(T[:3, :3]).as_quat()  # xyzw
    return T[:3, 3].tolist(), q.tolist()


class SceneBuilder:
    def __init__(self, scene_name: str):
        self.name = scene_name
        self.src = EXTRACTED / scene_name
        self.out = SCENES / scene_name
        self.scene = json.loads((self.src / 'scene.json').read_text())
        self.geo = np.load(self.src / 'geometry.npz')
        self.objs = {o['handle']: o for o in self.scene['objects']}
        self.by_name = {o['name']: o for o in self.scene['objects']}
        self.children = {}
        for o in self.scene['objects']:
            self.children.setdefault(o['parent'], []).append(o['handle'])
        self.mesh_assets = []      # xml lines
        self.texture_assets = {}   # png name -> texture/material names
        self.mesh_hashes = {}
        self.meta_objects = {}
        self.geom_count = 0
        self.warnings = []

    # ------------------------------------------------------------------ classify
    def subtree(self, h):
        out = [h]
        for c in self.children.get(h, []):
            out.extend(self.subtree(c))
        return out

    def ancestors(self, h):
        out = []
        p = self.objs[h]['parent']
        while p >= 0:
            out.append(p)
            p = self.objs[p]['parent']
        return out

    def is_movable_root(self, o):
        if o['type'] != 'shape':
            return False
        if o['handle'] in self.robot_set:
            return False
        name = o['name']
        if name in DETACHABLE_JOINT_CHILDREN or name in REPARENTABLE_EXTRAS:
            return True
        under_joint = any(self.objs[a]['type'] == 'joint' for a in self.ancestors(o['handle']))
        if under_joint:
            return False
        if any(re.match(p, name) for p in MOVABLE_PATTERNS):
            return True
        # Anything dynamic at scene start that is free of joints.
        return not o['shape']['static'] and o['shape']['respondable']

    def classify(self):
        robot = self.by_name.get(ROBOT_ROOT)
        self.robot_set = set(self.subtree(robot['handle'])) if robot else set()
        self.kind = {}
        self.phys_parent = {}
        movable_roots = {h for h, o in self.objs.items() if self.is_movable_root(o)}
        self.movable_roots = movable_roots

        def assign(h, inherited):
            o = self.objs[h]
            if h in self.robot_set:
                kind = 'robot'
            elif h in movable_roots:
                kind = 'movable'
            elif inherited in ('movable', 'movable_child'):
                kind = 'movable_child'
            elif o['type'] == 'joint' or inherited == 'joint_chain':
                kind = 'joint_chain'
            else:
                kind = 'fixture'
            self.kind[h] = kind
            for c in self.children.get(h, []):
                assign(c, kind)

        for h in self.children.get(-1, []):
            assign(h, None)

        for h, o in self.objs.items():
            k = self.kind[h]
            p = o['parent']
            if k == 'movable' or k == 'fixture':
                self.phys_parent[h] = -1
            elif k == 'robot':
                self.phys_parent[h] = p if p in self.robot_set else -1
            elif k == 'movable_child':
                self.phys_parent[h] = p
            elif k == 'joint_chain':
                # Nest under the parent only if the parent is also part of
                # the same joint chain; the chain root hangs off the world.
                self.phys_parent[h] = p if (p >= 0 and self.kind.get(p) == 'joint_chain') else -1
        # Detachable joint children hang off their joint logically, but are
        # physically free bodies.
        for h in movable_roots:
            self.phys_parent[h] = -1
        self.emulated_joints = {
            h for h, o in self.objs.items()
            if o['type'] == 'joint' and self.children.get(h)
            and all(self.objs[c]['name'] in DETACHABLE_JOINT_CHILDREN for c in self.children[h])
        }

    # ------------------------------------------------------------------ geometry
    def world_T(self, h):
        o = self.objs[h]
        return pose_matrix(o['world_pos'], o['world_quat'])

    def body_T(self, h):
        """Frame of the MJCF body for object h at scene configuration."""
        return self.world_T(h)

    def add_mesh(self, verts, faces, tex_coords=None, key_hint='m'):
        verts = np.asarray(verts, dtype=np.float64)
        faces = np.asarray(faces, dtype=np.int64)
        if len(verts) < 4 or len(faces) < 1:
            return None
        h = hash((verts.round(6).tobytes(), faces.tobytes(), None if tex_coords is None else np.asarray(tex_coords).round(5).tobytes()))
        if h in self.mesh_hashes:
            return self.mesh_hashes[h]
        mname = f'{key_hint}_{len(self.mesh_hashes)}'
        path = self.out / 'meshes' / f'{mname}.obj'
        lines = [f'v {x:.7g} {y:.7g} {z:.7g}' for x, y, z in verts]
        if tex_coords is not None:
            tc = np.asarray(tex_coords, dtype=np.float64).reshape(-1, 2)
            lines += [f'vt {u:.6g} {v:.6g}' for u, v in tc]
            for k, (a, b, c) in enumerate(faces):
                t = 3 * k
                lines.append(f'f {a+1}/{t+1} {b+1}/{t+2} {c+1}/{t+3}')
        else:
            lines += [f'f {a+1} {b+1} {c+1}' for a, b, c in faces]
        path.write_text('\n'.join(lines) + '\n')
        self.mesh_assets.append(f'<mesh name="{mname}" file="meshes/{mname}.obj" inertia="shell"/>')
        self.mesh_hashes[h] = mname
        return mname

    def material_for_texture(self, png):
        if png in self.texture_assets:
            return self.texture_assets[png]
        tname = f'tex_{len(self.texture_assets)}'
        shutil.copy(self.src / 'textures' / png, self.out / 'textures' / png)
        self.mesh_assets.append(f'<texture name="{tname}" type="2d" file="textures/{png}"/>')
        # Textured surfaces (floor, table, walls, labels) are matte.
        self.mesh_assets.append(f'<material name="mat_{tname}" texture="{tname}" rgba="1 1 1 1" '
                                f'specular="0.15" shininess="0.25"/>')
        self.texture_assets[png] = f'mat_{tname}'
        return self.texture_assets[png]

    def primitive_geom(self, gi, verts):
        """Return (type, size, center) for a pure primitive fitted to its mesh, or None."""
        if not gi['pure'] or len(verts) == 0:
            return None
        mn, mx = verts.min(0), verts.max(0)
        ext = mx - mn
        center = (mn + mx) / 2
        pt = gi['pure_type']
        dims = np.array(gi['dims'][:3])
        if pt == PURE_CUBOID:
            if np.allclose(np.sort(ext), np.sort(dims), atol=2e-3, rtol=2e-2):
                return 'box', ext / 2, center
            return None
        if pt in (PURE_PLANE, PURE_DISC):
            half = ext / 2
            half[2] = max(half[2], 0.0005)
            return 'box', half, center
        if pt == PURE_SPHEROID:
            if np.allclose(ext, ext[0], rtol=1e-3):
                return 'sphere', [ext[0] / 2], center
            return 'ellipsoid', ext / 2, center
        if pt == PURE_CYLINDER:
            if abs(ext[0] - ext[1]) < 2e-3:
                return 'cylinder', [ext[0] / 2, ext[2] / 2], center
            return None
        return None

    def collision_geoms(self, o, contype, conaff, group=3):
        """Geoms reproducing a shape's collision geometry, in the shape frame."""
        sh = o['shape']
        parts = []
        comps = sh.get('components') or []
        if comps and (sh['geom_info']['compound'] or sh.get('decomposed')):
            for c in comps:
                v = self.geo[c['mesh']['vertices']]
                f = self.geo[c['mesh']['indices']]
                T = pose_matrix(c['local_pos'], c['local_quat'])
                parts.append((c['geom_info'], v, f, T))
        else:
            v = self.geo[sh['mesh']['vertices']]
            f = self.geo[sh['mesh']['indices']]
            parts.append((sh['geom_info'], v, f, np.eye(4)))
        out = []
        for gi, v, f, T in parts:
            prim = self.primitive_geom(gi, v)
            if prim is not None:
                gtype, size, center = prim
                Tg = T @ pose_matrix(center, [0, 0, 0, 1])
                pos, quat = matrix_to_pos_quat(Tg)
                out.append(dict(type=gtype, size=size, pos=pos, quat=quat))
            else:
                if not gi['convex'] and not gi['pure'] and sh['respondable'] and not sh.get('decomposed'):
                    self.warnings.append(f"{o['name']}: concave collision mesh approximated by convex hull")
                mname = self.add_mesh(v, f, key_hint='col')
                if mname is None:
                    continue
                pos, quat = matrix_to_pos_quat(T)
                out.append(dict(type='mesh', mesh=mname, pos=pos, quat=quat))
        for g in out:
            g.update(contype=contype, conaffinity=conaff, group=group)
        return out

    def visual_geoms(self, o, group):
        sh = o['shape']
        out = []
        # CoppeliaSim reports a transparency factor (default 0.5) even when
        # transparency is disabled, so shapes are rendered opaque.
        alpha = 1.0
        planes = [self._viz_plane(viz) for viz in sh['viz']]
        for i, viz in enumerate(sh['viz']):
            v = self.geo[viz['vertices']]
            f = self.geo[viz['indices']]
            tex = viz.get('texture')
            # A flat untextured part lying in the plane of a textured part (the
            # floor's black backing quad) only z-fights with it; CoppeliaSim
            # draws the textured part on top.
            if not tex and planes[i] is not None and any(
                    j != i and other.get('texture') and planes[j] is not None
                    and np.allclose(planes[i], planes[j], atol=1e-4)
                    for j, other in enumerate(sh['viz'])):
                continue
            tc = self.geo[viz['tex_coords']] if (tex and viz.get('tex_coords')) else None
            mname = self.add_mesh(v, f, tex_coords=tc, key_hint='vis')
            if mname is None:
                continue
            col = viz['colors'][:3] if viz.get('colors') else (sh.get('color') or [0.7, 0.7, 0.7])
            g = dict(type='mesh', mesh=mname, pos=[0, 0, 0], quat=[0, 0, 0, 1],
                     contype=0, conaffinity=0, group=group, rgba=list(col) + [alpha])
            if tc is not None:
                g['material'] = self.material_for_texture(tex)
                g['rgba'] = [1, 1, 1, alpha]
            out.append(g)
        return out

    def _viz_plane(self, viz):
        """(normal, offset) if the viz mesh is flat, else None."""
        v = self.geo[viz['vertices']].reshape(-1, 3).astype(float)
        if len(v) < 3:
            return None
        c = v.mean(0)
        _, s, vt = np.linalg.svd(v - c, full_matrices=False)
        if s[-1] > 1e-5 * max(s[0], 1e-9):
            return None
        n = vt[-1] * (1 if vt[-1][np.argmax(np.abs(vt[-1]))] > 0 else -1)
        return np.concatenate([n, [n @ c]])

    # ------------------------------------------------------------------ xml
    def geom_xml(self, name, g):
        attrs = [f'name="{name}"', f'type="{g["type"]}"']
        if g['type'] == 'mesh':
            attrs.append(f'mesh="{g["mesh"]}"')
        else:
            attrs.append(f'size="{fmt(g["size"])}"')
        attrs.append(f'pos="{fmt(g["pos"])}"')
        attrs.append(f'quat="{fmt(quat_xyzw_to_wxyz(g["quat"]))}"')
        attrs.append(f'contype="{g["contype"]}" conaffinity="{g["conaffinity"]}" group="{g["group"]}"')
        if 'material' in g:
            attrs.append(f'material="{g["material"]}"')
        if 'rgba' in g:
            attrs.append(f'rgba="{fmt(g["rgba"], 4)}"')
        else:
            attrs.append('rgba="0.5 0.5 0.5 0.3"')
        if g.get('condim'):
            attrs.append(f'condim="{g["condim"]}"')
        if g.get('robot'):
            # CoppeliaSim teleports the arm (set_joint_positions resets link
            # dynamics), so arm contacts only correct penetration weakly.
            attrs.append(f'solref="{ROBOT_SOLREF}" solimp="{ROBOT_SOLIMP}" solmix="100"')
        return f'<geom {" ".join(attrs)}/>'

    def inertial_xml(self, o, fallback_mass=1e-3):
        mi = (o.get('shape') or {}).get('mass_inertia') if o['type'] == 'shape' else None
        if mi is None:
            return f'<inertial pos="0 0 0" mass="{fallback_mass}" diaginertia="{fmt([1e-7]*3)}"/>'
        mass = max(float(mi['mass']), MIN_MASS)
        I = np.array(mi['inertia'], dtype=float).reshape(3, 3)
        I = 0.5 * (I + I.T)
        # CoppeliaSim returns mass-normalised inertia when massless; scale if tiny.
        w, V = np.linalg.eigh(I)
        if np.linalg.det(V) < 0:
            V[:, 0] = -V[:, 0]
        w = np.maximum(np.abs(w), MIN_INERTIA)
        # Keep the triangle inequality valid for MuJoCo.
        w = np.sort(w)
        if w[0] + w[1] < w[2]:
            w[2] = w[0] + w[1]
        q = R.from_matrix(V).as_quat()
        com = mi['com']
        return (f'<inertial pos="{fmt(com)}" quat="{fmt(quat_xyzw_to_wxyz(q))}" '
                f'mass="{mass:.6g}" diaginertia="{fmt(w)}"/>')

    def build_body(self, h, parent_T, lines, indent):
        o = self.objs[h]
        kind = self.kind[h]
        T = self.body_T(h)
        rel = np.linalg.inv(parent_T) @ T
        pos, quat = matrix_to_pos_quat(rel)
        pad = '  ' * indent
        grav = ' gravcomp="1"' if kind == 'robot' else ''
        lines.append(f'{pad}<body name={quoteattr(o["name"])} pos="{fmt(pos)}" quat="{fmt(quat_xyzw_to_wxyz(quat))}"{grav}>')
        meta = {
            'handle': h,
            'name': o['name'],
            'type': o['type'],
            'parent': o['parent'],
            'kind': kind,
            'body': o['name'],
            'special_property': o['special_property'],
            'model_property': o['model_property'],
            'visibility_layer': o['visibility_layer'],
            'explicit_handling': o['explicit_handling'],
            'bbox': [o['bbox'][0], o['bbox'][3], o['bbox'][1], o['bbox'][4], o['bbox'][2], o['bbox'][5]],
            'bbox_params': o['bbox'],
            'world_pos': o['world_pos'],
            'world_quat': o['world_quat'],
            'col_geoms': [],
            'vis_geoms': [],
            'gui_geoms': [],
        }
        is_robot = kind == 'robot'
        moving = kind in ('movable',) or (o['type'] == 'joint')
        if kind == 'movable':
            lines.append(f'{pad}  <freejoint name={quoteattr(o["name"] + "__free")}/>')
            lines.append(f'{pad}  ' + self.inertial_xml(o))
        elif o['type'] == 'joint':
            j = o['joint']
            jtype = {JOINT_REVOLUTE: 'hinge', JOINT_PRISMATIC: 'slide', JOINT_SPHERICAL: 'ball'}[j['joint_type']]
            lo, rng = j['interval']
            attrs = [f'name={quoteattr(o["name"])}', f'type="{jtype}"']
            if jtype != 'ball':
                attrs.append('axis="0 0 1"')
                attrs.append(f'ref="{j["position"]:.9g}"')
                if not j['cyclic']:
                    attrs.append(f'range="{lo:.9g} {lo + rng:.9g}" limited="true"')
                else:
                    attrs.append('limited="false"')
            if o['name'] in ARM_JOINTS:
                attrs.append('armature="0.01" damping="0"')
            elif o['name'] in GRIPPER_JOINTS:
                attrs.append('armature="0.01" damping="1" frictionloss="0"')
            else:
                attrs.append('armature="0.005" damping="0.05" solreflimit="0.002 1"')
            lines.append(f'{pad}  <joint {" ".join(attrs)}/>')
            lines.append(f'{pad}  <inertial pos="0 0 0" mass="1e-3" diaginertia="1e-7 1e-7 1e-7"/>')
            meta['joint'] = dict(j)
            meta['joint']['mj_type'] = jtype
            meta['joint']['native'] = True
            meta['joint']['detachable_children'] = [
                self.objs[c]['name'] for c in self.children.get(h, []) if c in self.movable_roots]
        elif kind in ('robot', 'joint_chain', 'movable_child') and o['type'] == 'shape' and self.moving_ancestor(h):
            # Only dynamic shapes carry mass in CoppeliaSim; static (visual)
            # shapes welded into a moving chain contribute nothing.
            if kind != 'movable_child' and not o['shape']['static']:
                lines.append(f'{pad}  ' + self.inertial_xml(o))

        if o['type'] == 'shape':
            sh = o['shape']
            sp = o['special_property']
            layer = o['visibility_layer']
            collidable = bool(sp & SP_COLLIDABLE)
            renderable = bool(sp & SP_RENDERABLE) and bool(layer & 0xFF)
            gui_visible = bool(layer & 0xFF) and not renderable
            if sh['respondable'] or collidable:
                if sh['respondable']:
                    ct, ca = (ROBOT_CONTYPE, ROBOT_CONAFF) if is_robot else (WORLD_CONTYPE, WORLD_CONAFF)
                else:
                    ct, ca = 0, 0
                for k, g in enumerate(self.collision_geoms(o, ct, ca)):
                    gname = f'{o["name"]}__col{k}'
                    if sh['respondable'] and not is_robot:
                        g['condim'] = 4
                    if is_robot:
                        g['robot'] = True
                    lines.append(f'{pad}  ' + self.geom_xml(gname, g))
                    meta['col_geoms'].append({'name': gname, 'contype': ct, 'conaffinity': ca})
            if o['name'] in HIDDEN_FROM_CAMERAS:
                pass
            elif renderable:
                for k, g in enumerate(self.visual_geoms(o, group=1)):
                    gname = f'{o["name"]}__vis{k}'
                    lines.append(f'{pad}  ' + self.geom_xml(gname, g))
                    meta['vis_geoms'].append(gname)
            elif gui_visible and not is_robot and sh['viz']:
                for k, g in enumerate(self.visual_geoms(o, group=2)):
                    g['rgba'][3] = min(g['rgba'][3], 0.35)
                    g.pop('material', None)
                    gname = f'{o["name"]}__gui{k}'
                    lines.append(f'{pad}  ' + self.geom_xml(gname, g))
                    meta['gui_geoms'].append(gname)
            meta['shape'] = {
                'respondable': sh['respondable'],
                'static': sh['static'],
                'respondable_mask': sh['respondable_mask'],
                'mass': (sh['mass_inertia'] or {}).get('mass'),
                'color': sh.get('color'),
                'transparency': sh.get('transparency'),
                'geom_info': sh['geom_info'],
            }
        elif o['type'] == 'vision_sensor':
            v = o['vision']
            # CoppeliaSim sensors look along +z with +y up; MuJoCo cameras
            # look along -z. Rotate 180 deg about y.
            lines.append(f'{pad}  <camera name={quoteattr(o["name"])} pos="0 0 0" quat="0 0 1 0" fovy="{self.fovy(v):.6g}"/>')
            meta['vision'] = v
        elif o['type'] == 'proximity_sensor':
            pts = self.geo[o['proximity']['detected_points']]
            meta['proximity'] = {'n_hits': int(len(pts))}
            if len(pts) >= 4:
                hull = self.hull_mesh(pts, pad=0.002)
                if hull is not None:
                    mname = self.add_mesh(*hull, key_hint='prox')
                    gname = f'{o["name"]}__volume'
                    lines.append(f'{pad}  <geom name="{gname}" type="mesh" mesh="{mname}" contype="0" conaffinity="0" group="5" rgba="0 1 0 0.1"/>')
                    meta['proximity']['volume_geom'] = gname
        if o['type'] in ('dummy', 'force_sensor') or o['name'] in ('Panda_tip',):
            lines.append(f'{pad}  <site name={quoteattr(o["name"] + "__site")} size="0.005" group="5" rgba="1 0 1 0.5"/>')
            meta['site'] = o['name'] + '__site'

        self.meta_objects[h] = meta
        for c in self.children.get(h, []):
            if self.phys_parent.get(c) == h:
                self.build_body(c, T, lines, indent + 1)
        lines.append(f'{pad}</body>')

    def moving_ancestor(self, h):
        for a in [h] + self.ancestors(h):
            o = self.objs[a]
            if o['type'] == 'joint' or self.kind.get(a) == 'movable':
                return True
        return False

    def hull_mesh(self, pts, pad=0.0):
        from scipy.spatial import ConvexHull
        pts = np.asarray(pts, dtype=float)
        # Grow the sampled volume by half a grid cell so the hull covers it.
        try:
            hull = ConvexHull(pts)
        except Exception:
            return None
        c = pts.mean(0)
        v = pts[hull.vertices]
        d = v - c
        n = np.linalg.norm(d, axis=1, keepdims=True)
        v = v + d / np.maximum(n, 1e-9) * pad
        hull2 = ConvexHull(v)
        return v, hull2.simplices

    @staticmethod
    def fovy(v, resolution=None):
        res = resolution or v['resolution']
        pa = v.get('perspective_angle') or math.radians(60)
        w, h = res
        if w >= h:
            fy = 2 * math.atan(math.tan(pa / 2) * h / w)
        else:
            fy = pa
        return math.degrees(fy)

    def build(self):
        self.classify()
        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / 'meshes').mkdir(parents=True)
        (self.out / 'textures').mkdir(parents=True)
        body_lines = []
        for h in sorted(self.objs):
            if self.phys_parent.get(h) == -1:
                self.build_body(h, np.eye(4), body_lines, 2)
        missing = [self.objs[h]['name'] for h in self.objs if h not in self.meta_objects]
        if missing:
            raise RuntimeError(f'objects not placed in MJCF: {missing}')

        # The scene's lights, with the most downward-pointing one (the lamp over
        # the table) as a shadow-casting key light and the rest as soft fills.
        lights = []
        scene_lights = [o for o in self.scene['objects'] if o['type'] == 'light']
        key = min(scene_lights, key=lambda o: self.light_dir(o)[2], default=None)
        for o in scene_lights:
            attrs = (f'name={quoteattr(o["name"] + "__light")} pos="{fmt(o["world_pos"])}" '
                     f'dir="{fmt(self.light_dir(o))}" directional="false" attenuation="1 0 0"')
            if o is key:
                attrs += ' diffuse="0.55 0.53 0.5" specular="0.2 0.2 0.2" castshadow="true" cutoff="75" exponent="2"'
            else:
                attrs += ' diffuse="0.22 0.22 0.24" specular="0.05 0.05 0.05" castshadow="false"'
            lights.append(f'    <light {attrs}/>')

        equality, actuators = self.constraints_and_actuators()
        g = self.scene['gravity']
        xml = [
            f'<mujoco model={quoteattr(self.name)}>',
            '  <compiler angle="radian" inertiafromgeom="false" autolimits="true" boundmass="1e-4" boundinertia="1e-8" balanceinertia="true"/>',
            f'  <option timestep="0.005" gravity="{fmt(g)}" integrator="implicitfast" cone="pyramidal" impratio="1">',
            '    <flag multiccd="enable"/>',
            '  </option>',
            '  <size memory="256M"/>',
            '  <visual>',
            '    <global offwidth="1920" offheight="1080" fovy="45"/>',
            '    <headlight ambient="0.38 0.38 0.38" diffuse="0.16 0.16 0.16" specular="0.02 0.02 0.02"/>',
            '    <quality shadowsize="4096" offsamples="8"/>',
            '    <map znear="0.002" zfar="50" shadowclip="3" shadowscale="0.6"/>',
            '  </visual>',
            '  <default>',
            '    <geom friction="1 0.005 0.0001" solref="0.004 1" solimp="0.95 0.99 0.001"/>',
            '  </default>',
            '  <asset>',
            '    <texture name="skybox" type="skybox" builtin="gradient" rgb1="0.78 0.82 0.88" rgb2="0.42 0.45 0.5" width="256" height="1536"/>',
            *[f'    {a}' for a in self.mesh_assets],
            '  </asset>',
            '  <worldbody>',
            *lights,
            *body_lines,
            '  </worldbody>',
            *equality,
            *actuators,
            '</mujoco>',
        ]
        (self.out / 'scene.xml').write_text('\n'.join(xml) + '\n')
        meta = {
            'scene': self.name,
            'source': self.scene['source'],
            'dt': self.scene['dt'],
            'gravity': self.scene['gravity'],
            'collections': self.scene['collections'],
            'fk_samples': self.scene.get('fk_samples'),
            'objects': {str(h): m for h, m in self.meta_objects.items()},
            'detachable': [self.objs[h]['name'] for h in self.movable_roots if self.objs[h]['name'] in DETACHABLE_JOINT_CHILDREN],
            'warnings': self.warnings,
        }
        (self.out / 'scene_meta.json').write_text(json.dumps(meta, indent=1))
        print(f'[build] {self.name}: {len(self.meta_objects)} bodies, {len(self.mesh_hashes)} meshes, '
              f'{len(self.movable_roots)} movable -> {self.out / "scene.xml"}')
        for w in self.warnings:
            print(f'[build]   warning: {w}')

    @staticmethod
    def light_dir(o):
        Rm = R.from_quat(o['world_quat']).as_matrix()
        d = Rm[:, 2]
        if np.linalg.norm(d) < 1e-6:
            d = np.array([0, 0, -1.0])
        return d

    def constraints_and_actuators(self):
        eq = []
        act = []
        for h in self.movable_roots:
            o = self.objs[h]
            if o['name'] not in DETACHABLE_JOINT_CHILDREN:
                continue
            jh = o['parent']
            j = self.objs[jh]
            # The detachable child is a free body welded to the native joint
            # rotor; the shim toggles / re-anchors the weld on re-parenting.
            eq.append(f'    <weld name="{o["name"]}__hinge" body1={quoteattr(j["name"])} body2={quoteattr(o["name"])} solref="0.004 1" solimp="0.99 0.999 0.001"/>')
        for o in self.scene['objects']:
            if o['type'] != 'joint':
                continue
            if self.kind.get(o['handle']) in ('robot', 'joint_chain'):
                # Gains/force limits are set at runtime by the shim from the
                # CoppeliaSim joint mode (position / velocity / passive).
                act.append(f'    <position name={quoteattr(o["name"] + "__motor")} joint={quoteattr(o["name"])} kp="0" ctrllimited="false" forcelimited="true" forcerange="-1 1"/>')
        eq_xml = ['  <equality>', *eq, '  </equality>'] if eq else []
        excl = self.mask_excludes()
        if excl:
            eq_xml = ['  <contact>', *excl, '  </contact>'] + eq_xml
        act_xml = ['  <actuator>', *act, '  </actuator>'] if act else []
        return eq_xml, act_xml


def _model_base(builder, h):
    """Nearest ancestor (inclusive) flagged as a CoppeliaSim model base."""
    a = h
    while a >= 0:
        o = builder.objs[a]
        if not (o['model_property'] & 61440):
            return a
        a = o['parent']
    return None


def _mask_excludes(self):
    """<exclude> pairs for respondable shapes CoppeliaSim would not let collide.

    Two respondable shapes collide if (maskA & maskB) has a common bit in the
    local byte (same model) or in the global byte (different models).
    """
    resp = [h for h, o in self.objs.items() if o['type'] == 'shape' and o['shape']['respondable']
            and self.meta_objects.get(h, {}).get('col_geoms')]
    out = []
    seen = set()
    for i, a in enumerate(resp):
        for b in resp[i + 1:]:
            ka, kb = self.kind[a], self.kind[b]
            if ka == 'robot' and kb == 'robot':
                continue
            ma = self.objs[a]['shape']['respondable_mask']
            mb = self.objs[b]['shape']['respondable_mask']
            ba, bb = _model_base(self, a), _model_base(self, b)
            same = ba is not None and ba == bb
            bits = (ma & mb) & (0x00FF if same else 0xFF00)
            if bits:
                continue
            key = tuple(sorted((self.objs[a]['name'], self.objs[b]['name'])))
            if key in seen:
                continue
            seen.add(key)
            out.append(f'    <exclude body1={quoteattr(key[0])} body2={quoteattr(key[1])}/>')
    return out


SceneBuilder.mask_excludes = _mask_excludes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scenes', nargs='*')
    ap.add_argument('--all', action='store_true')
    args = ap.parse_args()
    names = sorted(p.name for p in EXTRACTED.iterdir() if (p / 'scene.json').exists()) if args.all else args.scenes
    for n in names:
        SceneBuilder(n).build()


if __name__ == '__main__':
    main()
