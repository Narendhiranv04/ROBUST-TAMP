# Phase 5: WHERE (corrective sub-plans, urgency, insertion)

First-proposal urgency accuracy: the first corrective proposal of a trial vs the variant spec (objects
correct / judged). Re-queries: rejected proposals (`insertion_too_late`, `invalid_corrective_block`).
Hard-constraint and procedure failures come from the evaluator (`trial_end.missing`).

| Run | Variant | Trials | First-proposal urgency | Re-queries | Success | Unmet (evaluator) |
|---|---|---|---|---|---|---|
| corrective_planner | FINAL.K0 | 2 | — | 0 | 100% | — |
| corrective_planner | FINAL.G0 | 2 | — | 0 | 100% | — |
| corrective_planner | FINAL.K1 | 2 | 2/2 | 0 | 100% | — |
| corrective_planner | FINAL.K2 | 2 | — | 0 | 100% | — |
| corrective_planner | FINAL.K3 | 2 | 2/2 | 0 | 100% | — |
| corrective_planner | FINAL.K4 | 2 | 2/2 | 0 | 100% | — |
| corrective_planner | FINAL.G1 | 2 | 4/4 | 0 | 100% | — |
| corrective_planner | FINAL.G2 | 2 | 4/4 | 0 | 100% | — |
| corrective_planner | FINAL.G3 | 2 | 4/4 | 0 | 100% | — |
| corrective_planner | FINAL.K3-n2 | 2 | 4/4 | 0 | 100% | — |
| corrective_planner | FINAL.K3-n3 | 2 | 6/6 | 0 | 100% | — |
| corrective_planner | FINAL.G1-n1 | 2 | 2/2 | 0 | 100% | — |
| corrective_planner | FINAL.K1-w1 | 2 | 2/2 | 0 | 100% | — |
| corrective_planner | FINAL.K1-w2 | 2 | 2/2 | 0 | 100% | — |
| always_front | FINAL.K1 | 1 | 1/1 | 0 | 100% | — |
| always_front | FINAL.K3 | 1 | 1/1 | 0 | 100% | — |
| always_front | FINAL.K4 | 1 | 1/1 | 0 | 100% | — |
| always_front | FINAL.G1 | 1 | 2/2 | 0 | 100% | — |
| always_front | FINAL.G2 | 1 | 2/2 | 0 | 0% | plate is in dish_rack, expected serving_area; raw_meat_1 is in table, expected plate_top; raw_meat_1 never completed a cooking cycle; raw_meat_2 placed on plate |
| always_front | FINAL.G3 | 1 | 2/2 | 0 | 0% | plate is in dish_rack, expected serving_area; raw_meat_1 is in table, expected plate_top; raw_meat_1 never completed a cooking cycle; raw_meat_2 placed on plate |
| always_end | FINAL.K1 | 1 | 1/1 | 2 (insertion_too_late) | 0% | HC-box violated: phone never cleared from the box placement area; mug1 is in pantry_area, expected inside_box; mug2 is in table_staging_area, expected inside_bo |
| always_end | FINAL.K3 | 1 | 1/1 | 2 (insertion_too_late) | 0% | HC-box violated: can_of_beans never cleared from the box placement area; can_of_beans is in inside_box, expected cupboard_shelf; mug1 is in pantry_area, expecte |
| always_end | FINAL.K4 | 1 | 1/1 | 0 | 100% | — |
| always_end | FINAL.G1 | 1 | 2/2 | 0 | 0% | HC-grill violated: cooked_meat_1 inside the grill at close(grill_lid) after it was cooked; HC-grill violated: cooked_meat_2 inside the grill at close(grill_lid) |
| always_end | FINAL.G2 | 1 | 2/2 | 0 | 0% | HC-grill violated: cooked_meat_1 inside the grill at close(grill_lid) after it was cooked; cooked_meat_1 overcooked: inside the grill during a close->reopen cyc |
| always_end | FINAL.G3 | 1 | 2/2 | 0 | 100% | — |
