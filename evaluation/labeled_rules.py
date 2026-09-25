"""Label-based goal and procedure rules for the final (Phase 3) scene files.

plan.md Phase 1, step 4, with the decisions from Section 10:

* Meat objects are identified by label: ``cooked_meat*`` starts cooked;
  ``raw_meat*`` becomes cooked after exactly one close->reopen cycle of the
  grill lid while it is inside the grill.
* Overcooked: an already-cooked meat is inside the grill during another
  close->reopen cycle. A ``cooked_meat`` that starts in the grill is therefore
  overcooked by the first close->reopen. Overcooking fails that meat's
  procedure check (the trial fails; partial goal completion still counts the
  other meats).
* A ``raw_meat`` placed on the plate before its cycle ("served raw") fails its
  procedure check.
* Goal: every meat on the plate, the plate in the serving area, every mug in
  the box, every grocery in the cupboard. The phone must not be in the box's
  placement area at the end (anywhere else is fine).

These rules apply only to variants listed in :data:`LABELED_RULE_VARIANTS`
(the Phase 3 scene files); today's scenes keep ``llm_pipeline.metrics``
unchanged. :func:`meat_procedure_status` is the single implementation of the
cooking procedure: the evaluator feeds it ground truth, and the Phase 4 IF rule
must feed it only information the agent has (action history, visible state,
memory).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set

from llm_pipeline.metrics import _normalize_region, _normalize_token, _validator_result, parse_action_string

# Variant ids evaluated with these rules. Filled in Phase 3 when the final scene
# files exist; until then every variant uses llm_pipeline.metrics.
LABELED_RULE_VARIANTS: Set[str] = set()

GRILL_LID = 'grill_lid'
INSIDE_GRILL = 'inside_grill'
PLATE_TOP = 'plate_top'

# Relevant categories per scene (plan.md Section 0.3; confirm in Section 10, Q8).
SCENE_GOAL_CATEGORIES: Dict[str, tuple] = {
    'kitchen': ('mug', 'grocery'),
    'grill': ('raw_meat', 'cooked_meat'),
}
CATEGORY_GOAL_REGIONS: Dict[str, str] = {
    'mug': 'inside_box',
    'grocery': 'cupboard_shelf',
    'raw_meat': PLATE_TOP,
    'cooked_meat': PLATE_TOP,
    'plate': 'serving_area',
}
GROCERY_NAMES = frozenset({'can_of_beans', 'soup', 'mustard', 'spam', 'sugar', 'crackers'})
MEAT_CATEGORIES = ('raw_meat', 'cooked_meat')


def object_category(object_name: str) -> Optional[str]:
    """Category of an object from its label (``raw_meat_2`` -> ``raw_meat``)."""
    name = _normalize_token(object_name)
    for prefix in ('raw_meat', 'cooked_meat', 'mug', 'phone', 'plate'):
        if name == prefix or name.startswith(prefix) and name[len(prefix):].lstrip('_').isdigit():
            return prefix
    base = name.rstrip('0123456789').rstrip('_')
    if name in GROCERY_NAMES or base in GROCERY_NAMES:
        return 'grocery'
    return None


@dataclass
class MeatProcedureStatus:
    meat: str
    category: str
    cooking_cycles: int = 0
    cooked: bool = False
    overcooked: bool = False
    served_raw: bool = False
    events: List[str] = field(default_factory=list)

    @property
    def satisfied(self) -> bool:
        return self.cooked and not self.overcooked and not self.served_raw

    def failure_reason(self) -> Optional[str]:
        if self.overcooked:
            return f'{self.meat} overcooked: inside the grill during a close->reopen cycle after it was cooked'
        if self.served_raw:
            return f'{self.meat} placed on {PLATE_TOP} before completing a cooking cycle'
        if not self.cooked:
            return f'{self.meat} never completed a cooking cycle'
        return None


def meat_procedure_status(
    meat: str,
    category: str,
    initial_region: Optional[str],
    action_history: Sequence[object],
) -> MeatProcedureStatus:
    """Replay ``action_history`` symbolically and return the meat's cooking status.

    ``initial_region`` is the meat's region at the start of the trial. A cycle
    counts for the meat when it is inside the grill at ``close(grill_lid)``; it
    cannot move while the lid is closed, so it is still inside at the reopen.
    """
    if category not in MEAT_CATEGORIES:
        raise ValueError(f'{meat}: category must be one of {MEAT_CATEGORIES}, got {category!r}')
    meat = _normalize_token(meat)
    status = MeatProcedureStatus(meat=meat, category=category)
    level = 1 if category == 'cooked_meat' else 0
    inside = _normalize_region(initial_region) == INSIDE_GRILL
    inside_at_close: Optional[bool] = None
    for raw in action_history:
        action = parse_action_string(raw) if not isinstance(raw, dict) else raw
        if action is None:
            continue
        name, args = action.get('action'), list(action.get('args') or [])
        target = args[0] if args else None
        if name == 'pick' and target == meat:
            inside = False
        elif name == 'place' and target == meat and len(args) >= 2:
            region = _normalize_region(args[1])
            inside = region == INSIDE_GRILL
            if region == PLATE_TOP and level == 0:
                status.served_raw = True
                status.events.append(f'served raw: {raw}')
        elif name == 'close_lid' and target == GRILL_LID:
            inside_at_close = inside
        elif name in ('open_lid', 'open_grill') and target == GRILL_LID and inside_at_close is not None:
            if inside_at_close:
                if level >= 1:
                    status.overcooked = True
                    status.events.append(f'overcooked in cycle ending at: {raw}')
                level += 1
                status.cooking_cycles += 1
            inside_at_close = None
    status.cooked = level >= 1
    return status


def validate_labeled_goal(
    scene: str,
    variant_id: str,
    object_region_map: Mapping[str, str],
    completed_actions: Sequence[object],
    initial_object_region_map: Mapping[str, str],
    placement_area_objects: Optional[Mapping[str, Iterable[str]]] = None,
) -> Dict[str, object]:
    """Goal relations and procedure checks for a Phase 3 variant.

    ``object_region_map`` / ``initial_object_region_map``: ground-truth final and
    initial regions of every object in the scene. ``placement_area_objects``:
    region -> objects whose footprint is in that region's placement area at the
    end (needed when a phone is present).
    """
    scene = str(scene).strip().lower()
    if scene not in SCENE_GOAL_CATEGORIES:
        raise ValueError(f'Unknown scene {scene!r}')
    final = {_normalize_token(name): _normalize_region(region) for name, region in (object_region_map or {}).items()}
    initial = {
        _normalize_token(name): _normalize_region(region) for name, region in (initial_object_region_map or {}).items()
    }
    all_objects = sorted(set(final) | set(initial))
    satisfied_relations: List[str] = []
    missing_relations: List[str] = []
    satisfied_procedures: List[str] = []
    missing_procedures: List[str] = []
    procedure_details: Dict[str, Dict[str, object]] = {}

    relevant = set(SCENE_GOAL_CATEGORIES[scene])
    goal_objects = [name for name in all_objects if object_category(name) in relevant]
    if scene == 'grill':
        goal_objects += [name for name in all_objects if object_category(name) == 'plate']
    for name in goal_objects:
        goal_region = CATEGORY_GOAL_REGIONS[object_category(name)]
        observed = final.get(name)
        if observed == goal_region:
            satisfied_relations.append(f'{name} in {goal_region}')
        else:
            missing_relations.append(f'{name} is in {observed or "unknown"}, expected {goal_region}')

    phones = [name for name in all_objects if object_category(name) == 'phone']
    if phones:
        if placement_area_objects is None:
            raise ValueError('placement_area_objects is required when a phone is present')
        in_box_area = {_normalize_token(name) for name in (placement_area_objects.get('inside_box') or ())}
        for name in phones:
            if name in in_box_area:
                missing_relations.append(f'{name} is in the inside_box placement area')
            else:
                satisfied_relations.append(f'{name} not in inside_box placement area')

    for name in all_objects:
        category = object_category(name)
        if category not in MEAT_CATEGORIES:
            continue
        status = meat_procedure_status(name, category, initial.get(name), completed_actions)
        procedure_details[name] = {
            'category': category,
            'cooking_cycles': status.cooking_cycles,
            'cooked': status.cooked,
            'overcooked': status.overcooked,
            'served_raw': status.served_raw,
            'events': list(status.events),
        }
        check = f'{name} cooked, not overcooked, not served raw'
        if status.satisfied:
            satisfied_procedures.append(check)
        else:
            missing_procedures.append(status.failure_reason())

    return _validator_result(
        str(variant_id).strip().upper(),
        f'{scene}_labeled_rules',
        {
            'object_region_map': final,
            'initial_object_region_map': initial,
            'procedures': procedure_details,
        },
        missing_relations=missing_relations,
        satisfied_relations=satisfied_relations,
        missing_procedures=missing_procedures,
        satisfied_procedures=satisfied_procedures,
    )


def uses_labeled_rules(variant_id: str) -> bool:
    return str(variant_id or '').strip().upper() in LABELED_RULE_VARIANTS


__all__ = [
    'CATEGORY_GOAL_REGIONS',
    'LABELED_RULE_VARIANTS',
    'MeatProcedureStatus',
    'SCENE_GOAL_CATEGORIES',
    'meat_procedure_status',
    'object_category',
    'uses_labeled_rules',
    'validate_labeled_goal',
]
