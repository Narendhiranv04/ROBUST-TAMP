# qwen3-8b-nothink (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0% (0) | 0% | 8.3 | 32.5 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.G0 | 10/10 | 30% (3) | 53% | 5.8 | 95.3 | plan_completed: 5, replan_budget_exhausted: 2, replan_loop: 3 |
| FINAL.K1 | 10/10 | 0% (0) | 0% | 8.0 | 35.5 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K2 | 10/10 | 0% (0) | 17% | 7.5 | 33.0 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K3 | 10/10 | 0% (0) | 1% | 9.1 | 37.1 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K4 | 10/10 | 0% (0) | 7% | 9.1 | 41.6 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.G1 | 10/10 | 0% (0) | 52% | 8.3 | 99.4 | plan_completed: 1, replan_budget_exhausted: 1, replan_loop: 8 |
| FINAL.G2 | 10/10 | 0% (0) | 28% | 8.2 | 49.9 | replan_budget_exhausted: 2, replan_loop: 8 |
| FINAL.G3 | 10/10 | 0% (0) | 3% | 7.8 | 52.6 | replan_budget_exhausted: 2, replan_loop: 8 |
| FINAL.K3-n2 | 10/10 | 10% (1) | 11% | 8.4 | 46.2 | plan_completed: 1, replan_budget_exhausted: 1, replan_loop: 8 |
| FINAL.K3-n3 | 10/10 | 0% (0) | 1% | 8.1 | 35.2 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 38% | 6.8 | 54.0 | replan_loop: 10 |
| FINAL.K1-w1 | 10/10 | 0% (0) | 1% | 7.8 | 34.1 | replan_loop: 10 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 2% | 8.8 | 44.0 | replan_budget_exhausted: 2, replan_loop: 8 |
