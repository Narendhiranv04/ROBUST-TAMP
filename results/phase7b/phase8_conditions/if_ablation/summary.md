# Ablation: IF (discovery, corrective, parallel, memory; oracle, 20 s delay)

| Variant | Trials | Task success rate | Partial goal completion | Planner calls (mean) | Trial time s (mean) | Termination reasons |
|---|---|---|---|---|---|---|
| FINAL.K0 | 1/1 | 100% (1) | 100% | 1.0 | 95.9 | plan_completed: 1 |
| FINAL.G0 | 1/1 | 100% (1) | 100% | 1.0 | 91.6 | plan_completed: 1 |
| FINAL.K1 | 1/1 | 100% (1) | 100% | 2.0 | 113.9 | plan_completed: 1 |
| FINAL.K2 | 1/1 | 100% (1) | 100% | 2.0 | 99.5 | plan_completed: 1 |
| FINAL.K3 | 1/1 | 100% (1) | 100% | 2.0 | 132.8 | plan_completed: 1 |
| FINAL.K4 | 1/1 | 100% (1) | 100% | 2.0 | 118.1 | plan_completed: 1 |
| FINAL.G1 | 1/1 | 100% (1) | 100% | 2.0 | 131.5 | plan_completed: 1 |
| FINAL.G2 | 1/1 | 100% (1) | 100% | 2.0 | 124.5 | plan_completed: 1 |
| FINAL.G3 | 1/1 | 100% (1) | 100% | 2.0 | 118.1 | plan_completed: 1 |
| FINAL.K3-n2 | 1/1 | 100% (1) | 100% | 2.0 | 149.4 | plan_completed: 1 |
| FINAL.K3-n3 | 1/1 | 0% (0) | 64% | 6.0 | 209.0 | replan_loop: 1 |
| FINAL.G1-n1 | 1/1 | 100% (1) | 100% | 2.0 | 113.1 | plan_completed: 1 |
| FINAL.K1-w1 | 1/1 | 100% (1) | 100% | 3.0 | 158.5 | plan_completed: 1 |
| FINAL.K1-w2 | 1/1 | 100% (1) | 100% | 2.0 | 152.1 | plan_completed: 1 |
