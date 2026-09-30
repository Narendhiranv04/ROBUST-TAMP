# holo2-8b (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 50% (5) | 62% | 8.1 | 181.7 | plan_completed: 5, replan_budget_exhausted: 4, replan_loop: 1 |
| FINAL.G0 | 10/10 | 0% (0) | 30% | 7.9 | 168.3 | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K1 | 10/10 | 10% (1) | 20% | 9.9 | 159.5 | plan_completed: 1, replan_budget_exhausted: 6, replan_loop: 3 |
| FINAL.K2 | 10/10 | 20% (2) | 42% | 9.3 | 187.4 | plan_completed: 2, replan_budget_exhausted: 6, replan_loop: 2 |
| FINAL.K3 | 10/10 | 40% (4) | 53% | 10.1 | 193.3 | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K4 | 10/10 | 40% (4) | 55% | 9.6 | 239.9 | plan_completed: 5, replan_budget_exhausted: 3, replan_loop: 2 |
| FINAL.G1 | 10/10 | 0% (0) | 64% | 9.3 | 262.7 | plan_completed: 3, replan_budget_exhausted: 7 |
| FINAL.G2 | 10/10 | 0% (0) | 40% | 10.5 | 200.4 | plan_completed: 2, replan_budget_exhausted: 8 |
| FINAL.G3 | 10/10 | 0% (0) | 27% | 10.9 | 211.4 | plan_completed: 1, replan_budget_exhausted: 9 |
| FINAL.K3-n2 | 10/10 | 30% (3) | 42% | 10.1 | 215.3 | plan_completed: 3, replan_budget_exhausted: 7 |
| FINAL.K3-n3 | 10/10 | 40% (4) | 51% | 8.9 | 247.3 | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.G1-n1 | 10/10 | 10% (1) | 52% | 10.2 | 161.5 | plan_completed: 2, replan_budget_exhausted: 8 |
| FINAL.K1-w1 | 10/10 | 10% (1) | 12% | 10.8 | 147.8 | plan_completed: 1, replan_budget_exhausted: 9 |
| FINAL.K1-w2 | 10/10 | 40% (4) | 41% | 9.3 | 234.8 | plan_completed: 4, replan_budget_exhausted: 5, replan_loop: 1 |
