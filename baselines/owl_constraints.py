"""OWL-TAMP continuous constraints: the paper's helper codebook (Appendix A.6) over our scene
geometry, and a restricted evaluator for the ``goal_checkN`` functions the VLM writes.

A constraint function is evaluated on a *predicted* state: every observed object and region is
a variable with ``.pose`` (RavenPose: x, y, z, roll, pitch, yaw) and ``.category`` (its name);
the object being placed carries the candidate pose. ``init_state``, ``env`` and ``init_bounds``
are the arguments the paper's examples pass to the helpers.

Bounds are ``(lo, hi)`` pairs of 6-vectors (x, y, z, roll, pitch, yaw). Directions are in the
table plane relative to the robot base: "in front of" an object is on its robot side, "behind"
on the far side, "left"/"right" as seen from the robot.
"""

from __future__ import annotations

import ast
import math
import re
from collections import namedtuple
from typing import Dict, List, Optional, Sequence, Tuple

RavenPose = namedtuple('RavenPose', 'x y z roll pitch yaw')
PI = math.pi

HELPER_DOCS = '''def get_aabb_bounds
"""Given the state of a particular env, and an object_name that appears in
this state, return tuples corresponding to the bounds of the axis-aligned
bounding box of object_name in this state in the world frame.

In particular, return the lower and upper bounds on the axis-aligned
x, y, z values.
"""

def get_obj_center
"""Given the state of a particular env, return the pose of the object with
object_name.

The pose is a tuple of dim 6 corresponding to (x, y, z, roll, pitch,
yaw).
"""

def modify_pose_bounds_to_be_behind_object
"""Given a tuple of initial bounds (init_bounds), return a modified set of
bounds such that sampling randomly from the output bounds will ensure that
a pose will be selected that is behind (on the table plane) the object with
name `object_name`'s. For instance:
modify_pose_bounds_to_be_behind_object(init_state, env, init_bounds,
'hammer') will modify init_bounds such that they only contain poses that
are behind the 'hammer' object on the table surface ahead the robot.

Note that this does not constrain
the pose's horizontal position (it may be anywhere on the table - in the
left or right half - such that it's behind object_name).
"""

def modify_pose_bounds_to_be_in_front_of_object
"""Given a tuple of initial bounds (init_bounds), return a modified set of
bounds such that sampling randomly from the output bounds will ensure that
a pose will be selected that is to the in front of (on the table plane) the
object with name `object_name`'s. For instance:
modify_pose_bounds_to_be_in_front_of_object(init_state, env, init_bounds,
'hammer') will modify init_bounds such that they only contain poses that
are in front of the 'hammer' object on the table surface ahead the robot.

Note that this does not constrain
the pose's horizontal position (it may be anywhere on the table - in the
left or right half - such that it's in front of object_name).
"""

def modify_pose_bounds_to_be_left_of_object
"""Given a tuple of initial bounds (init_bounds), return a modified set of
bounds such that sampling randomly from the output bounds will ensure that
a pose will be selected that is to the left of (on the table plane) the
object with name `object_name`'s. For instance:
modify_pose_bounds_to_be_left_of_object(init_state, env, init_bounds,
'hammer') will modify init_bounds such that they only contain poses that
are to the left of the 'hammer' object on the table surface ahead the
robot.

Note that this does not constrain
the pose's vertical position (it may be anywhere on the table - in the
upper or lower half - such that it's to the left of object_name).
"""

def modify_pose_bounds_to_be_right_of_object
"""Given a tuple of initial bounds (init_bounds), return a modified set of
bounds such that sampling randomly from the output bounds will ensure that
a pose will be selected that is to the right of (on the table plane) the
object with name `object_name`'s. For instance:
modify_pose_bounds_to_be_right_of_object(init_state, env, init_bounds,
'hammer') will modify init_bounds such that they only contain poses that
are to the right of the 'hammer' object on the table surface ahead the
robot.

Note that this does not constrain
the pose's vertical position (it may be anywhere on the table - in the
upper or lower half - such that it's to the right of object_name).
"""

def modify_pose_bounds_to_be_above_object
"""Given a tuple of initial bounds (init_bounds), return a modified set of
bounds such that sampling randomly from the output bounds will ensure that
a pose will be selected that is above (on the table plane) the object with
name `object_name`'s. For instance:
modify_pose_bounds_to_be_above_object(init_state, env, init_bounds,
'hammer') will modify init_bounds such that they only contain poses that
are above the 'hammer' object on the table surface ahead the robot.

Note that this does actually also constrain the pose's horizontal
position and vertical positions so that it is directly above the
object in question. Note also that this function might particularly
useful to constraint pouring actions (because pouring must be done
from above); though you will also likely have to apply an additional
angular constraint (since this function doesn't apply any angular
constraints on its own).
"""

def modify_pose_bounds_to_be_below_object
"""Given a tuple of initial bounds (init_bounds), return a modified set of
bounds such that sampling randomly from the output bounds will ensure that
a pose will be selected that is below (on the table plane) the object with
name `object_name`'s. For instance:
modify_pose_bounds_to_be below_object(init_state, env, init_bounds,
'hammer') will modify init_bounds such that they only contain poses that
are below the 'hammer' object on the table surface ahead the robot.

Note that this does actually also constrain the pose's horizontal
position and vertical positions so that it is directly below the
object in question. Note also that this function might particularly
useful to constraint pouring actions (because pouring must be done
from above into a container that's below); though you will also
likely have to apply an additional angular constraint (since this
function doesn't apply any angular constraints on its own).
"""

def modify_pose_bounds_to_be_near_object
"""Given a tuple of initial bounds (init_bounds), return a modified set of
bounds such that sampling randomly from the output bounds will ensure that
a pose will be selected such that the distance of the pose from the object
with name `object_name` will be within closeness_thresh along the x, y, and
z axes respectively (note that the pose might have an L2) distance that's
greater than that."""

def modify_pose_bounds_to_be_ontop_of_object
"""Assuming the init_bounds are on the pose (x, y, z, roll, pitch, yaw) of
an object with name obj1_name, modify these such that the pose must be
confined to be on top of the object with name obj2_name.

Specifically, restrict the bounds to be within x and y of
obj2_name's bounding-box, but have its z-position touching the top
of the bounding box of obj2_name.

IMPORTANT: use this only when trying to place an object atop another
(e.g. atop a region, or a surface of another object). If you want to put
something inside a container, use the
modify_pose_bounds_to_be_ontop_of_object function instead.
"""

def modify_pose_bounds_to_be_inside_object
"""Assuming the init_bounds are on the pose (x, y, z, roll, pitch, yaw) of
an object with name obj1_name, modify these such that the pose must be
confined to be inside the object with name obj2_name.

Specifically, restrict the bounds to be within x and y of
obj2_name's bounding-box.

IMPORTANT: use this only when trying to place an object inside a container
(e.g. a cup, or vase, or 3D box). If you want to put something in a 2D
region, use the modify_pose_bounds_to_be_ontop_of_object function instead.
Also note that this function is generally not suitable to constrain
pouring; it should generally be used when constraining placement!
"""

def position_within_bounds
"""Checks that the xyz position component of a 6-d pose is within specific
bounds."""

def initialize_bounds_anywhere_on_object
"""Given obj, get its aabb and initialize bounds such that sampling within
these bounds will yield a pose with a position atop obj and any arbitrary
rotation."""

def sample_ravenpose_uniformly_within_bounds
"""Given obj, get its aabb and initialize bounds such that sampling within
these bounds will yield a pose with a position atop obj and any arbitrary
rotation."""

def modify_obj_pose
"""Modifies the pose of obj to new_pose."""'''

# The paper's three few-shot examples for goal constraints (A.7), verbatim.
GOAL_FEW_SHOT = '''To give you an idea of what your output function should look like, here is an
example function generated for the task "put the lemon on the spoon and the
banana on the table", where "lemon", "spoon", "banana", and "table" are all
objects in that task/scene.
```python
def goal_check0() -> bool:
    ontop_spoon_bounds = modify_pose_bounds_to_be_ontop_of_object(init_state, env, init_bounds, lemon.category, spoon.category)
    return position_within_bounds(lemon.pose, ontop_spoon_bounds)
```
```python
def goal_check1() -> bool:
    ontop_table_bounds = modify_pose_bounds_to_be_ontop_of_object(init_state, env, init_bounds, banana.category, table.category)
    return position_within_bounds(banana.pose, ontop_table_bounds)
```
Here is another example set of functions generated for the task "serve the banana
inside the blue thing after drying it by placing on the plate". Here, `banana` and `bowl` are both objects (
the bowl happens to be blue, whereas the plate is red).
The initial state in this example is:
bowl: Pose=RavenPose(x=-0.09269248694181442, y=-0.7042829990386963, z=0.026169249787926674, roll=0.0, pitch=-0.0, yaw=0.8605557025412023)
banana: Pose=RavenPose(x=0.17416073374449514, y=-0.33348321026557554, z=0.02017684663429707, roll=5.081222700168695e-05, pitch=0.00013538346655467005, yaw=-3.0371082921616765)
plate: Pose=RavenPose(x=-0.11636300384998322, y=-0.4429782032966614, z=0.014744692512349077, roll=7.884650441866775e-28, pitch=-7.554679105908491e-28, yaw=2.245637386214381)
table: Pose=RavenPose(x=0.0, y=-0.5, z=0.0, roll=0.0, pitch=-0.0, yaw=0.0)
Importantly, notice how the `goal_check` function checks that the banana is 'upright'
in the bowl by checking its rotation is 90 degrees (approx. 1.57 radians)
along the roll axis. This is necessary, because the banana only fits into the bowl
in this orientation. Pay careful attention and think about any similar orientation
constraints that might be necessary in new problems.
```python
def goal_check0() -> bool:
    in_bowl_bounds = modify_pose_bounds_to_be_inside_object(init_state, env, init_bounds, bowl.category)
    banana_in_bowl_bounds = position_within_bounds(banana.pose, in_bowl_bounds)
    is_upright = 1.4 <= abs(banana.pose.roll) <= 1.65
    return banana_in_bowl_bounds and is_upright
```
Notice here that only one `goal_check` function was each defined, because satisfying
the goal depends on all the continuous variables jointly.
Notice also that the `goal_check` doesn't test for anything to do with the plate,
even though "drying" the banana in the plate was important to the task. This is
because - in the final state - the banana should be in the bowl (it should
have previously been placed in the cup), and the `goal_check` function only
operates in the final state.
Finally, here's an example of constraints for a task "serve spam from its can into
the cup". Here, the objects available are `potted_meat_can` and `mug`.
```python
def goal_check0() -> bool:
    above_mug_bounds = modify_pose_bounds_to_be_above_object(init_state, env, init_bounds, mug.category)
    above_mug = position_within_bounds(potted_meat_can.pose, above_bowl_bounds)
    pour_angle_sufficient = abs(potted_meat_can.pose.roll) > 1.2
    return above_bowl and pour_angle_sufficient
```
Notice once again that only one `goal_check` function was defined.
Notice also that the function checks the roll of the `potted_meat_can`, because this
is important to know that it has been sufficiently 'tipped-over' such that its
contents can fall from the bowl inside it into the cup.
Carefully consider these examples to inform your own functions for the current
problem.'''


def quat_to_rpy(qx, qy, qz, qw) -> Tuple[float, float, float]:
    roll = math.atan2(2 * (qw * qx + qy * qz), 1 - 2 * (qx * qx + qy * qy))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (qw * qy - qz * qx))))
    yaw = math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy * qy + qz * qz))
    return roll, pitch, yaw


def raven_pose(pose: Sequence[float]) -> RavenPose:
    pose = list(pose)
    if len(pose) >= 7:
        return RavenPose(pose[0], pose[1], pose[2], *quat_to_rpy(*pose[3:7]))
    if len(pose) == 6:
        return RavenPose(*pose)
    return RavenPose(pose[0], pose[1], pose[2], 0.0, 0.0, 0.0)


class Entity:
    def __init__(self, name: str, pose: RavenPose):
        self.category = name
        self.name = name
        self.pose = pose


class Geometry:
    """Observed boxes of objects and regions, the robot base, and the predicted poses."""

    def __init__(self, boxes: Dict[str, tuple], poses: Dict[str, RavenPose], robot_xy: Tuple[float, float]):
        self.boxes = dict(boxes)            # name -> ((x0, y0, z0), (x1, y1, z1))
        self.poses = dict(poses)            # name -> RavenPose (current / predicted)
        self.robot_xy = robot_xy

    def box(self, name: str):
        if name in self.boxes:
            return self.boxes[name]
        pose = self.poses[name]
        return ((pose.x - 0.03, pose.y - 0.03, pose.z - 0.03), (pose.x + 0.03, pose.y + 0.03, pose.z + 0.03))

    def box_at(self, name: str, pose: RavenPose):
        """The object's box moved to ``pose`` (same extents)."""
        (x0, y0, z0), (x1, y1, z1) = self.box(name)
        hx, hy, hz = (x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2
        return ((pose.x - hx, pose.y - hy, pose.z - hz), (pose.x + hx, pose.y + hy, pose.z + hz))

    def workspace(self):
        lo = [min(b[0][i] for b in self.boxes.values()) for i in range(3)] if self.boxes else [-2.0, -2.0, 0.0]
        hi = [max(b[1][i] for b in self.boxes.values()) for i in range(3)] if self.boxes else [2.0, 2.0, 2.0]
        return (lo + [-PI, -PI, -PI], [h + 0.5 for h in hi[:2]] + [hi[2] + 0.5] + [PI, PI, PI])


def _helpers(geo: Geometry):
    def _name(x):
        return getattr(x, 'category', x)

    def _center(name):
        (x0, y0, z0), (x1, y1, z1) = geo.box(name)
        return (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2

    def _copy(bounds):
        lo, hi = bounds
        return [list(lo), list(hi)]

    def _toward_robot(name):
        cx, cy, _ = _center(name)
        dx, dy = geo.robot_xy[0] - cx, geo.robot_xy[1] - cy
        return (0, 1 if dx > 0 else -1) if abs(dx) >= abs(dy) else (1, 1 if dy > 0 else -1)

    def get_aabb_bounds(state, env, object_name):
        return geo.box(_name(object_name))

    def get_obj_center(state, env, object_name):
        return tuple(geo.poses.get(_name(object_name)) or RavenPose(*_center(_name(object_name)), 0.0, 0.0, 0.0))

    def _side(bounds, name, towards_robot: bool, lateral: bool = False):
        lo, hi = _copy(bounds)
        axis, sign = _toward_robot(name)
        (b0, b1) = geo.box(name)
        if lateral:                       # left/right: the other table axis
            axis = 1 - axis
            sign = -sign if axis == 1 else sign
        if towards_robot == (sign > 0):
            lo[axis] = max(lo[axis], b1[axis])
        else:
            hi[axis] = min(hi[axis], b0[axis])
        return (lo, hi)

    def modify_pose_bounds_to_be_behind_object(state, env, init_bounds, object_name, *a, **k):
        return _side(init_bounds, _name(object_name), towards_robot=False)

    def modify_pose_bounds_to_be_in_front_of_object(state, env, init_bounds, object_name, *a, **k):
        return _side(init_bounds, _name(object_name), towards_robot=True)

    def modify_pose_bounds_to_be_left_of_object(state, env, init_bounds, object_name, *a, **k):
        return _side(init_bounds, _name(object_name), towards_robot=True, lateral=True)

    def modify_pose_bounds_to_be_right_of_object(state, env, init_bounds, object_name, *a, **k):
        return _side(init_bounds, _name(object_name), towards_robot=False, lateral=True)

    def modify_pose_bounds_to_be_above_object(state, env, init_bounds, object_name, *a, **k):
        lo, hi = _copy(init_bounds)
        (x0, y0, z0), (x1, y1, z1) = geo.box(_name(object_name))
        lo[0], hi[0], lo[1], hi[1], lo[2] = max(lo[0], x0), min(hi[0], x1), max(lo[1], y0), min(hi[1], y1), max(lo[2], z1)
        return (lo, hi)

    def modify_pose_bounds_to_be_below_object(state, env, init_bounds, object_name, *a, **k):
        lo, hi = _copy(init_bounds)
        (x0, y0, z0), (x1, y1, z1) = geo.box(_name(object_name))
        lo[0], hi[0], lo[1], hi[1], hi[2] = max(lo[0], x0), min(hi[0], x1), max(lo[1], y0), min(hi[1], y1), min(hi[2], z0)
        return (lo, hi)

    def modify_pose_bounds_to_be_near_object(state, env, init_bounds, object_name, closeness_thresh=(0.1, 0.1, 0.1),
                                             *a, **k):
        if isinstance(closeness_thresh, (int, float)):
            closeness_thresh = (closeness_thresh,) * 3
        lo, hi = _copy(init_bounds)
        c = _center(_name(object_name))
        for i in range(3):
            lo[i], hi[i] = max(lo[i], c[i] - closeness_thresh[i]), min(hi[i], c[i] + closeness_thresh[i])
        return (lo, hi)

    def modify_pose_bounds_to_be_ontop_of_object(state, env, init_bounds, obj1_name, obj2_name=None, *a, **k):
        target = _name(obj2_name if obj2_name is not None else obj1_name)
        lo, hi = _copy(init_bounds)
        (x0, y0, z0), (x1, y1, z1) = geo.box(target)
        lo[0], hi[0], lo[1], hi[1] = max(lo[0], x0), min(hi[0], x1), max(lo[1], y0), min(hi[1], y1)
        lo[2], hi[2] = max(lo[2], z0), min(hi[2], z1 + 0.25)       # resting on its top surface
        return (lo, hi)

    def modify_pose_bounds_to_be_inside_object(state, env, init_bounds, obj1_name, obj2_name=None, *a, **k):
        target = _name(obj2_name if obj2_name is not None else obj1_name)
        lo, hi = _copy(init_bounds)
        (x0, y0, z0), (x1, y1, z1) = geo.box(target)
        lo[0], hi[0], lo[1], hi[1] = max(lo[0], x0), min(hi[0], x1), max(lo[1], y0), min(hi[1], y1)
        lo[2], hi[2] = max(lo[2], z0 - 0.05), min(hi[2], z1 + 0.1)
        return (lo, hi)

    def position_within_bounds(pose, bounds):
        lo, hi = bounds
        p = (pose.x, pose.y, pose.z) if hasattr(pose, 'x') else tuple(pose[:3])
        return all(lo[i] - 1e-6 <= p[i] <= hi[i] + 1e-6 for i in range(3))

    def initialize_bounds_anywhere_on_object(state, env, obj, *a, **k):
        (x0, y0, z0), (x1, y1, z1) = geo.box(_name(obj))
        return ([x0, y0, z1, -PI, -PI, -PI], [x1, y1, z1 + 0.25, PI, PI, PI])

    def sample_ravenpose_uniformly_within_bounds(bounds, *a, **k):
        import random

        lo, hi = bounds
        return RavenPose(*[random.uniform(lo[i], hi[i]) for i in range(6)])

    def modify_obj_pose(obj, new_pose, *a, **k):
        obj.pose = new_pose
        return obj

    return {name: fn for name, fn in locals().items() if callable(fn) and not name.startswith('_')}


SAFE_BUILTINS = {'abs': abs, 'min': min, 'max': max, 'len': len, 'range': range, 'all': all, 'any': any,
                 'float': float, 'int': int, 'bool': bool, 'round': round, 'sum': sum, 'tuple': tuple, 'list': list,
                 'True': True, 'False': False, 'None': None, 'zip': zip, 'enumerate': enumerate}
FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.With, ast.AsyncFunctionDef,
                   ast.Lambda, ast.Try, ast.While, ast.Delete)
CODE_BLOCK = re.compile(r'```(?:python)?\s*\n(.*?)```', re.S)


def extract_functions(text: str) -> Tuple[List[str], List[str]]:
    """The ``goal_check*`` function sources in a model answer, and why others were rejected."""
    from baselines.common import strip_reasoning

    text = strip_reasoning(text)
    blocks = CODE_BLOCK.findall(text) or [text]
    functions, rejected = [], []
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError as exc:
            rejected.append(f'syntax error: {exc}')
            continue
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith('goal_check'):
                continue
            bad = [type(n).__name__ for n in ast.walk(node) if isinstance(n, FORBIDDEN_NODES)
                   or (isinstance(n, ast.Attribute) and n.attr.startswith('__'))
                   or (isinstance(n, ast.Name) and n.id.startswith('__'))]
            if bad:
                rejected.append(f'{node.name}: not allowed ({", ".join(sorted(set(bad)))})')
                continue
            functions.append(ast.get_source_segment(block, node) or ast.unparse(node))
    return functions, rejected


def evaluate(functions: Sequence[str], geo: Geometry, names: Sequence[str]) -> Tuple[bool, List[str]]:
    """All functions true on ``geo``'s predicted poses. A function that raises counts as false."""
    namespace = {'__builtins__': SAFE_BUILTINS, 'math': math, 'np': None, 'RavenPose': RavenPose,
                 'init_state': None, 'env': None, 'init_bounds': geo.workspace(), 'pi': PI}
    namespace.update(_helpers(geo))
    for name in names:
        pose = geo.poses.get(name)
        if pose is None:
            (x0, y0, z0), (x1, y1, z1) = geo.box(name)
            pose = RavenPose((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, 0.0, 0.0, 0.0)
        namespace[name] = Entity(name, pose)
    errors = []
    for source in functions:
        local = dict(namespace)
        try:
            exec(compile(source, '<goal_check>', 'exec'), local)
            fn = next(v for k, v in local.items() if k.startswith('goal_check') and callable(v))
            if not bool(fn()):
                return False, errors
        except Exception as exc:
            errors.append(f'{type(exc).__name__}: {exc}')
            return False, errors
    return True, errors


__all__ = ['HELPER_DOCS', 'GOAL_FEW_SHOT', 'Geometry', 'RavenPose', 'raven_pose', 'extract_functions', 'evaluate']
_ = Optional
