"""In-context examples for prompt v2 (``icl_mode = examples_v2`` / ``examples_v3``), grill scene only.

The examples come from a different scene (a laundry dryer) with the same kind of mechanism as the
grill: a wet towel is dried only by being inside the dryer while its door is closed and opened
again; a dry towel inside the dryer during another close/open is scorched; the dry towels go into a
basket that must be in the laundry area. No rule is stated: each example shows a good and a bad
answer in the prompt's own format, with what happened afterwards. They name no object, lid or region
of the grill scene, and they are appended to the unchanged zero-shot system prompt, so every other
part of the prompt (action definitions, output format, state, replan sections) is identical.
"""

ICL_MODE = 'examples_v2'

_EXAMPLE_FULL = """Example 1 (a request for a full plan)
## Goal
DRY all wet towels using the dryer and PUT all dry towels in the BASKET in the laundry area.
## Current state
Visible objects and the region each one is in:
- basket: shelf
- wet_towel_1: counter
Lids:
- dryer_door: closed (closes off inside_dryer)
Gripper: empty
Regions: counter, shelf, inside_dryer, basket_top, laundry_area

Good answer:
FINAL ACTIONS:
pick(basket)
place(basket, laundry_area)
open(dryer_door)
pick(wet_towel_1)
place(wet_towel_1, inside_dryer)
close(dryer_door)
open(dryer_door)
pick(wet_towel_1)
place(wet_towel_1, basket_top)
Outcome: the towel came out dry and is in the basket in the laundry area. Goal met.

Bad answer:
FINAL ACTIONS:
open(dryer_door)
pick(wet_towel_1)
place(wet_towel_1, inside_dryer)
pick(wet_towel_1)
place(wet_towel_1, basket_top)
Outcome: the towel is still wet, and the basket is still on the shelf. Goal not met."""

_EXAMPLE_CORRECTIVE = """Example 2 (a corrective request)
## Goal
DRY all wet towels using the dryer and PUT all dry towels in the BASKET in the laundry area.
## Current state
Visible objects and the region each one is in:
- basket: laundry_area
- wet_towel_1: counter
- dry_towel_2: inside_dryer
Lids:
- dryer_door: open (closes off inside_dryer)
Gripper: empty
Regions: counter, shelf, inside_dryer, basket_top, laundry_area
## Completed actions
- a1: pick(basket)
- a2: place(basket, laundry_area)
- a3: open(dryer_door)
## Remaining plan (not executed yet)
- a4: pick(wet_towel_1)
- a5: place(wet_towel_1, inside_dryer)
- a6: close(dryer_door)
- a7: open(dryer_door)
- a8: pick(wet_towel_1)
- a9: place(wet_towel_1, basket_top)
## Why a new plan is requested
- After open(dryer_door), these observed objects are not handled by the remaining plan:
  - dry_towel_2 (in inside_dryer): relevant to the goal, not in its goal state

Good answer:
FINAL BLOCKS:
BLOCK
objects: dry_towel_2
urgency: urgent
insert: front
reason: dry_towel_2 is already dry.
actions:
pick(dry_towel_2)
place(dry_towel_2, basket_top)
END BLOCK
Outcome: both towels are dry and in the basket. Goal met.

Bad answer:
FINAL BLOCKS:
BLOCK
objects: dry_towel_2
urgency: deferred
insert: end
reason: dry_towel_2 can be moved at the end.
actions:
pick(dry_towel_2)
place(dry_towel_2, basket_top)
END BLOCK
Outcome: dry_towel_2 was still inside during a6 and a7 and came out scorched. Goal not met."""

# examples_v3 adds a deferred corrective example from another unrelated scene (a germination chamber
# in a plant nursery): an item found inside while a cycle is scheduled is left in for the cycle and
# moved after it, the counterpart of Example 2 (an item already done is taken out first).
_EXAMPLE_DEFERRED = """Example 3 (a corrective request)
## Goal
GERMINATE all seed trays using the germination chamber and PUT all sprouted trays on the NURSERY BENCH.
## Current state
Visible objects and the region each one is in:
- seed_tray_1: potting_table
- seed_tray_2: inside_chamber
Lids:
- chamber_door: open (closes off inside_chamber)
Gripper: empty
Regions: potting_table, inside_chamber, nursery_bench
## Completed actions
- a1: open(chamber_door)
## Scheduled to run before your corrective block is applied (not executed yet)
- a2: pick(seed_tray_1)
- a3: place(seed_tray_1, inside_chamber)
- These actions run while you plan. Do not repeat them, and do not use their ids as an insertion point; the Current state does not include their effects yet.
## Remaining plan (not executed yet)
- a4: close(chamber_door)
- a5: open(chamber_door)
- a6: pick(seed_tray_1)
- a7: place(seed_tray_1, nursery_bench)
## Why a new plan is requested
- After open(chamber_door), these observed objects are not handled by the remaining plan:
  - seed_tray_2 (in inside_chamber): relevant to the goal, not in its goal state; does not lie where the remaining plan places objects

Good answer:
FINAL BLOCKS:
BLOCK
objects: seed_tray_2
urgency: deferred
insert: after a5
reason: seed_tray_2 has not germinated yet.
actions:
pick(seed_tray_2)
place(seed_tray_2, nursery_bench)
END BLOCK
Outcome: both trays sprouted during a4 and a5 and are on the nursery bench. Goal met.

Bad answer:
FINAL BLOCKS:
BLOCK
objects: seed_tray_2
urgency: urgent
insert: front
reason: seed_tray_2 must be moved before the door closes.
actions:
pick(seed_tray_2)
place(seed_tray_2, nursery_bench)
END BLOCK
Outcome: seed_tray_2 was taken out before a4 and a5 and never sprouted. Goal not met."""

_HEADER = 'Examples (from a different scene; its objects, lids and regions are not in your scene):\n\n'
EXAMPLES_TEXT = _HEADER + _EXAMPLE_FULL + '\n\n' + _EXAMPLE_CORRECTIVE
EXAMPLES_TEXT_V3 = ('Examples (from different scenes; their objects, lids and regions are not in your scene):\n\n'
                    + _EXAMPLE_FULL + '\n\n' + _EXAMPLE_CORRECTIVE + '\n\n' + _EXAMPLE_DEFERRED)
EXAMPLES_BY_MODE = {'examples_v2': EXAMPLES_TEXT, 'examples_v3': EXAMPLES_TEXT_V3}

# Scenes that get the examples: identified by a lid of the scene.
EXAMPLE_SCENE_LIDS = ('grill_lid',)


def examples_for(objects, mode: str = ICL_MODE) -> str:
    """The examples text of ``mode`` for a scene with these planner objects ('' when the scene has none)."""
    objects = set(objects or ())
    return EXAMPLES_BY_MODE[mode] if any(lid in objects for lid in EXAMPLE_SCENE_LIDS) else ''
