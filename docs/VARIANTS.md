# Final variant set (plan.md Phase 3)

**Status: approved, built.** Section 7 records the decisions (plan.md Section 10, Q2–Q6 and Q12). The registry is `evaluation/final_variants.py`, the scenes are `mujoco_port/scenes/final_<name>/` (built by `mujoco_port/tools/compose_variant.py`), and variant ids are `FINAL.<name>` (`--variant final.K1`).

Terminology follows plan.md 0.6. Region names are the canonical internal ones; prompt v2 shows `table_staging_area` as `table_center_area`, `pantry_area` as `table_right_area` and `prep_area` as `grill_side_area`.

## 1. Audit of the current variants

The audit is taken from the MuJoCo scene files (`mujoco_port/scenes/`), the initial segmentation snapshot of each scene, and `llm_pipeline/metrics.py`. Hidden objects are the ones not visible at the first observation.

| Variant | Scene file | Visible at start (region) | Hidden at start (where) | Lid | Goal relations (evaluator today) |
|---|---|---|---|---|---|
| K1 | `task1_variation1` | mug2 (box_lid_top), mug3 (cupboard_shelf), spam (pantry_area) | soup = `can_of_beans` (inside_box) | box_lid closed | mug2, mug3 → inside_box; can_of_beans, spam → cupboard_shelf |
| K2 | `task1_variation2` | mug2 (box_lid_top), mug3 (cupboard_shelf), sugar (pantry_area) | soup (inside_box), mug1 (inside_box, already goal-attained) | closed | mug2, mug3 → inside_box; sugar, can_of_beans → cupboard_shelf |
| K3 | `task1_variation3` | mug1 (pantry_area), mug2 (box_lid_top), mug3 (cupboard_shelf), spam (cupboard_shelf), sugar (pantry_area) | soup (inside_box) | closed | mug1–3 → inside_box; sugar, can_of_beans → cupboard_shelf |
| G1 | `grill_variation1` | chicken (prep_area), plate (dish_rack) | phone (inside_grill) | grill_lid closed | chicken → plate_top (cooked); plate → serving_area; phone → table |
| G2 | `grill_variation2` | chicken, steak1 (prep_area), plate (dish_rack) | steak (inside_grill, treated as cooked) | closed | steak, chicken, steak1 → plate_top (chicken and steak1 cooked); plate → serving_area |
| G3 | `grill_variation3` | chicken, steak1 (prep_area), plate (dish_rack) | steak, phone (inside_grill) | closed | as G2, plus phone → table |

Geometry (world AABBs):
- **Box interior** (`box_boundary`): 33.0 × 28.6 cm.
- **Cupboard shelf** (`cupboard_boundary`): 9.3 × 37.3 cm, plus an upper shelf (`cupboard_boundary_top`) of 1.6 × 23.1 cm.
- **Grill interior** (`grill_boundary`): 6.5 × 23.1 cm.
- **Grill side area** (`prep_area`): 14.0 × 18.6 cm.
- **Footprints:**
  - mug 9.7 × 6.6 cm (including the handle);
  - soup can 5.5 × 5.5 cm;
  - spam 10 × 5 cm;
  - sugar 3.5 × 9 cm;
  - meats about 10.5 × 5 cm;
  - phone 8.7 × 2.5 cm;
  - plate 20.4 cm diameter.

Executor ceiling today: 60/60 oracle trials (`results/executor_ceiling/`).

## 2. Shared base layouts

**Kitchen base layout.** Derived from K3's table layout, which has the most table objects:
- `mug1` on the table (pantry_area);
- `mug2` on the box lid (box_lid_top);
- `mug3` in the cupboard (the scripted cupboard pick);
- `sugar` on the table (pantry_area);
- `spam` on the table (pantry_area).

In K3 today, spam starts in the cupboard. In the base layout it moves to the table, so it becomes independent work.

**Grill base layout.** Derived from G2 (`grill_variation2`, steak and steak1 removed; Q12):
- exactly one raw meat beside the grill (`raw_meat_1` on prep_area; today's chicken);
- `plate` in the dish_rack.

So a cooking cycle is always required (plan.md 3.2), and up to three hidden meats fit in the grill's far slots.

**Labels.**
- Meats are renamed `raw_meat_<n>` or `cooked_meat_<n>`. They keep today's meshes: the drumstick for `raw_meat_1`, and steak meshes for the others.
- The phone keeps the name `phone`.
- The executor, symbol lists and grill semantic facts gain the label prefixes (build item B4).

**What differs between variants.** Families A, B and C1 differ only in the box or grill contents. C2 additionally adds groceries to the table.

## 3. Placement areas (config; your decision, Q4)

A *placement area* is the part of a region that the remaining plan's `place` actions into that region will use. The executor must place only inside it, and an object *overlaps* when its footprint intersects it.

| Region | Proposed placement area | Rest of the region | Why |
|---|---|---|---|
| `inside_box` | robot-side half of the interior: x ∈ [−0.054, 0.111], y ∈ [0.187, 0.473] (16.5 × 28.6 cm, room for 4 mugs at their footprint) | far half x ∈ [0.111, 0.276]: used for *non-overlapping* hidden objects | K2/K4 need a place inside the box where a hidden object does not block mug placements |
| `inside_grill` | the single grill slot nearest the robot: x ∈ [0.287, 0.352], y ∈ [−0.189, −0.112]; the executor places every meat at (0.3195, −0.150) | y ∈ [−0.343, −0.189]: the far slots, where hidden meats are placed (2 meats at y = −0.300, −0.237; 3 at −0.316, −0.264, −0.212) | plan.md: meat revealed in the grill is always non-overlapping (Q12) |
| `plate_top`, `cupboard_shelf`, `table_staging_area` | whole region | — | no hidden objects there |

The kitchen executor's box sampler is restricted to the placement area (`env.placement_areas`, `rlbench_kitchen_env.sample_stable_pose`), and the grill executor places into the fixed placement pose (`env.placement_poses`, `_region_slot_pose`). An automated check (`python -m evaluation.check_final_variants`) tests each hidden object's overlap status against its spec, footprint against placement area.

## 4. Variant specs

For each variant below: the family, the point it proves, the hidden contents and their exact placement, the goal relations (R) and procedure checks (P), the expected IF decision, the expected urgency, the hard constraints checked by the evaluator, and the success condition. "Base" means the base layout of section 2. The expected corrective sub-plans are reference answers for the evaluator only; they are **never** shown to the planner.

Two IF decisions come up repeatedly:
- **IF-irr:** "trigger, irrelevant_overlapping".
- **IF-rel:** "trigger, relevant_not_goal_attained".

Hard-constraint keys:
- **HC-box:** the trigger objects are out of the box placement area before the next `place` into the box.
- **HC-grill:** every `cooked_meat` is out of the grill before the next `close(grill_lid)`. Where it goes is the planner's choice (Q2); the goal still requires it on the plate at the end.
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
- **Reference sub-plan (oracle):** `pick(phone)`, `place(phone, table)`. Any region outside every placement area is accepted (Q3).
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
| G1-n3 | 3 cooked_meat | 3 |

- **Measured:** corrective sub-plan correctness, urgency accuracy per object, sub-plan length and planner-call latency against n.
- **Constraints:** HC-box for the kitchen members; HC-grill and HC-raw for the grill members.

**C2: amount of independent work** (the WHEN sweep)

| Variant | Hidden | Extra groceries on the table (→ cupboard) | w |
|---|---|---|---|
| K1 | overlapping phone | 0 | 0 |
| K1-w1 | same | +1 (`can_of_beans` on the table) | 1 |
| K1-w2 | same | +2 (`can_of_beans`, `can_of_beans_2`) | 2 |

(Reduced from w = 0, 2, 4 by Q12: the cupboard shelf holds about 4 groceries.)

The extra groceries go to the cupboard, so they don't touch the phone's replan (box, phone, region outside the placement area).

## 5. Coverage matrix

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

## 6. How each variant is built

All kitchen variants start from `task1_variation3` with the soup removed from the box and spam moved to the table at (0.27, −0.35); all grill variants start from `grill_variation2` with steak and steak1 removed. Edits are listed in `evaluation/final_variants.py` and applied by `compose_variant.py` (remove, move, or copy an object subtree from any extracted scene with new handles, names, geometry keys and textures). The source `.ttt` files are untouched.

| Final | Edits on the base | Scene objects → labels |
|---|---|---|
| K0 | — | mug1–3, spam, sugar |
| K1 / K2 | phone copied from `grill_variation1` to (0.03, 0.33) / (0.20, 0.33) on the box floor | + phone |
| K3 / K4 | soup moved to (0.07, 0.33) / (0.20, 0.33) | + soup → can_of_beans |
| K3-n2 | soup at (0.02, 0.26), copy soup2 at (0.02, 0.40) | + can_of_beans, can_of_beans_2 |
| K3-n3 | as K3-n2, plus soup3 at (0.075, 0.33) | + can_of_beans_3 |
| K1-w1 / K1-w2 | K1, plus soup on the table at (−0.10, −0.36) / plus soup2 at (0.42, −0.30) | + can_of_beans (, can_of_beans_2) |
| G0 | — | chicken → raw_meat_1, plate |
| G1 | steak moved and steak2 copied into the far slots | + cooked_meat_1, cooked_meat_2 |
| G2 | steak and steak1 into the far slots | + cooked_meat_1, raw_meat_2 |
| G3 | steak and steak2 into the far slots | + raw_meat_2, raw_meat_3 |
| G1-n1 | steak into the far slot | + cooked_meat_1 |
| G1-n3 | steak, steak2, steak3 into the three far slots | + cooked_meat_1–3 |

Scene objects keep the names the executor knows. The planner, the trial log and the evaluator use the labels (`llm_pipeline/object_aliases.set_variant_labels`). Old variants K1–K3 and G1–G3 stay in the repository for regression only and are not reported (Q5).

## 7. Decisions (answered)

1. **Q2:** a cooked meat removed urgently may go anywhere outside the grill; the planner decides. Evaluator: HC-grill (out of the grill before the next `close(grill_lid)`) plus the goal (on the plate at the end).
2. **Q3:** the phone may go anywhere outside the box's placement area, but not into any other region's placement area; the planner decides.
3. **Q4:** placement areas approved, with the grill area changed to the single nearest slot (Q12). Verify with the oracle that in K2 and K4 all mugs fit in the box without moving the hidden object.
4. **Q5:** today's K1–K3 and G1–G3 for regression only, not reported.
5. **Q6:** no goal-attained variant.
6. **Q12:** grill placement area = the single slot nearest the robot for every grill variant; exactly one raw meat outside the grill in the base layout, so G1-n3's three hidden meats fit in the far slots (if not, cut the sweep to n = 1, 2). C2 is w = 0, 1, 2.

## 8. Build plan after approval

- **B1:** a scene composition tool, `mujoco_port/tools/compose_variant.py`. It builds a new scene from a base scene by removing, adding or moving objects. Added objects come from any extracted scene, with new unique handles for segmentation. It writes `mujoco_port/scenes/<variant>/`, and the source `.ttt` files are untouched.
- **B2:** variant registry entries (`evaluation/canonical_variants.py`) for the 15 variants, the goal texts (unchanged), and `LABELED_RULE_VARIANTS`.
- **B3:** placement-area config, and the executor's box sampler restricted to the placement area.
- **B4:** meat labels (`raw_meat_*`, `cooked_meat_*`) in the executor symbol lists, grill semantic facts and executor meat detection.
- **B5:** GT action sequences and oracle support for every new variant.
- **B6:** automated tests. All 15 variants load, every hidden object's overlap status matches its spec, and the feasibility check passes. Then an executor-ceiling oracle run on all 15, and baseline-system runs saved under `results/phase3/`.
