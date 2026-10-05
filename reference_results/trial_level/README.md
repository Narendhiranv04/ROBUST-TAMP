# Trial-level results

One row per scored trial, extracted from the trial logs (`trial_log.jsonl`) of the runs behind the
paper's tables by `supplementary/scripts/extract_trial_results.py` (not part of this archive's code;
it applies `evaluation.model_run_report.paper_outcome`). Superseded attempts (infrastructure reruns,
runs replaced after code changes) are excluded.

| Column | Meaning |
|---|---|
| `label` | run (see below) |
| `variant`, `seed` | `FINAL.<id>`, seed 0-9 |
| `attempt` | attempt number of the scored trial (2-3 after an infrastructure rerun) |
| `success`, `pgc` | paper metric: every goal relation and cooking condition holds; partial goal completion |
| `conditions`, `unmet` | number of evaluated conditions and of unmet ones |
| `hc_violations` | ordering hard constraints violated (insertion errors; do not affect success or PGC) |
| `planner_calls`, `planner_time_s`, `trial_time_s` | per trial |
| `termination_reason` | how the trial ended |

## Files and labels

| File | Labels | Paper table rows |
|---|---|---|
| `main_results.csv` | `ours_zero_shot` (14 variants), `ours_icl_grill` (5 grill variants, `examples_v3`) | main results; "Ours" rows of the baseline comparison; 8B VLM rows of the planner comparison |
| `baselines.csv` | `<baseline>_zero_shot`, `<baseline>_icl_grill` for `vlm_tamp`, `owl_tamp`, `inner_monologue`, `epog` | baseline comparison |
| `ablations.csv` | `kitchen_zs_<condition>` (zero-shot runs of the 7 core variants; the paper uses K1-K4), `grill_icl_<condition>` (G1-G3, `examples_v3`), `grill_icl_llm_planner_qwen3-8b` | ablations ("Full system" kitchen/grill: `ours_zero_shot` K1-K4 and `ours_icl_grill` G1-G3; "LLM planner" kitchen: `qwen3-8b` K1-K4 in `planner_selection.csv`) |
| `planner_selection.csv` | 8B-class models (zero-shot, 14 variants), `qwen3-8b_icl_grill`, and the FP8 rows `qwen3-4b-fp8`, `qwen3-32b-fp8`, `qwen3-vl-32b-thinking-fp8` | planner comparison |

ICL rows are reported as in the paper: the kitchen trials of the zero-shot label with the grill trials
of the ICL label (kitchen prompts are identical with and without ICL), e.g.

    python summarize_trial_results.py results/trial_level/baselines.csv \
        --combine inner_monologue_zero_shot:inner_monologue_icl_grill

## Verification

Aggregating these files reproduces the paper's SR and PGC (kitchen, grill, all), planner calls,
planning time and trial time for every row listed above (checked when the files were extracted).

## Not included (run records not available in this repository copy)

- Planner comparison (a): Qwen3-VL-4B zero-shot, and the 4B and 32B ICL rows (`examples_v3`, RTX PRO 5000).
- Planner comparison (b): InternVL3.5-8B and Qwen2.5-7B-Instruct (parser-fix reruns, RTX PRO 5000). The
  runs of these two models in this repository copy predate the fix and do not match the paper.
- Median per-call latency (`Lat.`) and idle time (`Idle`) need the full prompt and event logs.
