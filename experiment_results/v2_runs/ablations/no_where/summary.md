# ablations/no_where (qwen3-vl-8b-thinking, zero-shot)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 0% (0) | 73% | 6.0 | 591.3 | plan_completed: 10 |
| FINAL.K2 | 10/10 | 90% (9) | 95% | 3.2 | 363.9 | plan_completed: 9, replan_loop: 1 |
| FINAL.K3 | 10/10 | 80% (8) | 97% | 3.0 | 367.8 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100% (10) | 100% | 3.3 | 414.4 | plan_completed: 10 |
| FINAL.G1 | 10/10 | 40% (4) | 77% | 4.2 | 564.0 | plan_completed: 10 |
| FINAL.G2 | 10/10 | 10% (1) | 65% | 5.9 | 904.8 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G3 | 10/10 | 60% (6) | 77% | 4.8 | 642.8 | plan_completed: 8, replan_budget_exhausted: 2 |
