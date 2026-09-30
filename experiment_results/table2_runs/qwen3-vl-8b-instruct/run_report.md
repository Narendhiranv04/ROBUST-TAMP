# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/table2/qwen3-vl-8b-instruct

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 1.1 | 2.0 | 1.4 | 12.7 | 167.7 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0.0 | 0.0 | 7.0 | 30.8 | 38.1 | 1325.3 | 0 | missing_post_pick_place: 15, repeated_planner_output: 24 | - | replan_loop: 10 |
| FINAL.G0 | 10/10 | 10.0 | 30.0 | 9.5 | 192.4 | 291.5 | 7647.3 | 2 | planner_output_not_parseable: 2, unknown_action_token: 10, pick_place_mismatch: 2, invalid_corrective_block: 42, missing_post_pick_place: 1, orphan_place: 6, repeated_planner_output: 2 | - | plan_completed: 2, replan_budget_exhausted: 8 |
| FINAL.K1 | 10/10 | 0.0 | 0.0 | 8.1 | 34.7 | 44.1 | 1301.8 | 0 | missing_post_pick_place: 19, repeated_planner_output: 27, insertion_too_late: 1, invalid_corrective_block: 2 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.K2 | 10/10 | 10.0 | 25.0 | 8.5 | 55.1 | 70.2 | 1760.0 | 0 | missing_post_pick_place: 22, repeated_planner_output: 24, orphan_place: 1 | - | replan_loop: 9, plan_completed: 1 |
| FINAL.K3 | 10/10 | 0.0 | 0.0 | 8.0 | 137.7 | 148.7 | 4137.4 | 1 | missing_post_pick_place: 15, repeated_planner_output: 20, planner_output_not_parseable: 1, invalid_corrective_block: 8, insertion_too_late: 1, orphan_place: 3 | - | replan_loop: 8, replan_budget_exhausted: 2 |
| FINAL.K4 | 10/10 | 0.0 | 0.0 | 7.5 | 92.4 | 100.5 | 3684.5 | 1 | missing_post_pick_place: 17, repeated_planner_output: 26, planner_output_not_parseable: 1 | - | replan_loop: 10 |
| FINAL.G1 | 10/10 | 0.0 | 43.3 | 10.6 | 221.1 | 271.0 | 3348.6 | 0 | unknown_action_token: 5, invalid_corrective_block: 60, orphan_place: 7, repeated_planner_output: 5, pick_place_mismatch: 2 | - | replan_budget_exhausted: 8, replan_loop: 1, plan_completed: 1 |
| FINAL.G2 | 10/10 | 0.0 | 30.0 | 11.0 | 605.6 | 654.8 | 9420.0 | 3 | unknown_action_token: 8, invalid_corrective_block: 60, orphan_place: 3, planner_output_not_parseable: 3, repeated_planner_output: 2, insertion_too_late: 2, pick_place_mismatch: 1, remembered_object_inaccessible: 3 | - | replan_budget_exhausted: 10 |
| FINAL.G3 | 10/10 | 0.0 | 10.0 | 10.7 | 608.3 | 653.9 | 3742.4 | 1 | invalid_corrective_block: 71, planner_output_not_parseable: 1, unknown_action_token: 5, repeated_planner_output: 6, orphan_place: 1 | - | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.K3-n2 | 10/10 | 0.0 | 1.1 | 7.6 | 26.8 | 37.8 | 1359.0 | 0 | missing_post_pick_place: 18, repeated_planner_output: 25, orphan_place: 1 | - | replan_loop: 10 |
| FINAL.K3-n3 | 10/10 | 0.0 | 0.0 | 7.5 | 35.2 | 44.1 | 1200.5 | 0 | missing_post_pick_place: 17, repeated_planner_output: 26 | - | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.G1-n1 | 10/10 | 0.0 | 38.3 | 10.8 | 249.8 | 300.3 | 8545.9 | 3 | invalid_corrective_block: 58, orphan_place: 3, planner_output_not_parseable: 3, unknown_action_token: 13, repeated_planner_output: 7 | - | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.K1-w1 | 10/10 | 0.0 | 0.0 | 7.9 | 27.7 | 36.2 | 1370.4 | 0 | missing_post_pick_place: 20, repeated_planner_output: 29 | - | replan_loop: 10 |
| FINAL.K1-w2 | 10/10 | 0.0 | 0.0 | 7.9 | 30.0 | 39.0 | 1480.9 | 0 | missing_post_pick_place: 21, repeated_planner_output: 21, orphan_place: 1, unknown_action_token: 1 | - | replan_loop: 8, replan_budget_exhausted: 2 |

Planner call latency (s): mean 19.147, p50 3.793, p90 12.431, max 708.302407503128 over 1226 calls
Output tokens per call: mean 563.5386, p50 179, p90 455, max 24576; cut off at the limit: 11
