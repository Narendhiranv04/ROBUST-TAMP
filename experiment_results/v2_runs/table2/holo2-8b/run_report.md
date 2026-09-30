# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/holo2-8b

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 31.1 | 2.0 | 20.7 | 42.2 | 135.5 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 50.0 | 62.0 | 8.1 | 119.9 | 181.7 | 6484.5 | 0 | invalid_corrective_block: 17, missing_post_pick_place: 14, orphan_place: 6, unknown_action_token: 1, repeated_planner_output: 2 | - | replan_budget_exhausted: 4, plan_completed: 5, replan_loop: 1 |
| FINAL.G0 | 10/10 | 0.0 | 30.0 | 7.9 | 90.0 | 168.3 | 3373.4 | 0 | invalid_corrective_block: 29, unknown_action_token: 11, orphan_place: 1, repeated_planner_output: 1, missing_post_pick_place: 4, pick_place_mismatch: 1 | - | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K1 | 10/10 | 10.0 | 20.0 | 9.9 | 120.3 | 159.5 | 7259.9 | 0 | missing_post_pick_place: 18, repeated_planner_output: 9, orphan_place: 1, invalid_corrective_block: 25, insertion_too_late: 3, unknown_action_token: 1, block_ends_holding: 1 | - | replan_budget_exhausted: 6, replan_loop: 3, plan_completed: 1 |
| FINAL.K2 | 10/10 | 20.0 | 41.7 | 9.3 | 151.0 | 187.4 | 9164.3 | 0 | orphan_place: 5, missing_post_pick_place: 24, repeated_planner_output: 9, invalid_corrective_block: 15, unknown_action_token: 1 | - | plan_completed: 2, replan_budget_exhausted: 6, replan_loop: 2 |
| FINAL.K3 | 10/10 | 40.0 | 52.9 | 10.1 | 121.4 | 193.3 | 7750.3 | 0 | unknown_action_token: 4, missing_post_pick_place: 17, orphan_place: 2, repeated_planner_output: 4, invalid_corrective_block: 18, insertion_too_late: 3 | - | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K4 | 10/10 | 40.0 | 55.0 | 9.6 | 169.7 | 239.9 | 11628.2 | 1 | missing_post_pick_place: 16, invalid_corrective_block: 15, orphan_place: 9, unknown_action_token: 3, repeated_planner_output: 4 | - | plan_completed: 5, replan_budget_exhausted: 3, replan_loop: 2 |
| FINAL.G1 | 10/10 | 0.0 | 64.4 | 9.3 | 185.1 | 262.7 | 3876.6 | 0 | unknown_action_token: 6, repeated_planner_output: 1, invalid_corrective_block: 47, orphan_place: 3, missing_post_pick_place: 2, pick_place_mismatch: 1 | - | plan_completed: 3, replan_budget_exhausted: 7 |
| FINAL.G2 | 10/10 | 0.0 | 40.0 | 10.5 | 128.0 | 200.4 | 5419.6 | 0 | orphan_place: 2, invalid_corrective_block: 55, unknown_action_token: 6, missing_post_pick_place: 4, repeated_planner_output: 3, pick_place_mismatch: 1 | - | replan_budget_exhausted: 8, plan_completed: 2 |
| FINAL.G3 | 10/10 | 0.0 | 27.1 | 10.9 | 144.3 | 211.4 | 4378.0 | 0 | invalid_corrective_block: 61, insertion_too_late: 4, missing_post_pick_place: 1, block_ends_holding: 1, orphan_place: 1 | - | replan_budget_exhausted: 9, plan_completed: 1 |
| FINAL.K3-n2 | 10/10 | 30.0 | 42.2 | 10.1 | 147.3 | 215.3 | 7948.8 | 0 | missing_post_pick_place: 17, invalid_corrective_block: 23, orphan_place: 3, unknown_action_token: 2, planner_output_not_parseable: 1, repeated_planner_output: 1, insertion_too_late: 2 | - | replan_budget_exhausted: 7, plan_completed: 3 |
| FINAL.K3-n3 | 10/10 | 40.0 | 50.9 | 8.9 | 157.5 | 247.3 | 9488.6 | 0 | missing_post_pick_place: 12, unknown_action_token: 2, invalid_corrective_block: 22, orphan_place: 3, repeated_planner_output: 1 | - | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.G1-n1 | 10/10 | 10.0 | 51.7 | 10.2 | 90.4 | 161.5 | 2863.3 | 0 | invalid_corrective_block: 58, missing_post_pick_place: 2, unknown_action_token: 2, block_ends_holding: 1 | - | replan_budget_exhausted: 8, plan_completed: 2 |
| FINAL.K1-w1 | 10/10 | 10.0 | 12.5 | 10.8 | 110.2 | 147.8 | 5272.8 | 0 | invalid_corrective_block: 35, insertion_too_late: 8, missing_post_pick_place: 17, orphan_place: 5, block_ends_holding: 1, repeated_planner_output: 1 | - | replan_budget_exhausted: 9, plan_completed: 1 |
| FINAL.K1-w2 | 10/10 | 40.0 | 41.1 | 9.3 | 161.7 | 234.8 | 8392.5 | 0 | missing_post_pick_place: 18, repeated_planner_output: 5, orphan_place: 6, invalid_corrective_block: 18, insertion_too_late: 4, unknown_action_token: 1, pick_place_mismatch: 1 | - | replan_budget_exhausted: 5, replan_loop: 1, plan_completed: 4 |

Planner call latency (s): mean 14.061, p50 6.793, p90 34.834, max 377.7925546169281 over 1349 calls
Output tokens per call: mean 1082.3759, p50 602, p90 2594, max 24576; cut off at the limit: 1
