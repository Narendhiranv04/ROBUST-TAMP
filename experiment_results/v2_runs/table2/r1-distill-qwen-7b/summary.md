# r1-distill-qwen-7b (zero-shot, full system)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 10/10 | 0% (0) | 0% | 9.7 | 784.7 | planner_returned_no_actions: 2, replan_budget_exhausted: 7, replan_loop: 1 |
| FINAL.G0 | 10/10 | 0% (0) | 20% | 9.1 | 575.7 | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.K1 | 10/10 | 0% (0) | 0% | 8.8 | 648.9 | planner_returned_no_actions: 4, replan_budget_exhausted: 6 |
| FINAL.K2 | 10/10 | 0% (0) | 20% | 9.7 | 750.2 | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.K3 | 10/10 | 0% (0) | 0% | 9.6 | 467.0 | planner_returned_no_actions: 4, replan_budget_exhausted: 6 |
| FINAL.K4 | 10/10 | 0% (0) | 0% | 8.5 | 636.6 | planner_returned_no_actions: 4, replan_budget_exhausted: 6 |
| FINAL.G1 | 10/10 | 0% (0) | 47% | 10.6 | 574.7 | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.G2 | 10/10 | 0% (0) | 25% | 10.1 | 521.9 | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.G3 | 10/10 | 0% (0) | 9% | 10.6 | 651.4 | planner_returned_no_actions: 1, replan_budget_exhausted: 9 |
| FINAL.K3-n2 | 10/10 | 0% (0) | 0% | 9.9 | 713.2 | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.K3-n3 | 10/10 | 0% (0) | 0% | 9.6 | 595.1 | planner_returned_no_actions: 2, replan_budget_exhausted: 8 |
| FINAL.G1-n1 | 10/10 | 0% (0) | 38% | 10.1 | 597.6 | planner_returned_no_actions: 1, replan_budget_exhausted: 9 |
| FINAL.K1-w1 | 10/10 | 0% (0) | 2% | 9.0 | 596.7 | planner_returned_no_actions: 3, replan_budget_exhausted: 7 |
| FINAL.K1-w2 | 10/10 | 0% (0) | 0% | 7.2 | 355.5 | planner_returned_no_actions: 5, replan_budget_exhausted: 5 |
