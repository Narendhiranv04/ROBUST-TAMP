# Phase 6: WHEN (parallel planning and execution)

Oracle planner with a simulated 20 s planner latency per call. Idle time: planner latency not covered by
executing independent bundles (parallel off: the whole replan latency). Independent bundles: available
/ executed during the wait, summed over replans. Trial time from `trial_end.trial_time_s`.

| Variant | Trials | Indep. bundles available | Indep. bundles executed | Idle s (off) | Idle s (on) | Trial s (off) | Trial s (on) | Merge conflicts (on) | Success (off) | Success (on) |
|---|---|---|---|---|---|---|---|---|---|---|
| FINAL.K0 | 2 | — | — | 0.0 | 0.0 | 94.4 | 96.1 | — | 100% | 100% |
| FINAL.G0 | 2 | — | — | 0.0 | 0.0 | 91.1 | 91.4 | — | 100% | 100% |
| FINAL.K1 | 2 | 2.0 | 2.0 | 20.0 | 0.0 | 142.5 | 122.4 | 0% | 100% | 100% |
| FINAL.K2 | 2 | — | — | 0.0 | 0.0 | 98.1 | 98.1 | — | 100% | 100% |
| FINAL.K3 | 2 | 0.0 | 0.0 | 20.0 | 20.0 | 133.3 | 132.4 | 0% | 100% | 100% |
| FINAL.K4 | 2 | 3.0 | 2.0 | 20.0 | 0.0 | 140.0 | 118.2 | 0% | 100% | 100% |
| FINAL.G1 | 2 | 2.0 | 2.0 | 20.0 | 4.9 | 146.5 | 129.4 | 0% | 100% | 100% |
| FINAL.G2 | 2 | 2.0 | 2.0 | 20.0 | 5.0 | 139.6 | 122.3 | 0% | 100% | 100% |
| FINAL.G3 | 2 | 2.0 | 2.0 | 20.0 | 5.2 | 132.5 | 116.2 | 0% | 100% | 100% |
| FINAL.K3-n2 | 2 | 0.0 | 0.0 | 20.0 | 20.0 | 150.0 | 149.9 | 0% | 100% | 100% |
| FINAL.K3-n3 | 2 | 0.0 | 0.0 | 20.0 | 20.0 | 183.5 | 178.8 | 0% | 100% | 50% |
| FINAL.G1-n1 | 2 | 2.0 | 2.0 | 20.0 | 6.2 | 127.1 | 112.5 | 0% | 100% | 100% |
| FINAL.K1-w1 | 2 | 3.0 | 2.0 | 20.0 | 0.0 | 150.6 | 146.6 | 0% | 100% | 100% |
| FINAL.K1-w2 | 2 | 4.0 | 2.0 | 20.0 | 0.0 | 184.9 | 166.7 | 0% | 100% | 100% |

## C2 sweep (K1, K1-w1, K1-w2): idle time saved vs independent work

| w | Independent bundles executed | Idle time saved s | Trial time saved s |
|---|---|---|---|
| 0 | 2.0 | 20.0 | 20.2 |
| 1 | 2.0 | 20.0 | 4.0 |
| 2 | 2.0 | 20.0 | 18.2 |

![C2](c2_idle_time_saved.png)
