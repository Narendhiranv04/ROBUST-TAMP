"""EPoG (Yang et al., "EPoG: Integrated Exploration and Sequential Manipulation on Scene Graph with
LLM-based Situated Replanning", ICRA 2026) in our scenes, adapted from the authors' code
(buaa-colalab/EPoG, Apache-2.0, commit 1e7ed52): epog/algorithm/epog/EPoG.py, planner_dynamic.py,
problem_dynamic.py, fake_simulator.py, llm_prompt/action_replaner.py, and pog/planning (ged.py,
action.py, searchNode.py, planner.py).

Kept from the authors' code:

* Belief graph and goal (task) graph: scene graphs of parent -> child edges (an object on / in a
  location or on another object). The global planner is EPoG's: the graph-edit sequence between
  belief and goal (``ged_seq``: a (delete, add) edge pair per object whose parent differs, an add
  for an object in the hand), ``Planner.pick_place_constraints`` (pick before its place; an object
  already in the hand is placed first) and the POG search (``SearchNode`` / ``Searcher``:
  depth-first over the unordered action set under the partial-order constraints, a pick followed
  by a place, at most 10,000 expansions, the first complete sequence).
* The local planner (``local_plan``): every global step is simulated on a copy of the belief graph
  with the checks of ``FakeMotionPlanner.simulate_step`` in its order (accessibility, collision,
  stability, block); a failed check builds a ``MotionError`` (the authors' reason texts, error
  types, involved nodes, parking place) and the LLM resolve call (``get_resolve_action_seq``: the
  authors' system and user messages verbatim, numeric node ids, JSON-schema output
  ``{"steps", "final_answer"}``, ``Action.from_func_string`` parsing) returns actions that are
  simulated recursively on a copy of the graph, as the authors do.
* Global replanning: after every executed step the observation is compared with the belief graph
  (``update_belief_graph``); an object observed where the belief does not have it, or an object
  not seen before, sets the replan flag, and the global plan is recomputed from the updated belief.
  Objects outside the goal graph are EPoG's obstacle ("virtual") nodes: the graph edit ignores them,
  and once moved aside they stay where they were put.

Adapted (docs/BASELINES.md lists every deviation and why):

* The goal graph is built from the natural-language goal and the VISIBLE objects only, by one
  query of our planner model (GOAL_PROMPT, JSON-schema output of EPoG's ``Relationship`` triples);
  objects observed later get their goal relations from the same query when they appear. EPoG's
  tasks are given as goal graphs; our variants give a sentence. Hidden objects are never given.
* No "lost node" estimation (EPoG estimates the room and receptacle of goal objects not yet seen
  with LLM queries): the goal graph only names observed objects, our scenes have one room, and a
  hidden object's location is what the robot has to discover. No walk actions and no exploration
  (a fixed arm; ``insert_exploration_action`` and the visited maps are removed).
* FakeMotionPlanner's checks read our facts: AccessError -- the target or source is a closed
  container (a lid's inside region); CollisionError -- the placement area of the target region is
  occupied (system geometry: an object's footprint intersects it, as computed for our IF rule; the
  occupants are the involved nodes; objects whose goal is that region do not count); StabilityError
  -- objects are on the object being picked (the plate); BlockError -- objects on a lid's top
  surface block opening it (the lid is the grasped part; our pre-action check box_lid_obstructed).
  Steps are then executed by our executor with its pre-action checks; a pre-action failure of one
  of these kinds is resolved the same way after the belief is updated, any other execution failure
  contradicts the belief and triggers a global replan.
* The resolve call goes to our planner model through the OpenAI-compatible vLLM endpoint with the
  same ``response_format`` JSON schema; the parking place is the staging area (kitchen:
  table_center_area; grill: grill_side_area). Its calls (and the authors' retry on invalid output)
  are capped by our replan budget, as are global replans.
* Execution: a pick and the place of the same object run as one executor call; ``Close`` of the
  kitchen box is skipped (our executor cannot close the box, and no kitchen goal needs it closed).
* Grill: the goal graph is the final state only (the meats on the plate, the plate in the serving
  area). EPoG's goal graph cannot express the cooking procedure (raw meat into the grill, close,
  reopen); no workaround is added.
"""

from __future__ import annotations

import json
import random
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from baselines.common import action_text, strip_reasoning
from baselines.icl_examples import examples_for
from baselines.llm_planner import StepLoopPipeline, belief_description
from llm_pipeline.failures import TerminationReason
from llm_pipeline.prompt_v2 import LID_REGIONS, LID_TOP_REGIONS
from llm_pipeline.region_aliases import planner_region_name

ROOT = 'world'
# containers (a lid's inside region) -> lid, and the lid's top surface
CONTAINER_LID = {planner_region_name(r): lid for lid, regions in LID_REGIONS.items() for r in regions}
CONTAINER_TOP = {planner_region_name(r): planner_region_name(LID_TOP_REGIONS[lid])
                 for lid, regions in LID_REGIONS.items() for r in regions if lid in LID_TOP_REGIONS}
# a region that is the top surface of a movable object -> that object (a node of the graph)
SURFACE_OBJECT = {'plate_top': 'plate'}
PARKING = {'kitchen': 'table_center_area', 'grill': 'grill_side_area'}
UNCLOSABLE = {'inside_box'}                 # the kitchen box (baselines.common.UNCLOSABLE_LIDS)
MAX_EXPANSIONS = 10000                      # pog.planning.planner.Searcher.search


# --- graph and actions (pog.planning.action, epog.envs.graph) --------------------------------------

class ActionType(Enum):
    Pick = 0
    Place = 1
    PicknPlace = 2
    Open = 3
    Close = 4
    Walk = 5


@dataclass(frozen=True)
class Action:
    action_type: ActionType
    del_edge: Optional[Tuple[str, str]] = None      # (parent, child)
    add_edge: Optional[Tuple[str, str]] = None

    def render(self, ids: 'NodeIds') -> str:
        """``Action.__repr__`` with node ids."""
        t = self.action_type
        if t == ActionType.Pick:
            return f'Pick {ids[self.del_edge[1]]} from {ids[self.del_edge[0]]}'
        if t == ActionType.Place:
            return f'Place {ids[self.add_edge[1]]} on {ids[self.add_edge[0]]}'
        return f'{t.name} {ids[self.del_edge[1]]}'

    @property
    def child(self) -> str:
        return (self.add_edge or self.del_edge)[1]


class NodeIds:
    """Numeric node ids for the prompts (EPoG's graphs are keyed by ints): 0 is the root."""

    def __init__(self):
        self.by_name: Dict[str, int] = {ROOT: 0}
        self.by_id: Dict[int, str] = {0: ROOT}

    def __getitem__(self, name: str) -> int:
        if name not in self.by_name:
            self.by_name[name] = len(self.by_name)
            self.by_id[self.by_name[name]] = name
        return self.by_name[name]

    def name(self, node_id: int) -> Optional[str]:
        return self.by_id.get(node_id)


@dataclass
class SceneGraph:
    parent: Dict[str, str] = field(default_factory=dict)      # child -> parent
    closed: Set[str] = field(default_factory=set)              # closed containers
    hand: Optional[str] = None
    overlaps: Dict[str, Tuple[str, ...]] = field(default_factory=dict)   # object -> placement areas it occupies

    def copy(self) -> 'SceneGraph':
        return SceneGraph(dict(self.parent), set(self.closed), self.hand, dict(self.overlaps))

    def children(self, node: str) -> List[str]:
        return sorted(c for c, p in self.parent.items() if p == node)


def node_of_region(region: Optional[str]) -> Optional[str]:
    return SURFACE_OBJECT.get(region, region) if region else None


def object_parent(region: Optional[str]) -> str:
    """An object's parent node; an object whose region perception does not resolve (set down
    between two regions) hangs off the root, as every node of the authors' graphs does."""
    return node_of_region(region) or ROOT


def graph_from_observation(obs, overlaps: Dict[str, Sequence[str]]) -> SceneGraph:
    g = SceneGraph()
    for obj, region in obs.objects.items():
        if obj != obs.holding:
            g.parent[obj] = object_parent(region)
    g.hand = obs.holding
    g.closed = {c for c, lid in CONTAINER_LID.items() if lid in obs.lids and not obs.lids[lid]}
    g.overlaps = {o: tuple(v) for o, v in overlaps.items()}
    return g


def apply(graph: SceneGraph, action: Action) -> None:
    """``update_graph`` without navigation."""
    t = action.action_type
    if t == ActionType.Pick:
        graph.parent.pop(action.del_edge[1], None)
        graph.hand = action.del_edge[1]
    elif t == ActionType.Place:
        graph.parent[action.add_edge[1]] = action.add_edge[0]
        if graph.hand == action.add_edge[1]:
            graph.hand = None
    elif t == ActionType.Open:
        graph.closed.discard(action.del_edge[1])
    elif t == ActionType.Close:
        graph.closed.add(action.del_edge[1])


# --- global planner (pog.planning.ged, planner_dynamic.Planner, searchNode, planner) ---------------

def ged_seq(belief: SceneGraph, goal: SceneGraph) -> List[Tuple[Optional[Tuple[str, str]], Tuple[str, str]]]:
    """The edge edit pairs of ``ged_seq`` for scene trees whose nodes match by identity: an object
    whose parent differs gives (delete old edge, add goal edge); an object in the hand gives (None,
    add). Nodes outside the goal graph (obstacles) are ignored, as the authors' edge pairing ignores
    deletions without an add."""
    pairs = []
    for child, goal_parent in goal.parent.items():
        if belief.hand == child:
            pairs.append((None, (goal_parent, child)))
        elif child in belief.parent and belief.parent[child] != goal_parent:
            pairs.append(((belief.parent[child], child), (goal_parent, child)))
    return pairs


class ActionConstraints:
    """pog.planning.action.ActionConstraints: latter -> formers that must come first."""

    def __init__(self):
        self.constraints: Dict[Action, List[Action]] = {}

    def violate(self, action: Action) -> bool:
        return action in self.constraints

    def add(self, former: Action, latter: Action) -> None:
        self.constraints.setdefault(latter, [])
        if former not in self.constraints[latter]:
            self.constraints[latter].append(former)

    def remove(self, action: Action) -> None:
        for key in list(self.constraints):
            if action in self.constraints[key]:
                self.constraints[key].remove(action)
                if not self.constraints[key]:
                    del self.constraints[key]

    def copy(self) -> 'ActionConstraints':
        out = ActionConstraints()
        out.constraints = {k: list(v) for k, v in self.constraints.items()}
        return out


def pick_place_constraints(pairs, rng: random.Random) -> Tuple[List[Action], ActionConstraints]:
    """``Planner.pick_place_constraints``. The authors return ``list(set(actions))`` (an arbitrary
    order that varies with the interpreter's hash seed); here a shuffle seeded by the trial seed."""
    seq, constraints, in_hand = [], ActionConstraints(), []
    for del_edge, add_edge in pairs:
        place = Action(ActionType.Place, add_edge=add_edge)
        if del_edge is None:
            in_hand.append(place)
            seq.append(place)
        else:
            pick = Action(ActionType.Pick, del_edge=del_edge)
            seq += [pick, place]
            constraints.add(pick, place)
    for place in in_hand:
        for action in seq:
            if action not in in_hand:
                constraints.add(place, action)
    unique = sorted(set(seq), key=lambda a: (a.action_type.value, a.del_edge or ('', ''), a.add_edge or ('', '')))
    rng.shuffle(unique)
    return unique, constraints


def pog_search(actions: List[Action], constraints: ActionConstraints) -> Tuple[Optional[List[Action]], int]:
    """``Searcher.search`` (depth-first, first solution; every path has the same cost without
    navigation) over ``SearchNode.selectAction``: an action is selectable if no constraint holds
    it back and, after a pick, it is a place."""
    stack = [([], list(actions), constraints)]
    expanded = 0
    while stack:
        expanded += 1
        if expanded > MAX_EXPANSIONS:
            return None, expanded
        path, remaining, cons = stack.pop()
        if not remaining:
            return path, expanded
        occupied = bool(path) and path[-1].action_type == ActionType.Pick
        children = []
        for index, action in enumerate(remaining):
            if cons.violate(action) or (occupied and action.action_type != ActionType.Place):
                continue
            nxt = cons.copy()
            nxt.remove(action)
            children.append((path + [action], remaining[:index] + remaining[index + 1:], nxt))
        stack.extend(reversed(children))           # the first selectable action is explored first
    return None, expanded


# --- local planner (fake_simulator.FakeMotionPlanner, MotionError) ----------------------------------

class MotionErrorType(Enum):
    CollisionError = 0
    AccessError = 1
    StabilityError = 2
    BlockError = 3


@dataclass
class MotionError:
    reason: str
    error_type: MotionErrorType
    failure_action: Action
    involved_nodes: List[str]
    observation_involved: object = None
    parking_place: int = 0

    def render(self, ids: NodeIds) -> str:
        """``MotionError.__repr__``."""
        return f"""
            MotionError: {self.reason}, Error Type: {self.error_type},
            Failure Action: {self.failure_action.render(ids)}, Parking Place: {self.parking_place}
            observation_involved: {self.observation_involved}
        """


def simulate_step(graph: SceneGraph, action: Action, goal: SceneGraph, ids: NodeIds) -> Optional[MotionError]:
    """``FakeMotionPlanner.simulate_step``: the checks in the authors' order; the graph is updated
    when they pass."""
    t = action.action_type
    if t == ActionType.Pick:
        parent, child = action.del_edge
        if parent in graph.closed:
            return MotionError(f'object {ids[child]} is not accessible, because {[ids[parent]]} is closed',
                               MotionErrorType.AccessError, action, [parent], [])
        on_top = graph.children(child)
        if on_top:
            return MotionError(f'object {ids[child]} is not stable, because {[ids[n] for n in on_top]} is on {ids[child]}',
                               MotionErrorType.StabilityError, action, on_top,
                               [f'{ids[n]} on {ids[child]}' for n in on_top])
    elif t == ActionType.Place:
        parent, child = action.add_edge
        if parent in graph.closed:
            return MotionError(f'object {ids[child]} is not accessible, because {[ids[parent]]} is closed',
                               MotionErrorType.AccessError, action, [parent], [])
        occupants = [n for n, p in sorted(graph.parent.items())
                     if n != child and p == parent and parent in graph.overlaps.get(n, ()) and goal.parent.get(n) != parent]
        if occupants:
            return MotionError(f'object {ids[child]} is in collision with {[ids[n] for n in occupants]} on {ids[parent]}',
                               MotionErrorType.CollisionError, action, occupants,
                               [f'{ids[n]} on {ids[parent]}' for n in occupants])
    elif t == ActionType.Open:
        container = action.del_edge[1]
        top = CONTAINER_TOP.get(container)
        blockers = graph.children(top) if top else []
        if blockers:
            return MotionError(f'object {ids[container]} is blocked by {[ids[n] for n in blockers]}',
                               MotionErrorType.BlockError, action, blockers, [f'{ids[n]} on {ids[top]}' for n in blockers])
    apply(graph, action)
    return None


# --- the resolve call (llm_prompt/action_replaner.py, verbatim) ----------------------------------

RESOLVE_SYSTEM = ('You are a robot, and you need to insert some action to resolved any errors that occur during '
                  'the task planning process.')


def resolve_user_message(error: MotionError, ids: NodeIds, examples: str = '') -> str:
    """The authors' message; ``examples`` (the ICL condition) follow the authors' worked example."""
    return f"""
        You are going to resolve the error that occurs during the task planning process.
        The primitives are: Pick(x, y): Pick x from y, Place(x, y): Place x on y, Open(x): Open x, Close(x): Close x
        The parking place is {error.parking_place}, you can place temporarily place the object here.
        Here is the example:
        error: "place 1 on 2 is failure and object 1 will be collision with [3]"
        Whole Anaylsis: object 1 is collision within object 3, so i need to adjust the object 3 so that we can place object 1 on object 2.
            Robot Hand State: because the failed action type is place, so my hand is occupied, object 1 is in my hand.
            Frist Step: Because object 1 is in my hand, so i need to place object 1 on the parking place. Place(1, 0)
            Second Step: Because object 3 is collision with object 1, so i need to remove the collision, Pick(3, 2)
            Third Step: I need to replace object 3 in the parking place so that i can pick the object 1, Place(3, 0)
            Fourth Step: I need to pick object 1 from the parking place, Pick(1, 0)
            Fifth Step: I need to replay the failed action, place object 1 on object 2, Place(1, 2)
            then I summarize the action sequence below:
        action sequence: ["Place(1, 0)", "Pick(3, 2)", "Place(3, 0)", "Pick(1, 0)", "Place(1, 2)"]
{examples}        Your robot is trying to {error.failure_action.render(ids)} but it failed. The error is {error.render(ids)}.
    """


def _step_schema():
    # 'required' added: the authors' pydantic Step requires both fields, but their JSON schema does not
    # say so, and constrained decoding then lets a model leave out the explanation -- an answer their
    # own validator rejects (a retry that uses the budget; 161 of 808 fix answers in our first run)
    return {'type': 'object', 'properties': {'explanation': {'type': 'string'}, 'output': {'type': 'string'}},
            'required': ['explanation', 'output'],
            'description': 'Step-by-step analysis of the action.', 'additionalProperties': False}


RESOLVE_SCHEMA = {'name': 'probability_analysis', 'schema': {
    'strict': False, 'type': 'object',
    'properties': {'steps': {'type': 'array', 'items': _step_schema()},
                   'final_answer': {'type': 'array', 'items': {
                       'type': 'object', 'properties': {'action': {'type': 'string'}}, 'required': ['action'],
                       'description': 'Action to resolve the error.', 'additionalProperties': False},
                       'description': 'action sequence to resolve the error.'}},
    'additionalProperties': False, 'required': ['steps', 'final_answer']}}


def parse_action_seq(text: str) -> Optional[List[str]]:
    """``ActionSeq.parse_raw``: the final_answer actions, or None when the output does not validate."""
    try:
        data = json.loads(strip_reasoning(text))
        if not isinstance(data.get('steps'), list) or not isinstance(data.get('final_answer'), list):
            return None
        for step in data['steps']:
            if not isinstance(step, dict) or not all(isinstance(step.get(k), str) for k in ('explanation', 'output')):
                return None
        if not all(isinstance(a, dict) and isinstance(a.get('action'), str) for a in data['final_answer']):
            return None
        return [a['action'] for a in data['final_answer']]
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def from_func_string(text: str, ids: NodeIds) -> Optional[Action]:
    """``Action.from_func_string`` (the authors' patterns, whitespace inside the parentheses allowed:
    the authors' patterns need exactly "Place(1, 2)" and dropped "Place(1,2)"), node ids mapped back
    to names."""
    text = text.strip()
    place, pick = re.match(r'Place\(\s*(\d+)\s*,\s*(\d+)\s*\)', text), re.match(r'Pick\(\s*(\d+)\s*,\s*(\d+)\s*\)', text)
    opened, closed = re.match(r'Open\(\s*(\d+)\s*\)', text), re.match(r'Close\(\s*(\d+)\s*\)', text)
    if place or pick:
        m = place or pick
        child, parent = ids.name(int(m.group(1))), ids.name(int(m.group(2)))
        if child is None or parent is None:
            return None
        return Action(ActionType.Place, add_edge=(parent, child)) if place else Action(ActionType.Pick, del_edge=(parent, child))
    if opened or closed:
        node = ids.name(int((opened or closed).group(1)))
        if node is None:
            return None
        return Action(ActionType.Open if opened else ActionType.Close, del_edge=(node, node), add_edge=(node, node))
    return None


def rule_based_resolution(error: MotionError, ids: NodeIds) -> List[str]:
    """``Planner.rule_based_replanner`` (the authors' expert local agent), as action strings with
    node ids; used by mock trials in place of the model."""
    a, park = error.failure_action, error.parking_place
    out = []
    if error.error_type == MotionErrorType.AccessError:
        out += [f'Open({ids[n]})' for n in error.involved_nodes] + [_func_string(a, ids)]
        out += [f'Close({ids[n]})' for n in error.involved_nodes]
    elif error.error_type == MotionErrorType.CollisionError:
        parent = a.add_edge[0]
        for n in error.involved_nodes:
            out += [f'Pick({ids[n]}, {ids[parent]})', f'Place({ids[n]}, {park})']
        out.append(_func_string(a, ids))
    elif error.error_type == MotionErrorType.StabilityError:
        child = a.del_edge[1]
        for n in error.involved_nodes:
            out += [f'Pick({ids[n]}, {ids[child]})', f'Place({ids[n]}, {park})']
        out.append(_func_string(a, ids))
    elif error.error_type == MotionErrorType.BlockError:
        top = CONTAINER_TOP.get(a.del_edge[1], a.del_edge[0])
        for n in error.involved_nodes:
            out += [f'Pick({ids[n]}, {ids[top]})', f'Place({ids[n]}, {park})']
        out.append(_func_string(a, ids))
    return out


def example_resolution(error: MotionError, ids: NodeIds) -> List[str]:
    """A resolution as the authors' prompt example reasons (a failed place: the held object is
    parked first, picked again before the failed action is replayed); mock trials use it, since the
    rule-based agent ignores the hand (the authors' fake simulator does not check it)."""
    actions = rule_based_resolution(error, ids)
    a = error.failure_action
    if a.action_type != ActionType.Place:
        return actions
    o, park = ids[a.child], error.parking_place
    replay = _func_string(a, ids)
    middle = [x for x in actions if x != replay and not x.startswith('Close(')]
    closes = [x for x in actions if x.startswith('Close(')]
    return [f'Place({o}, {park})'] + middle + [f'Pick({o}, {park})', replay] + closes


def _func_string(a: Action, ids: NodeIds) -> str:
    if a.action_type == ActionType.Pick:
        return f'Pick({ids[a.del_edge[1]]}, {ids[a.del_edge[0]]})'
    if a.action_type == ActionType.Place:
        return f'Place({ids[a.add_edge[1]]}, {ids[a.add_edge[0]]})'
    return f'{a.action_type.name}({ids[a.del_edge[1]]})'


# --- goal graph (our adapter: EPoG's tasks come as goal graphs) ----------------------------------

def goal_relations(objects: Sequence[str], scene: str) -> Dict[str, Tuple[str, str]]:
    """EPoG's native task graph for the given (observed) objects, from the benchmark's goal
    specification (evaluation.labeled_rules: an object's category -> its goal region; the grill's
    plate goes to the serving area): child -> (relationType, parent). Objects the goal does not
    place are left out (obstacle nodes). Hidden objects are never passed in."""
    from evaluation.labeled_rules import CATEGORY_GOAL_REGIONS, SCENE_GOAL_CATEGORIES, object_category

    placed = set(SCENE_GOAL_CATEGORIES[scene]) | ({'plate'} if scene == 'grill' else set())
    out = {}
    for obj in objects:
        category = object_category(obj)
        if category in placed:
            region = planner_region_name(CATEGORY_GOAL_REGIONS[category])
            relation = 'in' if region in CONTAINER_LID or region == 'cupboard_shelf' else 'on'
            out[obj] = (relation, node_of_region(region))
    return out


# the language variant (``epog_language_goal``): the goal relations from one model query

GOAL_SYSTEM = 'You are a robot that converts a task instruction into the goal state of a scene graph.'
GOAL_PROMPT = """The task instruction is: {goal}
The current scene graph (the objects the robot has observed and where they are):
{state}
{known}Give the goal relations of the scene graph, one relation "child relationType parent" per object whose final location the instruction determines: child is {which}, relationType is "on" or "in", parent is one of the locations or an object that other objects are placed on. Leave out objects whose final location the instruction does not determine."""
GOAL_SCHEMA = {'name': 'goal_graph', 'schema': {
    'type': 'object', 'additionalProperties': False, 'required': ['relations'],
    'properties': {'relations': {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False, 'required': ['children', 'relationType', 'parent'],
        'properties': {'children': {'type': 'string'}, 'relationType': {'type': 'string'}, 'parent': {'type': 'string'}}}}}}}


def parse_goal_relations(text: str, objects: Sequence[str], obs) -> Tuple[Dict[str, str], List[dict]]:
    """Relations (``Relationship`` triples) for the given objects; parent names are grounded to
    graph nodes (a location, or the plate for plate_top). Returns (child -> parent, rejected)."""
    try:
        relations = json.loads(strip_reasoning(text)).get('relations') or []
    except (json.JSONDecodeError, AttributeError):
        return {}, [{'output': text[-300:]}]
    goal, rejected = {}, []
    locations = set(obs.regions) | set(SURFACE_OBJECT.values())
    for rel in relations:
        child, parent = str(rel.get('children', '')).strip(), str(rel.get('parent', '')).strip()
        parent = node_of_region(parent)
        if child in objects and parent in locations and parent != child and child not in goal:
            if parent in SURFACE_OBJECT.values() and parent not in obs.objects:
                rejected.append(rel)
                continue
            goal[child] = parent
        else:
            rejected.append(rel)
    return goal, rejected


# --- the trial ---------------------------------------------------------------------------------

class BudgetExhausted(Exception):
    pass


class EPoGPipeline(StepLoopPipeline):
    """EPoG without lost-object estimation (the reported row): the goal graph from the goal
    specification for the observed objects."""

    baseline_name = 'epog'
    ground_containers = False
    goal_from_language = False

    # -- model calls ------------------------------------------------------------------------------
    def complete_json(self, system: str, user: str, schema: dict, purpose: str, obs) -> str:
        out = self.chat().complete([('user', user)], image=self.query_image(obs), purpose=purpose, system=system,
                                   response_format={'type': 'json_schema', 'json_schema': schema})
        return out['content']

    def ground_goal(self, obs, objects: Sequence[str]) -> Dict[str, str]:
        if not self.goal_from_language:
            relations = goal_relations(objects, self.scene)
            self.goal_relation_types.update({c: r for c, (r, _) in relations.items()})
            self._baseline_trace['goal_queries'].append({'objects': list(objects), 'source': 'goal_specification',
                                                         'relations': {c: f'{r} {p}' for c, (r, p) in relations.items()}})
            return {c: p for c, (_, p) in relations.items()}
        known = ''
        if self.goal.parent:
            known = 'The goal relations so far:\n' + '\n'.join(
                f'{c} {"in" if p in CONTAINER_LID else "on"} {p}' for c, p in self.goal.parent.items()) + '\n'
        which = 'one of these objects: ' + ', '.join(objects)
        user = GOAL_PROMPT.format(goal=self.goal_text, state=belief_description(obs), known=known, which=which)
        text = self.complete_json(GOAL_SYSTEM, user, GOAL_SCHEMA, 'epog_goal_graph', obs)
        relations, rejected = parse_goal_relations(text, objects, obs)
        self._baseline_trace['goal_queries'].append({'objects': list(objects), 'source': 'model',
                                                     'relations': relations, 'rejected': rejected})
        return relations

    def resolve(self, error: MotionError, obs) -> List[Action]:
        """``generate_reslove_actions`` with the LLM agent; retries on invalid output, capped."""
        error.parking_place = self.ids[self.parking]
        self._last_motion_error = error                 # read by the mock (rule-based) resolver
        examples = examples_for(self)                  # ICL condition, grill scene only
        user = resolve_user_message(error, self.ids, textwrap.indent(examples, ' ' * 8) + '\n' if examples else '')
        while True:
            if self.resolve_calls >= self.budget:
                raise BudgetExhausted(f'{self.resolve_calls} resolve calls')
            self.resolve_calls += 1
            text = self.complete_json(RESOLVE_SYSTEM, user, RESOLVE_SCHEMA, 'epog_resolve', obs)
            raw = parse_action_seq(text)
            record = {'error': error.render(self.ids).strip(), 'error_type': error.error_type.name,
                      'failure_action': action_text(self.primitive(error.failure_action) or ('?',)),
                      'raw_actions': raw}
            self._baseline_trace['resolves'].append(record)
            if raw is None:
                continue                              # ValidationError: the authors query again
            actions = [from_func_string(a, self.ids) for a in raw]
            record['actions'] = [a.render(self.ids) if a else None for a in actions]
            return [a for a in actions if a is not None]

    # -- planning -----------------------------------------------------------------------------------
    def global_plan(self) -> Optional[List[Action]]:
        pairs = ged_seq(self.belief, self.goal)
        actions, constraints = pick_place_constraints(pairs, self.rng)
        plan, expanded = pog_search(actions, constraints)
        self._baseline_trace['global_plans'].append({
            'plan': None if plan is None else [a.render(self.ids) for a in plan],
            'plan_names': None if plan is None else [action_text(self.primitive(a) or ('?',)) for a in plan],
            'expanded': expanded})
        return plan

    def local_plan(self, graph: SceneGraph, actions: Sequence[Action], obs, depth: int = 0) -> None:
        """``EPoG.local_plan``: a failed step's resolution is planned recursively in its place. The
        authors plan it on a copy of the graph and continue the remaining actions on the unchanged
        graph; here the resolution's effects carry over (with a nested error -- the resolution's own
        open blocked by an object on the lid -- the authors' version simulates the rest of the
        resolution with the lid still closed and repeats the access error until the budget ends)."""
        for action in actions:
            error = simulate_step(graph, action, self.goal, self.ids)
            if error is not None:
                inserts = self.resolve(error, obs)
                self.local_plan(graph, inserts, obs, depth + 1)
            else:
                self.local_action_seq.append(action)

    # -- execution and belief ------------------------------------------------------------------------
    def primitive(self, action: Action) -> Optional[Tuple[str, ...]]:
        t = action.action_type
        if t == ActionType.Pick:
            return ('pick', action.del_edge[1])
        if t == ActionType.Place:
            return ('place', action.add_edge[1], action.add_edge[0])
        container = action.del_edge[1]
        lid = CONTAINER_LID.get(container)
        if lid is None:
            return None
        return ('open' if t == ActionType.Open else 'close', lid)

    def observe_belief(self, executed: Sequence[Action]) -> Tuple[object, bool]:
        """``update_belief_graph``: the executed actions' effects, then the observation; the replan
        flag when an observed object contradicts the belief or was not seen before."""
        for action in executed:
            apply(self.belief, action)
        obs = self.observe_scene()
        flag = False
        new = [o for o in obs.objects if o not in self.seen]
        for obj, region in obs.objects.items():
            if obj == obs.holding:
                if self.belief.hand != obj:
                    flag = obj in self.seen or flag
                self.belief.parent.pop(obj, None)
                continue
            parent = object_parent(region)
            if self.belief.parent.get(obj) != parent:
                flag = flag or obj in self.seen
                self.belief.parent[obj] = parent
        if self.belief.hand and self.belief.hand != obs.holding:
            flag = True
        self.belief.hand = obs.holding
        self.belief.closed = {c for c, lid in CONTAINER_LID.items() if lid in obs.lids and not obs.lids[lid]}
        for obj in obs.objects:
            self.belief.overlaps[obj] = tuple(self.placement_overlaps(obj))
        if new:
            self.seen.update(new)
            self.goal.parent.update(self.ground_goal(obs, new))
            flag = True
        self.obs = obs
        return obs, flag

    def placement_overlaps(self, obj: str) -> List[str]:
        return [planner_region_name(r) for r in self._placement_area_overlaps(obj)]

    def roll_out(self, local_seq: List[Action]) -> Tuple[bool, Optional[dict]]:
        """Execute the local sequence bundle by bundle; (replan flag, the failed step if any)."""
        flag = False
        i = 0
        while i < len(local_seq):
            bundle = [local_seq[i]]
            if (local_seq[i].action_type == ActionType.Pick and i + 1 < len(local_seq)
                    and local_seq[i + 1].action_type == ActionType.Place and local_seq[i + 1].child == local_seq[i].child):
                bundle.append(local_seq[i + 1])
            i += len(bundle)
            prims = [self.primitive(a) for a in bundle]
            if any(p is None for p in prims) or any(p[0] == 'close' and a.del_edge[1] in UNCLOSABLE
                                                    for p, a in zip(prims, bundle) if p):
                self._baseline_trace['steps'].append({'bundle': [a.render(self.ids) for a in bundle],
                                                      'skipped': 'not an action of this scene'})
                continue
            step = self.run_step(prims, set(self.seen))
            self._baseline_trace['steps'].append(step)
            _, observed_flag = self.observe_belief(bundle if step['success'] else [])
            flag = flag or observed_flag
            if not step['success']:
                return True, step
        return flag, None

    # -- main loop (EPoG.main_loop) --------------------------------------------------------------------
    def run_baseline(self, goal_text: str) -> Optional[str]:
        trace = self._baseline_trace
        self.budget = int(self.config.max_replans)
        trace.update({'goal_queries': [], 'global_plans': [], 'resolves': [], 'steps': [], 'max_replans': self.budget})
        self.goal_text, self.ids, self.resolve_calls, self.global_replans = goal_text, NodeIds(), 0, 0
        self.rng = random.Random(int(self.config.seed or 0))
        obs = self.obs = self.observe_scene()
        self.scene = scene = 'grill' if any('grill' in r for r in obs.regions) else 'kitchen'
        self.goal_relation_types: Dict[str, str] = {}
        self.parking = PARKING[scene]
        for region in [ROOT] + list(obs.regions):
            self.ids[node_of_region(region)]
        self.seen = set(obs.objects)
        for obj in obs.objects:
            self.ids[obj]
        self.belief = graph_from_observation(obs, {o: self.placement_overlaps(o) for o in obs.objects})
        self.goal = SceneGraph()
        self.goal.parent.update(self.ground_goal(obs, list(obs.objects)))
        trace['goal_graph'] = {c: f'{self.goal_relation_types.get(c, "on")} {p}' for c, p in self.goal.parent.items()}
        try:
            return self._main_loop(trace)
        finally:
            trace['final_goal_graph'] = {c: f'{self.goal_relation_types.get(c, "on")} {p}' for c, p in self.goal.parent.items()}
            trace['budget_use'] = {'global_replans': self.global_replans, 'resolve_calls': self.resolve_calls,
                                   'goal_queries': len(trace['goal_queries']),
                                   'model_calls': len(self.chat().calls)}

    def _main_loop(self, trace) -> Optional[str]:
        try:
            rough = self.global_plan()
            while True:
                if rough is None:
                    self._set_termination(TerminationReason.PLANNING_FAILED)
                    return 'global planner found no plan'
                if not rough:
                    return None                             # the goal graph is reached in the belief
                step = rough.pop(0)
                pair = [step]
                if step.action_type == ActionType.Pick and rough and rough[0].action_type == ActionType.Place \
                        and rough[0].child == step.child:
                    pair.append(rough.pop(0))               # simulated one by one, executed as one bundle
                for obj in self.seen:
                    self.ids[obj]
                self.local_action_seq = []
                self.local_plan(self.belief.copy(), pair, self.obs)      # the latest observation
                flag, failed = self.roll_out(self.local_action_seq)
                self.record_cycle(self.global_replans > 0, [a.render(self.ids) for a in self.local_action_seq], '',
                                  0.0, failed is None, error=(failed or {}).get('failure'))
                if flag:
                    if self.global_replans >= self.budget:
                        raise BudgetExhausted(f'{self.global_replans} global replans')
                    self.global_replans += 1
                    rough = self.global_plan()
        except BudgetExhausted as exc:
            self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
            return f'replan budget exhausted ({exc})'


class EPoGLanguageGoalPipeline(EPoGPipeline):
    """The adaptation in which the goal graph comes from the language goal (one model query per
    batch of newly observed objects) instead of the goal specification."""

    baseline_name = 'epog_language_goal'
    goal_from_language = True


__all__ = ['EPoGPipeline', 'EPoGLanguageGoalPipeline', 'goal_relations', 'ged_seq', 'pick_place_constraints', 'pog_search', 'simulate_step', 'SceneGraph',
           'Action', 'ActionType', 'MotionError', 'MotionErrorType', 'NodeIds', 'from_func_string',
           'parse_action_seq', 'parse_goal_relations', 'resolve_user_message', 'RESOLVE_SCHEMA', 'GOAL_SCHEMA']
