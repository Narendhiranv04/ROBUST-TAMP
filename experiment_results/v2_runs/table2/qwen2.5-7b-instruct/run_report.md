# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/qwen2.5-7b-instruct

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 0.0 | 9.0 | 7.1 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0.0 | 4.0 | 10.2 | 7.9 | 34.8 | 600.5 | 0 | missing_post_pick_place: 30, invalid_corrective_block: 12, pick_place_mismatch: 3, repeated_planner_output: 19, unknown_action_token: 1 | - | replan_budget_exhausted: 4, replan_loop: 5, plan_completed: 1 |
| FINAL.G0 | 10/10 | 0.0 | 0.0 | 8.9 | 5.0 | 6.7 | 492.0 | 0 | unknown_action_token: 40, orphan_place: 10, missing_post_pick_place: 17, repeated_planner_output: 21, planner_output_not_parseable: 1 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.K1 | 10/10 | 0.0 | 1.4 | 10.0 | 8.2 | 31.8 | 545.2 | 0 | missing_post_pick_place: 23, invalid_corrective_block: 18, pick_place_mismatch: 3, repeated_planner_output: 15, orphan_place: 1, unknown_action_token: 3 | - | replan_budget_exhausted: 5, replan_loop: 5 |
| FINAL.K2 | 10/10 | 0.0 | 18.3 | 9.4 | 7.4 | 27.1 | 476.3 | 0 | missing_post_pick_place: 30, invalid_corrective_block: 16, repeated_planner_output: 21, unknown_action_token: 1 | - | replan_loop: 7, replan_budget_exhausted: 3 |
| FINAL.K3 | 10/10 | 0.0 | 0.0 | 10.1 | 8.1 | 30.3 | 478.1 | 0 | missing_post_pick_place: 28, invalid_corrective_block: 22, repeated_planner_output: 18, orphan_place: 1, pick_place_mismatch: 1 | - | replan_loop: 5, replan_budget_exhausted: 5 |
| FINAL.K4 | 10/10 | 0.0 | 0.0 | 9.0 | 7.4 | 28.3 | 507.7 | 0 | missing_post_pick_place: 21, invalid_corrective_block: 17, repeated_planner_output: 17, pick_place_mismatch: 2, unknown_action_token: 3 | - | replan_loop: 6, replan_budget_exhausted: 4 |
| FINAL.G1 | 10/10 | 0.0 | 44.4 | 10.0 | 5.7 | 7.6 | 547.2 | 0 | unknown_action_token: 40, orphan_place: 10, missing_post_pick_place: 26, repeated_planner_output: 23, planner_output_not_parseable: 1 | - | replan_loop: 5, replan_budget_exhausted: 5 |
| FINAL.G2 | 10/10 | 0.0 | 25.0 | 10.5 | 6.0 | 8.0 | 573.1 | 0 | unknown_action_token: 43, orphan_place: 10, missing_post_pick_place: 28, repeated_planner_output: 22, planner_output_not_parseable: 2 | - | replan_budget_exhausted: 8, replan_loop: 2 |
| FINAL.G3 | 10/10 | 0.0 | 0.0 | 9.6 | 5.7 | 7.6 | 544.8 | 0 | unknown_action_token: 40, orphan_place: 11, repeated_planner_output: 20, missing_post_pick_place: 22, planner_output_not_parseable: 3 | - | replan_loop: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n2 | 10/10 | 0.0 | 0.0 | 10.0 | 7.7 | 28.5 | 557.1 | 0 | missing_post_pick_place: 33, repeated_planner_output: 20, invalid_corrective_block: 15 | - | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.K3-n3 | 10/10 | 0.0 | 0.0 | 9.1 | 7.0 | 31.4 | 545.5 | 0 | missing_post_pick_place: 27, invalid_corrective_block: 12, repeated_planner_output: 19, pick_place_mismatch: 1, unknown_action_token: 1 | - | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.G1-n1 | 10/10 | 0.0 | 33.3 | 9.3 | 5.4 | 7.2 | 524.4 | 0 | unknown_action_token: 42, orphan_place: 10, missing_post_pick_place: 18, repeated_planner_output: 21, planner_output_not_parseable: 2 | - | replan_loop: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w1 | 10/10 | 0.0 | 0.0 | 8.7 | 8.3 | 25.6 | 628.3 | 0 | missing_post_pick_place: 24, invalid_corrective_block: 13, repeated_planner_output: 22, unknown_action_token: 3 | - | replan_loop: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w2 | 10/10 | 0.0 | 0.0 | 9.1 | 9.3 | 33.6 | 606.0 | 0 | missing_post_pick_place: 20, invalid_corrective_block: 24, repeated_planner_output: 24 | - | replan_loop: 9, replan_budget_exhausted: 1 |

Planner call latency (s): mean 0.7402, p50 0.607, p90 1.528, max 3.020207166671753 over 1339 calls
Output tokens per call: mean 64.0857, p50 57, p90 84, max 300; cut off at the limit: 0
