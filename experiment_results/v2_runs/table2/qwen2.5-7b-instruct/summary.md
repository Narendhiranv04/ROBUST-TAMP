# qwen2.5-7b-instruct (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0% (0) | 4% | 10.2 | 34.8 | plan_completed: 1, replan_budget_exhausted: 4, replan_loop: 5 |
| FINAL.G0 | 10/10 | 0% (0) | 0% | 8.9 | 6.7 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K1 | 10/10 | 0% (0) | 1% | 10.0 | 31.8 | replan_budget_exhausted: 5, replan_loop: 5 |
| FINAL.K2 | 10/10 | 0% (0) | 18% | 9.4 | 27.1 | replan_budget_exhausted: 3, replan_loop: 7 |
| FINAL.K3 | 10/10 | 0% (0) | 0% | 10.1 | 30.3 | replan_budget_exhausted: 5, replan_loop: 5 |
| FINAL.K4 | 10/10 | 0% (0) | 0% | 9.0 | 28.3 | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.G1 | 10/10 | 0% (0) | 44% | 10.0 | 7.6 | replan_budget_exhausted: 5, replan_loop: 5 |
| FINAL.G2 | 10/10 | 0% (0) | 25% | 10.5 | 8.0 | replan_budget_exhausted: 8, replan_loop: 2 |
| FINAL.G3 | 10/10 | 0% (0) | 0% | 9.6 | 7.6 | replan_budget_exhausted: 2, replan_loop: 8 |
| FINAL.K3-n2 | 10/10 | 0% (0) | 0% | 10.0 | 28.5 | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.K3-n3 | 10/10 | 0% (0) | 0% | 9.1 | 31.4 | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 33% | 9.3 | 7.2 | replan_budget_exhausted: 2, replan_loop: 8 |
| FINAL.K1-w1 | 10/10 | 0% (0) | 0% | 8.7 | 25.6 | replan_budget_exhausted: 2, replan_loop: 8 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 0% | 9.1 | 33.6 | replan_budget_exhausted: 1, replan_loop: 9 |
