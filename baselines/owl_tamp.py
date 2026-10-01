"""OWL-TAMP (Kumar et al., "Open-World Task and Motion Planning via Vision-Language Model
Generated Constraints", arXiv:2411.08253v4) in our scenes. No author code has been released;
this follows the paper: Sec. 5, Algorithms 1-2, Appendix A.1 (search-then-sample, backtracking),
A.6 (helper codebook) and A.7 (prompts, verbatim where the paper gives them).

Protocol:

1. Relaxed grounding of the observed scene: every pick / place / open / close over the observed
   objects, regions and lids (ground operators), and the initial ground atoms.
2. Discrete constraints (one call, image + A.7 prompt, 1-shot, chain of thought): a plan sketch,
   each operator with a natural-language description, ending in ``achieve_goal(...)``.
3. Continuous constraints: first the goal (``achieve_goal``) constraints with the helper codebook
   and the three few-shot examples, then, for each sketch operator with a VLM pose constraint
   (every ``place``), constraints conditioned on its description and the goal constraints.
4. Search-then-sample: A* for a plan that contains the sketch as a subsequence (Executed(i));
   then up to 500 samples per operator from the scene's own placement sampler, each accepted
   only if the operator's constraints (and at the end the goal constraints) hold on the
   predicted state. When an operator's budget is exhausted, backtrack with the paper's
   plan-modification strategy (a failed place onto an occupied region: move one of the
   objects on it elsewhere first), at most five skeletons.
5. Execute the plan open-loop with our executor; the sampled placement pose of each place is the
   one the executor uses (kitchen). The VLM is never re-queried (single-shot protocol, Sec. 6.1).

Recorded deviations: the planning-time checks of a sample are the VLM constraints on the
predicted poses and the sampler's own collision-free footprint; IK and motion feasibility are
checked when the executor runs the action (a sample infeasible for motion is an execution
failure, which open-loop OWL-TAMP cannot recover from). A place on the broad table goes to the
first named table area, as the VLM-TAMP refinement parks objects. In the grill scene the executor places at
the scene's fixed slot poses, so the sampled pose is checked but not imposed. Card sampling of
each model (the paper used GPT-4o).
"""

from __future__ import annotations

import contextlib
import heapq
import itertools
import random
import re
from typing import Dict, List, Optional, Sequence, Tuple

from baselines.common import (BaselinePipeline, SymState, SymbolicDomain, action_text, surface_region_of,
                              observe, parse_action_text, strip_reasoning)
from baselines.owl_constraints import (GOAL_FEW_SHOT, HELPER_DOCS, Geometry, RavenPose, evaluate, extract_functions,
                                       raven_pose)
from llm_pipeline.failures import TerminationReason

SAMPLES_PER_OPERATOR = 500            # Sec. 6
SAMPLES_PER_ATTEMPT = 50             # per operator within one joint attempt (then the plan is resampled)
MAX_SKELETONS = 5                     # Sec. 6
MAX_EXPANSIONS = 20000

DISCRETE_PROMPT = """You are an expert-level robot task planning system whose job is to help a robot
accomplish the following task: ''{task_str}''.
Here is the initial predicate state (i.e., the set of all ground atoms that are true
) of this task. Note that an image corresponding to the environment in this
state
is attached below:
{initial_preds}
Your job is to output a sequence of ground operators (i.e., a plan) that ideally
achieve the goal from this initial state.
Your plan need not be perfect, but it should capture the critical objects and
actions necessary to accomplish this task (e.g.
if the task requires 4 objects being in a specific location, then you should take
care to make sure the plan contains
an action to manipulate each of the 4 objects in turn).
Here are the unground operators with their descriptions.
{nsrts_description}
Here are all the ground operators available to you; each operator you use in your
plan must be one of these.
{ground_operators}
Along with each operator in your plan, you should also output a natural language
description of what that operator should
do. This description can be as detailed as you like, and should explain any details
relevant to completing the particular
ground operator successfully.
As an example, consider the example task ''serve the banana inside the blue thing''.
Here, the bowl happens to be blue, and
the initial state is:
OnTable(banana)
OnTable(bowl)
And the available ground operators are:
pick(banana)
pick(bowl)
pick(table)
place_ontop(banana, bowl)
place_inside(banana, bowl)
place_ontop(bowl, banana)
place_inside(bowl, banana)
place_ontop(banana, table)
place_inside(banana, table)
place_ontop(bowl, table)
place_inside(bowl, table)
place_ontop(table, bowl)
place_inside(table, bowl)
Given this, the output should be something like:
\"\"\"
In the initial state, there is a blue bowl on the table, and a banana atop the table
. The banana is not in the bowl, and the task is to
move the banana into the bowl.
The main actions relevant to the task are `pick(banana)` and `place(banana, bowl)`.
The goal involves a relationship between the banana and the bowl only.
All other objects can be ignored.
Plan:
pick(banana); make a stable grasp on the banana - try to make a top-down grasp for
maximum likelihood of success
place(banana, bowl); place the banana stably so that it rests in the bowl - the
banana is too large to fit inside the bowl if it is placed flatly: it needs to
be reoriented to be upright so that it can fit into the bowl
achieve_goal(banana, bowl); the goal involves the banana being inside the bowl -
this relationship is purely between the banana and bowl and doesn't involve/
require any other objects.
\"\"\"
Notice how the plan ends in an `achieve_goal` operator. Every plan you output should
end with such an operator, and the object arguments
to this operator (i.e., `(banana, bowl)` in this case) should be all the objects
necessary to decide whether or not the goal has been achieved
(i.e., do your best not to include extraneous objects that are irrelevant to
deciding whether the task goal has been achieved or not).
Please output your plan in the following format (do not include the angle brackets:
those are just for illustrative purposes). Importantly, please do not list the
plan with a numbered or bulleted list,
simply output each ground operator on a new line with no marking in front of the
line as indicated below.
<description of the initial state and task in your own words>
<description of which objects and actions are particularly relevant to solving the
task>
<description of any challenges or other important considerations/obstacles that
might arise when solving the task>
Plan:
<ground_operator0>; <natural language description0>
<ground_operator1>; <natural language description1>
...
<ground_operatorm>; <natural language descriptionm>"""

GOAL_CONSTRAINT_PROMPT = """You are an expert-level robot task planning system whose job is to help a robot
accomplish the following task: ''{task_str}''.
An image of the initial state is attached. The objects and regions available in the scene, with their
poses in the initial state, are:
{object_poses}
The plan the robot will follow ends with the operator
{achieve_goal}; {goal_description}
Write Python functions named goal_check0, goal_check1, ... (each taking no arguments and returning a
bool) that are all true exactly when the task goal has been achieved in the final state. Every
object and region above is available as a variable of the same name with `.pose` (RavenPose with
x, y, z, roll, pitch, yaw) and `.category` (its name); `init_state`, `env` and `init_bounds` are
available to pass to the helper functions.

You also have access to helper functions whose signatures and docstrings are shown below:
{helper_functions}

{few_shot}

Output each function in its own ```python code block."""

ACTION_CONSTRAINT_PROMPT = """You are an expert-level robot task planning system whose job is to help a robot
accomplish the following task: ''{task_str}''.
An image of the initial state is attached. The objects and regions available in the scene, with their
poses in the initial state, are:
{object_poses}
The robot's plan is:
{plan}
These goal check functions must hold in the final state:
{goal_functions}
Write Python functions named goal_check0, goal_check1, ... (each taking no arguments and returning a
bool) that must be true right after the robot executes the operator
{operator}; {description}
They constrain only where {placed} ends up when this operator places it: at this point of the plan the
other objects need not be in their final state yet, so do not include checks about them. Every
object and region above is available as a variable of the same name with `.pose` and `.category`;
`init_state`, `env` and `init_bounds` are available to pass to the helper functions.

You also have access to helper functions whose signatures and docstrings are shown below:
{helper_functions}

{few_shot}

Output each function in its own ```python code block."""

# Scene data: the grill env's region keys (as in llm_pipeline/executor.py's grill transfer), and
# regions that are the top surface of a movable object (region_aliases.CANONICAL_REGION_SCENE_OBJECTS).
GRILL_SAMPLER_REGIONS = {'inside_grill': 'grill-top', 'plate_top': 'plate-top', 'serving_area': 'plate_boundary'}
CARRIED_REGIONS = {'plate': ('plate_top',)}


def mentions(source: str, name: str) -> bool:
    """Whether a constraint function constrains the pose of ``name`` (it reads ``name.pose``, or the
    object's centre through ``get_obj_center``): only such a function restricts where that object goes."""
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr == 'pose' and isinstance(n.value, ast.Name) and n.value.id == name:
            return True
        if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'get_obj_center' and any(
                isinstance(x, ast.Name) and x.id == name for a in n.args for x in ast.walk(a)):
            return True
    return False


def _xy_overlap(a, b, margin: float = 0.01) -> bool:
    (ax0, ay0, _), (ax1, ay1, _) = a
    (bx0, by0, _), (bx1, by1, _) = b
    return ax0 < bx1 + margin and bx0 < ax1 + margin and ay0 < by1 + margin and by0 < ay1 + margin


PLAN_LINE = re.compile(r'^\s*([a-z_]+\s*\([^()]*\))\s*;?\s*(.*)$')


# Unground operators and their descriptions (Sec. 5.1: "we associate a natural language description of
# each available action"; the paper's operators are pick, place_ontop and place_inside -- A.7 example;
# open and close are added for this scene's lids, which the paper's tasks do not have).
NSRTS_DESCRIPTION = """pick(?obj): grasp ?obj with the gripper and lift it. The gripper must be empty.
place_ontop(?obj, ?surface): place the held ?obj so that it rests on top of ?surface.
place_inside(?obj, ?container): place the held ?obj inside ?container.
open(?lid): open ?lid. The gripper must be empty.
close(?lid): close ?lid. The gripper must be empty."""


class OWLDomain(SymbolicDomain):
    """Relaxed grounding over every named entity (as the paper's example grounds pick(table),
    place_inside(table, bowl), ...); the TAMP system's own semantics decide which are feasible."""

    def __init__(self, obs):
        super().__init__(obs.objects, obs.regions, obs.lids)
        self.obs = obs
        from baselines.vlm_tamp import space_regions

        self.spaces = set(space_regions(obs.regions))
        self.entities = list(obs.objects) + list(obs.regions) + list(obs.lids)
        # A place on the broad table goes to a named table area, as the VLM-TAMP refinement parks
        # objects (baselines.common.SymbolicDomain): in the kitchen the broad table overlaps every
        # named area, and the executor's broad-table placements can leave an object in the arm's
        # way (e.g. of the lid's opening). The first named table area in the same order.
        self.table_area = next((r for r in self.regions if r.startswith('table_')), None)

    def target(self, action) -> Optional[str]:
        """The region a place_ontop / place_inside puts the object in (None: not a feasible support)."""
        kind, obj, support = action
        if support == obj:
            return None
        if support == 'table' and self.table_area is not None:
            return self.table_area
        if support in self.regions:
            # Our regions are placement areas: on the grill's grate and inside the grill are the same
            # region, so both detach operators are feasible for any region.
            return support
        if kind == 'place_ontop':
            return surface_region_of(support, self.obs)
        return None

    def primitive(self, action) -> Tuple[str, ...]:
        if action[0] in ('place_ontop', 'place_inside'):
            return ('place', action[1], self.target(action))
        return action

    def ground_actions(self):
        ents = self.entities
        out = [('pick', e) for e in ents]
        for kind in ('place_ontop', 'place_inside'):
            out += [(kind, x, y) for x in ents for y in ents if x != y]
        out += [('open', l) for l in self.lids] + [('close', l) for l in self.lids]
        return out

    def applicable(self, state, action) -> bool:
        if action[0] in ('place_ontop', 'place_inside'):
            region = self.target(action)
            return region is not None and super().applicable(state, ('place', action[1], region))
        return super().applicable(state, action)

    def apply(self, state, action):
        return SymbolicDomain.apply(state, self.primitive(action))

    def successors(self, state):
        # (the same set as filtering ground_actions() by applicability, without enumerating the pairs
        # whose first object is not the held one)
        if state.holding is None:
            candidates = [('pick', o) for o in self.objects] + [('open', l) for l in self.lids] + \
                         [('close', l) for l in self.lids]
        else:
            candidates = [(kind, state.holding, y) for kind in ('place_ontop', 'place_inside')
                          for y in self.entities if y != state.holding]
        for action in candidates:
            if self.applicable(state, action):
                yield action, self.apply(state, action)


def initial_predicates(obs) -> List[str]:
    from baselines.vlm_tamp import space_regions

    spaces = set(space_regions(obs.regions))
    atoms = []
    for obj, region in obs.objects.items():
        if region is None:
            atoms.append(f'Holding({obj})')
        else:
            atoms.append(f'{"Inside" if region in spaces else "OnTop"}({obj}, {region})')
    for lid, is_open in obs.lids.items():
        atoms.append(f'{"Open" if is_open else "Closed"}({lid})')
    if not obs.holding:
        atoms.append('HandEmpty()')
    return atoms


def parse_sketch(text: str, grounded: set) -> Tuple[List[Tuple[Tuple[str, ...], str]], Optional[Tuple[str, ...]], List[str]]:
    """(operator, description) lines after ``Plan:``; the achieve_goal operator; rejected lines."""
    answer = strip_reasoning(text)
    body = answer.split('Plan:', 1)[1] if 'Plan:' in answer else ''
    sketch, rejected, achieve = [], [], None
    for line in body.splitlines():
        match = PLAN_LINE.match(line.strip().strip('`').strip('"'))
        if not match:
            continue
        op = parse_action_text(match.group(1))
        if op is None:
            continue
        if op[0] == 'achieve_goal':
            achieve = (op, match.group(2).strip())
            break
        if op in grounded:
            sketch.append((op, match.group(2).strip()))
        else:
            rejected.append(action_text(op))
    return sketch, achieve, rejected


def astar_with_sketch(domain: SymbolicDomain, start: SymState, sketch: Sequence[Tuple[str, ...]],
                      max_expansions: int = MAX_EXPANSIONS) -> Optional[List[Tuple[str, ...]]]:
    """A* for the shortest plan admitting ``sketch`` as a subsequence (Executed(i) compilation)."""
    n = len(sketch)
    counter = itertools.count()
    frontier = [(n, next(counter), 0, start, 0, [])]
    best = {(start, 0): 0}
    expansions = 0
    while frontier:
        _, _, g, state, k, plan = heapq.heappop(frontier)
        if k == n:
            return plan
        expansions += 1
        if expansions > max_expansions:
            return None
        for action, nxt in domain.successors(state):
            k2 = k + 1 if action == sketch[k] else k
            key = (nxt, k2)
            if best.get(key, 1e9) <= g + 1:
                continue
            best[key] = g + 1
            heapq.heappush(frontier, (g + 1 + (n - k2), next(counter), g + 1, nxt, k2, plan + [action]))
    return None


class OWLTAMPPipeline(BaselinePipeline):
    baseline_name = 'owl_tamp'

    # -- geometry --------------------------------------------------------------
    def geometry(self, obs) -> Geometry:
        from llm_pipeline.object_aliases import scene_object_for_object

        # Object boxes from the same detector the scene state uses for region boxes (perception).
        detector = getattr(self.segmentation_adapter, 'detector', None)
        boxes = dict(obs.region_boxes)
        for name in obs.objects:
            try:
                bb = detector.get_bounding_box(scene_object_for_object(name, self.env)) if detector else None
                if bb:
                    boxes[name] = (tuple(float(v) for v in bb[0]), tuple(float(v) for v in bb[1]))
            except Exception:
                continue
        poses = {name: raven_pose(pose) for name, pose in obs.poses.items()}
        try:
            base = self.env.robot.get_position()
            robot_xy = (float(base[0]), float(base[1]))
        except Exception:
            robot_xy = (0.0, 0.0)
        return Geometry(boxes, poses, robot_xy, regions=obs.regions)

    def scene_sample(self, obj: str, region: str) -> Optional[list]:
        """One pose from the scene's own placement sampler (its resting height and orientation)."""
        from llm_pipeline.object_aliases import scene_object_for_object
        from llm_pipeline.region_aliases import normalize_region_name

        region = normalize_region_name(region)
        if (self.config.task_family or '').lower() == 'grill':
            # the grill env keys its regions by the scene names the grill executor also uses
            region = GRILL_SAMPLER_REGIONS.get(region, region)
        try:
            scene_obj = self.env.get_object(scene_object_for_object(obj, self.env))
            return [float(v) for v in self.env.sample_stable_pose(scene_obj, region)]
        except Exception as exc:
            self._baseline_trace.setdefault('sampler_errors', []).append(f'{obj}->{region}: {exc}')
            return None

    @contextlib.contextmanager
    def predicted_scene(self, where: Dict[str, Optional[str]], placed: Dict[str, list]):
        """The scene as predicted at this point of the plan, for the scene's own sampler: objects the
        plan has placed are at their sampled poses, objects in the hand are out of the way. Pure
        kinematic writes (no physics step); every pose is restored on exit."""
        from llm_pipeline.object_aliases import scene_object_for_object

        saved = []
        try:
            for name, region in where.items():
                if region is not None and name not in placed:
                    continue
                try:
                    body = self.env.get_object(scene_object_for_object(name, self.env))
                except Exception:
                    body = None
                if body is None:
                    continue
                original = list(body.get_pose())
                target = list(placed[name]) if region is not None else original[:2] + [original[2] + 5.0] + original[3:]
                saved.append((body, original))
                body.set_pose(target, reset_dynamics=False)
            yield
        finally:
            for body, original in reversed(saved):
                body.set_pose(original, reset_dynamics=False)

    def candidate_poses(self, obj: str, region: str, predicted: Geometry, occupants: Sequence[str],
                        where: Dict[str, Optional[str]], placed: Dict[str, list], rng: random.Random,
                        count: int) -> List[Tuple[list, bool]]:
        """Up to ``count`` placement candidates (7-D pose, from the scene sampler?) on the predicted state.

        First the scene's own placement sampler run on the predicted scene (its region-specific packing
        and clearance rules); then positions on a grid over the region's box ordered by clearance from
        the predicted occupants, then uniform ones, at the sampler's height and orientation.
        """
        out: List[Tuple[list, bool]] = []
        with self.predicted_scene(where, placed):
            for _ in range(min(10, count)):
                pose = self.scene_sample(obj, region)
                if pose is None:
                    break
                if not any(abs(pose[0] - q[0][0]) < 1e-4 and abs(pose[1] - q[0][1]) < 1e-4 for q in out):
                    out.append((list(pose), True))
        if not out:
            return out
        base = out[0][0]
        box = predicted.boxes.get(region)
        if box is not None:
            (x0, y0, _), (x1, y1, _) = box
            pad = 0.12 if region == 'inside_box' else 0.05
            pad_x, pad_y = min(pad, (x1 - x0) / 3), min(pad, (y1 - y0) / 3)
            lo_x, hi_x, lo_y, hi_y = x0 + pad_x, x1 - pad_x, y0 + pad_y, y1 - pad_y
            centers = [((b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2) for b in
                       (predicted.boxes[m] for m in occupants if m in predicted.boxes)]
            n = 12
            grid = [(lo_x + (hi_x - lo_x) * i / (n - 1), lo_y + (hi_y - lo_y) * j / (n - 1))
                    for i in range(n) for j in range(n)]
            grid.sort(key=lambda c: -min([((c[0] - q[0]) ** 2 + (c[1] - q[1]) ** 2) for q in centers] or [0.0]))
            start = rng.randrange(0, 6) if len(out) else 0
            for x, y in grid[start:]:
                out.append(([x, y] + base[2:], False))
            while len(out) < count:
                out.append(([rng.uniform(lo_x, hi_x), rng.uniform(lo_y, hi_y)] + base[2:], False))
        return out[:count]

    # -- prompts ---------------------------------------------------------------
    @staticmethod
    def object_poses_text(geo: Geometry, names: Sequence[str]) -> str:
        lines = []
        for name in names:
            pose = geo.poses.get(name)
            if pose is None:
                (x0, y0, z0), (x1, y1, z1) = geo.box(name)
                pose = RavenPose((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, 0.0, 0.0, 0.0)
            lines.append(f'{name}: Pose=RavenPose(x={pose.x:.4f}, y={pose.y:.4f}, z={pose.z:.4f}, roll={pose.roll:.4f}, '
                         f'pitch={pose.pitch:.4f}, yaw={pose.yaw:.4f})')
        return '\n'.join(lines)

    # -- search-then-sample ------------------------------------------------------
    def sample_plan(self, plan, geo: Geometry, names, action_constraints: Dict[int, List[str]],
                    goal_functions: List[str], trace: dict) -> Tuple[Optional[Dict[int, list]], Optional[int]]:
        """Poses for every place of ``plan`` satisfying the constraints, or the failed operator's index."""
        budgets = {i: SAMPLES_PER_OPERATOR for i, a in enumerate(plan) if a[0] == 'place'}
        goal_budget = SAMPLES_PER_OPERATOR
        rng = random.Random((self.config.seed or 0) + 7)
        attempt = -1
        while goal_budget > 0 and all(v > 0 for v in budgets.values()):
            goal_budget -= 1
            attempt += 1
            predicted = Geometry(geo.boxes, dict(geo.poses), geo.robot_xy, regions=geo.regions)
            chosen: Dict[int, list] = {}
            where = dict(self._initial_regions)          # predicted region of every object, in plan order
            placed: Dict[str, list] = {}                 # 7-D poses the plan has placed objects at
            for i, action in enumerate(plan):
                if action[0] == 'pick':
                    where[action[1]] = None
                if action[0] != 'place':
                    continue
                obj, region = action[1], action[2]
                accepted = pose = None
                occupants = [m for m, r in where.items() if r == region and m != obj]
                candidates = self.candidate_poses(obj, region, predicted, occupants, where, placed, rng,
                                                  min(SAMPLES_PER_ATTEMPT, budgets[i]))
                for pose7, from_scene_sampler in candidates:
                    budgets[i] -= 1
                    pose = raven_pose(pose7)
                    box = predicted.box_at(obj, pose)
                    # Engineered collision constraint on the predicted state: the scene sampler's own
                    # clearance rules for its candidates; for the others, no overlap with the objects
                    # predicted to be in the region (placing onto the top surface of an object, e.g.
                    # the plate, is not a collision).
                    if not from_scene_sampler and any(
                            _xy_overlap(box, predicted.boxes[m]) for m, r in where.items()
                            if r == region and m != obj and m in predicted.boxes
                            and region not in CARRIED_REGIONS.get(m, ())):
                        continue
                    predicted.poses[obj] = pose
                    predicted.boxes[obj] = box
                    # a region on top of a movable object (the plate's top) moves with it
                    # (a plate rests flat once placed: its top is its full footprint, whatever its current tilt,
                    # e.g. on edge in the dish rack)
                    for carried in CARRIED_REGIONS.get(obj, ()):
                        (x0, y0, z0), (x1, y1, z1) = geo.box(obj)
                        extents = sorted((x1 - x0, y1 - y0, z1 - z0))
                        half, height = extents[2] / 2, extents[0]
                        predicted.boxes[carried] = ((pose.x - half, pose.y - half, pose.z - 0.02),
                                                    (pose.x + half, pose.y + half, pose.z + height + 0.05))
                        # the plate itself lies flat too (constraints may refer to the object, not its top)
                        predicted.boxes[obj] = ((pose.x - half, pose.y - half, pose.z - 0.01),
                                                (pose.x + half, pose.y + half, pose.z + height))
                    ok, errors = evaluate(action_constraints.get(i, []), predicted, names)
                    if errors:
                        trace.setdefault('constraint_errors', []).append({'operator': action_text(action),
                                                                          'errors': errors[:3]})
                    if ok:
                        accepted = pose
                        placed[obj] = pose7
                        break
                if accepted is None and budgets[i] > 0:
                    break                        # this attempt failed; resample the plan jointly
                if accepted is None:
                    trace.setdefault('exhausted', []).append({
                        'operator': action_text(action), 'last_sample': list(pose) if pose else None,
                        'object_box': predicted.boxes.get(obj), 'region_box': predicted.boxes.get(region),
                        'predicted_poses': {k: list(v) for k, v in predicted.poses.items() if k in (obj, 'plate')}})
                    return None, i
                chosen[i] = placed[obj]
                where[obj] = region
            else:
                ok, errors = evaluate(goal_functions, predicted, names)
                if errors:
                    trace.setdefault('constraint_errors', []).append({'operator': 'achieve_goal', 'errors': errors[:3]})
                if ok:
                    return chosen, None
                if not budgets:
                    break                          # nothing to resample: the goal constraints fail on this plan
        exhausted = next((i for i, v in budgets.items() if v <= 0), None)
        if exhausted is not None:
            return None, exhausted
        return None, len(plan)                 # achieve_goal failed

    @staticmethod
    def modify_plan(plan, failed: int, obs, domain: 'OWLDomain', rng: random.Random):
        """A.1.1: a failed detach onto a surface with objects on it -> first move one of them to a
        different part of the table (an attach-detach pair)."""
        if failed >= len(plan) or plan[failed][0] not in ('place_ontop', 'place_inside'):
            return None
        obj, region = plan[failed][1], domain.target(plan[failed])
        state = obs.symbolic()
        for action in plan[:failed]:
            state = domain.apply(state, action)
        blockers = [o for o, r in state.regions if r == region and o != obj]
        if not blockers or (state.holding is not None and state.holding != obj):
            return None
        blocker = rng.choice(sorted(blockers))
        # "a different part of the table": the first other open surface region (the broad 'table' last)
        others = [r for r in domain.regions if r != region and r not in domain.spaces
                  and domain._reachable(state, r)]
        if not others:
            return None
        pick_index = max((j for j in range(failed) if plan[j] == ('pick', obj)), default=failed)
        return plan[:pick_index] + [('pick', blocker), ('place_ontop', blocker, others[0])] + plan[pick_index:]

    # -- run -------------------------------------------------------------------
    def run_baseline(self, goal_text: str) -> Optional[str]:
        trace = self._baseline_trace
        chat = self.chat()
        obs = observe(self)
        domain = OWLDomain(obs)
        self.owl_domain = domain
        grounded = set(domain.ground_actions())
        trace['observation'] = obs.to_dict()
        prompt = DISCRETE_PROMPT.format(
            task_str=goal_text, initial_preds='\n'.join(initial_predicates(obs)),
            nsrts_description=NSRTS_DESCRIPTION,
            ground_operators='\n'.join(action_text(a) for a in domain.ground_actions()))
        answer = chat.complete([('user', prompt)], image=obs.image, purpose='owl_tamp_discrete')
        sketch, achieve, rejected = parse_sketch(answer['content'], grounded)
        trace.update({'sketch': [f'{action_text(op)}; {d}' for op, d in sketch],
                      'achieve_goal': f'{action_text(achieve[0])}; {achieve[1]}' if achieve else None,
                      'rejected_sketch_lines': rejected})
        self.record_cycle(False, [action_text(op) for op, _ in sketch], strip_reasoning(answer['content']), 0.0,
                          bool(sketch))
        if not sketch:
            return 'no plan sketch in the model answer'

        geo = self.geometry(obs)
        self._initial_regions = dict(obs.objects)
        names = sorted(set(obs.objects) | set(obs.regions) | set(obs.lids))
        poses_text = self.object_poses_text(geo, names)
        goal_functions: List[str] = []
        if achieve is not None:
            goal_answer = chat.complete([('user', GOAL_CONSTRAINT_PROMPT.format(
                task_str=goal_text, object_poses=poses_text, achieve_goal=action_text(achieve[0]),
                goal_description=achieve[1], helper_functions=HELPER_DOCS, few_shot=GOAL_FEW_SHOT))],
                image=obs.image, purpose='owl_tamp_goal_constraints')
            goal_functions, goal_rejected = extract_functions(goal_answer['content'])
            trace.update({'goal_functions': goal_functions, 'goal_functions_rejected': goal_rejected})
        plan_text = '\n'.join(f'{action_text(op)}; {d}' for op, d in sketch)
        sketch_constraints: Dict[Tuple[str, ...], List[str]] = {}
        for op, description in sketch:
            if op[0] not in ('place_ontop', 'place_inside'):
                continue                          # only operators with a VLM pose constraint (detach)
            reply = chat.complete([('user', ACTION_CONSTRAINT_PROMPT.format(
                task_str=goal_text, object_poses=poses_text, plan=plan_text,
                goal_functions='\n\n'.join(goal_functions) or '(none)', operator=action_text(op),
                description=description, placed=op[1], helper_functions=HELPER_DOCS, few_shot=GOAL_FEW_SHOT))],
                image=obs.image, purpose='owl_tamp_action_constraints')
            functions, bad = extract_functions(reply['content'])
            # An operator's constraint restricts that operator's continuous parameter (the placed
            # object's pose, Sec. 5.2): a function that never refers to the placed object does not
            # constrain it (e.g. a copied goal check about another object) and is not applied here.
            used = [f for f in functions if mentions(f, op[1])]
            sketch_constraints[op] = used
            trace.setdefault('action_functions', {})[action_text(op)] = {
                'functions': used, 'not_about_placed_object': [f for f in functions if f not in used], 'rejected': bad}

        rng = random.Random(self.config.seed or 0)
        skeletons = []
        plan = astar_with_sketch(domain, obs.symbolic(), [op for op, _ in sketch])
        solution = None
        while plan is not None and len(skeletons) < MAX_SKELETONS:
            # constraints attach to the sketch's own operators (first unused occurrence in the plan)
            constraints, used = {}, set()
            for op, _ in sketch:
                index = next((i for i, a in enumerate(plan) if a == op and i not in used), None)
                if index is not None:
                    used.add(index)
                    if op in sketch_constraints:
                        constraints[index] = sketch_constraints[op]
            poses, failed = self.sample_plan([domain.primitive(a) for a in plan], geo, names, constraints,
                                             goal_functions, trace)
            skeletons.append({'plan': [action_text(a) for a in plan],
                              'failed_operator': None if failed is None else
                              (action_text(plan[failed]) if failed < len(plan) else 'achieve_goal')})
            if poses is not None:
                solution = (plan, poses, constraints)
                break
            plan = self.modify_plan(plan, failed, obs, domain, rng)
        trace['skeletons'] = skeletons
        if solution is None:
            self._set_termination(TerminationReason.PLANNING_FAILED)
            return ('no task plan admits the sketch' if not skeletons else
                    f'sampling budget exhausted on {len(skeletons)} skeleton(s)')

        plan, poses, constraints = solution
        primitive_plan = [domain.primitive(a) for a in plan]
        trace['executed_plan'] = [action_text(a) for a in plan]
        trace['executed_primitive_plan'] = [action_text(a) for a in primitive_plan]
        with self.forced_placements(primitive_plan, poses):
            outcome = self.execute(primitive_plan)
        self.record_cycle(False, [action_text(a) for a in plan], '', 0.0, bool(outcome.success),
                          error=outcome.error_message)
        trace['execution'] = {'success': bool(outcome.success), 'failure': outcome.error_message}
        return None if outcome.success else f'open-loop execution failed: {outcome.error_message}'

    @contextlib.contextmanager
    def forced_placements(self, plan, poses: Dict[int, list]):
        """While executing, the k-th placement of an (object, region) uses OWL-TAMP's sampled pose first."""
        from llm_pipeline.object_aliases import scene_object_for_object
        from llm_pipeline.region_aliases import normalize_region_name

        env = self.env
        queue: Dict[Tuple[str, str], List[list]] = {}
        for i, pose7 in sorted(poses.items()):
            obj, region = plan[i][1], normalize_region_name(plan[i][2])
            queue.setdefault((scene_object_for_object(obj, env), region), []).append(list(pose7))
        original_sample = getattr(env, 'sample_stable_pose', None)
        original_best = getattr(env, 'find_best_placement', None)
        forced_log = self._baseline_trace.setdefault('forced_placements', [])

        def _key(obj, region):
            try:
                name = obj.get_name()
            except Exception:
                name = str(obj)
            return name, normalize_region_name(region)

        def sample(obj, region_name, *a, **k):
            key = _key(obj, region_name)
            if queue.get(key):
                pose = queue[key].pop(0)
                forced_log.append({'object': key[0], 'region': key[1], 'pose': pose})
                return pose
            return original_sample(obj, region_name, *a, **k)

        def best(obj, region_name, *a, **k):
            key = _key(obj, region_name)
            if queue.get(key):
                pose = queue[key].pop(0)
                forced_log.append({'object': key[0], 'region': key[1], 'pose': pose})
                return pose
            return original_best(obj, region_name, *a, **k)

        if original_sample is not None:
            env.sample_stable_pose = sample
        if original_best is not None:
            env.find_best_placement = best
        try:
            yield
        finally:
            if original_sample is not None:
                env.__dict__.pop('sample_stable_pose', None)
            if original_best is not None:
                env.__dict__.pop('find_best_placement', None)


__all__ = ['OWLTAMPPipeline', 'DISCRETE_PROMPT', 'parse_sketch', 'astar_with_sketch']
