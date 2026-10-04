"""LLM-Planner (Song et al., "LLM-Planner: Few-Shot Grounded Planning for Embodied Agents with Large
Language Models", ICCV 2023) in our scenes, after the re-implementation in the EPoG repository
(buaa-colalab/EPoG, epog/algorithm/baseline/LLM_Planner.py, Apache-2.0).

The method, as in that re-implementation:

* One query generates the full plan from the current state and the goal (the reference's system
  and user prompts, its JSON ``{"Plan": [...]}`` output and its parsing: ``Pick(x, y)``,
  ``Place(x, y)``, ``Open(x)``, ``Close(x)``; an entry that does not parse is skipped, as in
  ``BaseLLMPlanner.json_to_actions``).
* The plan is executed step by step. When a step cannot be executed (the reference's "check 2":
  ``roll_out`` skipped by the environment), the full remaining plan is regenerated from scratch
  from the new state (a global replan); LLM-Planner's dynamic re-planning also re-plans when the
  agent observes an object it had not seen, so a newly observed object triggers the same replan.
* No corrective blocks, no urgency, no concurrent execution: every replan replaces the plan.

Adapted to our scenes (docs/BASELINES.md lists every deviation):

* No ``Walk``: our robot is a fixed arm, so the walk action, the robot-location line of the
  prompt and the reference's "check 1" (the robot is not at the receptacle -> replan) are removed.
* Names instead of numeric node ids (our objects and regions have unique names). The current
  state is the reference's belief-graph text ("x is on y"), for the visible objects, plus the lid
  states, the gripper and the list of regions (empty regions are not on any edge); the goal is
  the natural-language goal (the reference gives the task graph's edges; LLM-Planner's own input
  is the instruction).
* Execution is ours: a pick and the place of the same object run as one executor call (our
  bundles), with our pre-action checks. ``Pick(x, y)`` is checked against where ``x`` is observed
  (the reference's action is the graph edge (y, x)): a wrong source fails the step, which triggers a
  replan; our pick then takes the object. A step naming an unknown object, region or action fails like a step the environment
  skips. The model receives the same camera image our planner receives.
* The replan budget is ours (``max_replans``, 10): the initial plan plus at most 10 replans.
"""

from __future__ import annotations

import json
import re
from typing import Iterable, List, Optional, Sequence, Tuple

from baselines.common import BaselinePipeline, action_text, observe, strip_reasoning, surface_region_of
from llm_pipeline.failures import TerminationReason
from llm_pipeline.prompt_v2 import ACTION_DEFINITIONS, LID_REGIONS, LID_TOP_REGIONS
from llm_pipeline.region_aliases import planner_region_name

# --- the reference's prompts (LLM_Planner.py get_plan), walk removed -------------------------------

SYSTEM_PROMPT = """You are an AI robot that generate a plan of actions to reach the goal.
The goal is to perform pick and place actions to move objects from one location to another in the housing scenario.
You will be given the initial state of the environment and the goal state.
The primitive actions are {action_names}:
{action_lines}
The robot can only perform one action at a time.
x, y should be the name of the object or location. For the same object, Pick must be performed before Place.
"""

ACTION_LINES = {
    'pick': "'Pick(x, y): Pick x from y'",
    'place': "'Place(x, y): Place x on y',",
    'open': "'Open(x): Open container x',",
    'close': "'Close(x): Close container x',",
}

# Added to the reference prompt: the preconditions and effects of the actions in this scene, as our
# planner receives them (prompt_v2.ACTION_DEFINITIONS; the other baselines have them in their
# task-level search). The reference's domain has no such preconditions (an open needs nothing).
DOMAIN_DEFINITIONS = """
Preconditions and effects of the actions (o and x: an object; r and y: a location; l: a lid that opens a container):
"""

USER_PROMPT = """The current state of the environment is given below.
{current_description}
The goal state is given below.
{goal_description}
Please organize the output following the json format below:

 "Plan":[
    "Pick(mug, table)",
    "Place(mug, shelf)",
]
"""

TWO_ARGS = re.compile(r'(\w+)\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*\)')
ONE_ARG = re.compile(r'(\w+)\(\s*([^,()]+?)\s*\)')


def get_json(text: str) -> str:
    """``get_json_from_llm``: from the first '{' to the last '}'."""
    return text[text.find('{'): text.rfind('}') + 1]


def parse_plan(text: str) -> Tuple[Optional[List[Tuple[str, ...]]], List[str]]:
    """The reference's parsing: JSON with a "Plan" list; entries that do not parse are skipped.

    Returns (actions, skipped entries); actions is None when the output has no valid JSON plan."""
    answer = strip_reasoning(text)
    try:
        data = json.loads(get_json(answer))
        raw = data['Plan']
        if not isinstance(raw, list):
            raise TypeError('Plan is not a list')
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
        return None, []
    actions, skipped = [], []
    for entry in raw:
        entry = str(entry).strip()
        two, one = TWO_ARGS.match(entry), ONE_ARG.match(entry)
        name = (two or one).group(1).lower() if (two or one) else None
        if two and name in ('pick', 'place'):
            x, y = two.group(2).strip('\'"'), two.group(3).strip('\'"')
            actions.append(('pick', x, y) if name == 'pick' else ('place', x, y))   # the pick keeps its source
        elif one and name in ('open', 'close'):
            actions.append((name, one.group(2).strip('\'"')))
        else:
            skipped.append(entry)
    return actions, skipped


def belief_description(obs) -> str:
    """``output_belief_graph`` over the visible objects ("x is on y"), then lids, gripper, regions."""
    spaces = {planner_region_name(r) for regions in LID_REGIONS.values() for r in regions}
    lines = []
    for obj, region in obs.objects.items():
        if obj == obs.holding:
            continue
        relation = 'in' if (region in spaces or (region or '').startswith('inside') or 'cupboard' in (region or '')) else 'on'
        lines.append(f'{obj} is {relation} {region or "an unknown location"}')
    for lid, is_open in obs.lids.items():
        closes = ', '.join(planner_region_name(r) for r in LID_REGIONS.get(lid, ()))
        top = f'; its top surface is {planner_region_name(LID_TOP_REGIONS[lid])}' if lid in LID_TOP_REGIONS else ''
        lines.append(f'{lid} is {"open" if is_open else "closed"} (it closes off {closes}{top})')
    lines.append(f'The robot is holding {obs.holding}' if obs.holding else 'The robot is holding nothing')
    lines.append('Locations: ' + ', '.join(obs.regions))
    return '\n'.join(lines)


def split_bundles(actions: Sequence[Tuple[str, ...]]) -> List[List[Tuple[str, ...]]]:
    """Our executor's bundles: pick(o) with the place(o, r) right after it; other actions alone."""
    out, i = [], 0
    while i < len(actions):
        a = actions[i]
        if a[0] == 'pick' and i + 1 < len(actions) and actions[i + 1][0] == 'place' and actions[i + 1][1] == a[1]:
            out.append([a, actions[i + 1]])
            i += 2
        else:
            out.append([a])
            i += 1
    return out


def unknown_names(bundle: Sequence[Tuple[str, ...]], obs, actions_available: Sequence[str],
                  seen: Iterable[str] = ()) -> List[str]:
    """Names in the bundle that are not in the scene (the step is skipped by the environment). An
    object observed earlier in the trial is known even when the cameras miss it now (occluded): the
    executor's pre-pick check allows it for a baseline, the allowance our memory gives our system."""
    bad = []
    known = set(obs.objects) | set(seen)
    for a in bundle:
        if a[0] not in actions_available:
            bad.append(a[0])
        elif a[0] in ('pick', 'place') and a[1] not in known:
            bad.append(a[1])
        elif a[0] == 'place' and a[2] not in obs.regions:
            bad.append(a[2])
        elif a[0] in ('open', 'close') and a[1] not in obs.lids:
            bad.append(a[1])
    return bad


def container_lid(name: str, obs) -> Optional[str]:
    """The lid that opens a container named by the container (box) or its inside region (inside_box)."""
    for lid, regions in LID_REGIONS.items():
        container = lid[:-len('_lid')] if lid.endswith('_lid') else lid
        if lid in obs.lids and name in {container} | {planner_region_name(r) for r in regions}:
            return lid
    return None


def wrong_sources(bundle: Sequence[Tuple[str, ...]], obs) -> List[str]:
    """Pick(x, y) whose source y is not where x is observed (the reference's action is the graph edge
    (y, x), so a wrong y is a wrong action). The plate is the source of what is on plate_top."""
    bad = []
    for a in bundle:
        if a[0] == 'pick' and len(a) == 3 and a[1] in obs.objects and a[1] != obs.holding:
            region = obs.objects[a[1]]
            if region is None:
                continue                     # perception does not place it: nothing to contradict
            if a[2] != region and SURFACE_OF.get(region) != a[2]:
                bad.append(f'{a[1]} is in {region or "an unknown location"}, not {a[2]}')
    return bad


SURFACE_OF = {'plate_top': 'plate'}       # a region that is the top surface of an object -> the object


def resolve_supports(bundle: Sequence[Tuple[str, ...]], obs, containers: bool = False) -> List[Tuple[str, ...]]:
    """Place(x, plate): an object given as the location is its top surface (plate_top), as for VLM-TAMP.

    ``containers``: Open(x) / Close(x) of a container (the reference's "Open container x") opens or
    closes the lid that closes it off (Open(box) -> open(box_lid))."""
    out = []
    for a in bundle:
        if a[0] == 'place' and a[2] in obs.objects:
            a = ('place', a[1], surface_region_of(a[2], obs) or a[2])
        elif containers and a[0] in ('open', 'close') and a[1] not in obs.lids:
            a = (a[0], container_lid(a[1], obs) or a[1])
        out.append(a)
    return out


class StepLoopPipeline(BaselinePipeline):
    """Shared step loop of the closed-loop baselines: observe, execute one bundle, observe."""

    ground_containers = False      # Open(container) -> open(its lid)

    def observe_scene(self):
        return observe(self)

    def available_actions(self) -> Tuple[str, ...]:
        return tuple(self.context_builder._actions())

    def execute_bundle(self, bundle: Sequence[Tuple[str, ...]]) -> dict:
        """Execute one bundle with our executor: success, error message, failure code, failed action."""
        outcome = self.execute(bundle)
        event = outcome.last_failure_event
        failed_action = None
        if not outcome.success:
            failed_action = (str(event.action) if event is not None and event.action else None) or \
                (outcome.remaining_actions[0] if outcome.remaining_actions else None)
        return {'success': bool(outcome.success), 'failure': outcome.error_message,
                'failure_code': str(event.failure_id) if event is not None else None, 'failed_action': failed_action}

    def query_image(self, obs):
        return obs.image

    def run_step(self, bundle, seen: set) -> dict:
        """Run one bundle; the step's record (executed, failure, newly observed objects)."""
        obs = self.observe_scene()
        bundle = resolve_supports(bundle, obs, containers=self.ground_containers)
        wrong = wrong_sources(bundle, obs)
        bundle = [a[:2] if a[0] == 'pick' else a for a in bundle]       # our pick takes the object
        bad = unknown_names(bundle, obs, self.available_actions(), seen)
        step = {'bundle': [action_text(a) for a in bundle]}
        if wrong:
            step.update(success=False, failure='wrong pick source: ' + '; '.join(wrong), failure_code='wrong_pick_source',
                        failed_action=step['bundle'][0])
        elif bad:
            step.update(success=False, failure=f'unknown name(s): {", ".join(bad)}', failure_code='unknown_name',
                        failed_action=step['bundle'][0])
        else:
            result = self.execute_bundle(bundle)
            step.update(result)
            if not result['success']:
                step['failure'] = result['failure'] or 'execution failed'
                step['failed_action'] = result['failed_action'] or step['bundle'][0]
        after = self.observe_scene()
        new = sorted(o for o in after.objects if o not in seen)
        seen.update(after.objects)
        step['newly_observed'] = new
        return step


class LLMPlannerPipeline(StepLoopPipeline):
    """The reference prompt with the scene's action definitions added (DOMAIN_DEFINITIONS), and
    Open(container) grounded to the container's lid."""

    baseline_name = 'llm_planner'
    domain_definitions = True
    ground_containers = True

    def system_prompt(self) -> str:
        names = [n for n in ('pick', 'place', 'open', 'close') if n in self.available_actions()]
        system = SYSTEM_PROMPT.format(action_names=', '.join(names),
                                      action_lines='\n'.join(ACTION_LINES[n] for n in names))
        if self.domain_definitions:
            system += DOMAIN_DEFINITIONS + '\n'.join(ACTION_DEFINITIONS[n] for n in names) + '\n'
        return system

    def query_plan(self, goal_text: str, obs, purpose: str) -> Tuple[Optional[List[Tuple[str, ...]]], dict]:
        system = self.system_prompt()
        user = USER_PROMPT.format(current_description=belief_description(obs), goal_description=goal_text)
        out = self.chat().complete([('user', user)], image=self.query_image(obs), purpose=purpose, system=system)
        plan, skipped = parse_plan(out['content'])
        return plan, {'purpose': purpose, 'answer': strip_reasoning(out['content']),
                      'plan': None if plan is None else [action_text(a) for a in plan], 'skipped_entries': skipped,
                      'observation': obs.to_dict()}

    def run_baseline(self, goal_text: str) -> Optional[str]:
        trace = self._baseline_trace
        budget = int(self.config.max_replans)
        trace.update({'queries': [], 'steps': [], 'max_replans': budget})
        seen = set(self.observe_scene().objects)
        replans = 0
        reason = None                      # why the next query is a replan
        while True:
            obs = self.observe_scene()
            seen.update(obs.objects)
            plan, query = self.query_plan(goal_text, obs, 'llm_planner_plan' if reason is None else 'llm_planner_replan')
            query['replan_reason'] = reason
            trace['queries'].append(query)
            if plan is None:
                reason = 'output_not_valid_json'
            elif not plan:
                self.record_cycle(reason is not None, [], query['answer'], 0.0, True)
                return None                # an empty plan: the planner considers the goal reached
            else:
                reason = None
                for bundle in split_bundles(plan):
                    step = self.run_step(bundle, seen)
                    trace['steps'].append(step)
                    if not step['success']:
                        reason = f"step failed: {step['failure']}"
                        break
                    if step['newly_observed']:
                        reason = f"new objects observed: {', '.join(step['newly_observed'])}"
                        break
            self.record_cycle(len(trace['queries']) > 1, query['plan'] or [], query['answer'], 0.0, reason is None,
                              error=reason)
            if reason is None:
                return None                # the plan ran to its end
            if replans >= budget:
                self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
                return f'{reason}; replan budget exhausted'
            replans += 1


class LLMPlannerReferencePromptPipeline(LLMPlannerPipeline):
    """The reference prompt verbatim (walk removed): no action preconditions, Open(x) only for a lid name."""

    baseline_name = 'llm_planner_refprompt'
    domain_definitions = False
    ground_containers = False


__all__ = ['LLMPlannerPipeline', 'LLMPlannerReferencePromptPipeline',  'StepLoopPipeline', 'parse_plan', 'belief_description', 'split_bundles',
           'SYSTEM_PROMPT', 'USER_PROMPT']
