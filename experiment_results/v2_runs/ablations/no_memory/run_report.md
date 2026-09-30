# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/ablations/no_memory

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 80.0 | 23.3 | 55.7 | 84.0 | 554.8 | 70 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 70.0 | 95.7 | 6.7 | 541.8 | 623.5 | 24398.3 | 0 | missing_post_pick_place: 4, orphan_place: 3, invalid_corrective_block: 10, insertion_too_late: 16 | - | plan_completed: 10 |
| FINAL.K2 | 10/10 | 90.0 | 98.3 | 2.2 | 195.5 | 267.5 | 13395.3 | 0 | missing_post_pick_place: 2, orphan_place: 4 | - | plan_completed: 10 |
| FINAL.K3 | 10/10 | 80.0 | 97.1 | 3.9 | 316.8 | 403.1 | 20970.7 | 0 | orphan_place: 6, invalid_corrective_block: 1, missing_post_pick_place: 1, insertion_too_late: 1 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 80.0 | 96.7 | 3.2 | 313.3 | 384.6 | 21165.2 | 0 | invalid_corrective_block: 1, orphan_place: 3 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 20.0 | 76.7 | 5.5 | 646.9 | 752.8 | 32428.3 | 0 | unknown_action_token: 1, pick_place_mismatch: 1, invalid_corrective_block: 12, orphan_place: 2 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G2 | 10/10 | 30.0 | 76.2 | 6.9 | 810.0 | 897.9 | 38888.2 | 0 | invalid_corrective_block: 15, repeated_planner_output: 1, pick_place_mismatch: 1, unknown_action_token: 1 | - | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G3 | 10/10 | 20.0 | 47.1 | 8.3 | 1059.0 | 1160.3 | 59255.4 | 0 | invalid_corrective_block: 14, orphan_place: 14, repeated_planner_output: 5, unknown_action_token: 3, pick_place_mismatch: 1 | - | replan_loop: 2, replan_budget_exhausted: 4, plan_completed: 4 |

Planner call latency (s): mean 105.8128, p50 102.699, p90 162.951, max 258.42818546295166 over 367 calls
Output tokens per call: mean 7135.6407, p50 6970, p90 10646, max 16785; cut off at the limit: 0
