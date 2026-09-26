"""Single source of truth for failure codes (plan.md Phase 1, step 2).

Every module reports failures through :class:`FailureCode`. Code values are
the strings already written to ``record.json`` (``failure_id``), so existing
records stay comparable; new JSONL trial logs add the check that reported the
code (:class:`FailureCheck`, plan.md Section 0.6 terminology) and, where it
applies, the condition from the failure-taxonomy table (Table II of the
ROBUST TAMP paper draft).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, FrozenSet, Optional, Tuple


class _StrEnum(str, Enum):
    """``str`` enum whose ``str()``/``format()`` is the plain value."""

    def __str__(self) -> str:
        return str(self.value)

    def __format__(self, spec: str) -> str:
        return format(str(self.value), spec)


class FailureCheck(_StrEnum):
    """Which part of the system reports a code (plan.md Section 0.6)."""

    PLAN_CHECK = 'plan_check'
    PRE_ACTION_CHECK = 'pre_action_check'
    EXECUTION_FAILURE = 'execution_failure'
    TRIGGER = 'trigger'
    GOAL_CHECK = 'goal_check'
    EVALUATION = 'evaluation'
    REPLAN = 'replan'
    INSERTION = 'insertion'
    PARALLEL = 'parallel'
    MEMORY = 'memory'
    INFRASTRUCTURE = 'infrastructure'


class TaxonomyFamily(_StrEnum):
    """Families of the failure-taxonomy table (Table II)."""

    MOTION_PLANNING = 'motion_planning'
    SCENE_ACCESSIBILITY = 'scene_accessibility'
    EXECUTION_DEVIATION = 'execution_deviation'
    PLAN_INCONSISTENCY = 'plan_inconsistency'


class FailureCode(_StrEnum):
    # plan check
    UNKNOWN_ACTION_TOKEN = 'unknown_action_token'
    PICK_PLACE_MISMATCH = 'pick_place_mismatch'
    ORPHAN_PLACE = 'orphan_place'
    MISSING_POST_PICK_PLACE = 'missing_post_pick_place'
    UNOBSERVED_OBJECT = 'unobserved_object'
    REMEMBERED_OBJECT_INACCESSIBLE = 'remembered_object_inaccessible'
    PLANNER_OUTPUT_TOO_VERBOSE = 'planner_output_too_verbose'
    PLANNER_OUTPUT_NOT_PARSEABLE = 'planner_output_not_parseable'
    MISSING_PRECEDING_MOVE = 'missing_preceding_move'
    INVALID_MOVE_TARGET = 'invalid_move_target'
    UNSUPPORTED_ACTION = 'unsupported_action'
    CONSECUTIVE_MOVES = 'consecutive_moves'
    DANGLING_MOVE = 'dangling_move'
    # pre-action check
    INVALID_EXECUTOR_STATE = 'invalid_executor_state'
    PICK_OBJECT_MISSING = 'pick_object_missing'
    LID_MISSING = 'lid_missing'
    GEOMETRIC_DISCOVERY_FAIL = 'geometric_discovery_fail'
    BOX_LID_CLOSED = 'box_lid_closed'
    GRILL_LID_CLOSED = 'grill_lid_closed'
    BOX_LID_OBSTRUCTED = 'box_lid_obstructed'
    # execution failure (motion planning)
    EMPTY_PICK_TRAJECTORY = 'empty_pick_trajectory'
    EMPTY_PLACE_TRAJECTORY = 'empty_place_trajectory'
    LID_HOVER_PLANNING_FAIL = 'lid_hover_planning_fail'
    LID_SLIDE_PLANNING_FAIL = 'lid_slide_planning_fail'
    PDDL_NO_PLAN = 'pddl_no_plan'
    NO_IK_SOLUTION = 'no_ik_solution'
    NO_MOTION_PLAN = 'no_motion_plan'
    NO_GRASP_FOUND = 'no_grasp_found'
    EXECUTOR_FAILURE = 'executor_failure'
    # execution failure (execution deviation, detected after the action)
    GRASP_FAILED = 'grasp_failed'
    OBJECT_DROPPED = 'object_dropped'
    OBJECT_DID_NOT_MOVE = 'object_did_not_move'
    OBJECT_MISSING_AFTER_PLACE = 'object_missing_after_place'
    PLACEMENT_FAILED = 'placement_failed'
    GEOMETRIC_PLACEMENT_FAILED = 'geometric_placement_failed'
    LID_NOT_OPEN_ENOUGH = 'lid_not_open_enough'
    LID_NOT_CLOSED_ENOUGH = 'lid_not_closed_enough'
    # trigger (not a failure): discovery-mode replan trigger
    NEW_OBJECT_DISCOVERED = 'new_object_discovered'
    IF_RULE_TRIGGER = 'if_rule_trigger'          # Phase 4: replan.trigger_mode = if_rule
    # goal check / evaluation
    GOAL_NOT_SATISFIED = 'goal_not_satisfied'
    GOAL_VALIDATION_FAILED = 'goal_validation_failed'
    # planner call / infrastructure
    PLANNER_CALL_FAILED = 'planner_call_failed'
    SIMULATOR_ERROR = 'simulator_error'
    # replan (Phase 7 failure area 8)
    REPLAN_BUDGET_EXHAUSTED = 'replan_budget_exhausted'
    REPEATED_PLANNER_OUTPUT = 'repeated_planner_output'
    # later phases (reserved; not emitted yet)
    MEMORY_MISMATCH = 'memory_mismatch'
    INSERTION_TOO_LATE = 'insertion_too_late'
    INVALID_CORRECTIVE_BLOCK = 'invalid_corrective_block'   # Phase 5: block list rejected by the plan check
    ANCHOR_ALREADY_EXECUTED = 'anchor_already_executed'
    MERGE_CONFLICT = 'merge_conflict'


class LegacyFailureId(_StrEnum):
    """Adapter error ids kept only as ``evidence.legacy_failure_id``."""

    TAMP_EXECUTION_ERROR = 'TAMP_EXECUTION_ERROR'
    TAMP_OPEN_ERROR = 'TAMP_OPEN_ERROR'
    TAMP_CLOSE_ERROR = 'TAMP_CLOSE_ERROR'
    DEBUG_EXECUTION_ERROR = 'DEBUG_EXECUTION_ERROR'


class LegacyMessageCategory(_StrEnum):
    """Categories of the old free-text classifier (record.json ``raw_failure_occurrences``)."""

    UNKNOWN = 'unknown'
    NEW_OBJECT_INTRODUCED_IN_SCENE = 'new_object_introduced_in_scene'
    OBJECT_BLOCKED = 'object_blocked'
    LID_CLOSED = 'lid_closed'
    OBJECT_NOT_FOUND = 'object_not_found'
    ORPHAN_PLACE = 'orphan_place'
    PICK_MISMATCH = 'pick_mismatch'
    GRASP_FAILED = 'grasp_failed'
    PLACEMENT_FAILED = 'placement_failed'
    NO_IK_SOLUTION = 'no_ik_solution'
    NO_MOTION_PLAN = 'no_motion_plan'
    NO_GRASP_FOUND = 'no_grasp_found'
    PDDL_NO_PLAN = 'pddl_no_plan'
    COLLISION_DETECTED = 'collision_detected'
    OBJECT_DROPPED = 'object_dropped'


class CycleError(_StrEnum):
    """Values of ``ExecutionCycleRecord.error_message`` that are not free text."""

    PLANNING_FAILED = 'planning_failed'
    PLANNER_RETURNED_NO_ACTIONS = 'planner_returned_no_actions'


class TerminationReason(_StrEnum):
    """Why a trial ended (``trial_end.termination_reason``)."""

    PLAN_COMPLETED = 'plan_completed'
    PLANNER_RETURNED_NO_ACTIONS = 'planner_returned_no_actions'
    GOAL_CHECK_SATISFIED = 'goal_check_satisfied'
    NON_REPLANNABLE_FAILURE = 'non_replannable_failure'
    REPLAN_BUDGET_EXHAUSTED = 'replan_budget_exhausted'
    PLANNING_FAILED = 'planning_failed'
    EXECUTION_SKIPPED = 'execution_skipped'
    PREFLIGHT_ONLY = 'preflight_only'
    INFRASTRUCTURE = 'infrastructure'


@dataclass(frozen=True)
class FailureCodeInfo:
    check: FailureCheck
    legacy_layer: str
    taxonomy: Optional[Tuple[TaxonomyFamily, str]] = None
    emitted: bool = True
    phase: int = 1


_L1, _L2 = 'layer_1', 'layer_2'
_MP, _SA, _ED, _PI = (
    TaxonomyFamily.MOTION_PLANNING,
    TaxonomyFamily.SCENE_ACCESSIBILITY,
    TaxonomyFamily.EXECUTION_DEVIATION,
    TaxonomyFamily.PLAN_INCONSISTENCY,
)
_PLAN, _PRE, _EXE = FailureCheck.PLAN_CHECK, FailureCheck.PRE_ACTION_CHECK, FailureCheck.EXECUTION_FAILURE

FAILURE_CODE_INFO: Dict[FailureCode, FailureCodeInfo] = {
    FailureCode.UNKNOWN_ACTION_TOKEN: FailureCodeInfo(_PLAN, _L1, (_PI, 'Unknown action token')),
    FailureCode.PICK_PLACE_MISMATCH: FailureCodeInfo(_PLAN, _L1, (_PI, 'Pick-place mismatch')),
    FailureCode.ORPHAN_PLACE: FailureCodeInfo(_PLAN, _L1, (_PI, 'Orphan place')),
    FailureCode.MISSING_POST_PICK_PLACE: FailureCodeInfo(_PLAN, _L1, (_PI, 'Missing post-pick place')),
    FailureCode.UNOBSERVED_OBJECT: FailureCodeInfo(_PLAN, _L1),
    FailureCode.REMEMBERED_OBJECT_INACCESSIBLE: FailureCodeInfo(_PLAN, _L1, phase=2),
    FailureCode.PLANNER_OUTPUT_TOO_VERBOSE: FailureCodeInfo(_PLAN, _L1),
    FailureCode.PLANNER_OUTPUT_NOT_PARSEABLE: FailureCodeInfo(_PLAN, _L1),
    FailureCode.MISSING_PRECEDING_MOVE: FailureCodeInfo(_PLAN, _L1, emitted=False),
    FailureCode.INVALID_MOVE_TARGET: FailureCodeInfo(_PLAN, _L1, emitted=False),
    FailureCode.UNSUPPORTED_ACTION: FailureCodeInfo(_PLAN, _L1, emitted=False),
    FailureCode.CONSECUTIVE_MOVES: FailureCodeInfo(_PLAN, _L1, emitted=False),
    FailureCode.DANGLING_MOVE: FailureCodeInfo(_PLAN, _L1, emitted=False),
    FailureCode.INVALID_EXECUTOR_STATE: FailureCodeInfo(_PRE, _L1),
    FailureCode.PICK_OBJECT_MISSING: FailureCodeInfo(_PRE, _L1, (_SA, 'Pick object missing')),
    FailureCode.LID_MISSING: FailureCodeInfo(_PRE, _L1, (_SA, 'Lid missing')),
    FailureCode.GEOMETRIC_DISCOVERY_FAIL: FailureCodeInfo(_PRE, _L1),
    FailureCode.BOX_LID_CLOSED: FailureCodeInfo(_PRE, _L2, (_SA, 'Closed-box access')),
    FailureCode.GRILL_LID_CLOSED: FailureCodeInfo(_PRE, _L2, (_SA, 'Closed-box access')),
    FailureCode.BOX_LID_OBSTRUCTED: FailureCodeInfo(_PRE, _L2, (_SA, 'Lid blocked')),
    FailureCode.EMPTY_PICK_TRAJECTORY: FailureCodeInfo(_EXE, _L1, (_MP, 'Empty pick trajectory')),
    FailureCode.EMPTY_PLACE_TRAJECTORY: FailureCodeInfo(_EXE, _L1, (_MP, 'Empty place trajectory')),
    FailureCode.LID_HOVER_PLANNING_FAIL: FailureCodeInfo(_EXE, _L1, (_MP, 'Lid hover planning fail')),
    FailureCode.LID_SLIDE_PLANNING_FAIL: FailureCodeInfo(_EXE, _L1, (_MP, 'Lid slide planning fail')),
    FailureCode.PDDL_NO_PLAN: FailureCodeInfo(_EXE, _L1),
    FailureCode.NO_IK_SOLUTION: FailureCodeInfo(_EXE, _L1),
    FailureCode.NO_MOTION_PLAN: FailureCodeInfo(_EXE, _L1),
    FailureCode.NO_GRASP_FOUND: FailureCodeInfo(_EXE, _L1),
    FailureCode.EXECUTOR_FAILURE: FailureCodeInfo(_EXE, _L1),
    FailureCode.GRASP_FAILED: FailureCodeInfo(_EXE, _L2, (_ED, 'Grasp failed')),
    FailureCode.OBJECT_DROPPED: FailureCodeInfo(_EXE, _L2, (_ED, 'Object dropped')),
    FailureCode.OBJECT_DID_NOT_MOVE: FailureCodeInfo(_EXE, _L2),
    FailureCode.OBJECT_MISSING_AFTER_PLACE: FailureCodeInfo(_EXE, _L2),
    FailureCode.PLACEMENT_FAILED: FailureCodeInfo(_EXE, _L2, (_ED, 'Placement failed')),
    FailureCode.GEOMETRIC_PLACEMENT_FAILED: FailureCodeInfo(_EXE, _L2, (_ED, 'Placement failed')),
    FailureCode.LID_NOT_OPEN_ENOUGH: FailureCodeInfo(_EXE, _L2),
    FailureCode.LID_NOT_CLOSED_ENOUGH: FailureCodeInfo(_EXE, _L2),
    FailureCode.NEW_OBJECT_DISCOVERED: FailureCodeInfo(FailureCheck.TRIGGER, _L2),
    FailureCode.IF_RULE_TRIGGER: FailureCodeInfo(FailureCheck.TRIGGER, _L2, phase=4),
    FailureCode.GOAL_NOT_SATISFIED: FailureCodeInfo(FailureCheck.GOAL_CHECK, _L2),
    FailureCode.GOAL_VALIDATION_FAILED: FailureCodeInfo(FailureCheck.EVALUATION, _L2),
    FailureCode.PLANNER_CALL_FAILED: FailureCodeInfo(FailureCheck.INFRASTRUCTURE, _L1),
    FailureCode.SIMULATOR_ERROR: FailureCodeInfo(FailureCheck.INFRASTRUCTURE, _L1),
    FailureCode.REPLAN_BUDGET_EXHAUSTED: FailureCodeInfo(FailureCheck.REPLAN, _L1),
    FailureCode.REPEATED_PLANNER_OUTPUT: FailureCodeInfo(FailureCheck.REPLAN, _L1, emitted=False, phase=7),
    FailureCode.MEMORY_MISMATCH: FailureCodeInfo(FailureCheck.MEMORY, _L2, phase=2),
    FailureCode.INSERTION_TOO_LATE: FailureCodeInfo(FailureCheck.INSERTION, _L1, phase=5),
    FailureCode.INVALID_CORRECTIVE_BLOCK: FailureCodeInfo(FailureCheck.PLAN_CHECK, _L1, phase=5),
    FailureCode.ANCHOR_ALREADY_EXECUTED: FailureCodeInfo(FailureCheck.PARALLEL, _L1, phase=6),
    FailureCode.MERGE_CONFLICT: FailureCodeInfo(FailureCheck.PARALLEL, _L1, phase=6),
}

assert set(FAILURE_CODE_INFO) == set(FailureCode), 'every FailureCode needs a FailureCodeInfo entry'

LAYER_1_FAILURE_CODES: FrozenSet[FailureCode] = frozenset(
    code for code, info in FAILURE_CODE_INFO.items() if info.legacy_layer == _L1
)
LAYER_2_FAILURE_CODES: FrozenSet[FailureCode] = frozenset(
    code for code, info in FAILURE_CODE_INFO.items() if info.legacy_layer == _L2
)


# Codes shown to the planner model. A hidden object must look exactly like a name
# that does not exist, so unobserved_object is shown as unknown_action_token.
_PLANNER_FACING_CODES = {FailureCode.UNOBSERVED_OBJECT: FailureCode.UNKNOWN_ACTION_TOKEN}


def planner_facing_code(value) -> str:
    code = as_failure_code(value)
    return str(_PLANNER_FACING_CODES.get(code, value)) if code is not None else str(value)


def as_failure_code(value) -> Optional[FailureCode]:
    """Return the :class:`FailureCode` for a code or string, or ``None`` if unknown."""
    if isinstance(value, FailureCode):
        return value
    try:
        return FailureCode(str(value))
    except ValueError:
        return None


def failure_check_for(value) -> Optional[FailureCheck]:
    code = as_failure_code(value)
    return FAILURE_CODE_INFO[code].check if code is not None else None


def taxonomy_for(value) -> Optional[Tuple[TaxonomyFamily, str]]:
    code = as_failure_code(value)
    return FAILURE_CODE_INFO[code].taxonomy if code is not None else None


__all__ = [
    'CycleError',
    'FAILURE_CODE_INFO',
    'FailureCheck',
    'FailureCode',
    'FailureCodeInfo',
    'LAYER_1_FAILURE_CODES',
    'LAYER_2_FAILURE_CODES',
    'LegacyFailureId',
    'LegacyMessageCategory',
    'TaxonomyFamily',
    'TerminationReason',
    'as_failure_code',
    'failure_check_for',
    'planner_facing_code',
    'taxonomy_for',
]
