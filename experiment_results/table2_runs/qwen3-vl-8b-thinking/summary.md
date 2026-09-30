# qwen3-vl-8b-thinking (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 90% (9) | 98% | 2.1 | 279.5 | plan_completed: 10 |
| FINAL.G0 | 10/10 | 50% (5) | 80% | 3.2 | 383.6 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K1 | 10/10 | 100% (10) | 100% | 3.9 | 423.8 | plan_completed: 10 |
| FINAL.K2 | 10/10 | 80% (8) | 93% | 3.1 | 322.7 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3 | 10/10 | 100% (10) | 100% | 2.8 | 345.4 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100% (10) | 100% | 3.1 | 368.2 | plan_completed: 10 |
| FINAL.G1 | 10/10 | 30% (3) | 80% | 5.9 | 775.0 | plan_completed: 8, replan_budget_exhausted: 1, replan_loop: 1 |
| FINAL.G2 | 10/10 | 40% (4) | 76% | 6.3 | 976.4 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G3 | 10/10 | 40% (4) | 51% | 7.5 | 1008.6 | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K3-n2 | 10/10 | 80% (8) | 91% | 4.2 | 450.5 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K3-n3 | 10/10 | 60% (6) | 95% | 3.5 | 534.0 | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 60% (6) | 93% | 4.9 | 607.5 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w1 | 10/10 | 80% (8) | 92% | 5.4 | 569.9 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w2 | 10/10 | 70% (7) | 94% | 6.7 | 723.1 | plan_completed: 7, replan_budget_exhausted: 3 |
