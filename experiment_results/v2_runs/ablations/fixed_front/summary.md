# ablations/fixed_front (qwen3-vl-8b-thinking, zero-shot)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 80% (8) | 83% | 6.2 | 648.6 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K2 | 10/10 | 90% (9) | 95% | 2.9 | 340.7 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3 | 10/10 | 100% (10) | 100% | 2.9 | 378.2 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 90% (9) | 95% | 4.1 | 522.8 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1 | 10/10 | 50% (5) | 90% | 6.2 | 896.6 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G2 | 10/10 | 10% (1) | 68% | 7.5 | 1245.1 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G3 | 10/10 | 0% (0) | 36% | 10.1 | 1476.1 | plan_completed: 2, replan_budget_exhausted: 8 |
