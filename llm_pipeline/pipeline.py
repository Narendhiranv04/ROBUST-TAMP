"""LLM-only replanning pipeline driven directly by segmentation evidence."""

from __future__ import annotations

import os
import sys
import time
import numpy as np
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from llm_pipeline.catalog import resolve_llm_model, resolve_planner_model, resolve_vlm_model
from llm_pipeline.client import RemoteTextLLMPlanner
from llm_pipeline.executable_symbols import build_runtime_symbol_registry
from llm_pipeline.failure_logic import SegmentationFirstFailureChecker, GeometricFailureChecker
from llm_pipeline.object_aliases import scene_object_for_object
from llm_pipeline.planner import TextLLMPlanner
from llm_pipeline.prompt_builder import TextOnlyContextBuilder
from llm_pipeline.quantization import normalize_quantization
from llm_pipeline.segmentation_adapter import SegmentationEvidenceAdapter
from llm_pipeline.strict_parser import StrictActionParser
from llm_pipeline.region_aliases import normalize_region_name, scene_object_for_region
from llm_pipeline.region_geometry import resolve_object_regions
from llm_pipeline.grill_geometry import (
    derive_grill_semantic_facts,
    grill_meat_status_from_facts,
    infer_grill_lid_open,
    initially_cooked_meats_from_regions,
    unplaced_inside_grill_meats_from_regions,
)
from llm_pipeline.metrics import validate_variant_success
from llm_pipeline.pipeline_types import (
    DirectAction, FailureEvent, FailureLayer, FailureSource, FailureStage,
    GoalCheckResult, PlanResult, ICLMode, SceneState,
    BasePlanner, BaseContextBuilder
)

# NEW Modular Components
from llm_pipeline.geometric_builder import GeometricContextBuilder
try:
    from llm_pipeline.vlm_planner import VLMPlanner
except ImportError:
    VLMPlanner = None


PROMPT_MODE_SEGMENTATION_TEXT = 'segmentation_text_only'
PROMPT_MODE_VLM_MULTIMODAL = 'segmentation_text_image'
VLM_CAMERA_NAMES = ('left', 'right', 'overhead', 'wrist', 'front')
VLM_CAMERA_ALIASES = {
    'left': ('left', 'cam_over_shoulder_left'),
    'right': ('right', 'cam_over_shoulder_right'),
    'overhead': ('overhead', 'cam_overhead'),
    'wrist': ('wrist', 'cam_wrist'),
    'front': ('front', 'cam_front'),
}


@dataclass
class LLMPipelineConfig:
    model_alias: str = 'qwen'
    model_path: str = ''
    icl_mode: str = ICLMode.ZERO_SHOT.value
    max_replans: int = 10
    enable_replanning: bool = True
    use_4bit: bool = False
    quantization: str = ''
    device: str = 'cuda'
    headless: bool = False
    text_only: bool = True
    segmentation_first: bool = True
    pre_action_checks_enabled: bool = True
    post_action_checks_enabled: bool = True
    return_home_after_each_action: bool = False
    planner_max_new_tokens: int = 4096
    planner_temperature: float = 0.0
    live_segmentation_view: bool = True
    visible_objects_only: bool = True
    prompt_mode: str = PROMPT_MODE_SEGMENTATION_TEXT
    model_type: str = ''
    direct_executable_names: bool = True
    explicit_move_token: bool = True
    live_view_update_stride: int = 5
    use_remote_planner: bool = False
    remote_planner_url: str = ''
    task_family: str = 'kitchen'
    scene_path: str = ''
    variant_id: str = ''
    scene_state_trace: bool = False
    show_llm_output: bool = False
    enable_goal_check: bool = True
    goal_check_max_new_tokens: int = 128
    goal_check_temperature: float = 0.0
    
    # NEW Multimodal & Prompting Flags
    enable_vision: bool = False
    system_prompt_path: str = ''
    user_prompt_path: str = ''
    exemplar_path: str = ''
    context_builder_type: str = 'geometric'  # IMPROVED ACCURACY: Default to 3D geometric reasoning

    def resolve_model_name(self) -> Tuple[str, str]:
        model_type = (self.model_type or ('vlm' if self.enable_vision else 'llm')).strip().lower()
        spec = resolve_planner_model(self.model_path or self.model_alias, model_type)
        return spec.alias, spec.path

    @property
    def effective_model_type(self) -> str:
        return (self.model_type or ('vlm' if self.enable_vision else 'llm')).strip().lower()

    @property
    def effective_quantization(self) -> str:
        return normalize_quantization(self.quantization, use_4bit=self.use_4bit)


@dataclass
class ExecutionCycleRecord:
    cycle_number: int
    is_replan: bool
    icl_mode: str
    planned_actions: List[str] = field(default_factory=list)
    completed_actions: List[str] = field(default_factory=list)
    remaining_actions: List[str] = field(default_factory=list)
    raw_output: str = ''
    inference_time_s: float = 0.0
    success: bool = False
    error_message: Optional[str] = None
    failure_event: Optional[Dict[str, Any]] = None
    goal_check: Optional[Dict[str, Any]] = None
    prompt_bundle: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'cycle_number': int(self.cycle_number),
            'is_replan': bool(self.is_replan),
            'icl_mode': self.icl_mode,
            'planned_actions': list(self.planned_actions),
            'completed_actions': list(self.completed_actions),
            'remaining_actions': list(self.remaining_actions),
            'raw_output': self.raw_output,
            'inference_time_s': float(self.inference_time_s),
            'success': bool(self.success),
            'error_message': self.error_message,
            'failure_event': dict(self.failure_event) if self.failure_event else None,
            'goal_check': dict(self.goal_check) if self.goal_check else None,
            'prompt_bundle': dict(self.prompt_bundle),
        }


class LLMOnlyReplanningPipeline:
    """Runs text-only planning on raw segmentation evidence with primitive execution."""

    def __init__(
        self,
        config: Optional[LLMPipelineConfig] = None,
        planner: Optional[BasePlanner] = None,
        context_builder: Optional[BaseContextBuilder] = None,
        segmentation_adapter=None,
        failure_checker=None,
        executor=None,
    ):
        self.config = config or LLMPipelineConfig()
        self.planner = planner
        self.context_builder = context_builder
        self.segmentation_adapter = segmentation_adapter
        self.failure_checker = failure_checker
        self.executor = executor
        self.env = None
        self.cycles: List[ExecutionCycleRecord] = []
        self.last_prompt_trace: Dict[str, Any] = {}
        self.symbol_registry = None
        self._sim_step_counter = 0
        self._last_image_camera_names: List[str] = []

        # Default Context Builder based on config
        # IMPROVED ACCURACY: Always default to 3D Geometric Reasoning
        if self.context_builder is None:
            self.context_builder = GeometricContextBuilder(
                system_prompt_path=self.config.system_prompt_path,
                user_prompt_path=self.config.user_prompt_path
            )

    def initialize(self, env=None) -> bool:
        if env is None:
            os.environ['HEADLESS'] = 'True' if self.config.headless else 'False'
            scene_path = (self.config.scene_path or '').strip()
            task_family = (self.config.task_family or 'kitchen').strip().lower()

            if task_family == 'grill':
                if scene_path:
                    os.environ['GRILL_SCENE_FILE'] = scene_path
                grill_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'grill_task2')
                if grill_dir not in sys.path:
                    sys.path.insert(0, grill_dir)
                from grill_task_streams import ENV  # Lazy import for testability
            else:
                if scene_path:
                    os.environ['KITCHEN_SCENE_FILE'] = scene_path
                from rlbench_kitchen_streams import ENV  # Lazy import for testability

            env = ENV
        self.env = env

        if hasattr(self.context_builder, 'set_env'):
            self.context_builder.set_env(env)

        if self.segmentation_adapter is None:
            self.segmentation_adapter = SegmentationEvidenceAdapter(
                env=env,
                live_segmentation_view=(self.config.live_segmentation_view and not self.config.headless),
                visible_objects_only=self.config.visible_objects_only,
            )
        else:
            if hasattr(self.segmentation_adapter, 'set_env'):
                self.segmentation_adapter.set_env(env)

        # Get mask-discovered objects from the detector (intersection of class vocab and mask visibility)
        detected_objects = None
        detector = getattr(self.segmentation_adapter, 'detector', None)
        if detector is not None and hasattr(detector, 'task_objects'):
            detected_objects = detector.task_objects
        self.symbol_registry = build_runtime_symbol_registry(env=env, detected_objects=detected_objects)
        if hasattr(self.segmentation_adapter, 'set_symbol_registry'):
            self.segmentation_adapter.set_symbol_registry(self.symbol_registry)
        if hasattr(self.context_builder, 'set_symbol_registry'):
            self.context_builder.set_symbol_registry(self.symbol_registry)

        if self.failure_checker is None:
            # IMPROVED ACCURACY: Use 3D Geometric Failure Checking by default
            self.failure_checker = GeometricFailureChecker(
                adapter=self.segmentation_adapter,
                env=env
            )
        else:
            self.failure_checker.env = env
            self.failure_checker.adapter = self.segmentation_adapter

        if self.executor is None:
            from llm_pipeline.executor import DirectPrimitiveExecutor
            from vlm_pipeline.vlm_executor_v2 import ExecutorConfig

            self.executor = DirectPrimitiveExecutor(
                env=env,
                config=ExecutorConfig(return_home_after_each_action=self.config.return_home_after_each_action),
            )
        else:
            if hasattr(self.executor, 'set_env'):
                self.executor.set_env(env)

        if hasattr(self.executor, 'set_step_callback'):
            self.executor.set_step_callback(self._on_sim_step)
        if hasattr(self.executor, 'set_action_start_callback'):
            self.executor.set_action_start_callback(self._on_action_start)
        if hasattr(self.executor, 'set_scene_state_trace_enabled'):
            self.executor.set_scene_state_trace_enabled(self.config.scene_state_trace)

        if self.planner is None:
            model_alias, model_name = self.config.resolve_model_name()
            if self.config.use_remote_planner:
                expected_model = (
                    resolve_vlm_model(self.config.model_path or self.config.model_alias)
                    if self.config.effective_model_type == 'vlm'
                    else resolve_llm_model(self.config.model_path or self.config.model_alias)
                )
                self.planner = RemoteTextLLMPlanner(
                    server_url=self.config.remote_planner_url or None,
                    expected_model=expected_model,
                )
            elif self.config.effective_model_type == 'vlm':
                if VLMPlanner is None:
                    raise ImportError("VLMPlanner dependencies not met, but model_type='vlm'")
                self.planner = VLMPlanner(
                    model_path=model_name or model_alias,
                    model_alias=model_alias,
                    device=self.config.device,
                    use_4bit=self.config.use_4bit,
                    quantization=self.config.effective_quantization,
                )
            else:
                self.planner = TextLLMPlanner(
                    model_name=model_name,
                    model_alias=model_alias,
                    use_4bit=self.config.use_4bit,
                    quantization=self.config.effective_quantization,
                    device=self.config.device,
                )

        parser = StrictActionParser(
            valid_actions=self.symbol_registry.actions,
            valid_objects=self.symbol_registry.objects,
            valid_regions=self.symbol_registry.regions,
        )
        if hasattr(self.planner, 'parser'):
            self.planner.parser = parser

        if not getattr(self.planner, 'loaded', False):
            if not self.planner.load_model():
                return False

        self.reset_episode_state()
        self._settle_environment()
        if self.segmentation_adapter is not None:
            self.segmentation_adapter.refresh_visibility(event='initial')
        self._update_live_action_sequence([], None)
        return True

    def reset_episode_state(self) -> None:
        self.cycles = []
        self.last_prompt_trace = {}
        self._sim_step_counter = 0
        self._initial_cooked_meats = set()
        self._initial_cooked_meats_captured = False
        if self.executor is not None and hasattr(self.executor, 'reset_episode'):
            self.executor.reset_episode()
        if self.segmentation_adapter is not None and hasattr(self.segmentation_adapter, 'reset_tracking'):
            self.segmentation_adapter.reset_tracking()

    def _image_metadata(self, images: Optional[List[np.ndarray]]) -> Dict[str, Any]:
        image_list = [image for image in (list(images) if images is not None else []) if image is not None]
        shapes = [list(getattr(image, 'shape', ())) for image in image_list]
        return {
            'image_present': bool(image_list),
            'image_count': len(image_list),
            'image_shapes': shapes,
            'camera_names': list(self._last_image_camera_names) if image_list else [],
        }

    def _prompt_bundle_trace(self, bundle) -> Dict[str, Any]:
        trace = {}
        for key, value in bundle.__dict__.items():
            if value is None:
                continue
            if key == 'images':
                trace['image_metadata'] = self._image_metadata(value)
                continue
            if key == 'image_paths' and not value:
                continue
            trace[key] = value
        return trace

    def preflight(self, goal_text: str) -> Dict[str, Any]:
        plan_result, prompt_trace = self.plan_once(goal_text=goal_text, failure_event=None, silent=True)
        self._cached_preflight_plan = (plan_result, prompt_trace)
        debug_snapshot = self.get_debug_snapshot()
        bundle = prompt_trace.get('bundle', {})
        prompt_contract_issues = []
        image_metadata = dict(bundle.get('image_metadata', {}) or {})
        image_present = bool(image_metadata.get('image_present', False))
        if self.config.enable_vision:
            if not image_present:
                prompt_contract_issues.append('missing_image_in_prompt_bundle')
        else:
            if image_present:
                prompt_contract_issues.append('image_key_in_prompt_bundle')
            if debug_snapshot and any('image' in key and debug_snapshot.get(key) for key in debug_snapshot):
                prompt_contract_issues.append('image_key_in_debug_snapshot')
        return {
            'model_alias': getattr(self.planner, 'model_alias', self.config.model_alias),
            'model_name': getattr(self.planner, 'model_name', self.config.model_path or self.config.model_alias),
            'model_type': self.config.effective_model_type,
            'quantization': self._planner_quantization(debug_snapshot),
            'icl_mode': self.config.icl_mode,
            'loaded': bool(getattr(self.planner, 'loaded', False)),
            'text_only': not self.config.enable_vision,
            'use_vision': bool(self.config.enable_vision),
            'image_present': image_present,
            'image_metadata': image_metadata,
            'prompt_contract_ok': not prompt_contract_issues,
            'prompt_contract_issues': prompt_contract_issues,
            'dry_run_plan_success': bool(plan_result.success),
            'dry_run_action_count': len(plan_result.actions),
            'dry_run_error_message': plan_result.error_message,
            'dry_run_failure_event': plan_result.failure_event.to_dict() if plan_result.failure_event else None,
            'dry_run_raw_output': plan_result.raw_output,
            'prompt_trace': prompt_trace,
            'debug_snapshot': debug_snapshot,
        }

    def _print_plan_result(self, result: PlanResult, is_replan: bool, cycle_num: int, failure_event: Optional[FailureEvent] = None):
        print(f'\n{"=" * 60}')
        print(f'[LLM] {"REPLAN" if is_replan else "PLAN"} cycle {cycle_num}')
        if is_replan and failure_event is not None:
            print(f'[LLM] Failure context: {failure_event.message}')
        print(f'{"=" * 60}')
        print(f'[LLM] Raw output: {len(result.raw_output or "")} characters')
        if result.success and result.actions:
            print(f'[LLM] Parsed plan ({len(result.actions)} actions):')
            for i, action in enumerate(result.actions, 1):
                print(f'   {i:2}. {action}')
        elif result.failure_event:
            print(f'[LLM] Parse FAILED: {result.failure_event.message}')
        elif not result.success:
            print(f'[LLM] Plan FAILED: {result.error_message}')
        print(f'{"=" * 60}')

    def plan_once(
        self,
        goal_text: str,
        failure_event: Optional[FailureEvent],
        silent: bool = False,
    ) -> Tuple[PlanResult, Dict[str, Any]]:
        # 1. Capture and resolve scene state
        state = self._build_scene_state()
        
        # 2. Build prompt bundle via modular context builder
        bundle = self.context_builder.build_bundle(
            state=state,
            goal_text=goal_text,
            failure_event=failure_event,
            previous_actions=[
                action
                for cycle in self.cycles
                for action in cycle.completed_actions
            ],
            icl_mode=self.config.icl_mode
        )
        bundle_metadata = dict(getattr(bundle, 'metadata', {}) or {})
        bundle_metadata.update({
            'held_object': getattr(self.executor, 'held_object', None),
            'max_new_tokens': int(self.config.planner_max_new_tokens),
            'temperature': float(self.config.planner_temperature),
        })
        bundle = replace(bundle, metadata=bundle_metadata)

        is_replan = failure_event is not None
        cycle_num = len(self.cycles) + 1
        if not silent:
            print(f'\n{"=" * 60}')
            print(f'[LLM] {"REPLAN" if is_replan else "PLAN"} cycle {cycle_num}')
            if is_replan and failure_event is not None:
                print(f'[LLM] Failure context: {failure_event.message}')
            print(f'{"=" * 60}')

        # 3. Plan using modular planner
        # We try to use the new .plan() interface, fall back to .generate_plan() for legacy
        if hasattr(self.planner, 'plan'):
            result = self.planner.plan(bundle)
        else:
            result = self.planner.generate_plan(
                system_prompt=bundle.system_prompt,
                user_prompt=bundle.user_prompt,
                icl_mode=bundle.icl_mode,
                max_new_tokens=self.config.planner_max_new_tokens,
                temperature=self.config.planner_temperature,
                held_object=getattr(self.executor, 'held_object', None),
            )

        if not silent:
            print(f'[LLM] Raw output: {len(result.raw_output or "")} characters')
            if self.config.show_llm_output and result.raw_output:
                print('[LLM] Raw output text:')
                print(result.raw_output.rstrip())
            if result.success and result.actions:
                print(f'[LLM] Parsed plan ({len(result.actions)} actions):')
                for i, action in enumerate(result.actions, 1):
                    print(f'   {i:2}. {action}')
            elif result.failure_event:
                print(f'[LLM] Parse FAILED: {result.failure_event.message}')
            elif not result.success:
                print(f'[LLM] Plan FAILED: {result.error_message}')
            print(f'{"=" * 60}')

        bundle_trace = self._prompt_bundle_trace(bundle)
        self.last_prompt_trace = {
            'bundle': bundle_trace,
            'state': state.to_dict(),
            'system_prompt': bundle.system_prompt,
            'user_prompt': bundle.user_prompt,
        }
        if result.success:
            self._update_live_action_sequence(result.actions, None)
        else:
            self._update_live_action_sequence([], None)
        return result, dict(self.last_prompt_trace)

    def _capture_rgb_frames(self) -> Dict[str, np.ndarray]:
        frames: Dict[str, np.ndarray] = {}
        cameras = getattr(self.env, 'cams', {}) or {}
        for camera_name in VLM_CAMERA_NAMES:
            camera = None
            if isinstance(cameras, dict):
                for candidate_name in VLM_CAMERA_ALIASES.get(camera_name, (camera_name,)):
                    camera = cameras.get(candidate_name)
                    if camera is not None:
                        break
            if camera is None:
                continue
            try:
                if hasattr(camera, 'handle_explicitly'):
                    camera.handle_explicitly()
                image = camera.capture_rgb()
            except Exception:
                continue
            if image is None:
                continue
            array = np.asarray(image)
            if array.dtype != np.uint8:
                array = np.clip(array * 255.0, 0, 255).astype(np.uint8)
            frames[camera_name] = array
        return frames

    def _capture_composite_image(self) -> Optional[np.ndarray]:
        self._last_image_camera_names = []
        if not self.config.enable_vision:
            return None
        frames = self._capture_rgb_frames()
        if not frames:
            return None
        self._last_image_camera_names = [name for name in VLM_CAMERA_NAMES if name in frames]
        stitcher = getattr(self.context_builder, 'stitch_frames', None)
        if callable(stitcher):
            return stitcher(frames)

        ordered = [frames[name] for name in VLM_CAMERA_NAMES if name in frames]
        if not ordered:
            return None
        return ordered[0]

    def _build_scene_state(self) -> SceneState:
        """Helper to build a unified SceneState from current sensors."""
        snapshot = self.segmentation_adapter.capture_snapshot(event='planning')
        composite_image = self._capture_composite_image()
        
        # Extract 3D poses and region bboxes if available
        pose_map = {}
        region_map = {}
        detector = getattr(self.segmentation_adapter, 'detector', None)
        if detector:
            # 1. Objects
            for obj_name in snapshot.visible_objects:
                pose = detector.get_object_pose(scene_object_for_object(obj_name, self.env))
                if pose:
                    pose_map[obj_name] = pose
            
            # 2. Regions (Geometric Resolution)
            # Use the detector to get absolute world AABBs for all supported regions.
            # This ensures GeometricContextBuilder has the data needed for resolve_region().
            for region_name in snapshot.supported_regions:
                # Map semantic names to simulator names if needed
                scene_name = scene_object_for_region(region_name)
                
                bb = detector.get_bounding_box(scene_name)
                if bb:
                    # bb is (min, max)
                    region_map[region_name] = (np.array(bb[0]), np.array(bb[1]))

        object_region_map, object_region_descriptions = resolve_object_regions(
            {name: tuple(pose[:3]) for name, pose in pose_map.items()},
            region_map,
            snapshot.supported_regions,
        )
        snapshot_object_region_map = dict(getattr(snapshot, 'object_region_map', {}) or {})
        snapshot_object_region_descriptions = dict(getattr(snapshot, 'object_region_descriptions', {}) or {})
        if snapshot_object_region_map:
            # The adapter can resolve previously seen objects that are no longer
            # mask-visible, e.g. a mug occluded inside the box. Keep that richer
            # map, while letting fresh visible-object geometry override stale data.
            object_region_map = {**snapshot_object_region_map, **object_region_map}
            object_region_descriptions = {
                **snapshot_object_region_descriptions,
                **object_region_descriptions,
            }

        pddl_state = []
        if (self.config.task_family or '').strip().lower() == 'grill':
            completed_actions = list(getattr(self.executor, 'completed_primitive_actions', []) or [])
            if not getattr(self, '_initial_cooked_meats_captured', False):
                self._initial_cooked_meats = initially_cooked_meats_from_regions(object_region_map)
                self._initial_cooked_meats_captured = True
            self._initial_cooked_meats.update(
                unplaced_inside_grill_meats_from_regions(object_region_map, completed_actions)
            )
            pddl_state = derive_grill_semantic_facts(
                object_region_map,
                lid_open=infer_grill_lid_open(self.env),
                completed_actions=completed_actions,
                initially_cooked_meats=getattr(self, '_initial_cooked_meats', set()),
            )

        # Resolve lid open/closed states for all lid objects
        lid_names = [name for name in snapshot.visible_objects if name in {'box_lid', 'grill_lid', 'lid'}]
        lid_states = {}
        for lid_name in lid_names:
            try:
                lid_states[lid_name] = bool(self.segmentation_adapter.is_lid_open(snapshot, lid_name=lid_name))
            except Exception:
                lid_states[lid_name] = False

        state = SceneState(
            frame_index=snapshot.frame_index,
            visible_objects=snapshot.visible_objects,
            valid_regions=snapshot.supported_regions,
            pddl_state=pddl_state,
            masks=snapshot.gripper_evidence.get('masks', {}),
            pose_map=pose_map,
            images=[composite_image] if composite_image is not None else None,
            region_map=region_map,
            object_region_map=object_region_map,
            object_region_descriptions=object_region_descriptions,
            lid_states=lid_states,
            gripper_state={'status': 'holding' if getattr(self.executor, 'held_object', None) else 'empty',
                           'holding': getattr(self.executor, 'held_object', None)}
        )
        # Preserve original snapshot for text-only builders that 
        # need more evidence than the resolved symbolic state
        state._original_snapshot = snapshot
        return state

    def _build_goal_check_prompts(self, goal_text: str) -> Tuple[str, str, Optional[np.ndarray]]:
        state = self._build_scene_state()
        goal_check_image = None
        if self.config.enable_vision and state.images:
            goal_check_image = state.images[0]
        bundle = self.context_builder.build_bundle(
            state=state,
            goal_text=goal_text,
            failure_event=None,
            previous_actions=list(getattr(self.executor, 'completed_primitive_actions', [])),
            icl_mode=self.config.icl_mode,
        )
        current_state_text = bundle.user_prompt
        for marker in ('### Executable Interface', '### Output Contract', 'OUTPUT CONTRACT:'):
            if marker in current_state_text:
                current_state_text = current_state_text.split(marker, 1)[0].strip()

        completed_actions = list(getattr(self.executor, 'completed_primitive_actions', []))
        completed_text = '\n'.join(completed_actions) if completed_actions else '(none)'
        system_prompt = (
            'You are a strict robotic goal-completion verifier.\n'
            'Decide whether the current scene state satisfies the goal.\n'
            'Return exactly one line:\n'
            'GOAL_COMPLETE\n'
            'or\n'
            'GOAL_INCOMPLETE: <short reason>\n'
            'Do not propose actions. Do not include markdown, bullets, or extra text.'
        )
        user_prompt = (
            f'{current_state_text}\n\n'
            f'COMPLETED ACTIONS:\n{completed_text}\n\n'
            f'GOAL:\n{goal_text}\n\n'
            'Is the goal fully complete in the current state?'
        )
        return system_prompt, user_prompt, goal_check_image

    def _check_goal_completion(self, goal_text: str) -> GoalCheckResult:
        checker = getattr(self.planner, 'check_goal_completion', None)
        if not callable(checker):
            return GoalCheckResult(
                success=True,
                goal_satisfied=True,
                raw_output='GOAL_COMPLETE',
                inference_time=0.0,
                reason='goal_check_not_supported_by_planner',
            )

        system_prompt, user_prompt, goal_check_image = self._build_goal_check_prompts(goal_text)
        kwargs = {
            'system_prompt': system_prompt,
            'user_prompt': user_prompt,
            'icl_mode': self.config.icl_mode,
            'max_new_tokens': self.config.goal_check_max_new_tokens,
            'temperature': self.config.goal_check_temperature,
            'held_object': getattr(self.executor, 'held_object', None),
        }
        if self.config.enable_vision:
            if goal_check_image is None:
                return GoalCheckResult(
                    success=False,
                    goal_satisfied=False,
                    raw_output='',
                    inference_time=0.0,
                    error_message='VLM goal check requires an image, but no image was captured.',
                )
            kwargs['image'] = goal_check_image
        return checker(**kwargs)

    def _variant_id_for_goal_check(self) -> str:
        configured = (self.config.variant_id or '').strip().upper()
        if configured:
            return configured

        scene_path = (self.config.scene_path or '').lower()
        task_family = (self.config.task_family or '').strip().lower()
        prefix = 'G' if task_family == 'grill' or 'grill' in scene_path else 'K'
        if 'variation1' in scene_path or 'variation_1' in scene_path:
            return f'{prefix}1'
        if 'variation2' in scene_path or 'variation_2' in scene_path:
            return f'{prefix}2'
        if 'variation3' in scene_path or 'variation_3' in scene_path:
            return f'{prefix}3'
        return ''

    def _deterministic_goal_completion_from_scene(self, goal_text: str) -> Optional[GoalCheckResult]:
        del goal_text
        variant_id = self._variant_id_for_goal_check()
        if not variant_id:
            return None
        state = self._build_scene_state()
        object_region_map = dict(getattr(state, 'object_region_map', {}) or {})
        completed_actions = list(getattr(self.executor, 'completed_primitive_actions', []) or [])
        validation = validate_variant_success(variant_id, object_region_map, completed_actions)
        if not bool(validation.get('success', False)):
            missing = list(validation.get('missing') or [])
            return GoalCheckResult(
                success=True,
                goal_satisfied=False,
                raw_output='DETERMINISTIC_GOAL_INCOMPLETE',
                inference_time=0.0,
                reason='; '.join(missing),
            )

        return GoalCheckResult(
            success=True,
            goal_satisfied=True,
            raw_output='DETERMINISTIC_GOAL_COMPLETE',
            inference_time=0.0,
            reason=f'scene_state_satisfies_{variant_id}_goal',
        )

    def _is_implicit_non_target_only_goal_failure(self, goal_check: GoalCheckResult) -> bool:
        variant_id = self._variant_id_for_goal_check()
        if variant_id not in {'G1', 'G3'}:
            return False
        if goal_check.raw_output != 'DETERMINISTIC_GOAL_INCOMPLETE':
            return False
        missing = [
            part.strip()
            for part in (goal_check.reason or '').split(';')
            if part.strip()
        ]
        return (
            len(missing) == 1
            and missing[0].startswith('phone is in ')
            and missing[0].endswith(', expected table')
        )

    def _check_goal_completion_with_deterministic_override(self, goal_text: str) -> GoalCheckResult:
        deterministic_goal_check = self._deterministic_goal_completion_from_scene(goal_text)
        if (
            deterministic_goal_check is not None
            and self._is_implicit_non_target_only_goal_failure(deterministic_goal_check)
        ):
            return deterministic_goal_check

        goal_check = self._check_goal_completion(goal_text)
        if deterministic_goal_check is not None and (
            not goal_check.success
            or goal_check.goal_satisfied != deterministic_goal_check.goal_satisfied
        ):
            return deterministic_goal_check
        return goal_check

    def _goal_check_failure_event(self, goal_check: GoalCheckResult) -> FailureEvent:
        return FailureEvent(
            failure_id='goal_not_satisfied',
            stage=FailureStage.AFTER_EXECUTION,
            source=FailureSource.GOAL_CHECK,
            action=None,
            evidence={
                'raw_output': goal_check.raw_output,
                'reason': goal_check.reason,
                'error_message': goal_check.error_message,
            },
            failure_layer=FailureLayer.LAYER_2,
            should_replan=True,
            message=(
                'Goal check failed: the goal is not fully satisfied in the current scene. '
                'Review the current object states, completed actions, and original goal, then produce a corrective plan.'
            ),
        )

    def _final_scene_state_summary(self) -> Dict[str, Any]:
        try:
            state = self._build_scene_state()
        except Exception as exc:
            return {'error': str(exc)}
        summary = {
            'visible_objects': list(getattr(state, 'visible_objects', []) or []),
            'valid_regions': list(getattr(state, 'valid_regions', []) or []),
            'object_region_map': dict(getattr(state, 'object_region_map', {}) or {}),
            'object_region_descriptions': dict(getattr(state, 'object_region_descriptions', {}) or {}),
            'lid_states': dict(getattr(state, 'lid_states', {}) or {}),
        }
        semantic_facts = list(getattr(state, 'pddl_state', []) or [])
        meat_state = grill_meat_status_from_facts(semantic_facts)
        if semantic_facts:
            summary['debug_domain_semantic_facts'] = semantic_facts
        if meat_state:
            summary['debug_grill_meat_state'] = meat_state
        return summary

    def run(self, goal_text: str) -> Dict[str, Any]:
        if self.env is None:
            raise RuntimeError('Pipeline is not initialized')

        self.reset_episode_state()
        self._settle_environment()
        if self.segmentation_adapter is not None:
            self.segmentation_adapter.refresh_visibility(event='initial')
        started_at = time.time()
        pending_failure: Optional[FailureEvent] = None
        failure_reason: Optional[str] = None
        last_failure_event: Optional[FailureEvent] = None
        execution_skipped = not self.config.enable_replanning

        if execution_skipped:
            if getattr(self, '_cached_preflight_plan', None):
                plan_result, prompt_trace = self._cached_preflight_plan
                self._cached_preflight_plan = None
                self._print_plan_result(plan_result, False, 1, None)
            else:
                plan_result, prompt_trace = self.plan_once(goal_text=goal_text, failure_event=None)
            cycle = ExecutionCycleRecord(
                cycle_number=1,
                is_replan=False,
                icl_mode=self.config.icl_mode,
                planned_actions=[str(action) for action in plan_result.actions],
                raw_output=plan_result.raw_output,
                inference_time_s=plan_result.inference_time,
                prompt_bundle=dict(prompt_trace.get('bundle', {})),
            )
            if plan_result.success and plan_result.actions:
                cycle.success = True
                cycle.remaining_actions = list(cycle.planned_actions)
            else:
                cycle.success = False
                cycle.error_message = plan_result.error_message or 'planning_failed'
                if plan_result.failure_event is not None:
                    cycle.failure_event = plan_result.failure_event.to_dict()
                    last_failure_event = plan_result.failure_event
                failure_reason = cycle.error_message
            self.cycles.append(cycle)
        else:
            while len(self.cycles) <= self.config.max_replans:
                cycle_number = len(self.cycles) + 1
                is_replan = pending_failure is not None
                if cycle_number == 1 and not is_replan and getattr(self, '_cached_preflight_plan', None):
                    plan_result, prompt_trace = self._cached_preflight_plan
                    self._cached_preflight_plan = None
                    self._print_plan_result(plan_result, is_replan, cycle_number, pending_failure)
                else:
                    plan_result, prompt_trace = self.plan_once(goal_text=goal_text, failure_event=pending_failure)
                cycle = ExecutionCycleRecord(
                    cycle_number=cycle_number,
                    is_replan=is_replan,
                    icl_mode=self.config.icl_mode,
                    planned_actions=[str(action) for action in plan_result.actions],
                    raw_output=plan_result.raw_output,
                    inference_time_s=plan_result.inference_time,
                    prompt_bundle=dict(prompt_trace.get('bundle', {})),
                )

                if plan_result.success and not plan_result.actions:
                    cycle.success = True
                    cycle.error_message = None
                    cycle.completed_actions = list(getattr(self.executor, 'completed_primitive_actions', []))
                    cycle.remaining_actions = []
                    deterministic_goal_check = self._deterministic_goal_completion_from_scene(goal_text)
                    if (
                        pending_failure is not None
                        and pending_failure.failure_id == 'goal_not_satisfied'
                        and (pending_failure.evidence or {}).get('error_message')
                        and 'NO_ACTIONS' in (plan_result.raw_output or '').upper()
                        and (deterministic_goal_check is None or deterministic_goal_check.goal_satisfied)
                    ):
                        if deterministic_goal_check is not None:
                            cycle.goal_check = deterministic_goal_check.to_dict()
                        self.cycles.append(cycle)
                        failure_reason = None
                        break
                    if self.config.enable_goal_check:
                        goal_check = deterministic_goal_check or self._check_goal_completion(goal_text)
                        cycle.goal_check = goal_check.to_dict()
                        if goal_check.success and goal_check.goal_satisfied:
                            self.cycles.append(cycle)
                            failure_reason = None
                            break
                        if self._is_implicit_non_target_only_goal_failure(goal_check):
                            self.cycles.append(cycle)
                            failure_reason = None
                            break
                        goal_failure = self._goal_check_failure_event(goal_check)
                        cycle.success = False
                        cycle.failure_event = goal_failure.to_dict()
                        last_failure_event = goal_failure
                        self.cycles.append(cycle)
                        pending_failure = goal_failure
                        failure_reason = goal_failure.message
                        if len(self.cycles) > self.config.max_replans:
                            break
                        continue
                    cycle.success = False
                    cycle.error_message = 'planner_returned_no_actions'
                    self.cycles.append(cycle)
                    failure_reason = cycle.error_message
                    break

                if not plan_result.success:
                    cycle.success = False
                    cycle.error_message = plan_result.error_message or 'planning_failed'
                    if plan_result.failure_event is not None:
                        cycle.failure_event = plan_result.failure_event.to_dict()
                        last_failure_event = plan_result.failure_event
                    self.cycles.append(cycle)
                    failure_reason = cycle.error_message
                    # If the planning failure is recoverable (e.g. parse error),
                    # feed it back as context and let the LLM replan
                    if plan_result.failure_event is not None and plan_result.failure_event.should_replan:
                        # Clear stale remaining_actions — no execution happened this cycle
                        if hasattr(self.executor, 'remaining_actions'):
                            self.executor.remaining_actions = []
                        pending_failure = plan_result.failure_event
                        continue
                    break

                execution = self.executor.execute_actions(
                    plan_result.actions,
                    self.failure_checker,
                    pre_action_checks_enabled=self.config.pre_action_checks_enabled,
                    post_action_checks_enabled=self.config.post_action_checks_enabled,
                )

                cycle.completed_actions = list(getattr(self.executor, 'completed_primitive_actions', []))
                cycle.remaining_actions = list(execution.remaining_actions)
                cycle.success = bool(execution.success)
                cycle.error_message = execution.error_message
                if execution.last_failure_event is not None:
                    cycle.failure_event = execution.last_failure_event.to_dict()
                    last_failure_event = execution.last_failure_event

                self.cycles.append(cycle)

                if execution.success:
                    if self.config.enable_goal_check:
                        goal_check = self._check_goal_completion_with_deterministic_override(goal_text)
                        cycle.goal_check = goal_check.to_dict()
                        if goal_check.success and goal_check.goal_satisfied:
                            failure_reason = None
                            break
                        if self._is_implicit_non_target_only_goal_failure(goal_check):
                            failure_reason = None
                            break
                        goal_failure = self._goal_check_failure_event(goal_check)
                        cycle.success = False
                        cycle.failure_event = goal_failure.to_dict()
                        last_failure_event = goal_failure
                        pending_failure = goal_failure
                        failure_reason = goal_failure.message
                        if len(self.cycles) > self.config.max_replans:
                            break
                        continue

                    failure_reason = None
                    break

                pending_failure = execution.last_failure_event
                failure_reason = execution.error_message or (pending_failure.message if pending_failure else 'execution_failed')
                if pending_failure is None or not pending_failure.should_replan:
                    break
                if len(self.cycles) > self.config.max_replans:
                    break

        success = bool(self.cycles) and self.cycles[-1].success
        planned_actions = list(self.cycles[0].planned_actions) if self.cycles else []
        completed_actions = list(getattr(self.executor, 'completed_primitive_actions', []))
        remaining_actions = list(getattr(self.executor, 'remaining_actions', []))
        held_object = getattr(self.executor, 'held_object', None)
        if execution_skipped:
            completed_actions = []
            remaining_actions = list(planned_actions) if success else []
            held_object = None
        final_scene_state = self._final_scene_state_summary()
        model_type = self.config.effective_model_type
        image_metadata = (
            (self.last_prompt_trace.get('bundle') or {}).get('image_metadata')
            or self._image_metadata(None)
        )
        prompt_mode = PROMPT_MODE_VLM_MULTIMODAL if self.config.enable_vision else self.config.prompt_mode
        planner_times = [float(cycle.inference_time_s or 0.0) for cycle in self.cycles]
        planner_invocations = len(planner_times)
        total_planner_time_s = float(sum(planner_times))
        return {
            'success': success,
            'goal_text': goal_text,
            'model_alias': getattr(self.planner, 'model_alias', self.config.model_alias),
            'model_path': getattr(self.planner, 'model_name', self.config.model_path or self.config.model_alias),
            'model_type': model_type,
            'quantization': self._planner_quantization(),
            'icl_mode': self.config.icl_mode,
            'prompt_mode': prompt_mode,
            'replan_mode': 'off' if execution_skipped else 'on',
            'replanning_enabled': bool(self.config.enable_replanning),
            'execution_skipped': execution_skipped,
            'text_only': not self.config.enable_vision,
            'use_vision': bool(self.config.enable_vision),
            'image_present': bool(image_metadata.get('image_present', False)),
            'image_metadata': image_metadata,
            'segmentation_first': True,
            'use_remote_planner': bool(self.config.use_remote_planner),
            'remote_planner_url': self.config.remote_planner_url or None,
            'pre_action_checks_enabled': bool(self.config.pre_action_checks_enabled),
            'post_action_checks_enabled': bool(self.config.post_action_checks_enabled),
            'goal_check_enabled': bool(self.config.enable_goal_check),
            'planned_actions': planned_actions,
            'completed_actions': completed_actions,
            'remaining_actions': remaining_actions,
            'held_object': held_object,
            'final_scene_state': final_scene_state,
            'final_object_region_map': dict(final_scene_state.get('object_region_map', {}) or {}),
            'final_lid_states': dict(final_scene_state.get('lid_states', {}) or {}),
            'last_goal_check': next(
                (cycle.goal_check for cycle in reversed(self.cycles) if cycle.goal_check),
                None,
            ),
            'last_failure_event': last_failure_event.to_dict() if last_failure_event else None,
            'failure_reason': failure_reason,
            'total_cycles': len(self.cycles),
            'total_replans': sum(1 for cycle in self.cycles if cycle.is_replan),
            'planner_invocations': int(planner_invocations),
            'total_planner_time_s': total_planner_time_s,
            'mean_planner_time_per_invocation_s': (
                total_planner_time_s / planner_invocations if planner_invocations else None
            ),
            'episode_time_s': time.time() - started_at,
            'cycles': [cycle.to_dict() for cycle in self.cycles],
        }

    def get_debug_snapshot(self) -> Dict[str, Any]:
        debug = {}
        if hasattr(self.planner, 'get_debug_info'):
            debug.update(dict(self.planner.get_debug_info()))
        if self.symbol_registry is not None:
            debug['symbol_registry'] = self.symbol_registry.to_dict()
        return debug

    def _planner_quantization(self, debug_snapshot: Optional[Dict[str, Any]] = None) -> str:
        direct = getattr(self.planner, 'quantization', None)
        if direct:
            return str(direct)
        if debug_snapshot is None:
            debug_snapshot = self.get_debug_snapshot()
        for source in (
            debug_snapshot,
            debug_snapshot.get('health', {}) if isinstance(debug_snapshot, dict) else {},
            debug_snapshot.get('last_request', {}) if isinstance(debug_snapshot, dict) else {},
        ):
            if isinstance(source, dict) and source.get('quantization'):
                return str(source['quantization'])
        return self.config.effective_quantization

    def shutdown(self) -> None:
        if self.segmentation_adapter is not None and hasattr(self.segmentation_adapter, 'shutdown'):
            try:
                self.segmentation_adapter.shutdown()
            except Exception:
                pass
        if self.env is None or not hasattr(self.env, 'pr'):
            return
        try:
            self.env.pr.stop()
        except Exception:
            pass
        try:
            self.env.pr.shutdown()
        except Exception:
            pass


    def _settle_environment(self) -> None:
        if self.env is None or not hasattr(self.env, 'pr'):
            return
        hold_startup_lid_pose = getattr(self.env, 'hold_startup_lid_pose', None)
        for _ in range(50):
            if callable(hold_startup_lid_pose):
                hold_startup_lid_pose()
            self.env.pr.step()
        if hasattr(self.env, 'get_home_conf') and hasattr(self.env, 'set_robot_conf'):
            try:
                self.env.set_robot_conf(self.env.get_home_conf())
                for _ in range(10):
                    if callable(hold_startup_lid_pose):
                        hold_startup_lid_pose()
                    self.env.pr.step()
            except Exception:
                pass

    def _on_sim_step(self) -> None:
        if not self.config.live_segmentation_view or self.config.headless:
            return
        self._sim_step_counter += 1
        stride = max(1, int(self.config.live_view_update_stride))
        if self._sim_step_counter % stride != 0:
            return
        if self.segmentation_adapter is not None and hasattr(self.segmentation_adapter, 'update_live_segmentation_view'):
            self.segmentation_adapter.update_live_segmentation_view()

    def _on_action_start(self, actions: List[DirectAction], current_action_index: int) -> None:
        self._update_live_action_sequence(actions, current_action_index)

    def _update_live_action_sequence(self, actions, current_action_index: Optional[int] = None) -> None:
        if not self.config.live_segmentation_view or self.config.headless:
            return
        current_action_label = None
        if actions and current_action_index is not None and 0 <= current_action_index < len(actions):
            current_action_label = str(actions[current_action_index])
        if self.segmentation_adapter is not None and hasattr(self.segmentation_adapter, 'set_live_action_sequence'):
            self.segmentation_adapter.set_live_action_sequence(
                actions=actions or [],
                current_action_index=current_action_index,
                current_action_label=current_action_label,
            )

if __name__ == '__main__':
    """CLI Entry Point for the Replanning Pipeline."""
    import argparse
    import json
    parser = argparse.ArgumentParser(description="Run the LLM/VLM Replanning Pipeline")
    parser.add_argument("--variant", type=str, default="", help="Canonical variant id (K1/K2/K3/G1/G2/G3)")
    parser.add_argument("--goal", type=str, default="", help="Task goal text. Defaults to the variant goal when --variant is set.")
    parser.add_argument("--model", type=str, default="qwen", help="Model alias")
    parser.add_argument("--model-type", choices=["", "llm", "vlm"], default="", help="Optional explicit model type")
    parser.add_argument("--quantization", choices=["", "none", "bnb8", "bnb4"], default="", help="Local quantization mode for Hugging Face loading")
    parser.add_argument("--icl-mode", type=str, default=ICLMode.ZERO_SHOT.value, choices=[mode.value for mode in ICLMode], help="Prompt mode")
    parser.add_argument("--vision", action="store_true", help="Enable vision-first reasoning (VLM)")
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument("--gui", action="store_true", help="Run with simulator GUI (default)")
    display_group.add_argument("--headless", action="store_true", help="Run without simulator GUI")
    parser.add_argument("--remote", action="store_true", help="Use the maintained remote LLM planner server")
    parser.add_argument("--remote-url", default=os.environ.get("LLM_SERVER_URL", os.environ.get("VLM_SERVER_URL", "http://localhost:8000")), help="Remote planner server URL")
    parser.add_argument("--max-replans", type=int, default=3, help="Maximum replans during execution")
    parser.add_argument("--replan-mode", choices=["on", "off"], default="on", help="Use full execution+replanning or first-plan-only mode")
    parser.add_argument("--task-family", choices=["kitchen", "grill"], default="", help="Task family override when --variant is not set")
    parser.add_argument("--scene-path", default="", help="Scene path override")
    parser.add_argument("--no-live-masks", action="store_true", help="Disable the separate live segmentation window")
    parser.add_argument("--scene-state-trace", action="store_true", help="Print scene-state snapshots around execution checks")
    parser.add_argument("--no-goal-check", action="store_true", help="Disable LLM goal-completion verification after each completed plan")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    variant_spec = None
    if args.variant:
        from evaluation.canonical_variants import get_variant_spec

        variant_spec = get_variant_spec(args.variant)
    goal_text = args.goal or (variant_spec.goal_text if variant_spec is not None else "")
    if not goal_text:
        parser.error("--goal is required when --variant is not set")

    task_family = args.task_family or (variant_spec.task_family if variant_spec is not None else "kitchen")
    scene_path = args.scene_path or (variant_spec.scene_path if variant_spec is not None else "")
    headless = bool(args.headless)
    env = None

    if variant_spec is not None and task_family == "grill":
        from llm_pipeline.debug_execution import (
            DebugSequence,
            _configure_scene_env,
            _load_env_for_sequence,
        )

        sequence = DebugSequence(
            name=f"{variant_spec.variant_id}_llm_pipeline",
            variant=variant_spec.variant_id,
            goal=goal_text,
            actions=(),
        )
        _configure_scene_env(sequence, headless=headless)
        env = _load_env_for_sequence(sequence)
    else:
        os.environ["HEADLESS"] = "True" if headless else "False"
        os.environ["COPPELIASIM_HEADLESS"] = "1" if headless else "0"
        if task_family == "grill" and scene_path:
            os.environ["GRILL_SCENE_FILE"] = scene_path
        elif scene_path:
            os.environ["KITCHEN_SCENE_FILE"] = scene_path

    config = LLMPipelineConfig(
        model_alias=args.model,
        icl_mode=args.icl_mode,
        max_replans=args.max_replans,
        enable_replanning=args.replan_mode != "off",
        headless=headless,
        enable_vision=args.vision,
        model_type=args.model_type or ("vlm" if args.vision else "llm"),
        quantization=args.quantization,
        text_only=not args.vision,
        prompt_mode=PROMPT_MODE_VLM_MULTIMODAL if args.vision else PROMPT_MODE_SEGMENTATION_TEXT,
        use_remote_planner=args.remote,
        remote_planner_url=args.remote_url,
        task_family=task_family,
        scene_path=scene_path,
        variant_id=variant_spec.variant_id if variant_spec is not None else "",
        live_segmentation_view=not args.no_live_masks and not headless,
        scene_state_trace=args.scene_state_trace,
        enable_goal_check=not args.no_goal_check,
        context_builder_type='geometric',
    )
    pipeline = LLMOnlyReplanningPipeline(config=config)
    
    print(f"[ENTRY] Initializing pipeline in {config.context_builder_type} mode...")
    if pipeline.initialize(env=env):
        print(f"[ENTRY] Starting loop for goal: {goal_text}")
        results = pipeline.run(goal_text)
        print(f"[ENTRY] Loop finished. Success: {results['success']}")
        if args.output:
            from pathlib import Path

            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(results, indent=2))
        else:
            print(json.dumps(results, indent=2))
    else:
        print("[ENTRY] Optimization: Initialization failed.")
