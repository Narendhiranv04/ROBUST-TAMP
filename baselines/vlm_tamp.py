"""VLM-TAMP (Yang et al., "Guiding Long-Horizon Task and Motion Planning with Vision Language
Models") in our scenes, as the authors define it (Learning-and-Intelligent-Systems/kitchen-worlds,
pybullet_planning/vlm_tools: prompts_gpt4v.py, vlm_planning_api.py, vlm_utils.py,
world_builder/world_utils.py), planning mode ``sequence-reprompt``.

The method's own input, verbatim:

* Query 1 (``prompt_subgoals_english``): the goal, the list of object names, the observed facts
  ("the X is in/on the Y", "<joint> is fully closed"), the history, "You are a mobile robot with
  one arm" and the five commonsense rules; the query image with ``composed_annotated_image_description``
  appended to the prompt (``vlm_api.ask``).
* The query image (``generate_query_images``): one downward camera view twice, side by side --
  the first labelled with the movable objects and joints, the second with the movable objects,
  surfaces and spaces -- each name drawn with its segmentation bounding box.
* Query 2 (``prompt_english_to_subgoals``, the same conversation): the authors' full subgoal
  catalogue, with the objects by type (``world.get_objects_by_type``: pformat of every category).
* Parsing as ``parse_subgoals``: ``preds_rename`` (opened-door/-drawer -> openedjoint, ...),
  ``preds_skipped`` (pressed, stirred, chopped), subgoals naming an unknown object are skipped.
* The subgoals are achieved in order; a failed subgoal re-prompts with ``include_history`` (the
  achieved subgoals, what the robot holds, "do not list this subgoal as the first ..."); at most
  two re-prompts (``len(replan_memory) < 2``). An empty list or the last subgoal ends the episode.

The scene side: our articulated parts are lids, which in the authors' world model are joints of
type door; our objects and regions are given the authors' categories (movable, food, surface,
space, joint, door), the semantic types from each object's benchmark category (CATEGORY_TYPES), as
the authors' world model gives them.

Refinement (the TAMP half; Algorithm 1): each subgoal is refined before anything of it is executed:
(1) discretely, the shortest pick / place / open / close sequence that achieves it from the observed
state, prerequisite actions included (bounded by the search's expansion budget, no depth cap); (2)
geometrically, in the kitchen, every pick-place of that sequence by our planner -- the executor's
PDDLStream refinement (grasp, IK and motion streams) run on the scene as the sequence predicts it
(baselines.planning_model), with place poses from the scene's sampler (MAX_PLACE_SAMPLES tries per
transfer). A subgoal whose refinement fails is a failed subgoal before execution; the bodies the robot
collided with while planning (baselines.collisions) go into the reprompt in the authors' words
(get_action_history_and_failure: "When trying to solve the previous problem in simulation. The
robot has collided with these objects: [...]"). The refined poses are the ones executed. The grill
executor plans each stage while it moves, so grill subgoals are refined discretely before execution
and geometrically by the executor as it runs (its collisions also reach the reprompt).

Adapted, and why:
* picked(x) followed by the subgoal placing x run as one executor call (one refinement, one
  execution), with each subgoal keeping its own result: our executor plans a pick together with its
  place, and a pick and a place sent as separate calls take its weaker held-object paths. This
  removes the observation between the two subgoals.
* Object reduction (REDUCE-OBJECT) is disabled: every observed object is passed to each refinement
  (our scenes have at most ~10 objects).
* Objects appear once the robot observes them, by the study's protocol (the authors' world model
  also names objects inside closed storage); hidden objects' identities are not given.
* A place subgoal holds when perception sees the object in the target region; an object perception
  no longer sees after its place counts only if the executor's post-place check confirmed it in the
  target region.
* The model runs with its card sampling (the authors used GPT-4V at temperature 0.2 / 0.0,
  max_tokens 1000).
"""

from __future__ import annotations

import re
from pprint import pformat
from typing import Dict, List, Optional, Tuple

from baselines.common import BaselinePipeline, SymbolicDomain, action_text, observe, region_closed_by, surface_region_of
from baselines.icl_examples import examples_for
from llm_pipeline.failures import TerminationReason

# --- the authors' prompts (prompts_gpt4v.py), verbatim ------------------------------------------

PROMPT_PLANNING = """
Plan a short sequence of [OUTPUT] that accomplishes the following goal:
``{goal}''.
[RESPOND_WITH]
where <obj>, <surface>, <joint>, <button> and <handle> must be items from the following list:
{objects}.

Currently, you can see the following objects:
``{observed}''
{history}
You are a mobile robot with {n_arms}. You must obey the following commonsense rules:
1. You must have at least one empty hand before you can pick up an object or open or close a joint.
2. When you sprinkle or pour something into a container, there must not be objects placed on top of the container.
3. You can only take actions on objects that you can see.
4. If you cannot see an object, it may be behind a door or inside drawer.
5. If you cannot see the inside of a space, you must open its door or drawer before you can pick objects from it or place objects inside it.
"""

INCLUDE_HISTORY = """
You have already taken the following actions written in a formal language:
{actions}

You just failed at planning for {failure}.

"""

PROMPT_SUBGOALS_ENGLISH = (PROMPT_PLANNING.replace('[OUTPUT]', 'intermediate goals')
                           .replace('<obj>, <surface>, <joint>, <button> and <handle>', 'objects mentioned')
                           .replace('[RESPOND_WITH]', """
Respond with detailed but simple instructions in English. Each line must consists of only one intermediate goal, """))

PROMPT_ENGLISH_TO_SUBGOALS = """
Translate the above intermediate goals into a formal language defined by the following subgoals.

subgoals =
[
'picked(<movable>)': the result of picking up <movable>, it contains one argument.
'in(<movable>, <space>)': the result of picking up <movable> and placing it inside <space>, it contains two arguments.
'on(<movable>, <surface>)': the result of picking up <movable> and placing it on <surface>, it contains two arguments.
'sprinkled-to(<movable>, <region>)': the result of picking up <movable> and sprinkling it into <region>, it contains two arguments.
'stirred(<region>, <movable>)': the result of picking up <movable> to stir <region>, it contains two arguments.
'chopped(<movable>, <utensil>)': the result of picking up <utensil> to chop <movable>, it contains two arguments.
'opened-door(<door>)': the result of opening <door>, it contains one argument.
'closed-door(<door>)': the result of closing <door>, it contains one argument.
'opened-drawer(<drawer>)': the result of closing <drawer>, it contains one argument.
'closed-drawer(<drawer>)': the result of closing <drawer>, it contains one argument.
'pressed(<button>)': the result of pressing <button>, it contains one argument.
'turned-on(<knob>)': the result of turning <handle> or <knob> to start up the associated appliance, it contains one argument.
'turned-off(<knob>)': the result of turning <handle> or <knob> to shut down the associated appliance, it contains one argument.
],

The above subgoals include argument types. Please use the objects in the respective types:
``
{objects}
''

Return the subgoals in a list and give no explanation.
Make sure the sub-goals are in the same order as the steps in the intermediate goals.
Note that the arguments shouldn't include robot parts, e.g., 'arm', 'gripper'.
If a new object not mentioned in the set of objects is used as arguments, please name it with the same as the object that constitutes it the most and exists in the given list of objects.
If one intermediate goal cannot be translated into a sub-goal, skip that step.
"""

COMPOSED_ANNOTATED_IMAGE_DESCRIPTION = """
The accompanying image is a collage of two images depicting a scene with a robot in a kitchen.
There are different sets of annotations of object names with object bounding boxes drawn on the images.
"""

# vlm_utils.py
PREDS_RENAME = {
    'sprinkled-into': 'sprinkledto', 'sprinkled-to': 'sprinkledto', 'poured-into': 'pouredto',
    'poured-to': 'pouredto', 'opened': 'openedjoint', 'closed': 'closedjoint', 'pulled-open': 'openedjoint',
    'pulled-close': 'closedjoint', 'opened-door': 'openedjoint', 'opened-drawer': 'openedjoint',
    'closed-door': 'closedjoint', 'closed-drawer': 'closedjoint', 'turned-on': 'openedjoint',
    'turned-off': 'closedjoint', 'place': 'arrange',
}
PREDS_SKIPPED = ['pressed', 'stirred', 'chopped', 'stir', 'chop']

MAX_REPROMPTS = 2        # ``len(self.agent_memory['replan_memory']) < 2``
MAX_PLACE_SAMPLES = 5    # place poses tried per pick-place during a subgoal's geometric refinement
N_ARMS = 'one arm'
QUERY_CAMERA = 'front'   # the authors' query camera is "tilted downward" (world.cameras[1])
SUBGOAL = re.compile(r"([a-z][a-z_-]*)\s*\(([^()]*)\)")
# world.summarize_all_types(categories=extra_categories), in the authors' order
CATEGORIES = ['movable', 'surface', 'space', 'joint', 'door', 'drawer',
              'food', 'utensil', 'condiment', 'appliance', 'region', 'button', 'knob']
# Semantic types as the authors' world model gives them, from each object's benchmark category
# (evaluation.labeled_rules.object_category); every object is also movable, the plate also a surface.
CATEGORY_TYPES = {'grocery': 'food', 'raw_meat': 'food', 'cooked_meat': 'food', 'mug': 'movable',
                  'phone': 'movable', 'plate': 'movable'}


def object_type(name: str) -> str:
    from evaluation.labeled_rules import object_category

    return CATEGORY_TYPES.get(object_category(name), 'movable')


# --- the scene in the authors' world-model terms -------------------------------------------------

def space_regions(regions) -> List[str]:
    return [r for r in regions if region_closed_by(r) is not None or r.startswith('inside') or 'cupboard' in r]


def categories(obs) -> Dict[str, List[str]]:
    spaces = space_regions(obs.regions)
    cats = {c: [] for c in CATEGORIES}
    cats['movable'] = list(obs.objects)
    cats['food'] = [o for o in obs.objects if object_type(o) == 'food']
    cats['space'] = spaces
    cats['surface'] = [r for r in obs.regions if r not in spaces] + [o for o in obs.objects if surface_region_of(o, obs)]
    cats['joint'] = list(obs.lids)
    cats['door'] = list(obs.lids)
    return cats


def objects_by_type(obs) -> str:
    return pformat({f'<{c}>': names for c, names in categories(obs).items()}, indent=3)


def observed_descriptions(obs) -> List[str]:
    """``get_observed_objects``: attachments ("the X is in/on the Y"), then every joint's status."""
    spaces = set(space_regions(obs.regions))
    lines = [f"the {obj} is {'in' if region in spaces else 'on'} the {region}"
             for obj, region in obs.objects.items() if region is not None]
    lines += [f'{lid} is {"fully open" if is_open else "fully closed"}' for lid, is_open in obs.lids.items()]
    return lines


def query_image(pipeline, obs):
    """``generate_query_images``: the query camera's view twice, labelled as the authors do."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    from llm_pipeline.object_aliases import canonical_object_name
    from llm_pipeline.region_aliases import planner_region_name

    detector = getattr(pipeline.segmentation_adapter, 'detector', None)
    frames = pipeline._capture_rgb_frames()
    if not frames or detector is None:
        return obs.image
    camera = QUERY_CAMERA if QUERY_CAMERA in frames else next(iter(frames))
    rgb = frames[camera]
    try:
        mask = detector._capture_mask(camera)
    except Exception:
        mask = None
    if mask is None or getattr(mask, 'shape', None)[:2] != rgb.shape[:2]:
        return obs.image
    names: Dict[int, str] = {}
    for handle, task in getattr(detector, 'handle_to_task_name', {}).items():
        names[int(handle)] = canonical_object_name(task)
    for handle, region in getattr(detector, 'handle_to_region_name', {}).items():
        names.setdefault(int(handle), planner_region_name(region))
    cats = categories(obs)
    first = set(cats['movable']) | set(cats['joint'])
    second = set(cats['movable']) | set(cats['surface']) | set(cats['space'])

    def boxes(wanted):
        out = {}
        for handle in np.unique(mask):
            name = names.get(int(handle))
            if name is None or name not in wanted or name.endswith('space'):
                continue
            ys, xs = np.nonzero(mask == handle)
            if len(xs) < 20:
                continue
            x0, y0, x1, y1 = xs.min(), ys.min(), xs.max(), ys.max()
            prev = out.get(name)
            out[name] = (min(x0, prev[0]), min(y0, prev[1]), max(x1, prev[2]), max(y1, prev[3])) if prev else (x0, y0, x1, y1)
        return out

    def panel(wanted):
        image = Image.fromarray(rgb[:, :, :3]).convert('RGB').resize((800, 600))
        sx, sy = 800 / rgb.shape[1], 600 / rgb.shape[0]
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        used = []
        for name, (x0, y0, x1, y1) in sorted(boxes(wanted).items(), key=lambda kv: kv[1][0]):
            box = (x0 * sx, y0 * sy, x1 * sx, y1 * sy)
            draw.rectangle(box, outline=(255, 0, 0), width=2)
            tx, ty = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            while any(abs(ty - u) < 14 and abs(tx - v) < 80 for u, v in used):      # keep labels apart
                ty += 14
            used.append((ty, tx))
            w = draw.textlength(name, font=font)
            draw.rectangle((tx - w / 2 - 2, ty - 7, tx + w / 2 + 2, ty + 7), fill=(255, 255, 255))
            draw.text((tx - w / 2, ty - 6), name, fill=(0, 0, 0), font=font)
        return image

    a, b = panel(first), panel(second)
    collage = Image.new('RGB', (a.width + b.width + 20, a.height), (255, 255, 255))
    collage.paste(a, (0, 0))
    collage.paste(b, (a.width + 20, 0))
    return np.asarray(collage)


# --- parsing and refinement ------------------------------------------------------------------------

def parse_subgoals(text: str, obs) -> Tuple[List[Tuple[str, ...]], List[str]]:
    """``parse_subgoals``: renames, skipped predicates, unknown objects skip the subgoal."""
    from baselines.common import strip_reasoning

    known = set(obs.objects) | set(obs.regions) | set(obs.lids)
    subgoals, skipped = [], []
    for pred, args in SUBGOAL.findall(strip_reasoning(text)):
        if len(pred) + len(args) + 2 < 4:
            continue
        if pred in PREDS_SKIPPED:
            skipped.append(f'{pred}({args})')
            continue
        pred = PREDS_RENAME.get(pred, pred)
        names = [a.strip().strip('\'"') for a in args.split(',') if a.strip()]
        if len(names) == 2 and names[1] in ('arm', 'hand', 'gripper'):
            pred, names = 'picked', names[:1]
        if any(n not in known for n in names):
            skipped.append(f'{pred}({", ".join(names)})')
            continue
        if pred in ('in', 'on') and len(names) == 2 and names[1] in obs.objects:
            # an object as the support: its surface (the plate's top), as in the authors' world model
            names[1] = surface_region_of(names[1], obs) or names[1]
        subgoals.append((pred,) + tuple(names))
    return subgoals, skipped


def subgoal_text(subgoal: Tuple[str, ...]) -> str:
    return f"{subgoal[0]}({', '.join(subgoal[1:])})"


def subgoal_test(subgoal: Tuple[str, ...]):
    """The subgoal as a condition on the symbolic state (None: not achievable in this scene)."""
    pred, args = subgoal[0], subgoal[1:]
    if pred == 'picked' and len(args) == 1:
        return lambda s: s.holding == args[0]
    if pred in ('in', 'on') and len(args) == 2:
        return lambda s: s.holding != args[0] and s.region_of(args[0]) == args[1]
    if pred in ('openedjoint', 'closedjoint') and len(args) == 1:
        want_open = pred == 'openedjoint'
        return lambda s: (args[0] in s.open_lids) == want_open
    return None


class VLMTAMPPipeline(BaselinePipeline):
    baseline_name = 'vlm_tamp'

    def observe_known(self):
        """The observation with every object observed earlier in the trial: one the cameras miss now
        (occluded) stays at the region it was last observed in, as objects stay in the authors' world
        model once known (and as the executor lets a baseline pick an object it has observed)."""
        obs = observe(self)
        obs.visible = set(obs.objects)              # what the cameras see now
        last = self.__dict__.setdefault('_last_regions', {})
        for name, region in obs.objects.items():
            if region is not None:
                last[name] = region
        for name, region in last.items():
            if name not in obs.objects:
                obs.objects[name] = region
        return obs

    @property
    def scene(self) -> str:
        return 'grill' if (self.config.task_family or '').lower() == 'grill' else 'kitchen'

    def query_subgoals(self, goal_text: str, obs, history: str) -> Tuple[List[Tuple[str, ...]], dict]:
        chat = self.chat()
        object_names = list(obs.objects) + list(obs.regions) + list(obs.lids)
        prompt = PROMPT_SUBGOALS_ENGLISH.format(goal=goal_text, objects=object_names,
                                                observed=',\n'.join(observed_descriptions(obs)),
                                                history=history, n_arms=N_ARMS)
        examples = examples_for(self)                            # ICL condition, grill scene only
        if examples:
            prompt += '\n' + examples + '\n'
        prompt += COMPOSED_ANNOTATED_IMAGE_DESCRIPTION           # vlm_api.ask: prompt += image_description
        image = query_image(self, obs)
        english = chat.complete([('user', prompt)], image=image, purpose='vlm_tamp_subgoals_english')
        from baselines.common import strip_reasoning

        translation = PROMPT_ENGLISH_TO_SUBGOALS.format(objects=objects_by_type(obs))
        formal = chat.complete([('user', prompt), ('assistant', strip_reasoning(english['content'])),
                                ('user', translation)], image=image, purpose='vlm_tamp_subgoals_string')
        subgoals, skipped = parse_subgoals(formal['content'], obs)
        return subgoals, {'english': strip_reasoning(english['content']), 'formal': strip_reasoning(formal['content']),
                          'subgoals': [subgoal_text(s) for s in subgoals], 'skipped': skipped,
                          'observation': obs.to_dict()}

    def refine(self, obs, test) -> Optional[List[Tuple[str, ...]]]:
        """The subgoal's discrete refinement: the shortest pick / place / open / close sequence from the
        observed state (prerequisite actions included), bounded by the search's expansion budget."""
        domain = SymbolicDomain(obs.objects, obs.regions, obs.lids)
        return domain.search(obs.symbolic(), test, max_depth=10 ** 6)

    def refine_geometry(self, obs, actions) -> Tuple[bool, list, List[str], Optional[str]]:
        """The subgoal's geometric refinement before anything is executed (kitchen): every pick-place
        of the refinement is refined by our planner (PDDLStream grasp / IK / motion) on the scene as the
        refinement predicts it, with place poses from the scene's sampler (MAX_PLACE_SAMPLES tries).
        Returns (feasible, (object, region, pose) to execute, collided bodies, failed transfer)."""
        from baselines.planning_model import planning_model, predict, refine_transfer, sample_place_pose

        if self.scene != 'kitchen':
            return True, [], [], None
        entries, collided = [], []
        predicted: Dict[str, list] = {}
        opened = [lid for lid, is_open in obs.lids.items() if is_open]
        with planning_model(self.env):
            i = 0
            while i < len(actions):
                a = actions[i]
                if a[0] == 'open':
                    opened.append(a[1])
                elif a[0] == 'pick' and i + 1 < len(actions) and actions[i + 1][0] == 'place' and actions[i + 1][1] == a[1]:
                    obj, region = a[1], actions[i + 1][2]
                    predict(self.env, predicted, opened)
                    feasible, pose = False, None
                    for _ in range(MAX_PLACE_SAMPLES):
                        pose = sample_place_pose(self.env, obj, region)
                        if pose is None:
                            break
                        feasible, _message, bodies = refine_transfer(self.env, obj, region, pose)
                        collided += [b for b in bodies if b not in collided]
                        if feasible:
                            break
                    if not feasible:
                        return False, entries, collided, f'{action_text(a)}, {action_text(actions[i + 1])}'
                    predicted[obj] = pose
                    entries.append((obj, region, pose))
                    i += 2
                    continue
                i += 1
        return True, entries, collided, None

    def execute_subgoals(self, subgoals, round_trace: dict, succeeded: List[str]) -> Tuple[Optional[str], List[str]]:
        """Achieve the subgoals in order: refine (discrete, then geometric), execute, check. Returns the
        failed subgoal (or None) and the bodies the robot collided with while planning / executing it."""
        from baselines.collisions import collision_bodies, recorded_collisions
        from baselines.planning_model import forced_placements

        failed, collided = None, []
        index = 0
        while index < len(subgoals):
            subgoal = subgoals[index]
            obs = self.observe_known()
            test = subgoal_test(subgoal)
            if test is None:
                failed = subgoal_text(subgoal)
                round_trace['subgoal_results'].append({'subgoal': failed, 'result': 'not achievable in this scene'})
                break
            if test(obs.symbolic()):
                succeeded.append(subgoal_text(subgoal))
                round_trace['subgoal_results'].append({'subgoal': subgoal_text(subgoal), 'result': 'already true'})
                index += 1
                continue
            actions = self.refine(obs, test)
            if actions is None:
                failed = subgoal_text(subgoal)
                round_trace['subgoal_results'].append({'subgoal': failed, 'result': 'no plan'})
                break
            # picked(x) followed by the subgoal that places x: both refinements run as one executor
            # call (our executor plans a pick together with its place; a pick and a place sent as
            # separate calls take its weaker held-object paths). Each subgoal keeps its own result.
            pair = None
            nxt = subgoals[index + 1] if index + 1 < len(subgoals) else None
            if subgoal[0] == 'picked' and nxt is not None and nxt[0] in ('in', 'on') and nxt[1] == subgoal[1] \
                    and actions == [('pick', subgoal[1])]:
                state = obs.symbolic()
                for a in actions:
                    state = SymbolicDomain.apply(state, a)
                domain = SymbolicDomain(obs.objects, obs.regions, obs.lids)
                more = domain.search(state, subgoal_test(nxt), max_depth=10 ** 6)
                if more:
                    pair = (nxt, more)
            plan = actions + (pair[1] if pair else [])
            feasible, entries, planning_collisions, failed_transfer = self.refine_geometry(obs, plan)
            if not feasible:
                # the TAMP refinement failed before execution: the subgoal (the first of a joint pair)
                failed = subgoal_text(subgoal)
                collided = planning_collisions
                round_trace['subgoal_results'].append({
                    'subgoal': failed, 'refined': [action_text(a) for a in plan], 'executed': False,
                    'result': 'refinement failed', 'failed_transfer': failed_transfer, 'collided': collided})
                break
            done_before = len(getattr(self.executor, 'completed_primitive_actions', []) or [])
            with recorded_collisions() as hits, forced_placements(self.env, entries,
                                                                  self._baseline_trace.setdefault('forced_placements', [])):
                outcome = self.execute(plan)
            execution_collisions = collision_bodies(hits, exclude=[a[1] for a in plan if a[0] == 'pick'])
            done = len(getattr(self.executor, 'completed_primitive_actions', []) or []) - done_before
            after = self.observe_known()
            steps = [(subgoal, actions, test)] + ([(pair[0], pair[1], subgoal_test(pair[0]))] if pair else [])
            end = 0
            for k, (goal_k, actions_k, test_k) in enumerate(steps):
                end += len(actions_k)
                executed_k = done >= end
                last = k == len(steps) - 1
                if last:
                    holds = test_k(after.symbolic())
                    # the target relation must be observed; an object perception no longer sees after
                    # its place counts only if the executor's post-place check confirmed it in the
                    # target region (outcome.success includes that check)
                    invisible = goal_k[0] in ('in', 'on') and goal_k[1] not in after.visible
                    ok = bool(outcome.success) and executed_k and (holds or invisible)
                    confirmed_by = 'perception' if holds else ('executor_post_place_check' if ok else None)
                else:
                    holds = executed_k        # the pick completed (the place that follows then released it)
                    ok = executed_k
                    confirmed_by = 'executor' if ok else None
                round_trace['subgoal_results'].append({
                    'subgoal': subgoal_text(goal_k), 'refined': [action_text(a) for a in actions_k],
                    'executed': executed_k, 'holds_after': holds, 'confirmed_by': confirmed_by,
                    'joint_execution': pair is not None, 'failure': None if ok else outcome.error_message,
                    'result': 'ok' if ok else 'failed'})
                if not ok:
                    failed = subgoal_text(goal_k)
                    collided = planning_collisions + [b for b in execution_collisions if b not in planning_collisions]
                    break
                succeeded.append(subgoal_text(goal_k))
            if failed is not None:
                break
            index += len(steps)
        return failed, collided

    def run_baseline(self, goal_text: str) -> Optional[str]:
        trace = self._baseline_trace
        trace.update({'rounds': [], 'max_reprompts': MAX_REPROMPTS, 'query_camera': QUERY_CAMERA})
        succeeded: List[str] = []
        history = ''
        for round_index in range(MAX_REPROMPTS + 1):
            obs = self.observe_known()
            subgoals, round_trace = self.query_subgoals(goal_text, obs, history)
            round_trace['subgoal_results'] = []
            trace['rounds'].append(round_trace)
            failed, collided = self.execute_subgoals(subgoals, round_trace, succeeded)
            round_trace['collision_bodies'] = collided
            self.record_cycle(round_index > 0, [a for r in round_trace['subgoal_results'] for a in r.get('refined', [])],
                              round_trace['formal'], 0.0, failed is None,
                              error=None if failed is None else f'subgoal {failed} failed')
            if failed is None:
                return None              # the subgoal list is exhausted (an empty list included)
            if round_index == MAX_REPROMPTS:
                self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
                return f'subgoal {failed} failed; re-prompt budget exhausted'
            # get_action_history_and_failure
            holding = observe(self).holding
            actions = '\n'.join(f'{i + 1}. {s}' for i, s in enumerate(succeeded))
            if holding:
                actions += f'\nCurrently, the robot is holding some objects. The left hand is holding {holding}. '
            failure = (f'subgoals {failed}. So please do not list this subgoals as the first subgoals to achieve '
                       f'in your answer.')
            if collided:
                failure += (f'\nWhen trying to solve the previous problem in simulation. '
                            f'The robot has collided with these objects: {collided}')
            history = INCLUDE_HISTORY.format(actions=actions, failure=failure)
        return 'unreachable'


__all__ = ['VLMTAMPPipeline', 'PROMPT_SUBGOALS_ENGLISH', 'PROMPT_ENGLISH_TO_SUBGOALS', 'parse_subgoals',
           'space_regions', 'categories']
