# Final variant set (plan.md Phase 3)

**Status: for approval.** No scene file will change until you approve this document. Section 7 lists the decisions needed from you: plan.md Section 10, questions Q2–Q6 and Q12.

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

**Grill base layout.** Derived from G2 and G3:
- two raw meats beside the grill (`raw_meat_1`, `raw_meat_2` on prep_area; these are today's chicken and steak1);
- `plate` in the dish_rack.

So a cooking cycle is always required (plan.md 3.2).

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
| `inside_grill` | the two grill slots nearest the robot: y ∈ [−0.343, −0.20] | y ∈ [−0.20, −0.112]: where hidden meats are placed | plan.md: meat revealed in the grill is always non-overlapping |
| `plate_top`, `cupboard_shelf`, `table_staging_area` | whole region | — | no hidden objects there |

The kitchen executor's box sampler is restricted to the placement area (build item B3), and the grill slot poses already lie in the proposed band. An automated test (B6) checks each hidden object's overlap status against its spec.

## 4. Variant specs

For each variant below: the family, the point it proves, the hidden contents and their exact placement, the goal relations (R) and procedure checks (P), the expected IF decision, the expected urgency, the hard constraints checked by the evaluator, and the success condition. "Base" means the base layout of section 2. The expected corrective sub-plans are reference answers for the evaluator only; they are **never** shown to the planner.

Two IF decisions come up repeatedly:
- **IF-irr:** "trigger, irrelevant_overlapping".
- **IF-rel:** "trigger, relevant_not_goal_attained".

Hard-constraint keys:
- **HC-box:** the trigger objects are out of the box placement area before the next `place` into the box.
- **HC-grill:** every `cooked_meat` is out of the grill before the next `close(grill_lid)`.
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
- **Hidden:** none; the grill opens empty. Adapted from G2 by removing the steak.
- **R:** raw_meat_1, raw_meat_2 → plate_top; plate → serving_area. **P:** raw_meat_1 and raw_meat_2 each cooked, not overcooked, not served raw.
- **IF:** no replan. **Urgency:** —. **Constraints:** HC-raw.
- **Success:** R and P satisfied.

### Family B: core

**K1**
- **Proves:** an irrelevant object triggers a replan only when it overlaps, and it must be cleared before any mug goes in.
- **Hidden:** phone inside the box, **overlapping** (centre in the placement area, e.g. (0.03, 0.33)). The phone is a new asset for the kitchen scene, taken from the grill scene.
- **R:** base R, plus the phone ends outside the box placement area. **P:** none.
- **IF:** IF-irr for the phone. **Urgency:** phone `urgent`.
- **Reference sub-plan:** `pick(phone)`, `place(phone, <region outside the placement area>)` (Q3).
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
- **Hidden:** `cooked_meat_1` and `cooked_meat_2` inside the grill, outside its placement area. Adapted from G3: the phone is removed, and the steak plus a second steak become cooked_meat_1/2.
- **R:** all 4 meats → plate_top; plate → serving_area. **P:** each meat cooked, not overcooked, not served raw.
- **IF:** IF-rel for both. **Urgency:** both `urgent`.
- **Reference sub-plan:** take both out (to the plate or elsewhere, Q2) before the next close.
- **Constraints:** HC-grill, HC-raw. **Success:** R and P.

**G2**
- **Proves:** one replan with split urgency: the cooked meat comes out now, the raw meat stays to be cooked.
- **Hidden:** `cooked_meat_1` and `raw_meat_3` inside the grill. Adapted from G2: the steak becomes cooked_meat_1, and a raw meat is added.
- **R:** all 4 meats → plate_top; plate → serving_area. **P:** as G1.
- **IF:** IF-rel for both. **Urgency:** cooked_meat_1 `urgent`; raw_meat_3 `deferred`.
- **Constraints:** HC-grill, HC-raw. **Success:** R and P.

**G3**
- **Proves:** a replan with no urgency: the raw meat stays, is cooked in the normal cycle and is served later.
- **Hidden:** `raw_meat_3` and `raw_meat_4` inside the grill.
- **R:** all 4 meats → plate_top; plate → serving_area. **P:** as G1.
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
| K1-w2 | same | +2 | 2 |
| K1-w4 | same | +4 | 4 |

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

## 6. Old → new mapping and feasibility

| Final | Built from | Change |
|---|---|---|
| K0 | K1 (`task1_variation1`) + K3 table layout | remove the soup from the box; base layout on the table |
| K1 / K2 | K0 | add a phone (asset from the grill scene) inside the box, in or outside the placement area |
| K3 / K4 | K0 | the soup in the box, in or outside the placement area (K3 = today's K1 position) |
| K3-n2 / K3-n3 | K3 | 1 or 2 more cans in the placement area |
| K1-w2 / K1-w4 | K1 | +2 or +4 groceries on the table |
| G0 | G2 (`grill_variation2`) | remove the steak; relabel chicken/steak1 → raw_meat_1/2 |
| G1 / G1-n1 / G1-n3 | G3 (`grill_variation3`) | remove the phone; 2, 1 or 3 cooked_meat in the grill |
| G2 | G2 | steak → cooked_meat_1; add raw_meat_3 in the grill |
| G3 | G0 | add raw_meat_3 and raw_meat_4 in the grill |

Old variants K1–K3 and G1–G3 stay in the repository, and in the executor-ceiling and GT runs, for regression only (Q5).

Physical feasibility estimates, to be verified by the build tests:
- **Box, K3-n3:** 3 cans (5.5 cm) in the 16.5 × 28.6 cm placement area, then 3 mugs after the cans are removed. **Fits.**
- **Grill, G1-n3:** 3 cooked meats (10.5 × 5 cm) in the grill's 6.5 × 23 cm interior, with the band outside the placement area (7–9 cm long) holding at most 2. **Does not fit as specified.**
  - Option (a): allow hidden meats in the placement area for G1-n3 only. Meat is always relevant, so overlap does not change its IF decision.
  - Option (b): reduce the sweep to n = 1, 2.
- **Cupboard, K1-w4:** the base groceries (spam, sugar) plus 4 extra on a 9.3 × 37 cm single-row shelf is about 6 items of 3.5–10 cm. **At the limit.** The upper shelf is only 1.6 cm deep in its bounding box, so it's unusable. Option: w = 0, 1, 2 (or 0, 2, 3).

## 7. Decisions needed

1. **Q2:** where urgently removed `cooked_meat` goes in G1/G2: directly onto the plate in the serving area, or any region outside the grill? This decides the reference sub-plans and HC-grill only; the planner is not told.
2. **Q3:** where the phone may go in K1: any region outside the box placement area, or a specific one (e.g. `table`)?
3. **Q4:** the placement areas in section 3 (the robot-side half of the box; the two nearest grill slots), and the hidden-object positions in section 4.
4. **Q5:** keep today's K1–K3 and G1–G3 for regression only (default), or report them too?
5. **Q6:** add a variant for the "goal-attained object → no replan" branch? Today's K2 has mug1 already in the box and K3 has spam already in the cupboard, so one is easy to derive. Default: no.
6. **Q12:** the base-layout counts (3 mugs; spam and sugar on the table) and the sweeps: C1 grill as n = 1, 2, 3 with option (a), or n = 1, 2; C2 as w = 0, 2, 4, or reduced to w = 0, 1, 2.

## 8. Build plan after approval

- **B1:** a scene composition tool, `mujoco_port/tools/compose_variant.py`. It builds a new scene from a base scene by removing, adding or moving objects. Added objects come from any extracted scene, with new unique handles for segmentation. It writes `mujoco_port/scenes/<variant>/`, and the source `.ttt` files are untouched.
- **B2:** variant registry entries (`evaluation/canonical_variants.py`) for the 15 variants, the goal texts (unchanged), and `LABELED_RULE_VARIANTS`.
- **B3:** placement-area config, and the executor's box sampler restricted to the placement area.
- **B4:** meat labels (`raw_meat_*`, `cooked_meat_*`) in the executor symbol lists, grill semantic facts and executor meat detection.
- **B5:** GT action sequences and oracle support for every new variant.
- **B6:** automated tests. All 15 variants load, every hidden object's overlap status matches its spec, and the feasibility check passes. Then an executor-ceiling oracle run on all 15, and baseline-system runs saved under `results/phase3/`.
