# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/internvl3.5-8b

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 15.6 | 0.0 | 10.0 | 23.8 | 75.9 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 40.0 | 54.0 | 8.6 | 59.7 | 102.1 | 2153.7 | 0 | repeated_planner_output: 15, invalid_corrective_block: 13, orphan_place: 4, missing_post_pick_place: 5 | - | replan_budget_exhausted: 4, plan_completed: 4, replan_loop: 2 |
| FINAL.G0 | 10/10 | 0.0 | 16.7 | 8.9 | 43.5 | 107.0 | 797.2 | 0 | invalid_corrective_block: 55, repeated_planner_output: 15, unknown_action_token: 1, orphan_place: 2 | - | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.K1 | 10/10 | 0.0 | 8.6 | 9.7 | 52.5 | 73.3 | 1728.8 | 0 | repeated_planner_output: 17, orphan_place: 4, invalid_corrective_block: 29, unknown_action_token: 2, missing_post_pick_place: 1, insertion_too_late: 5 | - | replan_budget_exhausted: 5, replan_loop: 5 |
| FINAL.K2 | 10/10 | 20.0 | 43.3 | 9.5 | 129.6 | 158.5 | 2195.6 | 0 | repeated_planner_output: 17, orphan_place: 6, invalid_corrective_block: 16, missing_post_pick_place: 6 | - | replan_loop: 4, plan_completed: 2, replan_budget_exhausted: 4 |
| FINAL.K3 | 10/10 | 10.0 | 14.3 | 8.9 | 67.5 | 96.8 | 2131.3 | 0 | orphan_place: 7, invalid_corrective_block: 19, repeated_planner_output: 15, missing_post_pick_place: 5, unknown_action_token: 1 | - | replan_budget_exhausted: 5, replan_loop: 4, plan_completed: 1 |
| FINAL.K4 | 10/10 | 40.0 | 46.7 | 9.3 | 60.9 | 115.5 | 2381.7 | 0 | repeated_planner_output: 14, orphan_place: 9, invalid_corrective_block: 13, missing_post_pick_place: 8 | - | plan_completed: 4, replan_budget_exhausted: 3, replan_loop: 3 |
| FINAL.G1 | 10/10 | 0.0 | 51.1 | 10.5 | 112.0 | 162.3 | 4380.0 | 1 | unknown_action_token: 1, invalid_corrective_block: 69, orphan_place: 1, repeated_planner_output: 4 | - | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.G2 | 10/10 | 0.0 | 25.0 | 9.5 | 58.3 | 100.1 | 858.5 | 0 | invalid_corrective_block: 64, repeated_planner_output: 12, remembered_object_inaccessible: 1 | - | replan_loop: 5, replan_budget_exhausted: 5 |
| FINAL.G3 | 10/10 | 0.0 | 2.9 | 9.1 | 50.4 | 91.5 | 1064.4 | 0 | invalid_corrective_block: 54, repeated_planner_output: 16, orphan_place: 1 | - | replan_loop: 6, replan_budget_exhausted: 4 |
| FINAL.K3-n2 | 10/10 | 20.0 | 20.0 | 8.6 | 41.9 | 80.2 | 2404.5 | 0 | repeated_planner_output: 12, orphan_place: 6, missing_post_pick_place: 16, invalid_corrective_block: 7 | - | replan_budget_exhausted: 5, replan_loop: 3, plan_completed: 2 |
| FINAL.K3-n3 | 10/10 | 10.0 | 10.0 | 9.5 | 139.8 | 172.8 | 2406.9 | 0 | orphan_place: 5, invalid_corrective_block: 23, repeated_planner_output: 11, missing_post_pick_place: 7, insertion_too_late: 2, pick_place_mismatch: 1 | - | replan_budget_exhausted: 7, plan_completed: 1, replan_loop: 2 |
| FINAL.G1-n1 | 10/10 | 0.0 | 26.7 | 9.6 | 54.1 | 104.7 | 1086.8 | 0 | invalid_corrective_block: 59, repeated_planner_output: 15, unknown_action_token: 3, orphan_place: 1 | - | replan_loop: 6, replan_budget_exhausted: 4 |
| FINAL.K1-w1 | 10/10 | 0.0 | 7.5 | 10.2 | 128.2 | 153.4 | 1997.0 | 0 | repeated_planner_output: 12, invalid_corrective_block: 25, insertion_too_late: 8, unknown_action_token: 1, missing_post_pick_place: 6, orphan_place: 10 | - | replan_budget_exhausted: 8, replan_loop: 2 |
| FINAL.K1-w2 | 10/10 | 0.0 | 6.7 | 9.3 | 64.2 | 79.5 | 1801.4 | 0 | repeated_planner_output: 13, insertion_too_late: 7, invalid_corrective_block: 23, orphan_place: 4, unknown_action_token: 2, missing_post_pick_place: 4, pick_place_mismatch: 1 | - | replan_budget_exhausted: 6, replan_loop: 4 |

Planner call latency (s): mean 8.0993, p50 4.64, p90 8.927, max 392.7115318775177 over 1312 calls
Output tokens per call: mean 338.5389, p50 266, p90 459, max 24576; cut off at the limit: 1
