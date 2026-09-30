# qwen3-8b (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 70% (7) | 84% | 4.1 | 206.9 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G0 | 10/10 | 0% (0) | 37% | 8.5 | 461.5 | plan_completed: 3, replan_budget_exhausted: 7 |
| FINAL.K1 | 10/10 | 40% (4) | 43% | 7.9 | 341.3 | plan_completed: 4, replan_budget_exhausted: 4, replan_loop: 2 |
| FINAL.K2 | 10/10 | 70% (7) | 87% | 5.1 | 264.5 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3 | 10/10 | 100% (10) | 100% | 4.7 | 256.8 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 60% (6) | 73% | 7.7 | 319.2 | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G1 | 10/10 | 0% (0) | 60% | 10.0 | 501.1 | plan_completed: 1, replan_budget_exhausted: 7, replan_loop: 2 |
| FINAL.G2 | 10/10 | 0% (0) | 61% | 10.3 | 604.6 | plan_completed: 1, replan_budget_exhausted: 8, replan_loop: 1 |
| FINAL.G3 | 10/10 | 0% (0) | 9% | 11.0 | 626.2 | replan_budget_exhausted: 10 |
| FINAL.K3-n2 | 10/10 | 80% (8) | 91% | 6.9 | 347.7 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n3 | 10/10 | 60% (6) | 81% | 7.3 | 383.7 | plan_completed: 7, replan_budget_exhausted: 2, replan_loop: 1 |
| FINAL.G1-n1 | 10/10 | 10% (1) | 62% | 9.9 | 457.4 | plan_completed: 1, replan_budget_exhausted: 5, replan_loop: 4 |
| FINAL.K1-w1 | 10/10 | 50% (5) | 51% | 7.8 | 331.2 | plan_completed: 5, replan_budget_exhausted: 4, replan_loop: 1 |
| FINAL.K1-w2 | 10/10 | 40% (4) | 48% | 8.9 | 404.8 | plan_completed: 4, replan_budget_exhausted: 3, replan_loop: 3 |
