"""Planner prompts, version 2 (``prompt.version = v2``; see docs/PROMPTS.md).

One template for every scene. A prompt contains only: the planner's role, the
action set with generic preconditions and effects, the output format, the goal
verbatim, the current state, and, for replans, the completed actions, the
remaining plan with action ids and the replan trigger as plain facts. Scene
differences enter only as data (object, region and lid names).

The replan user prompt is assembled from named sections
(:data:`REPLAN_SECTIONS`) so later phases can add sections, e.g. the Phase 5
corrective-block output format, without changing the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from llm_pipeline.failures import FailureCode, planner_facing_code
from llm_pipeline.pipeline_types import BaseContextBuilder, FailureEvent, ICLMode, PromptBundle, SceneState
from llm_pipeline.region_aliases import (
    PLANNER_HIDDEN_REGIONS,
    normalize_region_name,
    planner_action_text,
    planner_region_name,
)

PROMPT_VERSION = 'v2'

# Lids (articulated parts) and the regions they close off. Scene data, not advice.
LID_REGIONS: Dict[str, Tuple[str, ...]] = {
    'box_lid': ('inside_box',),
    'grill_lid': ('inside_grill',),
}
# Support surface on top of a lid, where it has one (scene data).
LID_TOP_REGIONS: Dict[str, str] = {
    'box_lid': 'box_lid_top',
}
LID_OBJECTS = frozenset(LID_REGIONS) | {'lid'}

ROLE_TEXT = (
    'You are the task planner for a robot arm. Given a goal and the current state of a scene, '
    'you output the ordered list of actions that achieves the goal.'
)

ACTION_DEFINITIONS: Dict[str, str] = {
    'pick': (
        'pick(o): grasp object o.\n'
        '  Preconditions: the gripper is empty; o is a listed object; o is not in a region closed off by a closed lid.\n'
        '  Effects: the gripper holds o.'
    ),
    'place': (
        'place(o, r): put the held object o into region r.\n'
        '  Preconditions: the gripper holds o; r is a listed region; r is not closed off by a closed lid.\n'
        '  Effects: o is in r; the gripper is empty.'
    ),
    'open': (
        'open(l): open lid l.\n'
        '  Preconditions: the gripper is empty; l is closed; no object is on the top surface of l.\n'
        '  Effects: l is open; the regions l closes off become reachable and their contents can become visible.'
    ),
    'close': (
        'close(l): close lid l.\n'
        '  Preconditions: the gripper is empty; l is open.\n'
        '  Effects: l is closed; the regions l closes off become unreachable and their contents are no longer visible.'
    ),
}

OUTPUT_FORMAT_TEXT = (
    'Output format:\n'
    'Reasoning is allowed. End your answer with a line containing only FINAL ACTIONS: '
    'followed by one action per line, in execution order, in this form:\n'
    'FINAL ACTIONS:\n'
    'pick(o)\n'
    'place(o, r)\n'
    'Use only the action names available in this scene and the object, lid and region names given in the state. '
    'Write nothing after the last action line. '
    'If the goal is already satisfied, write NO_ACTIONS as the only line after FINAL ACTIONS:.'
)

GOAL_CHECK_ROLE_TEXT = (
    'You check whether a robot has achieved a goal. You are given the goal, the current state of the scene '
    'and the actions the robot has completed.'
)
GOAL_CHECK_OUTPUT_TEXT = (
    'Output format: answer with exactly one line, either GOAL_COMPLETE or GOAL_INCOMPLETE: <short reason>.'
)


@dataclass(frozen=True)
class IdentifiedAction:
    action_id: str
    action: str

    def render(self) -> str:
        return f'{self.action_id}: {planner_action_text(self.action)}'


@dataclass
class ReplanContext:
    """Plain facts about the current plan for a replan prompt."""

    completed: List[IdentifiedAction] = field(default_factory=list)
    remaining: List[IdentifiedAction] = field(default_factory=list)


def system_prompt(actions: Sequence[str]) -> str:
    definitions = [ACTION_DEFINITIONS[name] for name in actions if name in ACTION_DEFINITIONS]
    return '\n\n'.join([
        ROLE_TEXT,
        'Actions available in this scene:\n' + '\n'.join(definitions),
        OUTPUT_FORMAT_TEXT,
    ])


def goal_check_system_prompt() -> str:
    return '\n\n'.join([GOAL_CHECK_ROLE_TEXT, GOAL_CHECK_OUTPUT_TEXT])


def _lid_states(state: SceneState, available_lids: Sequence[str]) -> Dict[str, bool]:
    lid_states = dict(getattr(state, 'lid_states', {}) or {})
    return {lid: lid_states[lid] for lid in available_lids if lid in lid_states}


def state_section(
    state: SceneState,
    regions: Sequence[str],
    lids: Sequence[str],
    remembered: Optional[Sequence[Tuple[str, Optional[str], int]]] = None,
) -> List[str]:
    """The current state: visible objects with regions, remembered objects, lids, gripper, regions."""
    object_region_map = dict(getattr(state, 'object_region_map', {}) or {})
    lines = ['## Current state', 'Visible objects and the region each one is in:']
    objects = [name for name in state.visible_objects if name not in LID_OBJECTS]
    if objects:
        for name in objects:
            region = object_region_map.get(name)
            lines.append(f'- {name}: {planner_region_name(region) if region else "unknown"}')
    else:
        lines.append('- (none)')
    if remembered is not None:
        lines.append('Remembered objects (not currently visible): last region, steps since last seen:')
        if remembered:
            for name, region, steps_ago in remembered:
                shown = planner_region_name(region) if region else 'unknown'
                lines.append(f'- {name}: {shown}, {steps_ago} step{"s" if steps_ago != 1 else ""} ago')
        else:
            lines.append('- (none)')
    lines.append('Lids:')
    lid_states = _lid_states(state, lids)
    if lid_states:
        for lid, is_open in lid_states.items():
            closes_off = ', '.join(planner_region_name(r) for r in LID_REGIONS.get(lid, ())) or '(none)'
            top = f'; top surface: {planner_region_name(LID_TOP_REGIONS[lid])}' if lid in LID_TOP_REGIONS else ''
            lines.append(f'- {lid}: {"open" if is_open else "closed"} (closes off {closes_off}{top})')
    else:
        lines.append('- (none)')
    holding = (getattr(state, 'gripper_state', {}) or {}).get('holding')
    lines.append(f'Gripper: {"holding " + holding if holding else "empty"}')
    lines.append('Regions: ' + (', '.join(regions) if regions else '(none)'))
    return lines


def trigger_facts(failure_event: FailureEvent, object_region_map: Dict[str, str], corrective: bool = False) -> List[str]:
    """Render the replan trigger as plain facts (no advice).

    A corrective replan lists its trigger objects with their labels in the same form for
    both trigger rules (IF and discovery), so the two modes differ only in which objects
    are listed."""
    code = planner_facing_code(failure_event.failure_id)
    evidence = dict(failure_event.evidence or {})
    action = planner_action_text(failure_event.action) if failure_event.action else failure_event.action
    if code == FailureCode.NEW_OBJECT_DISCOVERED and corrective and evidence.get('trigger_facts'):
        code = FailureCode.IF_RULE_TRIGGER
    if code == FailureCode.NEW_OBJECT_DISCOVERED:
        objects = list(evidence.get('newly_visible_objects') or [])
        rendered = ', '.join(
            f'{name} ({planner_region_name(object_region_map.get(name)) if object_region_map.get(name) else "unknown"})'
            for name in objects
        ) or '(none)'
        return [f'- After {action}, these objects became visible and had not been seen earlier in this trial: {rendered}.']
    if code == FailureCode.IF_RULE_TRIGGER:
        facts = list(evidence.get('trigger_facts') or [])
        after = f'After {action}, ' if action else ''
        return [f'- {after}these observed objects are not handled by the remaining plan:'] + [
            f'  - {fact}' for fact in facts
        ]
    if code == FailureCode.GOAL_NOT_SATISFIED:
        reason = evidence.get('reason') or ''
        return [f'- A goal check reported that the goal is not satisfied{": " + reason if reason else "."}']
    fact = evidence.get('fact')
    if failure_event.action is None:
        detail = f' {fact}' if fact else ''
        return [f'- The previous planner output was rejected before execution (failure code {code}).{detail}']
    return [f'- {action} failed (failure code {code}).' + (f' {fact}' if fact else '')]


REPLAN_SECTIONS = ('goal', 'state', 'completed_actions', 'remaining_plan', 'trigger')


class PromptV2Builder(BaseContextBuilder):
    """Builds prompt-v2 bundles (initial plan and replan) and goal-check prompts."""

    prompt_version = PROMPT_VERSION

    def __init__(self):
        self.env = None
        self.symbol_registry = None
        self.replan_context: Optional[ReplanContext] = None
        # memory.enabled: (object, last_region, steps since last seen) of remembered objects.
        self.memory_view: Optional[List[Tuple[str, Optional[str], int]]] = None
        # replan.output_mode = corrective: (trigger event, rejection of the previous blocks or None).
        self.corrective: Optional[Tuple[FailureEvent, Optional[FailureEvent]]] = None
        self.corrective_hints = False       # prompt.corrective_hints

    def set_env(self, env) -> None:
        self.env = env

    def set_symbol_registry(self, symbol_registry) -> None:
        self.symbol_registry = symbol_registry

    def stitch_frames(self, frames):
        """Same multi-camera composite image as the legacy prompts (images are perception, not prompt text)."""
        from llm_pipeline.geometric_builder import GeometricContextBuilder

        return GeometricContextBuilder().stitch_frames(frames)

    def set_replan_context(self, context: Optional[ReplanContext]) -> None:
        self.replan_context = context

    def set_corrective(self, trigger_event: Optional[FailureEvent], rejection: Optional[FailureEvent] = None,
                       hints: bool = False) -> None:
        self.corrective = None if trigger_event is None else (trigger_event, rejection)
        self.corrective_hints = bool(hints)

    def set_memory_view(self, remembered: Optional[Sequence[Tuple[str, Optional[str], int]]]) -> None:
        self.memory_view = None if remembered is None else list(remembered)

    # -- data -----------------------------------------------------------------
    def _actions(self) -> Tuple[str, ...]:
        return tuple(getattr(self.symbol_registry, 'actions', ()) or ('pick', 'place', 'open'))

    def _lids(self) -> Tuple[str, ...]:
        objects = set(getattr(self.symbol_registry, 'objects', ()) or ())
        return tuple(lid for lid in LID_REGIONS if lid in objects)

    def _regions(self, state: SceneState) -> List[str]:
        hidden = set(PLANNER_HIDDEN_REGIONS)
        ordered = []
        for region in state.valid_regions:
            name = normalize_region_name(region)
            if name and name not in hidden and planner_region_name(name) not in ordered:
                ordered.append(planner_region_name(name))
        return ordered

    # -- prompts --------------------------------------------------------------
    def system_prompt(self) -> str:
        if self.corrective is not None:
            from llm_pipeline.corrective import BLOCK_OUTPUT_FORMAT_TEXT

            definitions = [ACTION_DEFINITIONS[name] for name in self._actions() if name in ACTION_DEFINITIONS]
            return '\n\n'.join([ROLE_TEXT, 'Actions available in this scene:\n' + '\n'.join(definitions),
                                BLOCK_OUTPUT_FORMAT_TEXT])
        return system_prompt(self._actions())

    def user_sections(
        self,
        state: SceneState,
        goal_text: str,
        failure_event: Optional[FailureEvent],
    ) -> Dict[str, List[str]]:
        sections: Dict[str, List[str]] = {
            'goal': ['## Goal', goal_text],
            'state': state_section(state, self._regions(state), self._lids(), self.memory_view),
        }
        if failure_event is None:
            return sections
        context = self.replan_context or ReplanContext()
        sections['completed_actions'] = ['## Completed actions'] + (
            [f'- {item.render()}' for item in context.completed] or ['- (none)']
        )
        sections['remaining_plan'] = ['## Remaining plan (not executed yet)'] + (
            [f'- {item.render()}' for item in context.remaining] or ['- (none)']
        )
        object_region_map = dict(getattr(state, 'object_region_map', {}) or {})
        if self.corrective is not None:
            from llm_pipeline.corrective import corrective_instructions

            trigger_event, rejection = self.corrective
            sections['trigger'] = ['## Why a new plan is requested'] + trigger_facts(trigger_event, object_region_map,
                                                                                    corrective=True)
            if rejection is not None:
                fact = (rejection.evidence or {}).get('fact') or rejection.message
                sections['trigger'].append(
                    f'- Your previous blocks were rejected (failure code {planner_facing_code(rejection.failure_id)}): {fact}'
                )
            sections['what_to_plan'] = corrective_instructions(self.corrective_hints)
            return sections
        sections['trigger'] = ['## Why a new plan is requested'] + trigger_facts(failure_event, object_region_map)
        return sections

    def user_prompt(self, state: SceneState, goal_text: str, failure_event: Optional[FailureEvent]) -> str:
        sections = self.user_sections(state, goal_text, failure_event)
        order = REPLAN_SECTIONS + ('what_to_plan',) if failure_event is not None else ('goal', 'state')
        return '\n\n'.join('\n'.join(sections[name]) for name in order if name in sections)

    def build_bundle(
        self,
        state: SceneState,
        goal_text: str,
        failure_event: Optional[FailureEvent] = None,
        previous_actions: List[str] = None,
        icl_mode: str = ICLMode.ZERO_SHOT.value,
    ) -> PromptBundle:
        if icl_mode != ICLMode.ZERO_SHOT.value:
            raise ValueError(f'prompt.version=v2 has no in-context examples; icl_mode must be zero_shot, got {icl_mode}')
        return PromptBundle(
            goal_text=goal_text,
            system_prompt=self.system_prompt(),
            user_prompt=self.user_prompt(state, goal_text, failure_event),
            visible_objects=list(state.visible_objects),
            valid_regions=list(state.valid_regions),
            icl_mode=icl_mode,
            images=list(state.images) if state.images is not None else None,
            previous_actions=tuple(previous_actions) if previous_actions else (),
            failure_context=None,
            metadata={'held_object': state.gripper_state.get('holding'), 'prompt_version': PROMPT_VERSION},
        )

    def goal_check_prompts(self, state: SceneState, goal_text: str, completed_actions: Sequence[str]) -> Tuple[str, str]:
        lines = [
            '## Goal', goal_text, '',
            *state_section(state, self._regions(state), self._lids(), self.memory_view), '',
            '## Completed actions',
            *([f'- {planner_action_text(action)}' for action in completed_actions] or ['- (none)']),
        ]
        return goal_check_system_prompt(), '\n'.join(lines)


__all__ = [
    'ACTION_DEFINITIONS',
    'IdentifiedAction',
    'LID_REGIONS',
    'PROMPT_VERSION',
    'PromptV2Builder',
    'REPLAN_SECTIONS',
    'ReplanContext',
    'goal_check_system_prompt',
    'state_section',
    'system_prompt',
    'trigger_facts',
]
