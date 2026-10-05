# Simulation variants

Fourteen final variants are defined in `experiments/evaluation/final_variants.py`; converted scenes are in `assets/scenes/`. Legacy scenes support controller regression tests.

## Shared base layouts

**Kitchen base layout.** Derived from K3's table layout, which has the most table objects:
- `mug1` on the table (pantry_area);
- `mug2` on the box lid (box_lid_top);
- `mug3` in the cupboard (the scripted cupboard pick);
- `sugar` on the table (pantry_area);
- `spam` on the table (pantry_area).

In legacy K3, spam starts in the cupboard. In the base layout it moves to the table, so it becomes independent work.

**Grill base layout.** Derived from G2 (`grill_variation2`, steak and steak1 removed):
- exactly one raw meat beside the grill (`raw_meat_1` on prep_area; scene object chicken);
- `plate` in the dish_rack.

A cooking cycle is always required. The evaluated cardinality sweep includes one or two hidden meats in the far slots; the three-meat configuration is excluded because it cannot remain stably occluded.

**Labels.**
- Meats are renamed `raw_meat_<n>` or `cooked_meat_<n>`. They retain the original meshes: the drumstick for `raw_meat_1`, and steak meshes for the others.
- The phone keeps the name `phone`.
- The executor, symbol lists and grill semantic facts map these labels to scene objects.

**What differs between variants.** Families A, B and C1 differ only in the box or grill contents. C2 additionally adds groceries to the table.

## Placement areas

A *placement area* is the part of a region that the remaining plan's `place` actions into that region will use. The executor must place only inside it, and an object *overlaps* when its footprint intersects it.

| Region | Evaluated placement area | Rest of the region | Why |
|---|---|---|---|
| `inside_box` | robot-side half of the interior: x ∈ [−0.054, 0.111], y ∈ [0.187, 0.473] (16.5 × 28.6 cm, room for 4 mugs at their footprint) | far half x ∈ [0.111, 0.276]: used for *non-overlapping* hidden objects | K2/K4 need a place inside the box where a hidden object does not block mug placements |
| `inside_grill` | the single grill slot nearest the robot: x ∈ [0.287, 0.352], y ∈ [−0.189, −0.112]; the executor places every meat at (0.3195, −0.150) | y ∈ [−0.343, −0.189]: the far slots, where hidden meats are placed (x = 0.328; y = −0.295 and −0.237) | meat revealed in the grill is always non-overlapping  |
| `plate_top`, `cupboard_shelf`, `table_staging_area` | whole region | — | no hidden objects there |

The kitchen executor's box sampler is restricted to the placement area (`env.placement_areas`, `rlbench_kitchen_env.sample_stable_pose`), and the grill executor places into the fixed placement pose (`env.placement_poses`, `_region_slot_pose`). An automated check (`python -m evaluation.check_final_variants`) tests each hidden object's overlap status against its spec, footprint against placement area.

## Variant specs

For each variant below: the family, the point it proves, the hidden contents and their exact placement, the goal relations (R) and procedure checks (P), the expected IF decision, the expected urgency, the hard constraints checked by the evaluator, and the success condition. "Base" means the shared base layout above. The expected corrective sub-plans are reference answers for the evaluator only; they are **never** shown to the planner.

Two IF decisions come up repeatedly:
- **IF-irr:** "trigger, irrelevant_overlapping".
- **IF-rel:** "trigger, relevant_not_goal_attained".

Hard-constraint keys:
- **HC-box:** the trigger objects are out of the box placement area before the next `place` into the box.
- **HC-grill:** every `cooked_meat` is out of the grill before the next `close(grill_lid)`. Where it goes is the planner's choice ; the goal still requires it on the plate at the end.
- **HC-raw:** every `raw_meat` completes one cooking cycle before it is plated.

### Family A: basic

**K0**
- **Proves:** the kitchen reference, i.e. success, planner calls and trial time without any replan. No other variant has nothing hidden.
- **Hidden:** none; the box opens empty. Adapted from K1 by removing the soup.
- **R:** 3 mugs → inside_box; spam, sugar → cupboard_shelf. **P:** none.
- **IF:** no replan. **Urgency:** —.
- **Success:** all R satisfied.

**G0**
- **Proves:** the grill reference, i.e. the normal cook-and-serve procedure without a replan.
- **Hidden:** none; the grill opens empty.
- **R:** raw_meat_1 → plate_top; plate → serving_area. **P:** raw_meat_1 cooked, not overcooked, not served raw.
- **IF:** no replan. **Urgency:** —. **Constraints:** HC-raw.
- **Success:** R and P satisfied.

### Family B: core

**K1**
- **Proves:** an irrelevant object triggers a replan only when it overlaps, and it must be cleared before any mug goes in.
- **Hidden:** phone inside the box, **overlapping** (centre in the placement area, e.g. (0.03, 0.33)). The phone is a new asset for the kitchen scene, taken from the grill scene.
- **R:** base R, plus the phone ends outside every region's placement area (anywhere else; the planner decides, Q3). **P:** none.
- **IF:** IF-irr for the phone. **Urgency:** phone `urgent`.
- **Reference sub-plan (oracle):** `pick(phone)`, `place(phone, table)`. Any region outside every placement area is accepted .
- **Constraints:** HC-box. **Success:** R satisfied and HC-box respected.

**K2**
- **Proves:** a non-overlapping irrelevant object is ignored: no replan and no manipulation. This separates the IF rule from discovery-triggered replanning.
- **Hidden:** phone inside the box, **non-overlapping** (far half, e.g. (0.20, 0.33)).
- **R:** base R; the phone may stay in the box. **P:** none.
- **IF:** ignore. **Urgency:** —.
- **Success:** R satisfied. A manipulation of the phone is logged as an unnecessary action.

**K3**
- **Proves:** an overlapping relevant object must be handled before anything else goes into the box.
- **Hidden:** a grocery (`soup`) inside the box, **overlapping** (today's K1 position (0.07, 0.33) is in the placement area).
- **R:** base R, plus soup → cupboard_shelf. **P:** none.
- **IF:** IF-rel for the soup. **Urgency:** `urgent`.
- **Reference sub-plan:** `pick(soup)`, `place(soup, cupboard_shelf)`.
- **Constraints:** HC-box. **Success:** R and HC-box.

**K4**
- **Proves:** a relevant object that doesn't overlap still needs handling, but has no urgency.
- **Hidden:** a grocery (`soup`) inside the box, **non-overlapping** (far half, e.g. (0.20, 0.33)).
- **R:** base R, plus soup → cupboard_shelf. **P:** none.
- **IF:** IF-rel for the soup. **Urgency:** `deferred`.
- **Success:** R satisfied.

**G1**
- **Proves:** all corrective actions are urgent: stop and take both cooked meats out before continuing.
- **Hidden:** `cooked_meat_1` and `cooked_meat_2` inside the grill, in the far slots (outside the placement area).
- **R:** all 3 meats → plate_top; plate → serving_area. **P:** each meat cooked, not overcooked, not served raw; HC-grill for each cooked meat.
- **IF:** IF-rel for both. **Urgency:** both `urgent`.
- **Reference sub-plan:** take both out (to the plate or elsewhere, Q2) before the next close.
- **Constraints:** HC-grill, HC-raw. **Success:** R and P.

**G2**
- **Proves:** one replan with split urgency: the cooked meat comes out now, the raw meat stays to be cooked.
- **Hidden:** `cooked_meat_1` and `raw_meat_2` inside the grill, in the far slots.
- **R:** all 3 meats → plate_top; plate → serving_area. **P:** as G1.
- **IF:** IF-rel for both. **Urgency:** cooked_meat_1 `urgent`; raw_meat_2 `deferred`.
- **Constraints:** HC-grill, HC-raw. **Success:** R and P.

**G3**
- **Proves:** a replan with no urgency: the raw meat stays, is cooked in the normal cycle and is served later.
- **Hidden:** `raw_meat_2` and `raw_meat_3` inside the grill, in the far slots.
- **R:** all 3 meats → plate_top; plate → serving_area. **P:** each meat cooked, not overcooked, not served raw.
- **IF:** IF-rel for both. **Urgency:** both `deferred`.
- **Constraints:** HC-raw. **Success:** R and P.

### Family C: cardinality

Each sweep changes exactly one count, and everything else equals the core variant it starts from.

**C1: number of trigger objects revealed at once** (everything urgent)

| Variant | Hidden contents | n |
|---|---|---|
| K3 | 1 overlapping grocery (soup) in the box placement area | 1 |
| K3-n2 | soup and a second can, both overlapping | 2 |
| K3-n3 | soup and two more cans, all overlapping | 3 |
| G1-n1 | 1 cooked_meat in the grill | 1 |
| G1 | 2 cooked_meat | 2 |
| ~~G1-n3~~ | dropped: 3 meats do not fit outside the grill placement area  | — |

- **Measured:** corrective sub-plan correctness, urgency accuracy per object, sub-plan length and planner-call latency against n.
- **Constraints:** HC-box for the kitchen members; HC-grill and HC-raw for the grill members.

**C2: amount of independent work** (the WHEN sweep)

| Variant | Hidden | Extra groceries on the table (→ cupboard) | w |
|---|---|---|---|
| K1 | overlapping phone | 0 | 0 |
| K1-w1 | same | +1 (`can_of_beans` on the table) | 1 |
| K1-w2 | same | +2 (`can_of_beans`, `can_of_beans_2`) | 2 |

The evaluated width sweep uses w = 0, 1, 2. The cupboard placement rules below provide sufficient room for the five groceries in K3-n3 and four in K1-w2.

The extra groceries go to the cupboard, so they don't touch the phone's replan (box, phone, region outside the placement area).

## Coverage matrix

| Point proven | K0 | G0 | K1 | K2 | K3 | K4 | G1 | G2 | G3 | C1 | C2 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Reference without replan (kitchen) | ● | | | | | | | | | | |
| Reference without replan (grill) | | ● | | | | | | | | | |
| Irrelevant + overlapping → replan, urgent | | | ● | | | | | | | | |
| Irrelevant + not overlapping → ignored | | | | ● | | | | | | | |
| Relevant + overlapping → replan, urgent | | | | | ● | | | | | | |
| Relevant + not overlapping → replan, deferred | | | | | | ● | | | | | |
| Cooked meat revealed → urgent (all) | | | | | | | ● | | | | |
| Mixed urgency in one replan | | | | | | | | ● | | | |
| Raw meat revealed → deferred (all) | | | | | | | | | ● | | |
| Scaling in trigger count (trend) | | | | | | | | | | ● | |
| Scaling in independent work (trend) | | | | | | | | | | | ● |

One variant covers each point in families A and B, and one family covers each trend.

## Cupboard placement

The cupboard is shared by every kitchen variant. From the cupboard model: lower shelf top z = 1.222, upper shelf underside z = 1.528 (30.6 cm clearance), side walls' inner faces at y = ±0.258 (51.6 cm), open front at x = 0.434, back wall at x = 0.745. Placement sampling uses the following rules:
- **Usable region:** the whole interior width, 2 cm from each side wall (fingers + margin); objects are placed at the front.
- **Free spots only:** an object's width plus 1 cm on each side must be clear of every other object on the shelf (an object sticking out past the open front blocks 2 cm more on each side, where the hand passes); a full shelf gives no sample (the place then has no plan).
- **Order:** spots are grouped into the gaps between objects and walls; the planner's successive samples take the tightest spot of each gap in turn (gaps in order of their tightest spot), so every gap is tried early.
- **Orientation:** a non-round grocery is picked top-down with the fingers closing exactly across its thinner horizontal side (in the pose it rests in: upright, or lying on a face after being knocked over), and inserted with the fingers closing horizontally, so it lies with that side across the shelf: sugar 3.5 cm upright , spam about 5 cm . Cans (round) keep the previous hand roll (5.5 cm).
- **Insertion height:** the tip starts at the height that puts the object 1 cm above the shelf and goes up in steps until the insertion path is collision-free (thin-side: 1 cm steps up to 9 cm; cans: 2 cm steps up to 8 cm).

Widths across the shelf: K3-n3 (3 cans, spam, sugar) about 25 cm plus margins; K1-w2 (2 cans, spam, sugar) about 19.5 cm plus margins; both well inside the 47.6 cm usable width.
