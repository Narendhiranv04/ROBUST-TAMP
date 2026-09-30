# qwen3-vl-4b-thinking-fp8 (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 100% (10) | 100% | 2.5 | 287.8 | plan_completed: 10 |
| FINAL.G0 | 10/10 | 10% (1) | 63% | 7.1 | 808.7 | plan_completed: 6, replan_budget_exhausted: 1, replan_loop: 3 |
| FINAL.K1 | 10/10 | 10% (1) | 10% | 10.3 | 1067.2 | plan_completed: 1, replan_budget_exhausted: 7, replan_loop: 2 |
| FINAL.K2 | 10/10 | 90% (9) | 98% | 3.7 | 423.5 | plan_completed: 10 |
| FINAL.K3 | 10/10 | 80% (8) | 80% | 5.1 | 508.0 | plan_completed: 8, replan_loop: 2 |
| FINAL.K4 | 10/10 | 90% (9) | 93% | 5.4 | 565.9 | plan_completed: 9, replan_loop: 1 |
| FINAL.G1 | 10/10 | 20% (2) | 72% | 7.8 | 805.9 | plan_completed: 3, replan_loop: 7 |
| FINAL.G2 | 10/10 | 0% (0) | 44% | 9.0 | 1324.4 | replan_budget_exhausted: 4, replan_loop: 6 |
| FINAL.G3 | 10/10 | 10% (1) | 17% | 7.4 | 885.3 | plan_completed: 1, replan_loop: 9 |
| FINAL.K3-n2 | 10/10 | 70% (7) | 88% | 5.1 | 551.5 | plan_completed: 9, replan_budget_exhausted: 1 |
| FINAL.K3-n3 | 10/10 | 70% (7) | 77% | 7.2 | 779.2 | plan_completed: 7, replan_budget_exhausted: 1, replan_loop: 2 |
| FINAL.G1-n1 | 10/10 | 20% (2) | 72% | 7.9 | 858.9 | plan_completed: 5, replan_budget_exhausted: 1, replan_loop: 4 |
| FINAL.K1-w1 | 10/10 | 10% (1) | 14% | 10.4 | 1048.2 | plan_completed: 1, replan_budget_exhausted: 9 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 0% | 11.0 | 1126.7 | replan_budget_exhausted: 10 |
