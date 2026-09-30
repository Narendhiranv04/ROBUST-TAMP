"""VLM-TAMP (Yang et al., "Guiding Long-Horizon Task and Motion Planning with Vision Language
Models") in our scenes, ported from the authors' code (Learning-and-Intelligent-Systems/
kitchen-worlds, pybullet_planning/vlm_tools: prompts_gpt4v.py, vlm_planning_api.py).

Protocol (as in the authors' ``_query_subgoals`` / ``backtrack_planning_tree``):

1. Query 1, with the image: ``prompt_subgoals_english`` -- the goal, the objects, the observed
   facts, the history, and the five commonsense rules -- asks for intermediate goals in English.
2. Query 2, the same conversation: ``prompt_english_to_subgoals`` translates them into formal
   subgoals from a predicate catalogue.
3. The subgoals are achieved one at a time: each is refined into primitive actions by task-level
   search from the observed state (the authors refine with PDDLStream; here the task level is
   ``SymbolicDomain`` and the continuous level is our executor's own PDDLStream pick/place with
   stable-pose, IK and motion samplers), executed, and checked.
4. When a subgoal fails, the model is re-prompted (a fresh query 1 + 2 from the current
   observation) with ``include_history``: the subgoals achieved so far, what the robot holds,
   and the failed subgoal ("do not list this subgoal as the first subgoal"). At most two
   re-prompts (the authors' ``len(replan_memory) < 2``). The episode ends when the subgoal
   list is exhausted or the re-prompt budget is.

Adaptations to our scenes (recorded in every trial's ``baseline_trace``):
* The subgoal catalogue keeps the authors' entries that exist in our scenes (picked, in, on)
  and their door/drawer entries become lid entries (our articulated parts are lids); entries
  for actions our scenes do not have (sprinkle, stir, chop, press, turn-on/off) are left out.
* The object list names only observed objects (the authors list every object of the world,
  including ones inside closed storage; our benchmark hides them until they are seen).
* "You are a mobile robot with one arm" -> "You are a robot with one arm" (fixed-base arm).
* A round whose translation yields no usable subgoal is treated as a failed round (re-prompt),
  not as a finished plan.
* Sampling: each model's card sampling, as for every planner in our comparison (the authors
  used temperature 0.2 with GPT-4V).
"""

from __future__ import annotations

import re
from pprint import pformat
from typing import List, Optional, Tuple

from baselines.common import (BaselinePipeline, SymState, SymbolicDomain, action_text, observe, region_closed_by,
                              strip_reasoning)
from llm_pipeline.failures import TerminationReason

# --- the authors' prompts (prompts_gpt4v.py), scene adaptations marked [ours] ---------------------

PROMPT_PLANNING = """
Plan a short sequence of [OUTPUT] that accomplishes the following goal:
``{goal}''.
[RESPOND_WITH]
where <obj>, <surface>, <joint>, <button> and <handle> must be items from the following list:
{objects}.

Currently, you can see the following objects:
``{observed}''
{history}
You are a robot with {n_arms}. You must obey the following commonsense rules:
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

# [ours] catalogue: the authors' entries present in our scenes; door/drawer entries -> lid entries.
PROMPT_ENGLISH_TO_SUBGOALS = """
Translate the above intermediate goals into a formal language defined by the following subgoals.

subgoals =
[
'picked(<movable>)': the result of picking up <movable>, it contains one argument.
'in(<movable>, <space>)': the result of picking up <movable> and placing it inside <space>, it contains two arguments.
'on(<movable>, <surface>)': the result of picking up <movable> and placing it on <surface>, it contains two arguments.
'opened-lid(<lid>)': the result of opening <lid>, it contains one argument.
'closed-lid(<lid>)': the result of closing <lid>, it contains one argument.
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

MAX_REPROMPTS = 2        # the authors' ``len(self.agent_memory['replan_memory']) < 2``
SUBGOAL = re.compile(r"([a-z][a-z_-]*)\s*\(([^()]*)\)")
LID_PREDICATES = {'opened-lid': True, 'opened-door': True, 'opened-drawer': True,
                  'closed-lid': False, 'closed-door': False, 'closed-drawer': False}


def _space_regions(regions) -> List[str]:
    return [r for r in regions if region_closed_by(r) is not None or r.startswith('inside') or 'cupboard' in r]


def observed_descriptions(obs) -> List[str]:
    """The authors' ``get_observed_objects`` facts: "the X is in/on the Y", lids and their state."""
    spaces = set(_space_regions(obs.regions))
    lines = []
    for obj, region in obs.objects.items():
        if region is None:
            continue
        lines.append(f"the {obj} is {'in' if region in spaces else 'on'} the {region}")
    for lid, is_open in obs.lids.items():
        lines.append(f'{lid} is {"open" if is_open else "closed"}')
    return lines


def objects_by_type(obs) -> str:
    spaces = _space_regions(obs.regions)
    summary = {'<movable>': list(obs.objects), '<space>': spaces,
               '<surface>': [r for r in obs.regions if r not in spaces], '<lid>': list(obs.lids)}
    return pformat(summary, indent=3)


def parse_subgoals(text: str, obs) -> Tuple[List[Tuple[str, ...]], List[str]]:
    """Subgoals in order; unknown predicates or objects are skipped, as in the authors' parser."""
    known = set(obs.objects) | set(obs.regions) | set(obs.lids)
    subgoals, skipped = [], []
    for pred, args in SUBGOAL.findall(strip_reasoning(text)):
        names = tuple(a.strip().strip('\'"') for a in args.split(',') if a.strip())
        arity = {'picked': 1, 'in': 2, 'on': 2}.get(pred, 1 if pred in LID_PREDICATES else None)
        if arity is None or len(names) != arity or any(n not in known for n in names):
            skipped.append(f'{pred}({", ".join(names)})')
            continue
        subgoals.append((pred,) + names)
    return subgoals, skipped


def subgoal_text(subgoal: Tuple[str, ...]) -> str:
    return f"{subgoal[0]}({', '.join(subgoal[1:])})"


def subgoal_test(subgoal: Tuple[str, ...]):
    pred, args = subgoal[0], subgoal[1:]
    if pred == 'picked':
        return lambda s: s.holding == args[0]
    if pred in ('in', 'on'):
        return lambda s: s.holding != args[0] and s.region_of(args[0]) == args[1]
    want_open = LID_PREDICATES[pred]
    return lambda s: (args[0] in s.open_lids) == want_open


class VLMTAMPPipeline(BaselinePipeline):
    baseline_name = 'vlm_tamp'

    def query_subgoals(self, goal_text: str, obs, history: str) -> Tuple[List[Tuple[str, ...]], dict]:
        chat = self.chat()
        # The authors list every body of the world (movables, surfaces, spaces, joints); here the observed ones.
        prompt = PROMPT_SUBGOALS_ENGLISH.format(goal=goal_text,
                                                objects=list(obs.objects) + list(obs.lids) + list(obs.regions),
                                                observed=',\n'.join(observed_descriptions(obs)),
                                                history=history, n_arms='one arm')
        english = chat.complete([('user', prompt)], image=obs.image, purpose='vlm_tamp_subgoals_english')
        translation = PROMPT_ENGLISH_TO_SUBGOALS.format(objects=objects_by_type(obs))
        formal = chat.complete([('user', prompt), ('assistant', strip_reasoning(english['content'])),
                                ('user', translation)], image=obs.image, purpose='vlm_tamp_subgoals_string')
        subgoals, skipped = parse_subgoals(formal['content'], obs)
        return subgoals, {'english': strip_reasoning(english['content']), 'formal': strip_reasoning(formal['content']),
                          'subgoals': [subgoal_text(s) for s in subgoals], 'skipped': skipped,
                          'observation': obs.to_dict()}

    def refine(self, obs, subgoal) -> Optional[List[Tuple[str, ...]]]:
        domain = SymbolicDomain(obs.objects, obs.regions, obs.lids)
        return domain.search(obs.symbolic(), subgoal_test(subgoal), max_depth=8)

    def run_baseline(self, goal_text: str) -> Optional[str]:
        trace = self._baseline_trace
        trace.update({'rounds': [], 'max_reprompts': MAX_REPROMPTS})
        succeeded: List[str] = []
        history = ''
        for round_index in range(MAX_REPROMPTS + 1):
            obs = observe(self)
            subgoals, round_trace = self.query_subgoals(goal_text, obs, history)
            round_trace['subgoal_results'] = []
            trace['rounds'].append(round_trace)
            failed = None
            if not subgoals:
                failed = ('the intermediate goals', 'no subgoal could be read from the translation')
            for subgoal in subgoals:
                obs = observe(self)
                if subgoal_test(subgoal)(obs.symbolic()):
                    succeeded.append(subgoal_text(subgoal))
                    round_trace['subgoal_results'].append({'subgoal': subgoal_text(subgoal), 'result': 'already true'})
                    continue
                actions = self.refine(obs, subgoal)
                if actions is None:
                    failed = (subgoal_text(subgoal), 'no task plan from the observed state')
                    round_trace['subgoal_results'].append({'subgoal': subgoal_text(subgoal), 'result': 'no plan'})
                    break
                outcome = self.execute(actions)
                after = observe(self)
                holds = subgoal_test(subgoal)(after.symbolic())
                # An object inside closed storage is not observed; the executor's success stands for it.
                invisible = subgoal[0] in ('in', 'on') and subgoal[1] not in after.objects
                ok = bool(outcome.success) and (holds or invisible)
                round_trace['subgoal_results'].append({
                    'subgoal': subgoal_text(subgoal), 'refined': [action_text(a) for a in actions],
                    'executed': bool(outcome.success), 'holds_after': holds,
                    'failure': outcome.error_message, 'result': 'ok' if ok else 'failed'})
                if not ok:
                    failed = (subgoal_text(subgoal), outcome.error_message or 'subgoal not achieved')
                    break
                succeeded.append(subgoal_text(subgoal))
            self.record_cycle(round_index > 0, [a for r in round_trace['subgoal_results'] for a in r.get('refined', [])],
                              round_trace['formal'], 0.0, failed is None,
                              error=None if failed is None else f'{failed[0]}: {failed[1]}')
            if failed is None:
                return None
            if round_index == MAX_REPROMPTS:
                self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
                return f'subgoal {failed[0]} failed ({failed[1]}); re-prompt budget exhausted'
            holding = observe(self).holding
            actions = '\n'.join(f'{i + 1}. {s}' for i, s in enumerate(succeeded))
            if holding:
                actions += f'\nCurrently, the robot is holding some objects. The hand is holding {holding}. '
            failure = (f'subgoals {failed[0]}. So please do not list this subgoals as the first subgoals to achieve '
                       f'in your answer.')
            history = INCLUDE_HISTORY.format(actions=actions, failure=failure)
        return 'unreachable'


__all__ = ['VLMTAMPPipeline', 'PROMPT_SUBGOALS_ENGLISH', 'PROMPT_ENGLISH_TO_SUBGOALS', 'parse_subgoals']
_ = SymState
