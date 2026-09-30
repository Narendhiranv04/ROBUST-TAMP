# Table 2

(a) Scale, modality, and prompting

| Scale | Mod. | Prompt | SR_K | SR_G | SR | PGC | Plan. (s) | trials | calls | fail. replans/trial |
|---|---|---|---|---|---|---|---|---|---|---|
| 4B | LLM | ZS | 14.4 | 0.0 | 9.3 | 26.4 | 242 | 140 | 7.3786 | 5.493 |
| 4B | LLM | ICL | -- | -- | -- | -- | -- | 0 | -- | -- |
| 4B | VLM | ZS | 58.9 | 12.0 | 42.1 | 58.1 | 743 | 140 | 7.1357 | 5.071 |
| 4B | VLM | ICL | -- | -- | -- | -- | -- | 0 | -- | -- |
| 8B | LLM | ZS | 82.2 | 6.0 | 55.0 | 70.5 | 297 | 140 | 7.6071 | 4.936 |
| 8B | LLM | ICL | -- | -- | -- | -- | -- | 0 | -- | -- |
| 8B | VLM | ZS | 93.3 | 14.0 | 65.0 | 82.1 | 518 | 140 | 5.55 | 2.614 |
| 8B | VLM | ICL | -- | -- | -- | -- | -- | 0 | -- | -- |
| 32B | LLM | ZS | -- | -- | -- | -- | -- | 0 | -- | -- |
| 32B | LLM | ICL | -- | -- | -- | -- | -- | 0 | -- | -- |
| 32B | VLM | ZS | 100.0 | -- | 100.0 | 100.0 | 303 | 4 | 2.5 | 1.5 |
| 32B | VLM | ICL | -- | -- | -- | -- | -- | 0 | -- | -- |

(b) 8B-class models

| Mod. | Reas. | Model | SR_K | SR_G | SR | PGC | Plan. (s) | trials | calls | fail. replans/trial |
|---|---|---|---|---|---|---|---|---|---|---|
| VLM | no | Qwen3-VL-8B-Instruct | 1.1 | 2.0 | 1.4 | 10.6 | 168 | 140 | 8.7571 | 6.936 |
| VLM | no | Ministral-3-8B-Instruct | -- | -- | -- | -- | -- | 0 | -- | -- |
| VLM | no | InternVL3.5-8B | 15.6 | 0.0 | 10.0 | 21.8 | 76 | 140 | 9.3714 | 7.15 |
| VLM | yes | Qwen3-VL-8B-Thinking | 94.4 | 22.0 | 68.6 | 86.5 | 540 | 140 | 5.0714 | 2.279 |
| VLM | yes | Ministral-3-8B-Reasoning | -- | -- | -- | -- | -- | 0 | -- | -- |
| VLM | yes | Holo2-8B | 31.1 | 2.0 | 20.7 | 40.2 | 135 | 140 | 9.6357 | 6.864 |
| LLM | no | Qwen3-8B (think off) | 1.1 | 6.0 | 2.9 | 13.1 | 25 | 140 | 8 | 6.55 |
| LLM | no | Llama-3.1-8B-Instruct | 6.7 | 0.0 | 4.3 | 14.5 | 124 | 140 | 10.5571 | 8.843 |
| LLM | no | Qwen2.5-7B-Instruct | 0.0 | 0.0 | 0.0 | 6.2 | 7 | 140 | 9.5643 | 8.071 |
| LLM | yes | Qwen3-8B (think on) | 81.1 | 4.0 | 53.6 | 68.3 | 327 | 140 | 7.4714 | 5.0 |
| LLM | yes | R1-Distill-Llama-8B | 0.0 | 0.0 | 0.0 | 5.7 | 500 | 140 | 10.9857 | 9.986 |
| LLM | yes | R1-Distill-Qwen-7B | 0.0 | 0.0 | 0.0 | 8.8 | 597 | 140 | 9.4643 | 8.293 |

SR_K / SR_G: success over the 9 kitchen / 5 grill variants; SR, PGC over all 14 (10 trials each), with the paper's R and P conditions (evaluation/model_run_report.paper_outcome); insertion errors (ordering hard constraints violated) are counted separately in table2a/b.csv and do not change SR or PGC. Plan.: mean planner time per trial. `trials` < 140: run in progress or incomplete.
