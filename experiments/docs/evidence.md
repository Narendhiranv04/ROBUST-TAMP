# Scientific scope and evidence

This release supports the simulated experiments for *Deciding If, When, and Where to Replan for Robust Manipulation*. Fourteen final MuJoCo variants are used; legacy variants remain for controller regression tests. Real-robot operation is outside this release.

## Implementation map

| Paper component | Implementation |
|---|---|
| Planning and recovery loop | `src/llm_pipeline/pipeline.py` |
| Observation memory and occlusion | `src/llm_pipeline/memory.py`, `segmentation_adapter.py` |
| IF discovery/relevance/overlap decision | `src/llm_pipeline/if_rule.py`, `evaluation/labeled_rules.py` |
| WHEN independence and dependency propagation | `src/llm_pipeline/parallel.py` |
| WHERE validation and insertion | `src/llm_pipeline/corrective.py`, `strict_parser.py`, pipeline merge logic |
| Initial/corrective prompts and ICL | `src/llm_pipeline/prompt_v2.py`, `icl_examples.py` |
| Controllers and pre-action checks | `src/llm_pipeline/executor.py`, `ground_truth_orchestrator.py`, `src/grill_task2/controller.py` |
| Simulation and perception | `src/mujoco_port/shim/pyrep`, `rlbench_kitchen_env.py`, `src/grill_task2/grill_task_env.py` |
| Trial randomization | `src/llm_pipeline/randomization.py`, `final_variant_setup.py` |
| Final task definitions and scoring | `evaluation/final_variants.py`, `labeled_rules.py`, `model_run_report.py` |
| External baselines | `src/baselines/{vlm_tamp,owl_tamp,inner_monologue,epog}.py` |
| Oracle | `src/llm_pipeline/oracle_trial_runner.py` (explicit `gt_oracle` identity) |

The simulator's segmentation/known instance labels are a benchmark observation interface, not a learned real-world perception reproduction. Hidden objects enter observations only after visibility permits them. The oracle supplies ground-truth planning decisions, but executes through the same simulation controller.

## Records and table authority

The latest available main-paper PDF was checked against its baseline-table LaTeX and compact trial records. Table 5 in the README preserves all ten rows and eight metrics. Its kitchen ICL results reuse zero-shot trials. The compact CSVs contain 3,450 scored trial rows across main results, baselines, ablations and available planner conditions. Their origin is historical trial-log extraction, not newly generated fixtures.

`experiments/reference_results/events/` preserves metric-bearing events for the available final main/ablation/oracle runs: planning, parallel scheduling, insertion, validation, execution outcome and trial-end events. It omits personal runtime metadata, images and verbose stdout. Compact records and events allow independent aggregation; they do not prove fresh execution reproduces historical outcomes.

Final baseline per-call exchange logs are not available locally. Their median latency values are therefore **paper transcriptions**, not recomputed statistics. Other Table 5 metrics are checked from 950 unique scored trials (kitchen records are reused across ICL rows). Some planner rows are missing or superseded; see the [model guide](models.md). Missing rows are never filled with stale results.

## Code versus historical experiments

The working implementation is newer than several reported runs. Final ROBUST-TAMP ICL records predate grill held-object executor and trial-log changes; external baseline implementations were added after those framework runs. Earlier zero-shot records also predate parser and ICL changes. Consequently, matching aggregation does not establish exact historical execution equivalence.

Final main/ablation ICL evidence uses `examples_v3`; external baselines use `examples_v2`. Historical low-level flag defaults differ from the full system. The public runner explicitly applies the evaluated settings in `configs/experiments.json`, including the coupled −WHERE change to full replanning with concurrent execution disabled. Controllers, prompts, search budgets, insertion algorithms and evaluator definitions retain their scientific behavior.

## Denominators and exclusions

Paper SR requires all final object-region relations and cooking conditions. PGC is their satisfied fraction per trial, averaged over trials. Ordering hard constraints contribute to insertion-error analysis separately. `NO_ACTIONS`, a completed plan or normal baseline termination is not itself success. Infrastructure errors are excluded and rerun at most twice; task failures count. Superseded attempts are not additional trials. Success percentages summarize trial sets and make no assertion about individual animations.

## Licensing decisions still required

The source repository does not specify a project license. Redistribution terms for the original scene assets and reproduced baseline prompt material require author confirmation; third-party code licenses are retained. See [third-party notices](../../THIRD_PARTY_NOTICES.md). This is a release candidate pending those decisions, even if technical checks pass.
