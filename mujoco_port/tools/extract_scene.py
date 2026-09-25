#!/usr/bin/env python3
"""Dump a CoppeliaSim .ttt scene into a simulator-neutral JSON + NPZ bundle.

Must run with the *real* PyRep/CoppeliaSim (not the MuJoCo shim):

    COPPELIASIM_ROOT=~/CoppeliaSim LD_LIBRARY_PATH=~/CoppeliaSim \
    QT_QPA_PLATFORM=offscreen python mujoco_port/tools/extract_scene.py task1_variation1.ttt

Output: mujoco_port/extracted/<scene_stem>/{scene.json, geometry.npz, textures/*.png}

Everything the MJCF builder and the MuJoCo PyRep shim need is captured here:
the full object tree with local/world poses, shape geometry (per compound
component, with pure-primitive info), visuals + textures, dynamics flags,
joints, vision/proximity sensors, collections, and forward-kinematics samples
of the Panda used to validate the converted model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if 'mujoco_port/shim' in os.environ.get('PYTHONPATH', ''):
    raise SystemExit('extract_scene.py must run against the real PyRep, not the MuJoCo shim.')

from pyrep import PyRep  # noqa: E402
from pyrep.backend import sim  # noqa: E402
from pyrep.backend._sim_cffi import ffi, lib  # noqa: E402

TYPE_NAMES = {
    sim.sim_object_shape_type: 'shape',
    sim.sim_object_joint_type: 'joint',
    sim.sim_object_dummy_type: 'dummy',
    sim.sim_object_proximitysensor_type: 'proximity_sensor',
    sim.sim_object_visionsensor_type: 'vision_sensor',
    sim.sim_object_forcesensor_type: 'force_sensor',
    sim.sim_object_camera_type: 'camera',
    sim.sim_object_light_type: 'light',
    sim.sim_object_graph_type: 'graph',
    sim.sim_object_path_type: 'path',
    sim.sim_object_octree_type: 'octree',
    sim.sim_object_pointcloud_type: 'pointcloud',
    sim.sim_object_mirror_type: 'mirror',
}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def get_mesh(handle):
    """simGetShapeMesh without PyRep's broken buffer release."""
    verts = ffi.new('float **')
    nverts = ffi.new('int *')
    inds = ffi.new('int **')
    ninds = ffi.new('int *')
    norms = ffi.new('float **')
    ret = lib.simGetShapeMesh(handle, verts, nverts, inds, ninds, norms)
    if ret == -1:
        raise RuntimeError('simGetShapeMesh failed')
    v = np.frombuffer(ffi.buffer(verts[0], nverts[0] * 4), dtype=np.float32).copy().reshape(-1, 3)
    i = np.frombuffer(ffi.buffer(inds[0], ninds[0] * 4), dtype=np.int32).copy().reshape(-1, 3)
    return v, i


def get_geom_info(handle):
    ints = ffi.new('int[4]')
    floats = ffi.new('float[4]')
    ret = lib.simGetShapeGeomInfo(handle, ints, floats, ffi.NULL)
    return {
        'compound': bool(ret & 1),
        'pure': bool(ret & 2),
        'convex': bool(ret & 4),
        'pure_type': int(ints[0]),
        'dims': [float(floats[k]) for k in range(4)],
    }


def get_mass_inertia(handle):
    mass = ffi.new('float *')
    inertia = ffi.new('float[9]')
    com = ffi.new('float[3]')
    # Express inertia/COM in the shape's own frame.
    ref = ffi.new('float[12]', [float(x) for x in sim.simGetObjectMatrix(handle, -1)])
    ret = lib.simGetShapeMassAndInertia(handle, mass, inertia, com, ref)
    if ret == -1:
        return None
    return {
        'mass': float(mass[0]),
        'inertia': [float(inertia[k]) for k in range(9)],
        'com': [float(com[k]) for k in range(3)],
    }


def get_viz(handle, index):
    info = ffi.new('struct SShapeVizInfo *')
    ret = lib.simGetShapeViz(handle, index, info)
    if ret <= 0:
        return None
    nv = info.verticesSize
    ni = info.indicesSize
    verts = np.array([info.vertices[k] for k in range(nv)], dtype=np.float32).reshape(-1, 3)
    inds = np.array([info.indices[k] for k in range(ni)], dtype=np.int32).reshape(-1, 3)
    normals = np.array([info.normals[k] for k in range(ni * 3)], dtype=np.float32).reshape(-1, 3)
    colors = [float(c) for c in info.colors]
    tex_res = (int(info.textureRes[0]), int(info.textureRes[1]))
    texture = None
    tex_coords = None
    if tex_res[0] * tex_res[1] > 0:
        texture = np.frombuffer(
            ffi.buffer(info.texture, tex_res[0] * tex_res[1] * 4), np.uint8
        ).copy().reshape(tex_res[1], tex_res[0], 4)
        tex_coords = np.array(
            [info.textureCoords[k] for k in range(ni * 2)], dtype=np.float32
        ).reshape(-1, 2)
    return {
        'vertices': verts,
        'indices': inds,
        'normals': normals,
        'colors': colors,
        'shading_angle': float(info.shadingAngle),
        'texture': texture,
        'texture_id': int(info.textureId),
        'tex_coords': tex_coords,
    }


def pose_of(handle, rel):
    pos = sim.simGetObjectPosition(handle, rel)
    quat = sim.simGetObjectQuaternion(handle, rel)
    return [float(x) for x in pos], [float(x) for x in quat]


def object_parent(handle):
    try:
        p = sim.simGetObjectParent(handle)
    except Exception:
        return -1
    return int(p) if p is not None else -1


class Extractor:
    def __init__(self, scene_path: Path, out_dir: Path):
        self.scene_path = scene_path
        self.out_dir = out_dir
        self.arrays = {}
        self.tex_dir = out_dir / 'textures'
        self.tex_ids = {}

    def add_array(self, key, arr):
        self.arrays[key] = np.asarray(arr)
        return key

    def save_texture(self, viz):
        tid = viz['texture_id']
        if tid in self.tex_ids:
            return self.tex_ids[tid]
        from PIL import Image
        self.tex_dir.mkdir(parents=True, exist_ok=True)
        name = f'tex_{len(self.tex_ids)}.png'
        # CoppeliaSim textures are stored bottom-up.
        Image.fromarray(viz['texture'][::-1].copy(), 'RGBA').save(self.tex_dir / name)
        self.tex_ids[tid] = name
        return name

    def shape_record(self, h):
        rec = {}
        rec['geom_info'] = get_geom_info(h)
        rec['respondable'] = bool(sim.simGetObjectInt32Parameter(h, sim.sim_shapeintparam_respondable))
        rec['static'] = bool(sim.simGetObjectInt32Parameter(h, sim.sim_shapeintparam_static))
        rec['respondable_mask'] = int(_safe(lambda: sim.simGetObjectInt32Parameter(h, 3019), 0xffff))
        rec['mass_inertia'] = get_mass_inertia(h)
        rec['color'] = _safe(lambda: [float(c) for c in sim.simGetShapeColor(h, None, sim.sim_colorcomponent_ambient_diffuse)])
        rec['transparency'] = _safe(lambda: float(sim.simGetShapeColor(h, None, sim.sim_colorcomponent_transparency)[0]))
        v, i = get_mesh(h)
        rec['mesh'] = {
            'vertices': self.add_array(f'mesh_v_{h}', v),
            'indices': self.add_array(f'mesh_i_{h}', i),
        }
        vizs = []
        for idx in range(256):
            viz = get_viz(h, idx)
            if viz is None:
                break
            entry = {
                'vertices': self.add_array(f'viz_v_{h}_{idx}', viz['vertices']),
                'indices': self.add_array(f'viz_i_{h}_{idx}', viz['indices']),
                'normals': self.add_array(f'viz_n_{h}_{idx}', viz['normals']),
                'colors': viz['colors'],
                'shading_angle': viz['shading_angle'],
                'texture': None,
                'tex_coords': None,
            }
            if viz['texture'] is not None:
                entry['texture'] = self.save_texture(viz)
                entry['tex_coords'] = self.add_array(f'viz_t_{h}_{idx}', viz['tex_coords'])
            vizs.append(entry)
        rec['viz'] = vizs
        # Compound components (with their own primitive/convex info) are what
        # MuJoCo needs for collision geometry.
        gi = rec['geom_info']
        if gi['compound']:
            rec['components'] = self.compound_components(h)
        elif rec['respondable'] and not gi['convex'] and not gi['pure']:
            # MuJoCo collides with convex hulls; decompose concave respondables
            # (e.g. plate_visual) with CoppeliaSim's own V-HACD.
            rec['components'] = self.convex_decomposition(h)
            rec['decomposed'] = True
        return rec

    def convex_decomposition(self, h):
        try:
            copy_h = sim.simCopyPasteObjects([h], 0)[0]
            options = 128  # use V-HACD
            int_params = [1, 500, 200, 4, 0, 400000, 20, 4, 4, 64]
            float_params = [100.0, 30.0, 0.25, 0.0, 0.0, 0.0005, 0.05, 0.05, 0.00125, 0.0001]
            dec = lib.simConvexDecompose(copy_h, options, int_params, float_params)
            if dec < 0:
                raise RuntimeError('simConvexDecompose failed')
            comps = self.compound_components(dec) if get_geom_info(dec)['compound'] else []
            if not comps:
                v, i = get_mesh(dec)
                pos, quat = pose_of(dec, h)
                comps = [{
                    'geom_info': get_geom_info(dec),
                    'local_pos': pos,
                    'local_quat': quat,
                    'mesh': {
                        'vertices': self.add_array(f'dec_v_{h}', v),
                        'indices': self.add_array(f'dec_i_{h}', i),
                    },
                }]
            else:
                # compound_components expressed poses relative to `dec`; re-express relative to h.
                dpos, dquat = pose_of(dec, h)
                from scipy.spatial.transform import Rotation as R
                rd = R.from_quat(dquat)
                for c in comps:
                    c['local_pos'] = (np.array(dpos) + rd.apply(c['local_pos'])).tolist()
                    c['local_quat'] = (rd * R.from_quat(c['local_quat'])).as_quat().tolist()
            _safe(lambda: sim.simRemoveObject(dec))
            _safe(lambda: sim.simRemoveObject(copy_h))
            print(f'[extract] decomposed concave respondable {sim.simGetObjectName(h)} into {len(comps)} hulls')
            return comps
        except Exception as exc:
            print(f'[extract] warning: convex decomposition failed for {h}: {exc}')
            return []

    def compound_components(self, h):
        comps = []
        try:
            copy_h = sim.simCopyPasteObjects([h], 0)[0]
            sim.simSetObjectParent(copy_h, -1, True)
            parts = [copy_h]
            # Fully ungroup (nested compounds) breadth-first.
            final = []
            while parts:
                p = parts.pop()
                gi = get_geom_info(p)
                if gi['compound']:
                    parts.extend(sim.simUngroupShape(p))
                else:
                    final.append(p)
            ref_pos, ref_quat = pose_of(h, -1)
            for p in final:
                gi = get_geom_info(p)
                v, i = get_mesh(p)
                pos, quat = pose_of(p, h)
                comps.append({
                    'geom_info': gi,
                    'local_pos': pos,
                    'local_quat': quat,
                    'mesh': {
                        'vertices': self.add_array(f'comp_v_{h}_{len(comps)}', v),
                        'indices': self.add_array(f'comp_i_{h}_{len(comps)}', i),
                    },
                })
            for p in final:
                _safe(lambda: sim.simRemoveObject(p))
        except Exception as exc:
            print(f'[extract] warning: could not ungroup compound {h}: {exc}')
        return comps

    def joint_record(self, h):
        cyclic, interval = sim.simGetJointInterval(h)
        rec = {
            'joint_type': int(sim.simGetJointType(h)),
            'position': float(sim.simGetJointPosition(h)),
            'cyclic': bool(cyclic),
            'interval': [float(interval[0]), float(interval[1])],
            'mode': int(sim.simGetJointMode(h)),
            'max_force': _safe(lambda: float(sim.simGetJointMaxForce(h))),
            'target_position': _safe(lambda: float(sim.simGetJointTargetPosition(h))),
            'target_velocity': _safe(lambda: float(sim.simGetJointTargetVelocity(h))),
            'upper_velocity_limit': _safe(lambda: float(sim.simGetObjectFloatParameter(h, 2017))),
            'ctrl_enabled': _safe(lambda: bool(sim.simGetObjectInt32Parameter(h, 2001))),
            'motor_enabled': _safe(lambda: bool(sim.simGetObjectInt32Parameter(h, 2000))),
            'velocity_lock': _safe(lambda: bool(sim.simGetObjectInt32Parameter(h, 2030))),
            'pid': [_safe(lambda k=k: float(sim.simGetObjectFloatParameter(h, k))) for k in (2002, 2003, 2004)],
        }
        return rec

    def vision_record(self, h):
        res = sim.simGetVisionSensorResolution(h)
        return {
            'resolution': [int(res[0]), int(res[1])],
            'perspective_angle': _safe(lambda: float(sim.simGetObjectFloatParameter(h, 1004))),
            'ortho_size': _safe(lambda: float(sim.simGetObjectFloatParameter(h, 1005))),
            'near': _safe(lambda: float(sim.simGetObjectFloatParameter(h, 1000))),
            'far': _safe(lambda: float(sim.simGetObjectFloatParameter(h, 1001))),
            'perspective': _safe(lambda: int(sim.simGetObjectInt32Parameter(h, 1018))),
            'render_mode': _safe(lambda: int(sim.simGetObjectInt32Parameter(h, 1017))),
            'explicit_handling': _safe(lambda: int(sim.simGetExplicitHandling(h))),
        }

    def proximity_record(self, h):
        """Empirically sample the detection volume in the sensor frame."""
        from pyrep.objects.shape import Shape
        from pyrep.const import PrimitiveShape
        probe = Shape.create(PrimitiveShape.CUBOID, [0.002] * 3, respondable=False, static=True)
        sim.simSetObjectSpecialProperty(probe.get_handle(), 1 | 2 | 496 | 512)
        hits = []
        xs = np.arange(-0.06, 0.0601, 0.004)
        zs = np.arange(-0.03, 0.2001, 0.004)
        for x in xs:
            for y in xs:
                for z in zs:
                    sim.simSetObjectPosition(probe.get_handle(), h, [float(x), float(y), float(z)])
                    try:
                        state, _ = sim.simCheckProximitySensor(h, probe.get_handle())
                    except Exception:
                        state = 0
                    if state == 1:
                        hits.append([float(x), float(y), float(z)])
        probe.remove()
        return {'detected_points': self.add_array(f'prox_{h}', np.array(hits, dtype=np.float32).reshape(-1, 3)),
                'n_hits': len(hits)}

    def fk_samples(self, n=40):
        """Record Panda tip poses for random joint configurations."""
        try:
            joints = [sim.simGetObjectHandle(f'Panda_joint{i}') for i in range(1, 8)]
            tip = sim.simGetObjectHandle('Panda_tip')
        except Exception:
            return None
        rng = np.random.default_rng(0)
        q0 = [sim.simGetJointPosition(j) for j in joints]
        lows, highs = [], []
        for j in joints:
            _, (lo, rng_) = sim.simGetJointInterval(j)
            lows.append(lo)
            highs.append(lo + rng_)
        samples = []
        for k in range(n):
            q = q0 if k == 0 else [float(rng.uniform(lo, hi)) for lo, hi in zip(lows, highs)]
            for j, v in zip(joints, q):
                sim.simSetJointPosition(j, v)
            pos, quat = pose_of(tip, -1)
            samples.append({'q': [float(v) for v in q], 'tip_pos': pos, 'tip_quat': quat})
        for j, v in zip(joints, q0):
            sim.simSetJointPosition(j, v)
        return samples

    def run(self):
        pr = PyRep()
        pr.launch(str(self.scene_path), headless=True)
        pr.start()
        pr.step()
        handles = sim.simGetObjectsInTree(sim.sim_handle_scene, sim.sim_handle_all, 0)
        objects = []
        for h in handles:
            t = sim.simGetObjectType(h)
            parent = object_parent(h)
            wpos, wquat = pose_of(h, -1)
            lpos, lquat = pose_of(h, parent) if parent >= 0 else (wpos, wquat)
            rec = {
                'handle': int(h),
                'name': sim.simGetObjectName(h),
                'type': TYPE_NAMES.get(t, str(t)),
                'type_id': int(t),
                'parent': parent,
                'world_pos': wpos,
                'world_quat': wquat,
                'local_pos': lpos,
                'local_quat': lquat,
                'special_property': int(_safe(lambda: sim.simGetObjectSpecialProperty(h), 0)),
                'model_property': int(_safe(lambda: sim.simGetModelProperty(h), 0)),
                'visibility_layer': int(_safe(lambda: sim.simGetObjectInt32Parameter(h, 10), 1)),
                'explicit_handling': int(_safe(lambda: sim.simGetExplicitHandling(h), 0)),
                'bbox': [float(_safe(lambda k=k: sim.simGetObjectFloatParameter(h, k), 0.0)) for k in range(15, 21)],
            }
            if t == sim.sim_object_shape_type:
                rec['shape'] = self.shape_record(h)
            elif t == sim.sim_object_joint_type:
                rec['joint'] = self.joint_record(h)
            elif t == sim.sim_object_visionsensor_type:
                rec['vision'] = self.vision_record(h)
            elif t == sim.sim_object_proximitysensor_type:
                rec['proximity'] = self.proximity_record(h)
            objects.append(rec)
            print(f"[extract] {rec['name']} ({rec['type']})", flush=True)

        collections = {}
        for cname in ('Panda_arm',):
            try:
                ch = sim.simGetCollectionHandle(cname)
                cnt = ffi.new('int *')
                ptr = lib.simGetCollectionObjects(ch, cnt)
                collections[cname] = [int(ptr[k]) for k in range(cnt[0])]
            except Exception:
                pass

        scene = {
            'source': str(self.scene_path.relative_to(ROOT)) if self.scene_path.is_relative_to(ROOT) else str(self.scene_path),
            'dt': float(sim.simGetSimulationTimeStep()),
            'gravity': _safe(lambda: [float(x) for x in sim.simGetArrayParameter(sim.sim_arrayparam_gravity)], [0, 0, -9.81]),
            'objects': objects,
            'collections': collections,
            'fk_samples': self.fk_samples(),
        }
        pr.stop()
        pr.shutdown()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.out_dir / 'geometry.npz', **self.arrays)
        (self.out_dir / 'scene.json').write_text(json.dumps(scene, indent=1))
        print(f'[extract] wrote {self.out_dir} ({len(objects)} objects)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scene')
    ap.add_argument('--out-root', default=str(ROOT / 'mujoco_port' / 'extracted'))
    args = ap.parse_args()
    scene_path = Path(args.scene).resolve()
    stem = scene_path.stem.replace('.', '_')
    Extractor(scene_path, Path(args.out_root) / stem).run()
    os._exit(0)  # CoppeliaSim's teardown can abort under Python 3.13.


if __name__ == '__main__':
    main()
