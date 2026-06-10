from llm_pipeline.failure_logic import (
    GeometricFailureChecker,
    LAYER_1_FAILURE_IDS,
    LAYER_2_FAILURE_IDS,
    SegmentationFirstFailureChecker,
    failure_layer_for_id,
)
from llm_pipeline.pipeline_types import (
    DirectAction,
    FailureLayer,
    FailureSource,
    FailureStage,
    SegmentationObjectEvidence,
    SegmentationSnapshot,
)


class FakeAdapter:
    def capture_snapshot(self, event=''):
        raise AssertionError('capture_snapshot should not be called in this unit test')

    def is_lid_open(self, snapshot: SegmentationSnapshot) -> bool:
        evidence = snapshot.object_evidence.get('box_lid')
        return evidence is not None and 'box_lid_top' not in set(evidence.mask_regions)

    def blocking_objects_for_lid(self, snapshot: SegmentationSnapshot):
        return []


adapter = FakeAdapter()
checker = SegmentationFirstFailureChecker(adapter=adapter, env=None)


class FakeDetector:
    def get_object_pose(self, name):
        return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)


class FarFakeDetector:
    def get_object_pose(self, name):
        if name == 'mug2':
            return (1.0, 1.0, 1.0)
        return (0.0, 0.0, 0.0)


class FakeGeometricAdapter(FakeAdapter):
    detector = FakeDetector()


class FarFakeGeometricAdapter(FakeAdapter):
    detector = FarFakeDetector()


class ClosedGrillAdapter(FakeAdapter):
    def is_lid_open(self, snapshot: SegmentationSnapshot, lid_name: str = 'grill_lid') -> bool:
        return False


class OpenLidAdapter(FakeAdapter):
    def is_lid_open(self, snapshot: SegmentationSnapshot, lid_name: str = 'box_lid') -> bool:
        return True


def _snapshot(object_evidence, newly_visible=None, visible_regions=None, object_region_map=None):
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=sorted([name for name, evidence in object_evidence.items() if evidence.visible]),
        newly_visible_objects=list(newly_visible or []),
        object_evidence=object_evidence,
        gripper_evidence={},
        supported_regions=['table', 'table_staging_area', 'cupboard_shelf', 'inside_box'],
        visible_regions=list(visible_regions or []),
        object_region_map=dict(object_region_map or {}),
    )


def test_precheck_flags_missing_pick_object() -> None:
    snapshot = _snapshot({})
    failure = checker.precheck(
        DirectAction('pick', ('mug4',)),
        held_object=None,
        snapshot=snapshot,
        last_action_name='pick',
    )
    assert failure is not None
    assert failure.failure_id == 'pick_object_missing'
    assert failure.failure_layer == FailureLayer.LAYER_1
    assert failure.stage == FailureStage.BEFORE_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION


def test_precheck_blocks_inside_grill_place_when_lid_closed() -> None:
    grill_checker = SegmentationFirstFailureChecker(adapter=ClosedGrillAdapter(), env=None)
    snapshot = _snapshot(
        {
            'chicken': SegmentationObjectEvidence(name='chicken', visible=True, mask_regions=['prep_area']),
            'grill_lid': SegmentationObjectEvidence(name='grill_lid', visible=True, mask_regions=['inside_grill']),
        },
        visible_regions=['prep_area', 'inside_grill'],
    )
    failure = grill_checker.precheck(
        DirectAction('place', ('chicken', 'inside_grill')),
        held_object='chicken',
        snapshot=snapshot,
        last_action_name='pick',
    )
    assert failure is not None
    assert failure.failure_id == 'grill_lid_closed'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.BEFORE_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION


def test_precheck_blocks_inside_box_place_when_lid_closed() -> None:
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['table_staging_area']),
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['box_lid_top']),
        },
        visible_regions=['table_staging_area', 'box_lid_top'],
    )
    failure = checker.precheck(
        DirectAction('place', ('mug2', 'inside_box')),
        held_object='mug2',
        snapshot=snapshot,
        last_action_name='pick',
    )
    assert failure is not None
    assert failure.failure_id == 'box_lid_closed'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.BEFORE_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION
    assert 'open(box_lid) first' in failure.message


def test_precheck_blocks_open_box_lid_when_object_on_lid() -> None:
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['box_lid_top']),
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['box_lid_top']),
        },
        visible_regions=['box_lid_top'],
        object_region_map={'mug2': 'box_lid_top'},
    )
    failure = checker.precheck(
        DirectAction('open', ('box_lid',)),
        held_object=None,
        snapshot=snapshot,
        last_action_name='place',
    )
    assert failure is not None
    assert failure.failure_id == 'box_lid_obstructed'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.BEFORE_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION
    assert failure.evidence['blocking_objects'] == ['mug2']
    assert 'move mug2 to table_staging_area first' in failure.message


def test_postcheck_flags_bad_place_region() -> None:
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['cupboard_shelf']),
        },
        visible_regions=['cupboard_shelf'],
        object_region_map={'mug2': 'cupboard_shelf'},
    )
    failure = checker.postcheck(
        DirectAction('place', ('mug2', 'table_staging_area')),
        held_object=None,
        snapshot=snapshot,
    )
    assert failure is not None
    assert failure.failure_id == 'placement_failed'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION
    assert failure.source == FailureSource.GEOMETRY


def test_postcheck_flags_grasp_failed_when_pick_not_confirmed_near_gripper() -> None:
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(
                name='mug2',
                visible=True,
                mask_regions=['table'],
                gripper_proximity=0.9,
            ),
        },
        visible_regions=['table'],
    )
    failure = checker.postcheck(
        DirectAction('pick', ('mug2',)),
        held_object='mug2',
        snapshot=snapshot,
    )
    assert failure is not None
    assert failure.failure_id == 'grasp_failed'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION


def test_postcheck_accepts_pick_confirmed_near_gripper() -> None:
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(
                name='mug2',
                visible=True,
                mask_regions=['table'],
                gripper_proximity=0.1,
            ),
        },
        visible_regions=['table'],
    )
    failure = checker.postcheck(
        DirectAction('pick', ('mug2',)),
        held_object='mug2',
        snapshot=snapshot,
    )
    assert failure is None


def test_postcheck_flags_object_dropped_when_placed_object_not_visible() -> None:
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(name='mug2', visible=False, mask_regions=[]),
        },
    )
    failure = checker.postcheck(
        DirectAction('place', ('mug2', 'table_staging_area')),
        held_object=None,
        snapshot=snapshot,
    )
    assert failure is not None
    assert failure.failure_id == 'object_dropped'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION


def test_postcheck_uses_geometric_region_instead_of_mask_regions() -> None:
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['table']),
        },
        visible_regions=['table'],
        object_region_map={'mug2': 'inside_box'},
    )
    failure = checker.postcheck(
        DirectAction('place', ('mug2', 'inside_box')),
        held_object=None,
        snapshot=snapshot,
    )
    assert failure is None


def test_postcheck_accepts_geometric_region_when_object_mask_is_hidden() -> None:
    snapshot = _snapshot(
        {},
        visible_regions=['inside_box'],
        object_region_map={'mug1': 'inside_box'},
    )
    failure = checker.postcheck(
        DirectAction('place', ('mug1', 'inside_box')),
        held_object=None,
        snapshot=snapshot,
    )
    assert failure is None


def test_postcheck_accepts_gt_table_area_for_table_staging_area() -> None:
    snapshot = _snapshot(
        {
            'mug3': SegmentationObjectEvidence(name='mug3', visible=True, mask_regions=['pantry_area']),
        },
        visible_regions=['pantry_area'],
        object_region_map={'mug3': 'pantry_area'},
    )
    failure = checker.postcheck(
        DirectAction('place', ('mug3', 'table_staging_area')),
        held_object=None,
        snapshot=snapshot,
    )
    assert failure is None


def test_postcheck_triggers_replan_for_new_visibility() -> None:
    snapshot = _snapshot(
        {
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['table_staging_area']),
            'mug4': SegmentationObjectEvidence(name='mug4', visible=True, mask_regions=['inside_box']),
        },
        newly_visible=['mug4'],
        visible_regions=['table_staging_area', 'inside_box'],
    )
    failure = checker.postcheck(DirectAction('open', ('box_lid',)), held_object=None, snapshot=snapshot)
    assert failure is not None
    assert failure.failure_id == 'new_object_discovered'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION
    assert failure.should_replan is True


def test_postcheck_ignores_new_visibility_for_action_object() -> None:
    snapshot = _snapshot(
        {
            'mug4': SegmentationObjectEvidence(
                name='mug4',
                visible=True,
                mask_regions=['table'],
                gripper_proximity=0.1,
            ),
        },
        newly_visible=['mug4'],
        visible_regions=['table'],
    )
    failure = checker.postcheck(DirectAction('pick', ('mug4',)), held_object='mug4', snapshot=snapshot)
    assert failure is None


def test_fallback_postcheck_can_trigger_new_visibility_replan() -> None:
    snapshot = _snapshot(
        {
            'mustard': SegmentationObjectEvidence(name='mustard', visible=True, mask_regions=['table']),
        },
        newly_visible=['mustard'],
        visible_regions=['table'],
    )
    failure = checker.postcheck(DirectAction('wait', ()), held_object=None, snapshot=snapshot)
    assert failure is not None
    assert failure.failure_id == 'new_object_discovered'


def test_postcheck_flags_lid_not_open_enough() -> None:
    snapshot = _snapshot(
        {
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['box_lid_top']),
        },
        visible_regions=['box_lid_top'],
    )
    failure = checker.postcheck(DirectAction('open', ('box_lid',)), held_object=None, snapshot=snapshot)
    assert failure is not None
    assert failure.failure_id == 'lid_not_open_enough'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION


def test_postcheck_flags_lid_not_closed_enough() -> None:
    open_lid_checker = SegmentationFirstFailureChecker(adapter=OpenLidAdapter(), env=None)
    snapshot = _snapshot(
        {
            'box_lid': SegmentationObjectEvidence(name='box_lid', visible=True, mask_regions=['table_staging_area']),
        },
        visible_regions=['table_staging_area'],
    )
    failure = open_lid_checker.postcheck(DirectAction('close', ('box_lid',)), held_object=None, snapshot=snapshot)
    assert failure is not None
    assert failure.failure_id == 'lid_not_closed_enough'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION
    assert failure.source == FailureSource.SEGMENTATION


def test_runtime_error_maps_to_pddl_failure() -> None:
    failure = checker.classify_runtime_error(DirectAction('pick', ('mug2',)), 'No PDDL plan found')
    assert failure.failure_id == 'pddl_no_plan'
    assert failure.failure_layer == FailureLayer.LAYER_1
    assert failure.source == FailureSource.PDDL


def test_geometric_postcheck_trusts_resolved_object_region_map() -> None:
    geometric_checker = GeometricFailureChecker(adapter=FakeGeometricAdapter(), env=None)
    snapshot = _snapshot(
        {
            'sugar': SegmentationObjectEvidence(name='sugar', visible=True, mask_regions=['cupboard_shelf']),
        },
        visible_regions=['cupboard_shelf'],
        object_region_map={'sugar': 'cupboard_shelf'},
    )
    failure = geometric_checker.postcheck(
        DirectAction('place', ('sugar', 'cupboard_shelf')),
        held_object=None,
        snapshot=snapshot,
    )
    assert failure is None


def test_geometric_postcheck_flags_failed_containment() -> None:
    geometric_checker = GeometricFailureChecker(adapter=FarFakeGeometricAdapter(), env=None)
    snapshot = _snapshot(
        {
            'mug2': SegmentationObjectEvidence(name='mug2', visible=True, mask_regions=['table']),
        },
        visible_regions=['table'],
        object_region_map={'mug2': 'table'},
    )
    failure = geometric_checker.postcheck(
        DirectAction('place', ('mug2', 'inside_box')),
        held_object=None,
        snapshot=snapshot,
    )
    assert failure is not None
    assert failure.failure_id == 'geometric_placement_failed'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION
    assert failure.source == FailureSource.GEOMETRY


def test_runtime_validation_failure_maps_to_layer_2() -> None:
    failure = checker.classify_runtime_error(
        DirectAction('place', ('mug2', 'table_staging_area')),
        "Object 'mug2' not in target region 'table_staging_area'",
    )
    assert failure.failure_id == 'placement_failed'
    assert failure.failure_layer == FailureLayer.LAYER_2
    assert failure.stage == FailureStage.AFTER_EXECUTION


def test_runtime_error_maps_layer_2_validation_failures() -> None:
    cases = [
        ('Object mug2 not found after placement', 'object_missing_after_place'),
        ("Object 'mug2' didn't move after release", 'object_did_not_move'),
        ("Object 'mug2' fell during transport", 'object_dropped'),
        ("ERROR: validation failed for 'chicken'", 'placement_failed'),
        "Lid didn't slide open enough",
        "Lid didn't slide closed enough",
    ]
    for case in cases:
        if isinstance(case, tuple):
            message, expected = case
        else:
            message = case
            expected = 'lid_not_open_enough' if 'open' in case else 'lid_not_closed_enough'
        failure = checker.classify_runtime_error(
            DirectAction('place', ('mug2', 'table_staging_area')),
            message,
        )
        assert failure.failure_id == expected
        assert failure.failure_layer == FailureLayer.LAYER_2
        assert failure.stage == FailureStage.AFTER_EXECUTION


def test_failure_event_dict_includes_layer() -> None:
    failure = checker.classify_runtime_error(DirectAction('pick', ('mug2',)), 'No PDDL plan found')
    payload = failure.to_dict()
    assert payload['failure_layer'] == 'layer_1'


def test_known_failure_ids_have_one_layer() -> None:
    assert LAYER_1_FAILURE_IDS.isdisjoint(LAYER_2_FAILURE_IDS)
    for failure_id in LAYER_1_FAILURE_IDS:
        assert failure_layer_for_id(failure_id) == FailureLayer.LAYER_1
    for failure_id in LAYER_2_FAILURE_IDS:
        assert failure_layer_for_id(failure_id) == FailureLayer.LAYER_2
