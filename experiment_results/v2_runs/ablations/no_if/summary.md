# ablations/no_if (qwen3-vl-8b-thinking, zero-shot)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 90% (9) | 96% | 5.4 | 561.3 | plan_completed: 10 |
| FINAL.K2 | 10/10 | 100% (10) | 100% | 10.5 | 688.9 | plan_completed: 1, replan_budget_exhausted: 8, replan_loop: 1 |
| FINAL.K3 | 10/10 | 80% (8) | 97% | 3.0 | 403.9 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100% (10) | 100% | 3.1 | 389.4 | plan_completed: 10 |
| FINAL.G1 | 10/10 | 40% (4) | 83% | 3.4 | 506.5 | plan_completed: 10 |
| FINAL.G2 | 10/10 | 10% (1) | 56% | 5.7 | 917.2 | plan_completed: 9, replan_loop: 1 |
| FINAL.G3 | 10/10 | 10% (1) | 56% | 6.7 | 922.7 | plan_completed: 8, replan_budget_exhausted: 2 |
