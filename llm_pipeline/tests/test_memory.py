"""Phase 2: observation memory <object, last_seen_step, last_region>."""

import pytest

from llm_pipeline.executable_symbols import RuntimeSymbolRegistry
from llm_pipeline.failures import FailureCode
from llm_pipeline.flags import PipelineFlags
from llm_pipeline.memory import HELD_REGION, MemoryEntry, ObservationMemory
from llm_pipeline.pipeline import LLMOnlyReplanningPipeline, LLMPipelineConfig
from llm_pipeline.pipeline_types import (
    FailureEvent, FailureSource, FailureStage, SegmentationObjectEvidence, SegmentationSnapshot,
)
from llm_pipeline.strict_parser import StrictActionParser, StrictParseError
from llm_pipeline.tests.test_phase1_pipeline import (
    PLAN_1, PLAN_3, Checker, HookedExecutor, SceneAdapter, ScriptedPlanner, _pipeline,
)
from llm_pipeline.tests.test_pipeline import FakeEnv
from llm_pipeline.trial_log import TrialLogger


# ---------------------------------------------------------------- unit tests
def test_create_overwrite_keep_and_never_delete() -> None:
    memory = ObservationMemory()
    assert memory.update(1, ['mug2', 'spam'], {'mug2': 'table', 'spam': 'pantry_area'}) == ['mug2', 'spam']
    assert memory.get('mug2') == MemoryEntry('mug2', 1, 'table')
    # overwrite: visible again at a later step with a new region
    assert memory.update(2, ['mug2'], {'mug2': 'inside_box'}) == []
    assert memory.get('mug2') == MemoryEntry('mug2', 2, 'inside_box')
    # keep-when-hidden: spam not visible at step 2 keeps its entry
    assert memory.get('spam') == MemoryEntry('spam', 1, 'pantry_area')
    assert memory.is_visible('mug2') and not memory.is_visible('spam')
    assert [entry.object_id for entry in memory.remembered()] == ['spam']
    # never-delete: an empty observation removes nothing
    memory.update(3, [], {})
    assert len(memory) == 2 and {e.object_id for e in memory.remembered()} == {'mug2', 'spam'}


def test_never_observed_objects_are_never_in_memory() -> None:
    memory = ObservationMemory()
    memory.update(1, ['mug2'], {'mug2': 'table', 'soup': 'inside_box'})
    assert 'soup' not in memory


def test_held_object_is_remembered_in_the_gripper() -> None:
    memory = ObservationMemory()
    memory.update(4, ['mug2'], {'mug2': 'table'}, held_object='mug2')
    assert memory.get('mug2').last_region == HELD_REGION


def test_kitchen_object_revealed_by_opening_stays_after_it_is_hidden() -> None:
    memory = ObservationMemory()
    memory.update(1, ['mug2'], {'mug2': 'table'})
    assert 'can_of_beans' not in memory
    memory.update(2, ['mug2', 'can_of_beans'], {'mug2': 'table', 'can_of_beans': 'inside_box'})  # box opened
    memory.update(3, ['mug2'], {'mug2': 'table'})  # box closed again: can_of_beans hidden
    assert memory.get('can_of_beans') == MemoryEntry('can_of_beans', 2, 'inside_box')


def test_mismatch_only_when_the_last_region_is_visible_and_open() -> None:
    memory = ObservationMemory()
    memory.update(1, ['steak'], {'steak': 'inside_grill'})
    memory.update(2, [], {})
    assert memory.mismatches(visible_regions=['inside_grill'], open_regions=[]) == []  # lid closed
    assert memory.mismatches(visible_regions=[], open_regions=['inside_grill']) == []  # region not visible
    assert [e.object_id for e in memory.mismatches(['inside_grill'], ['inside_grill'])] == ['steak']


def test_plan_check_accepts_remembered_objects_only_when_reachable() -> None:
    parser = StrictActionParser(valid_actions=['pick', 'place', 'open', 'close'],
                                valid_objects=['steak', 'grill_lid', 'plate'], valid_regions=['plate_top', 'table'])
    parser.set_observed_objects({'steak', 'grill_lid', 'plate'})
    parser.set_access_context(remembered_regions={'steak': 'inside_grill'}, closed_regions={'inside_grill'},
                              lid_regions={'grill_lid': ('inside_grill',)})
    with pytest.raises(StrictParseError) as error:
        parser.parse('FINAL ACTIONS:\npick(steak)\nplace(steak, plate_top)')
    assert error.value.failure_id == FailureCode.REMEMBERED_OBJECT_INACCESSIBLE
    actions = parser.parse('FINAL ACTIONS:\nopen(grill_lid)\npick(steak)\nplace(steak, plate_top)')
    assert [a.action_name for a in actions] == ['open', 'pick', 'place']
    parser.set_access_context(None)
    assert len(parser.parse('FINAL ACTIONS:\npick(steak)\nplace(steak, plate_top)')) == 2


# ---------------------------------------------------------------- grill scene
class LidJoint:
    def __init__(self):
        self.value = 1.0

    def get_joint_position(self):
        return self.value


class FakeGrill(FakeEnv):
    def __init__(self):
        super().__init__()
        self.grill_boundary = object()
        self.lid_joint = LidJoint()
        self._closed_lid_angle = 0.0


class GrillAdapter(SceneAdapter):
    """chicken sits in the grill; it is visible only while the grill lid is open."""

    def __init__(self, env):
        super().__init__()
        self.env_ref = env

    def lid_open(self):
        return self.env_ref.lid_joint.value > 0.5

    def visible(self):
        return ['plate', 'grill_lid'] + (['chicken'] if self.lid_open() else [])

    def snapshot(self, newly=()):
        regions = {'plate': 'dish_rack'}
        if self.lid_open():
            regions['chicken'] = 'inside_grill'
        snap = SegmentationSnapshot(
            frame_index=1, visible_objects=self.visible(), newly_visible_objects=list(newly),
            object_evidence={n: SegmentationObjectEvidence(name=n, visible=True) for n in self.visible()},
            gripper_evidence={}, supported_regions=['table', 'inside_grill', 'plate_top', 'serving_area', 'dish_rack'],
            visible_regions=['inside_grill', 'serving_area'], object_region_map=regions, object_region_descriptions={},
        )
        self.known_visible.update(snap.visible_objects)
        return snap

    def is_lid_open(self, snapshot, lid_name='grill_lid'):
        return self.lid_open()


def _grill_pipeline(memory='true', tmp_path=None):
    env = FakeGrill()
    adapter = GrillAdapter(env)
    planner = ScriptedPlanner(['FINAL ACTIONS:\nclose(grill_lid)', 'FINAL ACTIONS:\npick(chicken)\nplace(chicken, plate_top)',
                               'FINAL ACTIONS:\nopen(grill_lid)'])
    pipeline = LLMOnlyReplanningPipeline(
        config=LLMPipelineConfig(model_alias='scripted', headless=True, live_segmentation_view=False,
                                 enable_goal_check=False, flags=PipelineFlags(memory_enabled=memory)),
        planner=planner, segmentation_adapter=adapter, failure_checker=Checker(adapter), executor=HookedExecutor(adapter),
    )
    assert pipeline.initialize(env=env)
    registry = RuntimeSymbolRegistry(('pick', 'place', 'open', 'close'), ('chicken', 'plate', 'grill_lid'),
                                     ('table', 'inside_grill', 'plate_top', 'serving_area', 'dish_rack'))
    pipeline.symbol_registry = registry
    pipeline.context_builder.set_symbol_registry(registry)
    planner.parser = StrictActionParser(valid_actions=registry.actions, valid_objects=registry.objects,
                                        valid_regions=registry.regions)
    if tmp_path is not None:
        pipeline.set_trial_logger(TrialLogger(tmp_path / 'trial_log.jsonl', trial_id='G_memory'))
    return pipeline, planner, adapter, env


def _trigger():
    return FailureEvent(failure_id=FailureCode.PLACEMENT_FAILED, stage=FailureStage.AFTER_EXECUTION,
                        source=FailureSource.GEOMETRY, action='place(plate, serving_area)', evidence={})


def test_grill_meat_stays_in_memory_after_closing_and_is_remembered_in_the_prompt(tmp_path) -> None:
    pipeline, planner, adapter, env = _grill_pipeline(tmp_path=tmp_path)
    pipeline.reset_episode_state()
    pipeline.plan_once('COOK all raw meat', failure_event=None)          # step 1: lid open, chicken visible
    assert pipeline.memory.get('chicken') == MemoryEntry('chicken', 1, 'inside_grill')
    env.lid_joint.value = 0.0                                              # close(grill_lid)
    pipeline._on_bundle_end(bundle_id='b1', actions=['close(grill_lid)'], success=True, failure_event=None,
                            snapshot=adapter.snapshot())                   # step 2: chicken hidden
    assert pipeline.memory.get('chicken') == MemoryEntry('chicken', 1, 'inside_grill')
    result, trace = pipeline.plan_once('COOK all raw meat', failure_event=_trigger())  # step 3
    prompt = trace['user_prompt']
    assert ('Remembered objects (not currently visible): last region, steps since last seen:\n'
            '- chicken: inside_grill, 2 steps ago') in prompt
    # The plan pick(chicken) while the grill is closed is rejected by the plan check.
    assert result.failure_event is not None
    assert result.failure_event.failure_id == FailureCode.REMEMBERED_OBJECT_INACCESSIBLE
    events = [line for line in (tmp_path / 'trial_log.jsonl').read_text().splitlines() if '"memory_snapshot"' in line]
    assert len(events) == 3


def test_remembered_object_can_be_picked_once_its_region_is_open() -> None:
    pipeline, planner, adapter, env = _grill_pipeline()
    pipeline.reset_episode_state()
    pipeline.plan_once('COOK all raw meat', failure_event=None)
    env.lid_joint.value = 0.0
    pipeline._on_bundle_end(bundle_id='b1', actions=[], success=True, failure_event=None, snapshot=adapter.snapshot())
    assert pipeline._remembered_pick_allowed('chicken') is False     # grill closed
    env.lid_joint.value = 1.0
    pipeline._last_articulation = {'grill_lid': True}
    assert pipeline._remembered_pick_allowed('chicken') is True
    assert pipeline._remembered_pick_allowed('steak') is False       # never observed


def test_memory_off_is_the_previous_behavior(tmp_path) -> None:
    pipeline, planner, adapter, env = _grill_pipeline(memory='false', tmp_path=tmp_path)
    pipeline.reset_episode_state()
    pipeline.plan_once('COOK all raw meat', failure_event=None)
    env.lid_joint.value = 0.0
    pipeline._on_bundle_end(bundle_id='b1', actions=[], success=True, failure_event=None, snapshot=adapter.snapshot())
    result, trace = pipeline.plan_once('COOK all raw meat', failure_event=_trigger())
    assert 'Remembered' not in trace['user_prompt']
    assert 'chicken' not in trace['user_prompt']
    assert len(pipeline.memory) == 0
    assert '"memory_snapshot"' not in (tmp_path / 'trial_log.jsonl').read_text()


def test_kitchen_trial_logs_memory_and_the_revealed_object(tmp_path) -> None:
    pipeline, planner, adapter = _pipeline([PLAN_1, PLAN_3], flags=PipelineFlags(memory_enabled='true'))
    pipeline.set_trial_logger(TrialLogger(tmp_path / 'log.jsonl', trial_id='K_memory'))
    pipeline.run('move ALL THE MUGS inside the box')
    assert pipeline.memory.get('can_of_beans').last_seen_step >= 3
    assert pipeline.memory.get('can_of_beans').last_region in ('inside_box', 'cupboard_shelf')
