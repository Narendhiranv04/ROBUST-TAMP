# Run report: /home/user1/robust_tamp_infer/real_trials/scale/qwen3-4b-fp8

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 14.4 | 0.0 | 9.3 | 28.2 | 242.3 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 30.0 | 42.0 | 5.7 | 174.1 | 196.4 | 16707.1 | 1 | missing_post_pick_place: 6, invalid_corrective_block: 12, repeated_planner_output: 14, planner_output_not_parseable: 1, orphan_place: 4 | - | replan_loop: 7, plan_completed: 3 |
| FINAL.G0 | 10/10 | 0.0 | 60.0 | 7.2 | 197.7 | 230.1 | 19086.8 | 0 | invalid_corrective_block: 18, repeated_planner_output: 16, pick_place_mismatch: 16, missing_post_pick_place: 3, orphan_place: 3, unknown_action_token: 5 | - | replan_loop: 7, replan_budget_exhausted: 2, plan_completed: 1 |
| FINAL.K1 | 10/10 | 0.0 | 5.7 | 7.9 | 220.3 | 232.8 | 20642.9 | 2 | orphan_place: 6, missing_post_pick_place: 5, planner_output_not_parseable: 3, invalid_corrective_block: 23, repeated_planner_output: 19, insertion_too_late: 4 | - | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K2 | 10/10 | 100.0 | 100.0 | 3.6 | 123.9 | 174.3 | 14385.5 | 1 | orphan_place: 2, missing_post_pick_place: 7, planner_output_not_parseable: 1, invalid_corrective_block: 2, repeated_planner_output: 2 | - | plan_completed: 9, replan_loop: 1 |
| FINAL.K3 | 10/10 | 0.0 | 2.9 | 6.9 | 145.2 | 157.1 | 15413.4 | 0 | missing_post_pick_place: 6, invalid_corrective_block: 18, repeated_planner_output: 18, orphan_place: 4 | - | replan_loop: 9, planner_returned_no_actions: 1 |
| FINAL.K4 | 10/10 | 0.0 | 3.3 | 8.2 | 322.3 | 332.2 | 35618.1 | 5 | missing_post_pick_place: 12, invalid_corrective_block: 14, repeated_planner_output: 14, orphan_place: 15, planner_output_not_parseable: 6 | - | replan_loop: 6, planner_returned_no_actions: 1, replan_budget_exhausted: 3 |
| FINAL.G1 | 10/10 | 0.0 | 56.7 | 8.1 | 244.9 | 273.6 | 20018.4 | 0 | pick_place_mismatch: 11, orphan_place: 2, missing_post_pick_place: 4, invalid_corrective_block: 24, repeated_planner_output: 18, unknown_action_token: 5 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.G2 | 10/10 | 0.0 | 32.5 | 8.4 | 350.6 | 369.4 | 33697.0 | 3 | unknown_action_token: 11, invalid_corrective_block: 16, repeated_planner_output: 15, pick_place_mismatch: 18, orphan_place: 3, planner_output_not_parseable: 4, missing_post_pick_place: 8 | - | replan_loop: 7, replan_budget_exhausted: 3 |
| FINAL.G3 | 10/10 | 0.0 | 34.3 | 9.3 | 375.5 | 417.5 | 35710.9 | 1 | orphan_place: 17, pick_place_mismatch: 10, unknown_action_token: 12, invalid_corrective_block: 18, repeated_planner_output: 11, missing_post_pick_place: 5, planner_output_not_parseable: 4 | - | replan_loop: 5, replan_budget_exhausted: 4, plan_completed: 1 |
| FINAL.K3-n2 | 10/10 | 0.0 | 0.0 | 7.9 | 267.5 | 280.7 | 25047.5 | 2 | invalid_corrective_block: 20, repeated_planner_output: 19, planner_output_not_parseable: 4, missing_post_pick_place: 7, orphan_place: 5 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.K3-n3 | 10/10 | 0.0 | 1.8 | 7.4 | 257.6 | 270.8 | 20284.9 | 1 | missing_post_pick_place: 6, invalid_corrective_block: 21, repeated_planner_output: 20, orphan_place: 3, planner_output_not_parseable: 2 | - | replan_loop: 10 |
| FINAL.G1-n1 | 10/10 | 0.0 | 51.7 | 7.4 | 291.0 | 313.1 | 19006.0 | 0 | invalid_corrective_block: 22, repeated_planner_output: 19, unknown_action_token: 3, pick_place_mismatch: 9, missing_post_pick_place: 3, orphan_place: 7 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.K1-w1 | 10/10 | 0.0 | 3.8 | 6.8 | 188.0 | 200.8 | 16724.2 | 1 | orphan_place: 3, invalid_corrective_block: 20, repeated_planner_output: 18, missing_post_pick_place: 4, planner_output_not_parseable: 1 | - | replan_loop: 9, planner_returned_no_actions: 1 |
| FINAL.K1-w2 | 10/10 | 0.0 | 0.0 | 8.5 | 233.9 | 246.8 | 20727.3 | 0 | planner_output_not_parseable: 3, unknown_action_token: 1, invalid_corrective_block: 21, repeated_planner_output: 20, missing_post_pick_place: 6, orphan_place: 9, insertion_too_late: 1 | - | replan_loop: 8, replan_budget_exhausted: 2 |

Planner call latency (s): mean 32.8431, p50 25.769, p90 49.625, max 281.90575981140137 over 1033 calls
Output tokens per call: mean 4018.8703, p50 3427, p90 5803, max 24576; cut off at the limit: 17
