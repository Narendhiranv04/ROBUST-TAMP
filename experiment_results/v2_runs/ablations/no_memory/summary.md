# ablations/no_memory (qwen3-vl-8b-thinking, zero-shot)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 70% (7) | 96% | 6.7 | 623.5 | plan_completed: 10 |
| FINAL.K2 | 10/10 | 90% (9) | 98% | 2.2 | 267.5 | plan_completed: 10 |
| FINAL.K3 | 10/10 | 80% (8) | 97% | 3.9 | 403.1 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 80% (8) | 97% | 3.2 | 384.6 | plan_completed: 10 |
| FINAL.G1 | 10/10 | 20% (2) | 77% | 5.5 | 752.8 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G2 | 10/10 | 30% (3) | 76% | 6.9 | 897.9 | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G3 | 10/10 | 20% (2) | 47% | 8.3 | 1160.3 | plan_completed: 4, replan_budget_exhausted: 4, replan_loop: 2 |
