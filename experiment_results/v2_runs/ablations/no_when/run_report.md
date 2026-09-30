# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/ablations/no_when

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 92.5 | 16.7 | 60.0 | 80.5 | 633.6 | 70 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 70.0 | 77.1 | 6.7 | 569.1 | 644.7 | 27364.5 | 0 | orphan_place: 6, insertion_too_late: 17, invalid_corrective_block: 8, missing_post_pick_place: 3 | - | replan_budget_exhausted: 3, plan_completed: 7 |
| FINAL.K2 | 10/10 | 100.0 | 100.0 | 3.1 | 291.2 | 365.8 | 18497.2 | 0 | orphan_place: 5, repeated_planner_output: 1, missing_post_pick_place: 1, invalid_corrective_block: 2 | - | plan_completed: 10 |
| FINAL.K3 | 10/10 | 100.0 | 100.0 | 4.4 | 389.7 | 483.5 | 25250.5 | 0 | orphan_place: 10, missing_post_pick_place: 3, invalid_corrective_block: 3 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100.0 | 100.0 | 3.7 | 346.2 | 439.8 | 23207.8 | 0 | missing_post_pick_place: 3, orphan_place: 7, invalid_corrective_block: 2 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 20.0 | 78.9 | 5.7 | 656.4 | 753.9 | 31954.5 | 1 | invalid_corrective_block: 16, orphan_place: 3, repeated_planner_output: 1, pick_place_mismatch: 1, planner_output_not_parseable: 1 | - | replan_budget_exhausted: 3, plan_completed: 7 |
| FINAL.G2 | 10/10 | 10.0 | 58.8 | 7.2 | 1005.1 | 1130.8 | 46501.6 | 0 | invalid_corrective_block: 21, orphan_place: 4, missing_post_pick_place: 1 | - | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G3 | 10/10 | 20.0 | 48.6 | 8.9 | 1177.9 | 1291.0 | 56438.9 | 0 | pick_place_mismatch: 1, invalid_corrective_block: 25, repeated_planner_output: 2, orphan_place: 1, unknown_action_token: 1, remembered_object_inaccessible: 2, insertion_too_late: 1 | - | replan_budget_exhausted: 6, plan_completed: 4 |

Planner call latency (s): mean 111.7252, p50 103.995, p90 173.17, max 347.37832593917847 over 397 calls
Output tokens per call: mean 7640.5, p50 7213, p90 11663, max 24576; cut off at the limit: 1
