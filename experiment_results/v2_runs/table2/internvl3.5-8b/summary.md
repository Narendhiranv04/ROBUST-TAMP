# internvl3.5-8b (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 40% (4) | 54% | 8.6 | 102.1 | plan_completed: 4, replan_budget_exhausted: 4, replan_loop: 2 |
| FINAL.G0 | 10/10 | 0% (0) | 17% | 8.9 | 107.0 | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.K1 | 10/10 | 0% (0) | 9% | 9.7 | 73.3 | replan_budget_exhausted: 5, replan_loop: 5 |
| FINAL.K2 | 10/10 | 20% (2) | 43% | 9.5 | 158.5 | plan_completed: 2, replan_budget_exhausted: 4, replan_loop: 4 |
| FINAL.K3 | 10/10 | 10% (1) | 14% | 8.9 | 96.8 | plan_completed: 1, replan_budget_exhausted: 5, replan_loop: 4 |
| FINAL.K4 | 10/10 | 40% (4) | 47% | 9.3 | 115.5 | plan_completed: 4, replan_budget_exhausted: 3, replan_loop: 3 |
| FINAL.G1 | 10/10 | 0% (0) | 51% | 10.5 | 162.3 | replan_budget_exhausted: 9, replan_loop: 1 |
| FINAL.G2 | 10/10 | 0% (0) | 25% | 9.5 | 100.1 | replan_budget_exhausted: 5, replan_loop: 5 |
| FINAL.G3 | 10/10 | 0% (0) | 3% | 9.1 | 91.5 | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.K3-n2 | 10/10 | 20% (2) | 20% | 8.6 | 80.2 | plan_completed: 2, replan_budget_exhausted: 5, replan_loop: 3 |
| FINAL.K3-n3 | 10/10 | 10% (1) | 10% | 9.5 | 172.8 | plan_completed: 1, replan_budget_exhausted: 7, replan_loop: 2 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 27% | 9.6 | 104.7 | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.K1-w1 | 10/10 | 0% (0) | 8% | 10.2 | 153.4 | replan_budget_exhausted: 8, replan_loop: 2 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 7% | 9.3 | 79.5 | replan_budget_exhausted: 6, replan_loop: 4 |
