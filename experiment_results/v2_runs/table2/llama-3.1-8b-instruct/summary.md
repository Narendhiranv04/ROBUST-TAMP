# llama-3.1-8b-instruct (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 10% (1) | 30% | 10.1 | 113.2 | plan_completed: 1, replan_budget_exhausted: 9 |
| FINAL.G0 | 10/10 | 0% (0) | 20% | 11.0 | 136.4 | replan_budget_exhausted: 10 |
| FINAL.K1 | 10/10 | 0% (0) | 1% | 11.0 | 144.6 | replan_budget_exhausted: 10 |
| FINAL.K2 | 10/10 | 50% (5) | 63% | 8.5 | 88.6 | plan_completed: 5, replan_budget_exhausted: 5 |
| FINAL.K3 | 10/10 | 0% (0) | 0% | 11.0 | 96.8 | replan_budget_exhausted: 10 |
| FINAL.K4 | 10/10 | 0% (0) | 10% | 11.0 | 203.7 | replan_budget_exhausted: 10 |
| FINAL.G1 | 10/10 | 0% (0) | 46% | 10.4 | 215.5 | replan_budget_exhausted: 6, replan_loop: 4 |
| FINAL.G2 | 10/10 | 0% (0) | 30% | 11.0 | 197.4 | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.G3 | 10/10 | 0% (0) | 1% | 11.0 | 259.9 | replan_budget_exhausted: 10 |
| FINAL.K3-n2 | 10/10 | 0% (0) | 0% | 9.5 | 55.7 | replan_budget_exhausted: 6, replan_loop: 4 |
| FINAL.K3-n3 | 10/10 | 0% (0) | 2% | 10.6 | 67.4 | replan_budget_exhausted: 7, replan_loop: 3 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 35% | 10.7 | 216.6 | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.K1-w1 | 10/10 | 0% (0) | 1% | 11.0 | 213.5 | replan_budget_exhausted: 10 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 1% | 11.0 | 110.2 | replan_budget_exhausted: 10 |
