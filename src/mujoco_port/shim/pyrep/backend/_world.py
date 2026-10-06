"""MuJoCo implementation of the CoppeliaSim object model used by PyRep.

One ``World`` holds the compiled MJCF scene (built by
the historical scene-conversion tool) plus everything CoppeliaSim tracks that
MuJoCo does not: CoppeliaSim handles and names, the *logical* parent tree
(which can change at runtime via set_parent / grasp), per-object dynamic /
respondable / collidable flags, joint motor modes and vision-sensor state.

Emulated CoppeliaSim semantics
  * Non-dynamic shapes rigidly follow their logical parent; dynamic shapes
    under a force sensor (the gripper attach point) are rigidly attached;
    dynamic shapes under a passive joint hang on a (constraint) hinge;
    otherwise dynamic shapes are free rigid bodies.
  * The Panda arm is kinematic (set positions / targets are tracked
    exactly); gripper fingers and scene joints are force-limited motors.
  * Collision / proximity queries use exact MuJoCo geom distances on the
    shapes' own collision geometry, with CoppeliaSim's entity rules.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from . import simConst as C


def trial_rng(tag: str, index: int) -> np.random.Generator:
    """Random generator for the motion planner (IK sampling, RRT-Connect).

    With ``TAMP_TRIAL_SEED`` set (the trial runner sets it to the trial seed), the generator is
    derived from (seed, purpose, call index), so the sequence of IK / RRT seeds is the same in
    every run of a trial whatever else consumed random numbers. What still varies between runs
    is wall-clock bound: IK and RRT stop at a time budget, so a slower or busier machine may try
    fewer seeds before giving up (documented in mujoco_port/README.md). Without the variable the
    generator is unseeded (previous behaviour)."""
    seed = os.environ.get('TAMP_TRIAL_SEED', '').strip()
    if not seed:
        return np.random.default_rng()
    import zlib
    return np.random.default_rng([int(seed) % (2 ** 32), zlib.crc32(tag.encode('utf-8')), int(index)])
from ._kin import ArmChain, limit_margin, linear_ik_path, mat_to_quat_xyzw, quat_wxyz_to_mat, quat_xyzw_to_mat, rrt_connect
from ._render import SensorRenderer, configure_gl_backend

configure_gl_backend()
import mujoco  # noqa: E402

ARM_JOINTS = [f'Panda_joint{i}' for i in range(1, 8)]
COLLECTION_HANDLE_BASE = 2_000_000
IK_GROUP_HANDLE_BASE = 3_000_000
DRAWING_HANDLE_BASE = 4_000_000
SP_DETECTABLE = C.sim_objectspecialproperty_detectable_all
SERVO_HZ = 20.0
# Legacy mode: drive the Panda arm purely kinematically (no contact compliance).
KINEMATIC_ARM = os.environ.get('MUJOCO_SHIM_KINEMATIC_ARM', '0') == '1'
SOFT_KINEMATIC_CONTACTS = os.environ.get('MUJOCO_SHIM_SOFT_KINEMATIC', '1') == '1'
SOFT_FOLLOWERS = os.environ.get('MUJOCO_SHIM_SOFT_FOLLOWERS', '0') == '1'
SOFT_RELEASE = os.environ.get('MUJOCO_SHIM_SOFT_RELEASE', '0') == '1'
SOFT_TELEPORT_ROBOT = os.environ.get('MUJOCO_SHIM_SOFT_TELEPORT_ROBOT', '1') == '1'
# Resting bodies sleep, as in CoppeliaSim's engines: MuJoCo's soft contacts let
# multi-hull meshes (the mugs) creep across flat supports by several cm per minute
# of arm motion. A free body that stays below SLEEP_LIN / SLEEP_ANG for SLEEP_SUBSTEPS
# substeps keeps its pose until it touches a moving body (robot, carried object, lid),
# moves faster than WAKE_LIN / WAKE_ANG, or is moved from outside (set_pose, followers).
SLEEP_RESTING = os.environ.get('MUJOCO_SHIM_SLEEP', '1') == '1'
SLEEP_LIN, SLEEP_ANG, SLEEP_SUBSTEPS = 0.004, 0.05, 20
WAKE_LIN, WAKE_ANG, SLEEP_POSE_TOL = 0.01, 0.1, 1e-4


def _T(pos, quat_xyzw):
    T = np.eye(4)
    T[:3, :3] = quat_xyzw_to_mat(quat_xyzw)
    T[:3, 3] = pos
    return T


def _inv(T):
    Ti = np.eye(4)
    Ti[:3, :3] = T[:3, :3].T
    Ti[:3, 3] = -T[:3, :3].T @ T[:3, 3]
    return Ti


def _rz(theta):
    c, s = math.cos(theta), math.sin(theta)
    T = np.eye(4)
    T[0, 0], T[0, 1], T[1, 0], T[1, 1] = c, -s, s, c
    return T


def _tz(d):
    T = np.eye(4)
    T[2, 3] = d
    return T


def euler_to_mat(e):
    """CoppeliaSim Euler angles: R = Rx(a) * Ry(b) * Rz(g)."""
    a, b, g = e
    ca, sa, cb, sb, cg, sg = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(g), math.sin(g)
    Rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
    Ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    Rz = np.array([[cg, -sg, 0], [sg, cg, 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def mat_to_euler(Rm):
    b = math.asin(max(-1.0, min(1.0, Rm[0, 2])))
    if abs(Rm[0, 2]) < 0.9999999:
        a = math.atan2(-Rm[1, 2], Rm[2, 2])
        g = math.atan2(-Rm[0, 1], Rm[0, 0])
    else:
        a = math.atan2(Rm[2, 1], Rm[1, 1])
        g = 0.0
    return [a, b, g]


def resolve_scene_dir(scene_file: str) -> Path:
    """Map a CoppeliaSim .ttt path to its converted MuJoCo scene directory."""
    root = Path(__file__).resolve().parents[3]
    scenes = Path(os.environ.get('MUJOCO_SCENE_ROOT', root.parents[1] / 'assets' / 'scenes'))
    p = Path(scene_file)
    if p.is_dir() and (p / 'scene.xml').exists():
        return p
    if p.suffix == '.xml' and p.exists():
        return p.parent
    stem = p.name
    for suffix in ('.ttt', '.ttm'):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    cand = scenes / stem.replace('.', '_')
    if (cand / 'scene.xml').exists():
        return cand
    raise FileNotFoundError(
        f'No converted MuJoCo scene for {scene_file!r} (looked for {cand}). '
        'Check the bundled assets/scenes directory or set MUJOCO_SCENE_ROOT.')


class Obj:
    """CoppeliaSim-side state of one scene object."""

    def __init__(self, meta: dict):
        self.meta = meta
        self.handle = int(meta['handle'])
        self.name = meta['name']
        self.type = meta['type']
        self.type_id = {
            'shape': C.sim_object_shape_type, 'joint': C.sim_object_joint_type,
            'dummy': C.sim_object_dummy_type, 'proximity_sensor': C.sim_object_proximitysensor_type,
            'vision_sensor': C.sim_object_visionsensor_type, 'force_sensor': C.sim_object_forcesensor_type,
            'camera': C.sim_object_camera_type, 'light': C.sim_object_light_type,
            'graph': C.sim_object_graph_type, 'path': C.sim_object_path_type,
            'octree': C.sim_object_octree_type, 'mirror': C.sim_object_mirror_type,
            'pointcloud': C.sim_object_pointcloud_type,
        }.get(self.type, -1)
        self.kind = meta['kind']
        self.parent = int(meta['parent'])
        self.sp = int(meta['special_property'])
        self.mp = int(meta['model_property'])
        self.layer = int(meta['visibility_layer'])
        self.explicit = int(meta.get('explicit_handling', 0))
        self.bbox = list(meta['bbox'])            # PyRep order
        self.bbox_params = list(meta['bbox_params'])  # params 15..20
        self.body = -1
        self.free = False
        self.qadr = self.dadr = -1
        self.mode = None
        self.follow_rel = None
        self.shape = meta.get('shape')
        self.respondable = bool(self.shape['respondable']) if self.shape else False
        self.static = bool(self.shape['static']) if self.shape else True
        self.resp_mask = int(self.shape['respondable_mask']) if self.shape else 0xFFFF
        self.col_geoms = np.zeros(0, dtype=np.int64)
        self.col_contype = np.zeros(0, dtype=np.int32)
        self.col_conaff = np.zeros(0, dtype=np.int32)
        self.vis_geoms = np.zeros(0, dtype=np.int64)
        self.gui_geoms = np.zeros(0, dtype=np.int64)
        self.color = list(self.shape['color']) if self.shape and self.shape.get('color') else [0.5, 0.5, 0.5]
        self.transparency = float(self.shape.get('transparency') or 0.0) if self.shape else 0.0
        self.mass = float(self.shape.get('mass') or 0.0) if self.shape else 0.0
        # joints
        self.joint = meta.get('joint')
        self.jid = self.jqadr = self.jdadr = self.act = -1
        # vision
        self.vision = meta.get('vision')
        self.cam = -1
        self.images = {}
        # proximity
        self.prox = meta.get('proximity')
        self.vol_geom = -1
        self.site = -1


class JointState:
    def __init__(self, o: Obj):
        j = o.joint
        self.obj = o
        self.jtype = int(j['joint_type'])
        self.cyclic = bool(j['cyclic'])
        self.interval = [float(j['interval'][0]), float(j['interval'][1])]
        self.mode = int(j['mode'])
        self.max_force = float(j['max_force'] if j['max_force'] is not None else 1.0)
        self.target_pos = float(j['target_position'] if j['target_position'] is not None else j['position'])
        self.target_vel = float(j['target_velocity'] or 0.0)
        self.vmax = float(j['upper_velocity_limit'] or 3.0)
        self.ctrl = bool(j['ctrl_enabled'])
        self.motor = bool(j['motor_enabled'])
        self.vlock = bool(j['velocity_lock'])
        self.pid = [p if p is not None else 0.1 for p in (j.get('pid') or [0.1, 0.0, 0.0])]
        self.native = bool(j.get('native', True))
        self.ref = float(j['position'])
        self.lock_q = float(j['position'])
        self.kinematic_arm = KINEMATIC_ARM and o.name in ARM_JOINTS
        lo, rng = self.interval
        self.eff_range = (lo, lo + rng)
        self.kp = 0.0
        self.kvd = 0.0


class World:
    def __init__(self, scene_file: str, headless: bool = True):
        self.scene_dir = resolve_scene_dir(scene_file)
        self.scene_file = scene_file
        self.headless = headless
        self.meta = json.loads((self.scene_dir / 'scene_meta.json').read_text())
        self.model = mujoco.MjModel.from_xml_path(str(self.scene_dir / 'scene.xml'))
        self.m = self.model
        self.d = mujoco.MjData(self.m)
        self.dt = float(self.meta['dt'])
        self.nsub = max(1, int(round(self.dt / self.m.opt.timestep)))
        self.sim_time = 0.0
        self.running = False
        self._dirty = True
        self._orig_body_pos = self.m.body_pos.copy()
        self._orig_body_quat = self.m.body_quat.copy()
        self._orig_geom_contype = self.m.geom_contype.copy()
        self._orig_geom_conaff = self.m.geom_conaffinity.copy()
        self._orig_geom_rgba = self.m.geom_rgba.copy()
        self._orig_geom_solref = self.m.geom_solref.copy()
        self._orig_geom_solimp = self.m.geom_solimp.copy()
        self._orig_geom_solmix = self.m.geom_solmix.copy()
        self.signals = {}
        self.string_params = {}
        self.drawings = 0
        self._ik_fail_memo = {}
        self._rng_calls = {}
        self._rml = {}
        self._build_tables()
        self._init_state()
        self.renderer = SensorRenderer(self.m, self.geom_handle)
        self.viewer = None
        if not headless and os.environ.get('MUJOCO_SHIM_VIEWER', '1') != '0':
            self._launch_viewer()

    # ------------------------------------------------------------------ setup
    def _build_tables(self):
        m = self.m
        self.objs: Dict[int, Obj] = {}
        self.by_name: Dict[str, int] = {}
        for hs, om in self.meta['objects'].items():
            o = Obj(om)
            self.objs[o.handle] = o
            self.by_name[o.name] = o.handle
        self.order = sorted(self.objs)
        self.geom_handle = np.full(m.ngeom, -1, dtype=np.int64)
        for o in self.objs.values():
            o.body = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, o.meta['body'])
            if o.kind == 'movable':
                jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, o.name + '__free')
                o.free = True
                o.qadr = int(m.jnt_qposadr[jid])
                o.dadr = int(m.jnt_dofadr[jid])
            if o.shape is not None:
                cg = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, g['name']) for g in o.meta['col_geoms']]
                o.col_geoms = np.array(cg, dtype=np.int64)
                o.col_contype = np.array([g['contype'] for g in o.meta['col_geoms']], dtype=np.int32)
                o.col_conaff = np.array([g['conaffinity'] for g in o.meta['col_geoms']], dtype=np.int32)
                o.vis_geoms = np.array([mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, g) for g in o.meta['vis_geoms']], dtype=np.int64)
                o.gui_geoms = np.array([mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, g) for g in o.meta['gui_geoms']], dtype=np.int64)
                for g in list(o.col_geoms) + list(o.vis_geoms) + list(o.gui_geoms):
                    self.geom_handle[g] = o.handle
            if o.joint is not None:
                o.jstate = JointState(o)
                if o.jstate.native:
                    o.jid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, o.name)
                    o.jqadr = int(m.jnt_qposadr[o.jid])
                    o.jdadr = int(m.jnt_dofadr[o.jid])
                    o.act = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, o.name + '__motor')
            if o.vision is not None:
                o.cam = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_CAMERA, o.name)
                o.vision = dict(o.vision)
            if o.prox is not None and o.prox.get('volume_geom'):
                o.vol_geom = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, o.prox['volume_geom'])
            if o.meta.get('site'):
                o.site = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, o.meta['site'])
        self.children: Dict[int, List[int]] = {}
        self._rebuild_children()
        self.free_objs = [o for o in self.objs.values() if o.free]
        self.native_joints = [o for o in self.objs.values() if o.joint is not None and o.jstate.native]
        self.arm_joints = [self.objs[self.by_name[n]] for n in ARM_JOINTS if n in self.by_name]
        # Effective joint inertia -> velocity-loop gain.
        for o in self.native_joints:
            inertia = float(m.dof_M0[o.jdadr]) if m.dof_M0[o.jdadr] > 0 else float(m.dof_armature[o.jdadr] + 1e-3)
            inertia = max(inertia, 1e-4)
            omega = 2 * math.pi * SERVO_HZ
            o.jstate.kp = inertia * omega ** 2
            o.jstate.kvd = 2.0 * inertia * omega
        # Collections (dynamic tree membership).
        self.collections = {}
        for k, (name, members) in enumerate(self.meta.get('collections', {}).items()):
            root = self.by_name.get('Panda') if name == 'Panda_arm' else None
            self.collections[COLLECTION_HANDLE_BASE + k] = {'name': name, 'root': root, 'static': members}
        self.collection_by_name = {v['name']: h for h, v in self.collections.items()}
        # Detachable joint children: free bodies welded to the joint rotor.
        self.hinge_eqs = {}
        for o in self.native_joints:
            for cname in o.joint.get('detachable_children', []) or []:
                ch = self.by_name[cname]
                e = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_EQUALITY, f'{cname}__hinge')
                if e >= 0:
                    self.hinge_eqs[ch] = (o.handle, e)
                    o.jstate.detachable = ch
        # Arm chain for IK.
        self._build_arm_chain()

    def _rebuild_children(self):
        self.children = {}
        for h in self.order:
            self.children.setdefault(self.objs[h].parent, []).append(h)

    def _build_arm_chain(self):
        self.chain = None
        if not all(n in self.by_name for n in ARM_JOINTS + ['Panda_tip']):
            return
        m = self.m
        d = mujoco.MjData(m)
        d.qpos[:] = m.qpos0
        mujoco.mj_kinematics(m, d)

        def bT(bid):
            T = np.eye(4)
            T[:3, :3] = d.xmat[bid].reshape(3, 3)
            T[:3, 3] = d.xpos[bid]
            return T
        jb = [self.objs[self.by_name[n]].body for n in ARM_JOINTS]
        tip = self.objs[self.by_name['Panda_tip']].body
        Ts = [bT(b) for b in jb]
        links = [_inv(Ts[i]) @ Ts[i + 1] for i in range(len(Ts) - 1)]
        tip_T = _inv(Ts[-1]) @ bT(tip)
        refs = [self.objs[self.by_name[n]].jstate.ref for n in ARM_JOINTS]
        lows, highs = [], []
        for n in ARM_JOINTS:
            js = self.objs[self.by_name[n]].jstate
            lo, rng = js.interval
            if js.cyclic:
                lows.append(-math.pi)
                highs.append(math.pi)
            else:
                lows.append(lo)
                highs.append(lo + rng)
        self.chain = ArmChain(Ts[0], links, refs, tip_T, lows, highs)
        self.chain_base_body = m.body_parentid[jb[0]]
        self.chain_base_T0 = bT(self.chain_base_body)

    def _init_state(self):
        m, d = self.m, self.d
        mujoco.mj_resetData(m, d)
        m.body_pos[:] = self._orig_body_pos
        m.body_quat[:] = self._orig_body_quat
        m.geom_contype[:] = self._orig_geom_contype
        m.geom_conaffinity[:] = self._orig_geom_conaff
        m.geom_rgba[:] = self._orig_geom_rgba
        m.geom_solref[:] = self._orig_geom_solref
        m.geom_solimp[:] = self._orig_geom_solimp
        m.geom_solmix[:] = self._orig_geom_solmix
        self._follow_prev = {}
        self._robot_soft = False
        self._soft_objs = set()
        self._soft_geom_sets = {}
        for o in self.objs.values():
            om = o.meta
            o.parent = int(om['parent'])
            o.sp = int(om['special_property'])
            o.mp = int(om['model_property'])
            o.follow_rel = None
            o.mode = None
            if o.shape is not None:
                o.respondable = bool(o.shape['respondable'])
                o.static = bool(o.shape['static'])
            if o.joint is not None:
                o.jstate = JointState(o) if not hasattr(o, 'jstate') else o.jstate
                js = o.jstate
                j = o.joint
                js.mode = int(j['mode'])
                js.max_force = float(j['max_force'] if j['max_force'] is not None else 1.0)
                js.target_pos = float(j['target_position'] if j['target_position'] is not None else j['position'])
                js.target_vel = float(j['target_velocity'] or 0.0)
                js.ctrl = bool(j['ctrl_enabled'])
                js.motor = bool(j['motor_enabled'])
                js.vlock = bool(j['velocity_lock'])
                js.lock_q = js.ref
                js.stalled = False
                js.interval = [float(j['interval'][0]), float(j['interval'][1])]
                js.eff_range = (js.interval[0], js.interval[0] + js.interval[1])
                if js.native:
                    m.jnt_range[o.jid] = list(js.eff_range)
        self._rebuild_children()
        self.arm_cmd = {o.handle: o.jstate.ref for o in self.arm_joints}
        self._dirty = True
        self._fresh()
        for o in self.free_objs:
            self._update_mode(o.handle, force=True)
        self._apply_respondable_all()
        self._dirty = True
        self._fresh()
        self.sim_time = 0.0
        self._ik_fail_memo = {}
        self._rng_calls = {}

    def _launch_viewer(self):
        try:
            import mujoco.viewer
            self.viewer = mujoco.viewer.launch_passive(self.m, self.d, show_left_ui=False, show_right_ui=False)
            with self.viewer.lock():
                self.viewer.opt.geomgroup[:] = 0
                self.viewer.opt.geomgroup[1] = 1
                self.viewer.opt.geomgroup[2] = 1
                # Start looking at the table from the front-left.
                bid = mujoco.mj_name2id(self.m, mujoco.mjtObj.mjOBJ_BODY, 'diningTable')
                self.viewer.cam.lookat[:] = (self.m.body_pos[bid] + [0, 0, 0.45]) if bid >= 0 else self.m.stat.center
                self.viewer.cam.distance = 2.6
                self.viewer.cam.azimuth = 200
                self.viewer.cam.elevation = -28
            self._viewer_last = 0.0
        except Exception as exc:
            print(f'[mujoco-shim] GUI viewer unavailable ({exc}); continuing headless.', file=sys.stderr)
            self.viewer = None

    # ------------------------------------------------------------------ lookup
    def obj(self, h) -> Obj:
        h = int(h)
        o = self.objs.get(h)
        if o is None:
            raise RuntimeError(f'The call failed on the V-REP side. Object handle {h} does not exist.')
        return o

    def handle_of(self, name: str) -> int:
        base = name.split('#')[0] if name.endswith('#') else name
        if base in self.by_name:
            return self.by_name[base]
        if '#' in name:
            stem, _, idx = name.partition('#')
            if idx in ('', '0') and stem in self.by_name:
                return self.by_name[stem]
        raise RuntimeError(f'Handle {name} does not exist.')

    # ------------------------------------------------------------------ frames
    def _fresh(self):
        if self._dirty:
            mujoco.mj_kinematics(self.m, self.d)
            self._dirty = False

    def body_T(self, bid):
        self._fresh()
        T = np.eye(4)
        T[:3, :3] = self.d.xmat[bid].reshape(3, 3)
        T[:3, 3] = self.d.xpos[bid]
        return T

    def _joint_delta(self, o):
        js = o.jstate
        if js.native:
            return float(self.d.qpos[o.jqadr]) - js.ref
        return 0.0

    def obj_T(self, h):
        if h is None or h < 0:
            return np.eye(4)
        o = self.obj(h)
        T = self.body_T(o.body)
        if o.joint is not None and o.jstate.native:
            delta = self._joint_delta(o)
            if o.jstate.jtype == C.sim_joint_revolute_subtype:
                T = T @ _rz(-delta)
            elif o.jstate.jtype == C.sim_joint_prismatic_subtype:
                T = T @ _tz(-delta)
        return T

    def rel_T(self, h, rel):
        T = self.obj_T(h)
        if rel is None or rel < 0:
            return T
        return _inv(self.obj_T(rel)) @ T

    def set_obj_T(self, h, T, reset_dynamics=True, _update_follow=True):
        o = self.obj(h)
        m, d = self.m, self.d
        if o.free:
            d.qpos[o.qadr:o.qadr + 3] = T[:3, 3]
            q = mat_to_quat_xyzw(T[:3, :3])
            d.qpos[o.qadr + 3:o.qadr + 7] = [q[3], q[0], q[1], q[2]]
            if reset_dynamics:
                d.qvel[o.dadr:o.dadr + 6] = 0.0
            self._dirty = True
            if _update_follow and o.mode == 'follow':
                o.follow_rel = _inv(self.obj_T(o.parent)) @ T if o.parent >= 0 else T.copy()
            if _update_follow and o.mode == 'hinge':
                self._configure_hinge(o)
        else:
            Tb = T.copy()
            if o.joint is not None and o.jstate.native:
                delta = self._joint_delta(o)
                if o.jstate.jtype == C.sim_joint_revolute_subtype:
                    Tb = T @ _rz(delta)
                elif o.jstate.jtype == C.sim_joint_prismatic_subtype:
                    Tb = T @ _tz(delta)
            pb = int(m.body_parentid[o.body])
            Tp = self.body_T(pb) if pb > 0 else np.eye(4)
            L = _inv(Tp) @ Tb
            m.body_pos[o.body] = L[:3, 3]
            q = mat_to_quat_xyzw(L[:3, :3])
            m.body_quat[o.body] = [q[3], q[0], q[1], q[2]]
            self._dirty = True
        if _update_follow:
            self._apply_followers()

    def _subtree_logical(self, h):
        out = [h]
        stack = list(self.children.get(h, []))
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(self.children.get(c, []))
        return out

    def objects_in_tree(self, root, type_id, options):
        exclude_base = bool(options & 1)
        first_gen = bool(options & 2)
        out = []

        def visit(h, depth):
            o = self.objs[h]
            if not (exclude_base and depth == 0):
                if type_id == C.sim_handle_all or o.type_id == type_id:
                    out.append(h)
            if first_gen and depth >= 1:
                return
            for c in self.children.get(h, []):
                visit(c, depth + 1)

        if root is None or int(root) == C.sim_handle_scene or int(root) < 0:
            for h in self.children.get(-1, []):
                visit(h, 1)
            return out
        visit(int(root), 0)
        return out

    # ------------------------------------------------------------------ flags
    def _model_ancestors(self, h):
        o = self.objs[h]
        chain = [h]
        p = o.parent
        while p >= 0:
            chain.append(p)
            p = self.objs[p].parent
        return chain

    def _model_flag(self, h, bit):
        """True if some model base on h's ancestry (inclusive) sets 'not <bit>'."""
        for a in self._model_ancestors(h):
            ao = self.objs[a]
            is_model = not (ao.mp & C.sim_modelproperty_not_model)
            if is_model and (ao.mp & bit):
                return True
        return False

    def is_dynamic(self, h):
        o = self.objs[h]
        return (not o.static) and not self._model_flag(h, C.sim_modelproperty_not_dynamic)

    def is_respondable(self, h):
        o = self.objs[h]
        return o.respondable and not self._model_flag(h, C.sim_modelproperty_not_respondable)

    def is_collidable(self, h):
        o = self.objs[h]
        return bool(o.sp & C.sim_objectspecialproperty_collidable) and not self._model_flag(h, C.sim_modelproperty_not_collidable)

    def is_detectable(self, h):
        o = self.objs[h]
        return bool(o.sp & SP_DETECTABLE) and not self._model_flag(h, C.sim_modelproperty_not_detectable)

    def _apply_respondable(self, h):
        o = self.objs[h]
        if o.shape is None or len(o.col_geoms) == 0:
            return
        on = self.is_respondable(h)
        for g, ct, ca in zip(o.col_geoms, o.col_contype, o.col_conaff):
            if ct == 0 and ca == 0 and on:
                # Originally non-respondable shape switched on: use world masks.
                ct, ca = (2, 1) if o.kind == 'robot' else (1, 3)
            self.m.geom_contype[g] = ct if on else 0
            self.m.geom_conaffinity[g] = ca if on else 0

    def _apply_respondable_all(self):
        for h, o in self.objs.items():
            if o.shape is not None:
                self._apply_respondable(h)

    def refresh_flags(self, h):
        """Re-derive physics after a flag / model-property change on h (and its tree)."""
        for t in self._subtree_logical(h):
            o = self.objs[t]
            if o.shape is not None:
                self._apply_respondable(t)
            if o.free:
                self._update_mode(t)

    def reset_dynamic_object(self, h):
        o = self.objs.get(int(h))
        if o is None:
            raise RuntimeError('The call failed on the V-REP side.')
        if o.free:
            self.d.qvel[o.dadr:o.dadr + 6] = 0.0
        if o.joint is not None and o.jstate.native and not o.jstate.kinematic_arm:
            self.d.qvel[o.jdadr] = 0.0

    # ------------------------------------------------------------------ parenting / modes
    def _update_mode(self, h, force=False):
        o = self.objs[h]
        if not o.free:
            return
        p = o.parent
        pt = self.objs[p].type if p >= 0 else None
        if not self.is_dynamic(h):
            mode = 'follow'
        elif pt == 'force_sensor':
            mode = 'follow'
        elif p >= 0 and h in self.hinge_eqs and self.hinge_eqs[h][0] == p:
            mode = 'hinge'
        else:
            mode = 'free'
        if mode == o.mode and not force:
            return
        released = (o.mode == 'follow') and mode in ('free', 'hinge') and not force
        o.mode = mode
        if released and SOFT_RELEASE:
            # A held/static object turned dynamic while overlapping something is
            # eased out of the overlap (CoppeliaSim) rather than ejected.
            geoms = self._object_geoms(o)
            if len(geoms):
                self.__dict__.setdefault('_soft_geom_sets', {})[('release', h)] = {
                    'geoms': geoms, 'depth': 2e-3, 'ttl': 40}
        T = self.obj_T(h)
        if mode == 'follow':
            o.follow_rel = _inv(self.obj_T(p)) @ T if p >= 0 else T.copy()
            self.d.qvel[o.dadr:o.dadr + 6] = 0.0
        else:
            o.follow_rel = None
        if h in self.hinge_eqs:
            jh, e = self.hinge_eqs[h]
            active = mode == 'hinge'
            self.d.eq_active[e] = 1 if active else 0
            if active:
                self._configure_hinge(o)

    def _configure_hinge(self, o):
        """Re-anchor the rotor weld at the current relative pose (keep in place)."""
        if o.handle not in self.hinge_eqs:
            return
        jh, e = self.hinge_eqs[o.handle]
        Tr = self.body_T(self.objs[jh].body)
        Tc = self.body_T(o.body)
        rel = _inv(Tr) @ Tc
        q = mat_to_quat_xyzw(rel[:3, :3])
        self.m.eq_data[e, 0:3] = 0.0
        self.m.eq_data[e, 3:6] = rel[:3, 3]
        self.m.eq_data[e, 6:10] = [q[3], q[0], q[1], q[2]]
        self.m.eq_data[e, 10] = 1.0
        o.hinge_rel = rel

    def set_parent(self, h, parent, keep_in_place=True):
        o = self.obj(h)
        parent = int(parent) if parent is not None else -1
        if parent >= 0:
            self.obj(parent)
            p = parent
            while p >= 0:
                if p == h:
                    raise RuntimeError('The call failed on the V-REP side. Cyclic parenting.')
                p = self.objs[p].parent
        T_before = self.obj_T(h)
        old_parent = o.parent
        if parent >= 0 and self.objs[parent].name == 'Panda_gripper_attachPoint':
            # Grasped objects are rigidly attached in CoppeliaSim, so closing
            # fingers stall at the object's surface: hold them where they are
            # until the next gripper command.
            for jn in ('Panda_gripper_joint1', 'Panda_gripper_joint2'):
                if jn in self.by_name:
                    fj = self.objs[self.by_name[jn]]
                    fj.jstate.stalled = True
                    fj.jstate.lock_q = float(self.d.qpos[fj.jqadr])
        local_old = _inv(self.obj_T(old_parent)) @ T_before if old_parent >= 0 else T_before
        o.parent = parent
        self._rebuild_children()
        if not keep_in_place:
            T_new = (self.obj_T(parent) @ local_old) if parent >= 0 else local_old
            if o.free:
                self.set_obj_T(h, T_new, _update_follow=False)
        if o.free:
            o.mode = None
            self._update_mode(h, force=True)
        self._dirty = True
        self._apply_followers()

    def _followers(self):
        return [o for o in self.free_objs if o.mode == 'follow' and o.follow_rel is not None]

    def _physical_root(self, h):
        """Free body that physically carries object h (itself, or the movable it is welded into)."""
        o = self.objs[h]
        while o.kind == 'movable_child' and o.parent >= 0:
            o = self.objs[o.parent]
        return o if o.free else None

    def _apply_followers(self):
        fol = self._followers()
        if not fol:
            return
        self._fresh()
        follower_set = {o.handle for o in fol}
        computed = {}

        def world_of(h, depth=0):
            if h < 0:
                return np.eye(4)
            if h in computed:
                return computed[h]
            if depth > 32:
                return self.obj_T(h)
            o = self.objs[h]
            if h in follower_set:
                T = world_of(o.parent, depth + 1) @ o.follow_rel
            else:
                root = self._physical_root(h)
                if root is not None and root.handle != h and root.handle in follower_set:
                    rel = _inv(self.body_T(root.body)) @ self.obj_T(h)
                    T = world_of(root.handle, depth + 1) @ rel
                else:
                    T = self.obj_T(h)
            computed[h] = T
            return T

        for o in fol:
            T = world_of(o.handle)
            self.d.qpos[o.qadr:o.qadr + 3] = T[:3, 3]
            q = mat_to_quat_xyzw(T[:3, :3])
            self.d.qpos[o.qadr + 3:o.qadr + 7] = [q[3], q[0], q[1], q[2]]
            self.d.qvel[o.dadr:o.dadr + 6] = 0.0
        self._dirty = True

    # ------------------------------------------------------------------ joints
    def joint_position(self, h):
        o = self.obj(h)
        if o.joint is None:
            raise RuntimeError('The call failed on the V-REP side. Not a joint.')
        js = o.jstate
        if js.kinematic_arm:
            return float(self.arm_cmd[o.handle])
        return float(self.d.qpos[o.jqadr])

    def set_joint_position(self, h, value):
        o = self.obj(h)
        js = o.jstate
        value = float(value)
        if not js.cyclic:
            lo, hi = js.eff_range
            value = min(max(value, lo), hi)
        self.d.qpos[o.jqadr] = value
        self.d.qvel[o.jdadr] = 0.0
        if js.kinematic_arm:
            self.arm_cmd[o.handle] = value
        js.lock_q = value
        if o.name in ARM_JOINTS:
            self._arm_teleported = True
        self._dirty = True
        if not (o.name in ARM_JOINTS):
            self._mark_teleported_joint(o)
        ch = getattr(js, 'detachable', None)
        if ch is not None and self.objs[ch].mode == 'hinge' and getattr(self.objs[ch], 'hinge_rel', None) is not None:
            # Carry the welded child along immediately (CoppeliaSim moves the tree).
            self.set_obj_T(ch, self.body_T(o.body) @ self.objs[ch].hinge_rel, _update_follow=False)
        self._apply_followers()

    def _joint_controls(self):
        """CoppeliaSim joint motor model on MuJoCo position actuators.

        Each non-arm joint tracks a reference r with a stiff, force-limited
        servo. Position control moves r toward the target with CoppeliaSim's
        P-gain velocity law; velocity control integrates the target velocity
        into r (so a zero target brakes and a blocked joint pushes with its
        max force); a disabled motor makes the joint passive.
        """
        m, d = self.m, self.d
        h = m.opt.timestep
        pin = getattr(self, '_pin_arm', False)
        for o in self.native_joints:
            js = o.jstate
            if js.kinematic_arm:
                continue
            if pin and (o.name in ARM_JOINTS or any(fo is o for fo, _ in getattr(self, '_pinned_fingers', ()))):
                self._set_servo(o, 0.0, 0.0, js.lock_q, 0.0)
                continue
            if js.mode != C.sim_jointmode_force:
                d.qpos[o.jqadr] = js.lock_q
                d.qvel[o.jdadr] = 0.0
                if o.act >= 0:
                    self._set_servo(o, 0.0, 0.0, js.lock_q, 0.0)
                continue
            if o.act < 0:
                continue
            if not js.motor:
                self._set_servo(o, 0.0, 0.0, 0.0, 0.0)
                continue
            if js.ctrl:
                gain = (js.pid[0] or 0.1) / self.dt
                step = max(-js.vmax, min(js.vmax, gain * (js.target_pos - js.lock_q))) * h
                js.lock_q += step
            else:
                if not getattr(js, 'stalled', False):
                    js.lock_q += js.target_vel * h
            if not js.cyclic:
                lo, hi = js.eff_range
                js.lock_q = min(max(js.lock_q, lo - 0.002), hi + 0.002)
            self._set_servo(o, js.kp, js.kvd, js.lock_q, abs(js.max_force))

    def _set_servo(self, o, kp, kv, ref, fmax):
        m, d = self.m, self.d
        a = o.act
        m.actuator_gainprm[a, 0] = kp
        m.actuator_biasprm[a, 1] = -kp
        m.actuator_biasprm[a, 2] = -kv
        m.actuator_forcerange[a] = (-fmax, fmax) if fmax > 0 else (-1e-9, 1e-9)
        d.ctrl[a] = ref

    def _update_robot_servo_gains(self):
        """Size arm/finger servo gains from the *effective* joint inertia.

        In a serial chain the mass-matrix diagonal can exceed the effective
        (inverse-diagonal) inertia by an order of magnitude; gains sized from
        the diagonal make the explicit position servo unstable.
        """
        m, d = self.m, self.d
        robot = [o for o in self.native_joints if o.kind == 'robot']
        if not robot:
            return
        idx = [o.jdadr for o in robot]
        M = np.zeros((m.nv, m.nv))
        mujoco.mj_fullM(m, d, M)
        Ms = M[np.ix_(idx, idx)]
        try:
            eff = 1.0 / np.diag(np.linalg.inv(Ms))
        except np.linalg.LinAlgError:
            return
        omega = 2 * math.pi * SERVO_HZ
        for o, inertia in zip(robot, eff):
            inertia = max(float(inertia), 1e-4)
            o.jstate.kp = inertia * omega ** 2
            o.jstate.kvd = 2.0 * inertia * omega

    def _sleep_resting(self):
        """Hold resting free bodies in place (see SLEEP_RESTING)."""
        m, d = self.m, self.d
        free = getattr(self, '_free_joints', None)
        if free is None:
            free = [(int(m.jnt_qposadr[j]), int(m.jnt_dofadr[j]), int(m.jnt_bodyid[j]))
                    for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE]
            self._free_joints = free
            self._sleep_state = {}
            self._prev_xpos = d.xpos.copy()
        # Bodies that moved this substep (robot links, carried objects, lids, followers,
        # teleports): anything in contact with one of them wakes up.
        speed = np.linalg.norm(d.xpos - self._prev_xpos, axis=1) / m.opt.timestep
        self._prev_xpos = d.xpos.copy()
        moving = speed > SLEEP_LIN
        moving[0] = False
        touched = set()
        if d.ncon:
            b1 = m.geom_bodyid[d.contact.geom1[:d.ncon]]
            b2 = m.geom_bodyid[d.contact.geom2[:d.ncon]]
            touched.update(b2[moving[b1]].tolist())
            touched.update(b1[moving[b2]].tolist())
        state = self._sleep_state
        for qadr, dadr, body in free:
            lin = float(np.linalg.norm(d.qvel[dadr:dadr + 3]))
            ang = float(np.linalg.norm(d.qvel[dadr + 3:dadr + 6]))
            entry = state.get(qadr)
            if entry is not None and entry[1] is not None:            # asleep
                pose = entry[1]
                moved = float(np.max(np.abs(d.qpos[qadr:qadr + 7] - pose)))   # set_pose, followers
                if body in touched or lin > WAKE_LIN or ang > WAKE_ANG or moved > SLEEP_POSE_TOL:
                    state[qadr] = [0, None]
                    continue
                d.qpos[qadr:qadr + 7] = pose
                d.qvel[dadr:dadr + 6] = 0.0
                continue
            if body in touched or lin > SLEEP_LIN or ang > SLEEP_ANG:
                state[qadr] = [0, None]
                continue
            count = (entry[0] if entry else 0) + 1
            state[qadr] = [count, d.qpos[qadr:qadr + 7].copy() if count >= SLEEP_SUBSTEPS else None]

    def _robot_geoms(self):
        g = getattr(self, '_robot_geom_ids', None)
        if g is None:
            ids = [o.col_geoms for o in self.objs.values() if o.kind == 'robot' and len(o.col_geoms)]
            g = np.concatenate(ids) if ids else np.zeros(0, dtype=np.int64)
            self._robot_geom_ids = g
        return g

    def _set_robot_contact_softness(self, soft):
        """Teleported robot links correct penetration only weakly (CoppeliaSim)."""
        if getattr(self, '_robot_soft', False) == soft:
            return
        g = self._robot_geoms()
        m = self.m
        if soft:
            m.geom_solref[g] = self.KINEMATIC_SOLREF
            m.geom_solimp[g] = self.KINEMATIC_SOLIMP
            m.geom_solmix[g] = 100.0
        else:
            m.geom_solref[g] = self._orig_geom_solref[g]
            m.geom_solimp[g] = self._orig_geom_solimp[g]
            m.geom_solmix[g] = self._orig_geom_solmix[g]
        self._robot_soft = soft

    def _arm_kinematics(self, frac=1.0):
        d = self.d
        for o in self.arm_joints:
            d.qpos[o.jqadr] = self.arm_cmd[o.handle]
            d.qvel[o.jdadr] = 0.0
        # The gripper tree is teleported with the arm: pin the fingers too, or
        # the finger servos' reaction on the (light) hand makes them drift.
        h = self.m.opt.timestep
        pinned = getattr(self, '_pinned_fingers', [])
        for k, (o, q) in enumerate(pinned):
            js = o.jstate
            if js.target_vel > 0.0 and not getattr(js, 'stalled', False):
                # Opening motors keep running while the arm is teleported
                # (moving away from contacts, so kinematic motion is safe).
                lo, hi = js.eff_range
                q = min(q + js.target_vel * h, hi)
                pinned[k] = (o, q)
                js.lock_q = q
            d.qpos[o.jqadr] = q
            d.qvel[o.jdadr] = 0.0

    def _advance_arm_targets(self):
        for o in self.arm_joints:
            js = o.jstate
            cur = self.arm_cmd[o.handle]
            if js.mode == C.sim_jointmode_force and js.motor:
                if js.ctrl:
                    err = js.target_pos - cur
                    lim = js.vmax * self.dt
                    cur += max(-lim, min(lim, err))
                elif js.target_vel != 0.0:
                    cur += js.target_vel * self.dt
            if not js.cyclic:
                lo, rng = js.interval
                cur = min(max(cur, lo), lo + rng)
            self.arm_cmd[o.handle] = cur

    # ------------------------------------------------------------------ stepping
    # CoppeliaSim resolves overlaps created by teleported (kinematically moved)
    # static shapes only weakly; mirror that by softening a follower's contacts
    # while it is actually being moved, and restoring them once it rests.
    KINEMATIC_SOLREF = (0.15, 1.0)
    KINEMATIC_SOLIMP = (0.5, 0.95, 0.01, 0.5, 2.0)

    def _mark_teleported_joint(self, o):
        """Geoms physically carried by a joint that was just teleported."""
        m = self.m
        bodies = {o.body}
        changed = True
        while changed:
            changed = False
            for b in range(m.nbody):
                if b not in bodies and m.body_parentid[b] in bodies:
                    bodies.add(b)
                    changed = True
        geoms = np.where(np.isin(m.geom_bodyid, list(bodies)) & (m.geom_contype > 0))[0]
        self.__dict__.setdefault('_soft_geom_sets', {})[('joint', o.handle)] = geoms

    def _object_geoms(self, o):
        geoms = [o.col_geoms]
        for t in self._subtree_logical(o.handle):
            to = self.objs[t]
            if to.kind == 'movable_child':
                geoms.append(to.col_geoms)
        return np.concatenate(geoms) if geoms else np.zeros(0, dtype=np.int64)

    def _penetrating(self, geoms, depth=1e-3):
        d = self.d
        gs = set(int(g) for g in geoms)
        for i in range(d.ncon):
            c = d.contact[i]
            if (c.geom1 in gs or c.geom2 in gs) and c.dist < -depth:
                return True
        return False

    def _update_kinematic_softness(self):
        """Soft contacts for teleported shapes until their overlaps resolve."""
        m, d = self.m, self.d
        prev = getattr(self, '_follow_prev', {})
        soft = getattr(self, '_soft_objs', set())
        cur = {}
        for o in self.free_objs if SOFT_FOLLOWERS else ():
            if o.mode == 'follow':
                q = d.qpos[o.qadr:o.qadr + 7].copy()
                cur[o.handle] = q
                p = prev.get(o.handle)
                if p is not None and np.max(np.abs(q - p)) > 2e-5:
                    soft.add(o.handle)
        for h in list(soft):
            o = self.objs[h]
            geoms = self._object_geoms(o)
            moving = h in cur and h in prev and np.max(np.abs(cur[h] - prev[h])) > 2e-5
            if moving or self._penetrating(geoms):
                m.geom_solref[geoms] = self.KINEMATIC_SOLREF
                m.geom_solimp[geoms] = self.KINEMATIC_SOLIMP
                m.geom_solmix[geoms] = 100.0
            else:
                m.geom_solref[geoms] = self._orig_geom_solref[geoms]
                m.geom_solimp[geoms] = self._orig_geom_solimp[geoms]
                m.geom_solmix[geoms] = self._orig_geom_solmix[geoms]
                soft.discard(h)
        self._soft_objs = soft
        self._follow_prev = cur
        sets = getattr(self, '_soft_geom_sets', {})
        for key in list(sets):
            entry = sets[key]
            if isinstance(entry, dict):
                geoms, depth = entry['geoms'], entry['depth']
                entry['ttl'] -= 1
                alive = entry['ttl'] > 0
            else:
                geoms, depth, alive = entry, 1e-3, True
            if alive and len(geoms) and self._penetrating(geoms, depth):
                m.geom_solref[geoms] = self.KINEMATIC_SOLREF
                m.geom_solimp[geoms] = self.KINEMATIC_SOLIMP
                m.geom_solmix[geoms] = 100.0
            else:
                m.geom_solref[geoms] = self._orig_geom_solref[geoms]
                m.geom_solimp[geoms] = self._orig_geom_solimp[geoms]
                m.geom_solmix[geoms] = self._orig_geom_solmix[geoms]
                sets.pop(key)

    def step(self):
        m, d = self.m, self.d
        if not self.running:
            # CoppeliaSim only advances physics while the simulation runs.
            self._fresh()
            self._sync_viewer()
            return
        if KINEMATIC_ARM:
            self._advance_arm_targets()
        # CoppeliaSim: simSetJointPosition on a dynamic joint resets the link
        # dynamics for that step, so a teleported arm acts as light, pinned
        # links; the joint servos only act in steps without a teleport.
        pin_arm = KINEMATIC_ARM or getattr(self, '_arm_teleported', False)
        self._arm_teleported = False
        if pin_arm and not KINEMATIC_ARM:
            for o in self.arm_joints:
                self.arm_cmd[o.handle] = float(d.qpos[o.jqadr])
        self._pin_arm = pin_arm
        if not pin_arm:
            self._fresh()
            self._update_robot_servo_gains()
        # Robot contacts correct penetration weakly (CoppeliaSim/Bullet ERP).
        self._set_robot_contact_softness(SOFT_TELEPORT_ROBOT)
        self._pinned_fingers = []
        if pin_arm and not KINEMATIC_ARM:
            for jn in ('Panda_gripper_joint1', 'Panda_gripper_joint2'):
                if jn in self.by_name:
                    fo = self.objs[self.by_name[jn]]
                    self._pinned_fingers.append((fo, float(d.qpos[fo.jqadr])))
        if SOFT_KINEMATIC_CONTACTS:
            self._update_kinematic_softness()
        for _ in range(self.nsub):
            if pin_arm:
                self._arm_kinematics()
            self._apply_followers()
            self._joint_controls()
            mujoco.mj_step(m, d)
            if SLEEP_RESTING:
                self._sleep_resting()
            self._dirty = True
        if pin_arm:
            self._arm_kinematics()
        self._apply_followers()
        self._dirty = True
        self._fresh()
        self.sim_time += self.dt
        for o in self.objs.values():
            if o.vision is not None and not o.explicit:
                o.images = {}
        self._sync_viewer()

    def _sync_viewer(self):
        if self.viewer is None:
            return
        try:
            if not self.viewer.is_running():
                return
            now = time.monotonic()
            if now - getattr(self, '_viewer_last', 0.0) < 1.0 / 60.0:
                return
            self._viewer_last = now
            self.viewer.sync()
        except Exception:
            self.viewer = None

    def start(self):
        self.running = True

    def stop(self):
        if self.running:
            self.running = False
            self._init_state()

    def close(self):
        try:
            self.renderer.close()
        except Exception:
            pass
        if self.viewer is not None:
            try:
                self.viewer.close()
            except Exception:
                pass
            self.viewer = None

    # ------------------------------------------------------------------ collision
    def entity_geoms(self, e, only_collidable=False):
        """(geom ids, member object handles) for an entity handle."""
        e = int(e)
        if e == C.sim_handle_all:
            hs = [h for h, o in self.objs.items() if o.shape is not None and self.is_collidable(h)]
        elif e in self.collections:
            hs = [h for h in self.collection_members(e) if self.objs[h].shape is not None and self.is_collidable(h)]
        else:
            o = self.obj(e)
            hs = [e] if o.shape is not None and (not only_collidable or self.is_collidable(e)) else []
        geoms = [self.objs[h].col_geoms for h in hs]
        g = np.concatenate(geoms) if geoms else np.zeros(0, dtype=np.int64)
        return g, set(hs)

    def collection_members(self, ch):
        c = self.collections[ch]
        if c['root'] is not None:
            return self._subtree_logical(c['root'])
        return list(c['static'])

    def _geom_pairs_colliding(self, A, B, first_only=True, margin=0.0):
        if len(A) == 0 or len(B) == 0:
            return []
        self._fresh()
        d, m = self.d, self.m
        pa = d.geom_xpos[A]
        pb = d.geom_xpos[B]
        ra = m.geom_rbound[A]
        rb = m.geom_rbound[B]
        dist = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=-1)
        cand = np.argwhere(dist <= (ra[:, None] + rb[None, :] + margin))
        hits = []
        for i, j in cand:
            ga, gb = int(A[i]), int(B[j])
            if ga == gb:
                continue
            dd = mujoco.mj_geomDistance(m, d, ga, gb, margin + 1e-3, None)
            if dd < margin - 1e-6:
                hits.append((ga, gb, dd))
                if first_only:
                    return hits
        return hits

    def check_collision(self, e1, e2):
        A, hs1 = self.entity_geoms(e1)
        if int(e2) == C.sim_handle_all:
            B, hs2 = self.entity_geoms(e2)
            excl = hs1
            if int(e1) in self.collections:
                excl = set(self.collection_members(int(e1)))
            keep = [h for h in hs2 if h not in excl]
            B = np.concatenate([self.objs[h].col_geoms for h in keep]) if keep else np.zeros(0, dtype=np.int64)
        else:
            B, hs2 = self.entity_geoms(e2)
            if int(e2) in self.collections and int(e1) not in self.collections:
                pass
        return 1 if self._geom_pairs_colliding(A, B) else 0

    def arm_in_collision(self, collision_pairs):
        """Evaluate CoppeliaSim collision pairs [e1, e2, e1, e2, ...]."""
        for k in range(0, len(collision_pairs) - 1, 2):
            if self.check_collision(collision_pairs[k], collision_pairs[k + 1]):
                return True
        return False

    def check_distance(self, e1, e2, threshold):
        A, _ = self.entity_geoms(e1)
        B, _ = self.entity_geoms(e2)
        self._fresh()
        best = None
        ft = np.zeros(6)
        dmax = threshold if threshold > 0 else 10.0
        for ga in A:
            for gb in B:
                if ga == gb:
                    continue
                dd = mujoco.mj_geomDistance(self.m, self.d, int(ga), int(gb), dmax, ft)
                if best is None or dd < best[0]:
                    best = (dd, ft.copy())
        if best is None:
            return [0.0] * 6 + [dmax]
        return list(best[1]) + [max(0.0, best[0])]

    def proximity_detect(self, sensor_h, entity_h):
        s = self.obj(sensor_h)
        if s.vol_geom < 0:
            return 0, [0.0, 0.0, 0.0]
        targets = []
        if int(entity_h) == C.sim_handle_all:
            targets = [h for h, o in self.objs.items() if o.shape is not None and self.is_detectable(h)
                       and h not in self._subtree_logical(self.by_name.get('Panda', -1))]
        else:
            e = self.obj(entity_h)
            # An explicitly named entity is checked regardless of its
            # 'detectable' flags (verified against CoppeliaSim 4.1).
            if e.shape is None:
                return 0, [0.0, 0.0, 0.0]
            targets = [int(entity_h)]
        self._fresh()
        ft = np.zeros(6)
        Ts = self.obj_T(sensor_h)
        best = None
        for h in targets:
            to = self.objs[h]
            geoms = to.col_geoms if len(to.col_geoms) else to.vis_geoms
            for g in geoms:
                dd = mujoco.mj_geomDistance(self.m, self.d, int(s.vol_geom), int(g), 0.01, ft)
                if dd <= 0.0:
                    p = ft[3:6]
                    pl = _inv(Ts) @ np.r_[p, 1.0]
                    dist = float(np.linalg.norm(pl[:3]))
                    if best is None or dist < best[0]:
                        best = (dist, pl[:3].tolist(), h)
        if best is None:
            return 0, [0.0, 0.0, 0.0]
        return 1, best[1]

    # ------------------------------------------------------------------ IK
    def arm_q(self):
        if KINEMATIC_ARM:
            return np.array([self.arm_cmd[o.handle] for o in self.arm_joints])
        return np.array([float(self.d.qpos[o.jqadr]) for o in self.arm_joints])

    def set_arm_q(self, q):
        for o, v in zip(self.arm_joints, q):
            self.arm_cmd[o.handle] = float(v)
            self.d.qpos[o.jqadr] = float(v)
            self.d.qvel[o.jdadr] = 0.0
            o.jstate.lock_q = float(v)
        self._arm_teleported = True
        self._dirty = True
        self._apply_followers()

    def _chain_with_base(self):
        """Arm chain with the current base pose (the robot base may be moved)."""
        base_now = self.body_T(self.chain_base_body)
        if not np.allclose(base_now, self.chain_base_T0, atol=1e-9):
            corr = base_now @ _inv(self.chain_base_T0)
            ch = ArmChain(corr @ self.chain.base_T, self.chain.links, self.chain.refs,
                          self.chain.tip_T, self.chain.lows, self.chain.highs)
            return ch
        return self.chain

    def ik_target_T(self):
        return self.obj_T(self.by_name['Panda_target'])

    def _collision_fn(self, collision_pairs):
        if not collision_pairs:
            return None
        saved = self.arm_q()
        saved_ref = [o.jstate.lock_q for o in self.arm_joints]
        saved_vel = [float(self.d.qvel[o.jdadr]) for o in self.arm_joints]

        def fn(q):
            self.set_arm_q(q)
            hit = self.arm_in_collision(collision_pairs)
            return hit

        def restore():
            self.set_arm_q(saved)
            for o, r, v in zip(self.arm_joints, saved_ref, saved_vel):
                o.jstate.lock_q = r
                self.d.qvel[o.jdadr] = v
        fn.restore = restore
        return fn

    def config_for_tip_pose(self, joint_handles, max_time_ms, collision_pairs, lows, ranges):
        """One simGetConfigForTipPose call: returns a config list or []."""
        if self.chain is None:
            return []
        chain = self._chain_with_base()
        target = self.ik_target_T()
        # CoppeliaSim semantics: joint search interval is [low, low + range].
        if lows is not None and ranges is not None:
            lo_in = np.asarray(lows, dtype=float)
            hi_in = lo_in + np.asarray(ranges, dtype=float)
            lows = np.maximum(lo_in, chain.lows)
            highs = np.minimum(hi_in, chain.highs)
        else:
            lows, highs = chain.lows, chain.highs
        key = (tuple(np.round(target[:3, :].ravel(), 5)), bool(collision_pairs), tuple(np.round(self.arm_q(), 4)) if collision_pairs else None)
        memo = self._ik_fail_memo.setdefault(key, {'tried': 0, 'found': 0})
        if memo['tried'] >= 384 and memo['found'] == 0:
            return []
        self._rng_calls['ik'] = self._rng_calls.get('ik', 0) + 1
        rng = trial_rng('ik', self._rng_calls['ik'])
        q_cur = self.arm_q()
        budget = time.monotonic() + max(0.005, min(float(max_time_ms), 250.0) / 1000.0)
        coll = self._collision_fn(collision_pairs)
        first = memo['tried'] == 0
        result = []
        try:
            while True:
                n = 48
                seeds = rng.uniform(lows, highs, size=(n, len(lows)))
                if first:
                    seeds[0] = np.clip(q_cur, lows, highs)
                    first = False
                Q, conv, err = chain.solve(seeds, target, iters=70, lows=lows, highs=highs)
                memo['tried'] += n
                idx = np.where(conv)[0]
                if len(idx):
                    # Prefer solutions close to the current configuration, but
                    # penalise ones hugging joint limits (they make the
                    # follow-up linear paths infeasible).
                    dist = np.linalg.norm(Q[idx] - q_cur, axis=1)
                    margin = limit_margin(Q[idx], lows, highs)
                    score = dist + 4.0 * np.maximum(0.0, 0.08 - margin) / 0.08
                    idx = idx[np.argsort(score)]
                    for i in idx:
                        if coll is not None and coll(Q[i]):
                            continue
                        result = Q[i].tolist()
                        break
                if result or time.monotonic() > budget or memo['tried'] >= 384:
                    break
        finally:
            if coll is not None:
                coll.restore()
        if result:
            memo['found'] += 1
        return result

    def ik_path(self, joint_handles, steps, collision_pairs):
        if self.chain is None:
            return []
        chain = self._chain_with_base()
        target = self.ik_target_T()
        coll = self._collision_fn(collision_pairs)
        try:
            path = linear_ik_path(chain, self.arm_q(), target, steps, coll)
        finally:
            if coll is not None:
                coll.restore()
        if path is None:
            return []
        return path.ravel().tolist()

    def check_ik_group(self, joint_handles):
        if self.chain is None:
            return C.sim_ikresult_not_performed, self.arm_q().tolist()
        chain = self._chain_with_base()
        Q, conv, _ = chain.solve(self.arm_q()[None], self.ik_target_T(), iters=100)
        return (C.sim_ikresult_success if conv[0] else C.sim_ikresult_fail), Q[0].tolist()

    def nonlinear_path(self, collection, ignore_collisions, trials_per_goal, joint_handles, configs, algorithm):
        if self.chain is None:
            return []
        goals = np.asarray(configs, dtype=float).reshape(-1, len(joint_handles))
        pairs = [] if ignore_collisions else [collection, C.sim_handle_all]
        coll = self._collision_fn(pairs)
        try:
            self._rng_calls['rrt'] = self._rng_calls.get('rrt', 0) + 1
            path = rrt_connect(self.arm_q(), list(goals), self.chain.lows, self.chain.highs, coll,
                               max_time_s=float(os.environ.get('MUJOCO_SHIM_RRT_TIME', '2.0')),
                               rng=trial_rng('rrt', self._rng_calls['rrt']))
        finally:
            if coll is not None:
                coll.restore()
        if path is None:
            return []
        return path.ravel().tolist()

    # ------------------------------------------------------------------ vision
    def vision_capture(self, h, kind):
        o = self.obj(h)
        if o.vision is None:
            raise RuntimeError('The call failed on the V-REP side. Not a vision sensor.')
        if kind not in o.images:
            self._render_sensor(o, kinds=(kind,))
        return o.images.get(kind)

    def handle_vision_sensor(self, h):
        o = self.obj(h)
        if o.vision is None:
            raise RuntimeError('The call failed on the V-REP side. Not a vision sensor.')
        o.images = {}
        self._render_sensor(o, kinds=('rgb',))
        return 1

    def _render_sensor(self, o, kinds):
        v = o.vision
        w, h = v['resolution']
        self._fresh()
        mujoco.mj_camlight(self.m, self.d)
        near = float(v.get('near') or 0.01)
        far = float(v.get('far') or 10.0)
        coded = int(v.get('render_mode') or 0) == C.sim_rendermode_colorcoded
        for kind in kinds:
            if kind == 'rgb':
                o.images['rgb'] = self.renderer.render(self.d, o.cam, w, h, mode='coded' if coded else 'rgb')
            elif kind == 'depth':
                o.images['depth'] = self.renderer.render(self.d, o.cam, w, h, mode='depth', near=near, far=far)

    def update_camera_fov(self, o):
        v = o.vision
        pa = v.get('perspective_angle') or math.radians(60)
        w, h = v['resolution']
        fy = 2 * math.atan(math.tan(pa / 2) * h / w) if w >= h else pa
        self.m.cam_fovy[o.cam] = math.degrees(fy)
