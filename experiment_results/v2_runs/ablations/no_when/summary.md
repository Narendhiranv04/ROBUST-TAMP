# ablations/no_when (qwen3-vl-8b-thinking, zero-shot)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 70% (7) | 77% | 6.7 | 644.7 | plan_completed: 7, replan_budget_exhausted: 3 |
| FINAL.K2 | 10/10 | 100% (10) | 100% | 3.1 | 365.8 | plan_completed: 10 |
| FINAL.K3 | 10/10 | 100% (10) | 100% | 4.4 | 483.5 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100% (10) | 100% | 3.7 | 439.8 | plan_completed: 10 |
| FINAL.G1 | 10/10 | 20% (2) | 79% | 5.7 | 753.9 | plan_completed: 7, replan_budget_exhausted: 3 |
| FINAL.G2 | 10/10 | 10% (1) | 59% | 7.2 | 1130.8 | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G3 | 10/10 | 20% (2) | 49% | 8.9 | 1291.0 | plan_completed: 4, replan_budget_exhausted: 6 |
