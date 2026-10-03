"""A planning model for the baselines' TAMP refinement: our own pick-place refinement (the kitchen
executor's PDDLStream solve -- grasp, IK and motion streams, the same call the executor makes before
it moves) run on the scene as a plan predicts it, without executing anything.

* ``planning_model(env)``: a kinematic snapshot (every free body's pose, the arm and gripper joint
  positions and targets) restored on exit; no physics step is taken meanwhile (the executor's
  ``step_and_record`` is a no-op inside), so the trial's scene is left exactly as it was.
* ``predict(env, poses, lids_open)``: inside the model, objects at the poses the plan puts them at
  and the box lid open if the plan has opened it (moved by the executor's slide distance).
* ``refine_transfer(env, obj, region, place_pose=None)``: the executor's refinement of pick(obj) +
  place(obj, region) (``create_primitive_transfer_executor(...).prepare()``), with the place pose
  forced when given; returns (feasible, message, collided bodies by planner name).

Only the kitchen executor separates planning from motion; the grill executor plans each stage while
it moves (its ``prepare`` only records the start pose), so grill transfers are not refined here.
"""

from __future__ import annotations

import contextlib
from typing import Dict, List, Optional, Sequence, Tuple

from baselines.collisions import collision_bodies, recorded_collisions

LID_SLIDE = 0.30          # rlbench_kitchen_env.compute_slide_lid_trajectory: LID_SLIDE_TARGET_DIST
RESTORE_DEVIATIONS: List[float] = []      # per planning-model use: the largest deviation after restoring


def _gt_module():
    from llm_pipeline import executor as ex

    ex._ensure_kitchen_gt_imports()
    return ex.kitchen_gt_module


def _shapes(env):
    """Every scene object the trial can move (free bodies), by scene name."""
    try:
        from pyrep.backend import sim

        world = sim._w()
        names = [o.name for o in world.free_objs]
    except Exception:
        names = []
    out = {}
    for name in names:
        try:
            obj = env.get_object(name)
        except Exception:
            obj = None
        if obj is not None:
            out[name] = obj
    return out


@contextlib.contextmanager
def planning_model(env):
    """The trial's scene, restored on exit; no simulation step is taken inside."""
    gt = _gt_module()
    bodies = _shapes(env)
    poses = {n: list(o.get_pose()) for n, o in bodies.items()}
    dynamic = {}
    for n, o in bodies.items():
        try:
            dynamic[n] = bool(o.is_dynamic())
        except Exception:
            pass
    robot = env.robot
    q = list(robot.get_joint_positions())
    try:
        q_target = list(robot.get_joint_target_positions())
    except Exception:
        q_target = None
    gripper = getattr(env, 'gripper', None) or getattr(robot, 'gripper', None)
    try:
        g = list(gripper.get_joint_positions()) if gripper is not None else None
    except Exception:
        g = None
    target_region = getattr(env, 'target_region', None)
    original_step = getattr(gt, 'step_and_record', None)
    if original_step is not None:
        gt.step_and_record = lambda pr, count=1: None
    try:
        yield
    finally:
        if original_step is not None:
            gt.step_and_record = original_step
        for n, o in bodies.items():
            try:
                o.set_pose(poses[n], reset_dynamics=True)
                if n in dynamic:
                    o.set_dynamic(dynamic[n])
            except Exception:
                pass
        robot.set_joint_positions(q)
        if q_target is not None:
            try:
                robot.set_joint_target_positions(q_target)
            except Exception:
                pass
        if g is not None:
            try:
                gripper.set_joint_positions(g)
            except Exception:
                pass
        try:
            env.target_region = target_region
        except Exception:
            pass
        # how exactly the scene was restored (largest body-position / arm-joint deviation)
        deviation = 0.0
        for n, o in bodies.items():
            try:
                deviation = max(deviation, max(abs(a - b) for a, b in zip(o.get_pose()[:3], poses[n][:3])))
            except Exception:
                pass
        try:
            deviation = max(deviation, max(abs(a - b) for a, b in zip(robot.get_joint_positions(), q)))
        except Exception:
            pass
        RESTORE_DEVIATIONS.append(deviation)


def predict(env, poses: Dict[str, Sequence[float]], lids_open: Sequence[str] = ()) -> None:
    """Inside ``planning_model``: objects (planner names) at the given 7-D poses, lids opened."""
    from llm_pipeline.object_aliases import scene_object_for_object

    for name, pose in poses.items():
        obj = env.get_object(scene_object_for_object(name, env))
        if obj is not None:
            obj.set_pose(list(pose), reset_dynamics=False)
    if 'box_lid' in lids_open:
        lid, box = env.get_object('box_lid'), env.get_object('box_base')
        if lid is not None and box is not None and abs(lid.get_position()[0] - box.get_position()[0]) <= 0.10:
            pose = list(lid.get_pose())
            pose[0] += LID_SLIDE
            lid.set_pose(pose, reset_dynamics=False)


@contextlib.contextmanager
def forced_pose(env, obj_scene_name: str, region: str, pose: Optional[Sequence[float]]):
    """The executor's place-pose samplers return ``pose`` for (object, region) while active."""
    from llm_pipeline.region_aliases import normalize_region_name

    if pose is None:
        yield
        return
    want = (obj_scene_name, normalize_region_name(region))
    originals = {k: getattr(env, k, None) for k in ('sample_stable_pose', 'find_best_placement')}

    def wrap(original):
        def sample(obj, region_name, *a, **k):
            try:
                name = obj.get_name()
            except Exception:
                name = str(obj)
            if (name, normalize_region_name(region_name)) == want:
                return list(pose)
            return original(obj, region_name, *a, **k)
        return sample

    for k, original in originals.items():
        if original is not None:
            setattr(env, k, wrap(original))
    try:
        yield
    finally:
        for k, original in originals.items():
            if original is not None:
                env.__dict__.pop(k, None)


GRILL_GT_REGIONS = {'inside_grill': 'grill-top', 'plate_top': 'plate-top', 'serving_area': 'plate_boundary'}


@contextlib.contextmanager
def forced_placements(env, entries: Sequence[Tuple[str, str, Sequence[float]]], log: Optional[list] = None):
    """While executing, the k-th placement of (object, region) uses the k-th given pose: the
    kitchen executor's place-pose samplers, and the grill handler's slot pose (the grill executor
    otherwise places at fixed slots). ``entries``: (planner object, planner region, 7-D pose)."""
    import sys

    from llm_pipeline.object_aliases import scene_object_for_object
    from llm_pipeline.region_aliases import normalize_region_name

    queue: Dict[Tuple[str, str], List[list]] = {}
    for obj, region, pose in entries:
        queue.setdefault((scene_object_for_object(obj, env), normalize_region_name(region)), []).append(list(pose))
    grill_to_region = {v: k for k, v in GRILL_GT_REGIONS.items()}
    log = log if log is not None else []

    def take(obj, region_name):
        try:
            name = obj.get_name()
        except Exception:
            name = str(obj)
        key = (name, normalize_region_name(grill_to_region.get(region_name, region_name)))
        if queue.get(key):
            pose = queue[key].pop(0)
            log.append({'object': key[0], 'region': key[1], 'pose': pose})
            return pose
        return None

    originals = {k: getattr(env, k, None) for k in ('sample_stable_pose', 'find_best_placement')}

    def wrap(original):
        def sample(obj, region_name, *a, **k):
            pose = take(obj, region_name)
            return pose if pose is not None else original(obj, region_name, *a, **k)
        return sample

    for k, original in originals.items():
        if original is not None:
            setattr(env, k, wrap(original))
    grill_gt = sys.modules.get('grill_gt')
    original_slot = getattr(grill_gt, '_region_slot_pose', None)
    if original_slot is not None:
        def slot(env_, obj, region_name, *a, **k):
            pose = take(obj, region_name)
            return pose if pose is not None else original_slot(env_, obj, region_name, *a, **k)
        grill_gt._region_slot_pose = slot
    try:
        yield log
    finally:
        for k, original in originals.items():
            if original is not None:
                env.__dict__.pop(k, None)
        if original_slot is not None:
            grill_gt._region_slot_pose = original_slot


def sampler_region(region: str) -> str:
    """The region name the kitchen executor passes to the placement sampler (its scene name, e.g.
    cupboard_boundary): the sampler seeds its k-th draw for an (object, region name) pair from that
    name, so sampling under the same name draws the executor's own samples."""
    from llm_pipeline.region_aliases import normalize_region_name, scene_object_for_region

    return scene_object_for_region(normalize_region_name(region))


def sample_place_pose(env, obj: str, region: str) -> Optional[list]:
    """One pose from the scene's own placement sampler (on the current, possibly predicted scene),
    drawn as the executor draws it (``sampler_region``)."""
    from llm_pipeline.object_aliases import scene_object_for_object

    try:
        body = env.get_object(scene_object_for_object(obj, env))
        return [float(v) for v in env.sample_stable_pose(body, sampler_region(region))]
    except Exception:
        return None


def refine_transfer(env, obj: str, region: str, place_pose: Optional[Sequence[float]] = None
                    ) -> Tuple[bool, str, List[str]]:
    """The kitchen executor's refinement of pick(obj) + place(obj, region) on the current (predicted)
    scene, nothing executed: (feasible, message, bodies the robot collided with while planning)."""
    from llm_pipeline.object_aliases import scene_object_for_object
    from llm_pipeline.region_aliases import normalize_region_name, scene_object_for_region

    gt = _gt_module()
    scene_obj = scene_object_for_object(obj, env)
    gt_region = scene_object_for_region(normalize_region_name(region))
    with recorded_collisions() as hits, forced_pose(env, scene_obj, region, place_pose):
        try:
            executor = gt.create_primitive_transfer_executor(env, scene_obj, gt_region,
                                                             task_name=f'refine: {obj} -> {region}')
            ok, message = executor.prepare()
        except Exception as exc:                      # a sampler or IK error is a failed refinement
            ok, message = False, f'{type(exc).__name__}: {exc}'
    return bool(ok), str(message), collision_bodies(hits, exclude=[obj])


__all__ = ['planning_model', 'predict', 'forced_pose', 'forced_placements', 'sample_place_pose', 'refine_transfer',
           'LID_SLIDE']
