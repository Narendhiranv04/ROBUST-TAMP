"""Modular context builder using 3D geometric resolution and multi-view stitching."""

from __future__ import annotations
import os
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from llm_pipeline.pipeline_types import (
    BaseContextBuilder, SceneState, PromptBundle, FailureEvent, ICLMode
)
from llm_pipeline.executable_symbols import ACTION_SYMBOLS
from llm_pipeline.geometric_utils import resolve_region
from llm_pipeline.region_aliases import PLANNER_HIDDEN_REGIONS, normalize_region_name, region_semantics
from llm_pipeline.prompt_builder import PROMPTS_DIR


class GeometricContextBuilder(BaseContextBuilder):
    """
    Builds multimodal prompts using 3D geometric resolution.
    Ported logic from seg2/vlm_context_aggregator.py
    """

    def __init__(
        self,
        system_prompt_path: Optional[str] = None,
        user_prompt_path: Optional[str] = None,
        camera_names: List[str] = None,
        layout: str = "grid"
    ):
        self.system_prompt_template = self._load_template(system_prompt_path)
        self.user_prompt_template = self._load_template(user_prompt_path)
        self.camera_names = camera_names or ['left', 'right', 'overhead', 'wrist', 'front']
        self.layout = layout
        self.env = None
        self.symbol_registry = None

    def set_env(self, env) -> None:
        self.env = env

    def set_symbol_registry(self, symbol_registry: Any) -> None:
        self.symbol_registry = symbol_registry

    def _load_template(self, path: Optional[str]) -> Optional[str]:
        if path and os.path.exists(path):
            with open(path, 'r') as f:
                return f.read()
        return None

    def stitch_frames(self, frames: Dict[str, np.ndarray]) -> np.ndarray:
        """Stitch camera frames into a single composite image."""
        ordered_frames = [frames[name] for name in self.camera_names if name in frames]
        if not ordered_frames:
            return np.zeros((100, 100, 3), dtype=np.uint8)

        target_h, target_w = ordered_frames[0].shape[:2]
        resized = []
        for f in ordered_frames:
            if f.shape[:2] != (target_h, target_w):
                import cv2
                f = cv2.resize(f, (target_w, target_h))
            resized.append(f)

        if self.layout == "grid":
            # 2x3 grid
            while len(resized) < 6:
                resized.append(np.zeros_like(resized[0]))
            row1 = np.concatenate(resized[:3], axis=1)
            row2 = np.concatenate(resized[3:6], axis=1)
            return np.concatenate([row1, row2], axis=0)
        else:
            return np.concatenate(resized, axis=1)

    def build_bundle(
        self,
        state: SceneState,
        goal_text: str,
        failure_event: Optional[FailureEvent] = None,
        previous_actions: List[str] = None,
        icl_mode: str = ICLMode.ZERO_SHOT.value
    ) -> PromptBundle:
        region_map = getattr(state, 'region_map', {}) # Fallback to state's pre-resolved map if available
        object_region_map = getattr(state, 'object_region_map', {}) or {}
        object_region_descriptions = getattr(state, 'object_region_descriptions', {}) or {}
        valid_regions = [
            region for region in state.valid_regions
            if normalize_region_name(region) not in set(PLANNER_HIDDEN_REGIONS)
        ]

        snapshot = getattr(state, '_original_snapshot', None)
        newly_visible = list(getattr(snapshot, 'newly_visible_objects', []) or []) if failure_event else []

        checkpoint_lines = ['### Planning Checkpoint']
        checkpoint_lines.append(f"checkpoint_type: {'replanning' if failure_event else 'initial_planning'}")
        checkpoint_lines.append(f"frame_index: {state.frame_index}")
        checkpoint_lines.append(f"gripper: {state.gripper_state.get('status', 'empty')}")
        if state.gripper_state.get('holding'):
            checkpoint_lines.append(f"holding: {state.gripper_state['holding']}")
        checkpoint_lines.append(
            'visible_objects: ' + (', '.join(state.visible_objects) if state.visible_objects else '(none)')
        )
        checkpoint_lines.append(
            'newly_visible_objects: ' + (', '.join(newly_visible) if newly_visible else '(none)')
        )

        relational_lines = ['### Visible-Object Relational State']
        lid_objects = set(getattr(state, 'lid_states', {}).keys()) | {'box_lid', 'grill_lid', 'lid'}
        rendered_objects = [obj_name for obj_name in state.visible_objects if obj_name not in lid_objects]
        if not rendered_objects:
            relational_lines.append('- (none)')
        for obj_name in rendered_objects:
            pos = state.pose_map.get(obj_name)
            r_id = object_region_map.get(obj_name)
            r_desc = object_region_descriptions.get(obj_name)
            if pos and not r_id:
                r_id, r_desc = resolve_region(pos, region_map, state.valid_regions)
            r_id = r_id or 'unresolved'
            r_desc = r_desc or '(none)'
            relational_lines.append(f"- {obj_name}: region={r_id}, description={r_desc}")

        region_lines = ['### Valid Target Regions']
        if valid_regions:
            for region in valid_regions:
                meaning = self._region_meaning(region)
                if meaning:
                    region_lines.append(f"- {region}: {meaning}")
                else:
                    region_lines.append(f"- {region}")
        else:
            region_lines.append('- (none)')

        # Render lid states as OPEN/CLOSED instead of geometric regions
        lid_states = getattr(state, 'lid_states', {})
        articulation_lines = ['### Articulation State']
        access_lines = ['### Access Constraints']
        if lid_states:
            for lid_name, is_open in lid_states.items():
                articulation_lines.append(f"- {lid_name}: {'OPEN' if is_open else 'CLOSED'}")
            box_lid_blockers = sorted(
                obj_name
                for obj_name, region_name in object_region_map.items()
                if normalize_region_name(region_name) == 'box_lid_top'
            )
            if lid_states.get('box_lid') is False:
                access_lines.append('- inside_box is BLOCKED until open(box_lid) is completed')
                if box_lid_blockers:
                    blockers = ', '.join(box_lid_blockers)
                    access_lines.append(
                        f'- box_lid is OBSTRUCTED by {blockers}; before open(box_lid), move '
                        f'{blockers} to table_target_area'
                    )
            if lid_states.get('grill_lid') is False:
                access_lines.append('- inside_grill is BLOCKED until open(grill_lid) is completed')
        else:
            articulation_lines.append('- (none)')
        if len(access_lines) == 1:
            access_lines.append('- (none)')

        semantic_lines = ['### Domain Semantic State']
        if state.pddl_state:
            semantic_lines.extend(f"- {fact}" for fact in state.pddl_state)
        else:
            semantic_lines.append('- (none)')

        completed_lines = ['### Completed Actions']
        if previous_actions:
            completed_lines.extend(f"- {action}" for action in previous_actions)
        else:
            completed_lines.append('- (none)')

        replan_lines = []
        if failure_event:
            event_type = 'discovery' if failure_event.failure_id == 'new_object_discovered' else 'failure'
            event_stage = getattr(failure_event.stage, 'value', failure_event.stage)
            event_source = getattr(failure_event.source, 'value', failure_event.source)
            event_layer = getattr(failure_event.failure_layer, 'value', failure_event.failure_layer)
            replan_lines = [
                '### Replanning Event',
                f'event_type: {event_type}',
                f'event_id: {failure_event.failure_id}',
                f'event_stage: {event_stage}',
                f'event_source: {event_source}',
                f'event_layer: {event_layer}',
            ]
            if event_type == 'discovery':
                replan_lines.append(
                    f'interrupted_after_successful_action: {failure_event.action or "(none)"}'
                )
            else:
                replan_lines.append(f'failed_action: {failure_event.action or "(none)"}')
            replan_lines.append(f'event_message: {failure_event.message}')

        # 3. Assemble Prompts
        system_prompt = self.system_prompt_template
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / 'system_prompt.txt').read_text(encoding='utf-8').strip()

        if icl_mode == ICLMode.FEW_SHOT_SHARED_1.value:
            example = (PROMPTS_DIR / 'shared_exemplar.txt').read_text(encoding='utf-8').strip()
            system_prompt = f"{system_prompt}\n\nSHARED FEW-SHOT EXEMPLAR:\n{example}\n"

        user_sections = [
            checkpoint_lines,
            ['### Goal', goal_text],
            relational_lines,
            region_lines,
            articulation_lines,
            access_lines,
            semantic_lines,
            completed_lines,
        ]
        if replan_lines:
            user_sections.append(replan_lines)
        user_sections.append(self._build_action_contract_lines())
        user_prompt = '\n\n'.join('\n'.join(section) for section in user_sections)

        return PromptBundle(
            goal_text=goal_text,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            visible_objects=state.visible_objects,
            valid_regions=state.valid_regions,
            icl_mode=icl_mode,
            images=list(state.images) if state.images is not None else None,
            previous_actions=tuple(previous_actions) if previous_actions else (),
            failure_context=failure_event.message if failure_event else None,
            metadata={'held_object': state.gripper_state.get('holding')},
        )

    def _build_action_contract_lines(self) -> List[str]:
        actions = tuple(getattr(self.symbol_registry, 'actions', ()) or ACTION_SYMBOLS)
        lines = ['### Executable Interface']
        lines.append('Choose the task-level action order needed to satisfy the goal from the current checkpoint.')
        lines.append('Use only visible object names and target-region names listed above.')
        lines.append('Do not output move, grasp, trajectory, coordinate, PDDL, or implementation steps.')
        lines.append('Respect Access Constraints: do not place into a blocked container region until its lid has been opened.')
        if self.symbol_registry is not None and 'grill_lid' in getattr(self.symbol_registry, 'objects', ()):
            lines.append('For grill tasks, meat already reported inside_grill is considered cooked; raw meat outside the grill must be placed inside_grill, followed by close(grill_lid) and open(grill_lid), before serving.')
        lines.append('Prefer FINAL ACTIONS immediately; do not write step-by-step analysis or repeated alternatives.')
        lines.append('If a rationale is necessary, write at most two short lines before FINAL ACTIONS.')
        lines.append('End every response with a block headed exactly: FINAL ACTIONS:')
        lines.append('Inside FINAL ACTIONS, return one raw action per line with lowercase action names and no numbering, prose, markdown, or commentary.')
        lines.append('Do not include any text after the FINAL ACTIONS block.')
        lines.append('If the goal is already fully satisfied in the current state, put exactly NO_ACTIONS inside FINAL ACTIONS.')
        lines.append('')
        lines.append('### Actions')
        for action_name in actions:
            lines.append(self._action_description_line(action_name))
        return lines

    def _action_description_line(self, action_name: str) -> str:
        if action_name == 'pick':
            return '- pick(object): grasp a visible movable object.'
        if action_name == 'place':
            return '- place(object, region): put the held object on or in a listed target region.'
        if action_name == 'open':
            if self.symbol_registry is not None and 'grill_lid' in getattr(self.symbol_registry, 'objects', ()):
                return '- open(grill_lid): open the grill lid when access to the grill is needed.'
            if self.symbol_registry is not None and 'box_lid' in getattr(self.symbol_registry, 'objects', ()):
                return '- open(box_lid): open the box lid when access to the box is needed.'
            return '- open(object): open a visible openable object.'
        if action_name == 'close':
            if self.symbol_registry is not None and 'grill_lid' in getattr(self.symbol_registry, 'objects', ()):
                return '- close(grill_lid): close the grill lid when the goal requires it.'
            return '- close(object): close a visible closeable object.'
        return f'- {action_name}(...): use this action only when it directly advances the goal.'

    def _region_meaning(self, region: str) -> str:
        if (
            normalize_region_name(region) == 'table'
            and self.symbol_registry is not None
            and 'grill_lid' in getattr(self.symbol_registry, 'objects', ())
        ):
            return 'table surface for placing non-target objects that should be removed from the grill'
        return region_semantics(region)
