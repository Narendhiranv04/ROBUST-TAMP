# Run report: /home/projects/long-horizon/robust_tamp_infer/real_trials/v2/table2/r1-distill-llama-8b

Complete: **True**

| SR_K | SR_G | SR | PGC | Plan. (s) | trials |
|---|---|---|---|---|---|
| 0.0 | 0.0 | 0.0 | 8.5 | 500.5 | 140 |

| Variant | Trials | SR | PGC | Calls | Planner s | Trial s | Tokens/trial | Cut off | Rejections | INH | Terminations |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0.0 | 0.0 | 11.0 | 719.0 | 720.5 | 49880.5 | 10 | planner_output_not_parseable: 106, repeated_planner_output: 4 | - | replan_budget_exhausted: 10 |
| FINAL.G0 | 10/10 | 0.0 | 0.0 | 11.0 | 297.5 | 299.1 | 21073.2 | 0 | planner_output_not_parseable: 109, repeated_planner_output: 1 | - | replan_budget_exhausted: 10 |
| FINAL.K1 | 10/10 | 0.0 | 0.0 | 10.8 | 687.9 | 689.3 | 47242.9 | 10 | planner_output_not_parseable: 106, repeated_planner_output: 2 | - | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.K2 | 10/10 | 0.0 | 16.7 | 11.0 | 637.7 | 639.2 | 44718.0 | 7 | planner_output_not_parseable: 110 | - | replan_budget_exhausted: 10 |
| FINAL.K3 | 10/10 | 0.0 | 0.0 | 11.0 | 554.4 | 555.8 | 38738.5 | 5 | planner_output_not_parseable: 110 | - | replan_budget_exhausted: 10 |
| FINAL.K4 | 10/10 | 0.0 | 0.0 | 11.0 | 603.7 | 605.2 | 42358.2 | 6 | planner_output_not_parseable: 110 | - | replan_budget_exhausted: 10 |
| FINAL.G1 | 10/10 | 0.0 | 44.4 | 11.0 | 325.2 | 326.9 | 22871.7 | 0 | planner_output_not_parseable: 108, repeated_planner_output: 2 | - | replan_budget_exhausted: 10 |
| FINAL.G2 | 10/10 | 0.0 | 25.0 | 11.0 | 317.3 | 319.0 | 22686.1 | 1 | planner_output_not_parseable: 110 | - | replan_budget_exhausted: 10 |
| FINAL.G3 | 10/10 | 0.0 | 0.0 | 11.0 | 290.5 | 292.2 | 21581.4 | 0 | planner_output_not_parseable: 110 | - | replan_budget_exhausted: 10 |
| FINAL.K3-n2 | 10/10 | 0.0 | 0.0 | 11.0 | 629.9 | 631.3 | 45638.4 | 8 | planner_output_not_parseable: 109, repeated_planner_output: 1 | - | replan_budget_exhausted: 10 |
| FINAL.K3-n3 | 10/10 | 0.0 | 0.0 | 11.0 | 587.1 | 588.5 | 42336.7 | 6 | planner_output_not_parseable: 108, repeated_planner_output: 2 | - | replan_budget_exhausted: 10 |
| FINAL.G1-n1 | 10/10 | 0.0 | 33.3 | 11.0 | 269.6 | 271.2 | 20249.9 | 0 | planner_output_not_parseable: 110 | - | replan_budget_exhausted: 10 |
| FINAL.K1-w1 | 10/10 | 0.0 | 0.0 | 11.0 | 569.2 | 570.7 | 39915.9 | 7 | planner_output_not_parseable: 108, repeated_planner_output: 2 | - | replan_budget_exhausted: 10 |
| FINAL.K1-w2 | 10/10 | 0.0 | 0.0 | 11.0 | 517.7 | 519.2 | 36651.9 | 4 | planner_output_not_parseable: 108, repeated_planner_output: 2 | - | replan_budget_exhausted: 10 |

Planner call latency (s): mean 45.5571, p50 28.742, p90 63.665, max 398.86154341697693 over 1538 calls
Output tokens per call: mean 3224.5988, p50 2077, p90 4593, max 24576; cut off at the limit: 64
