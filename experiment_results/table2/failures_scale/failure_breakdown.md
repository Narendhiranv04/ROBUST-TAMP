# Failure analysis (Table 1 areas)

Counts are surfaced failure events (every rejection, refusal and execution failure) summed over the trials of a variant; "failed" is failed trials / scored trials; "decisive" is the cause each failed trial ended with: "budget <- X" / "loop <- X" = the trial ran out of replans / repeated an output, X being its most frequent failure before that; "Task plan" / "Insertion" = the plan completed but the evaluator found the goal unmet / a procedure or ordering violation.

## qwen3-4b-fp8

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 7/10 | 1 | 10 | 12 |  | 5 |  | 6 |  | 14 | 6x loop <- Corrective block: invalid_corrective_block; 1x loop <- Plan rules: missing_post_pick_place |
| FINAL.K1 | 10/10 | 3 | 11 | 23 | 14 | 4 |  | 5 |  | 19 | 8x loop <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: orphan_place; 1x loop <- Scene precondition: box_lid_obstructed |
| FINAL.K2 | 0/10 | 1 | 9 | 2 |  | 6 |  | 6 |  | 2 |  |
| FINAL.K3 | 10/10 |  | 10 | 18 | 10 | 7 |  | 6 |  | 18 | 6x loop <- Corrective block: invalid_corrective_block; 2x loop <- Plan rules: orphan_place; 1x Task plan; 1x loop <- Scene precondition: box_lid_obstructed |
| FINAL.K4 | 10/10 | 6 | 27 | 14 |  | 10 |  | 3 |  | 14 | 4x loop <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: orphan_place; 1x Task plan; 1x budget <- Plan rules: missing_post_pick_place; 1x loop <- Plan format: planner_output_not_parseable; 1x loop <- Plan rules: orphan_place |
| FINAL.K3-n2 | 10/10 | 4 | 12 | 20 | 20 | 8 |  | 6 |  | 19 | 9x loop <- Other: hc_violation; 1x budget <- Scene precondition: box_lid_obstructed |
| FINAL.K3-n3 | 10/10 | 2 | 9 | 21 | 30 | 6 |  | 6 |  | 20 | 10x loop <- Other: hc_violation |
| FINAL.K1-w1 | 10/10 | 1 | 7 | 20 | 10 | 7 |  | 5 |  | 18 | 8x loop <- Corrective block: invalid_corrective_block; 1x Task plan; 1x loop <- Scene precondition: box_lid_obstructed |
| FINAL.K1-w2 | 10/10 | 4 | 15 | 21 | 11 | 8 |  | 7 |  | 20 | 7x loop <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: orphan_place; 1x loop <- Plan rules: orphan_place; 1x budget <- Scene precondition: box_lid_obstructed |
| FINAL.G0 | 10/10 | 5 | 22 | 18 |  | 1 |  |  |  | 16 | 5x loop <- Corrective block: invalid_corrective_block; 2x loop <- Plan rules: pick_place_mismatch; 2x budget <- Plan rules: pick_place_mismatch; 1x Insertion |
| FINAL.G1 | 10/10 | 5 | 17 | 24 | 2 | 1 |  | 6 |  | 18 | 4x loop <- Plan rules: pick_place_mismatch; 4x loop <- Corrective block: invalid_corrective_block; 1x loop <- Motion / grasp: placement_failed; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.G2 | 10/10 | 15 | 29 | 16 | 1 | 1 |  | 1 |  | 15 | 4x loop <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: pick_place_mismatch; 2x loop <- Plan format: unknown_action_token; 1x loop <- Plan rules: pick_place_mismatch; 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.G3 | 10/10 | 16 | 32 | 18 |  |  |  | 8 |  | 11 | 4x loop <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: orphan_place; 1x budget <- Corrective block: invalid_corrective_block; 1x budget <- Plan format: unknown_action_token; 1x Insertion; 1x loop <- Plan format: unknown_action_token |
| FINAL.G1-n1 | 10/10 | 3 | 19 | 22 |  |  |  | 2 |  | 19 | 9x loop <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: orphan_place |
| **all** | | 66 | 229 | 249 | 98 | 64 |  | 67 |  | 223 | |

## qwen3-8b-fp8

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 0/10 | 2 | 21 |  |  | 6 |  | 5 |  | 3 |  |
| FINAL.K1 | 3/10 |  | 23 | 1 | 15 | 5 |  | 7 |  | 4 | 1x budget <- Plan rules: missing_post_pick_place; 1x budget <- Plan rules: orphan_place; 1x loop <- Plan rules: orphan_place |
| FINAL.K2 | 0/10 |  | 12 |  |  | 2 |  | 6 |  | 2 |  |
| FINAL.K3 | 1/10 | 1 | 19 | 3 | 1 | 5 |  | 5 |  | 5 | 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K4 | 1/10 | 1 | 24 | 3 |  | 6 |  | 6 |  | 2 | 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.K3-n2 | 0/10 | 1 | 17 | 6 | 1 | 5 |  | 6 |  | 2 |  |
| FINAL.K3-n3 | 0/10 |  | 22 | 7 | 1 | 3 |  | 6 |  | 1 |  |
| FINAL.K1-w1 | 7/10 | 2 | 29 | 5 | 25 | 12 |  | 8 |  | 8 | 2x budget <- Plan rules: missing_post_pick_place; 2x loop <- Plan rules: missing_post_pick_place; 1x Task plan; 1x budget <- Insertion: insertion_too_late; 1x budget <- Plan rules: orphan_place |
| FINAL.K1-w2 | 4/10 |  | 25 | 10 | 26 | 4 |  | 11 |  | 2 | 4x budget <- Insertion: insertion_too_late |
| FINAL.G0 | 9/10 | 1 | 6 | 13 |  |  |  | 3 |  | 1 | 5x budget <- Corrective block: invalid_corrective_block; 3x Insertion; 1x budget <- Motion / grasp: placement_failed |
| FINAL.G1 | 10/10 | 2 | 4 | 62 |  |  |  | 5 |  | 3 | 7x budget <- Corrective block: invalid_corrective_block; 2x Insertion; 1x loop <- Plan rules: orphan_place |
| FINAL.G2 | 10/10 |  | 5 | 56 |  | 1 |  | 5 |  |  | 8x budget <- Corrective block: invalid_corrective_block; 2x Insertion |
| FINAL.G3 | 10/10 |  | 15 | 66 | 2 |  |  | 7 |  |  | 8x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: orphan_place |
| FINAL.G1-n1 | 8/10 | 1 | 3 | 49 |  |  |  | 10 |  |  | 6x budget <- Corrective block: invalid_corrective_block; 2x Insertion |
| **all** | | 11 | 225 | 281 | 71 | 49 |  | 90 |  | 33 | |

## qwen3-vl-32b-thinking-fp8

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 0/1 |  |  |  |  |  |  |  |  |  |  |
| FINAL.K2 | 0/1 |  |  |  |  |  |  |  |  |  |  |
| FINAL.K3 | 0/1 |  | 1 | 1 |  |  |  | 1 |  |  |  |
| FINAL.K4 | 0/1 |  |  |  |  |  |  | 1 |  |  |  |
| **all** | |  | 1 | 1 |  |  |  | 2 |  |  | |

## qwen3-vl-4b-thinking-fp8

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 0/10 |  | 7 |  |  | 2 |  | 6 |  |  |  |
| FINAL.K1 | 9/10 |  | 13 | 32 | 38 | 4 |  | 6 |  | 8 | 4x budget <- Insertion: insertion_too_late; 3x budget <- Corrective block: invalid_corrective_block; 1x loop <- Corrective block: invalid_corrective_block; 1x loop <- Insertion: insertion_too_late |
| FINAL.K2 | 1/10 |  | 17 |  |  | 1 |  | 7 |  | 2 | 1x Task plan |
| FINAL.K3 | 2/10 |  | 11 | 12 | 2 |  |  | 6 |  | 4 | 2x loop <- Corrective block: invalid_corrective_block |
| FINAL.K4 | 1/10 |  | 17 | 6 |  | 4 |  | 6 |  | 3 | 1x loop <- Plan rules: orphan_place |
| FINAL.K3-n2 | 2/10 |  | 11 | 10 | 3 | 2 |  | 4 |  | 4 | 1x budget <- Plan rules: orphan_place; 1x Task plan |
| FINAL.K3-n3 | 3/10 | 1 | 15 | 19 | 7 |  |  | 8 |  | 7 | 2x loop <- Other: hc_violation; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K1-w1 | 9/10 |  | 8 | 43 | 40 | 1 |  | 7 |  | 1 | 7x budget <- Corrective block: invalid_corrective_block; 2x budget <- Insertion: insertion_too_late |
| FINAL.K1-w2 | 10/10 |  | 14 | 42 | 41 | 3 |  | 5 |  | 3 | 5x budget <- Corrective block: invalid_corrective_block; 5x budget <- Insertion: insertion_too_late |
| FINAL.G0 | 9/10 | 10 | 12 | 11 |  |  |  | 13 |  | 10 | 6x Insertion; 1x budget <- Corrective block: invalid_corrective_block; 1x loop <- Motion / grasp: placement_failed; 1x loop <- Corrective block: invalid_corrective_block |
| FINAL.G1 | 8/10 | 7 | 8 | 25 |  |  |  | 4 |  | 16 | 7x loop <- Corrective block: invalid_corrective_block; 1x Insertion |
| FINAL.G2 | 10/10 | 10 | 7 | 40 | 2 |  |  | 3 |  | 14 | 6x loop <- Corrective block: invalid_corrective_block; 4x budget <- Corrective block: invalid_corrective_block |
| FINAL.G3 | 9/10 | 2 | 3 | 40 |  |  |  |  |  | 18 | 9x loop <- Corrective block: invalid_corrective_block |
| FINAL.G1-n1 | 8/10 | 5 | 11 | 23 | 2 |  |  | 11 |  | 11 | 4x loop <- Corrective block: invalid_corrective_block; 3x Insertion; 1x budget <- Corrective block: invalid_corrective_block |
| **all** | | 35 | 154 | 303 | 135 | 17 |  | 86 |  | 101 | |

## qwen3-vl-8b-thinking-fp8

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 0/10 |  | 4 |  |  |  |  | 5 |  |  |  |
| FINAL.K1 | 2/10 |  | 7 | 8 | 16 |  |  | 9 |  |  | 1x budget <- Insertion: insertion_too_late; 1x budget <- Plan rules: orphan_place |
| FINAL.K2 | 0/10 |  | 9 |  |  |  |  | 6 |  |  |  |
| FINAL.K3 | 0/10 | 1 | 11 | 2 | 1 |  |  | 6 |  |  |  |
| FINAL.K4 | 0/10 | 2 | 15 | 1 |  |  |  | 6 |  |  |  |
| FINAL.K3-n2 | 1/10 | 1 | 8 |  | 3 |  |  | 6 |  | 2 | 1x loop <- Other: hc_violation |
| FINAL.K3-n3 | 0/10 |  | 8 | 2 | 2 | 1 |  | 10 |  |  |  |
| FINAL.K1-w1 | 2/10 |  | 15 | 3 | 16 |  |  | 7 |  | 4 | 1x loop <- Plan rules: orphan_place; 1x budget <- Insertion: insertion_too_late |
| FINAL.K1-w2 | 1/10 |  | 15 | 6 | 17 |  |  | 12 |  |  | 1x budget <- Plan rules: orphan_place |
| FINAL.G0 | 9/10 | 1 | 3 | 8 |  |  |  | 4 |  | 1 | 5x budget <- Corrective block: invalid_corrective_block; 1x budget <- Motion / grasp: placement_failed; 1x budget <- none; 1x Insertion; 1x Task plan |
| FINAL.G1 | 8/10 | 1 | 12 | 4 |  |  |  | 14 |  |  | 5x Insertion; 1x budget <- Motion / grasp: placement_failed; 1x budget <- Plan rules: orphan_place; 1x Task plan |
| FINAL.G2 | 8/10 | 3 | 6 | 24 |  |  |  | 6 |  | 2 | 4x Insertion; 2x budget <- Corrective block: invalid_corrective_block; 1x Task plan; 1x loop <- Plan rules: orphan_place |
| FINAL.G3 | 8/10 | 1 | 23 | 10 |  |  |  | 18 |  | 1 | 4x budget <- Motion / grasp: placement_failed; 2x Insertion; 2x budget <- Corrective block: invalid_corrective_block |
| FINAL.G1-n1 | 10/10 | 4 | 2 | 9 | 2 |  |  | 2 |  |  | 6x Insertion; 2x Task plan; 1x budget <- Corrective block: invalid_corrective_block; 1x budget <- Plan format: unknown_action_token |
| **all** | | 14 | 138 | 77 | 57 | 1 |  | 111 |  | 10 | |

