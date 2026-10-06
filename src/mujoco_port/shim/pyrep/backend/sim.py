"""CoppeliaSim C-API surface (as exposed by PyRep's backend) on top of MuJoCo.

Function names, argument orders, return shapes and error behaviour follow
PyRep 4.1's cffi wrapper so that PyRep's Python layer and user code calling
``sim.simXxx`` directly behave the same. Anything with no MuJoCo meaning
(UI thread management, scripts, octrees, ...) is a no-op or raises the same
RuntimeError CoppeliaSim would for an unsupported call.
"""

from __future__ import annotations

import math
from collections import namedtuple

import numpy as np

from .simConst import *  # noqa: F401,F403
from . import simConst as C
from ._kin import mat_to_quat_xyzw, quat_xyzw_to_mat
from ._world import (COLLECTION_HANDLE_BASE, DRAWING_HANDLE_BASE, IK_GROUP_HANDLE_BASE,
                     World, _inv, euler_to_mat, mat_to_euler)

_WORLD: World | None = None


def _set_world(world):
    global _WORLD
    _WORLD = world


def _w() -> World:
    if _WORLD is None:
        raise RuntimeError('The call failed on the V-REP side. No scene loaded (call PyRep.launch first).')
    return _WORLD


def _fail(msg=''):
    raise RuntimeError('The call failed on the V-REP side. Return value: -1' + (f' ({msg})' if msg else ''))


def _check_return(ret):
    if ret < 0:
        raise RuntimeError('The call failed on the V-REP side. Return value: %d' % ret)


def _check_null_return(val):
    if val is None:
        raise RuntimeError('The call failed on the V-REP side by returning null.')


# ---------------------------------------------------------------- lifecycle
def simExtLaunchUIThread(options, scene, pyrep_root):
    return None


def simExtSimThreadInit():
    return None


def simExtCanInitSimThread():
    return True


def simExtSimThreadDestroy():
    return None


def simExtPostExitRequest():
    return None


def simExtGetExitRequest():
    return False


def simExtStep(update=True):
    if _WORLD is not None and update:
        _WORLD.step()


def simStartSimulation():
    _w().start()
    return 1


def simStopSimulation():
    _w().stop()
    return 1


def simPauseSimulation():
    _w().running = False
    return 1


def simQuitSimulator(do_not_display_messages=True):
    return None


def simGetSimulationTimeStep():
    return _w().dt


def simGetSimulationTime():
    return _w().sim_time


def simSetFloatParameter(parameter, value):
    if parameter == C.sim_floatparam_simulation_time_step:
        return None
    return None


def simGetFloatParameter(parameter):
    if parameter == C.sim_floatparam_simulation_time_step:
        return _w().dt
    return 0.0


def simSetStringParameter(parameter, value):
    if _WORLD is not None:
        _WORLD.string_params[parameter] = value


def simGetStringParameter(parameter):
    if parameter == C.sim_stringparam_scene_path_and_name:
        return str(_w().scene_file)
    return (_WORLD.string_params.get(parameter, '') if _WORLD else '')


def simSetBoolParameter(parameter, value):
    return None


def simGetBoolParameter(parameter):
    return False


def simSetInt32Parameter(parameter, value):
    return None


def simGetInt32Parameter(parameter):
    return 0


def simGetArrayParameter(parameter):
    if parameter == C.sim_arrayparam_gravity:
        return list(_w().m.opt.gravity)
    return [0.0, 0.0, 0.0]


def simSetArrayParameter(parameter, value):
    if parameter == C.sim_arrayparam_gravity:
        _w().m.opt.gravity[:] = value


# ---------------------------------------------------------------- objects
def simGetObjectHandle(objectName):
    return _w().handle_of(objectName)


def simGetObjectName(objectHandle):
    o = _WORLD.objs.get(int(objectHandle)) if _WORLD else None
    if o is None:
        return ''
    return o.name


def simSetObjectName(objectHandle, name):
    w = _w()
    o = w.obj(objectHandle)
    w.by_name.pop(o.name, None)
    o.name = name
    w.by_name[name] = o.handle


def simGetObjectType(objectHandle):
    return _w().obj(objectHandle).type_id


def simGetObjects(index, objectType):
    w = _w()
    hs = [h for h in w.order if objectType == C.sim_handle_all or w.objs[h].type_id == objectType]
    if 0 <= index < len(hs):
        return hs[index]
    return -1


def simGetObjectsInTree(treeBaseHandle, objectType, options):
    return _w().objects_in_tree(treeBaseHandle, objectType, options)


def simGetObjectParent(childObjectHandle):
    p = _w().obj(childObjectHandle).parent
    _check_return(p)
    return p


def simGetObjectChild(parentObjectHandle, childIndex):
    ch = _w().children.get(int(parentObjectHandle), [])
    if 0 <= childIndex < len(ch):
        return ch[childIndex]
    return -1


def simSetObjectParent(objectHandle, parentObject, keepInPlace):
    _w().set_parent(int(objectHandle), int(parentObject) if parentObject is not None else -1, bool(keepInPlace))


def _rel(rel):
    return None if rel is None or int(rel) < 0 else int(rel)


def simGetObjectPosition(objectHandle, relativeToObjectHandle):
    T = _w().rel_T(int(objectHandle), _rel(relativeToObjectHandle))
    return T[:3, 3].tolist()


def simGetObjectQuaternion(objectHandle, relativeToObjectHandle):
    T = _w().rel_T(int(objectHandle), _rel(relativeToObjectHandle))
    return mat_to_quat_xyzw(T[:3, :3]).tolist()


def simGetObjectOrientation(objectHandle, relativeToObjectHandle):
    T = _w().rel_T(int(objectHandle), _rel(relativeToObjectHandle))
    return mat_to_euler(T[:3, :3])


def simGetObjectMatrix(objectHandle, relativeToObjectHandle):
    T = _w().rel_T(int(objectHandle), _rel(relativeToObjectHandle))
    return T[:3, :4].reshape(12).tolist()


def _set_world_T_from_rel(h, rel, T_rel, reset=True):
    w = _w()
    rel = _rel(rel)
    T = (w.obj_T(rel) @ T_rel) if rel is not None else T_rel
    w.set_obj_T(int(h), T, reset_dynamics=reset)


def simSetObjectPosition(objectHandle, relativeToObjectHandle, position):
    w = _w()
    rel = _rel(relativeToObjectHandle)
    T = w.rel_T(int(objectHandle), rel)
    T[:3, 3] = list(position)
    _set_world_T_from_rel(objectHandle, rel, T)


def simSetObjectQuaternion(objectHandle, relativeToObjectHandle, quaternion):
    w = _w()
    rel = _rel(relativeToObjectHandle)
    T = w.rel_T(int(objectHandle), rel)
    T[:3, :3] = quat_xyzw_to_mat(quaternion)
    _set_world_T_from_rel(objectHandle, rel, T)


def simSetObjectOrientation(objectHandle, relativeToObjectHandle, eulerAngles):
    w = _w()
    rel = _rel(relativeToObjectHandle)
    T = w.rel_T(int(objectHandle), rel)
    T[:3, :3] = euler_to_mat(eulerAngles)
    _set_world_T_from_rel(objectHandle, rel, T)


def simSetObjectMatrix(objectHandle, relativeToObjectHandle, matrix):
    M = np.eye(4)
    M[:3, :4] = np.asarray(matrix, dtype=float).reshape(3, 4)
    # Orthonormalise (callers sometimes pass slightly skewed matrices).
    U, _, Vt = np.linalg.svd(M[:3, :3])
    M[:3, :3] = U @ Vt
    _set_world_T_from_rel(objectHandle, relativeToObjectHandle, M)


def simGetObjectVelocity(objectHandle):
    import mujoco
    w = _w()
    o = w.obj(objectHandle)
    res = np.zeros(6)
    mujoco.mj_objectVelocity(w.m, w.d, mujoco.mjtObj.mjOBJ_BODY, o.body, res, 0)
    return res[3:].tolist(), res[:3].tolist()


def simResetDynamicObject(objectHandle):
    _w().reset_dynamic_object(objectHandle)


def simRemoveObject(objectHandle):
    _fail('removing objects is not supported in the MuJoCo backend')


def simRemoveModel(objectHandle):
    _fail('removing models is not supported in the MuJoCo backend')


def simGetObjectSpecialProperty(objectHandle):
    return _w().obj(objectHandle).sp


def simSetObjectSpecialProperty(objectHandle, prop):
    w = _w()
    w.obj(objectHandle).sp = int(prop)
    w.refresh_flags(int(objectHandle))


def simGetModelProperty(objectHandle):
    return _w().obj(objectHandle).mp


def simSetModelProperty(objectHandle, prop):
    w = _w()
    w.obj(objectHandle).mp = int(prop)
    w.refresh_flags(int(objectHandle))


def simGetExplicitHandling(objectHandle):
    return _w().obj(objectHandle).explicit


def simSetExplicitHandling(objectHandle, explicitFlags):
    _w().obj(objectHandle).explicit = int(explicitFlags)


def simGetObjectFloatParameter(objectHandle, parameter):
    w = _w()
    o = w.obj(objectHandle)
    p = int(parameter)
    if 15 <= p <= 20:
        return float(o.bbox_params[p - 15])
    if 21 <= p <= 26:
        return float(_model_bbox(o.handle)[p - 21])
    if o.vision is not None:
        v = o.vision
        if p == C.sim_visionfloatparam_near_clipping:
            return float(v.get('near') or 0.01)
        if p == C.sim_visionfloatparam_far_clipping:
            return float(v.get('far') or 10.0)
        if p == C.sim_visionfloatparam_perspective_angle:
            return float(v.get('perspective_angle') or math.radians(60))
        if p == C.sim_visionfloatparam_ortho_size:
            return float(v.get('ortho_size') or 1.0)
    if o.joint is not None:
        js = o.jstate
        if p == C.sim_jointfloatparam_velocity:
            if js.native and not js.kinematic_arm:
                return float(w.d.qvel[o.jdadr])
            return 0.0
        if p == C.sim_jointfloatparam_upper_limit:
            return js.vmax
        if p in (C.sim_jointfloatparam_pid_p, C.sim_jointfloatparam_pid_i, C.sim_jointfloatparam_pid_d):
            return float(js.pid[p - C.sim_jointfloatparam_pid_p])
    if o.shape is not None and p == C.sim_shapefloatparam_mass:
        return o.mass
    _fail(f'float parameter {p} not available for {o.name}')


def _model_bbox(h):
    w = _w()
    pts = []
    Tb = w.obj_T(h)
    Tinv = _inv(Tb)
    for t in w._subtree_logical(h):
        o = w.objs[t]
        if o.shape is None:
            continue
        b = o.bbox
        T = Tinv @ w.obj_T(t)
        for x in (b[0], b[1]):
            for y in (b[2], b[3]):
                for z in (b[4], b[5]):
                    pts.append((T @ np.array([x, y, z, 1.0]))[:3])
    if not pts:
        return [0.0] * 6
    pts = np.array(pts)
    mn, mx = pts.min(0), pts.max(0)
    return [mn[0], mn[1], mn[2], mx[0], mx[1], mx[2]]


def simSetObjectFloatParameter(objectHandle, parameter, value):
    w = _w()
    o = w.obj(objectHandle)
    p = int(parameter)
    if o.vision is not None:
        v = o.vision
        if p == C.sim_visionfloatparam_near_clipping:
            v['near'] = float(value)
            return 1
        if p == C.sim_visionfloatparam_far_clipping:
            v['far'] = float(value)
            return 1
        if p == C.sim_visionfloatparam_perspective_angle:
            v['perspective_angle'] = float(value)
            w.update_camera_fov(o)
            return 1
        if p == C.sim_visionfloatparam_ortho_size:
            v['ortho_size'] = float(value)
            return 1
    if o.joint is not None:
        js = o.jstate
        if p == C.sim_jointfloatparam_upper_limit:
            js.vmax = float(value)
            return 1
        if p in (C.sim_jointfloatparam_pid_p, C.sim_jointfloatparam_pid_i, C.sim_jointfloatparam_pid_d):
            js.pid[p - C.sim_jointfloatparam_pid_p] = float(value)
            return 1
    if o.shape is not None and p == C.sim_shapefloatparam_mass:
        o.mass = float(value)
        if o.free:
            w.m.body_mass[o.body] = max(float(value), 1e-4)
        return 1
    return 1


def simGetObjectInt32Parameter(objectHandle, parameter):
    w = _w()
    o = w.obj(objectHandle)
    p = int(parameter)
    if p == C.sim_objintparam_visibility_layer:
        return o.layer
    if o.shape is not None:
        if p == C.sim_shapeintparam_static:
            return 1 if o.static else 0
        if p == C.sim_shapeintparam_respondable:
            return 1 if o.respondable else 0
        if p == C.sim_shapeintparam_respondable_mask:
            return o.resp_mask
    if o.vision is not None:
        v = o.vision
        if p == C.sim_visionintparam_resolution_x:
            return int(v['resolution'][0])
        if p == C.sim_visionintparam_resolution_y:
            return int(v['resolution'][1])
        if p == C.sim_visionintparam_render_mode:
            return int(v.get('render_mode') or 0)
        if p == C.sim_visionintparam_perspective_operation:
            return int(v.get('perspective') if v.get('perspective') is not None else 1)
        if p in (C.sim_visionintparam_windowed_size_x, C.sim_visionintparam_windowed_size_y):
            return int(v.get('windowed', [0, 0])[p - C.sim_visionintparam_windowed_size_x])
        if p == C.sim_visionintparam_entity_to_render:
            return int(v.get('entity_to_render', -1))
    if o.joint is not None:
        js = o.jstate
        if p == C.sim_jointintparam_motor_enabled:
            return 1 if js.motor else 0
        if p == C.sim_jointintparam_ctrl_enabled:
            return 1 if js.ctrl else 0
        if p == C.sim_jointintparam_velocity_lock:
            return 1 if js.vlock else 0
    _fail(f'int parameter {p} not available for {o.name}')


def simSetObjectInt32Parameter(objectHandle, parameter, value):
    w = _w()
    o = w.obj(objectHandle)
    p = int(parameter)
    if p == C.sim_objintparam_visibility_layer:
        o.layer = int(value)
        return 1
    if o.shape is not None:
        if p == C.sim_shapeintparam_static:
            o.static = bool(value)
            w.refresh_flags(o.handle)
            return 1
        if p == C.sim_shapeintparam_respondable:
            o.respondable = bool(value)
            w.refresh_flags(o.handle)
            return 1
        if p == C.sim_shapeintparam_respondable_mask:
            o.resp_mask = int(value)
            return 1
    if o.vision is not None:
        v = o.vision
        if p == C.sim_visionintparam_resolution_x:
            v['resolution'] = [int(value), int(v['resolution'][1])]
            w.update_camera_fov(o)
            return 1
        if p == C.sim_visionintparam_resolution_y:
            v['resolution'] = [int(v['resolution'][0]), int(value)]
            w.update_camera_fov(o)
            return 1
        if p == C.sim_visionintparam_render_mode:
            v['render_mode'] = int(value)
            o.images = {}
            return 1
        if p == C.sim_visionintparam_perspective_operation:
            v['perspective'] = int(value)
            return 1
        if p in (C.sim_visionintparam_windowed_size_x, C.sim_visionintparam_windowed_size_y):
            win = list(v.get('windowed', [0, 0]))
            win[p - C.sim_visionintparam_windowed_size_x] = int(value)
            v['windowed'] = win
            return 1
        if p == C.sim_visionintparam_entity_to_render:
            v['entity_to_render'] = int(value)
            return 1
    if o.joint is not None:
        js = o.jstate
        if p == C.sim_jointintparam_motor_enabled:
            js.motor = bool(value)
            return 1
        if p == C.sim_jointintparam_ctrl_enabled:
            js.ctrl = bool(value)
            return 1
        if p == C.sim_jointintparam_velocity_lock:
            js.vlock = bool(value)
            if js.vlock:
                js.lock_q = w.joint_position(o.handle)
            return 1
    return 1


def simGetObjectSizeFactor(objectHandle):
    return 1.0


def simScaleObject(handle, x, y, z, options=0):
    _fail('scaling objects is not supported in the MuJoCo backend')


def simScaleObjects(handles, factor, positions):
    _fail('scaling objects is not supported in the MuJoCo backend')


def simGetExtensionString(objectHandle, index, key):
    return ''


def simGetConfigurationTree(objectHandle):
    w = _w()
    return (w.d.qpos.copy(), w.d.qvel.copy(), dict(w.arm_cmd))


def simSetConfigurationTree(data):
    w = _w()
    qpos, qvel, arm = data
    w.d.qpos[:] = qpos
    w.d.qvel[:] = qvel
    w.arm_cmd.update(arm)
    w._dirty = True


def simCopyPasteObjects(objectHandles, options):
    _fail('copy/paste is not supported in the MuJoCo backend')


def simGetContactInfo(contact_obj_handle, get_contact_normal):
    import mujoco
    w = _w()
    o = w.obj(contact_obj_handle)
    geoms = set(int(g) for g in o.col_geoms)
    out = []
    ft = np.zeros(6)
    for i in range(w.d.ncon):
        c = w.d.contact[i]
        if c.geom1 in geoms or c.geom2 in geoms:
            other = c.geom2 if c.geom1 in geoms else c.geom1
            f6 = np.zeros(6)
            mujoco.mj_contactForce(w.m, w.d, i, f6)
            frame = c.frame.reshape(3, 3)
            fw = frame.T @ f6[:3]
            vals = list(c.pos) + list(fw)
            if get_contact_normal:
                vals += list(frame[0])
            out.append({'contact': vals,
                        'contact_handles': [int(contact_obj_handle), int(w.geom_handle[other])]})
    return out


# ---------------------------------------------------------------- shapes
def simGetShapeColor(shapeHandle, colorName, colorComponent):
    o = _w().obj(shapeHandle)
    if colorComponent == C.sim_colorcomponent_transparency:
        return [o.transparency, 0.0, 0.0]
    return list(o.color)


def simSetShapeColor(shapeHandle, colorName, colorComponent, rgbData):
    w = _w()
    o = w.obj(shapeHandle)
    if colorComponent == C.sim_colorcomponent_transparency:
        o.transparency = float(rgbData[0])
        for g in list(o.vis_geoms):
            w.m.geom_rgba[g, 3] = 1.0 - o.transparency
        return
    o.color = [float(c) for c in rgbData[:3]]
    for g in list(o.vis_geoms):
        if w.m.geom_matid[g] < 0:
            w.m.geom_rgba[g, :3] = o.color


def simGetShapeMesh(shapeHandle):
    import mujoco
    w = _w()
    o = w.obj(shapeHandle)
    verts, inds = [], []
    base = 0
    Tinv = _inv(w.obj_T(o.handle))
    for g in list(o.col_geoms) + list(o.vis_geoms):
        mid = w.m.geom_dataid[g]
        if w.m.geom_type[g] != mujoco.mjtGeom.mjGEOM_MESH or mid < 0:
            continue
        va = w.m.mesh_vertadr[mid]
        vn = w.m.mesh_vertnum[mid]
        fa = w.m.mesh_faceadr[mid]
        fn = w.m.mesh_facenum[mid]
        v = w.m.mesh_vert[va:va + vn]
        Tg = np.eye(4)
        w._fresh()
        Tg[:3, :3] = w.d.geom_xmat[g].reshape(3, 3)
        Tg[:3, 3] = w.d.geom_xpos[g]
        T = Tinv @ Tg
        vl = (T[:3, :3] @ v.T).T + T[:3, 3]
        verts.extend(vl.ravel().tolist())
        inds.extend((w.m.mesh_face[fa:fa + fn] + base).ravel().tolist())
        base += vn
    return verts, inds, [0.0] * len(inds) * 3


def simGetShapeTextureId(shapeHandle):
    return -1


def simSetShapeTexture(*args, **kwargs):
    return None


def simGetShapeViz(shapeHandle, index):
    _fail('shape viz data is not available in the MuJoCo backend')


def simGroupShapes(handles, merge=False):
    _fail('grouping shapes is not supported in the MuJoCo backend')


def simUngroupShape(handle):
    _fail('ungrouping shapes is not supported in the MuJoCo backend')


def simReorientShapeBoundingBox(handle, relativeTo):
    return None


def simCreatePureShape(*args, **kwargs):
    _fail('creating shapes at runtime is not supported in the MuJoCo backend')


def simCreateMeshShape(*args, **kwargs):
    _fail('creating shapes at runtime is not supported in the MuJoCo backend')


def simCreateDummy(*args, **kwargs):
    _fail('creating dummies at runtime is not supported in the MuJoCo backend')


def simImportShape(*args, **kwargs):
    _fail('importing shapes is not supported in the MuJoCo backend')


def simImportMesh(*args, **kwargs):
    _fail('importing meshes is not supported in the MuJoCo backend')


def simComputeMassAndInertia(shapeHandle, density):
    return 1


def simAddForce(shapeHandle, position, force):
    w = _w()
    o = w.obj(shapeHandle & 0xFFFFFF)
    import mujoco
    mujoco.mj_applyFT(w.m, w.d, np.asarray(force, float), np.zeros(3), np.asarray(position, float), o.body, w.d.qfrc_applied)


def simAddForceAndTorque(shapeHandle, force, torque):
    w = _w()
    o = w.obj(shapeHandle & 0xFFFFFF)
    w.d.xfrc_applied[o.body, :3] += np.asarray(force if force is not None else [0, 0, 0], float)
    w.d.xfrc_applied[o.body, 3:] += np.asarray(torque if torque is not None else [0, 0, 0], float)


def simGetEngineFloatParameter(paramId, objectHandle):
    return 1.0


def simSetEngineFloatParameter(paramId, objectHandle, val):
    return None


# ---------------------------------------------------------------- joints
def _joint(h):
    o = _w().obj(h)
    if o.joint is None:
        _fail('object is not a joint')
    return o


def simGetJointType(objectHandle):
    return _joint(objectHandle).jstate.jtype


def simGetJointPosition(jointHandle):
    _joint(jointHandle)
    return _w().joint_position(int(jointHandle))


def simSetJointPosition(jointHandle, position):
    _joint(jointHandle)
    _w().set_joint_position(int(jointHandle), position)


def simGetJointTargetPosition(jointHandle):
    return _joint(jointHandle).jstate.target_pos


def simSetJointTargetPosition(jointHandle, targetPosition):
    _joint(jointHandle).jstate.target_pos = float(targetPosition)


def simGetJointTargetVelocity(jointHandle):
    return _joint(jointHandle).jstate.target_vel


def simSetJointTargetVelocity(jointHandle, targetVelocity):
    w = _w()
    o = _joint(jointHandle)
    js = o.jstate
    if float(targetVelocity) != js.target_vel:
        # Re-anchor the velocity reference at the current position.
        js.lock_q = w.joint_position(o.handle)
        if float(targetVelocity) != 0.0:
            js.stalled = False
    js.target_vel = float(targetVelocity)


def simGetJointForce(jointHandle):
    w = _w()
    o = _joint(jointHandle)
    if o.jstate.native and o.act >= 0:
        return float(w.d.actuator_force[o.act])
    return 0.0


def simSetJointForce(jointHandle, forceOrTorque):
    _joint(jointHandle).jstate.max_force = abs(float(forceOrTorque))


def simGetJointMaxForce(jointHandle):
    return _joint(jointHandle).jstate.max_force


def simSetJointMaxForce(jointHandle, forceOrTorque):
    _joint(jointHandle).jstate.max_force = abs(float(forceOrTorque))


def simGetJointInterval(jointHandle):
    js = _joint(jointHandle).jstate
    return js.cyclic, list(js.interval)


def simSetJointInterval(jointHandle, cyclic, interval):
    w = _w()
    o = _joint(jointHandle)
    js = o.jstate
    js.cyclic = bool(cyclic)
    js.interval = [float(interval[0]), float(interval[1])]
    if js.native:
        lo, rng = js.interval
        hi = lo + rng
        # CoppeliaSim does not snap a joint that is already outside a newly
        # set interval back into it; keep the current value reachable.
        q = w.joint_position(o.handle)
        eff_lo, eff_hi = min(lo, q), max(hi, q)
        js.eff_range = (eff_lo, eff_hi)
        w.m.jnt_range[o.jid] = [eff_lo, eff_hi]
        w.m.jnt_limited[o.jid] = 0 if js.cyclic else 1
        if o.name.startswith('Panda_joint') and w.chain is not None:
            idx = int(o.name[-1]) - 1
            w.chain.lows[idx] = -math.pi if js.cyclic else lo
            w.chain.highs[idx] = math.pi if js.cyclic else hi


def simGetJointMode(shapeHandle):
    return _joint(shapeHandle).jstate.mode


def simSetJointMode(jointHandle, jointMode, options=0):
    w = _w()
    o = _joint(jointHandle)
    o.jstate.mode = int(jointMode)
    o.jstate.lock_q = w.joint_position(o.handle)


def simGetJointMatrix(jointHandle):
    w = _w()
    o = _joint(jointHandle)
    delta = w.joint_position(o.handle) - o.jstate.ref
    from ._world import _rz, _tz
    M = _rz(delta) if o.jstate.jtype == C.sim_joint_revolute_subtype else _tz(delta)
    return M[:3, :4].reshape(12).tolist()


def simSetSphericalJointMatrix(jointHandle, matrix):
    _fail('spherical joints are not supported')


# ---------------------------------------------------------------- collisions / distances
def simCheckCollision(entity1Handle, entity2Handle):
    return _w().check_collision(int(entity1Handle), int(entity2Handle))


def simCheckDistance(entity1Handle, entity2Handle, threshold):
    return _w().check_distance(int(entity1Handle), int(entity2Handle), float(threshold))


def simGetCollectionHandle(collectionName):
    w = _w()
    if collectionName in w.collection_by_name:
        return w.collection_by_name[collectionName]
    _fail(f'collection {collectionName} does not exist')


def simGetCollisionHandle(name):
    _fail('collision objects are not supported')


def simGetDistanceHandle(name):
    _fail('distance objects are not supported')


def simReadCollision(handle):
    _fail('collision objects are not supported')


def simReadDistance(handle):
    _fail('distance objects are not supported')


def simHandleDistance(handle):
    _fail('distance objects are not supported')


# ---------------------------------------------------------------- sensors
def simCheckProximitySensor(sensorHandle, entityHandle):
    return _w().proximity_detect(int(sensorHandle), int(entityHandle))


def simReadProximitySensor(sensorHandle):
    state, pt = _w().proximity_detect(int(sensorHandle), C.sim_handle_all)
    return state, -1, pt, [0.0, 0.0, 1.0]


def simHandleProximitySensor(sensorHandle):
    return simReadProximitySensor(sensorHandle)[0]


def simReadForceSensor(forceSensorHandle):
    return 1, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]


def simBreakForceSensor(forceSensorHandle):
    return None


def simGetVisionSensorResolution(sensorHandle):
    o = _w().obj(sensorHandle)
    if o.vision is None:
        _fail('not a vision sensor')
    return list(o.vision['resolution'])


def simHandleVisionSensor(sensorHandle):
    return _w().handle_vision_sensor(int(sensorHandle)), []


def simReadVisionSensor(sensorHandle):
    return 0, []


def simGetVisionSensorImage(sensorHandle, resolution):
    img = _w().vision_capture(int(sensorHandle), 'rgb')
    return np.array(img, dtype=np.float32, copy=True)


def simGetVisionSensorDepthBuffer(sensorHandle, resolution, in_meters):
    w = _w()
    h = int(sensorHandle)
    if h >= C.sim_handleflag_depthbuffermeters:
        h -= C.sim_handleflag_depthbuffermeters
        in_meters = True
    o = w.obj(h)
    depth = np.array(w.vision_capture(h, 'depth'), dtype=np.float32, copy=True)
    near = float(o.vision.get('near') or 0.01)
    far = float(o.vision.get('far') or 10.0)
    depth = np.clip(depth, near, far)
    if in_meters:
        return depth
    return (depth - near) / (far - near)


def simCreateVisionSensor(options, intParams, floatParams, color):
    _fail('creating vision sensors at runtime is not supported in the MuJoCo backend')


def simCreateForceSensor(options, intParams, floatParams, color):
    _fail('creating force sensors at runtime is not supported in the MuJoCo backend')


def simCreateProximitySensor(*args, **kwargs):
    _fail('creating proximity sensors at runtime is not supported in the MuJoCo backend')


# ---------------------------------------------------------------- IK / planning
def simGetIkGroupHandle(ikGroupName):
    return IK_GROUP_HANDLE_BASE


def simSetIkElementProperties(ikGroupHandle, tipDummyHandle, constraints, precision=None, weight=None):
    return None


def simSetIkGroupProperties(ikGroupHandle, resolutionMethod, maxIterations, damping):
    return None


def simGetConfigForTipPose(ikGroupHandle, jointHandles, thresholdDist, maxTimeInMs, metric,
                           collisionPairs, jointOptions, lowLimits, ranges):
    return _w().config_for_tip_pose(jointHandles, maxTimeInMs, list(collisionPairs or []), lowLimits, ranges)


def generateIkPath(ikGroupHandle, jointHandles, ptCnt, collisionPairs, jointOptions):
    return _w().ik_path(jointHandles, int(ptCnt), list(collisionPairs or []))


def simCheckIkGroup(ikGroupHandle, jointHandles):
    return _w().check_ik_group(jointHandles)


def simHandleIkGroup(ikGroupHandle):
    w = _w()
    res, q = w.check_ik_group(None)
    if res == C.sim_ikresult_success:
        w.set_arm_q(q)
    return res


def simComputeJacobian(ikGroupHandle, options):
    return 0


def simGetIkGroupMatrix(ikGroupHandle, options):
    w = _w()
    if w.chain is None:
        return [], (0, 0)
    _, J = w._chain_with_base().jacobian(w.arm_q()[None])
    J = J[0]
    return J.ravel(order='F').tolist(), J.shape


def simExtCallScriptFunction(functionNameAtScriptName, scriptHandleOrType,
                             inputInts, inputFloats, inputStrings, inputBuffer):
    w = _w()
    fname = functionNameAtScriptName.split('@')[0]
    if fname == 'getNonlinearPath':
        collection, ignore, trials_per_goal = inputInts[:3]
        handles = list(inputInts[3:])
        floats = w.nonlinear_path(collection, bool(ignore), trials_per_goal, handles, inputFloats,
                                  inputStrings[0] if inputStrings else 'RRTConnect')
        return [], floats, [], ''
    raise RuntimeError(f'The call failed on the V-REP side. Script function {functionNameAtScriptName} unavailable in MuJoCo backend.')


# ---------------------------------------------------------------- RML (1-DoF, used by ArmConfigurationPath.step)
def simRMLPos(dofs, smallestTimeStep, flags, currentPosVelAccel, maxVelAccelJerk, selection, targetPosVel):
    w = _w()
    h = len(w._rml) + 1
    w._rml[h] = {
        'pos': float(currentPosVelAccel[0]),
        'target': float(targetPosVel[0]),
        'vmax': max(float(maxVelAccelJerk[0]), 1e-6),
        'amax': max(float(maxVelAccelJerk[1]), 1e-6),
        'vel': float(currentPosVelAccel[1]) if len(currentPosVelAccel) > 1 else 0.0,
    }
    return h


def simRMLStep(handle, timeStep, dofs):
    w = _w()
    r = w._rml[handle]
    remaining = r['target'] - r['pos']
    direction = 1.0 if remaining >= 0 else -1.0
    stop_dist = r['vel'] ** 2 / (2 * r['amax'])
    if abs(remaining) <= stop_dist:
        r['vel'] = max(0.0, abs(r['vel']) - r['amax'] * timeStep) * direction
    else:
        r['vel'] = min(r['vmax'], abs(r['vel']) + r['amax'] * timeStep) * direction
    r['pos'] += r['vel'] * timeStep
    done = (r['target'] - r['pos']) * direction <= 1e-9
    if done:
        r['pos'] = r['target']
        r['vel'] = 0.0
    return (1 if done else 0), [r['pos'], r['vel'], 0.0]


def simRMLRemove(handle):
    _w()._rml.pop(handle, None)


def simRMLVel(*args, **kwargs):
    _fail('simRMLVel is not supported')


# ---------------------------------------------------------------- drawing / signals / misc
def simAddDrawingObject(objectType, size, duplicateTolerance, parentObjectHandle, maxItemCount,
                        ambient_diffuse=None, *args, **kwargs):
    w = _w()
    w.drawings += 1
    return DRAWING_HANDLE_BASE + w.drawings


def simAddDrawingObjectItem(drawingObjectHandle, itemData):
    return 1


def simRemoveDrawingObject(drawingObjectHandle):
    return 1


def simAddStatusbarMessage(message):
    print(message)


def simSetIntegerSignal(signalName, signalValue):
    _w().signals[('i', signalName)] = int(signalValue)


def simGetIntegerSignal(signalName):
    v = _w().signals.get(('i', signalName))
    return (1, v) if v is not None else (0, 0)


def simClearIntegerSignal(signalName):
    return 1 if _w().signals.pop(('i', signalName), None) is not None else 0


def simSetFloatSignal(signalName, signalValue):
    _w().signals[('f', signalName)] = float(signalValue)


def simGetFloatSignal(signalName):
    v = _w().signals.get(('f', signalName))
    return (1, v) if v is not None else (0, 0.0)


def simClearFloatSignal(signalName):
    return 1 if _w().signals.pop(('f', signalName), None) is not None else 0


def simSetDoubleSignal(signalName, signalValue):
    _w().signals[('d', signalName)] = float(signalValue)


def simGetDoubleSignal(signalName):
    v = _w().signals.get(('d', signalName))
    return (1, v) if v is not None else (0, 0.0)


def simClearDoubleSignal(signalName):
    return 1 if _w().signals.pop(('d', signalName), None) is not None else 0


def simSetStringSignal(signalName, signalValue):
    _w().signals[('s', signalName)] = signalValue


def simGetStringSignal(signalName):
    v = _w().signals.get(('s', signalName))
    return (1, v) if v is not None else (0, '')


def simClearStringSignal(signalName):
    return 1 if _w().signals.pop(('s', signalName), None) is not None else 0


def simSetUserParameter(objectHandle, parameterName, parameterValue):
    return None


def simGetUserParameter(objectHandle, parameterName):
    return ''


def simRotateAroundAxis(matrixIn, axis, axisPos, angle):
    M = np.eye(4)
    M[:3, :4] = np.asarray(matrixIn, float).reshape(3, 4)
    ax = np.asarray(axis, float)
    ax = ax / np.linalg.norm(ax)
    K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    Rm = np.eye(3) + math.sin(angle) * K + (1 - math.cos(angle)) * (K @ K)
    p = np.asarray(axisPos, float)
    T = np.eye(4)
    T[:3, :3] = Rm
    T[:3, 3] = p - Rm @ p
    return (T @ M)[:3, :4].reshape(12).tolist()


def simInvertMatrix(matrix):
    M = np.eye(4)
    M[:3, :4] = np.asarray(matrix, float).reshape(3, 4)
    return _inv(M)[:3, :4].reshape(12).tolist()


def simMultiplyMatrices(inMatrix1, inMatrix2):
    A = np.eye(4)
    B = np.eye(4)
    A[:3, :4] = np.asarray(inMatrix1, float).reshape(3, 4)
    B[:3, :4] = np.asarray(inMatrix2, float).reshape(3, 4)
    return (A @ B)[:3, :4].reshape(12).tolist()


def simGetEulerAnglesFromMatrix(matrix):
    return mat_to_euler(np.asarray(matrix, float).reshape(3, 4)[:, :3])


def simSaveScene(filename):
    _fail('saving scenes is not supported in the MuJoCo backend')


def simSaveModel(modelHandle, filename):
    _fail('saving models is not supported in the MuJoCo backend')


def simLoadModel(modelPathAndName):
    _fail('loading models is not supported in the MuJoCo backend')


def simLoadScene(scenePathAndName):
    _fail('use PyRep.launch to load scenes in the MuJoCo backend')


def simCloseScene():
    return None


def simReleaseBuffer(buffer):
    return None


def simGetDecimatedMesh(*args, **kwargs):
    _fail('mesh decimation is not supported in the MuJoCo backend')


def simConvexDecompose(*args, **kwargs):
    _fail('convex decomposition is not supported at runtime in the MuJoCo backend')


def simGetConvexHullShape(*args, **kwargs):
    _fail('not supported in the MuJoCo backend')


def simGetPositionOnPath(pathHandle, relativeDistance):
    _fail('paths are not supported in the MuJoCo backend')


def simGetOrientationOnPath(pathHandle, relativeDistance):
    _fail('paths are not supported in the MuJoCo backend')


def simCreatePath(*args, **kwargs):
    _fail('paths are not supported in the MuJoCo backend')


def simGetLightParameters(lightHandle):
    return 1, [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]


def simSetLightParameters(lightHandle, state, diffusePart, specularPart):
    return None


def simCreateStack():
    return 1


def simReleaseStack(stackHandle):
    return 1


SShapeVizInfo = namedtuple('SShapeVizInfo', [
    'vertices', 'indices', 'normals', 'shadingAngle', 'colors', 'texture',
    'textureId', 'textureRes', 'textureCoords', 'textureApplyMode', 'textureOptions'])


def __getattr__(name):
    # Unknown C-API entry points behave like an unavailable CoppeliaSim call.
    if name.startswith('sim') and not name.startswith('sim_'):
        def _unsupported(*args, **kwargs):
            raise RuntimeError(f'The call failed on the V-REP side. {name} is not available in the MuJoCo backend.')
        _unsupported.__name__ = name
        return _unsupported
    raise AttributeError(name)
