"""WHEN: what the robot may execute while a replan is generated (plan.md Phase 6).

``parallel.enabled = true`` with ``replan.output_mode = corrective``: after an IF-rule
trigger the planner call runs in the background while the robot executes the
**independent** bundles of the remaining plan, one at a time, in order.

Affected set of a replan:
* the trigger objects themselves;
* the region a trigger object is in (its container) **only if the object overlaps that
  region's placement area** (a non-overlapping object is not in the way, so placements
  into its container stay independent, e.g. the mugs into the box in K4);
* the goal regions of the trigger objects and the scene's parking regions (regions a
  corrective sub-plan may use; plan.md Section 10, Q10);
* lids that close off an affected region, and always the lid of a trigger object's
  container (closing it would change the trigger object's state, e.g. overcook a cooked
  meat left in the grill).

Bundles: a ``pick(o)`` immediately followed by ``place(o, r)`` is one bundle; every other
action (a lid action, a lone pick or place) is a bundle of its own. A bundle's pick source is
the region the object is in **when the bundle runs**, projected along the remaining plan
(e.g. the second pick of a meat that an earlier bundle put into the grill has source
``inside_grill``); its destinations are the place region, or for a lid action the regions the
lid closes off.

A bundle is dependent when it uses an affected object, places into an affected region, or
picks from an affected region that is not a parking region (taking an object out of a
parking area cannot conflict with parking something there). A dependent bundle blocks later
bundles (Phase 7c):
* through its objects: a later bundle using one of them is dependent;
* through its destinations: a later bundle placing into, or picking from, one of them is
  dependent;
* through its pick sources: a later bundle **placing into** one of them is dependent (the
  region is not freed until the dependent bundle runs, e.g. groceries must not fill the
  cupboard before mug3 is taken out of it). Picking from a shared source stays independent.
Independent bundles run in their plan order; they may run before an earlier dependent bundle
they share nothing with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from evaluation.labeled_rules import CATEGORY_GOAL_REGIONS, object_category
from llm_pipeline.metrics import parse_action_string
from llm_pipeline.region_aliases import normalize_region_name

# Regions a corrective sub-plan may use to move things out of the way (Section 10, Q10):
# only the dedicated areas. The whole table is not a parking region: with `table` in the
# affected set every pick from the table would wait for the replan.
PARKING_REGIONS: Dict[str, Tuple[str, ...]] = {
    'kitchen': ('table_staging_area',),
    'grill': ('prep_area',),
}
LID_REGIONS: Dict[str, Tuple[str, ...]] = {
    'box_lid': ('inside_box', 'box_lid_top'),
    'grill_lid': ('inside_grill',),
}


@dataclass
class PlanBundle:
    actions: List[Tuple[str, str]]              # (action id, action)
    objects: Set[str] = field(default_factory=set)
    regions: Set[str] = field(default_factory=set)
    sources: Set[str] = field(default_factory=set)        # regions picked from
    destinations: Set[str] = field(default_factory=set)   # regions placed into (or closed off by a lid action)

    @property
    def ids(self) -> List[str]:
        return [action_id for action_id, _ in self.actions]


def split_bundles(remaining: Sequence[Tuple[str, str]], object_regions: Mapping[str, Optional[str]]) -> List[PlanBundle]:
    """Group the remaining plan into bundles (pick+place pairs, other actions alone), with each
    pick's source region projected along the plan from the regions at the trigger."""
    bundles: List[PlanBundle] = []
    index = 0
    items = list(remaining)
    projected = {obj: region for obj, region in object_regions.items() if region}
    while index < len(items):
        action_id, action = items[index]
        parsed = parse_action_string(action) or {}
        name, args = parsed.get('action'), list(parsed.get('args') or [])
        bundle = PlanBundle([(action_id, action)])
        if name == 'pick' and index + 1 < len(items):
            next_parsed = parse_action_string(items[index + 1][1]) or {}
            if next_parsed.get('action') == 'place' and (next_parsed.get('args') or [None])[0] == args[0]:
                bundle.actions.append(items[index + 1])
                index += 1
        for _, member in bundle.actions:
            member_parsed = parse_action_string(member) or {}
            member_args = list(member_parsed.get('args') or [])
            kind = member_parsed.get('action')
            if kind == 'pick' and member_args:
                bundle.objects.add(member_args[0])
                if projected.get(member_args[0]):
                    source = normalize_region_name(projected[member_args[0]])
                    bundle.regions.add(source)
                    bundle.sources.add(source)
            elif kind == 'place' and len(member_args) >= 2:
                bundle.objects.add(member_args[0])
                bundle.regions.add(normalize_region_name(member_args[1]))
                bundle.destinations.add(normalize_region_name(member_args[1]))
                projected[member_args[0]] = member_args[1]
            elif kind in ('open_lid', 'close_lid', 'open_grill', 'close_grill', 'open', 'close') and member_args:
                bundle.objects.add(member_args[0])
                bundle.regions.update(LID_REGIONS.get(member_args[0], ()))
                bundle.destinations.update(LID_REGIONS.get(member_args[0], ()))
        bundles.append(bundle)
        index += 1
    return bundles


def affected_set(scene: str, trigger_objects: Iterable[str], object_regions: Mapping[str, Optional[str]],
                 overlapping: Optional[Mapping[str, Iterable[str]]] = None) -> Dict[str, List[str]]:
    """``overlapping``: per trigger object, the regions whose placement area its footprint
    intersects (system geometry). ``None`` keeps the containers unconditionally (callers
    without geometry)."""
    triggers = set(trigger_objects)
    objects = set(triggers)
    parking = set(PARKING_REGIONS.get(scene, ()))
    regions: Set[str] = set(parking)
    containers: Set[str] = set()
    for obj in triggers:
        container = normalize_region_name(object_regions.get(obj) or '')
        if container:
            containers.add(container)
            overlaps = None if overlapping is None else {normalize_region_name(r) for r in overlapping.get(obj) or ()}
            if overlaps is None or container in overlaps:
                regions.add(container)
        goal = CATEGORY_GOAL_REGIONS.get(object_category(obj))
        if goal:
            regions.add(goal)
    for lid, lid_regions in LID_REGIONS.items():
        if (regions | containers) & set(lid_regions):
            objects.add(lid)
    return {'objects': sorted(objects), 'regions': sorted(regions), 'parking_regions': sorted(parking)}


def independent_bundles(bundles: Sequence[PlanBundle], affected: Mapping[str, Sequence[str]]) -> List[PlanBundle]:
    blocked_objects = set(affected.get('objects') or ())
    affected_regions = set(affected.get('regions') or ())
    parking = set(affected.get('parking_regions') or ())
    blocked_destinations = set(affected_regions)
    blocked_sources = affected_regions - parking
    independent = []
    for bundle in bundles:
        if (bundle.objects & blocked_objects or bundle.destinations & blocked_destinations
                or bundle.sources & blocked_sources):
            # Later bundles depend on this one through its objects, where it puts them, and the
            # region it takes its object out of (nothing may be placed there before it runs).
            blocked_objects |= bundle.objects
            blocked_destinations |= bundle.destinations | bundle.sources
            blocked_sources |= bundle.destinations
            continue
        independent.append(bundle)
    return independent


__all__ = ['LID_REGIONS', 'PARKING_REGIONS', 'PlanBundle', 'affected_set', 'independent_bundles', 'split_bundles']
