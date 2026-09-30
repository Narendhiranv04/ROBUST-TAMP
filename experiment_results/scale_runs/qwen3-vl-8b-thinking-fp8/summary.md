# qwen3-vl-8b-thinking-fp8 (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 100% (10) | 100% | 1.9 | 221.8 | plan_completed: 10 |
| FINAL.G0 | 10/10 | 10% (1) | 30% | 8.2 | 792.1 | plan_completed: 3, replan_budget_exhausted: 7 |
| FINAL.K1 | 10/10 | 80% (8) | 89% | 6.0 | 480.1 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K2 | 10/10 | 100% (10) | 100% | 2.5 | 258.1 | plan_completed: 10 |
| FINAL.K3 | 10/10 | 100% (10) | 100% | 4.2 | 418.8 | plan_completed: 10 |
| FINAL.K4 | 10/10 | 100% (10) | 100% | 4.4 | 427.0 | plan_completed: 10 |
| FINAL.G1 | 10/10 | 20% (2) | 83% | 6.2 | 715.7 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.G2 | 10/10 | 20% (2) | 76% | 6.8 | 952.4 | plan_completed: 7, replan_budget_exhausted: 2, replan_loop: 1 |
| FINAL.G3 | 10/10 | 20% (2) | 50% | 9.7 | 1122.4 | plan_completed: 4, replan_budget_exhausted: 6 |
| FINAL.K3-n2 | 10/10 | 80% (8) | 89% | 3.5 | 396.9 | plan_completed: 9, replan_loop: 1 |
| FINAL.K3-n3 | 10/10 | 80% (8) | 98% | 4.3 | 512.4 | plan_completed: 10 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 67% | 6.3 | 680.8 | plan_completed: 8, replan_budget_exhausted: 2 |
| FINAL.K1-w1 | 10/10 | 80% (8) | 84% | 6.6 | 607.4 | plan_completed: 8, replan_budget_exhausted: 1, replan_loop: 1 |
| FINAL.K1-w2 | 10/10 | 80% (8) | 92% | 7.1 | 638.3 | plan_completed: 9, replan_budget_exhausted: 1 |
