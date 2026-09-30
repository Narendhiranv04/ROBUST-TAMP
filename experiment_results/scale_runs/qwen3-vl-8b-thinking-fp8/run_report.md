# Run report: /home/user1/robust_tamp_infer/real_trials/scale/qwen3-vl-8b-thinking-fp8

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 88.9 | 14.0 | 62.1 | 82.7 | 517.7 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 100.0 | 100.0 | 1.9 | 174.0 | 221.8 | 13206.8 | 0 | orphan_place: 3, missing_post_pick_place: 1 | - | plan_completed: 10 |
| FINAL.G0 | 10/10 | 10.0 | 30.0 | 8.2 | 676.8 | 792.1 | 45276.0 | 0 | invalid_corrective_block: 8, orphan_place: 3, unknown_action_token: 1, repeated_planner_output: 1 | - | replan_budget_exhausted: 7, plan_completed: 3 |
| FINAL.K1 | 10/10 | 80.0 | 88.6 | 6.0 | 428.3 | 480.1 | 22298.0 | 0 | orphan_place: 7, insertion_too_late: 15, invalid_corrective_block: 8 | - | replan_budget_exhausted: 2, plan_completed: 8 |
| FINAL.K2 | 10/10 | 100.0 | 100.0 | 2.5 | 208.8 | 258.1 | 16048.8 | 0 | orphan_place: 7, missing_post_pick_place: 2 | - | plan_completed: 10 |
| FINAL.K3 | 10/10 | 100.0 | 100.0 | 4.2 | 357.9 | 418.8 | 23970.0 | 0 | orphan_place: 9, invalid_corrective_block: 2, missing_post_pick_place: 2, unknown_action_token: 1, insertion_too_late: 1 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100.0 | 100.0 | 4.4 | 379.0 | 427.0 | 28168.8 | 0 | orphan_place: 13, unknown_action_token: 2, missing_post_pick_place: 2, invalid_corrective_block: 1 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 20.0 | 83.3 | 6.2 | 641.2 | 715.7 | 41763.2 | 0 | invalid_corrective_block: 4, orphan_place: 11, unknown_action_token: 1, pick_place_mismatch: 1 | - | replan_budget_exhausted: 2, plan_completed: 8 |
| FINAL.G2 | 10/10 | 20.0 | 76.2 | 6.8 | 886.8 | 952.4 | 37181.5 | 0 | invalid_corrective_block: 24, orphan_place: 5, unknown_action_token: 3, repeated_planner_output: 2, missing_post_pick_place: 1 | - | plan_completed: 7, replan_budget_exhausted: 2, replan_loop: 1 |
| FINAL.G3 | 10/10 | 20.0 | 50.0 | 9.7 | 1030.4 | 1122.4 | 66005.2 | 0 | pick_place_mismatch: 1, invalid_corrective_block: 10, orphan_place: 21, repeated_planner_output: 1, unknown_action_token: 1, missing_post_pick_place: 1 | - | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K3-n2 | 10/10 | 80.0 | 88.9 | 3.5 | 329.2 | 396.9 | 24639.2 | 0 | orphan_place: 8, repeated_planner_output: 2, unknown_action_token: 1 | - | plan_completed: 9, replan_loop: 1 |
| FINAL.K3-n3 | 10/10 | 80.0 | 98.2 | 4.3 | 424.3 | 512.4 | 30691.8 | 0 | missing_post_pick_place: 3, orphan_place: 5, invalid_corrective_block: 2 | - | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 0.0 | 66.7 | 6.3 | 612.6 | 680.8 | 37849.6 | 0 | invalid_corrective_block: 9, unknown_action_token: 4, orphan_place: 2 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w1 | 10/10 | 80.0 | 83.8 | 6.6 | 547.0 | 607.4 | 33029.3 | 0 | missing_post_pick_place: 3, orphan_place: 12, repeated_planner_output: 4, insertion_too_late: 15, invalid_corrective_block: 3 | - | replan_loop: 1, plan_completed: 8, replan_budget_exhausted: 1 |
| FINAL.K1-w2 | 10/10 | 80.0 | 92.2 | 7.1 | 552.2 | 638.3 | 32848.9 | 0 | orphan_place: 15, insertion_too_late: 16, invalid_corrective_block: 6 | - | plan_completed: 9, replan_budget_exhausted: 1 |

Planner call latency (s): mean 93.2874, p50 90.293, p90 141.312, max 240.35112404823303 over 777 calls
Output tokens per call: mean 7099.9545, p50 7034, p90 10347, max 15358; cut off at the limit: 0
