# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/table2/qwen3-8b

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 63.3 | 2.0 | 41.4 | 63.3 | 324.4 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 70.0 | 84.0 | 4.1 | 141.2 | 206.9 | 10745.1 | 0 | missing_post_pick_place: 8, orphan_place: 4, invalid_corrective_block: 5, repeated_planner_output: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G0 | 10/10 | 0.0 | 36.7 | 8.5 | 359.6 | 461.5 | 15220.5 | 0 | pick_place_mismatch: 2, invalid_corrective_block: 33, unknown_action_token: 1, repeated_planner_output: 1, orphan_place: 1 | - | plan_completed: 3, replan_budget_exhausted: 7 |
| FINAL.K1 | 10/10 | 40.0 | 42.9 | 7.9 | 295.7 | 341.3 | 14400.0 | 1 | insertion_too_late: 31, invalid_corrective_block: 11, repeated_planner_output: 6, orphan_place: 2, missing_post_pick_place: 6, planner_output_not_parseable: 1 | - | replan_loop: 2, replan_budget_exhausted: 4, plan_completed: 4 |
| FINAL.K2 | 10/10 | 70.0 | 86.7 | 5.1 | 194.9 | 264.5 | 14502.3 | 0 | missing_post_pick_place: 8, repeated_planner_output: 2, orphan_place: 9, invalid_corrective_block: 7 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3 | 10/10 | 100.0 | 100.0 | 4.7 | 164.6 | 256.8 | 12972.3 | 0 | invalid_corrective_block: 4, missing_post_pick_place: 8, repeated_planner_output: 2, orphan_place: 4 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 60.0 | 73.3 | 7.7 | 259.9 | 319.2 | 17750.3 | 0 | orphan_place: 4, missing_post_pick_place: 14, invalid_corrective_block: 14, repeated_planner_output: 6 | - | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G1 | 10/10 | 0.0 | 60.0 | 10.0 | 457.5 | 501.1 | 14961.9 | 0 | invalid_corrective_block: 64, repeated_planner_output: 4, orphan_place: 2 | - | replan_budget_exhausted: 7, plan_completed: 1, replan_loop: 2 |
| FINAL.G2 | 10/10 | 0.0 | 61.3 | 10.3 | 539.9 | 604.6 | 21970.6 | 0 | invalid_corrective_block: 49, orphan_place: 9, repeated_planner_output: 2, missing_post_pick_place: 1, pick_place_mismatch: 3 | - | replan_budget_exhausted: 8, replan_loop: 1, plan_completed: 1 |
| FINAL.G3 | 10/10 | 0.0 | 8.6 | 11.0 | 595.7 | 626.2 | 8413.9 | 0 | pick_place_mismatch: 1, invalid_corrective_block: 91, repeated_planner_output: 3, orphan_place: 1, missing_post_pick_place: 1 | - | replan_budget_exhausted: 10 |
| FINAL.K3-n2 | 10/10 | 80.0 | 91.1 | 6.9 | 245.8 | 347.7 | 12572.3 | 0 | invalid_corrective_block: 30, repeated_planner_output: 4, missing_post_pick_place: 6, orphan_place: 2 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n3 | 10/10 | 60.0 | 80.9 | 7.3 | 267.3 | 383.7 | 17300.4 | 0 | invalid_corrective_block: 19, missing_post_pick_place: 6, orphan_place: 5, repeated_planner_output: 5 | - | plan_completed: 7, replan_budget_exhausted: 2, replan_loop: 1 |
| FINAL.G1-n1 | 10/10 | 10.0 | 61.7 | 9.9 | 415.8 | 457.4 | 11201.6 | 0 | pick_place_mismatch: 1, invalid_corrective_block: 68, repeated_planner_output: 10 | - | replan_loop: 4, replan_budget_exhausted: 5, plan_completed: 1 |
| FINAL.K1-w1 | 10/10 | 50.0 | 51.2 | 7.8 | 267.7 | 331.2 | 12042.6 | 0 | missing_post_pick_place: 9, repeated_planner_output: 4, insertion_too_late: 31, invalid_corrective_block: 12, orphan_place: 2 | - | plan_completed: 5, replan_budget_exhausted: 4, replan_loop: 1 |
| FINAL.K1-w2 | 10/10 | 40.0 | 47.8 | 8.9 | 336.1 | 404.8 | 21708.5 | 1 | missing_post_pick_place: 20, repeated_planner_output: 10, insertion_too_late: 12, invalid_corrective_block: 11, planner_output_not_parseable: 1, orphan_place: 3 | - | plan_completed: 4, replan_budget_exhausted: 3, replan_loop: 3 |

Planner call latency (s): mean 41.2486, p50 37.032, p90 65.614, max 343.7954685688019 over 1101 calls
Output tokens per call: mean 3406.6606, p50 3150, p90 5445, max 24576; cut off at the limit: 2
