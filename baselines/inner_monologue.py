"""Inner Monologue (Huang et al., "Inner Monologue: Embodied Reasoning through Planning with Language
Models", CoRL 2022) in our scenes.

The method: the language model plans in a closed loop and is asked again after every step it
takes, with textual feedback added to its prompt as a running dialogue (the "inner monologue"):

* success detection -- whether the last action succeeded;
* passive scene description -- the objects in the scene, and the objects that became visible.

Here, after EVERY executed bundle (a pick with its place, or an open / close), the planner gets
the goal, the dialogue so far (each executed bundle with "Success: True/False" and the scene
feedback) and the current visible state, and returns the plan from now on; the robot executes its
first bundle and asks again. The episode ends when the planner returns NO_ACTIONS (the paper's
"done"). There is no trigger rule, no corrective block and no concurrent execution.

Adapted to our scenes (docs/baselines.md lists every deviation):

* Zero-shot, with our action definitions and output format (prompt v2 system prompt, FINAL
  ACTIONS / NO_ACTIONS), where the paper prompts few-shot with its own examples; the in-context
  examples of all baselines are off.
* The feedback is from our perception and executor (the failed action and, after each step, the
  newly visible objects with their regions); the paper's active scene description (questions to
  a human) has no counterpart and is not used. The model receives the same camera image our
  planner receives.
* The episode budget: at most ``max_replans`` (10) failed steps or unusable answers, and at most
  ``MAX_QUERIES`` queries in all.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from baselines.common import parse_action_text, strip_reasoning
from baselines.icl_examples import examples_for
from baselines.llm_planner import StepLoopPipeline, split_bundles
from llm_pipeline.failures import TerminationReason
from llm_pipeline.prompt_v2 import state_section, system_prompt
from llm_pipeline.region_aliases import planner_action_text

MAX_QUERIES = 30           # a step limit: ~3x the longest ground-truth plan in bundles (11)

LOOP_NOTE = ('The robot carries out the first step of your plan (one action, or a pick together with the place '
             'of the same object), then reports the result and the scene to you and asks you again.')


def parse_final_actions(text: str) -> Tuple[Optional[List[Tuple[str, ...]]], List[str]]:
    """Actions after the last 'FINAL ACTIONS:' line; [] for NO_ACTIONS; None without the marker or actions.

    Lines that are not an action are skipped (returned as the second value)."""
    answer = strip_reasoning(text)
    marker = answer.rfind('FINAL ACTIONS:')
    if marker < 0:
        return None, []
    actions, skipped = [], []
    for line in answer[marker + len('FINAL ACTIONS:'):].splitlines():
        line = line.strip().lstrip('-*').strip()
        if line[:1].isdigit() and '.' in line[:4]:
            line = line.split('.', 1)[1].strip()
        if not line:
            continue
        if line.upper() == 'NO_ACTIONS':
            return [], skipped
        action = parse_action_text(line)
        if action is None or action[0] not in ('pick', 'place', 'open', 'close'):
            skipped.append(line)
            continue
        actions.append(action)
    return (actions or None), skipped


def scene_line(objects: dict, holding: Optional[str]) -> str:
    seen = ', '.join(f'{o} ({"in the gripper" if o == holding else (r or "unknown")})' for o, r in objects.items())
    return f'Scene: visible objects: {seen or "(none)"}.'


def feedback_lines(step: dict, regions: dict) -> List[str]:
    """Success detection and passive scene description for one executed step."""
    lines = ['Robot action: ' + ', '.join(step['bundle'])]
    if step['success']:
        lines.append('Success: True')
    else:
        failed = planner_action_text(step.get('failed_action') or step['bundle'][0])
        lines.append(f'Success: False ({failed} did not succeed)')
    new = step.get('newly_observed') or []
    if new:
        lines.append('Scene: newly visible objects: ' + ', '.join(f'{o} ({regions.get(o) or "unknown"})' for o in new) + '.')
    else:
        lines.append('Scene: no new objects.')
    return lines


class InnerMonologuePipeline(StepLoopPipeline):
    baseline_name = 'inner_monologue'

    def current_state_text(self, obs) -> str:
        state = self._build_scene_state()
        builder = self.context_builder
        return '\n'.join(state_section(state, builder._regions(state), builder._lids()))

    def query(self, goal_text: str, obs, monologue: Sequence[str], purpose: str):
        system = system_prompt(self.available_actions())
        examples = examples_for(self)                            # ICL condition, grill scene only
        if examples:
            system += '\n\n' + examples
        user = '\n\n'.join([
            '## Goal\n' + goal_text,
            '## Inner monologue so far\n' + '\n'.join(monologue),
            self.current_state_text(obs),
            LOOP_NOTE,
        ])
        out = self.chat().complete([('user', user)], image=self.query_image(obs), purpose=purpose, system=system)
        plan, skipped = parse_final_actions(out['content'])
        return plan, {'purpose': purpose, 'answer': strip_reasoning(out['content']),
                      'plan': None if plan is None else [f"{a[0]}({', '.join(a[1:])})" for a in plan],
                      'skipped_lines': skipped}

    def run_baseline(self, goal_text: str) -> Optional[str]:
        trace = self._baseline_trace
        budget = int(self.config.max_replans)
        trace.update({'queries': [], 'steps': [], 'max_replans': budget, 'max_queries': MAX_QUERIES})
        obs = self.observe_scene()
        seen = set(obs.objects)
        monologue = [scene_line(obs.objects, obs.holding)]
        failures = 0
        last_failed = False
        for index in range(MAX_QUERIES):
            obs = self.observe_scene()
            purpose = 'inner_monologue_plan' if index == 0 else (
                'inner_monologue_replan' if last_failed else 'inner_monologue_step')
            plan, query = self.query(goal_text, obs, monologue, purpose)
            trace['queries'].append(query)
            if plan == []:
                self.record_cycle(index > 0, [], query['answer'], 0.0, True)
                return None                       # the planner reports the goal done
            if plan is None:
                monologue += ['Robot action: (none: the answer had no FINAL ACTIONS list of actions)', 'Success: False']
                step = None
                last_failed = True
            else:
                bundle = split_bundles(plan)[0]
                step = self.run_step(bundle, seen)
                trace['steps'].append(step)
                after = self.observe_scene()
                monologue += feedback_lines(step, after.objects)
                last_failed = not step['success']
            self.record_cycle(index > 0, query['plan'] or [], query['answer'], 0.0, not last_failed,
                              error=(step or {}).get('failure') if last_failed else None)
            if last_failed:
                failures += 1
                if failures > budget:
                    self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
                    return f'{failures} failed steps; replan budget exhausted'
        self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
        return f'{MAX_QUERIES} queries without the planner reporting the goal done'


__all__ = ['InnerMonologuePipeline', 'parse_final_actions', 'feedback_lines', 'MAX_QUERIES']
