# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/llama-3.1-8b-instruct

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 6.7 | 0.0 | 4.3 | 17.2 | 123.8 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 10.0 | 30.0 | 10.1 | 80.9 | 113.2 | 2346.1 | 0 | pick_place_mismatch: 13, unknown_action_token: 19, repeated_planner_output: 3, orphan_place: 1, invalid_corrective_block: 33, missing_post_pick_place: 4 | - | replan_budget_exhausted: 9, plan_completed: 1 |
| FINAL.G0 | 10/10 | 0.0 | 20.0 | 11.0 | 96.2 | 136.4 | 4275.4 | 1 | orphan_place: 7, missing_post_pick_place: 6, unknown_action_token: 23, invalid_corrective_block: 56, repeated_planner_output: 2, pick_place_mismatch: 4, planner_output_not_parseable: 1 | - | replan_budget_exhausted: 10 |
| FINAL.K1 | 10/10 | 0.0 | 1.4 | 11.0 | 125.1 | 144.6 | 7911.3 | 2 | pick_place_mismatch: 16, unknown_action_token: 21, invalid_corrective_block: 24, planner_output_not_parseable: 2, missing_post_pick_place: 12, repeated_planner_output: 1, orphan_place: 1 | - | replan_budget_exhausted: 10 |
| FINAL.K2 | 10/10 | 50.0 | 63.3 | 8.5 | 37.5 | 88.6 | 2510.6 | 0 | missing_post_pick_place: 8, pick_place_mismatch: 20, orphan_place: 4, unknown_action_token: 15, repeated_planner_output: 1, invalid_corrective_block: 10 | - | replan_budget_exhausted: 5, plan_completed: 5 |
| FINAL.K3 | 10/10 | 0.0 | 0.0 | 11.0 | 85.2 | 96.8 | 5641.3 | 1 | pick_place_mismatch: 27, missing_post_pick_place: 8, unknown_action_token: 29, invalid_corrective_block: 20, repeated_planner_output: 3, orphan_place: 1, planner_output_not_parseable: 1 | - | replan_budget_exhausted: 10 |
| FINAL.K4 | 10/10 | 0.0 | 10.0 | 11.0 | 182.0 | 203.7 | 10035.9 | 3 | unknown_action_token: 24, repeated_planner_output: 4, missing_post_pick_place: 8, invalid_corrective_block: 30, pick_place_mismatch: 9, planner_output_not_parseable: 3, orphan_place: 4 | - | replan_budget_exhausted: 10 |
| FINAL.G1 | 10/10 | 0.0 | 45.6 | 10.4 | 184.5 | 215.5 | 4147.2 | 1 | unknown_action_token: 22, missing_post_pick_place: 4, invalid_corrective_block: 53, repeated_planner_output: 11, planner_output_not_parseable: 1, orphan_place: 1, unobserved_object: 1 | - | replan_budget_exhausted: 6, replan_loop: 4 |
| FINAL.G2 | 10/10 | 0.0 | 30.0 | 11.0 | 160.3 | 197.4 | 7554.6 | 2 | unknown_action_token: 39, orphan_place: 10, missing_post_pick_place: 7, planner_output_not_parseable: 2, invalid_corrective_block: 34, repeated_planner_output: 3, pick_place_mismatch: 2, unobserved_object: 1 | - | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.G3 | 10/10 | 0.0 | 1.4 | 11.0 | 226.3 | 259.9 | 8553.7 | 3 | unknown_action_token: 13, orphan_place: 10, missing_post_pick_place: 7, invalid_corrective_block: 67, planner_output_not_parseable: 3 | - | replan_budget_exhausted: 10 |
| FINAL.K3-n2 | 10/10 | 0.0 | 0.0 | 9.5 | 38.3 | 55.7 | 2200.1 | 0 | unknown_action_token: 13, invalid_corrective_block: 30, repeated_planner_output: 8, pick_place_mismatch: 15, orphan_place: 4, missing_post_pick_place: 2 | - | replan_loop: 4, replan_budget_exhausted: 6 |
| FINAL.K3-n3 | 10/10 | 0.0 | 1.8 | 10.6 | 46.5 | 67.4 | 2696.1 | 0 | unknown_action_token: 20, orphan_place: 7, pick_place_mismatch: 12, missing_post_pick_place: 8, repeated_planner_output: 8, invalid_corrective_block: 27 | - | replan_budget_exhausted: 7, replan_loop: 3 |
| FINAL.G1-n1 | 10/10 | 0.0 | 35.0 | 10.7 | 188.3 | 216.6 | 8872.4 | 3 | unknown_action_token: 20, planner_output_not_parseable: 3, missing_post_pick_place: 2, invalid_corrective_block: 59, orphan_place: 7, pick_place_mismatch: 3, unobserved_object: 2, repeated_planner_output: 2 | - | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.K1-w1 | 10/10 | 0.0 | 1.2 | 11.0 | 191.9 | 213.5 | 10008.9 | 3 | invalid_corrective_block: 36, repeated_planner_output: 3, unknown_action_token: 22, pick_place_mismatch: 11, orphan_place: 4, planner_output_not_parseable: 3, missing_post_pick_place: 7 | - | replan_budget_exhausted: 10 |
| FINAL.K1-w2 | 10/10 | 0.0 | 1.1 | 11.0 | 90.4 | 110.2 | 2939.3 | 0 | unknown_action_token: 25, missing_post_pick_place: 8, pick_place_mismatch: 6, invalid_corrective_block: 42, repeated_planner_output: 6 | - | replan_budget_exhausted: 10 |

Planner call latency (s): mean 11.7283, p50 3.883, p90 7.175, max 401.89425230026245 over 1478 calls
Output tokens per call: mean 833.6077, p50 331, p90 534, max 24576; cut off at the limit: 19
