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
        
        # 1. State to PDDL-style Text
        obs_lines = []
        obs_lines.append("## Robot State:")
        obs_lines.append(f"- gripper: {state.gripper_state.get('status', 'empty')}")
        if state.gripper_state.get('holding'):
            obs_lines.append(f"- holding: {state.gripper_state['holding']}")
        
        region_map = getattr(state, 'region_map', {}) # Fallback to state's pre-resolved map if available
        object_region_map = getattr(state, 'object_region_map', {}) or {}
        object_region_descriptions = getattr(state, 'object_region_descriptions', {}) or {}
        valid_regions = [
            region for region in state.valid_regions
            if normalize_region_name(region) not in set(PLANNER_HIDDEN_REGIONS)
        ]
        if valid_regions:
            obs_lines.append("\n## Valid Target Regions:")
            for region in valid_regions:
                meaning = region_semantics(region)
                if meaning:
                    obs_lines.append(f"- {region}: {meaning}")
                else:
                    obs_lines.append(f"- {region}")
        
        lid_objects = set(getattr(state, 'lid_states', {}).keys()) | {'box_lid', 'grill_lid', 'lid'}

        obs_lines.append("\n## Object States (Geometric):")
        for obj_name in state.visible_objects:
            # Lid objects are rendered separately as state, not geometric region
            if obj_name in lid_objects:
                continue
            pos = state.pose_map.get(obj_name)
            r_id = object_region_map.get(obj_name)
            r_desc = object_region_descriptions.get(obj_name)
            if pos:
                if not r_id:
                    r_id, r_desc = resolve_region(pos, region_map, state.valid_regions)
                obs_lines.append(f"- {obj_name}: region={r_id}, description={r_desc}, pose={tuple(np.round(pos, 3))}")
            elif r_id:
                obs_lines.append(f"- {obj_name}: region={r_id}, description={r_desc or '(none)'}, pose=unresolved")
            else:
                obs_lines.append(f"- {obj_name}: visible but pose unresolved")

        # Render lid states as OPEN/CLOSED instead of geometric regions
        lid_states = getattr(state, 'lid_states', {})
        if lid_states:
            obs_lines.append("\n## Lid State:")
            for lid_name, is_open in lid_states.items():
                obs_lines.append(f"- {lid_name}: {'OPEN' if is_open else 'CLOSED'}")
            blocked_regions = []
            box_lid_blockers = sorted(
                obj_name
                for obj_name, region_name in object_region_map.items()
                if normalize_region_name(region_name) == 'box_lid_top'
            )
            if lid_states.get('box_lid') is False:
                blocked_regions.append('inside_box is BLOCKED until open(box_lid) is completed')
                if box_lid_blockers:
                    blockers = ', '.join(box_lid_blockers)
                    blocked_regions.append(
                        f'box_lid is OBSTRUCTED by {blockers}; before open(box_lid), move '
                        f'{blockers} to table_target_area'
                    )
            if lid_states.get('grill_lid') is False:
                blocked_regions.append('inside_grill is BLOCKED until open(grill_lid) is completed')
            if blocked_regions:
                obs_lines.append("\n## Access Constraints:")
                for constraint in blocked_regions:
                    obs_lines.append(f"- {constraint}")
        
        # Use the pre-computed pddl_state if available
        if state.pddl_state:
            obs_lines.extend(state.pddl_state)
        else:
            obs_lines.append("(No symbolic state retrieved)")

        observation_text = "\n".join(obs_lines)

        # 3. Assemble Prompts
        system_prompt = self.system_prompt_template
        if not system_prompt:
            system_prompt = (PROMPTS_DIR / 'system_prompt.txt').read_text(encoding='utf-8').strip()

        if icl_mode == ICLMode.FEW_SHOT_SHARED_1.value:
            example = (PROMPTS_DIR / 'shared_exemplar.txt').read_text(encoding='utf-8').strip()
            system_prompt = f"{system_prompt}\n\nSHARED FEW-SHOT EXEMPLAR:\n{example}\n"
        
        user_prompt = ""
        if failure_event:
            user_prompt += "=== REPLANNING TRIGGERED ===\n"
            user_prompt += f"EVENT_ID: {failure_event.failure_id}\n"
            user_prompt += f"STAGE: {failure_event.stage.value}\n"
            if failure_event.failure_id == 'new_object_discovered':
                user_prompt += f"INTERRUPTED_AFTER_SUCCESSFUL_ACTION: {failure_event.action or '(none)'}\n"
            else:
                user_prompt += f"ACTION_FAILED: {failure_event.action or '(none)'}\n"
            user_prompt += f"ERROR/MESSAGE: {failure_event.message}\n"
            if previous_actions:
                user_prompt += f"COMPLETED_ACTIONS: {', '.join(previous_actions)}\n"
            user_prompt += "================================\n\n"
        
        user_prompt += f"### Current State\n{observation_text}\n\n### Goal\n{goal_text}"
        user_prompt += "\n\n" + "\n".join(self._build_action_contract_lines())

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
        lines = ['### Output Contract']
        lines.append('Choose the action order needed to satisfy the goal from the current state.')
        lines.append('Use only object names and target regions listed above.')
        lines.append('Respect Access Constraints: do not place into a blocked container region until its lid has been opened.')
        lines.append('You may include brief reasoning before the executable plan.')
        lines.append('End every response with a block headed exactly: FINAL ACTIONS:')
        lines.append('Inside FINAL ACTIONS, return one raw action per line with no numbering, prose, markdown, or commentary.')
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
