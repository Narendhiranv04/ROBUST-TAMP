# qwen3-8b-fp8 (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 100% (10) | 100% | 4.7 | 256.8 | plan_completed: 10 |
| FINAL.G0 | 10/10 | 10% (1) | 47% | 8.1 | 384.4 | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K1 | 10/10 | 70% (7) | 77% | 7.1 | 305.4 | plan_completed: 7, replan_budget_exhausted: 2, replan_loop: 1 |
| FINAL.K2 | 10/10 | 100% (10) | 100% | 3.2 | 163.7 | plan_completed: 10 |
| FINAL.K3 | 10/10 | 90% (9) | 90% | 5.6 | 235.1 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K4 | 10/10 | 90% (9) | 90% | 6.0 | 276.3 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G1 | 10/10 | 0% (0) | 67% | 10.3 | 480.9 | plan_completed: 2, replan_budget_exhausted: 7, replan_loop: 1 |
| FINAL.G2 | 10/10 | 0% (0) | 52% | 10.0 | 531.1 | plan_completed: 2, replan_budget_exhausted: 8 |
| FINAL.G3 | 10/10 | 0% (0) | 10% | 11.0 | 548.1 | replan_budget_exhausted: 10 |
| FINAL.K3-n2 | 10/10 | 90% (9) | 99% | 5.8 | 314.4 | plan_completed: 10 |
| FINAL.K3-n3 | 10/10 | 90% (9) | 99% | 6.0 | 307.7 | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 20% (2) | 75% | 9.9 | 471.3 | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K1-w1 | 10/10 | 30% (3) | 41% | 9.6 | 364.1 | plan_completed: 4, replan_budget_exhausted: 4, replan_loop: 2 |
| FINAL.K1-w2 | 10/10 | 60% (6) | 63% | 9.2 | 305.8 | plan_completed: 6, replan_budget_exhausted: 4 |
