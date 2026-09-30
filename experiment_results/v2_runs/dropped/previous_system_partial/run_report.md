# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/ablations/previous_system

Complete: **False** - FINAL.K0 seed 3: no trial_end; FINAL.K0 seed 4: no trial_end; FINAL.K0 seed 5: no trial_end; FINAL.K0 seed 6: no trial_end; FINAL.K0 seed 7: no trial_end; FINAL.K0 seed 8: no trial_end; FINAL.K0 seed 9: no trial_end; FINAL.G0 seed 3: no trial_end; FINAL.G0 seed 4: no trial_end; FINAL.G0 seed 5: no trial_end; FINAL.G0 seed 6: no trial_end; FINAL.G0 seed 7: no trial_end; FINAL.G0 seed 8: no trial_end; FINAL.G0 seed 9: no trial_end; FINAL.K1 seed 2: no trial_end; FINAL.K1 seed 3: no trial_end; FINAL.K1 seed 4: no trial_end; FINAL.K1 seed 5: no trial_end; FINAL.K1 seed 6: no trial_end; FINAL.K1 seed 7: no trial_end

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 22.2 | 18.2 | 20.7 | 76.1 | 328.5 | 29 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 3/3 | 33.3 | 86.7 | 3.3 | 298.2 | 365.6 | 21401.7 | 0 | orphan_place: 3 | - | plan_completed: 3 |
| FINAL.G0 | 3/3 | 66.7 | 88.9 | 1.0 | 119.2 | 182.6 | 8612.7 | 0 | - | - | plan_completed: 3 |
| FINAL.K1 | 2/2 | 0.0 | 71.4 | 3.5 | 288.7 | 362.7 | 20575.0 | 0 | orphan_place: 1 | - | plan_completed: 2 |
| FINAL.K2 | 2/2 | 50.0 | 91.7 | 4.0 | 283.8 | 348.4 | 20302.5 | 0 | orphan_place: 1 | - | plan_completed: 2 |
| FINAL.K3 | 2/2 | 0.0 | 85.7 | 2.5 | 209.3 | 292.9 | 14805.5 | 0 | - | - | plan_completed: 2 |
| FINAL.K4 | 2/2 | 50.0 | 91.7 | 3.0 | 274.3 | 356.4 | 19607.5 | 0 | - | - | plan_completed: 2 |
| FINAL.G1 | 2/2 | 0.0 | 61.1 | 3.5 | 399.5 | 498.5 | 28447.5 | 0 | orphan_place: 1 | - | plan_completed: 2 |
| FINAL.G2 | 2/2 | 0.0 | 62.5 | 2.5 | 324.2 | 412.1 | 23112.0 | 0 | unknown_action_token: 1 | - | plan_completed: 2 |
| FINAL.G3 | 2/2 | 0.0 | 42.9 | 6.5 | 738.3 | 841.1 | 52723.5 | 0 | orphan_place: 7 | - | replan_budget_exhausted: 1, plan_completed: 1 |
| FINAL.K3-n2 | 2/2 | 0.0 | 72.2 | 3.5 | 368.4 | 470.0 | 26051.5 | 0 | orphan_place: 1 | - | plan_completed: 2 |
| FINAL.K3-n3 | 1/1 | 100.0 | 100.0 | 8.0 | 689.3 | 823.5 | 48620.0 | 0 | missing_post_pick_place: 1, orphan_place: 1 | - | plan_completed: 1 |
| FINAL.G1-n1 | 2/2 | 0.0 | 58.3 | 3.0 | 428.1 | 505.7 | 30344.5 | 0 | pick_place_mismatch: 2 | - | plan_completed: 2 |
| FINAL.K1-w1 | 2/2 | 0.0 | 75.0 | 3.0 | 254.2 | 350.7 | 18232.0 | 0 | orphan_place: 1 | - | plan_completed: 2 |
| FINAL.K1-w2 | 2/2 | 0.0 | 77.8 | 2.5 | 223.3 | 343.5 | 15847.5 | 0 | - | - | plan_completed: 2 |

Planner call latency (s): mean 99.2246, p50 95.456, p90 145.6, max 195.72587966918945 over 96 calls
Output tokens per call: mean 7070.4271, p50 6763, p90 10236, max 13889; cut off at the limit: 0
