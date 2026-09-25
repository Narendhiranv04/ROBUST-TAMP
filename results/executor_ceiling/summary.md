# Executor ceiling: GT oracle planner, seeds 0-9

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| K1 | 10/10 | 100% (10) | 100% | 2.6 | 42.4 | plan_completed: 10 |
| K2 | 10/10 | 90% (9) | 98% | 2.0 | 52.0 | plan_completed: 10 |
| K3 | 10/10 | 60% (6) | 92% | 2.9 | 62.3 | plan_completed: 9, replan_budget_exhausted: 1 |
| G1 | 10/10 | 100% (10) | 100% | 2.0 | 73.9 | plan_completed: 10 |
| G2 | 10/10 | 100% (10) | 100% | 2.0 | 88.7 | plan_completed: 10 |
| G3 | 10/10 | 90% (9) | 96% | 2.9 | 94.5 | plan_completed: 9, replan_budget_exhausted: 1 |
