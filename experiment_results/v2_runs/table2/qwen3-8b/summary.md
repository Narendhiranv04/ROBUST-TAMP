# qwen3-8b (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 80% (8) | 80% | 3.5 | 218.3 | plan_completed: 8, replan_loop: 2 |
| FINAL.G0 | 10/10 | 10% (1) | 57% | 8.2 | 434.4 | plan_completed: 5, replan_budget_exhausted: 5 |
| FINAL.K1 | 10/10 | 80% (8) | 81% | 6.5 | 337.5 | plan_completed: 8, replan_budget_exhausted: 1, replan_loop: 1 |
| FINAL.K2 | 10/10 | 90% (9) | 95% | 3.6 | 215.2 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3 | 10/10 | 90% (9) | 90% | 6.0 | 336.3 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K4 | 10/10 | 90% (9) | 90% | 4.9 | 253.2 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1 | 10/10 | 0% (0) | 56% | 10.1 | 554.1 | plan_completed: 1, replan_budget_exhausted: 7, replan_loop: 2 |
| FINAL.G2 | 10/10 | 10% (1) | 52% | 10.5 | 698.2 | plan_completed: 1, replan_budget_exhausted: 9 |
| FINAL.G3 | 10/10 | 0% (0) | 13% | 10.1 | 539.7 | replan_budget_exhausted: 7, replan_loop: 3 |
| FINAL.K3-n2 | 10/10 | 80% (8) | 89% | 6.2 | 332.2 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n3 | 10/10 | 80% (8) | 95% | 6.3 | 396.2 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 52% | 10.4 | 563.3 | plan_completed: 1, replan_budget_exhausted: 7, replan_loop: 2 |
| FINAL.K1-w1 | 10/10 | 60% (6) | 64% | 10.0 | 426.0 | plan_completed: 6, replan_budget_exhausted: 3, replan_loop: 1 |
| FINAL.K1-w2 | 10/10 | 60% (6) | 70% | 8.3 | 411.1 | plan_completed: 6, replan_budget_exhausted: 4 |
