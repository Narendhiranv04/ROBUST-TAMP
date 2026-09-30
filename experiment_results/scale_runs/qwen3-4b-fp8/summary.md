# qwen3-4b-fp8 (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 30% (3) | 42% | 5.7 | 196.4 | plan_completed: 3, replan_loop: 7 |
| FINAL.G0 | 10/10 | 0% (0) | 60% | 7.2 | 230.1 | plan_completed: 1, replan_budget_exhausted: 2, replan_loop: 7 |
| FINAL.K1 | 10/10 | 0% (0) | 6% | 7.9 | 232.8 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K2 | 10/10 | 100% (10) | 100% | 3.6 | 174.3 | plan_completed: 9, replan_loop: 1 |
| FINAL.K3 | 10/10 | 0% (0) | 3% | 6.9 | 157.1 | planner_returned_no_actions: 1, replan_loop: 9 |
| FINAL.K4 | 10/10 | 0% (0) | 3% | 8.2 | 332.2 | planner_returned_no_actions: 1, replan_budget_exhausted: 3, replan_loop: 6 |
| FINAL.G1 | 10/10 | 0% (0) | 57% | 8.1 | 273.6 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.G2 | 10/10 | 0% (0) | 32% | 8.4 | 369.4 | replan_budget_exhausted: 3, replan_loop: 7 |
| FINAL.G3 | 10/10 | 0% (0) | 34% | 9.3 | 417.5 | plan_completed: 1, replan_budget_exhausted: 4, replan_loop: 5 |
| FINAL.K3-n2 | 10/10 | 0% (0) | 0% | 7.9 | 280.7 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K3-n3 | 10/10 | 0% (0) | 2% | 7.4 | 270.8 | replan_loop: 10 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 52% | 7.4 | 313.1 | replan_budget_exhausted: 1, replan_loop: 9 |
| FINAL.K1-w1 | 10/10 | 0% (0) | 4% | 6.8 | 200.8 | planner_returned_no_actions: 1, replan_loop: 9 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 0% | 8.5 | 246.8 | replan_budget_exhausted: 2, replan_loop: 8 |
