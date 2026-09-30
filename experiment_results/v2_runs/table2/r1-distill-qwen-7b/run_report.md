# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/r1-distill-qwen-7b

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 0.0 | 11.5 | 597.5 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0.0 | 0.0 | 9.7 | 778.7 | 784.7 | 60708.6 | 19 | unknown_action_token: 12, missing_post_pick_place: 2, planner_output_not_parseable: 23, orphan_place: 5, repeated_planner_output: 2, invalid_corrective_block: 8 | - | planner_returned_no_actions: 2, replan_budget_exhausted: 7, replan_loop: 1 |
| FINAL.G0 | 10/10 | 0.0 | 20.0 | 9.1 | 562.4 | 575.7 | 31003.1 | 7 | unknown_action_token: 26, orphan_place: 6, missing_post_pick_place: 18, invalid_corrective_block: 23, planner_output_not_parseable: 8, repeated_planner_output: 1 | - | replan_budget_exhausted: 8, planner_returned_no_actions: 2 |
| FINAL.K1 | 10/10 | 0.0 | 0.0 | 8.8 | 645.7 | 648.9 | 53427.2 | 15 | orphan_place: 9, pick_place_mismatch: 1, unknown_action_token: 6, planner_output_not_parseable: 18, missing_post_pick_place: 3 | - | replan_budget_exhausted: 6, planner_returned_no_actions: 4 |
| FINAL.K2 | 10/10 | 0.0 | 20.0 | 9.7 | 745.6 | 750.2 | 61387.9 | 20 | planner_output_not_parseable: 25, missing_post_pick_place: 7, repeated_planner_output: 1, unknown_action_token: 8, orphan_place: 7, invalid_corrective_block: 1, unobserved_object: 1 | - | replan_budget_exhausted: 8, planner_returned_no_actions: 2 |
| FINAL.K3 | 10/10 | 0.0 | 0.0 | 9.6 | 462.3 | 467.0 | 38342.2 | 9 | unknown_action_token: 21, planner_output_not_parseable: 18, orphan_place: 9, unobserved_object: 1, missing_post_pick_place: 5, pick_place_mismatch: 1 | - | planner_returned_no_actions: 4, replan_budget_exhausted: 6 |
| FINAL.K4 | 10/10 | 0.0 | 0.0 | 8.5 | 633.7 | 636.6 | 52269.5 | 16 | orphan_place: 9, planner_output_not_parseable: 21, unknown_action_token: 9, pick_place_mismatch: 2, missing_post_pick_place: 4 | - | planner_returned_no_actions: 4, replan_budget_exhausted: 6 |
| FINAL.G1 | 10/10 | 0.0 | 46.7 | 10.6 | 564.6 | 574.7 | 35342.6 | 7 | missing_post_pick_place: 23, unknown_action_token: 46, pick_place_mismatch: 4, orphan_place: 5, planner_output_not_parseable: 7, invalid_corrective_block: 14, repeated_planner_output: 1 | - | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.G2 | 10/10 | 0.0 | 25.0 | 10.1 | 517.7 | 521.9 | 38886.5 | 9 | missing_post_pick_place: 24, planner_output_not_parseable: 12, unknown_action_token: 38, orphan_place: 12, pick_place_mismatch: 2, invalid_corrective_block: 10 | - | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.G3 | 10/10 | 0.0 | 8.6 | 10.6 | 630.4 | 651.4 | 16558.1 | 2 | unknown_action_token: 20, missing_post_pick_place: 15, pick_place_mismatch: 2, planner_output_not_parseable: 4, invalid_corrective_block: 47, repeated_planner_output: 2, orphan_place: 6 | - | replan_budget_exhausted: 9, planner_returned_no_actions: 1 |
| FINAL.K3-n2 | 10/10 | 0.0 | 0.0 | 9.9 | 706.2 | 713.2 | 55220.0 | 16 | unknown_action_token: 8, planner_output_not_parseable: 22, orphan_place: 10, missing_post_pick_place: 6, repeated_planner_output: 1, invalid_corrective_block: 4 | - | replan_budget_exhausted: 8, planner_returned_no_actions: 2 |
| FINAL.K3-n3 | 10/10 | 0.0 | 0.0 | 9.6 | 589.7 | 595.1 | 49016.2 | 14 | unknown_action_token: 12, orphan_place: 11, planner_output_not_parseable: 16, missing_post_pick_place: 7, pick_place_mismatch: 1 | - | replan_budget_exhausted: 8, planner_returned_no_actions: 2 |
| FINAL.G1-n1 | 10/10 | 0.0 | 38.3 | 10.1 | 587.3 | 597.6 | 28663.3 | 6 | unknown_action_token: 21, missing_post_pick_place: 36, invalid_corrective_block: 23, repeated_planner_output: 1, planner_output_not_parseable: 5, orphan_place: 6, pick_place_mismatch: 3 | - | replan_budget_exhausted: 9, planner_returned_no_actions: 1 |
| FINAL.K1-w1 | 10/10 | 0.0 | 2.5 | 9.0 | 588.6 | 596.7 | 45955.6 | 13 | orphan_place: 7, pick_place_mismatch: 2, missing_post_pick_place: 9, planner_output_not_parseable: 15, unknown_action_token: 6, unobserved_object: 4, invalid_corrective_block: 1 | - | replan_budget_exhausted: 7, planner_returned_no_actions: 3 |
| FINAL.K1-w2 | 10/10 | 0.0 | 0.0 | 7.2 | 351.7 | 355.5 | 29113.4 | 6 | unobserved_object: 2, planner_output_not_parseable: 11, orphan_place: 11, unknown_action_token: 11, pick_place_mismatch: 1, missing_post_pick_place: 2, invalid_corrective_block: 1 | - | replan_budget_exhausted: 5, planner_returned_no_actions: 5 |

Planner call latency (s): mean 63.1296, p50 21.725, p90 297.022, max 313.63158082962036 over 1325 calls
Output tokens per call: mean 5003.3098, p50 1820, p90 24576, max 24576; cut off at the limit: 159
