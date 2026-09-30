# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/qwen3-8b

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 78.9 | 4.0 | 52.1 | 70.2 | 327.2 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 80.0 | 80.0 | 3.5 | 153.8 | 218.3 | 12504.8 | 0 | missing_post_pick_place: 7, orphan_place: 7, repeated_planner_output: 4 | - | plan_completed: 8, replan_loop: 2 |
| FINAL.G0 | 10/10 | 10.0 | 56.7 | 8.2 | 292.4 | 434.4 | 19341.3 | 0 | invalid_corrective_block: 15, repeated_planner_output: 4, orphan_place: 5 | - | plan_completed: 5, replan_budget_exhausted: 5 |
| FINAL.K1 | 10/10 | 80.0 | 81.4 | 6.5 | 259.1 | 337.5 | 15805.7 | 1 | orphan_place: 7, insertion_too_late: 19, missing_post_pick_place: 3, planner_output_not_parseable: 1, repeated_planner_output: 2, invalid_corrective_block: 4, unknown_action_token: 1 | - | replan_budget_exhausted: 1, replan_loop: 1, plan_completed: 8 |
| FINAL.K2 | 10/10 | 90.0 | 95.0 | 3.6 | 138.8 | 215.2 | 10045.6 | 0 | orphan_place: 7, invalid_corrective_block: 7, missing_post_pick_place: 5 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3 | 10/10 | 90.0 | 90.0 | 6.0 | 246.2 | 336.3 | 15846.6 | 0 | missing_post_pick_place: 10, orphan_place: 8, invalid_corrective_block: 13, repeated_planner_output: 2 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K4 | 10/10 | 90.0 | 90.0 | 4.9 | 175.7 | 253.2 | 13103.3 | 0 | orphan_place: 4, invalid_corrective_block: 7, missing_post_pick_place: 8, repeated_planner_output: 3 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1 | 10/10 | 0.0 | 55.6 | 10.1 | 511.6 | 554.1 | 15762.4 | 0 | invalid_corrective_block: 63, pick_place_mismatch: 1, missing_post_pick_place: 2, unknown_action_token: 1, repeated_planner_output: 6, orphan_place: 6 | - | replan_budget_exhausted: 7, replan_loop: 2, plan_completed: 1 |
| FINAL.G2 | 10/10 | 10.0 | 52.5 | 10.5 | 637.6 | 698.2 | 14201.7 | 0 | invalid_corrective_block: 74, repeated_planner_output: 1, pick_place_mismatch: 3, orphan_place: 1 | - | replan_budget_exhausted: 9, plan_completed: 1 |
| FINAL.G3 | 10/10 | 0.0 | 12.9 | 10.1 | 506.5 | 539.7 | 9877.1 | 0 | invalid_corrective_block: 76, repeated_planner_output: 7, unknown_action_token: 1, pick_place_mismatch: 1, missing_post_pick_place: 1, orphan_place: 1 | - | replan_budget_exhausted: 7, replan_loop: 3 |
| FINAL.K3-n2 | 10/10 | 80.0 | 88.9 | 6.2 | 228.4 | 332.2 | 14615.2 | 0 | orphan_place: 7, invalid_corrective_block: 15, missing_post_pick_place: 4, repeated_planner_output: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n3 | 10/10 | 80.0 | 94.5 | 6.3 | 263.8 | 396.2 | 19839.1 | 0 | missing_post_pick_place: 14, repeated_planner_output: 4, orphan_place: 4, invalid_corrective_block: 6 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1-n1 | 10/10 | 0.0 | 51.7 | 10.4 | 510.9 | 563.3 | 16264.0 | 0 | invalid_corrective_block: 61, pick_place_mismatch: 1, repeated_planner_output: 5, orphan_place: 4, unknown_action_token: 1 | - | replan_budget_exhausted: 7, replan_loop: 2, plan_completed: 1 |
| FINAL.K1-w1 | 10/10 | 60.0 | 63.7 | 10.0 | 346.5 | 426.0 | 18160.6 | 0 | missing_post_pick_place: 11, orphan_place: 12, insertion_too_late: 26, invalid_corrective_block: 15, repeated_planner_output: 7 | - | replan_budget_exhausted: 3, plan_completed: 6, replan_loop: 1 |
| FINAL.K1-w2 | 10/10 | 60.0 | 70.0 | 8.3 | 309.1 | 411.1 | 17248.7 | 0 | insertion_too_late: 21, orphan_place: 12, invalid_corrective_block: 11, missing_post_pick_place: 3, pick_place_mismatch: 1, repeated_planner_output: 2 | - | replan_budget_exhausted: 4, plan_completed: 6 |

Planner call latency (s): mean 43.791, p50 41.716, p90 68.998, max 340.16854453086853 over 1046 calls
Output tokens per call: mean 3491.2332, p50 3319, p90 5442, max 24576; cut off at the limit: 1
