import json

import pytest

from llm_pipeline.failure_logic import LAYER_1_FAILURE_IDS, LAYER_2_FAILURE_IDS, failure_layer_for_id
from llm_pipeline.failures import (
    FAILURE_CODE_INFO,
    FailureCheck,
    FailureCode,
    LegacyMessageCategory,
    TaxonomyFamily,
    as_failure_code,
    failure_check_for,
)
from llm_pipeline.flags import FLAG_SPECS, PipelineFlags
from llm_pipeline.pipeline_types import FailureEvent, FailureLayer, FailureSource, FailureStage

# Layer-2 ids as they were before the shared enum (record.json failure_layer).
PREVIOUS_LAYER_2_IDS = {
    'grasp_failed', 'object_dropped', 'object_did_not_move', 'object_missing_after_place', 'placement_failed',
    'geometric_placement_failed', 'lid_not_open_enough', 'lid_not_closed_enough', 'new_object_discovered',
    'grill_lid_closed', 'box_lid_closed', 'box_lid_obstructed', 'goal_not_satisfied',
}

# The failure-taxonomy table (Table II in the paper drafts): family -> conditions.
TAXONOMY_TABLE = {
    TaxonomyFamily.MOTION_PLANNING: {
        'Empty pick trajectory', 'Empty place trajectory', 'Lid hover planning fail', 'Lid slide planning fail',
    },
    TaxonomyFamily.SCENE_ACCESSIBILITY: {'Pick object missing', 'Lid missing', 'Closed-box access', 'Lid blocked'},
    TaxonomyFamily.EXECUTION_DEVIATION: {'Grasp failed', 'Placement failed', 'Object dropped'},
    TaxonomyFamily.PLAN_INCONSISTENCY: {
        'Missing post-pick place', 'Pick-place mismatch', 'Orphan place', 'Unknown action token',
    },
}


def test_every_taxonomy_condition_has_a_code() -> None:
    covered = {}
    for info in FAILURE_CODE_INFO.values():
        if info.taxonomy:
            family, condition = info.taxonomy
            covered.setdefault(family, set()).add(condition)
    assert covered == TAXONOMY_TABLE


def test_legacy_layers_are_unchanged_for_previous_codes() -> None:
    previous_codes = {code.value for code in FailureCode if FAILURE_CODE_INFO[code].phase == 1}
    for code in previous_codes - {'goal_validation_failed', 'unobserved_object', 'planner_call_failed',
                                  'simulator_error', 'replan_budget_exhausted', 'planner_output_too_verbose',
                                  'planner_output_not_parseable'}:
        expected = FailureLayer.LAYER_2 if code in PREVIOUS_LAYER_2_IDS else FailureLayer.LAYER_1
        assert failure_layer_for_id(code) == expected, code
    assert LAYER_1_FAILURE_IDS.isdisjoint(LAYER_2_FAILURE_IDS)


def test_codes_serialize_as_plain_strings() -> None:
    event = FailureEvent(
        failure_id=FailureCode.PLACEMENT_FAILED,
        stage=FailureStage.AFTER_EXECUTION,
        source=FailureSource.GEOMETRY,
        action='place(mug2, inside_box)',
        evidence={},
    )
    payload = event.to_dict()
    assert type(payload['failure_id']) is str
    assert json.loads(json.dumps(payload))['failure_id'] == 'placement_failed'
    assert json.dumps({'code': FailureCode.GRASP_FAILED}) == '{"code": "grasp_failed"}'
    assert f'{FailureCode.ORPHAN_PLACE}' == str(FailureCode.ORPHAN_PLACE) == 'orphan_place'
    assert FailureCode.ORPHAN_PLACE == 'orphan_place'
    assert str(LegacyMessageCategory.PICK_MISMATCH) == 'pick_mismatch'


def test_checks_use_plan_terminology() -> None:
    assert failure_check_for('unknown_action_token') == FailureCheck.PLAN_CHECK
    assert failure_check_for('unobserved_object') == FailureCheck.PLAN_CHECK
    assert failure_check_for('box_lid_closed') == FailureCheck.PRE_ACTION_CHECK
    assert failure_check_for('grasp_failed') == FailureCheck.EXECUTION_FAILURE
    assert failure_check_for('new_object_discovered') == FailureCheck.TRIGGER
    assert failure_check_for('not_a_code') is None
    assert as_failure_code('pddl_no_plan') is FailureCode.PDDL_NO_PLAN
    assert {check.value for check in FailureCheck} >= {'plan_check', 'pre_action_check', 'execution_failure'}


def test_default_flags_match_plan_section_0_7() -> None:
    assert PipelineFlags().to_dict() == {
        'memory.enabled': 'false',
        'replan.trigger_mode': 'discovery',
        'replan.output_mode': 'full_replan',
        'replan.insertion_mode': 'planner',
        'parallel.enabled': 'false',
        'termination.mode': 'agent',
        'prompt.version': 'v2',
        'grasp.confirmation': 'gripper_state',
        'scene.randomization': 'pose_jitter',
    }


def test_flags_parse_cli_assignments() -> None:
    flags = PipelineFlags.from_assignments(['termination.mode=evaluator', 'prompt.version=legacy'])
    assert flags.termination_mode == 'evaluator'
    assert flags.prompt_version == 'legacy'
    assert PipelineFlags.from_assignments(flags.to_assignments()) == flags


@pytest.mark.parametrize(
    'assignment',
    ['memory.enabled=true', 'replan.trigger_mode=if_rule', 'replan.output_mode=corrective',
     'replan.insertion_mode=always_front', 'parallel.enabled=true'],
)
def test_flags_of_later_phases_are_not_available_yet(assignment) -> None:
    with pytest.raises(NotImplementedError):
        PipelineFlags.from_assignments([assignment])


def test_unknown_flag_values_are_rejected() -> None:
    with pytest.raises(ValueError):
        PipelineFlags.from_assignments(['termination.mode=sometimes'])
    with pytest.raises(ValueError):
        PipelineFlags.from_assignments(['no.such_flag=1'])
