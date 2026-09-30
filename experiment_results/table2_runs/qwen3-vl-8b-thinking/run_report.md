# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/table2/qwen3-vl-8b-thinking

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 84.4 | 44.0 | 70.0 | 89.0 | 458.2 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 90.0 | 98.0 | 2.1 | 209.6 | 279.5 | 14460.3 | 0 | missing_post_pick_place: 2, orphan_place: 5 | - | plan_completed: 10 |
| FINAL.G0 | 10/10 | 50.0 | 80.0 | 3.2 | 287.2 | 383.6 | 18689.4 | 0 | invalid_corrective_block: 3, orphan_place: 3 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K1 | 10/10 | 100.0 | 100.0 | 3.9 | 343.2 | 423.8 | 17245.6 | 0 | missing_post_pick_place: 1, insertion_too_late: 13, invalid_corrective_block: 1, orphan_place: 2 | - | plan_completed: 10 |
| FINAL.K2 | 10/10 | 80.0 | 93.3 | 3.1 | 250.9 | 322.7 | 17460.3 | 0 | missing_post_pick_place: 1, orphan_place: 1 | - | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3 | 10/10 | 100.0 | 100.0 | 2.8 | 255.9 | 345.4 | 16108.9 | 0 | invalid_corrective_block: 1, missing_post_pick_place: 1, orphan_place: 3, insertion_too_late: 1 | - | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100.0 | 100.0 | 3.1 | 297.3 | 368.2 | 20443.4 | 0 | missing_post_pick_place: 3, orphan_place: 3, invalid_corrective_block: 1 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 30.0 | 80.0 | 5.9 | 673.2 | 775.0 | 39942.9 | 0 | orphan_place: 7, invalid_corrective_block: 6, unknown_action_token: 1, repeated_planner_output: 2 | - | plan_completed: 8, replan_budget_exhausted: 1, replan_loop: 1 |
| FINAL.G2 | 10/10 | 40.0 | 76.2 | 6.3 | 883.9 | 976.4 | 42985.6 | 0 | orphan_place: 7, invalid_corrective_block: 13, pick_place_mismatch: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G3 | 10/10 | 40.0 | 51.4 | 7.5 | 902.9 | 1008.6 | 56182.3 | 0 | pick_place_mismatch: 1, orphan_place: 13, invalid_corrective_block: 5, unknown_action_token: 1, repeated_planner_output: 1 | - | replan_budget_exhausted: 6, plan_completed: 4 |
| FINAL.K3-n2 | 10/10 | 80.0 | 91.1 | 4.2 | 347.7 | 450.5 | 23274.0 | 0 | missing_post_pick_place: 1, invalid_corrective_block: 2, orphan_place: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n3 | 10/10 | 60.0 | 95.5 | 3.5 | 394.6 | 534.0 | 22919.2 | 0 | missing_post_pick_place: 2, orphan_place: 2, insertion_too_late: 1, invalid_corrective_block: 3 | - | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 60.0 | 93.3 | 4.9 | 518.9 | 607.5 | 31539.5 | 1 | unknown_action_token: 1, invalid_corrective_block: 5, planner_output_not_parseable: 1, orphan_place: 2 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w1 | 10/10 | 80.0 | 92.5 | 5.4 | 458.6 | 569.9 | 25629.0 | 0 | invalid_corrective_block: 4, insertion_too_late: 11, orphan_place: 2, missing_post_pick_place: 1 | - | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w2 | 10/10 | 70.0 | 94.4 | 6.7 | 591.3 | 723.1 | 30788.1 | 0 | insertion_too_late: 10, invalid_corrective_block: 12, missing_post_pick_place: 2, repeated_planner_output: 1, orphan_place: 2 | - | plan_completed: 7, replan_budget_exhausted: 3 |

Planner call latency (s): mean 102.4791, p50 96.705, p90 157.883, max 371.17512488365173 over 626 calls
Output tokens per call: mean 7166.3852, p50 6898, p90 10879, max 24576; cut off at the limit: 1
