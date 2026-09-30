# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/table2/qwen3-8b-nothink

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 1.1 | 6.0 | 2.9 | 15.3 | 25.3 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0.0 | 0.0 | 8.3 | 24.4 | 32.5 | 2130.4 | 0 | unknown_action_token: 5, repeated_planner_output: 22, missing_post_pick_place: 22, orphan_place: 1 | - | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.G0 | 10/10 | 30.0 | 53.3 | 5.8 | 16.3 | 95.3 | 1170.1 | 0 | orphan_place: 17, invalid_corrective_block: 12, repeated_planner_output: 10, missing_post_pick_place: 2, remembered_object_inaccessible: 2 | - | replan_loop: 3, plan_completed: 5, replan_budget_exhausted: 2 |
| FINAL.K1 | 10/10 | 0.0 | 0.0 | 8.0 | 22.5 | 35.5 | 1841.4 | 0 | repeated_planner_output: 19, missing_post_pick_place: 14, unknown_action_token: 3, orphan_place: 1, invalid_corrective_block: 6, insertion_too_late: 3 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.K2 | 10/10 | 0.0 | 16.7 | 7.5 | 21.5 | 33.0 | 1758.9 | 0 | unknown_action_token: 7, invalid_corrective_block: 5, repeated_planner_output: 18, missing_post_pick_place: 14 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.K3 | 10/10 | 0.0 | 1.4 | 9.1 | 24.8 | 37.1 | 2014.4 | 0 | missing_post_pick_place: 21, repeated_planner_output: 20, unknown_action_token: 5, orphan_place: 2, insertion_too_late: 1, invalid_corrective_block: 6, planner_output_not_parseable: 1 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.K4 | 10/10 | 0.0 | 6.7 | 9.1 | 25.5 | 41.6 | 2049.7 | 0 | missing_post_pick_place: 21, repeated_planner_output: 21, orphan_place: 1, unknown_action_token: 7, invalid_corrective_block: 8 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.G1 | 10/10 | 0.0 | 52.2 | 8.3 | 56.1 | 99.4 | 1134.5 | 0 | invalid_corrective_block: 37, repeated_planner_output: 16, orphan_place: 15, pick_place_mismatch: 2, unknown_action_token: 1 | - | replan_loop: 8, plan_completed: 1, replan_budget_exhausted: 1 |
| FINAL.G2 | 10/10 | 0.0 | 27.5 | 8.2 | 24.3 | 49.9 | 1335.1 | 0 | unknown_action_token: 2, orphan_place: 16, repeated_planner_output: 17, invalid_corrective_block: 31, missing_post_pick_place: 6 | - | replan_loop: 8, replan_budget_exhausted: 2 |
| FINAL.G3 | 10/10 | 0.0 | 2.9 | 7.8 | 22.2 | 52.6 | 1191.5 | 0 | orphan_place: 18, repeated_planner_output: 20, invalid_corrective_block: 29, unknown_action_token: 1 | - | replan_loop: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n2 | 10/10 | 10.0 | 11.1 | 8.4 | 23.0 | 46.2 | 1892.4 | 0 | unknown_action_token: 4, missing_post_pick_place: 20, repeated_planner_output: 19, invalid_corrective_block: 5, orphan_place: 2 | - | replan_loop: 8, plan_completed: 1, replan_budget_exhausted: 1 |
| FINAL.K3-n3 | 10/10 | 0.0 | 0.9 | 8.1 | 22.7 | 35.2 | 1882.9 | 0 | orphan_place: 2, missing_post_pick_place: 22, repeated_planner_output: 19, unknown_action_token: 2, invalid_corrective_block: 3 | - | replan_loop: 9, replan_budget_exhausted: 1 |
| FINAL.G1-n1 | 10/10 | 0.0 | 38.3 | 6.8 | 19.7 | 54.0 | 1164.6 | 0 | orphan_place: 13, repeated_planner_output: 21, invalid_corrective_block: 22, missing_post_pick_place: 1, unobserved_object: 1 | - | replan_loop: 10 |
| FINAL.K1-w1 | 10/10 | 0.0 | 1.2 | 7.8 | 22.6 | 34.1 | 1956.7 | 0 | missing_post_pick_place: 22, repeated_planner_output: 21, invalid_corrective_block: 2 | - | replan_loop: 10 |
| FINAL.K1-w2 | 10/10 | 0.0 | 2.2 | 8.8 | 28.7 | 44.0 | 2297.4 | 0 | unknown_action_token: 6, missing_post_pick_place: 18, repeated_planner_output: 20, invalid_corrective_block: 7, orphan_place: 1, insertion_too_late: 2 | - | replan_loop: 8, replan_budget_exhausted: 2 |

Planner call latency (s): mean 3.1644, p50 2.847, p90 4.109, max 314.40249729156494 over 1120 calls
Output tokens per call: mean 255.0321, p50 255, p90 352, max 626; cut off at the limit: 0
