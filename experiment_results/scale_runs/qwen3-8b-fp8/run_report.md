# Run report: /home/user1/robust_tamp_infer/real_trials/scale/qwen3-8b-fp8

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 80.0 | 6.0 | 53.6 | 72.2 | 296.8 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 100.0 | 100.0 | 4.7 | 208.1 | 256.8 | 19546.5 | 2 | missing_post_pick_place: 11, planner_output_not_parseable: 2, orphan_place: 10, repeated_planner_output: 3 | - | plan_completed: 10 |
| FINAL.G0 | 10/10 | 10.0 | 46.7 | 8.1 | 289.8 | 384.4 | 22437.3 | 0 | invalid_corrective_block: 13, orphan_place: 4, unknown_action_token: 1, missing_post_pick_place: 1, pick_place_mismatch: 1, repeated_planner_output: 1 | - | replan_budget_exhausted: 6, plan_completed: 4 |
| FINAL.K1 | 10/10 | 70.0 | 77.1 | 7.1 | 259.4 | 305.4 | 19662.5 | 0 | missing_post_pick_place: 10, orphan_place: 13, insertion_too_late: 14, repeated_planner_output: 4, invalid_corrective_block: 1 | - | replan_budget_exhausted: 2, plan_completed: 7, replan_loop: 1 |
| FINAL.K2 | 10/10 | 100.0 | 100.0 | 3.2 | 113.9 | 163.7 | 10825.0 | 0 | orphan_place: 6, missing_post_pick_place: 6, repeated_planner_output: 2 | - | plan_completed: 10 |
| FINAL.K3 | 10/10 | 90.0 | 90.0 | 5.6 | 179.5 | 235.1 | 16833.4 | 0 | missing_post_pick_place: 12, orphan_place: 7, repeated_planner_output: 5, planner_output_not_parseable: 1, invalid_corrective_block: 3 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K4 | 10/10 | 90.0 | 90.0 | 6.0 | 230.6 | 276.3 | 21102.4 | 1 | missing_post_pick_place: 17, orphan_place: 7, planner_output_not_parseable: 1, repeated_planner_output: 2, invalid_corrective_block: 3 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1 | 10/10 | 0.0 | 66.7 | 10.3 | 433.8 | 480.9 | 15203.3 | 0 | unknown_action_token: 2, invalid_corrective_block: 62, repeated_planner_output: 3, orphan_place: 3, pick_place_mismatch: 1 | - | replan_budget_exhausted: 7, replan_loop: 1, plan_completed: 2 |
| FINAL.G2 | 10/10 | 0.0 | 52.5 | 10.0 | 481.9 | 531.1 | 17660.5 | 0 | invalid_corrective_block: 56, orphan_place: 5, remembered_object_inaccessible: 1 | - | plan_completed: 2, replan_budget_exhausted: 8 |
| FINAL.G3 | 10/10 | 0.0 | 10.0 | 11.0 | 514.4 | 548.1 | 15997.6 | 0 | invalid_corrective_block: 66, pick_place_mismatch: 3, orphan_place: 12, insertion_too_late: 2 | - | replan_budget_exhausted: 10 |
| FINAL.K3-n2 | 10/10 | 90.0 | 98.9 | 5.8 | 239.6 | 314.4 | 19685.5 | 1 | missing_post_pick_place: 12, repeated_planner_output: 2, orphan_place: 5, planner_output_not_parseable: 1, invalid_corrective_block: 6 | - | plan_completed: 10 |
| FINAL.K3-n3 | 10/10 | 90.0 | 99.1 | 6.0 | 221.7 | 307.7 | 18851.6 | 0 | missing_post_pick_place: 12, repeated_planner_output: 1, invalid_corrective_block: 7, orphan_place: 10 | - | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 20.0 | 75.0 | 9.9 | 410.4 | 471.3 | 17251.9 | 0 | invalid_corrective_block: 49, unobserved_object: 1, orphan_place: 3 | - | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K1-w1 | 10/10 | 30.0 | 41.2 | 9.6 | 326.6 | 364.1 | 25516.3 | 1 | orphan_place: 10, insertion_too_late: 20, missing_post_pick_place: 19, invalid_corrective_block: 5, repeated_planner_output: 8, planner_output_not_parseable: 2 | - | plan_completed: 4, replan_budget_exhausted: 4, replan_loop: 2 |
| FINAL.K1-w2 | 10/10 | 60.0 | 63.3 | 9.2 | 245.7 | 305.8 | 18374.1 | 0 | missing_post_pick_place: 10, orphan_place: 15, insertion_too_late: 23, invalid_corrective_block: 10, repeated_planner_output: 2 | - | replan_budget_exhausted: 4, plan_completed: 6 |

Planner call latency (s): mean 39.0159, p50 34.199, p90 60.772, max 325.3850266933441 over 1065 calls
Output tokens per call: mean 3611.5467, p50 3186, p90 5616, max 24576; cut off at the limit: 5
