from llm_pipeline.executable_symbols import GRILL_ACTION_SYMBOLS, GRILL_OBJECT_ORDER, GRILL_REGION_ORDER, RuntimeSymbolRegistry
from llm_pipeline.prompt_builder import TextOnlyContextBuilder
from llm_pipeline.pipeline_types import (
    FailureEvent,
    FailureSource,
    FailureStage,
    SceneState,
    SegmentationObjectEvidence,
    SegmentationSnapshot,
)


def _snapshot() -> SegmentationSnapshot:
    return SegmentationSnapshot(
        frame_index=1,
        visible_objects=['mug2', 'box_lid'],
        newly_visible_objects=['mug2'],
        object_evidence={
            'mug2': SegmentationObjectEvidence(
                name='mug2',
                visible=True,
                camera_hits=['overhead'],
                pixel_count=16,
                camera_pixels={'overhead': 16},
                bbox={'overhead': (0.4000, 0.3000, 0.6000, 0.5000)},
                centroid={'overhead': (0.5000, 0.4000)},
                mask_regions=['inside_box'],
                newly_visible=True,
            ),
            'box_lid': SegmentationObjectEvidence(
                name='box_lid',
                visible=True,
                camera_hits=['overhead'],
                pixel_count=20,
                camera_pixels={'overhead': 20},
                bbox={'overhead': (0.3000, 0.2000, 0.7000, 0.5200)},
                centroid={'overhead': (0.5000, 0.3600)},
                mask_regions=['box_lid_top'],
            ),
        },
        gripper_evidence={},
        supported_regions=['table', 'table_target_area', 'cupboard_shelf', 'inside_box'],
        visible_regions=['inside_box'],
        object_region_map={'mug2': 'inside_box'},
        object_region_descriptions={'mug2': 'inside the box storage target'},
    )


def _state(snapshot: SegmentationSnapshot, held_object=None) -> SceneState:
    state = SceneState(
        frame_index=snapshot.frame_index,
        visible_objects=snapshot.visible_objects,
        valid_regions=snapshot.supported_regions,
        gripper_state={'status': 'holding' if held_object else 'empty', 'holding': held_object},
        object_region_map=dict(snapshot.object_region_map),
        object_region_descriptions=dict(snapshot.object_region_descriptions),
    )
    state._original_snapshot = snapshot
    return state


def test_prompt_bundle_stays_text_only() -> None:
    builder = TextOnlyContextBuilder()
    failure = FailureEvent(
        failure_id='placement_failed',
        stage=FailureStage.AFTER_EXECUTION,
        source=FailureSource.SEGMENTATION,
        action='place(mug2, table_target_area)',
        evidence={},
        message='failure_id=placement_failed',
    )
    bundle = builder.build_bundle(
        state=_state(_snapshot(), held_object='mug2'),
        goal_text='Move mug2 to table_target_area.',
        icl_mode='few_shot_shared_1',
        failure_event=failure,
        previous_actions=['pick(mug2)'],
    )
    assert set(bundle.__dict__.keys()) == {
        'goal_text',
        'system_prompt',
        'user_prompt',
        'visible_objects',
        'valid_regions',
        'images',
        'image_paths',
        'failure_context',
        'icl_mode',
        'previous_actions',
        'metadata',
    }
    assert bundle.images is None
    assert bundle.image_paths is None

    system_prompt = bundle.system_prompt
    user_prompt = bundle.user_prompt

    assert 'SHARED FEW-SHOT EXEMPLAR' in system_prompt
    assert 'Move mug2 to table_target_area.' not in system_prompt
    assert 'failure_id=placement_failed' not in system_prompt
    assert 'CURRENT SEGMENTATION SNAPSHOT:' in user_prompt
    assert 'REGION MEANINGS:' in user_prompt
    assert 'table_target_area: specific target area on the table for objects that should be moved onto the table' in user_prompt
    assert 'inside_box: interior storage area of the box for objects that should be put inside the box' in user_prompt
    assert 'VISIBLE OBJECT EVIDENCE:' in user_prompt
    assert 'COMPACT SEGMENTATION SUMMARY:' in user_prompt
    assert 'ACCESS CONSTRAINTS:' in user_prompt
    assert 'inside_box is BLOCKED until open(box_lid) is completed' in user_prompt
    assert 'PREVIOUS ACTIONS (already executed, do not repeat):' in user_prompt
    assert 'pick(mug2)' in user_prompt
    assert 'FAILURE CONTEXT:' in user_prompt
    assert 'available_actions=pick, place, open, close, wait' in user_prompt or 'available_actions=' in user_prompt
    assert 'Executable action formats for this run:' in user_prompt
    assert 'Respect ACCESS CONSTRAINTS' in user_prompt
    assert 'open(box_lid)' in user_prompt
    assert 'FINAL ACTIONS:' in user_prompt
    assert 'Start the response with exactly two short checks, then FINAL ACTIONS:.' in user_prompt
    assert 'CHECK 1 must map goal object categories to target regions using the visible object names.' in user_prompt
    assert 'CHECK 2 must identify blockers, access constraints, or already-satisfied objects.' in user_prompt
    assert 'Do not write additional reasoning, analysis, alternatives, prose, markdown, bullets, numbering, or commentary.' in user_prompt
    assert 'state_text' not in user_prompt
    assert 'region=inside_box' in user_prompt
    assert 'visual_mask_regions=inside_box' in user_prompt
    assert 'visible_regions=inside_box' in user_prompt
    assert 'box_lid_state' not in user_prompt
    assert 'region_hint=' not in user_prompt


def test_zero_shot_system_prompt_has_no_shared_exemplar() -> None:
    builder = TextOnlyContextBuilder()
    bundle = builder.build_bundle(
        state=_state(_snapshot()),
        goal_text='Open the lid.',
        icl_mode='zero_shot',
    )
    system_prompt = bundle.system_prompt
    assert 'SHARED FEW-SHOT EXEMPLAR' not in system_prompt
    assert 'Valid action lines:' not in system_prompt
    assert 'FINAL ACTIONS:' in system_prompt
    assert 'CHECK 1:' in system_prompt
    assert 'CHECK 2:' in system_prompt
    assert 'Plan only from the current scene evidence' in system_prompt
    assert 'Do not invent hidden objects' in system_prompt
    assert 'Do not output robot motions, grasp poses, trajectories, coordinates, PDDL predicates' in system_prompt
    assert 'For grill tasks, keep the same object name before and after cooking' in system_prompt
    assert 'chicken, steak, steak1, or other listed meat names' in system_prompt
    assert 'Multiple raw meat objects may be cooked together' not in system_prompt
    assert 'Multiple raw meats can be cooked together' not in system_prompt
    assert 'EXECUTABLE ACTION SEQUENCE' not in system_prompt
    assert 'mug_box' not in system_prompt


def test_grill_batch_cooking_hint_is_user_prompt_only() -> None:
    builder = TextOnlyContextBuilder(
        symbol_registry=RuntimeSymbolRegistry(
            actions=GRILL_ACTION_SYMBOLS,
            objects=GRILL_OBJECT_ORDER,
            regions=GRILL_REGION_ORDER,
        )
    )
    snapshot = SegmentationSnapshot(
        frame_index=1,
        visible_objects=['chicken', 'steak', 'plate', 'grill_lid'],
        newly_visible_objects=[],
        object_evidence={},
        gripper_evidence={},
        supported_regions=['table', 'inside_grill', 'plate_top'],
        visible_regions=['table', 'inside_grill', 'plate_top'],
        object_region_map={'chicken': 'table', 'steak': 'table', 'plate': 'table'},
        object_region_descriptions={
            'chicken': 'on the table surface',
            'steak': 'on the table surface',
            'plate': 'on the table surface',
        },
    )

    bundle = builder.build_bundle(
        state=_state(snapshot),
        goal_text='Cook all meat and serve it on the plate.',
        icl_mode='zero_shot',
    )

    assert 'Multiple raw meats can be cooked together' in bundle.user_prompt
    assert 'placing all of them inside_grill before one close(grill_lid) and one open(grill_lid)' in bundle.user_prompt
    assert 'Cooking status and serving location are separate' in bundle.user_prompt
    assert 'Multiple raw meats can be cooked together' not in bundle.system_prompt
    assert 'Cooking status and serving location are separate' not in bundle.system_prompt


def test_text_prompt_repeats_cooked_status_for_fallen_meat() -> None:
    builder = TextOnlyContextBuilder(
        symbol_registry=RuntimeSymbolRegistry(
            actions=GRILL_ACTION_SYMBOLS,
            objects=GRILL_OBJECT_ORDER,
            regions=GRILL_REGION_ORDER,
        )
    )
    snapshot = SegmentationSnapshot(
        frame_index=7,
        visible_objects=['steak1', 'grill_lid'],
        newly_visible_objects=[],
        object_evidence={},
        gripper_evidence={},
        supported_regions=['table', 'inside_grill', 'plate_top'],
        visible_regions=['table', 'inside_grill', 'plate_top'],
        object_region_map={'steak1': 'table'},
        object_region_descriptions={'steak1': 'on the table surface'},
    )
    state = _state(snapshot)
    state.pddl_state = [
        'grill_lid_open',
        'on_table(steak1)',
        'cooked(steak1)',
    ]

    bundle = builder.build_bundle(
        state=state,
        goal_text='Serve all cooked meat on the plate.',
        icl_mode='zero_shot',
    )

    assert '- steak1: region=table, cook_status=cooked' in bundle.user_prompt
    assert '- cooked(steak1)' in bundle.user_prompt
    assert 'raw(steak1)' not in bundle.user_prompt


def test_fallback_regions_are_hidden_from_llm_prompt() -> None:
    snapshot = _snapshot()
    snapshot.supported_regions = [
        'table',
        'cupboard_shelf',
        'inside_box',
    ]
    snapshot.object_evidence['mug2'].mask_regions = [
        'inside_box',
    ]
    snapshot.object_region_map = {'mug2': 'inside_box'}

    bundle = TextOnlyContextBuilder().build_bundle(
        state=_state(snapshot),
        goal_text='Move mug2 to inside_box.',
        icl_mode='zero_shot',
    )

    assert 'inside_box' in bundle.user_prompt
    assert 'cupboard_shelf' in bundle.user_prompt


def test_prompt_marks_box_lid_obstruction_when_object_is_on_lid() -> None:
    snapshot = _snapshot()
    snapshot.object_region_map = {'mug2': 'box_lid_top'}
    snapshot.object_region_descriptions = {'mug2': 'on top of the box lid'}

    bundle = TextOnlyContextBuilder().build_bundle(
        state=_state(snapshot),
        goal_text='Move all mugs inside_box.',
        icl_mode='zero_shot',
    )

    assert 'box_lid is OBSTRUCTED by mug2; before open(box_lid), move mug2 to table_target_area' in bundle.user_prompt
