"""LLM-only replanning pipeline driven directly by segmentation evidence."""

from __future__ import annotations

import hashlib
import os
import sys
import time
import numpy as np
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from llm_pipeline.catalog import resolve_llm_model, resolve_planner_model, resolve_vlm_model
from llm_pipeline.failures import (
    INFRASTRUCTURE_FAILURE_CODES, CycleError, FailureCheck, FailureCode, TerminationReason, failure_check_for,
)
from llm_pipeline.flags import PipelineFlags
from llm_pipeline.memory import ObservationMemory
from llm_pipeline.prompt_v2 import LID_REGIONS, IdentifiedAction, PromptV2Builder, ReplanContext
from llm_pipeline.trial_log import LoggingFailureChecker, NullTrialLogger, prompt_hash
from llm_pipeline.client import RemoteTextLLMPlanner
from llm_pipeline.executable_symbols import build_runtime_symbol_registry
from llm_pipeline.failure_logic import SegmentationFirstFailureChecker, GeometricFailureChecker
from llm_pipeline.object_aliases import scene_object_for_object
from llm_pipeline.planner import TextLLMPlanner
from llm_pipeline.prompt_builder import TextOnlyContextBuilder
from llm_pipeline.quantization import normalize_quantization
from llm_pipeline.segmentation_adapter import SegmentationEvidenceAdapter
from llm_pipeline.strict_parser import StrictActionParser, split_reasoning
from llm_pipeline.region_aliases import normalize_region_name, planner_region_name, scene_object_for_region
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


# Replan budget for every run type (model, oracle, matrix, benchmark). It is set here only;
# the runners take no command-line default for it and log it in trial_start.
DEFAULT_MAX_REPLANS = 10


@dataclass
class LLMPipelineConfig:
    model_alias: str = 'qwen'
    model_path: str = ''
    icl_mode: str = ICLMode.ZERO_SHOT.value
    max_replans: int = DEFAULT_MAX_REPLANS
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
    # Remote planner protocol: 'openai' (a vLLM server's OpenAI-compatible API, the real-model
    # planner; llm_pipeline/vllm_client.py) or 'legacy' (llm_pipeline/server.py job protocol).
    remote_planner_api: str = 'openai'
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
    # plan.md Section 0.7 flags (termination.mode, prompt.version, ...).
    flags: PipelineFlags = field(default_factory=PipelineFlags)
    # Trial seed; with scene.randomization=pose_jitter it seeds the initial-pose jitter.
    seed: Optional[int] = None

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
        self.trial_logger = NullTrialLogger()
        self._reset_trial_log_state()

        # Default context builder: prompt.version selects v2 (docs/PROMPTS.md) or the legacy prompts.
        if self.context_builder is None:
            if self.config.flags.prompt_version == 'v2':
                self.context_builder = PromptV2Builder()
            else:
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
        from llm_pipeline.final_variant_setup import configure_env

        self.final_variant = configure_env(env, self.config.variant_id)

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
        if hasattr(self.executor, 'set_event_sink'):
            self.executor.set_event_sink(self._log_executor_event)
        if hasattr(self.executor, 'set_bundle_end_callback'):
            self.executor.set_bundle_end_callback(self._on_bundle_end)
        # Both trigger rules (discovery and IF) run at the same point: after every bundle that
        # leaves the gripper empty. The failure checker's own discovery trigger is off, so the
        # two modes differ only in which observed objects trigger (plan.md 8.1, Ablation: IF).
        if hasattr(self.executor, 'set_trigger_check'):
            self.executor.set_trigger_check(self._trigger_check)
        if hasattr(self.failure_checker, 'replan_on_new_visibility'):
            self.failure_checker.replan_on_new_visibility = False
        if hasattr(self.failure_checker, 'grasp_confirmation'):
            self.failure_checker.grasp_confirmation = self.config.flags.grasp_confirmation
        if hasattr(self.failure_checker, 'remembered_pick_allowed'):
            self.failure_checker.remembered_pick_allowed = self._remembered_pick_allowed
        if not isinstance(self.failure_checker, LoggingFailureChecker):
            self.failure_checker = LoggingFailureChecker(
                self.failure_checker,
                emit=self._log_event,
                step=lambda: self.step,
            )

        if self.planner is None:
            model_alias, model_name = self.config.resolve_model_name()
            if self.config.use_remote_planner and self.config.remote_planner_api == 'openai':
                from llm_pipeline.vllm_client import VLLMChatPlanner

                self.planner = VLLMChatPlanner(server_url=self.config.remote_planner_url or None,
                                               model=self.config.model_alias)
            elif self.config.use_remote_planner:
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

        self.randomization_record = None
        if self.config.flags.scene_randomization == 'pose_jitter' and self.config.seed is not None:
            from llm_pipeline.randomization import apply_pose_jitter

            variant_id = self._variant_id_for_goal_check()
            self.randomization_record = apply_pose_jitter(env, variant_id, self.config.seed)
            print(f'[RANDOMIZE] seed={self.config.seed} {self.randomization_record["objects"]}')

        self.reset_episode_state()
        self._settle_environment()
        if self.segmentation_adapter is not None:
            self.segmentation_adapter.refresh_visibility(event='initial')
        self.initial_ground_truth = self._final_variant_ground_truth()
        self._update_live_action_sequence([], None)
        return True

    def _final_variant_ground_truth(self) -> Optional[Dict[str, Any]]:
        """Simulator ground truth for the labeled evaluator (final variants only)."""
        spec = getattr(self, 'final_variant', None)
        if spec is None:
            return None
        from llm_pipeline.final_variant_setup import ground_truth_state

        detector = getattr(self.segmentation_adapter, 'detector', None)
        return ground_truth_state(self.env, spec, detector, self.symbol_registry.regions)

    # ---------------------------------------------------------------- trial log
    def set_trial_logger(self, trial_logger) -> None:
        self.trial_logger = trial_logger or NullTrialLogger()

    def _reset_trial_log_state(self) -> None:
        self.step = 0
        self.termination_reason: Optional[str] = None
        self._observation_seen: set = set()
        self._action_counter = 0
        self._completed_with_ids: List[IdentifiedAction] = []
        self._remaining_with_ids: List[IdentifiedAction] = []
        self._current_plan_with_ids: List[IdentifiedAction] = []
        self.memory = ObservationMemory()
        self._last_articulation: Dict[str, bool] = {}
        # IF rule (Phase 4): the agent's own view of object regions.
        self._first_seen_regions: Dict[str, Optional[str]] = {}
        self._last_object_regions: Dict[str, Optional[str]] = {}
        self._current_visible: set = set()
        # Placement areas each object's footprint intersected when it was last visible.
        self._overlap_at_last_sight: Dict[str, List[str]] = {}
        # Discovery trigger: objects already seen at a planning event or a trigger check.
        self._trigger_seen: set = set()
        # Objects a corrective replan declared as needing no action, with their region then.
        self._no_action_objects: Dict[str, Optional[str]] = {}
        # WHERE (Phase 5): the trigger a corrective replan answers, and its proposal count.
        self._active_trigger: Optional[FailureEvent] = None
        self._corrective_attempts = 0
        self._next_plan_ids: Optional[List[str]] = None
        # Repeated-output detection (DIAGNOSTICS area 8): (abstract state, output) hashes.
        self._tried_outputs: set = set()
        self._repeat_counts: Dict[str, int] = {}   # per (abstract state, output, failure signature)

    def _log_event(self, event: str, **fields) -> None:
        try:
            self.trial_logger.emit(event, **fields)
        except Exception as exc:
            print(f'[TRIAL-LOG] {event} not logged: {exc}')

    def _log_executor_event(self, event: str, **fields) -> None:
        self._log_event(event, step=self.step, **fields)

    def _scene_lids(self) -> List[str]:
        objects = set(getattr(self.symbol_registry, 'objects', ()) or ())
        return [lid for lid in LID_REGIONS if lid in objects]

    def _lid_states_from_snapshot(self, snapshot) -> Dict[str, bool]:
        """Lid states from joint/pose values: a stand-in for camera perception (docs/ARCHITECTURE.md)."""
        states = {}
        for lid in self._scene_lids():
            try:
                if lid == 'grill_lid':
                    value = infer_grill_lid_open(self.env)
                else:
                    value = self.segmentation_adapter.is_lid_open(snapshot, lid_name=lid)
            except Exception:
                value = None
            if value is not None:
                states[lid] = bool(value)
        return states

    def observed_objects(self) -> set:
        """Objects the robot has observed so far in this trial, plus the scene's lids."""
        seen = set(getattr(self.segmentation_adapter, 'known_visible', set()) or set())
        seen.update(self._observation_seen)
        seen.update(self._scene_lids())
        return seen

    @property
    def memory_enabled(self) -> bool:
        return self.config.flags.memory_enabled == 'true'

    def _closed_regions(self, articulation_states) -> set:
        closed = set()
        for lid, is_open in (articulation_states or {}).items():
            if not is_open:
                closed.update(LID_REGIONS.get(lid, ()))
        return closed

    def _update_memory(self, visible, object_region_map, articulation_states, visible_regions) -> None:
        self.memory.update(self.step, visible, object_region_map, held_object=getattr(self.executor, 'held_object', None))
        self._log_event('memory_snapshot', step=self.step, memory=self.memory.snapshot())
        all_regions = set(getattr(self.symbol_registry, 'regions', ()) or ())
        open_regions = all_regions - self._closed_regions(articulation_states)
        for entry in self.memory.mismatches(visible_regions, open_regions):
            self._log_event('memory_mismatch', step=self.step, object=entry.object_id,
                            last_region=entry.last_region, last_seen_step=entry.last_seen_step,
                            failure_code=str(FailureCode.MEMORY_MISMATCH))

    def _remembered_pick_allowed(self, object_name: str) -> bool:
        if not self.memory_enabled or self.memory.is_visible(object_name):
            return False
        entry = self.memory.get(object_name)
        return entry is not None and entry.last_region not in self._closed_regions(self._last_articulation)

    def _emit_observation(self, visible_objects, object_region_map, articulation_states, visible_regions=()) -> None:
        self.step += 1
        visible = [name for name in visible_objects if name not in LID_REGIONS]
        newly_visible = [name for name in visible if name not in self._observation_seen]
        self._observation_seen.update(visible)
        self._last_articulation = dict(articulation_states or {})
        self._current_visible = set(visible)
        for name in visible:
            region = (object_region_map or {}).get(name)
            self._first_seen_regions.setdefault(name, region)
            self._last_object_regions[name] = region
            self._overlap_at_last_sight[name] = self._placement_area_overlaps(name)
        if self.memory_enabled:
            self._update_memory(visible, dict(object_region_map or {}), articulation_states, visible_regions)
        self._log_event(
            'observation',
            step=self.step,
            visible_objects=visible,
            object_regions={name: object_region_map.get(name) for name in visible},
            articulation_states={name: ('open' if is_open else 'closed') for name, is_open in articulation_states.items()},
            newly_visible_objects=newly_visible,
            **self._gt_positions_field(),
        )

    def _gt_positions_field(self) -> Dict[str, Any]:
        """Final variants: simulator positions of the variant objects, for diagnosing the
        executor (evaluator-side only; never shown to the planner)."""
        spec = getattr(self, 'final_variant', None)
        if spec is None or self.env is None:
            return {}
        positions = {}
        for scene_name, label in spec.labels.items():
            try:
                positions[label] = [round(float(v), 3) for v in self.env.get_object(scene_name).get_position()]
            except Exception:
                continue
        return {'gt_positions': positions}

    def _on_bundle_end(self, bundle_id, actions, success, failure_event, snapshot) -> None:
        del bundle_id, actions, success, failure_event
        if snapshot is None:
            return
        self._emit_observation(
            list(getattr(snapshot, 'visible_objects', []) or []),
            dict(getattr(snapshot, 'object_region_map', {}) or {}),
            self._lid_states_from_snapshot(snapshot),
            list(getattr(snapshot, 'visible_regions', []) or []),
        )

    # -- triggers: IF rule (plan.md Phase 4) and discovery -------------------------
    TRIGGER_CODES = (FailureCode.IF_RULE_TRIGGER, FailureCode.NEW_OBJECT_DISCOVERED)

    @classmethod
    def _is_trigger(cls, failure_event) -> bool:
        return failure_event is not None and failure_event.failure_id in cls.TRIGGER_CODES

    def _if_rule_object_regions(self) -> Dict[str, Optional[str]]:
        """Objects the IF rule evaluates: the visible ones, plus the remembered ones when memory
        is on (plan.md 4.1), each with the region the agent last saw it in (never hidden state)."""
        regions = {name: self._last_object_regions.get(name) for name in self._current_visible}
        if self.memory_enabled:
            for entry in self.memory.remembered():
                regions.setdefault(entry.object_id, entry.last_region)
        return regions

    def _known_object_regions(self) -> Dict[str, Optional[str]]:
        """The region every observed object was last seen in (the scheduler's view, Phase 6)."""
        return dict(self._last_object_regions)

    def _placement_area_overlaps(self, object_id: str) -> List[str]:
        """System geometry at observation time: placement areas the visible object's footprint intersects."""
        areas = getattr(self.env, 'placement_areas', None) or {}
        if not areas or self.env is None:
            return []
        from llm_pipeline.final_variant_setup import footprint_overlaps

        try:
            obj = self.env.get_object(scene_object_for_object(object_id, self.env))
        except Exception:
            obj = None
        if obj is None:
            return []
        return [region for region, area in areas.items() if footprint_overlaps(obj, area)]

    def _overlapping_regions(self, object_id: str, regions) -> List[str]:
        """Regions among ``regions`` whose placement area the object's footprint intersected when
        it was last visible (a remembered object is never looked up in the simulator)."""
        seen = set(self._overlap_at_last_sight.get(object_id) or ())
        return [region for region in regions if region in seen]

    def _trigger_check(self, remaining_plan) -> Optional[FailureEvent]:
        """Called after every bundle that leaves the gripper empty, in both trigger modes.

        The object classifier (relevant / goal-attained / overlapping / accounted-for) is the
        same in both modes; only the choice of trigger objects differs: ``if_rule`` applies
        plan.md 4.1, ``discovery`` takes every object seen for the first time."""
        from llm_pipeline.if_rule import assess_objects, describe_trigger, trigger_objects

        mode = self.config.flags.replan_trigger_mode
        completed = list(getattr(self.executor, 'completed_primitive_actions', []) or [])
        object_regions = self._if_rule_object_regions()
        acknowledged = {obj for obj, region in self._no_action_objects.items() if object_regions.get(obj) == region}
        assessments = assess_objects(
            scene=(self.config.task_family or 'kitchen').strip().lower(),
            object_regions=object_regions,
            remaining_plan=list(remaining_plan or []),
            completed_actions=completed,
            initial_regions=self._first_seen_regions,
            overlapping=self._overlapping_regions,
            pending_objects=acknowledged,
            held_object=getattr(self.executor, 'held_object', None),
        )
        newly_visible: List[str] = []
        if mode == 'discovery':
            by_id = {a.object_id: a for a in assessments}
            newly_visible = sorted(obj for obj in self._observation_seen - self._trigger_seen
                                   if obj not in LID_REGIONS)
            self._trigger_seen.update(self._observation_seen)
            triggers = [by_id[obj] for obj in newly_visible if obj in by_id]
        else:
            triggers = trigger_objects(assessments)
        self._log_event('if_check', step=self.step, trigger_mode=mode, objects=[a.to_dict() for a in assessments],
                        trigger_objects=[a.object_id for a in triggers], newly_visible_objects=newly_visible,
                        no_action_objects=sorted(acknowledged), remaining_plan=list(remaining_plan or []))
        if not triggers:
            return None
        last_action = completed[-1] if completed else None
        facts = [describe_trigger(a, planner_region_name) for a in triggers]
        names = [a.object_id for a in triggers]
        discovery = mode == 'discovery'
        return FailureEvent(
            failure_id=FailureCode.NEW_OBJECT_DISCOVERED if discovery else FailureCode.IF_RULE_TRIGGER,
            stage=FailureStage.AFTER_EXECUTION,
            source=FailureSource.SEGMENTATION,
            action=last_action,
            evidence={
                'trigger_mode': mode,
                'trigger_objects': names,
                'newly_visible_objects': names if discovery else [],
                'trigger_kinds': {a.object_id: a.trigger_kind for a in triggers},
                'assessments': [a.to_dict() for a in triggers],
                'trigger_facts': facts,
            },
            failure_layer=FailureLayer.LAYER_2,
            should_replan=True,
            message=(('Newly visible objects: ' if discovery else 'Objects the remaining plan does not handle: ')
                     + '; '.join(facts)),
        )

    # Kept for callers of the Phase 4 name.
    _if_rule_check = _trigger_check

    def _assign_plan_ids(self, actions) -> List[IdentifiedAction]:
        # A merged plan (Phase 5) keeps the ids of its remaining-plan actions.
        ids, self._next_plan_ids = self._next_plan_ids, None
        if ids is not None and len(ids) == len(list(actions)):
            return [IdentifiedAction(action_id, str(action)) for action_id, action in zip(ids, actions)]
        identified = []
        for action in actions:
            self._action_counter += 1
            identified.append(IdentifiedAction(f'a{self._action_counter}', str(action)))
        return identified

    def _record_execution_progress(self, plan_with_ids: List[IdentifiedAction], remaining_actions) -> None:
        remaining_count = len(list(remaining_actions or []))
        done = plan_with_ids[: max(0, len(plan_with_ids) - remaining_count)]
        self._completed_with_ids.extend(done)
        self._remaining_with_ids = plan_with_ids[len(done):]

    def _set_termination(self, reason) -> None:
        if self.termination_reason is None:
            self.termination_reason = str(reason)

    def reset_episode_state(self) -> None:
        self.cycles = []
        self.last_prompt_trace = {}
        self._sim_step_counter = 0
        self._reset_trial_log_state()
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
        request = self._prepare_planning(goal_text, failure_event, silent=silent)
        started = time.time()
        result = self._call_planner(request)
        return self._finish_planning(request, result, wall_latency_s=time.time() - started)

    def _prepare_planning(self, goal_text: str, failure_event: Optional[FailureEvent], silent: bool = False) -> Dict[str, Any]:
        """Observation, context and prompt bundle (main thread: reads the simulator)."""
        # 1. Capture and resolve scene state
        state = self._build_scene_state()
        # Every planning event is an observation, except a re-query after a plan-check
        # failure, which belongs to the same planning event (plan.md Section 10, Q7).
        is_plan_check_requery = (
            failure_event is not None
            and failure_check_for(failure_event.failure_id) in (FailureCheck.PLAN_CHECK, FailureCheck.INSERTION)
        )
        if not is_plan_check_requery:
            snapshot = getattr(state, '_original_snapshot', None)
            self._emit_observation(state.visible_objects, dict(state.object_region_map or {}), dict(state.lid_states or {}),
                                   list(getattr(snapshot, 'visible_regions', []) or []))
            # Objects in a planning prompt are not "newly visible" for the discovery trigger.
            self._trigger_seen.update(self._observation_seen)
        if hasattr(self.context_builder, 'set_replan_context'):
            completed, remaining = list(self._completed_with_ids), list(self._remaining_with_ids)
            # Phase 6/7c: the independent bundles the robot runs while the planner works are listed
            # as scheduled (never as completed: the Current state is the observation now, before
            # they run), and they are not part of the remaining plan the blocks are inserted into.
            during_wait = getattr(self, '_prompt_scheduled_ids', None) or set()
            scheduled = [item for item in remaining if item.action_id in during_wait]
            remaining = [item for item in remaining if item.action_id not in during_wait]
            self.context_builder.set_replan_context(ReplanContext(completed=completed, remaining=remaining,
                                                                  scheduled=scheduled))
        # Objects never observed must not reach the planner (plan.md Phase 1, step 5b).
        planner_parser = getattr(self.planner, 'parser', None)
        if planner_parser is not None and hasattr(planner_parser, 'set_observed_objects'):
            planner_parser.set_observed_objects(self.observed_objects())
        if planner_parser is not None and hasattr(planner_parser, 'require_final_marker'):
            planner_parser.require_final_marker = self.config.flags.prompt_version == 'v2'
        remembered = self.memory.remembered() if self.memory_enabled else None
        if hasattr(self.context_builder, 'set_memory_view'):
            self.context_builder.set_memory_view(
                None if remembered is None
                else [(entry.object_id, entry.last_region, self.step - entry.last_seen_step) for entry in remembered]
            )
        if planner_parser is not None and hasattr(planner_parser, 'set_access_context'):
            if remembered is None:
                planner_parser.set_access_context(None)
            else:
                planner_parser.set_access_context(
                    remembered_regions={entry.object_id: entry.last_region for entry in remembered},
                    closed_regions=self._closed_regions(self._last_articulation),
                    lid_regions=LID_REGIONS,
                )

        corrective = self._corrective_context(failure_event)
        if hasattr(self.context_builder, 'set_corrective'):
            self.context_builder.set_corrective(*(corrective or (None, None)),
                                                hints=self.config.flags.prompt_corrective_hints == 'on')

        # 2. Build prompt bundle via modular context builder. Completed actions come from
        # the executor's cumulative list; concatenating per-cycle lists duplicated them.
        bundle = self.context_builder.build_bundle(
            state=state,
            goal_text=goal_text,
            failure_event=failure_event,
            previous_actions=list(getattr(self.executor, 'completed_primitive_actions', []) or []),
            icl_mode=self.config.icl_mode
        )
        bundle_metadata = dict(getattr(bundle, 'metadata', {}) or {})
        bundle_metadata.update({
            'held_object': getattr(self.executor, 'held_object', None),
            'max_new_tokens': int(self.config.planner_max_new_tokens),
            'temperature': float(self.config.planner_temperature),
            'prompt_version': self.config.flags.prompt_version,
        })
        if corrective is not None:
            bundle_metadata.update({
                'output_format': 'corrective_blocks',
                'trigger_objects': list((corrective[0].evidence or {}).get('trigger_objects') or []),
                'trigger_mode': (corrective[0].evidence or {}).get('trigger_mode'),
                # Exactly the remaining plan shown in the prompt (scheduled actions excluded).
                'remaining_plan': [(item.action_id, item.action) for item in self._remaining_with_ids
                                   if item.action_id not in (getattr(self, '_prompt_scheduled_ids', None) or set())],
                'scheduled_actions': [(item.action_id, item.action) for item in self._remaining_with_ids
                                      if item.action_id in (getattr(self, '_prompt_scheduled_ids', None) or set())],
            })
        bundle = replace(bundle, metadata=bundle_metadata)
        abstract_state = self._abstract_state(state, corrective, failure_event)

        is_replan = failure_event is not None
        cycle_num = len(self.cycles) + 1
        if not silent:
            print(f'\n{"=" * 60}')
            print(f'[LLM] {"REPLAN" if is_replan else "PLAN"} cycle {cycle_num}')
            if is_replan and failure_event is not None:
                print(f'[LLM] Failure context: {failure_event.message}')
            print(f'{"=" * 60}')
        return {'state': state, 'bundle': bundle, 'failure_event': failure_event, 'corrective': corrective,
                'is_replan': is_replan, 'is_plan_check_requery': is_plan_check_requery, 'silent': silent,
                'step': self.step, 'abstract_state': abstract_state}

    def _call_planner(self, request: Dict[str, Any]) -> PlanResult:
        """The planner call only (safe to run off the main thread: no simulator access)."""
        bundle = request['bundle']
        # We try to use the new .plan() interface, fall back to .generate_plan() for legacy
        if hasattr(self.planner, 'plan'):
            return self.planner.plan(bundle)
        return self.planner.generate_plan(
            system_prompt=bundle.system_prompt,
            user_prompt=bundle.user_prompt,
            icl_mode=bundle.icl_mode,
            max_new_tokens=self.config.planner_max_new_tokens,
            temperature=self.config.planner_temperature,
            held_object=bundle.metadata.get('held_object'),
        )

    def _finish_planning(self, request: Dict[str, Any], result: PlanResult,
                         wall_latency_s: float) -> Tuple[PlanResult, Dict[str, Any]]:
        """Corrective merge, printing, planning-event log and prompt trace (main thread)."""
        bundle, state, corrective = request['bundle'], request['state'], request['corrective']
        failure_event, is_replan, silent = request['failure_event'], request['is_replan'], request['silent']
        repeated = None if self._is_infrastructure(result) or silent else self._repeated_output(request, result)
        if repeated is not None:
            result = repeated
        elif corrective is not None and not self._is_infrastructure(result):
            # Corrective blocks are parsed here (an empty output is an invalid block list, not a
            # reason to fall back to a full replan); a planner's own FINAL ACTIONS parse is irrelevant.
            result = self._merge_corrective(result, corrective[0], held_object=getattr(self.executor, 'held_object', None))

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

        if not silent:
            self._log_planning_event(bundle, result, failure_event, is_replan, request['is_plan_check_requery'],
                                     wall_latency_s=wall_latency_s, prompt_step=request.get('step'),
                                     corrective=corrective is not None)

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

    # -- WHEN (plan.md Phase 6) --------------------------------------------------
    def _parallel_applicable(self, failure_event) -> bool:
        flags = self.config.flags
        return (flags.parallel_enabled == 'true' and flags.replan_output_mode == 'corrective'
                and self._is_trigger(failure_event))

    @staticmethod
    def _direct_action(text: str) -> DirectAction:
        name, _, rest = str(text).partition('(')
        args = tuple(arg.strip() for arg in rest.rstrip(')').split(',') if arg.strip())
        return DirectAction(name.strip(), args)

    def _plan_in_parallel(self, goal_text: str, trigger: FailureEvent) -> Tuple[PlanResult, Dict[str, Any]]:
        """Replan in the background while executing independent bundles (plan.md 6.1)."""
        import threading

        from llm_pipeline.parallel import affected_set, independent_bundles, split_bundles

        scene = (self.config.task_family or 'kitchen').strip().lower()
        object_regions = self._known_object_regions()
        remaining = [(item.action_id, item.action) for item in self._remaining_with_ids]
        trigger_objects = (trigger.evidence or {}).get('trigger_objects') or []
        # A trigger object's container is affected only if the object overlaps its placement area.
        affected = affected_set(scene, trigger_objects, object_regions,
                                overlapping={obj: self._overlapping_regions(obj, [object_regions.get(obj)])
                                             for obj in trigger_objects if object_regions.get(obj)})
        independent = independent_bundles(split_bundles(remaining, object_regions), affected)
        # The prompt lists the independent actions as scheduled to run while the planner works.
        scheduled_ids = {action_id for bundle in independent for action_id in bundle.ids}
        self._prompt_scheduled_ids = scheduled_ids
        try:
            request = self._prepare_planning(goal_text, trigger)
        finally:
            self._prompt_scheduled_ids = set()
        box: Dict[str, Any] = {}

        def _worker():
            try:
                box['result'] = self._call_planner(request)
            except Exception as exc:  # planner server errors become a planner-call failure
                box['error'] = exc
            box['returned_at'] = time.monotonic()

        started = time.monotonic()
        thread = threading.Thread(target=_worker, name='replan', daemon=True)
        thread.start()
        executed_ids: List[str] = []
        busy_s, wait_failure = 0.0, None
        saved_check = getattr(self.executor, 'trigger_check', None)
        if hasattr(self.executor, 'set_trigger_check'):
            self.executor.set_trigger_check(None)   # new triggers during the wait are handled after the merge
        try:
            for bundle in independent:
                if not thread.is_alive():
                    break                            # the replan returned: merge after the current bundle
                actions = [self._direct_action(action) for _, action in bundle.actions]
                bundle_started = time.monotonic()
                outcome = self.executor.execute_actions(
                    actions, self.failure_checker,
                    pre_action_checks_enabled=self.config.pre_action_checks_enabled,
                    post_action_checks_enabled=self.config.post_action_checks_enabled,
                )
                busy_s += time.monotonic() - bundle_started
                done = len(actions) - len(list(outcome.remaining_actions or []))
                executed_ids.extend(bundle.ids[:max(0, done)])
                if not outcome.success:
                    wait_failure = outcome.last_failure_event
                    break
        finally:
            if hasattr(self.executor, 'set_trigger_check'):
                self.executor.set_trigger_check(saved_check)
        thread.join()
        latency_s = box.get('returned_at', time.monotonic()) - started
        executed = set(executed_ids)
        self._completed_with_ids.extend(item for item in self._remaining_with_ids if item.action_id in executed)
        self._remaining_with_ids = [item for item in self._remaining_with_ids if item.action_id not in executed]
        self._wait_executed_ids = list(executed_ids)
        self._anchor_excluded_ids = set(scheduled_ids)   # anchors may refer only to remaining actions

        result = box.get('result')
        if result is None:
            error = box.get('error')
            event = FailureEvent(
                failure_id=FailureCode.PLANNER_CALL_FAILED, stage=FailureStage.BEFORE_EXECUTION,
                source=FailureSource.VALIDATION, action=None, evidence={'error': str(error)},
                failure_layer=FailureLayer.LAYER_1, should_replan=False, message=f'Planner call failed: {error}',
            )
            result = PlanResult(False, [], '', latency_s, event.message, event)
        try:
            plan_result, trace = self._finish_planning(request, result, wall_latency_s=latency_s)
        finally:
            self._wait_executed_ids = []
            self._anchor_excluded_ids = set()

        merge_result = 'accepted' if plan_result.success else 'rejected'
        if not plan_result.success and plan_result.failure_event is not None and executed and \
                'the merged plan is invalid' in (plan_result.failure_event.message or ''):
            # The blocks were valid but the plan no longer fits what was executed during the wait.
            merge_result = 'merge_conflict'
            plan_result.failure_event.failure_id = FailureCode.MERGE_CONFLICT
        if wait_failure is not None:
            # An independent bundle failed: its failure is handled first (full replan).
            merge_result = 'discarded_after_execution_failure'
            plan_result = PlanResult(False, [], plan_result.raw_output, plan_result.inference_time,
                                     wait_failure.message, wait_failure)
            self._active_trigger = None
            self._next_plan_ids = None
        self._log_event(
            'parallel', step=self.step, affected_set=affected,
            independent_actions_available=[action for bundle in independent for _, action in bundle.actions],
            independent_actions_executed=[action for action_id, action in remaining if action_id in executed],
            planner_call_latency_s=round(latency_s, 3), robot_busy_time_s=round(busy_s, 3),
            robot_idle_time_s=round(max(0.0, latency_s - busy_s), 3), merge_result=merge_result,
            failure_code=(str(FailureCode.MERGE_CONFLICT) if merge_result == 'merge_conflict' else None),
        )
        return plan_result, trace

    # -- WHERE (plan.md Phase 5) -------------------------------------------------
    def _corrective_context(self, failure_event):
        """(trigger, rejection) when this planner call must return corrective blocks, else None.

        A trigger (IF rule or discovery) asks for blocks. Any rejection of those blocks (a
        block-format error, an unknown name, a block ending while holding, an invalid merged
        plan, insertion_too_late, merge_conflict, a repeated output) re-queries for blocks
        with the specific error; it never falls back to a full replan. Execution failures
        keep the full replan."""
        if self.config.flags.replan_output_mode != 'corrective' or failure_event is None:
            return None
        if self._is_trigger(failure_event):
            self._active_trigger, self._corrective_attempts = failure_event, 0
            return failure_event, None
        if (failure_event.evidence or {}).get('corrective_rejection') and self._active_trigger is not None:
            return self._active_trigger, failure_event
        self._active_trigger = None
        return None

    def _corrective_rejection(self, result, error) -> PlanResult:
        event = FailureEvent(
            failure_id=error.failure_id, stage=FailureStage.BEFORE_EXECUTION, source=FailureSource.VALIDATION,
            action=None, evidence={'fact': error.fact, 'raw_output': result.raw_output, 'corrective_rejection': True},
            failure_layer=FailureLayer.LAYER_1,
            should_replan=True, message=f'Corrective blocks rejected ({error.failure_id}): {error.fact}',
        )
        proposal = getattr(self, '_last_proposal', None) or {}
        self._log_event('insertion', step=self.step, corrective_sub_plans=proposal.get('blocks', []),
                        urgency=proposal.get('urgency', {}), insertion_point=proposal.get('insert', {}),
                        merged_plan=[], first_proposal=self._corrective_attempts == 1, accepted=False,
                        rejection_code=str(error.failure_id), rejection=error.fact)
        return PlanResult(False, [], result.raw_output, result.inference_time, event.message, event)

    def _merge_corrective(self, result, trigger_event, held_object=None) -> PlanResult:
        from llm_pipeline.corrective import (
            CorrectivePlanError, apply_insertion_mode, merge_blocks, parse_blocks, placement_conflict,
        )
        from llm_pipeline.strict_parser import StrictParseError

        self._corrective_attempts += 1
        self._last_proposal = None
        evidence = dict(trigger_event.evidence or {})
        triggers = list(evidence.get('trigger_objects') or [])
        remaining = [(item.action_id, item.action) for item in self._remaining_with_ids]
        parser = getattr(self.planner, 'parser', None)

        def _parse(lines, held=None):
            return parser.parse('FINAL ACTIONS:\n' + '\n'.join(lines), held_object=held)

        try:
            # Anchors may refer only to actions of the remaining plan shown in the prompt: not to
            # actions scheduled (or run) during a parallel replan (Phase 7c). An anchor that ran in
            # between is still moved to the front (anchor_already_executed).
            excluded = set(getattr(self, '_anchor_excluded_ids', set()) or ())
            known_ids = [action_id for action_id, _ in remaining if action_id not in excluded]
            blocks = parse_blocks(result.raw_output, triggers, known_ids)
            for block in blocks:
                if block.no_action:
                    continue
                try:
                    block.actions = [str(action) for action in _parse(block.actions)]
                except StrictParseError as exc:
                    # Keeps the specific code (e.g. an unknown region); the re-query stays corrective.
                    raise CorrectivePlanError(exc.failure_id, f'{", ".join(block.objects)} block: {exc.fact or exc}')
            proposed = [dict(b.to_dict()) for b in blocks]
            self._last_proposal = {
                'blocks': proposed,
                'urgency': {obj: (b.urgency or 'no_action') for b in reversed(blocks) for obj in b.objects},
                'insert': {obj: (b.insert or 'no_action') for b in reversed(blocks) for obj in b.objects},
            }
            blocks = apply_insertion_mode(blocks, self.config.flags.replan_insertion_mode)

            def _new_id():
                self._action_counter += 1
                return f'a{self._action_counter}'

            merge = merge_blocks(remaining, blocks, _new_id)
            merged_actions = [action for _, action in merge.merged]
            try:
                parsed = _parse(merged_actions, held_object)
            except StrictParseError as exc:
                raise CorrectivePlanError(exc.failure_id, f'the merged plan is invalid: {exc.fact or exc}')
            overlapping = {a['object_id']: list(a.get('overlapping_regions') or [])
                           for a in evidence.get('assessments') or []}
            conflict = placement_conflict([str(a) for a in parsed], overlapping)
            if conflict:
                raise CorrectivePlanError(FailureCode.INSERTION_TOO_LATE, conflict)
        except CorrectivePlanError as error:
            return self._corrective_rejection(result, error)

        self._next_plan_ids = [action_id for action_id, _ in merge.merged]
        urgency, insertion_point = {}, {}
        no_action = sorted({obj for block in blocks if block.no_action for obj in block.objects})
        for block in blocks:
            if block.no_action:
                continue
            for obj in block.objects:
                urgency.setdefault(obj, block.proposed_urgency)
                insertion_point.setdefault(obj, block.proposed_insert)
        for obj in no_action:
            urgency.setdefault(obj, 'no_action')
            insertion_point.setdefault(obj, 'no_action')
            self._no_action_objects[obj] = self._if_rule_object_regions().get(obj)
        self._log_event(
            'insertion', step=self.step, corrective_sub_plans=proposed, urgency=urgency, insertion_point=insertion_point,
            merged_plan=[f'{action_id}: {action}' for action_id, action in merge.merged],
            first_proposal=self._corrective_attempts == 1, accepted=True,
            insertion_mode=self.config.flags.replan_insertion_mode, applied=merge.insertions,
            no_action_objects=no_action, all_no_action=all(block.no_action for block in blocks),
            anchors_already_executed=list(merge.anchors_already_executed),
            failure_codes=[str(FailureCode.ANCHOR_ALREADY_EXECUTED)] if merge.anchors_already_executed else [],
        )
        self._active_trigger = None
        return PlanResult(True, list(parsed), result.raw_output, result.inference_time,
                          timing=getattr(result, 'timing', None))

    @staticmethod
    def _is_infrastructure(result: PlanResult) -> bool:
        event = getattr(result, 'failure_event', None)
        return event is not None and event.failure_id in INFRASTRUCTURE_FAILURE_CODES

    def _abstract_state(self, state, corrective, failure_event) -> str:
        """What the planner is asked about, without rejection notes: visible objects and regions,
        remembered objects, lids, gripper, remaining plan and trigger objects."""
        regions = dict(getattr(state, 'object_region_map', {}) or {})
        visible = sorted(name for name in (state.visible_objects or []) if name not in LID_REGIONS)
        trigger = corrective[0] if corrective is not None else (failure_event if self._is_trigger(failure_event) else None)
        parts = {
            'visible': [(name, regions.get(name)) for name in visible],
            'remembered': sorted((e.object_id, e.last_region) for e in self.memory.remembered()) if self.memory_enabled else [],
            'lids': sorted((str(k), bool(v)) for k, v in (getattr(state, 'lid_states', {}) or {}).items()),
            'holding': getattr(self.executor, 'held_object', None),
            'remaining': [item.action for item in self._remaining_with_ids],
            'triggers': sorted((trigger.evidence or {}).get('trigger_objects') or []) if trigger is not None else [],
        }
        return repr(parts)

    @staticmethod
    def _normalized_output(raw_output: str) -> str:
        text = raw_output or ''
        for marker in ('FINAL BLOCKS:', 'FINAL ACTIONS:'):
            index = text.rfind(marker)
            if index >= 0:
                text = text[index:]
                break
        return '\n'.join(line.strip().lower() for line in text.splitlines() if line.strip())

    @staticmethod
    def _failure_signature(failure_event) -> str:
        """What the planner call answers: the failure code and the failed action (a re-query
        after a repeated output answers the same failure as the call it repeats)."""
        if failure_event is None:
            return 'initial'
        evidence = failure_event.evidence or {}
        if failure_event.failure_id == FailureCode.REPEATED_PLANNER_OUTPUT and evidence.get('failure_signature'):
            return str(evidence['failure_signature'])
        return f'{failure_event.failure_id}|{failure_event.action or ""}'

    def _repeated_output(self, request, result) -> Optional[PlanResult]:
        """DIAGNOSTICS area 8: the same output for the same abstract state and the same failure.

        Repeats are counted per (abstract state, output, failure signature), not per trial
        (Phase 7c): the first repeat is rejected and re-queried once with a note (which keeps
        the reason the previous output failed); a second repeat of the same key stops the trial
        with termination reason ``replan_loop``."""
        output = self._normalized_output(result.raw_output)
        if not output:
            return None
        failure_event = request.get('failure_event')
        signature = self._failure_signature(failure_event)
        key = hashlib.sha256((request.get('abstract_state', '') + '\x00' + output + '\x00' + signature)
                             .encode('utf-8')).hexdigest()
        if key not in self._tried_outputs:
            self._tried_outputs.add(key)
            return None
        count = self._repeat_counts.get(key, 0) + 1
        self._repeat_counts[key] = count
        stop = count >= 2
        fact = 'This output was already tried in the same state and it did not work.'
        previous = None
        if failure_event is not None and failure_event.failure_id != FailureCode.REPEATED_PLANNER_OUTPUT:
            previous = (failure_event.evidence or {}).get('fact') or failure_event.message
        elif failure_event is not None:
            previous = (failure_event.evidence or {}).get('previous_fact')
        if previous:
            fact = f'{fact} Earlier it failed with: {previous}'
        event = FailureEvent(
            failure_id=FailureCode.REPEATED_PLANNER_OUTPUT, stage=FailureStage.BEFORE_EXECUTION,
            source=FailureSource.VALIDATION, action=None,
            evidence={'fact': fact, 'raw_output': result.raw_output, 'repeat': count, 'output_hash': key,
                      'failure_signature': signature, 'previous_fact': previous,
                      'corrective_rejection': request.get('corrective') is not None},
            failure_layer=FailureLayer.LAYER_1, should_replan=not stop,
            message=f'Repeated planner output ({count}): {fact}',
        )
        if stop:
            self._set_termination(TerminationReason.REPLAN_LOOP)
        return PlanResult(False, [], result.raw_output, result.inference_time, event.message, event,
                          timing=getattr(result, 'timing', None), reasoning=getattr(result, 'reasoning', None))

    def _replan_reason(self, failure_event, corrective: bool) -> str:
        """Why this planner call happens (logged on every planning_event)."""
        if failure_event is None:
            return 'initial'
        if failure_event.failure_id == FailureCode.IF_RULE_TRIGGER:
            return 'trigger:if_rule'
        if failure_event.failure_id == FailureCode.NEW_OBJECT_DISCOVERED:
            return 'trigger:discovery'
        if failure_event.failure_id == FailureCode.REPEATED_PLANNER_OUTPUT:
            return 'repeated_output_requery'
        if corrective and (failure_event.evidence or {}).get('corrective_rejection'):
            return 'corrective_requery'
        check = failure_check_for(failure_event.failure_id)
        if check in (FailureCheck.PLAN_CHECK, FailureCheck.INSERTION):
            return 'plan_check_requery'
        if check == FailureCheck.GOAL_CHECK:
            return 'goal_check'
        if check in (FailureCheck.EXECUTION_FAILURE, FailureCheck.PRE_ACTION_CHECK):
            return 'execution_failure'
        return str(check or 'other')

    def _log_planning_event(self, bundle, result, failure_event, is_replan, is_plan_check_requery, wall_latency_s,
                            prompt_step: Optional[int] = None, corrective: bool = False) -> None:
        # Events are logged at the current step (observations may have advanced it while a
        # parallel replan was running); the prompt was built at prompt_step.
        step = self.step
        prompt_step = step if prompt_step is None else prompt_step
        trigger_objects = []
        if self._is_trigger(failure_event):
            trigger_objects = list((failure_event.evidence or {}).get('trigger_objects')
                                   or (failure_event.evidence or {}).get('newly_visible_objects') or [])
        prompt_path = self.trial_logger.save_prompt(
            prompt_step, bundle.system_prompt, bundle.user_prompt, kind='replan' if is_replan else 'initial',
        )
        parsed = [str(action) for action in (result.actions or [])]
        timing = dict(getattr(result, 'timing', None) or {})
        self._log_event(
            'planning_event',
            step=step,
            prompt_step=prompt_step,
            kind='replan' if is_replan else 'initial',
            output_format='corrective' if corrective else 'full',
            replan_reason=self._replan_reason(failure_event, corrective),
            plan_check_requery=bool(is_plan_check_requery),
            trigger_code=str(failure_event.failure_id) if failure_event is not None else None,
            trigger_objects=trigger_objects,
            model=getattr(self.planner, 'model_name', None) or getattr(self.planner, 'model_alias', None),
            prompt_version=self.config.flags.prompt_version,
            prompt_hash=prompt_hash(bundle.system_prompt, bundle.user_prompt),
            prompt_path=prompt_path,
            image_present=bool(bundle.images),
            raw_output=result.raw_output,
            reasoning=(result.reasoning if getattr(result, 'reasoning', None) is not None
                       else split_reasoning(result.raw_output)[0]),
            parsed_output=parsed,
            planner_call_latency_s=float(result.inference_time or 0.0),
            wall_latency_s=round(float(wall_latency_s), 4),
            queue_wait_s=timing.get('queue_wait_s'),
            generation_time_s=timing.get('generation_time_s'),
            finish_reason=timing.get('finish_reason'),
            prompt_tokens=timing.get('prompt_tokens'),
            completion_tokens=timing.get('completion_tokens'),
            sampling_preset=timing.get('sampling_preset'),
            settings_fingerprint=timing.get('settings_fingerprint'),
            error_message=result.error_message,
        )
        if result.failure_event is not None:
            check = failure_check_for(result.failure_event.failure_id)
            self._log_event(
                'plan_check',
                step=step,
                result='fail' if check in (FailureCheck.PLAN_CHECK, FailureCheck.INSERTION) else 'not_run',
                failure_codes=[str(result.failure_event.failure_id)],
                fact=(result.failure_event.evidence or {}).get('fact'),
            )
        elif result.success:
            self._log_event('plan_check', step=step, result='pass', failure_codes=[], plan=parsed)
        else:
            self._log_event('plan_check', step=step, result='not_run',
                            failure_codes=[str(FailureCode.PLANNER_CALL_FAILED)], error_message=result.error_message)

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

        # Resolve lid open/closed states. Legacy prompts list visible lids only; prompt v2
        # lists every lid of the scene (joint/pose values as a stand-in for perception).
        lid_names = [name for name in snapshot.visible_objects if name in {'box_lid', 'grill_lid', 'lid'}]
        if self.config.flags.prompt_version == 'v2':
            lid_names = list(dict.fromkeys(lid_names + self._scene_lids()))
        lid_states = {}
        for lid_name in lid_names:
            try:
                if lid_name == 'grill_lid' and self.config.flags.prompt_version == 'v2':
                    grill_open = infer_grill_lid_open(self.env)
                    if grill_open is not None:
                        lid_states[lid_name] = bool(grill_open)
                        continue
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
        if hasattr(self.context_builder, 'goal_check_prompts'):
            system_prompt, user_prompt = self.context_builder.goal_check_prompts(
                state, goal_text, list(getattr(self.executor, 'completed_primitive_actions', []) or []),
            )
            return system_prompt, user_prompt, goal_check_image
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
        # termination.mode=agent: the evaluator only scores, it never controls the loop.
        if self.config.flags.termination_mode != 'evaluator':
            return None
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
            failure_id=FailureCode.GOAL_NOT_SATISFIED,
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
                cycle.error_message = plan_result.error_message or CycleError.PLANNING_FAILED
                if plan_result.failure_event is not None:
                    cycle.failure_event = plan_result.failure_event.to_dict()
                    last_failure_event = plan_result.failure_event
                failure_reason = cycle.error_message
            self.cycles.append(cycle)
            self._set_termination(TerminationReason.EXECUTION_SKIPPED)
        else:
            while len(self.cycles) <= self.config.max_replans:
                cycle_number = len(self.cycles) + 1
                is_replan = pending_failure is not None
                if cycle_number == 1 and not is_replan and getattr(self, '_cached_preflight_plan', None):
                    plan_result, prompt_trace = self._cached_preflight_plan
                    self._cached_preflight_plan = None
                    self._print_plan_result(plan_result, is_replan, cycle_number, pending_failure)
                elif self._parallel_applicable(pending_failure):
                    plan_result, prompt_trace = self._plan_in_parallel(goal_text, pending_failure)
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
                        and pending_failure.failure_id == FailureCode.GOAL_NOT_SATISFIED
                        and (pending_failure.evidence or {}).get('error_message')
                        and 'NO_ACTIONS' in (plan_result.raw_output or '').upper()
                        and (deterministic_goal_check is None or deterministic_goal_check.goal_satisfied)
                    ):
                        if deterministic_goal_check is not None:
                            cycle.goal_check = deterministic_goal_check.to_dict()
                        self.cycles.append(cycle)
                        failure_reason = None
                        self._remaining_with_ids = []
                        self._set_termination(TerminationReason.PLANNER_RETURNED_NO_ACTIONS)
                        break
                    self._remaining_with_ids = []
                    if self.config.enable_goal_check:
                        goal_check = deterministic_goal_check or self._check_goal_completion(goal_text)
                        cycle.goal_check = goal_check.to_dict()
                        if goal_check.success and goal_check.goal_satisfied:
                            self.cycles.append(cycle)
                            failure_reason = None
                            self._set_termination(TerminationReason.GOAL_CHECK_SATISFIED)
                            break
                        if self._is_implicit_non_target_only_goal_failure(goal_check):
                            self.cycles.append(cycle)
                            failure_reason = None
                            self._set_termination(TerminationReason.GOAL_CHECK_SATISFIED)
                            break
                        goal_failure = self._goal_check_failure_event(goal_check)
                        cycle.success = False
                        cycle.failure_event = goal_failure.to_dict()
                        last_failure_event = goal_failure
                        self.cycles.append(cycle)
                        pending_failure = goal_failure
                        failure_reason = goal_failure.message
                        if len(self.cycles) > self.config.max_replans:
                            self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
                            break
                        continue
                    cycle.success = False
                    cycle.error_message = CycleError.PLANNER_RETURNED_NO_ACTIONS
                    self.cycles.append(cycle)
                    failure_reason = cycle.error_message
                    self._set_termination(TerminationReason.PLANNER_RETURNED_NO_ACTIONS)
                    break

                if not plan_result.success:
                    cycle.success = False
                    cycle.error_message = plan_result.error_message or CycleError.PLANNING_FAILED
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
                    if self._is_infrastructure(plan_result):
                        self._set_termination(TerminationReason.INFRASTRUCTURE)
                    self._set_termination(
                        TerminationReason.PLANNING_FAILED if plan_result.failure_event is None
                        else TerminationReason.NON_REPLANNABLE_FAILURE
                    )
                    break

                plan_with_ids = self._assign_plan_ids(plan_result.actions)
                execution = self.executor.execute_actions(
                    plan_result.actions,
                    self.failure_checker,
                    pre_action_checks_enabled=self.config.pre_action_checks_enabled,
                    post_action_checks_enabled=self.config.post_action_checks_enabled,
                )

                cycle.completed_actions = list(getattr(self.executor, 'completed_primitive_actions', []))
                cycle.remaining_actions = list(execution.remaining_actions)
                self._record_execution_progress(plan_with_ids, execution.remaining_actions)
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
                            self._set_termination(TerminationReason.GOAL_CHECK_SATISFIED)
                            break
                        if self._is_implicit_non_target_only_goal_failure(goal_check):
                            failure_reason = None
                            self._set_termination(TerminationReason.GOAL_CHECK_SATISFIED)
                            break
                        goal_failure = self._goal_check_failure_event(goal_check)
                        cycle.success = False
                        cycle.failure_event = goal_failure.to_dict()
                        last_failure_event = goal_failure
                        pending_failure = goal_failure
                        failure_reason = goal_failure.message
                        if len(self.cycles) > self.config.max_replans:
                            self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
                            break
                        continue

                    failure_reason = None
                    self._set_termination(TerminationReason.PLAN_COMPLETED)
                    break

                pending_failure = execution.last_failure_event
                failure_reason = execution.error_message or (pending_failure.message if pending_failure else 'execution_failed')
                if pending_failure is not None and pending_failure.failure_id in INFRASTRUCTURE_FAILURE_CODES:
                    # A simulator error during an action (Phase 7c): excluded from scoring and rerun.
                    self._set_termination(TerminationReason.INFRASTRUCTURE)
                    break
                if pending_failure is None or not pending_failure.should_replan:
                    self._set_termination(TerminationReason.NON_REPLANNABLE_FAILURE)
                    break
                if len(self.cycles) > self.config.max_replans:
                    self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)
                    break
            self._set_termination(TerminationReason.REPLAN_BUDGET_EXHAUSTED)

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
            'initial_ground_truth': getattr(self, 'initial_ground_truth', None),
            'final_ground_truth': self._final_variant_ground_truth(),
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
    parser.add_argument("--remote", action="store_true", help="Use a remote planner server (default API: vLLM, OpenAI-compatible)")
    parser.add_argument("--remote-api", choices=["openai", "legacy"], default="openai", help="openai: vLLM server; legacy: llm_pipeline/server.py")
    parser.add_argument("--remote-url", default=os.environ.get("VLLM_SERVER_URL", os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:8000")), help="Remote planner server URL")
    parser.add_argument("--replan-mode", choices=["on", "off"], default="on", help="Use full execution+replanning or first-plan-only mode")
    parser.add_argument("--task-family", choices=["kitchen", "grill"], default="", help="Task family override when --variant is not set")
    parser.add_argument("--scene-path", default="", help="Scene path override")
    parser.add_argument("--no-live-masks", action="store_true", help="Disable the separate live segmentation window")
    parser.add_argument("--scene-state-trace", action="store_true", help="Print scene-state snapshots around execution checks")
    parser.add_argument("--no-goal-check", action="store_true", help="Disable LLM goal-completion verification after each completed plan")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    # The same refusals as llm_pipeline.trial_runner (Phase 7c): a clean tree and a planner
    # whose settings are reported and match the pinned model. This CLI writes no trial log;
    # use llm_pipeline.trial_runner for trials.
    import sys as _sys
    from llm_pipeline.trial_runner import (
        _pre_run_planner_settings, expected_model_revision, git_commit_info, real_model_refusals,
    )
    _requested = args.model if (args.remote and args.remote_api == "openai") else None
    _problems = real_model_refusals(
        git_commit_info(), _pre_run_planner_settings(args.remote, args.remote_url, args.remote_api, args.model),
        requested_model=_requested, expected_revision=expected_model_revision(args.model) if _requested else None)
    if _problems:
        print("[ENTRY] refusing to run: " + "; ".join(_problems), file=_sys.stderr)
        _sys.exit(2)

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
        enable_replanning=args.replan_mode != "off",
        headless=headless,
        enable_vision=args.vision,
        model_type=args.model_type or ("vlm" if args.vision else "llm"),
        quantization=args.quantization,
        text_only=not args.vision,
        prompt_mode=PROMPT_MODE_VLM_MULTIMODAL if args.vision else PROMPT_MODE_SEGMENTATION_TEXT,
        use_remote_planner=args.remote,
        remote_planner_url=args.remote_url,
        remote_planner_api=args.remote_api,
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
