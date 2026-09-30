# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/ablations/fixed_end

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 50.0 | 13.3 | 34.3 | 54.2 | 753.8 | 70 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 0.0 | 0.0 | 11.0 | 897.9 | 916.5 | 14171.2 | 0 | insertion_too_late: 78, repeated_planner_output: 2, invalid_corrective_block: 10, orphan_place: 4 | - | replan_budget_exhausted: 10 |
| FINAL.K2 | 10/10 | 100.0 | 100.0 | 2.2 | 243.6 | 315.4 | 16527.8 | 0 | orphan_place: 5 | - | plan_completed: 10 |
| FINAL.K3 | 10/10 | 0.0 | 8.6 | 10.2 | 818.6 | 849.5 | 20621.9 | 0 | missing_post_pick_place: 4, orphan_place: 6, insertion_too_late: 71, invalid_corrective_block: 2, repeated_planner_output: 1 | - | replan_budget_exhausted: 9, plan_completed: 1 |
| FINAL.K4 | 10/10 | 100.0 | 100.0 | 2.8 | 288.8 | 356.4 | 19852.5 | 0 | missing_post_pick_place: 2, orphan_place: 2 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 10.0 | 57.8 | 6.0 | 760.7 | 863.4 | 42614.4 | 0 | invalid_corrective_block: 8, orphan_place: 10, pick_place_mismatch: 3, missing_post_pick_place: 1 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G2 | 10/10 | 0.0 | 48.8 | 8.6 | 1211.2 | 1330.9 | 60340.5 | 0 | orphan_place: 16, unknown_action_token: 2, invalid_corrective_block: 14, insertion_too_late: 1 | - | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G3 | 10/10 | 30.0 | 64.3 | 8.5 | 1055.9 | 1139.6 | 45628.7 | 0 | unknown_action_token: 3, invalid_corrective_block: 16, insertion_too_late: 11, missing_post_pick_place: 2, orphan_place: 15 | - | replan_budget_exhausted: 6, plan_completed: 4 |

Planner call latency (s): mean 107.0351, p50 103.9, p90 166.469, max 258.8011600971222 over 493 calls
Output tokens per call: mean 7991.1636, p50 7831, p90 11456, max 16794; cut off at the limit: 0
