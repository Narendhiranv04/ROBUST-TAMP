# Table 4: main results (Qwen3-VL-8B-Thinking, full system, zero-shot)

| Group | ID | Ceil. | SR | PGC | Calls | Plan. | Idle | Time | Urg. | trials |
|---|---|---|---|---|---|---|---|---|---|---|
| A. Basic | K0 | 100.0 | 100.0 | 100.0 | 2.2 | 229 | – | 298 | – | 10 |
| A. Basic | G0 | 100.0 | 30.0 | 63.3 | 3.2 | 352 | – | 487 | – | 10 |
| B. Core | K1 | 100.0 | 90.0 | 93.3 | 5.7 | 481 | 189 | 561 | 10.0 | 10 |
| B. Core | K2 | 100.0 | 90.0 | 95.0 | 4.0 | 328 | – | 397 | – | 10 |
| B. Core | K3 | 100.0 | 100.0 | 100.0 | 3.8 | 385 | 122 | 480 | 70.0 | 10 |
| B. Core | K4 | 100.0 | 100.0 | 100.0 | 3.1 | 316 | 96 | 390 | 10.0 | 10 |
| B. Core | G1 | 100.0 | 40.0 | 84.3 | 5.4 | 684 | 143 | 774 | 50.0 | 10 |
| B. Core | G2 | 100.0 | 10.0 | 62.9 | 6.2 | 916 | 223 | 1017 | 15.0 | 10 |
| B. Core | G3 | 100.0 | 10.0 | 47.1 | 9.6 | 1223 | 180 | 1354 | 20.0 | 10 |
| C. Cardinality | K3-n2 | 100.0 | 90.0 | 98.6 | 3.9 | 413 | 143 | 522 | 70.0 | 10 |
| C. Cardinality | K3-n3 | 100.0 | 100.0 | 100.0 | 4.0 | 442 | 128 | 580 | 86.7 | 10 |
| C. Cardinality | G1-n1 | 100.0 | 20.0 | 74.0 | 5.8 | 626 | 117 | 714 | 80.0 | 10 |
| C. Cardinality | K1-w1 | 100.0 | 90.0 | 98.6 | 7.7 | 655 | 266 | 774 | 0.0 | 10 |
| C. Cardinality | K1-w2 | 100.0 | 90.0 | 93.8 | 6.4 | 515 | 143 | 648 | 0.0 | 10 |
| | Mean (kitchen) | 100.0 | 94.4 | 97.7 | 4.5 | 418 | 144 | 517 | 49.0 | 90 |
| | Mean (grill) | 100.0 | 22.0 | 66.3 | 6.0 | 760 | 163 | 869 | 35.7 | 50 |
| | Mean (all) | 100.0 | 68.6 | 86.5 | 5.1 | 540 | 155 | 643 | 43.5 | 140 |

Ceil.: the oracle planner, full system (GT, same code). Idle and Urg. only for variants with an expected replan; means over all trials of the group.

# Table 5: ablations (core variants K1-K4, G1-G3; 10 trials each)

| Condition | SR (%) | Calls | Unn. | Ins. (%) | Idle | Time (s) | trials |
|---|---|---|---|---|---|---|---|
| Full system | 62.9 | 5.4 | 0.0 | 44.3 | 162 | 710 | 70/70 |
| −Memory | 58.6 | 5.2 | 0.0 | 41.4 | 162 | 641 | 70/70 |
| −IF | 62.9 | 5.4 | 0.1 | 34.3 | 237 | 627 | 70/70 |
| −WHERE | 58.6 | 4.3 | 0.0 | – | 105 | 550 | 70/70 |
| Fixed front | 60.0 | 5.7 | 0.0 | 41.4 | 184 | 787 | 70/70 |
| Fixed end | 35.7 | 7.0 | 0.0 | 62.9 | 264 | 825 | 70/70 |
| −WHEN | 60.0 | 5.7 | 0.0 | 37.1 | 192 | 730 | 70/70 |
| LLM planner | 51.4 | 7.4 | 0.0 | 25.7 | 176 | 419 | 70/70 |

# Planner latency by scale (Qwen3 family, FP8, full system, zero-shot; all 14 variants)

| Scale | Mod. | Model | Calls/trial | Plan. (s/trial) | Call latency mean | p50 | p90 | max (s) | Output tokens/call | SR | trials |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4B | VLM | qwen3-vl-4b-thinking-fp8 | 7.1 | 743 | 104.2 | 99.9 | 146.8 | 295.5 | 9530 | 42.1 | 140/140 |
| 4B | LLM | qwen3-4b-fp8 | 7.4 | 242 | 32.8 | 25.8 | 49.6 | 281.9 | 4019 | 9.3 | 140/140 |
| 8B | VLM | qwen3-vl-8b-thinking-fp8 | 5.5 | 518 | 93.3 | 90.3 | 141.3 | 240.4 | 7100 | 65.0 | 140/140 |
| 8B | LLM | qwen3-8b-fp8 | 7.6 | 297 | 39.0 | 34.2 | 60.7 | 325.4 | 3612 | 55.0 | 140/140 |
| 32B | VLM | qwen3-vl-32b-thinking-fp8 | 2.5 | 303 | 121.1 | 128.1 | 180.9 | 181.9 | 3307 | 100.0 | 4/140 |
| 32B | LLM | qwen3-32b-fp8 | -- | -- | -- | -- | -- | -- | -- | -- | 0/140 |

Call latency: one planner call, request to answer (s). All scales on the same GPU (RTX PRO 5000, 48 GB), vLLM 0.30.0, 6 trials at a time.
