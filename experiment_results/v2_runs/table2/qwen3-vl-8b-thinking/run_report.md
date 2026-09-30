# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/qwen3-vl-8b-thinking

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 87.8 | 22.0 | 64.3 | 86.3 | 540.4 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 100.0 | 100.0 | 2.2 | 228.9 | 298.4 | 15857.5 | 0 | orphan_place: 3, missing_post_pick_place: 1 | - | plan_completed: 10 |
| FINAL.G0 | 10/10 | 30.0 | 63.3 | 3.2 | 351.8 | 486.9 | 23597.9 | 0 | missing_post_pick_place: 1, unknown_action_token: 1, invalid_corrective_block: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1 | 10/10 | 90.0 | 92.9 | 5.7 | 480.5 | 560.5 | 22331.6 | 0 | orphan_place: 4, insertion_too_late: 15, invalid_corrective_block: 5, missing_post_pick_place: 1, repeated_planner_output: 1, unknown_action_token: 1 | - | replan_budget_exhausted: 1, plan_completed: 9 |
| FINAL.K2 | 10/10 | 90.0 | 95.0 | 4.0 | 327.8 | 396.8 | 23139.5 | 0 | orphan_place: 7, repeated_planner_output: 1, missing_post_pick_place: 4 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3 | 10/10 | 100.0 | 100.0 | 3.8 | 385.5 | 479.8 | 24981.9 | 0 | orphan_place: 5, missing_post_pick_place: 3, insertion_too_late: 1, invalid_corrective_block: 2 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100.0 | 100.0 | 3.1 | 315.9 | 390.1 | 21527.1 | 0 | orphan_place: 3, invalid_corrective_block: 2, missing_post_pick_place: 1 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 40.0 | 84.4 | 5.4 | 683.7 | 773.6 | 35762.9 | 0 | orphan_place: 6, invalid_corrective_block: 8, unknown_action_token: 1 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G2 | 10/10 | 10.0 | 62.5 | 6.2 | 916.2 | 1016.7 | 41962.0 | 0 | invalid_corrective_block: 17, unknown_action_token: 1 | - | replan_budget_exhausted: 2, plan_completed: 8 |
| FINAL.G3 | 10/10 | 10.0 | 47.1 | 9.6 | 1223.5 | 1354.0 | 66082.0 | 0 | invalid_corrective_block: 16, orphan_place: 19, repeated_planner_output: 1, pick_place_mismatch: 1, remembered_object_inaccessible: 1 | - | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K3-n2 | 10/10 | 90.0 | 98.9 | 3.9 | 412.5 | 522.4 | 24072.7 | 0 | orphan_place: 5, missing_post_pick_place: 2, invalid_corrective_block: 1, insertion_too_late: 3 | - | plan_completed: 10 |
| FINAL.K3-n3 | 10/10 | 70.0 | 97.3 | 4.0 | 442.1 | 580.2 | 28395.2 | 0 | orphan_place: 4, missing_post_pick_place: 6, insertion_too_late: 1, repeated_planner_output: 1 | - | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 20.0 | 76.7 | 5.8 | 626.1 | 714.3 | 37164.5 | 0 | unknown_action_token: 1, pick_place_mismatch: 1, orphan_place: 2, missing_post_pick_place: 1, invalid_corrective_block: 6, unobserved_object: 2 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w1 | 10/10 | 80.0 | 97.5 | 7.7 | 655.4 | 773.5 | 30975.2 | 0 | orphan_place: 6, insertion_too_late: 19, missing_post_pick_place: 2, repeated_planner_output: 2, invalid_corrective_block: 10, unknown_action_token: 1 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K1-w2 | 10/10 | 70.0 | 92.2 | 6.4 | 515.1 | 648.0 | 27142.3 | 0 | missing_post_pick_place: 1, insertion_too_late: 14, invalid_corrective_block: 7, orphan_place: 6 | - | plan_completed: 9, replan_budget_exhausted: 1 |

Planner call latency (s): mean 106.5489, p50 103.424, p90 160.038, max 301.2916386127472 over 710 calls
Output tokens per call: mean 7369.2038, p50 7200, p90 10707, max 16634; cut off at the limit: 0
