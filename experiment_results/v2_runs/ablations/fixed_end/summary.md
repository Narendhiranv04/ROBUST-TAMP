# ablations/fixed_end (qwen3-vl-8b-thinking, zero-shot)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K1 | 10/10 | 0% (0) | 0% | 11.0 | 916.5 | replan_budget_exhausted: 10 |
| FINAL.K2 | 10/10 | 100% (10) | 100% | 2.2 | 315.4 | plan_completed: 10 |
| FINAL.K3 | 10/10 | 0% (0) | 9% | 10.2 | 849.5 | plan_completed: 1, replan_budget_exhausted: 9 |
| FINAL.K4 | 10/10 | 100% (10) | 100% | 2.8 | 356.4 | plan_completed: 10 |
| FINAL.G1 | 10/10 | 10% (1) | 58% | 6.0 | 863.4 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.G2 | 10/10 | 0% (0) | 49% | 8.6 | 1330.9 | plan_completed: 6, replan_budget_exhausted: 4 |
| FINAL.G3 | 10/10 | 30% (3) | 64% | 8.5 | 1139.6 | plan_completed: 4, replan_budget_exhausted: 6 |
