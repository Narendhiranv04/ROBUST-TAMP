# Phase 6: WHEN (parallel planning and execution)

Oracle planner with a simulated 20 s planner latency per call. Idle time: planner latency not covered by
executing independent bundles (parallel off: the whole replan latency). Independent bundles: available
/ executed during the wait, summed over replans. Trial time from `trial_end.trial_time_s`.

| Variant | Trials | Indep. bundles available | Indep. bundles executed | Idle s (off) | Idle s (on) | Trial s (off) | Trial s (on) | Merge conflicts (on) | Success (off) | Success (on) |
|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 2 | — | — | 0.0 | 0.0 | 95.9 | 95.0 | — | 100% | 100% |
| FINAL.G0 | 2 | — | — | 0.0 | 0.0 | 91.3 | 92.1 | — | 100% | 100% |
| FINAL.K1 | 2 | 2.0 | 2.0 | 20.0 | 0.0 | 129.5 | 110.2 | 0% | 100% | 100% |
| FINAL.K2 | 2 | — | — | 0.0 | 0.0 | 99.5 | 99.7 | — | 100% | 100% |
| FINAL.K3 | 2 | 0.0 | 0.0 | 20.0 | 20.0 | 131.6 | 133.5 | 0% | 100% | 100% |
| FINAL.K4 | 2 | 0.0 | 0.0 | 20.0 | 20.0 | 139.5 | 140.8 | 0% | 100% | 100% |
| FINAL.G1 | 2 | 1.0 | 1.0 | 20.0 | 12.1 | 150.1 | 138.7 | 0% | 100% | 100% |
| FINAL.G2 | 2 | 1.0 | 1.0 | 20.0 | 12.1 | 142.8 | 132.5 | 0% | 100% | 100% |
| FINAL.G3 | 2 | 1.0 | 1.0 | 20.0 | 12.2 | 137.0 | 125.7 | 0% | 100% | 100% |
| FINAL.K3-n2 | 2 | 0.0 | 0.0 | 20.0 | 20.0 | 157.2 | 151.4 | 0% | 100% | 100% |
| FINAL.K3-n3 | 2 | 0.0 | 0.0 | 20.0 | 20.0 | 173.8 | 187.0 | 0% | 100% | 100% |
| FINAL.G1-n1 | 2 | 1.0 | 1.0 | 20.0 | 12.7 | 127.0 | 122.8 | 0% | 100% | 100% |
| FINAL.K1-w1 | 2 | 3.0 | 2.0 | 20.0 | 0.0 | 148.3 | 156.0 | 0% | 100% | 100% |
| FINAL.K1-w2 | 2 | 4.0 | 2.0 | 20.0 | 0.0 | 184.9 | 150.8 | 0% | 100% | 100% |

## C2 sweep (K1, K1-w1, K1-w2): idle time saved vs independent work

| w | Independent bundles executed | Idle time saved s | Trial time saved s |
|---|---|---|---|
| 0 | 2.0 | 20.0 | 19.3 |
| 1 | 2.0 | 20.0 | -7.8 |
| 2 | 2.0 | 20.0 | 34.1 |

![C2](c2_idle_time_saved.png)
