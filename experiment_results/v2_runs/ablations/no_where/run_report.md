# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/ablations/no_where

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 67.5 | 36.7 | 54.3 | 83.4 | 447.8 | 70 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 0.0 | 72.9 | 6.0 | 513.2 | 591.3 | 36347.3 | 0 | orphan_place: 12, repeated_planner_output: 1 | - | plan_completed: 10 |
| FINAL.K2 | 10/10 | 90.0 | 95.0 | 3.2 | 290.2 | 363.9 | 20434.3 | 0 | orphan_place: 7, repeated_planner_output: 2, missing_post_pick_place: 2 | - | plan_completed: 9, replan_loop: 1 |
| FINAL.K3 | 10/10 | 80.0 | 97.1 | 3.0 | 271.3 | 367.8 | 19123.9 | 0 | missing_post_pick_place: 4, orphan_place: 2 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100.0 | 100.0 | 3.3 | 319.1 | 414.4 | 22800.0 | 0 | orphan_place: 4, missing_post_pick_place: 2 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 40.0 | 76.7 | 4.2 | 439.9 | 564.0 | 31178.6 | 0 | orphan_place: 5, repeated_planner_output: 1 | - | plan_completed: 10 |
| FINAL.G2 | 10/10 | 10.0 | 65.0 | 5.9 | 775.2 | 904.8 | 55640.1 | 0 | orphan_place: 11, unknown_action_token: 9, pick_place_mismatch: 1 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G3 | 10/10 | 60.0 | 77.1 | 4.8 | 525.4 | 642.8 | 37749.6 | 0 | orphan_place: 9, repeated_planner_output: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |

Planner call latency (s): mean 103.1031, p50 102.604, p90 147.124, max 219.0010106563568 over 304 calls
Output tokens per call: mean 7344.5329, p50 7300, p90 10384, max 15231; cut off at the limit: 0
