# Run report: /home/user1/robust_tamp_infer/real_trials/scale/qwen3-vl-4b-thinking-fp8

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 57.8 | 12.0 | 41.4 | 59.2 | 743.2 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 100.0 | 100.0 | 2.5 | 241.5 | 287.8 | 22158.8 | 0 | missing_post_pick_place: 4, orphan_place: 3 | - | plan_completed: 10 |
| FINAL.G0 | 10/10 | 10.0 | 63.3 | 7.1 | 709.1 | 808.7 | 55596.4 | 0 | unknown_action_token: 10, pick_place_mismatch: 5, orphan_place: 7, invalid_corrective_block: 11, repeated_planner_output: 10 | - | plan_completed: 6, replan_budget_exhausted: 1, replan_loop: 3 |
| FINAL.K1 | 10/10 | 10.0 | 10.0 | 10.3 | 1050.3 | 1067.2 | 38822.4 | 0 | insertion_too_late: 29, invalid_corrective_block: 32, repeated_planner_output: 8, missing_post_pick_place: 5, orphan_place: 8 | - | replan_budget_exhausted: 7, plan_completed: 1, replan_loop: 2 |
| FINAL.K2 | 10/10 | 90.0 | 98.3 | 3.7 | 374.0 | 423.5 | 34581.8 | 0 | orphan_place: 14, repeated_planner_output: 2, missing_post_pick_place: 3 | - | plan_completed: 10 |
| FINAL.K3 | 10/10 | 80.0 | 80.0 | 5.1 | 457.9 | 508.0 | 34165.7 | 0 | orphan_place: 9, invalid_corrective_block: 12, missing_post_pick_place: 2, repeated_planner_output: 4 | - | plan_completed: 8, replan_loop: 2 |
| FINAL.K4 | 10/10 | 90.0 | 93.3 | 5.4 | 521.0 | 565.9 | 45029.9 | 0 | orphan_place: 13, invalid_corrective_block: 6, missing_post_pick_place: 4, repeated_planner_output: 3 | - | plan_completed: 9, replan_loop: 1 |
| FINAL.G1 | 10/10 | 20.0 | 72.2 | 7.8 | 761.6 | 805.9 | 48095.0 | 0 | missing_post_pick_place: 1, invalid_corrective_block: 25, repeated_planner_output: 16, unknown_action_token: 7, pick_place_mismatch: 4, orphan_place: 3 | - | replan_loop: 7, plan_completed: 3 |
| FINAL.G2 | 10/10 | 0.0 | 43.8 | 9.0 | 1295.8 | 1324.4 | 57276.6 | 0 | invalid_corrective_block: 40, repeated_planner_output: 14, unknown_action_token: 9, orphan_place: 4, missing_post_pick_place: 1, pick_place_mismatch: 2, unobserved_object: 1 | - | replan_loop: 6, replan_budget_exhausted: 4 |
| FINAL.G3 | 10/10 | 10.0 | 17.1 | 7.4 | 855.9 | 885.3 | 35179.9 | 0 | pick_place_mismatch: 2, invalid_corrective_block: 40, repeated_planner_output: 18, unknown_action_token: 2, orphan_place: 1 | - | replan_loop: 9, plan_completed: 1 |
| FINAL.K3-n2 | 10/10 | 70.0 | 87.8 | 5.1 | 485.3 | 551.5 | 36463.2 | 0 | orphan_place: 9, invalid_corrective_block: 10, missing_post_pick_place: 2, repeated_planner_output: 4 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3-n3 | 10/10 | 70.0 | 77.3 | 7.2 | 710.6 | 779.2 | 46892.2 | 0 | orphan_place: 13, repeated_planner_output: 7, invalid_corrective_block: 19, missing_post_pick_place: 2, unknown_action_token: 1 | - | plan_completed: 7, replan_budget_exhausted: 1, replan_loop: 2 |
| FINAL.G1-n1 | 10/10 | 20.0 | 71.7 | 7.9 | 805.9 | 858.9 | 50157.0 | 0 | invalid_corrective_block: 23, orphan_place: 8, unknown_action_token: 5, repeated_planner_output: 11, pick_place_mismatch: 3 | - | replan_loop: 4, plan_completed: 5, replan_budget_exhausted: 1 |
| FINAL.K1-w1 | 10/10 | 10.0 | 13.8 | 10.4 | 1025.9 | 1048.2 | 28562.7 | 0 | missing_post_pick_place: 2, invalid_corrective_block: 43, insertion_too_late: 32, orphan_place: 6, repeated_planner_output: 1 | - | replan_budget_exhausted: 9, plan_completed: 1 |
| FINAL.K1-w2 | 10/10 | 0.0 | 0.0 | 11.0 | 1110.3 | 1126.7 | 37844.2 | 0 | orphan_place: 9, invalid_corrective_block: 42, repeated_planner_output: 3, insertion_too_late: 31, missing_post_pick_place: 5 | - | replan_budget_exhausted: 10 |

Planner call latency (s): mean 104.1546, p50 99.915, p90 146.804, max 295.50554490089417 over 999 calls
Output tokens per call: mean 9529.6461, p50 9376, p90 13022, max 19016; cut off at the limit: 0
