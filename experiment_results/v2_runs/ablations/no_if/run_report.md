# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/ablations/no_if

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 92.5 | 20.0 | 61.4 | 84.0 | 546.8 | 70 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 90.0 | 95.7 | 5.4 | 477.0 | 561.3 | 21363.8 | 0 | insertion_too_late: 16, invalid_corrective_block: 5, orphan_place: 4, missing_post_pick_place: 1 | - | plan_completed: 10 |
| FINAL.K2 | 10/10 | 100.0 | 100.0 | 10.5 | 666.9 | 688.9 | 18125.0 | 0 | orphan_place: 7, unknown_action_token: 61, invalid_corrective_block: 16, repeated_planner_output: 4 | - | plan_completed: 1, replan_budget_exhausted: 8, replan_loop: 1 |
| FINAL.K3 | 10/10 | 80.0 | 97.1 | 3.0 | 307.4 | 403.9 | 20274.9 | 0 | orphan_place: 4, missing_post_pick_place: 1, insertion_too_late: 1 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100.0 | 100.0 | 3.1 | 314.2 | 389.4 | 21572.4 | 0 | orphan_place: 3, unknown_action_token: 1, missing_post_pick_place: 3 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 40.0 | 83.3 | 3.4 | 425.6 | 506.5 | 22206.3 | 0 | invalid_corrective_block: 5, orphan_place: 2, unknown_action_token: 1, pick_place_mismatch: 1 | - | plan_completed: 10 |
| FINAL.G2 | 10/10 | 10.0 | 56.2 | 5.7 | 819.7 | 917.2 | 40619.9 | 0 | invalid_corrective_block: 12, missing_post_pick_place: 1, orphan_place: 14, unknown_action_token: 1, repeated_planner_output: 2, pick_place_mismatch: 1 | - | plan_completed: 9, replan_loop: 1 |
| FINAL.G3 | 10/10 | 10.0 | 55.7 | 6.7 | 816.6 | 922.7 | 48139.0 | 0 | invalid_corrective_block: 9, orphan_place: 21, missing_post_pick_place: 1, unknown_action_token: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |

Planner call latency (s): mean 101.2529, p50 95.545, p90 165.402, max 266.8011620044708 over 378 calls
Output tokens per call: mean 7661.4064, p50 7616, p90 10994, max 16562; cut off at the limit: 0
