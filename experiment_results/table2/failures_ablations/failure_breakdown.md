# Failure analysis (Table 1 areas)

Counts are surfaced failure events (every rejection, refusal and execution failure) summed over the trials of a variant; "failed" is failed trials / scored trials; "decisive" is the cause each failed trial ended with: "budget <- X" / "loop <- X" = the trial ran out of replans / repeated an output, X being its most frequent failure before that; "Task plan" / "Insertion" = the plan completed but the evaluator found the goal unmet / a procedure or ordering violation.

## fixed_end

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 |  | 4 | 10 | 88 | 1 |  | 5 |  | 2 | 10x budget <- Insertion: insertion_too_late |
| FINAL.K2 | 0/10 |  | 5 |  |  |  |  | 6 |  |  |  |
| FINAL.K3 | 9/10 |  | 10 | 2 | 81 | 2 |  | 6 |  | 1 | 9x budget <- Insertion: insertion_too_late |
| FINAL.K4 | 0/10 |  | 4 |  |  |  |  | 4 |  |  |  |
| FINAL.G1 | 9/10 |  | 14 | 8 | 16 |  |  | 9 |  |  | 8x Insertion; 1x budget <- Plan rules: orphan_place |
| FINAL.G2 | 10/10 | 2 | 16 | 14 | 8 |  |  | 15 |  |  | 6x Insertion; 2x budget <- Motion / grasp: placement_failed; 1x budget <- Plan rules: orphan_place; 1x budget <- Plan format: unknown_action_token |
| FINAL.G3 | 7/10 | 3 | 17 | 16 | 11 |  |  | 12 |  |  | 2x budget <- Insertion: insertion_too_late; 2x budget <- Corrective block: invalid_corrective_block; 1x budget <- Plan rules: orphan_place; 1x budget <- Motion / grasp: placement_failed; 1x Insertion |
| **all** | | 5 | 70 | 50 | 204 | 3 |  | 57 |  | 3 | |

## fixed_front

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 2/10 |  | 9 | 9 | 18 |  |  | 7 |  |  | 1x budget <- Insertion: insertion_too_late; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K2 | 1/10 |  | 5 |  |  |  |  | 5 |  |  | 1x budget <- Motion / grasp: placement_failed |
| FINAL.K3 | 0/10 |  | 4 |  |  | 1 |  | 4 |  |  |  |
| FINAL.K4 | 1/10 |  | 8 |  |  |  |  | 7 |  |  | 1x budget <- Plan rules: missing_post_pick_place |
| FINAL.G1 | 5/10 |  | 2 | 19 | 1 |  |  | 6 |  | 1 | 2x Insertion; 2x budget <- Corrective block: invalid_corrective_block; 1x Task plan |
| FINAL.G2 | 9/10 | 4 | 11 | 20 |  |  |  | 9 |  | 1 | 7x Insertion; 1x budget <- Plan rules: orphan_place; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.G3 | 10/10 | 3 | 20 | 17 |  | 1 |  | 14 |  |  | 4x budget <- Corrective block: invalid_corrective_block; 2x budget <- Plan rules: orphan_place; 1x Task plan; 1x Insertion; 1x budget <- Plan format: unknown_action_token; 1x budget <- Motion / grasp: placement_failed |
| **all** | | 7 | 59 | 65 | 19 | 2 |  | 52 |  | 2 | |

## no_if

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 1/10 |  | 5 | 5 | 17 |  |  | 8 |  |  | 1x Task plan |
| FINAL.K2 | 0/10 | 61 | 7 | 16 |  |  |  | 6 |  | 4 |  |
| FINAL.K3 | 1/10 |  | 5 |  | 2 |  |  | 5 |  |  | 1x Task plan |
| FINAL.K4 | 0/10 | 1 | 6 |  |  | 1 |  | 4 |  |  |  |
| FINAL.G1 | 6/10 | 1 | 3 | 5 | 2 |  |  | 7 |  |  | 3x Insertion; 3x Task plan |
| FINAL.G2 | 9/10 | 1 | 16 | 12 | 2 |  |  | 8 |  | 2 | 6x Insertion; 2x Task plan; 1x loop <- Plan rules: orphan_place |
| FINAL.G3 | 9/10 | 1 | 22 | 9 |  |  |  | 17 |  |  | 5x Task plan; 2x Insertion; 1x budget <- Motion / grasp: placement_failed; 1x budget <- Corrective block: invalid_corrective_block |
| **all** | | 65 | 64 | 47 | 23 | 1 |  | 55 |  | 6 | |

## no_memory

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 2/10 |  | 7 | 10 | 17 | 4 |  | 7 |  |  | 2x Task plan |
| FINAL.K2 | 1/10 |  | 6 |  |  | 2 |  | 4 |  |  | 1x Task plan |
| FINAL.K3 | 1/10 |  | 7 | 1 | 2 | 2 |  | 6 |  |  | 1x Task plan |
| FINAL.K4 | 2/10 |  | 3 | 1 |  | 2 |  | 6 |  |  | 2x Task plan |
| FINAL.G1 | 8/10 | 1 | 3 | 12 | 6 | 3 |  | 3 |  |  | 6x Insertion; 1x Task plan; 1x budget <- Motion / grasp: placement_failed |
| FINAL.G2 | 7/10 | 1 | 1 | 15 |  |  |  |  |  | 1 | 3x budget <- Corrective block: invalid_corrective_block; 2x Task plan; 1x Insertion; 1x budget <- none |
| FINAL.G3 | 8/10 | 3 | 15 | 14 |  | 1 |  | 7 |  | 5 | 2x loop <- Plan rules: orphan_place; 2x budget <- Plan rules: orphan_place; 2x budget <- Corrective block: invalid_corrective_block; 2x Insertion |
| **all** | | 5 | 42 | 53 | 25 | 14 |  | 33 |  | 6 | |

## no_when

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 3/10 |  | 9 | 8 | 19 | 2 |  | 9 |  |  | 2x budget <- Insertion: insertion_too_late; 1x budget <- Corrective block: invalid_corrective_block |
| FINAL.K2 | 0/10 |  | 6 | 2 |  |  |  | 5 |  | 1 |  |
| FINAL.K3 | 0/10 |  | 13 | 3 |  | 1 |  | 6 |  |  |  |
| FINAL.K4 | 0/10 |  | 10 | 2 |  |  |  | 5 |  |  |  |
| FINAL.G1 | 8/10 | 1 | 4 | 16 | 4 |  |  | 2 |  | 1 | 3x Insertion; 2x budget <- Corrective block: invalid_corrective_block; 2x Task plan; 1x budget <- Motion / grasp: placement_failed |
| FINAL.G2 | 9/10 |  | 5 | 21 | 5 |  |  | 4 |  |  | 5x Insertion; 4x budget <- Corrective block: invalid_corrective_block |
| FINAL.G3 | 8/10 | 1 | 2 | 25 | 1 | 2 |  | 7 |  | 2 | 5x budget <- Corrective block: invalid_corrective_block; 1x Insertion; 1x budget <- none; 1x Task plan |
| **all** | | 2 | 49 | 77 | 29 | 5 |  | 38 |  | 4 | |

## no_where

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 9/10 |  | 12 |  | 10 |  |  | 6 |  | 1 | 9x Task plan |
| FINAL.K2 | 1/10 |  | 9 |  |  | 1 |  | 6 |  | 2 | 1x loop <- Plan rules: orphan_place |
| FINAL.K3 | 0/10 |  | 6 |  | 2 | 1 |  | 3 |  |  |  |
| FINAL.K4 | 0/10 |  | 6 |  |  |  |  | 7 |  |  |  |
| FINAL.G1 | 6/10 |  | 5 |  | 8 |  |  | 6 |  | 1 | 6x Insertion |
| FINAL.G2 | 9/10 | 9 | 12 |  | 6 |  |  | 9 |  |  | 7x Insertion; 1x Task plan; 1x budget <- Plan format: unknown_action_token |
| FINAL.G3 | 4/10 |  | 9 |  |  |  |  | 10 |  | 1 | 2x Insertion; 1x budget <- Plan rules: orphan_place; 1x budget <- Motion / grasp: placement_failed |
| **all** | | 9 | 59 |  | 26 | 2 |  | 47 |  | 5 | |

## previous_system

| Variant | failed | Plan format | Plan rules | Corrective block | Insertion | Scene precondition | Task plan | Motion / grasp | Merge conflict | Replan budget | decisive causes of the failed trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 2/3 |  | 3 |  |  | 1 |  | 3 |  |  | 2x Task plan |
| FINAL.K1 | 2/2 |  | 1 |  | 2 |  |  | 2 |  |  | 2x Task plan |
| FINAL.K2 | 1/2 |  | 1 |  |  | 1 |  | 2 |  |  | 1x Task plan |
| FINAL.K3 | 1/2 |  |  |  | 1 |  |  | 1 |  |  | 1x Task plan |
| FINAL.K4 | 1/2 |  |  |  |  |  |  | 2 |  |  | 1x Task plan |
| FINAL.K3-n2 | 1/2 |  | 1 |  | 4 |  |  | 2 |  |  | 1x Task plan |
| FINAL.K3-n3 | 0/1 |  | 2 |  |  | 1 |  | 3 |  |  |  |
| FINAL.K1-w1 | 2/2 |  | 1 |  | 2 |  |  | 1 |  |  | 2x Task plan |
| FINAL.K1-w2 | 2/2 |  |  |  | 2 |  |  | 1 |  |  | 2x Task plan |
| FINAL.G0 | 1/3 |  |  |  |  |  |  |  |  |  | 1x Insertion |
| FINAL.G1 | 2/2 |  | 1 |  | 2 |  |  | 2 |  |  | 2x Insertion |
| FINAL.G2 | 2/2 | 1 |  |  | 2 |  |  |  |  |  | 2x Insertion |
| FINAL.G3 | 2/2 |  | 7 |  |  |  |  | 3 |  |  | 1x budget <- Plan rules: orphan_place; 1x Insertion |
| FINAL.G1-n1 | 2/2 |  | 2 |  | 1 |  |  |  |  |  | 1x Insertion; 1x Task plan |
| **all** | | 1 | 19 |  | 16 | 3 |  | 22 |  |  | |

