# Failure analysis (Table 1 areas)

Counts are surfaced failure events (every rejection, refusal and execution failure) summed over the trials of a variant; "failed" is failed trials / scored trials; "decisive" is the cause each failed trial ended with: "budget <- X" / "loop <- X" = the trial ran out of replans / repeated an output, X being its most frequent failure before that; "Task plan" / "Insertion" = the plan completed but the evaluator found the goal unmet / a procedure or ordering violation.

## holo2-8b

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 5/10 | 1 | 20 | 17 |  | 21 |  | 6 |  | 2 | 2x budget <- Corrective block: invalid_corrective_block; 1x budget <- Scene precondition: box_lid_closed; 1x budget <- Plan rules: missing_post_pick_place; 1x loop <- Scene precondition: box_lid_obstructed |
| FINAL.K1 | 9/10 | 1 | 20 | 25 | 12 | 20 |  | 6 |  | 9 | 4x budget <- Corrective block: invalid_corrective_block; 2x loop <- Plan rules: missing_post_pick_place; 1x budget <- Scene precondition: box_lid_obstructed; 1x budget <- Motion / grasp: executor_failure; 1x loop <- Corrective block: invalid_corrective_block |
| FINAL.K2 | 8/10 | 1 | 29 | 15 |  | 25 |  | 5 |  | 9 | 3x budget <- Plan rules: missing_post_pick_place; 2x budget <- Corrective block: invalid_corrective_block; 1x loop <- Scene precondition: box_lid_closed; 1x loop <- Plan rules: missing_post_pick_place; 1x budget <- Motion / grasp: executor_failure |
| FINAL.K3 | 6/10 | 4 | 19 | 18 | 7 | 21 |  | 12 |  | 4 | 2x budget <- Corrective block: invalid_corrective_block; 1x budget <- Motion / grasp: placement_failed; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Scene precondition: box_lid_closed; 1x budget <- Insertion: insertion_too_late |
| FINAL.K4 | 6/10 | 3 | 25 | 15 |  | 22 |  | 9 |  | 4 | 1x budget <- Scene precondition: box_lid_closed; 1x Task plan; 1x budget <- Corrective block: invalid_corrective_block; 1x loop <- Scene precondition: box_lid_closed; 1x budget <- Plan rules: missing_post_pick_place; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.K3-n2 | 7/10 | 3 | 20 | 23 | 12 | 24 |  | 10 |  | 1 | 4x budget <- Corrective block: invalid_corrective_block; 3x budget <- Plan rules: missing_post_pick_place |
| FINAL.K3-n3 | 6/10 | 2 | 15 | 22 | 13 | 18 |  | 12 |  | 1 | 4x budget <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Other: hc_violation |
| FINAL.K1-w1 | 9/10 |  | 23 | 35 | 17 | 26 |  | 3 |  | 1 | 6x budget <- Corrective block: invalid_corrective_block; 2x budget <- Scene precondition: box_lid_obstructed; 1x budget <- Scene precondition: box_lid_closed |
| FINAL.K1-w2 | 6/10 | 1 | 25 | 18 | 10 | 21 |  | 6 |  | 5 | 3x budget <- Corrective block: invalid_corrective_block; 1x loop <- Plan rules: missing_post_pick_place; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Scene precondition: box_lid_closed |
| FINAL.G0 | 10/10 | 11 | 6 | 29 |  | 3 |  |  |  | 1 | 4x budget <- Corrective block: invalid_corrective_block; 3x Task plan; 1x Insertion; 1x budget <- Plan format: unknown_action_token; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.G1 | 10/10 | 6 | 6 | 47 |  |  |  | 2 |  | 1 | 5x budget <- Corrective block: invalid_corrective_block; 3x Task plan; 1x budget <- Plan format: unknown_action_token; 1x budget <- Motion / grasp: placement_failed |
| FINAL.G2 | 10/10 | 6 | 7 | 55 | 1 | 5 |  | 1 |  | 3 | 8x budget <- Corrective block: invalid_corrective_block; 1x Task plan; 1x Insertion |
| FINAL.G3 | 10/10 |  | 3 | 61 | 4 |  |  | 1 |  |  | 9x budget <- Corrective block: invalid_corrective_block; 1x Task plan |
| FINAL.G1-n1 | 9/10 | 2 | 3 | 58 | 1 | 2 |  | 2 |  |  | 8x budget <- Corrective block: invalid_corrective_block; 1x Task plan |
| **all** | | 41 | 221 | 438 | 77 | 208 |  | 75 |  | 41 | |

## internvl3.5-8b

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 6/10 |  | 9 | 13 |  | 27 |  | 9 |  | 15 | 2x budget <- Corrective block: invalid_corrective_block; 2x budget <- Scene precondition: box_lid_obstructed; 1x loop <- Scene precondition: box_lid_obstructed; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.K1 | 10/10 | 2 | 5 | 29 | 15 | 28 |  | 3 |  | 17 | 5x budget <- Corrective block: invalid_corrective_block; 4x loop <- Scene precondition: box_lid_obstructed; 1x loop <- Corrective block: invalid_corrective_block |
| FINAL.K2 | 8/10 |  | 12 | 16 |  | 31 |  | 8 |  | 17 | 3x loop <- Scene precondition: box_lid_obstructed; 2x budget <- Scene precondition: box_lid_obstructed; 1x budget <- Motion / grasp: executor_failure; 1x budget <- Corrective block: invalid_corrective_block; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.K3 | 9/10 | 1 | 12 | 19 | 8 | 21 |  | 9 |  | 15 | 2x budget <- Corrective block: invalid_corrective_block; 2x loop <- Scene precondition: box_lid_obstructed; 2x loop <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Plan rules: orphan_place; 1x budget <- Motion / grasp: executor_failure |
| FINAL.K4 | 6/10 |  | 17 | 13 |  | 29 |  | 7 |  | 14 | 2x budget <- Corrective block: invalid_corrective_block; 2x loop <- Scene precondition: box_lid_obstructed; 1x loop <- Scene precondition: box_lid_closed; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K3-n2 | 8/10 |  | 22 | 7 | 16 | 34 |  | 4 |  | 12 | 2x budget <- Scene precondition: box_lid_obstructed; 1x loop <- Scene precondition: box_lid_obstructed; 1x loop <- Scene precondition: box_lid_closed; 1x budget <- Corrective block: invalid_corrective_block; 1x budget <- Scene precondition: box_lid_closed; 1x budget <- Plan rules: missing_post_pick_place; 1x loop <- Other: hc_violation |
| FINAL.K3-n3 | 9/10 |  | 13 | 23 | 29 | 31 |  | 5 |  | 11 | 4x budget <- Corrective block: invalid_corrective_block; 1x budget <- Scene precondition: box_lid_obstructed; 1x budget <- Scene precondition: box_lid_closed; 1x budget <- Other: hc_violation; 1x loop <- Scene precondition: box_lid_obstructed; 1x loop <- Other: hc_violation |
| FINAL.K1-w1 | 10/10 | 1 | 16 | 25 | 18 | 23 |  | 5 |  | 12 | 4x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: orphan_place; 1x budget <- Insertion: insertion_too_late; 1x loop <- Plan rules: missing_post_pick_place; 1x budget <- Scene precondition: box_lid_obstructed; 1x loop <- Scene precondition: box_lid_obstructed |
| FINAL.K1-w2 | 10/10 | 2 | 9 | 23 | 17 | 30 |  | 2 |  | 13 | 3x budget <- Corrective block: invalid_corrective_block; 2x loop <- Scene precondition: box_lid_obstructed; 2x loop <- Scene precondition: box_lid_closed; 2x budget <- Scene precondition: box_lid_obstructed; 1x budget <- Insertion: insertion_too_late |
| FINAL.G0 | 10/10 | 1 | 2 | 55 |  |  |  | 1 |  | 15 | 6x loop <- Corrective block: invalid_corrective_block; 4x budget <- Corrective block: invalid_corrective_block |
| FINAL.G1 | 10/10 | 1 | 1 | 69 | 1 |  |  | 4 |  | 4 | 9x budget <- Corrective block: invalid_corrective_block; 1x loop <- Corrective block: invalid_corrective_block |
| FINAL.G2 | 10/10 |  |  | 64 | 1 | 1 |  |  |  | 12 | 5x loop <- Corrective block: invalid_corrective_block; 5x budget <- Corrective block: invalid_corrective_block |
| FINAL.G3 | 10/10 |  | 1 | 54 |  |  |  |  |  | 16 | 6x loop <- Corrective block: invalid_corrective_block; 4x budget <- Corrective block: invalid_corrective_block |
| FINAL.G1-n1 | 10/10 | 3 | 1 | 59 | 3 | 1 |  |  |  | 15 | 6x loop <- Corrective block: invalid_corrective_block; 4x budget <- Corrective block: invalid_corrective_block |
| **all** | | 11 | 120 | 469 | 108 | 256 |  | 57 |  | 188 | |

## llama-3.1-8b-instruct

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 9/10 | 19 | 18 | 33 |  | 15 |  | 6 |  | 3 | 4x budget <- Corrective block: invalid_corrective_block; 3x budget <- Plan format: unknown_action_token; 2x budget <- Plan rules: pick_place_mismatch |
| FINAL.K1 | 10/10 | 23 | 29 | 24 | 10 | 22 |  | 3 |  | 1 | 3x budget <- Corrective block: invalid_corrective_block; 3x budget <- Plan rules: pick_place_mismatch; 2x budget <- Scene precondition: box_lid_obstructed; 2x budget <- Plan format: unknown_action_token |
| FINAL.K2 | 5/10 | 15 | 32 | 10 |  | 17 |  | 1 |  | 1 | 2x budget <- Plan format: unknown_action_token; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Plan rules: pick_place_mismatch; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K3 | 10/10 | 30 | 36 | 20 | 10 | 16 |  |  |  | 3 | 3x budget <- Corrective block: invalid_corrective_block; 3x budget <- Plan format: unknown_action_token; 2x budget <- Plan rules: pick_place_mismatch; 2x budget <- Scene precondition: box_lid_obstructed |
| FINAL.K4 | 10/10 | 27 | 21 | 30 |  | 18 |  | 4 |  | 4 | 4x budget <- Corrective block: invalid_corrective_block; 3x budget <- Plan format: unknown_action_token; 1x budget <- Scene precondition: box_lid_closed; 1x budget <- Plan rules: pick_place_mismatch; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K3-n2 | 10/10 | 13 | 21 | 30 | 20 | 15 |  |  |  | 8 | 3x loop <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: pick_place_mismatch; 2x budget <- Plan format: unknown_action_token; 2x budget <- Corrective block: invalid_corrective_block; 1x loop <- Other: hc_violation |
| FINAL.K3-n3 | 10/10 | 20 | 27 | 27 | 30 | 16 |  | 1 |  | 8 | 3x loop <- Other: hc_violation; 3x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan format: unknown_action_token; 2x budget <- Other: hc_violation |
| FINAL.K1-w1 | 10/10 | 25 | 22 | 36 | 10 | 16 |  | 1 |  | 3 | 4x budget <- Corrective block: invalid_corrective_block; 4x budget <- Plan format: unknown_action_token; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Plan rules: pick_place_mismatch |
| FINAL.K1-w2 | 10/10 | 25 | 14 | 42 | 10 | 15 |  | 1 |  | 6 | 7x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan format: unknown_action_token; 1x budget <- Plan rules: pick_place_mismatch |
| FINAL.G0 | 10/10 | 24 | 17 | 56 |  | 2 |  |  |  | 2 | 8x budget <- Corrective block: invalid_corrective_block; 1x budget <- Plan format: unknown_action_token; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.G1 | 10/10 | 24 | 5 | 53 |  |  |  | 2 |  | 11 | 5x budget <- Corrective block: invalid_corrective_block; 3x loop <- Corrective block: invalid_corrective_block; 1x loop <- Plan format: unknown_action_token; 1x budget <- Plan format: unknown_action_token |
| FINAL.G2 | 10/10 | 42 | 19 | 34 |  |  |  | 1 |  | 3 | 6x budget <- Plan format: unknown_action_token; 3x budget <- Corrective block: invalid_corrective_block; 1x loop <- Corrective block: invalid_corrective_block |
| FINAL.G3 | 10/10 | 16 | 17 | 67 |  |  |  |  |  |  | 8x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan format: unknown_action_token |
| FINAL.G1-n1 | 10/10 | 25 | 12 | 59 |  | 1 |  |  |  | 2 | 7x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan format: unknown_action_token; 1x loop <- Corrective block: invalid_corrective_block |
| **all** | | 328 | 290 | 521 | 90 | 153 |  | 20 |  | 55 | |

## qwen2.5-7b-instruct

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 1 | 33 | 12 |  | 26 |  | 2 |  | 19 | 2x budget <- Scene precondition: box_lid_closed; 2x budget <- Plan rules: missing_post_pick_place; 2x loop <- Plan rules: missing_post_pick_place; 2x loop <- Scene precondition: box_lid_closed; 1x loop <- Corrective block: invalid_corrective_block; 1x Task plan |
| FINAL.K1 | 10/10 | 3 | 27 | 18 | 10 | 29 |  |  |  | 15 | 5x budget <- Scene precondition: box_lid_closed; 2x loop <- Corrective block: invalid_corrective_block; 1x loop <- Plan rules: missing_post_pick_place; 1x loop <- Plan format: unknown_action_token; 1x loop <- Scene precondition: box_lid_closed |
| FINAL.K2 | 10/10 | 1 | 30 | 16 |  | 18 |  |  |  | 21 | 4x loop <- Plan rules: missing_post_pick_place; 3x loop <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: missing_post_pick_place; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K3 | 10/10 |  | 30 | 22 | 10 | 22 |  |  |  | 18 | 3x budget <- Plan rules: missing_post_pick_place; 3x loop <- Corrective block: invalid_corrective_block; 2x loop <- Plan rules: missing_post_pick_place; 1x budget <- Corrective block: invalid_corrective_block; 1x budget <- Scene precondition: box_lid_closed |
| FINAL.K4 | 10/10 | 3 | 23 | 17 |  | 22 |  |  |  | 17 | 3x loop <- Corrective block: invalid_corrective_block; 2x loop <- Scene precondition: box_lid_closed; 2x budget <- Plan rules: missing_post_pick_place; 1x budget <- Scene precondition: box_lid_closed; 1x loop <- Plan rules: missing_post_pick_place; 1x budget <- Plan format: unknown_action_token |
| FINAL.K3-n2 | 10/10 |  | 33 | 15 | 20 | 25 |  |  |  | 20 | 3x budget <- Plan rules: missing_post_pick_place; 3x loop <- Plan rules: missing_post_pick_place; 2x loop <- Corrective block: invalid_corrective_block; 1x loop <- Other: hc_violation; 1x budget <- Scene precondition: box_lid_closed |
| FINAL.K3-n3 | 10/10 | 1 | 28 | 12 | 30 | 23 |  |  |  | 19 | 5x loop <- Other: hc_violation; 2x budget <- Other: hc_violation; 1x budget <- Scene precondition: box_lid_closed; 1x budget <- Plan rules: missing_post_pick_place; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.K1-w1 | 10/10 | 3 | 24 | 13 | 10 | 19 |  |  |  | 22 | 5x loop <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: missing_post_pick_place; 1x loop <- Scene precondition: box_lid_obstructed; 1x loop <- Plan rules: missing_post_pick_place; 1x loop <- Scene precondition: box_lid_closed |
| FINAL.K1-w2 | 10/10 |  | 20 | 24 | 10 | 13 |  |  |  | 24 | 5x loop <- Corrective block: invalid_corrective_block; 4x loop <- Plan rules: missing_post_pick_place; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.G0 | 10/10 | 41 | 27 |  |  |  |  |  |  | 21 | 9x loop <- Plan format: unknown_action_token; 1x budget <- Plan format: unknown_action_token |
| FINAL.G1 | 10/10 | 41 | 36 |  |  |  |  |  |  | 23 | 5x loop <- Plan format: unknown_action_token; 5x budget <- Plan format: unknown_action_token |
| FINAL.G2 | 10/10 | 45 | 38 |  |  |  |  |  |  | 22 | 8x budget <- Plan format: unknown_action_token; 1x loop <- Plan format: unknown_action_token; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.G3 | 10/10 | 43 | 33 |  |  |  |  |  |  | 20 | 7x loop <- Plan format: unknown_action_token; 2x budget <- Plan format: unknown_action_token; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.G1-n1 | 10/10 | 44 | 28 |  |  |  |  |  |  | 21 | 8x loop <- Plan format: unknown_action_token; 2x budget <- Plan format: unknown_action_token |
| **all** | | 226 | 410 | 149 | 90 | 197 |  | 2 |  | 282 | |

## qwen3-8b

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 2/10 |  | 14 |  |  | 4 |  | 5 |  | 4 | 2x loop <- Plan rules: orphan_place |
| FINAL.K1 | 2/10 | 2 | 10 | 4 | 21 | 3 |  | 6 |  | 2 | 1x budget <- Insertion: insertion_too_late; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.K2 | 1/10 |  | 12 | 7 |  |  |  | 6 |  |  | 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K3 | 1/10 |  | 18 | 13 | 1 | 2 |  | 6 |  | 2 | 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K4 | 1/10 |  | 12 | 7 |  | 4 |  | 6 |  | 3 | 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K3-n2 | 1/10 |  | 11 | 15 | 3 | 3 |  | 8 |  | 1 | 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K3-n3 | 1/10 |  | 18 | 6 | 2 | 6 |  | 9 |  | 4 | 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K1-w1 | 4/10 |  | 23 | 15 | 30 | 4 |  | 8 |  | 7 | 1x budget <- Corrective block: invalid_corrective_block; 1x loop <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: orphan_place; 1x budget <- Insertion: insertion_too_late |
| FINAL.K1-w2 | 4/10 |  | 16 | 11 | 23 | 2 |  | 12 |  | 2 | 2x budget <- Insertion: insertion_too_late; 2x budget <- Corrective block: invalid_corrective_block |
| FINAL.G0 | 9/10 |  | 5 | 15 |  |  |  | 6 |  | 4 | 4x Insertion; 4x budget <- Corrective block: invalid_corrective_block; 1x budget <- none |
| FINAL.G1 | 10/10 | 1 | 9 | 63 |  |  |  | 9 |  | 6 | 7x budget <- Corrective block: invalid_corrective_block; 1x loop <- Corrective block: invalid_corrective_block; 1x loop <- Motion / grasp: placement_failed; 1x Task plan |
| FINAL.G2 | 9/10 |  | 4 | 74 | 1 |  |  | 1 |  | 1 | 9x budget <- Corrective block: invalid_corrective_block |
| FINAL.G3 | 10/10 | 1 | 3 | 76 |  |  |  | 1 |  | 7 | 7x budget <- Corrective block: invalid_corrective_block; 3x loop <- Corrective block: invalid_corrective_block |
| FINAL.G1-n1 | 10/10 | 1 | 5 | 61 |  |  |  | 2 |  | 5 | 7x budget <- Corrective block: invalid_corrective_block; 2x loop <- Corrective block: invalid_corrective_block; 1x Insertion |
| **all** | | 5 | 160 | 367 | 81 | 28 |  | 85 |  | 48 | |

## qwen3-vl-8b-thinking

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 0/10 |  | 4 |  |  | 1 |  | 5 |  |  |  |
| FINAL.K1 | 1/10 | 1 | 5 | 5 | 16 |  |  | 7 |  | 1 | 1x budget <- Insertion: insertion_too_late |
| FINAL.K2 | 1/10 |  | 11 |  |  |  |  | 5 |  | 1 | 1x budget <- Plan rules: orphan_place |
| FINAL.K3 | 0/10 |  | 8 | 2 | 1 | 2 |  | 5 |  |  |  |
| FINAL.K4 | 0/10 |  | 4 | 2 |  |  |  | 5 |  |  |  |
| FINAL.K3-n2 | 1/10 |  | 7 | 1 | 3 | 2 |  | 4 |  |  | 1x Task plan |
| FINAL.K3-n3 | 0/10 |  | 10 |  | 4 |  |  | 8 |  | 1 |  |
| FINAL.K1-w1 | 1/10 | 1 | 8 | 10 | 20 | 2 |  | 14 |  | 2 | 1x budget <- Motion / grasp: pddl_no_plan |
| FINAL.K1-w2 | 1/10 |  | 7 | 7 | 16 | 1 |  | 9 |  |  | 1x budget <- Insertion: insertion_too_late |
| FINAL.G0 | 7/10 | 1 | 1 | 1 |  |  |  | 1 |  |  | 5x Task plan; 1x budget <- Plan format: unknown_action_token; 1x budget <- none |
| FINAL.G1 | 6/10 | 1 | 6 | 8 | 3 |  |  | 8 |  |  | 4x Insertion; 1x Task plan; 1x budget <- Plan rules: orphan_place |
| FINAL.G2 | 9/10 | 1 |  | 17 | 4 |  |  | 6 |  |  | 5x Insertion; 2x budget <- Corrective block: invalid_corrective_block; 2x Task plan |
| FINAL.G3 | 9/10 |  | 20 | 16 |  | 1 |  | 11 |  | 1 | 3x Insertion; 3x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: orphan_place; 1x budget <- Plan rules: pick_place_mismatch |
| FINAL.G1-n1 | 8/10 | 3 | 4 | 6 | 1 |  |  | 3 |  |  | 6x Insertion; 1x budget <- none; 1x budget <- Motion / grasp: placement_failed |
| **all** | | 8 | 95 | 75 | 68 | 9 |  | 91 |  | 6 | |

## r1-distill-llama-8b

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 106 |  |  |  |  |  |  |  | 4 | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.K1 | 10/10 | 106 |  |  | 10 |  |  |  |  | 2 | 9x budget <- Plan format: planner_output_not_parseable; 1x loop <- Plan format: planner_output_not_parseable |
| FINAL.K2 | 10/10 | 110 |  |  |  |  |  |  |  |  | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.K3 | 10/10 | 110 |  |  | 10 |  |  |  |  |  | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.K4 | 10/10 | 110 |  |  |  |  |  |  |  |  | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.K3-n2 | 10/10 | 109 |  |  | 20 |  |  |  |  | 1 | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.K3-n3 | 10/10 | 108 |  |  | 30 |  |  |  |  | 2 | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.K1-w1 | 10/10 | 108 |  |  | 10 |  |  |  |  | 2 | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.K1-w2 | 10/10 | 108 |  |  | 10 |  |  |  |  | 2 | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.G0 | 10/10 | 109 |  |  |  |  |  |  |  | 1 | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.G1 | 10/10 | 108 |  |  |  |  |  |  |  | 2 | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.G2 | 10/10 | 110 |  |  |  |  |  |  |  |  | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.G3 | 10/10 | 110 |  |  |  |  |  |  |  |  | 10x budget <- Plan format: planner_output_not_parseable |
| FINAL.G1-n1 | 10/10 | 110 |  |  |  |  |  |  |  |  | 10x budget <- Plan format: planner_output_not_parseable |
| **all** | | 1522 |  |  | 90 |  |  |  |  | 16 | |

## r1-distill-qwen-7b

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 35 | 7 | 8 |  | 41 |  | 1 |  | 2 | 5x budget <- Scene precondition: box_lid_obstructed; 2x Task plan; 1x loop <- Scene precondition: box_lid_obstructed; 1x budget <- Corrective block: invalid_corrective_block; 1x budget <- Plan format: planner_output_not_parseable |
| FINAL.K1 | 10/10 | 24 | 13 |  | 10 | 47 |  |  |  |  | 6x budget <- Scene precondition: box_lid_obstructed; 4x Task plan |
| FINAL.K2 | 10/10 | 34 | 14 | 1 |  | 44 |  |  |  | 1 | 7x budget <- Scene precondition: box_lid_obstructed; 2x Task plan; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K3 | 10/10 | 40 | 15 |  | 10 | 36 |  | 1 |  |  | 4x Task plan; 3x budget <- Scene precondition: box_lid_obstructed; 2x budget <- Plan format: unknown_action_token; 1x budget <- Plan format: planner_output_not_parseable |
| FINAL.K4 | 10/10 | 30 | 15 |  |  | 36 |  |  |  |  | 4x Task plan; 4x budget <- Scene precondition: box_lid_obstructed; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Plan format: planner_output_not_parseable |
| FINAL.K3-n2 | 10/10 | 30 | 16 | 4 | 20 | 44 |  | 1 |  | 1 | 7x budget <- Scene precondition: box_lid_obstructed; 2x Task plan; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K3-n3 | 10/10 | 28 | 19 |  | 30 | 47 |  |  |  |  | 6x budget <- Scene precondition: box_lid_obstructed; 2x Task plan; 1x budget <- Scene precondition: box_lid_closed; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K1-w1 | 10/10 | 25 | 18 | 1 | 10 | 42 |  | 1 |  |  | 5x budget <- Scene precondition: box_lid_obstructed; 3x Task plan; 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Scene precondition: box_lid_closed |
| FINAL.K1-w2 | 10/10 | 24 | 14 | 1 | 10 | 28 |  |  |  |  | 5x budget <- Scene precondition: box_lid_obstructed; 5x Task plan |
| FINAL.G0 | 10/10 | 34 | 24 | 23 |  |  |  | 2 |  | 1 | 3x budget <- Corrective block: invalid_corrective_block; 3x budget <- Plan rules: missing_post_pick_place; 2x Task plan; 2x budget <- Plan format: unknown_action_token |
| FINAL.G1 | 10/10 | 53 | 32 | 14 |  |  |  | 1 |  | 1 | 5x budget <- Plan format: unknown_action_token; 2x Task plan; 2x budget <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.G2 | 10/10 | 50 | 38 | 10 |  |  |  |  |  |  | 5x budget <- Plan format: unknown_action_token; 2x Task plan; 2x budget <- Plan rules: missing_post_pick_place; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.G3 | 10/10 | 24 | 23 | 47 |  | 1 |  |  |  | 2 | 6x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan format: unknown_action_token; 1x budget <- Plan rules: missing_post_pick_place; 1x Task plan |
| FINAL.G1-n1 | 10/10 | 26 | 45 | 23 |  | 1 |  |  |  | 1 | 5x budget <- Plan rules: missing_post_pick_place; 3x budget <- Corrective block: invalid_corrective_block; 1x Task plan; 1x budget <- Plan format: unknown_action_token |
| **all** | | 457 | 293 | 132 | 90 | 367 |  | 7 |  | 9 | |

