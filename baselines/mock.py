"""Mock model answers for the baselines, built from each variant's ground-truth actions.

A mock trial exercises a baseline's whole loop -- prompts, parsing, task-level search, sampling,
execution with our executor, scoring -- without a model server. The answers name only objects the
robot has observed (as ``llm_pipeline.oracle_trial_runner`` does), so hidden objects enter a plan
only after they have been seen. Mock trials are plumbing tests, not results.
"""

from __future__ import annotations

import json
from typing import List, Tuple

from baselines.common import observe, parse_action_text
from llm_pipeline.region_aliases import planner_region_name


class MockPlanner:
    """Stands in for the vLLM client in mock trials (no server)."""

    model_alias = 'mock_gt'
    model_name = 'mock_gt'
    model_type = 'vlm'
    quantization = 'none'
    loaded = True
    profile = {'system_prompt_mode': 'system', 'alias': 'mock_gt'}

    def __init__(self):
        from llm_pipeline.strict_parser import StrictActionParser

        self.parser = StrictActionParser()

    def load_model(self) -> bool:
        return True

    def planner_settings(self) -> dict:
        return {'planner': 'mock_gt', 'model_name': 'mock_gt', 'thinking_mode': None, 'format_repair': False}

    def get_debug_info(self) -> dict:
        return {'model_alias': 'mock_gt'}


def _remaining_gt(pipeline) -> List[Tuple[str, ...]]:
    from llm_pipeline.oracle_trial_runner import load_gt_actions

    remaining = list(load_gt_actions(pipeline.config.variant_id))
    for done in list(getattr(pipeline.executor, 'completed_primitive_actions', []) or []):
        if done in remaining:
            remaining.remove(done)
    return [parse_action_text(a) for a in remaining]


def _observed_steps(pipeline) -> List[List[Tuple[str, ...]]]:
    """Remaining GT actions as steps (pick+place pairs, open, close) on observed objects only."""
    obs = observe(pipeline)
    known = set(obs.objects) | set(obs.lids)
    actions = _remaining_gt(pipeline)
    steps, i = [], 0
    while i < len(actions):
        a = actions[i]
        if a[0] == 'pick' and i + 1 < len(actions) and actions[i + 1][0] == 'place' and actions[i + 1][1] == a[1]:
            step = [a, ('place', a[1], planner_region_name(actions[i + 1][2]))]
            i += 2
        else:
            step = [a if a[0] != 'place' else ('place', a[1], planner_region_name(a[2]))]
            i += 1
        if step[0][1] in known:
            steps.append(step)
    return steps


def vlm_tamp_responder(pipeline):
    from baselines.vlm_tamp import space_regions

    def respond(purpose: str, turns) -> str:
        steps = _observed_steps(pipeline)
        if purpose.endswith('english'):
            return '\n'.join(f'{n + 1}. ' + ' then '.join(f'{a[0]} {" ".join(a[1:])}' for a in step)
                             for n, step in enumerate(steps))
        spaces = set(space_regions(observe(pipeline).regions))
        subgoals = []
        for step in steps:
            last = step[-1]
            if last[0] == 'place':
                # as the model writes them: picked(o), then in/on(o, r)
                subgoals.append(f'picked({last[1]})')
                subgoals.append(f"{'in' if last[2] in spaces else 'on'}({last[1]}, {last[2]})")
            elif last[0] == 'open':
                subgoals.append(f'opened-door({last[1]})')
            elif last[0] == 'close':
                subgoals.append(f'closed-door({last[1]})')
            elif last[0] == 'pick':
                subgoals.append(f'picked({last[1]})')
        return '[' + ', '.join(f"'{s}'" for s in subgoals) + ']'

    return respond


def owl_tamp_responder(pipeline):
    def respond(purpose: str, turns) -> str:
        if purpose == 'owl_tamp_discrete':
            from baselines.vlm_tamp import space_regions

            steps = _observed_steps(pipeline)
            spaces = set(space_regions(observe(pipeline).regions))

            def owl_op(a):
                if a[0] == 'place':
                    return ('place_inside' if a[2] in spaces else 'place_ontop', a[1], a[2])
                return a
            # (inside for a space, on top of for a surface, as the typed operators require)
            lines = [f"{o[0]}({', '.join(o[1:])}); {o[0]} as in the reference sequence"
                     for s in steps for o in map(owl_op, s)]
            # as the model writes it: the plate object as the support, not its top region
            lines = [l.replace(', plate_top)', ', plate)') for l in lines]
            placed = sorted({a[1] for s in steps for a in s if a[0] == 'place'})
            return ('The scene and task are as described.\nThe relevant objects are listed in the plan.\n'
                    'No particular obstacles.\nPlan:\n' + '\n'.join(lines) +
                    f"\nachieve_goal({', '.join(placed)}); every listed object ends in its goal region")
        if purpose == 'owl_tamp_goal_constraints':
            return '```python\ndef goal_check0() -> bool:\n    return True\n```'
        # action constraints: the placed object lies over its target region
        prompt = turns[-1][1]
        line = prompt.split('right after the robot executes the operator\n', 1)[-1].splitlines()[0]
        op = parse_action_text(line.split(';', 1)[0])
        if op and op[0] == 'place_ontop' and op[2] == 'plate':      # on top of the plate object, as the model wrote
            return ('```python\ndef goal_check0() -> bool:\n'
                    f'    bounds = modify_pose_bounds_to_be_ontop_of_object(init_state, env, init_bounds, {op[1]}.category, '
                    'plate.category)\n'
                    f'    return position_within_bounds({op[1]}.pose, bounds)\n```')
        if not op or op[0] not in ('place_ontop', 'place_inside'):
            return '```python\ndef goal_check0() -> bool:\n    return True\n```'
        helper = 'inside' if op[0] == 'place_inside' else 'ontop_of'
        return ('```python\ndef goal_check0() -> bool:\n'
                f'    bounds = modify_pose_bounds_to_be_{helper}_object(init_state, env, init_bounds, {op[1]}.category, '
                f'{op[2]}.category)\n'
                f'    return position_within_bounds({op[1]}.pose, bounds)\n```\n')

    return respond


def llm_planner_responder(pipeline):
    def respond(purpose: str, turns) -> str:
        obs = observe(pipeline)
        entries = []
        for step in _observed_steps(pipeline):
            for a in step:
                if a[0] == 'pick':
                    entries.append(f'Pick({a[1]}, {obs.objects.get(a[1]) or "table"})')
                elif a[0] == 'place':
                    entries.append(f'Place({a[1]}, {a[2]})')
                else:
                    entries.append(f'{a[0].capitalize()}({a[1]})')
        return 'Here is the plan.\n{\n "Plan": [' + ', '.join(f'"{e}"' for e in entries) + ']\n}'

    return respond


def inner_monologue_responder(pipeline):
    def respond(purpose: str, turns) -> str:
        lines = [f"{a[0]}({', '.join(a[1:])})" for step in _observed_steps(pipeline) for a in step]
        return 'FINAL ACTIONS:\n' + ('\n'.join(lines) if lines else 'NO_ACTIONS')

    return respond


def epog_responder(pipeline):
    """Goal relations: each observed object's last GT placement; resolve: as the authors' prompt example reasons."""
    from baselines.epog import SURFACE_OBJECT, example_resolution

    def respond(purpose: str, turns) -> str:
        if purpose == 'epog_resolve':
            actions = example_resolution(pipeline._last_motion_error, pipeline.ids)
            return json.dumps({'steps': [{'explanation': 'rule-based', 'output': a} for a in actions],
                               'final_answer': [{'action': a} for a in actions]})
        prompt = turns[-1][1]
        wanted = prompt.rsplit('child is one of these objects: ', 1)[1].split(', relationType', 1)[0].split(', ')
        final = {}
        for a in _remaining_gt(pipeline):
            if a[0] == 'place':
                final[a[1]] = planner_region_name(a[2])
        relations = [{'children': o, 'relationType': 'on', 'parent': SURFACE_OBJECT.get(final[o], final[o])}
                     for o in wanted if o in final]
        return json.dumps({'relations': relations})

    return respond


RESPONDERS = {'vlm_tamp': vlm_tamp_responder, 'owl_tamp': owl_tamp_responder,
              'llm_planner': llm_planner_responder,
              'llm_planner_refprompt': llm_planner_responder, 'inner_monologue': inner_monologue_responder,
              'epog': epog_responder, 'epog_language_goal': epog_responder}
