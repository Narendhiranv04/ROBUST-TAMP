import numpy as np

from llm_pipeline.executor import PrimitiveExecutionOutcome
from llm_pipeline.executable_symbols import RuntimeSymbolRegistry
from llm_pipeline.geometric_builder import GeometricContextBuilder
from llm_pipeline.grill_geometry import derive_grill_semantic_facts
from llm_pipeline.flags import PipelineFlags
from llm_pipeline.pipeline import LLMPipelineConfig, LLMOnlyReplanningPipeline
from llm_pipeline.planner import MockTextLLMPlanner, TextLLMPlanner
from llm_pipeline.strict_parser import StrictActionParser, StrictParseError
from llm_pipeline.pipeline_types import (
    FailureEvent,
    FailureLayer,
    FailureSource,
    FailureStage,
    DirectAction,
    GoalCheckResult,
    PlanResult,
    SceneState,
    SegmentationObjectEvidence,
    SegmentationSnapshot,
)


# Tests of the previous system's prompts and evaluator-driven stop condition.
LEGACY_FLAGS = PipelineFlags(prompt_version='legacy', termination_mode='evaluator')


def test_vlm_model_type_can_be_text_only() -> None:
    config = LLMPipelineConfig(
        model_alias='qwen3-vl-8b-thinking',
        model_type='vlm',
        enable_vision=False,
    )

    assert config.resolve_model_name() == ('qwen3-vl-8b-thinking', 'Qwen/Qwen3-VL-8B-Thinking')
    assert config.effective_model_type == 'vlm'


class QueuePlanner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.model_alias = 'mock-llm'
        self.model_name = 'mock-llm'
        self.loaded = True
        self.parser = StrictActionParser()
        self.requests = []

    def load_model(self):
        self.loaded = True
        return True

    def generate_plan(self, system_prompt, user_prompt, icl_mode, max_new_tokens=256, temperature=0.0, held_object=None):
        self.requests.append(
            {
                'system_prompt': system_prompt,
                'user_prompt': user_prompt,
                'icl_mode': icl_mode,
                'held_object': held_object,
            }
        )
        raw_output = self.outputs.pop(0)
        try:
            actions = self.parser.parse(raw_output, held_object=held_object)
            return PlanResult(
                success=True,
                actions=actions,
                raw_output=raw_output,
                inference_time=0.01,
            )
        except StrictParseError as exc:
            return PlanResult(
                success=False,
                actions=[],
                raw_output=raw_output,
                inference_time=0.01,
                error_message=str(exc),
                failure_event=FailureEvent(
                    failure_id=exc.failure_id,
                    stage=FailureStage.BEFORE_EXECUTION,
                    source=FailureSource.VALIDATION,
                    action=None,
                    evidence={'line_number': exc.line_number, 'raw_output': raw_output},
                    should_replan=False,
                    message=str(exc),
                ),
            )

    def get_debug_info(self):
        return {
            'model_alias': self.model_alias,
            'model_name': self.model_name,
            'loaded': self.loaded,
            'last_request': self.requests[-1] if self.requests else {},
        }


class GoalCheckingQueuePlanner(QueuePlanner):
    def __init__(self, outputs, goal_check_outputs):
        super().__init__(outputs)
        self.goal_check_outputs = list(goal_check_outputs)
        self.goal_check_requests = []

    def check_goal_completion(
        self,
        system_prompt,
        user_prompt,
        icl_mode,
        max_new_tokens=64,
        temperature=0.0,
        held_object=None,
    ):
        del max_new_tokens, temperature
        self.goal_check_requests.append(
            {
                'system_prompt': system_prompt,
                'user_prompt': user_prompt,
                'icl_mode': icl_mode,
                'held_object': held_object,
            }
        )
        raw_output = self.goal_check_outputs.pop(0)
        if raw_output.startswith('GOAL_COMPLETE'):
            return GoalCheckResult(
                success=True,
                goal_satisfied=True,
                raw_output=raw_output,
                inference_time=0.01,
            )
        return GoalCheckResult(
            success=True,
            goal_satisfied=False,
            raw_output=raw_output,
            inference_time=0.01,
            reason=raw_output.split(':', 1)[1].strip(),
        )


class GoalCheckParseFailurePlanner(QueuePlanner):
    def check_goal_completion(
        self,
        system_prompt,
        user_prompt,
        icl_mode,
        max_new_tokens=64,
        temperature=0.0,
        held_object=None,
    ):
        del system_prompt, user_prompt, icl_mode, max_new_tokens, temperature, held_object
        return GoalCheckResult(
            success=False,
            goal_satisfied=False,
            raw_output='I think it is done, but I forgot the required token.',
            inference_time=0.01,
            error_message='Goal check output must include GOAL_COMPLETE or GOAL_INCOMPLETE.',
        )


class BundleCapturingPlanner:
    def __init__(self, action_batches=None):
        self.model_alias = 'mock-vlm'
        self.model_name = 'mock-vlm'
        self.loaded = True
        self.parser = StrictActionParser()
        self.bundles = []
        self.action_batches = list(action_batches or [[DirectAction('open', ('box_lid',))]])

    def load_model(self):
        self.loaded = True
        return True

    def plan(self, bundle):
        self.bundles.append(bundle)
        actions = self.action_batches.pop(0) if self.action_batches else []
        return PlanResult(
            success=True,
            actions=actions,
            raw_output='\n'.join(str(action) for action in actions) or 'NO_ACTIONS',
            inference_time=0.01,
        )

    def get_debug_info(self):
        bundle = self.bundles[-1] if self.bundles else None
        images = getattr(bundle, 'images', None) or []
        return {
            'model_alias': self.model_alias,
            'model_name': self.model_name,
            'model_type': 'vlm',
            'loaded': self.loaded,
            'last_request': {
                'use_vision': True,
                'image_present': bool(images),
                'text_only': False,
            },
        }


class VisionGoalCheckPlanner:
    def __init__(self):
        self.model_alias = 'mock-vlm'
        self.model_name = 'mock-vlm'
        self.loaded = True
        self.goal_check_images = []

    def load_model(self):
        self.loaded = True
        return True

    def check_goal_completion(
        self,
        system_prompt,
        user_prompt,
        icl_mode,
        max_new_tokens=64,
        temperature=0.0,
        held_object=None,
        image=None,
    ):
        del system_prompt, user_prompt, icl_mode, max_new_tokens, temperature, held_object
        self.goal_check_images.append(image)
        return GoalCheckResult(
            success=True,
            goal_satisfied=True,
            raw_output='GOAL_COMPLETE',
            inference_time=0.01,
        )


class FakeSegmentationAdapter:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.refresh_calls = []
        self.capture_calls = []
        self.live_updates = 0
        self.action_sequence_calls = []
        self.reset_calls = 0
        self.shutdown_called = False
        self.symbol_registry = None

    def set_env(self, env):
        self.env = env

    def set_symbol_registry(self, symbol_registry):
        self.symbol_registry = symbol_registry

    def reset_tracking(self):
        self.reset_calls += 1

    def refresh_visibility(self, event=''):
        self.refresh_calls.append(event)
        return {
            'visible_objects': list(self.snapshot.visible_objects),
            'newly_visible_objects': list(self.snapshot.newly_visible_objects),
            'visible_regions': list(self.snapshot.visible_regions),
        }

    def capture_snapshot(self, event=''):
        self.capture_calls.append(event)
        return self.snapshot

    def update_live_segmentation_view(self):
        self.live_updates += 1
        return set(self.snapshot.visible_objects)

    def set_live_action_sequence(self, actions, current_action_index=None, current_action_label=None):
        self.action_sequence_calls.append(
            {
                'actions': [str(action) for action in actions],
                'current_action_index': current_action_index,
                'current_action_label': current_action_label,
            }
        )

    def shutdown(self):
        self.shutdown_called = True


class FakeFailureChecker:
    def __init__(self, adapter, snapshot):
        self.adapter = adapter
        self.snapshot = snapshot
        self.events = []
        self.render_calls = []
        self.env = None

    def capture_snapshot(self, event=''):
        self.events.append(event)
        return self.snapshot

    def render_failure_context(self, failure_event: FailureEvent, completed_actions=None, remaining_actions=None) -> str:
        self.render_calls.append(
            {
                'failure_event': failure_event,
                'completed_actions': list(completed_actions or []),
                'remaining_actions': list(remaining_actions or []),
            }
        )
        completed = ', '.join(completed_actions or []) or '(none)'
        remaining = ', '.join(remaining_actions or []) or '(none)'
        return '\n'.join(
            [
                f'failure_id={failure_event.failure_id}',
                f'action={failure_event.action}',
                f'message={failure_event.message}',
                f'completed_actions={completed}',
                f'remaining_actions={remaining}',
            ]
        )


class FakeExecutor:
    def __init__(self):
        self.completed_primitive_actions = []
        self.remaining_actions = []
        self.held_object = None
        self.last_failure_event = None
        self.calls = []
        self.step_callback = None
        self.action_start_callback = None

    def set_env(self, env):
        self.env = env

    def set_step_callback(self, callback):
        self.step_callback = callback

    def set_action_start_callback(self, callback):
        self.action_start_callback = callback

    def reset_episode(self):
        self.completed_primitive_actions = []
        self.remaining_actions = []
        self.held_object = None
        self.last_failure_event = None
        self.calls = []

    def execute_actions(self, actions, failure_checker, pre_action_checks_enabled=True, post_action_checks_enabled=True):
        del failure_checker, pre_action_checks_enabled, post_action_checks_enabled
        rendered = [str(action) for action in actions]
        self.calls.append(rendered)
        if self.action_start_callback is not None and actions:
            self.action_start_callback(actions, 0)
        if self.step_callback is not None:
            self.step_callback()

        if len(self.calls) == 1:
            pick_index = next(index for index, action in enumerate(actions) if action.action_name == 'pick')
            self.completed_primitive_actions.extend(rendered[: pick_index + 1])
            self.remaining_actions = rendered[pick_index + 1 :]
            self.held_object = 'mug2'
            failure = FailureEvent(
                failure_id='placement_failed',
                stage=FailureStage.AFTER_EXECUTION,
                source=FailureSource.SEGMENTATION,
                action=self.remaining_actions[-1],
                evidence={'target_region': 'table_staging_area'},
                message='place failed after pick',
            )
            self.last_failure_event = failure
            return PrimitiveExecutionOutcome(
                success=False,
                completed_actions=list(self.completed_primitive_actions),
                remaining_actions=list(self.remaining_actions),
                held_object=self.held_object,
                last_failure_event=failure,
                error_message=failure.message,
            )

        self.completed_primitive_actions.extend(rendered)
        self.remaining_actions = []
        self.held_object = None
        self.last_failure_event = None
        return PrimitiveExecutionOutcome(
            success=True,
            completed_actions=list(self.completed_primitive_actions),
            remaining_actions=[],
            held_object=None,
            last_failure_event=None,
            error_message=None,
        )


class PrecompletedFakeExecutor(FakeExecutor):
    def __init__(self, completed_actions):
        super().__init__()
        self._precompleted_actions = list(completed_actions)

    def reset_episode(self):
        super().reset_episode()
        self.completed_primitive_actions = list(self._precompleted_actions)


class RegionUpdatingSuccessExecutor(FakeExecutor):
    def __init__(self, snapshot):
        super().__init__()
        self.snapshot = snapshot

    def execute_actions(self, actions, failure_checker, pre_action_checks_enabled=True, post_action_checks_enabled=True):
        del failure_checker, pre_action_checks_enabled, post_action_checks_enabled
        rendered = [str(action) for action in actions]
        self.calls.append(rendered)
        if self.action_start_callback is not None and actions:
            self.action_start_callback(actions, 0)
        if self.step_callback is not None:
            self.step_callback()

        for action in actions:
            if action.action_name == 'place' and len(action.args) >= 2:
                object_name, region_name = action.args[:2]
                self.snapshot.object_region_map[object_name] = region_name
        self.completed_primitive_actions.extend(rendered)
        self.remaining_actions = []
        self.held_object = None
        self.last_failure_event = None
        return PrimitiveExecutionOutcome(
            success=True,
            completed_actions=list(self.completed_primitive_actions),
            remaining_actions=[],
            held_object=None,
            last_failure_event=None,
            error_message=None,
        )


class FakeEnv:
    class PR:
        def step(self):
            return None

        def stop(self):
            return None

        def shutdown(self):
            return None

    def __init__(self):
        self.pr = self.PR()
        self.startup_lid_hold_calls = 0

    def get_home_conf(self):
        return [0.0] * 7

    def set_robot_conf(self, conf):
        self.conf = list(conf)

    def hold_startup_lid_pose(self):
        self.startup_lid_hold_calls += 1
        return True


class FakeGrillEnv(FakeEnv):
    def __init__(self):
        super().__init__()
        self.grill_boundary = object()


class FakeCamera:
    def __init__(self, value):
        self.value = value
        self.capture_calls = 0

    def handle_explicitly(self):
        return None

    def capture_rgb(self):
        self.capture_calls += 1
        return np.full((4, 5, 3), self.value + self.capture_calls, dtype=np.uint8)


class FakeVisionEnv(FakeEnv):
    def __init__(self):
        super().__init__()
        self.cams = {
            'left': FakeCamera(10),
            'right': FakeCamera(20),
            'overhead': FakeCamera(30),
            'wrist': FakeCamera(40),
            'front': FakeCamera(50),
        }


def _snapshot() -> SegmentationSnapshot:
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=['mug2', 'box_lid'],
        newly_visible_objects=[],
        object_evidence={
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['inside_box']),
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['box_lid_top']),
        },
        gripper_evidence={},
        supported_regions=['table', 'table_staging_area', 'cupboard_shelf', 'inside_box'],
        visible_regions=['inside_box'],
        object_region_map={'mug2': 'inside_box'},
        object_region_descriptions={'mug2': 'inside the box storage target'},
    )


def _kitchen_snapshot_with_grocery_in_box() -> SegmentationSnapshot:
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=['mug2', 'mug3', 'can_of_beans', 'spam', 'box_lid'],
        newly_visible_objects=[],
        object_evidence={
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['inside_box']),
            'mug3': SegmentationObjectEvidence(name='mug3', visible=True, mask_regions=['inside_box']),
            'can_of_beans': SegmentationObjectEvidence(name='can_of_beans', visible=True, mask_regions=['inside_box']),
            'spam': SegmentationObjectEvidence(name='spam', visible=True, mask_regions=['cupboard_shelf']),
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['box_lid_top']),
        },
        gripper_evidence={},
        supported_regions=['table', 'table_staging_area', 'cupboard_shelf', 'inside_box'],
        visible_regions=['inside_box', 'cupboard_shelf'],
        object_region_map={
            'mug2': 'inside_box',
            'mug3': 'inside_box',
            'can_of_beans': 'inside_box',
            'spam': 'cupboard_shelf',
        },
        object_region_descriptions={
            'mug2': 'inside the box',
            'mug3': 'inside the box',
            'can_of_beans': 'inside the box',
            'spam': 'on lower cupboard shelf',
        },
    )


def _kitchen_snapshot_missing_required_mug() -> SegmentationSnapshot:
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=['mug2', 'can_of_beans', 'spam', 'box_lid'],
        newly_visible_objects=[],
        object_evidence={
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['inside_box']),
            'can_of_beans': SegmentationObjectEvidence(name='can_of_beans', visible=True, mask_regions=['cupboard_shelf']),
            'spam': SegmentationObjectEvidence(name='spam', visible=True, mask_regions=['cupboard_shelf']),
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['box_lid_top']),
        },
        gripper_evidence={},
        supported_regions=['table', 'table_staging_area', 'cupboard_shelf', 'inside_box'],
        visible_regions=['inside_box', 'cupboard_shelf'],
        object_region_map={
            'mug2': 'inside_box',
            'can_of_beans': 'cupboard_shelf',
            'spam': 'cupboard_shelf',
        },
        object_region_descriptions={
            'mug2': 'inside the box',
            'can_of_beans': 'on lower cupboard shelf',
            'spam': 'on lower cupboard shelf',
        },
    )


def _grill_g1_snapshot_phone_in_grill() -> SegmentationSnapshot:
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=['grill_lid', 'phone', 'chicken', 'plate'],
        newly_visible_objects=[],
        object_evidence={
            'grill_lid': SegmentationObjectEvidence(name='grill_lid', visible=True, mask_regions=['inside_grill']),
            'phone': SegmentationObjectEvidence(name='phone', visible=True, mask_regions=['inside_grill']),
            'chicken': SegmentationObjectEvidence(name='chicken', visible=True, mask_regions=['prep_area']),
            'plate': SegmentationObjectEvidence(name='plate', visible=True, mask_regions=['serving_area']),
        },
        gripper_evidence={},
        supported_regions=['table', 'prep_area', 'inside_grill', 'plate_top', 'serving_area', 'dish_rack'],
        visible_regions=['inside_grill', 'prep_area', 'serving_area'],
        object_region_map={
            'phone': 'inside_grill',
            'chicken': 'prep_area',
            'plate': 'serving_area',
        },
        object_region_descriptions={
            'phone': 'inside the grill cooking area',
            'chicken': 'in prep area',
            'plate': 'in serving area',
        },
    )


def _grill_g1_snapshot_only_phone_missing() -> SegmentationSnapshot:
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=['grill_lid', 'phone', 'chicken', 'plate'],
        newly_visible_objects=[],
        object_evidence={
            'grill_lid': SegmentationObjectEvidence(name='grill_lid', visible=True, mask_regions=['inside_grill']),
            'phone': SegmentationObjectEvidence(name='phone', visible=True, mask_regions=['inside_grill']),
            'chicken': SegmentationObjectEvidence(name='chicken', visible=True, mask_regions=['plate_top']),
            'plate': SegmentationObjectEvidence(name='plate', visible=True, mask_regions=['serving_area']),
        },
        gripper_evidence={},
        supported_regions=['table', 'prep_area', 'inside_grill', 'plate_top', 'serving_area', 'dish_rack'],
        visible_regions=['inside_grill', 'plate_top', 'serving_area'],
        object_region_map={
            'phone': 'inside_grill',
            'chicken': 'plate_top',
            'plate': 'serving_area',
        },
        object_region_descriptions={
            'phone': 'inside the grill cooking area',
            'chicken': 'on the plate top',
            'plate': 'in serving area',
        },
    )


def test_pipeline_replans_with_previous_direct_actions() -> None:
    planner = QueuePlanner([
        'pick(mug2)\nplace(mug2, table_staging_area)',
        'place(mug2, table_staging_area)\nopen(box_lid)',
    ])
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,model_alias='mock-llm', icl_mode='zero_shot', max_replans=2, live_view_update_stride=1),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('Move mug2 to table_staging_area and then open the lid.')

    assert summary['success'] is True
    assert summary['total_replans'] == 1
    assert summary['planner_invocations'] == 2
    assert summary['total_planner_time_s'] == 0.02
    assert summary['mean_planner_time_per_invocation_s'] == 0.01
    assert summary['completed_actions'] == [
        'pick(mug2)',
        'place(mug2, table_staging_area)',
        'open(box_lid)',
    ]
    assert summary['held_object'] is None

    assert 'checkpoint_type: initial_planning' in planner.requests[0]['user_prompt']
    assert 'newly_visible_objects: (none)' in planner.requests[0]['user_prompt']
    assert 'checkpoint_type: replanning' in planner.requests[1]['user_prompt']
    assert '### Completed Actions' in planner.requests[1]['user_prompt']
    assert '- pick(mug2)' in planner.requests[1]['user_prompt']
    assert '### Replanning Event' in planner.requests[1]['user_prompt']
    assert 'event_type: failure' in planner.requests[1]['user_prompt']
    assert 'failed_action: place(mug2, table_staging_area)' in planner.requests[1]['user_prompt']
    assert 'pick(mug2)' in planner.requests[1]['user_prompt']
    assert 'place failed after pick' in planner.requests[1]['user_prompt']
    assert 'You are a high-level robotic task planner' in planner.requests[0]['system_prompt']
    assert 'Do not invent hidden objects' in planner.requests[0]['system_prompt']
    assert '### Visible-Object Relational State' in planner.requests[0]['user_prompt']
    assert 'region=inside_box' in planner.requests[0]['user_prompt']
    assert 'pose=' not in planner.requests[0]['user_prompt']
    assert '### Executable Interface' in planner.requests[0]['user_prompt']
    assert 'Choose the task-level action order needed to satisfy the goal from the current checkpoint.' in planner.requests[0]['user_prompt']
    assert 'Every pick, place, open, or close must be immediately preceded by a matching move(target).' not in planner.requests[0]['user_prompt']
    assert 'visible_objects=' not in planner.requests[0]['user_prompt']
    assert segmentation_adapter.refresh_calls[:2] == ['initial', 'initial']
    assert segmentation_adapter.action_sequence_calls[0]['actions'] == []
    assert segmentation_adapter.live_updates >= 1


def test_parser_failure_replan_prompt_includes_structural_repair_rule() -> None:
    builder = GeometricContextBuilder()
    builder.symbol_registry = RuntimeSymbolRegistry(
        actions=('pick', 'place', 'open', 'close'),
        objects=('steak1', 'plate', 'grill_lid'),
        regions=('prep_area', 'inside_grill', 'plate_top', 'serving_area'),
    )
    state = SceneState(
        frame_index=2,
        visible_objects=['steak1', 'plate', 'grill_lid'],
        valid_regions=['prep_area', 'inside_grill', 'plate_top', 'serving_area'],
        pddl_state=['raw(steak1)', 'grill_lid_open'],
        gripper_state={'status': 'empty'},
        object_region_map={'steak1': 'prep_area', 'plate': 'dish_rack'},
        object_region_descriptions={'steak1': 'in prep area', 'plate': 'at dish rack'},
        lid_states={'grill_lid': True},
    )
    failure_event = FailureEvent(
        failure_id='invalid_action_sequence',
        stage=FailureStage.BEFORE_EXECUTION,
        source=FailureSource.VALIDATION,
        action=None,
        evidence={'line_number': 2},
        should_replan=True,
        message="Line 2: Cannot place 'steak1' without first picking it",
        failure_layer=FailureLayer.LAYER_1,
    )

    bundle = builder.build_bundle(
        state=state,
        goal_text='Cook all raw meat using the grill and serve all cooked meat on the plate.',
        failure_event=failure_event,
        previous_actions=[],
        icl_mode='zero_shot',
    )

    assert 'checkpoint_type: replanning' in bundle.user_prompt
    assert "event_message: Line 2: Cannot place 'steak1' without first picking it" in bundle.user_prompt
    assert 'repair_constraint: the previous output was not executable' in bundle.user_prompt
    assert 'repair_rule: every place(object, region) must be immediately preceded by pick(object)' in bundle.user_prompt
    assert 'A place(object, region) action is executable only immediately after pick(object)' in bundle.user_prompt


def test_pipeline_can_print_raw_llm_output_for_debugging(capsys) -> None:
    planner = QueuePlanner(['pick(mug2)\nplace(mug2, table_staging_area)'])
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            model_alias='mock-llm',
            icl_mode='zero_shot',
            max_replans=0,
            show_llm_output=True,
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    pipeline.run('Move mug2 to table_staging_area.')
    output = capsys.readouterr().out

    assert '[LLM] Raw output text:' in output
    assert 'pick(mug2)' in output
    assert 'place(mug2, table_staging_area)' in output


def test_plan_bundle_carries_generation_settings_for_plan_interface() -> None:
    planner = BundleCapturingPlanner()
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            model_alias='mock-vlm',
            icl_mode='zero_shot',
            planner_max_new_tokens=777,
            planner_temperature=0.2,
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    pipeline.plan_once('Open the lid.', failure_event=None, silent=True)

    metadata = planner.bundles[0].metadata
    assert metadata['max_new_tokens'] == 777
    assert metadata['temperature'] == 0.2
    assert 'held_object' in metadata


def test_vlm_goal_check_uses_image_from_same_scene_capture() -> None:
    planner = VisionGoalCheckPlanner()
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    env = FakeVisionEnv()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            model_alias='mock-vlm',
            icl_mode='zero_shot',
            enable_vision=True,
            model_type='vlm',
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=env) is True
    result = pipeline._check_goal_completion('Move mug2 to the table staging area.')

    assert result.goal_satisfied is True
    assert planner.goal_check_images
    assert planner.goal_check_images[0].shape == (8, 15, 3)
    assert all(camera.capture_calls == 1 for camera in env.cams.values())


def test_pipeline_replans_when_goal_check_reports_incomplete() -> None:
    planner = GoalCheckingQueuePlanner(
        [
            'pick(mug2)\nplace(mug2, table_staging_area)',
            'place(mug2, table_staging_area)',
            'open(box_lid)',
        ],
        [
            'GOAL_INCOMPLETE: box_lid still needs to be opened',
            'GOAL_COMPLETE',
        ],
    )
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,model_alias='mock-llm', icl_mode='zero_shot', max_replans=3),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('Move mug2 to table_staging_area and open the lid.')

    assert summary['success'] is True
    assert summary['goal_check_enabled'] is True
    assert summary['last_goal_check']['goal_satisfied'] is True
    assert len(planner.goal_check_requests) == 2
    assert 'GOAL_COMPLETE' in planner.goal_check_requests[0]['system_prompt']
    assert 'COMPLETED ACTIONS:' in planner.goal_check_requests[0]['user_prompt']
    assert summary['cycles'][1]['failure_event']['failure_id'] == 'goal_not_satisfied'
    assert summary['cycles'][1]['goal_check']['reason'] == 'box_lid still needs to be opened'
    assert 'Goal check failed' in planner.requests[2]['user_prompt']


def test_pipeline_replans_when_grill_deterministic_goal_is_incomplete() -> None:
    planner = BundleCapturingPlanner(
        action_batches=[
            [
                DirectAction('pick', ('chicken',)),
                DirectAction('place', ('chicken', 'plate_top')),
            ],
            [
                DirectAction('pick', ('phone',)),
                DirectAction('place', ('phone', 'table')),
                DirectAction('pick', ('chicken',)),
                DirectAction('place', ('chicken', 'inside_grill')),
                DirectAction('close', ('grill_lid',)),
                DirectAction('open', ('grill_lid',)),
                DirectAction('pick', ('chicken',)),
                DirectAction('place', ('chicken', 'plate_top')),
            ],
        ]
    )
    snapshot = _grill_g1_snapshot_phone_in_grill()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = RegionUpdatingSuccessExecutor(snapshot)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,
            model_alias='mock-vlm',
            icl_mode='zero_shot',
            max_replans=2,
            task_family='grill',
            scene_path='grill_task2/grill.variation1.ttt',
            variant_id='G1',
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeGrillEnv()) is True
    summary = pipeline.run('Cook all raw meat using the grill and serve all cooked meat on the plate in the serving area.')

    assert summary['success'] is True
    assert summary['total_replans'] == 1
    assert summary['cycles'][0]['failure_event']['failure_id'] == 'goal_not_satisfied'
    assert summary['cycles'][0]['failure_event']['source'] == 'goal_check'
    assert 'the goal is not fully satisfied' in summary['cycles'][0]['failure_event']['message']
    assert 'phone is in inside_grill, expected table' in summary['cycles'][0]['failure_event']['evidence']['reason']
    assert 'chicken missing ordered cooking sequence' in summary['cycles'][0]['failure_event']['evidence']['reason']
    replan_prompt = planner.bundles[1].user_prompt
    assert 'checkpoint_type: replanning' in replan_prompt
    assert 'event_id: goal_not_satisfied' in replan_prompt
    assert 'event_source: goal_check' in replan_prompt
    assert 'failed_action: (none)' in replan_prompt
    assert '- pick(chicken)' in replan_prompt
    assert '- place(chicken, plate_top)' in replan_prompt
    assert 'the goal is not fully satisfied' in replan_prompt
    assert 'expected table' not in replan_prompt
    assert 'missing ordered cooking sequence' not in replan_prompt


def test_pipeline_without_goal_check_stops_after_grill_execution_even_if_goal_incomplete() -> None:
    planner = BundleCapturingPlanner(
        action_batches=[
            [
                DirectAction('pick', ('chicken',)),
                DirectAction('place', ('chicken', 'plate_top')),
            ],
        ]
    )
    snapshot = _grill_g1_snapshot_phone_in_grill()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = RegionUpdatingSuccessExecutor(snapshot)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            model_alias='mock-vlm',
            icl_mode='zero_shot',
            max_replans=2,
            enable_goal_check=False,
            task_family='grill',
            scene_path='grill_task2/grill.variation1.ttt',
            variant_id='G1',
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeGrillEnv()) is True
    summary = pipeline.run('Cook all raw meat using the grill and serve all cooked meat on the plate in the serving area.')

    assert summary['success'] is True
    assert summary['goal_check_enabled'] is False
    assert summary['total_replans'] == 0
    assert summary['last_failure_event'] is None
    assert len(planner.bundles) == 1


def test_grill_phone_only_goal_mismatch_does_not_trigger_goal_check_replan() -> None:
    planner = BundleCapturingPlanner(action_batches=[[]])
    snapshot = _grill_g1_snapshot_only_phone_missing()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = PrecompletedFakeExecutor(
        [
            'open(grill_lid)',
            'pick(chicken)',
            'place(chicken, inside_grill)',
            'close(grill_lid)',
            'open(grill_lid)',
            'pick(plate)',
            'place(plate, serving_area)',
            'pick(chicken)',
            'place(chicken, plate_top)',
        ]
    )
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,
            model_alias='mock-vlm',
            icl_mode='zero_shot',
            max_replans=2,
            task_family='grill',
            scene_path='grill_task2/grill.variation1.ttt',
            variant_id='G1',
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeGrillEnv()) is True
    summary = pipeline.run('Cook all raw meat using the grill and serve all cooked meat on the plate in the serving area.')

    assert summary['success'] is True
    assert summary['total_replans'] == 0
    assert summary['last_failure_event'] is None
    assert summary['last_goal_check']['goal_satisfied'] is False
    assert summary['last_goal_check']['reason'] == 'phone is in inside_grill, expected table'
    assert len(planner.bundles) == 1


def test_grill_goal_check_respects_replan_budget() -> None:
    planner = BundleCapturingPlanner(
        action_batches=[
            [
                DirectAction('pick', ('chicken',)),
                DirectAction('place', ('chicken', 'plate_top')),
            ],
        ]
    )
    snapshot = _grill_g1_snapshot_phone_in_grill()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = RegionUpdatingSuccessExecutor(snapshot)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,
            model_alias='mock-vlm',
            icl_mode='zero_shot',
            max_replans=0,
            task_family='grill',
            scene_path='grill_task2/grill.variation1.ttt',
            variant_id='G1',
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeGrillEnv()) is True
    summary = pipeline.run('Cook all raw meat using the grill and serve all cooked meat on the plate in the serving area.')

    assert summary['success'] is False
    assert summary['total_replans'] == 0
    assert summary['last_failure_event']['failure_id'] == 'goal_not_satisfied'
    assert len(planner.bundles) == 1


def test_pipeline_allows_no_actions_when_goal_already_satisfied() -> None:
    planner = GoalCheckingQueuePlanner(
        ['NO_ACTIONS'],
        ['GOAL_COMPLETE'],
    )
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(model_alias='mock-llm', icl_mode='zero_shot', max_replans=1),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('Move mug2 to table_staging_area and open the lid.')

    assert summary['success'] is True
    assert summary['completed_actions'] == []
    assert summary['last_goal_check']['goal_satisfied'] is True
    assert executor.calls == []


def test_pipeline_stops_when_no_actions_follows_goal_check_format_failure() -> None:
    planner = GoalCheckParseFailurePlanner([
        'pick(mug2)\nplace(mug2, table_staging_area)',
        'place(mug2, table_staging_area)',
        'NO_ACTIONS',
    ])
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(model_alias='mock-llm', icl_mode='zero_shot', max_replans=3),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('Move mug2 to table_staging_area.')

    assert summary['success'] is True
    assert summary['failure_reason'] is None
    assert summary['total_cycles'] == 3
    assert summary['cycles'][1]['failure_event']['failure_id'] == 'goal_not_satisfied'
    assert summary['cycles'][2]['planned_actions'] == []


def test_no_actions_does_not_succeed_when_scene_state_goal_is_incomplete() -> None:
    planner = QueuePlanner(['NO_ACTIONS'])
    snapshot = _kitchen_snapshot_with_grocery_in_box()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,model_alias='mock-llm', icl_mode='zero_shot', max_replans=0, variant_id='K1'),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box')

    assert summary['success'] is False
    assert summary['last_goal_check']['goal_satisfied'] is False
    assert 'can_of_beans is in inside_box, expected cupboard_shelf' in summary['last_goal_check']['reason']
    assert summary['last_failure_event']['failure_id'] == 'goal_not_satisfied'


def test_no_actions_does_not_succeed_when_required_k1_object_is_missing() -> None:
    planner = QueuePlanner(['NO_ACTIONS'])
    snapshot = _kitchen_snapshot_missing_required_mug()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,
            model_alias='mock-llm',
            icl_mode='zero_shot',
            max_replans=0,
            scene_path='task1_variation1.ttt',
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box')

    assert summary['success'] is False
    assert summary['last_goal_check']['goal_satisfied'] is False
    assert 'mug3 is in unknown, expected inside_box' in summary['last_goal_check']['reason']


def test_goal_check_parser_accepts_token_after_reasoning() -> None:
    planner = TextLLMPlanner(model_name='mock-llm', model_alias='mock-llm')
    result = planner._parse_goal_check_output(
        'The objects appear to be in the correct regions.\n'
        '</think>\n\n'
        'GOAL_COMPLETE'
    )

    assert result.success is True
    assert result.goal_satisfied is True


def test_text_planner_parse_failure_requests_replan() -> None:
    planner = TextLLMPlanner(model_name='mock-llm', model_alias='mock-llm')
    failure = planner._build_parse_failure(
        StrictParseError("Unknown or unpickable object 'plate'", line_number=1),
        'pick(plate)',
    )

    assert failure.should_replan is True
    assert failure.failure_id == 'unknown_action_token'


def test_text_planner_prompt_text_does_not_prefill_planning_by_default() -> None:
    class FakeTokenizer:
        def apply_chat_template(self, messages, **kwargs):
            del messages, kwargs
            return '<assistant>'

    planner = TextLLMPlanner(model_name='mock-llm', model_alias='mock-llm')
    planner.tokenizer = FakeTokenizer()

    plan_prompt = planner._build_prompt_text('system', 'user')
    prefixed_prompt = planner._build_prompt_text('system', 'user', assistant_prefix='CHECK 1: ')

    assert plan_prompt == '<assistant>'
    assert prefixed_prompt.endswith('CHECK 1: ')


def test_initialize_holds_startup_lid_pose_during_settle() -> None:
    planner = QueuePlanner(['open(box_lid)'])
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    env = FakeEnv()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(model_alias='mock-llm', icl_mode='zero_shot'),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=FakeFailureChecker(segmentation_adapter, snapshot),
        executor=FakeExecutor(),
    )

    assert pipeline.initialize(env=env) is True
    assert env.startup_lid_hold_calls == 60


def test_pipeline_preflight_reports_no_image_input() -> None:
    planner = QueuePlanner(['open(box_lid)'])
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,model_alias='mock-llm', icl_mode='few_shot_shared_1'),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=FakeFailureChecker(segmentation_adapter, snapshot),
        executor=FakeExecutor(),
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    preflight = pipeline.preflight('Open the lid.')

    assert preflight['loaded'] is True
    assert preflight['image_present'] is False
    assert preflight['prompt_contract_ok'] is True
    assert preflight['dry_run_failure_event'] is None
    assert 'image' not in ''.join(preflight['prompt_trace']['bundle'].keys())


def test_vlm_preflight_uses_state_text_plus_redacted_composite_image() -> None:
    planner = BundleCapturingPlanner()
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,
            model_alias='mock-vlm',
            model_type='vlm',
            enable_vision=True,
            text_only=False,
            icl_mode='zero_shot',
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=FakeFailureChecker(segmentation_adapter, snapshot),
        executor=FakeExecutor(),
    )

    env = FakeVisionEnv()
    assert pipeline.initialize(env=env) is True
    preflight = pipeline.preflight('Open the lid.')

    assert preflight['model_type'] == 'vlm'
    assert preflight['text_only'] is False
    assert preflight['use_vision'] is True
    assert preflight['image_present'] is True
    assert preflight['prompt_contract_ok'] is True
    assert preflight['image_metadata']['camera_names'] == ['left', 'right', 'overhead', 'wrist', 'front']
    assert preflight['image_metadata']['image_shapes'] == [[8, 15, 3]]

    bundle = planner.bundles[-1]
    assert bundle.images is not None
    assert bundle.images[0].shape == (8, 15, 3)
    assert 'checkpoint_type: initial_planning' in bundle.user_prompt
    assert '### Valid Target Regions' in bundle.user_prompt
    assert '### Visible-Object Relational State' in bundle.user_prompt
    assert '### Articulation State' in bundle.user_prompt
    assert '### Access Constraints' in bundle.user_prompt
    assert '### Executable Interface' in bundle.user_prompt
    assert 'pose=' not in bundle.user_prompt

    trace_bundle = preflight['prompt_trace']['bundle']
    assert 'images' not in trace_bundle
    assert trace_bundle['image_metadata']['image_present'] is True


def test_vlm_replanning_sends_fresh_image_with_failure_context() -> None:
    planner = BundleCapturingPlanner(
        action_batches=[
            [
                DirectAction('pick', ('mug2',)),
                DirectAction('place', ('mug2', 'table_staging_area')),
            ],
            [
                DirectAction('place', ('mug2', 'table_staging_area')),
                DirectAction('open', ('box_lid',)),
            ],
        ]
    )
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            flags=LEGACY_FLAGS,
            model_alias='mock-vlm',
            model_type='vlm',
            enable_vision=True,
            text_only=False,
            icl_mode='zero_shot',
            max_replans=2,
            enable_goal_check=False,
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=FakeFailureChecker(segmentation_adapter, snapshot),
        executor=FakeExecutor(),
    )

    env = FakeVisionEnv()
    assert pipeline.initialize(env=env) is True
    summary = pipeline.run('Move mug2 to table_staging_area and open the lid.')

    assert summary['success'] is True
    assert summary['model_type'] == 'vlm'
    assert len(planner.bundles) == 2
    first_image = planner.bundles[0].images[0]
    replan_image = planner.bundles[1].images[0]
    assert first_image.shape == replan_image.shape == (8, 15, 3)
    assert not np.array_equal(first_image, replan_image)
    assert 'checkpoint_type: replanning' in planner.bundles[1].user_prompt
    assert '### Replanning Event' in planner.bundles[1].user_prompt
    assert 'event_type: failure' in planner.bundles[1].user_prompt
    assert '### Completed Actions' in planner.bundles[1].user_prompt
    assert '- pick(mug2)' in planner.bundles[1].user_prompt
    assert env.cams['left'].capture_calls >= 2


def test_geometric_prompt_renders_grill_semantics_without_phone_meat_fact() -> None:
    object_region_map = {
        'phone': 'inside_grill',
        'chicken': 'inside_grill',
        'plate': 'serving_area',
    }
    builder = GeometricContextBuilder()
    builder.set_symbol_registry(
        RuntimeSymbolRegistry(
            actions=('pick', 'place', 'open', 'close'),
            objects=('grill_lid', 'phone', 'chicken', 'plate'),
            regions=('table', 'inside_grill', 'plate_top', 'serving_area'),
        )
    )
    state = SceneState(
        frame_index=1,
        visible_objects=['grill_lid', 'phone', 'chicken', 'plate'],
        valid_regions=['inside_grill', 'table', 'plate_top', 'serving_area'],
        pddl_state=derive_grill_semantic_facts(object_region_map, lid_open=False),
        object_region_map=object_region_map,
        object_region_descriptions={
            'phone': 'inside the grill cooking area',
            'chicken': 'inside the grill cooking area',
            'plate': 'in the serving area',
        },
        lid_states={'grill_lid': False},
        gripper_state={'status': 'empty', 'holding': None},
    )

    bundle = builder.build_bundle(
        state=state,
        goal_text='Cook all raw meat using the grill and serve all cooked meat on the plate in the serving area.',
        icl_mode='zero_shot',
    )

    assert '### Domain Semantic State' in bundle.user_prompt
    assert '- grill_lid_closed' in bundle.user_prompt
    assert '- inside_grill(chicken)' in bundle.user_prompt
    assert '- cooked(chicken)' in bundle.user_prompt
    assert '- chicken: region=inside_grill, cook_status=cooked' in bundle.user_prompt
    assert 'inside_grill(phone)' not in bundle.user_prompt
    assert '- phone: region=inside_grill' in bundle.user_prompt
    assert '- table: table surface' in bundle.user_prompt
    assert 'keep object names unchanged; use raw(object) and cooked(object) facts' in bundle.user_prompt
    assert 'such as chicken, steak, or steak1' in bundle.user_prompt
    assert 'Multiple raw meats can be cooked together' in bundle.user_prompt
    assert 'placing all of them inside_grill before one close(grill_lid) and one open(grill_lid)' in bundle.user_prompt
    assert 'Cooking status and serving location are separate' in bundle.user_prompt
    assert 'DO NOT place objects here' not in bundle.user_prompt
    assert 'pose=' not in bundle.user_prompt


def test_few_shot_system_prompt_includes_shared_behavior_examples() -> None:
    builder = GeometricContextBuilder()
    state = SceneState(
        frame_index=1,
        visible_objects=['box_lid', 'mug1'],
        valid_regions=['table_staging_area', 'inside_box'],
        object_region_map={'mug1': 'box_lid_top'},
        object_region_descriptions={'mug1': 'on top of the box lid'},
        lid_states={'box_lid': False},
        gripper_state={'status': 'empty', 'holding': None},
    )

    bundle = builder.build_bundle(
        state=state,
        goal_text='Open the box and put the mug inside.',
        icl_mode='few_shot_shared_1',
    )

    assert 'SHARED FEW-SHOT EXEMPLAR' in bundle.system_prompt
    assert 'EXAMPLE 1: correct visible-only object planning' in bundle.system_prompt
    assert 'Do not invent or use hidden objects.' in bundle.system_prompt
    assert 'EXAMPLE 3: correct clearing before opening an obstructed lid' in bundle.system_prompt
    assert 'EXAMPLE 4: correct replanning after discovery' in bundle.system_prompt
    assert 'EXAMPLE 5: correct implicit handling of a visible non-target object' in bundle.system_prompt
    assert 'EXAMPLE 6: correct batch processing and serving' in bundle.system_prompt
    assert 'pick(stray_tool)' in bundle.system_prompt


def test_pipeline_reports_validation_failure_before_execution() -> None:
    planner = MockTextLLMPlanner(scripted_output='1. pick(mug_box)')
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(model_alias='mock-llm', icl_mode='zero_shot', max_replans=0),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=FakeFailureChecker(segmentation_adapter, snapshot),
        executor=FakeExecutor(),
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('Move mug2 to table_staging_area.')

    assert summary['success'] is False
    assert summary['last_failure_event']['failure_id'] == 'unknown_action_token'
    assert summary['last_failure_event']['stage'] == 'before_execution'
    assert summary['last_failure_event']['source'] == 'validation'


def test_pipeline_plan_only_mode_skips_execution_and_failure_checks() -> None:
    planner = QueuePlanner(['pick(mug2)\nplace(mug2, table_staging_area)'])
    snapshot = _snapshot()
    segmentation_adapter = FakeSegmentationAdapter(snapshot)
    failure_checker = FakeFailureChecker(segmentation_adapter, snapshot)
    executor = FakeExecutor()
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(
            model_alias='mock-llm',
            icl_mode='zero_shot',
            max_replans=2,
            enable_replanning=False,
            pre_action_checks_enabled=False,
            post_action_checks_enabled=False,
            live_view_update_stride=1,
        ),
        planner=planner,
        segmentation_adapter=segmentation_adapter,
        failure_checker=failure_checker,
        executor=executor,
    )

    assert pipeline.initialize(env=FakeEnv()) is True
    summary = pipeline.run('Move mug2 to table_staging_area.')

    assert summary['success'] is True
    assert summary['replan_mode'] == 'off'
    assert summary['replanning_enabled'] is False
    assert summary['execution_skipped'] is True
    assert summary['pre_action_checks_enabled'] is False
    assert summary['post_action_checks_enabled'] is False
    assert summary['planned_actions'] == [
        'pick(mug2)',
        'place(mug2, table_staging_area)',
    ]
    assert summary['completed_actions'] == []
    assert summary['remaining_actions'] == [
        'pick(mug2)',
        'place(mug2, table_staging_area)',
    ]
    assert summary['total_cycles'] == 1
    assert summary['total_replans'] == 0
    assert executor.calls == []
