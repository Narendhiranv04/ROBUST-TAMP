# qwen3-vl-8b-instruct (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0% (0) | 0% | 7.0 | 38.1 | replan_loop: 10 |
| FINAL.G0 | 10/10 | 10% (1) | 30% | 9.5 | 291.5 | plan_completed: 2, replan_budget_exhausted: 8 |
| FINAL.K1 | 10/10 | 0% (0) | 0% | 8.1 | 44.1 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K2 | 10/10 | 10% (1) | 25% | 8.5 | 70.2 | plan_completed: 1, replan_loop: 9 |
| FINAL.K3 | 10/10 | 0% (0) | 0% | 8.0 | 148.7 | replan_budget_exhausted: 2, replan_loop: 8 |
| FINAL.K4 | 10/10 | 0% (0) | 0% | 7.5 | 100.5 | replan_loop: 10 |
| FINAL.G1 | 10/10 | 0% (0) | 43% | 10.6 | 271.0 | plan_completed: 1, replan_budget_exhausted: 8, replan_loop: 1 |
| FINAL.G2 | 10/10 | 0% (0) | 30% | 11.0 | 654.8 | replan_budget_exhausted: 10 |
| FINAL.G3 | 10/10 | 0% (0) | 10% | 10.7 | 653.9 | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.K3-n2 | 10/10 | 0% (0) | 1% | 7.6 | 37.8 | replan_loop: 10 |
| FINAL.K3-n3 | 10/10 | 0% (0) | 0% | 7.5 | 44.1 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 38% | 10.8 | 300.3 | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.K1-w1 | 10/10 | 0% (0) | 0% | 7.9 | 36.2 | replan_loop: 10 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 0% | 7.9 | 39.0 | replan_budget_exhausted: 2, replan_loop: 8 |
