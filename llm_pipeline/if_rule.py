"""IF: the replan trigger rule (plan.md Phase 4, ``replan.trigger_mode = if_rule``).

After every observation the system evaluates every observed object (visible or
remembered) that the remaining plan does not account for:

| Relevant? | Goal-attained? | Overlapping? | Decision                              |
|-----------|----------------|--------------|---------------------------------------|
| no        | -              | yes          | trigger (``irrelevant_overlapping``)   |
| no        | -              | no           | ignore                                |
| yes       | no             | any          | trigger (``relevant_not_goal_attained``) |
| yes       | yes            | -            | ignore                                |

* relevant: the object's category is one of the scene's goal categories
  (``evaluation.labeled_rules.SCENE_GOAL_CATEGORIES``; plan.md Section 10, Q8);
* goal-attained: in its goal region with its procedure complete, computed with the
  evaluator's procedure logic (:func:`evaluation.labeled_rules.meat_procedure_status`)
  fed only with what the agent has: its action history and the regions it observed. A
  meat counts as complete once cooked: overcooking and plating before cooking cannot be
  undone, so they are left to the evaluator instead of triggering endless replans;
* overlapping: the object's footprint intersects the placement area of a region the
  remaining plan will ``place`` into (computed by the system from geometry and
  passed in as a callable; coordinates never reach the planner model);
* accounted for: the remaining plan (or a pending replan) already has an action on it.

All trigger objects found in one observation are handled by one replan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from evaluation.labeled_rules import (
    CATEGORY_GOAL_REGIONS,
    MEAT_CATEGORIES,
    SCENE_GOAL_CATEGORIES,
    meat_procedure_status,
    object_category,
)
from llm_pipeline.metrics import parse_action_string
from llm_pipeline.region_aliases import normalize_region_name

IRRELEVANT_OVERLAPPING = 'irrelevant_overlapping'
RELEVANT_NOT_GOAL_ATTAINED = 'relevant_not_goal_attained'
TRIGGER = 'trigger'
IGNORE = 'ignore'
# Articulated parts are never trigger objects.
NON_OBJECTS = frozenset({'box_lid', 'grill_lid', 'lid'})


@dataclass(frozen=True)
class ObjectAssessment:
    object_id: str
    region: Optional[str]
    category: Optional[str]
    relevant: bool
    goal_attained: Optional[bool]     # None for irrelevant objects
    overlapping: bool
    accounted_for: bool
    decision: str                     # trigger / ignore
    trigger_kind: Optional[str]       # irrelevant_overlapping / relevant_not_goal_attained
    overlapping_regions: tuple = ()

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data['overlapping_regions'] = list(self.overlapping_regions)
        return data


def objects_in_actions(actions: Iterable[object]) -> Set[str]:
    names = set()
    for raw in actions or ():
        parsed = parse_action_string(str(raw))
        if parsed and parsed.get('args') and parsed['action'] in ('pick', 'place'):
            names.add(parsed['args'][0])
    return names


def place_regions(actions: Iterable[object]) -> List[str]:
    """Regions the actions ``place`` into, in order of first use."""
    regions: List[str] = []
    for raw in actions or ():
        parsed = parse_action_string(str(raw))
        if parsed and parsed['action'] == 'place' and len(parsed.get('args') or []) >= 2:
            region = normalize_region_name(parsed['args'][1])
            if region not in regions:
                regions.append(region)
    return regions


def is_relevant(scene: str, object_id: str) -> bool:
    return object_category(object_id) in SCENE_GOAL_CATEGORIES.get(scene, ())


def is_goal_attained(
    object_id: str,
    region: Optional[str],
    completed_actions: Sequence[object],
    initial_region: Optional[str],
) -> bool:
    category = object_category(object_id)
    goal_region = CATEGORY_GOAL_REGIONS.get(category)
    if goal_region is None or normalize_region_name(region or '') != goal_region:
        return False
    if category in MEAT_CATEGORIES:
        # Cooked and on the plate: nothing is left to do. Overcooking or plating before
        # cooking cannot be undone; they are evaluator penalties, not reasons to replan.
        return meat_procedure_status(object_id, category, initial_region, completed_actions).cooked
    return True


def assess_objects(
    scene: str,
    object_regions: Mapping[str, Optional[str]],
    remaining_plan: Sequence[object],
    completed_actions: Sequence[object],
    initial_regions: Mapping[str, Optional[str]],
    overlapping: Callable[[str, Sequence[str]], Sequence[str]],
    pending_objects: Iterable[str] = (),
    held_object: Optional[str] = None,
) -> List[ObjectAssessment]:
    """Apply the IF rule to every observed object.

    ``overlapping(object_id, regions)`` returns the regions among ``regions`` whose
    placement area the object's footprint intersects.
    """
    accounted = objects_in_actions(remaining_plan) | set(pending_objects or ())
    target_regions = place_regions(remaining_plan)
    results = []
    for object_id in sorted(object_regions):
        if object_id in NON_OBJECTS or object_id == held_object:
            continue
        region = object_regions.get(object_id)
        relevant = is_relevant(scene, object_id)
        is_accounted = object_id in accounted
        overlap_regions = tuple(overlapping(object_id, target_regions) or ()) if target_regions else ()
        goal_attained = (is_goal_attained(object_id, region, completed_actions, initial_regions.get(object_id))
                         if relevant else None)
        kind = None
        if not is_accounted:
            if not relevant and overlap_regions:
                kind = IRRELEVANT_OVERLAPPING
            elif relevant and not goal_attained:
                kind = RELEVANT_NOT_GOAL_ATTAINED
        results.append(ObjectAssessment(
            object_id=object_id, region=region, category=object_category(object_id), relevant=relevant,
            goal_attained=goal_attained, overlapping=bool(overlap_regions), accounted_for=is_accounted,
            decision=TRIGGER if kind else IGNORE, trigger_kind=kind, overlapping_regions=overlap_regions,
        ))
    return results


def trigger_objects(assessments: Sequence[ObjectAssessment]) -> List[ObjectAssessment]:
    return [a for a in assessments if a.decision == TRIGGER]


def describe_trigger(assessment: ObjectAssessment, region_name: Callable[[str], str] = lambda r: r) -> str:
    """Plain-fact label of a trigger object for the replan prompt (no advice)."""
    where = region_name(assessment.region) if assessment.region else 'unknown region'
    areas = ', '.join(region_name(r) for r in assessment.overlapping_regions)
    overlap = (f'lies where the remaining plan places objects into {areas}' if areas
               else 'does not lie where the remaining plan places objects')
    if assessment.relevant:
        return f'{assessment.object_id} (in {where}): relevant to the goal, not in its goal state; {overlap}'
    return f'{assessment.object_id} (in {where}): not relevant to the goal; {overlap}'


__all__ = [
    'IGNORE', 'IRRELEVANT_OVERLAPPING', 'ObjectAssessment', 'RELEVANT_NOT_GOAL_ATTAINED', 'TRIGGER',
    'assess_objects', 'describe_trigger', 'is_goal_attained', 'is_relevant', 'objects_in_actions',
    'place_regions', 'trigger_objects',
]
