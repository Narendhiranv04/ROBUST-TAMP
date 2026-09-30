# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/ablations/fixed_front

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 90.0 | 20.0 | 60.0 | 80.9 | 699.7 | 70 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 80.0 | 82.9 | 6.2 | 572.9 | 648.6 | 25030.4 | 0 | orphan_place: 9, insertion_too_late: 16, invalid_corrective_block: 9 | - | replan_budget_exhausted: 2, plan_completed: 8 |
| FINAL.K2 | 10/10 | 90.0 | 95.0 | 2.9 | 268.8 | 340.7 | 17977.2 | 0 | orphan_place: 5 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3 | 10/10 | 100.0 | 100.0 | 2.9 | 284.9 | 378.2 | 19246.1 | 0 | missing_post_pick_place: 2, orphan_place: 2 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 90.0 | 95.0 | 4.1 | 451.3 | 522.8 | 30702.7 | 0 | missing_post_pick_place: 3, orphan_place: 5 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1 | 10/10 | 50.0 | 90.0 | 6.2 | 797.3 | 896.6 | 32418.3 | 0 | invalid_corrective_block: 19, orphan_place: 2, repeated_planner_output: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G2 | 10/10 | 10.0 | 67.5 | 7.5 | 1143.2 | 1245.1 | 50879.9 | 0 | pick_place_mismatch: 1, invalid_corrective_block: 20, orphan_place: 10, unknown_action_token: 4, repeated_planner_output: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G3 | 10/10 | 0.0 | 35.7 | 10.1 | 1379.8 | 1476.1 | 70471.3 | 0 | invalid_corrective_block: 17, orphan_place: 19, remembered_object_inaccessible: 1, unknown_action_token: 3, pick_place_mismatch: 1 | - | replan_budget_exhausted: 8, plan_completed: 2 |

Planner call latency (s): mean 122.7627, p50 119.977, p90 183.494, max 331.25459599494934 over 399 calls
Output tokens per call: mean 7933.3087, p50 7882, p90 11489, max 19142; cut off at the limit: 0
