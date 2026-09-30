# Experiment results (snapshot of 2026-09-30, 10:30 IST)

A copy of `results/` as synced from the lab servers. Runs still in progress at snapshot time are
partial (see below). PNGs sent to the planner are not included (they are on the servers and in the
archives); every trial's prompts, exact request/response (`*.exchange.json`), `trial_log.jsonl`,
`record.json` and logs are.

| Folder | Contents |
|---|---|
| `table2/` | Built tables: `table2.md`, `paper_tables.md`, `latex_tables.tex`, `table2_rows.tex`, CSVs, Figs. 4-5, failure breakdowns (`failures*/`) |
| `v2_runs/table2/` | Table 2 (b) runs and the full system (`qwen3-vl-8b-thinking`, Table 4), fixed code, 14 variants x 10 seeds; `*-fp8-icl`: Table 2 (a) grill ICL rows |
| `v2_runs/ablations/` | Table 5 ablations, zero-shot (7 core variants x 10 seeds each) |
| `v2_runs/icl/` | Full system with the grill in-context examples (G0-G3, G1-n1) |
| `v2_runs/dropped/` | Runs set aside (failed downloads, the dropped previous-system condition) |
| `scale_runs/` | Table 2 (a) scale study (Qwen3 4B/8B/32B, VLM/LLM, FP8), server2 |
| `table2_runs/` | Earlier Table 2 runs (pre-fix); `qwen3-vl-8b-instruct` and `qwen3-8b-nothink` are the kept rows |
| `gt_fixed/` | GT oracle reruns at the fixed code (Ceil. column of Table 4) |
| `figures/` | Fig. 1 frames (GT trials) and their annotated draft |
| `visuals/` | GT visual frames per variant (the 4K isometric videos are not included: 1.2 GB) |

In progress at snapshot time: 8B LLM grill ICL (server1), 32B VLM grill ICL and 32B LLM zero-shot /
ICL (server2), Table 5 grill ablations with ICL and the Ministral rows (server1, queued).
