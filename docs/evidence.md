# Scientific scope and evidence

This release supports the simulated experiments for *Deciding If, When, and Where to Replan for Robust Manipulation*. Fourteen final MuJoCo variants are used; legacy variants remain for controller regression tests. Real-robot operation is outside this release.

## Implementation map

| Paper component | Implementation |
|---|---|
| Planning and recovery loop | `llm_pipeline/pipeline.py` |
| Observation memory and occlusion | `llm_pipeline/memory.py`, `segmentation_adapter.py` |
| IF discovery/relevance/overlap decision | `llm_pipeline/if_rule.py`, `evaluation/labeled_rules.py` |
| WHEN independence and dependency propagation | `llm_pipeline/parallel.py` |
| WHERE validation and insertion | `llm_pipeline/corrective.py`, `strict_parser.py`, pipeline merge logic |
| Initial/corrective prompts and ICL | `llm_pipeline/prompt_v2.py`, `icl_examples.py` |
| Controllers and pre-action checks | `llm_pipeline/executor.py`, `ground_truth_orchestrator.py`, `grill_task2/controller.py` |
| Simulation and perception | `mujoco_port/shim/pyrep`, `rlbench_kitchen_env.py`, `grill_task2/grill_task_env.py` |
| Trial randomization | `llm_pipeline/randomization.py`, `final_variant_setup.py` |
| Final task definitions and scoring | `evaluation/final_variants.py`, `labeled_rules.py`, `model_run_report.py` |
| External baselines | `baselines/{vlm_tamp,owl_tamp,inner_monologue,epog}.py` |
| Oracle | `llm_pipeline/oracle_trial_runner.py` (explicit `gt_oracle` identity) |

The simulator's segmentation/known instance labels are a benchmark observation interface, not a learned real-world perception reproduction. Hidden objects enter observations only after visibility permits them. The oracle supplies ground-truth planning decisions, but executes through the same simulation controller.

## Records and table authority

The latest available main-paper PDF was checked against its baseline-table LaTeX and compact trial records. Table 5 in the README preserves all ten rows and eight metrics. Its kitchen ICL results reuse zero-shot trials. The compact CSVs contain 3,450 scored trial rows across main results, baselines, ablations and available planner conditions. Their origin is historical trial-log extraction, not newly generated fixtures.

`reference_results/events/` preserves metric-bearing events for the available final main/ablation/oracle runs: planning, parallel scheduling, insertion, validation, execution outcome and trial-end events. It omits personal runtime metadata, images and verbose stdout. File-level source hashes and exact selection history are retained in the private audit, not the anonymous archive. Compact records and events allow independent aggregation; they do not prove fresh execution reproduces historical outcomes.

Final baseline per-call exchange logs are not available locally. Their median latency values are therefore **paper transcriptions**, not recomputed statistics. Other Table 5 metrics are checked from 950 unique scored trials (kitchen records are reused across ICL rows). Some planner rows are missing or superseded; see the CSV README and model guide. Missing rows are never filled with stale results.

## Code versus historical experiments

The release begins from working files, including uncommitted/untracked changes, not merely the last commit. Final ROBUST-TAMP ICL runs predate the working snapshot's grill held-object executor and trial-log changes; the external baseline implementations were also added after that framework run. Earlier zero-shot runs also predate parser and ICL changes. Historical server scripts and old table scripts use superseded table numbers and in places `examples_v2`; the final main/ablation ICL evidence uses `examples_v3`. The final baseline adaptations still use `examples_v2`. Exact historical code identity and differences remain in the private audit.

Packaging changes provide explicit configuration, path portability, source-content identity, immutable run attempts and consistent commands. They do not alter corrective prompts, primitive controllers, search budgets, insertion algorithms or evaluator definitions. The active grill file formerly named `… copy.py` was renamed to `controller.py`; all dynamic consumers were updated. Its numerical/controller content is unchanged. Scene meshes/textures are shared by content hash; all 24 compiled models retained identical numerical arrays. The low-level historical flags remain intact, while the new runner supplies the evaluated full-system settings explicitly.

## Denominators and exclusions

Paper SR requires all final object-region relations and cooking conditions. PGC is their satisfied fraction per trial, averaged over trials. Ordering hard constraints contribute to insertion-error analysis separately. `NO_ACTIONS`, a completed plan or normal baseline termination is not itself success. Infrastructure errors are excluded and rerun at most twice; task failures count. Superseded attempts are not additional trials. Success percentages summarize trial sets and make no assertion about individual animations.

## Licensing decisions still required

The source repository does not specify a project license. None has been invented. Redistribution terms for the original scene assets and reproduced baseline prompt material require author confirmation; third-party code licenses are retained. See `THIRD_PARTY_NOTICES.md`. This is a release candidate pending those decisions, even if technical checks pass.
