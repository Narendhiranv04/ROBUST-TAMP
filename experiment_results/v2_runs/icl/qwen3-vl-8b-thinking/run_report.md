# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/icl/qwen3-vl-8b-thinking

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| - | 82.0 | 82.0 | 94.4 | 398.8 | 50 |

| Variant | Trials | SR | PGC | Insertion errors (trials) | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.G0 | 10/10 | 90.0 | 93.3 | 0 | 1.2 | 120.7 | 200.5 | 7062.8 | 0 | invalid_corrective_block: 1 | - | plan_completed: 10 |
| FINAL.G1 | 10/10 | 80.0 | 95.7 | 1 | 3.1 | 387.4 | 474.1 | 18954.1 | 0 | invalid_corrective_block: 7, repeated_planner_output: 1, pick_place_mismatch: 2 | - | plan_completed: 10 |
| FINAL.G2 | 10/10 | 80.0 | 91.4 | 0 | 3.3 | 507.5 | 590.4 | 20811.6 | 0 | invalid_corrective_block: 11, repeated_planner_output: 2, missing_post_pick_place: 1 | - | plan_completed: 9, replan_loop: 1 |
| FINAL.G3 | 10/10 | 80.0 | 95.7 | 0 | 4.6 | 655.0 | 750.9 | 23350.8 | 0 | invalid_corrective_block: 21, repeated_planner_output: 1 | - | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 80.0 | 96.0 | 1 | 3.1 | 323.2 | 404.1 | 17089.9 | 0 | invalid_corrective_block: 6, pick_place_mismatch: 1, unknown_action_token: 1, unobserved_object: 2 | - | plan_completed: 10 |

Planner call latency (s): mean 130.3176, p50 118.838, p90 189.769, max 392.1600592136383 over 153 calls
Output tokens per call: mean 8156, p50 7557, p90 12091, max 18834; cut off at the limit: 0
