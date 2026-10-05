# Reproducing the experiments

All client commands below run from the release root in the simulation environment. Start the selected model on the GPU server first; use a localhost tunnel or set `--endpoint` to your configured server. Each output path must be new. To continue an interrupted batch, repeat the exact command with `--resume`.

## Main evaluation

```sh
python -m robust_tamp run --method full --seeds 0-9 --jobs 6 --out runs/main-zero-shot
python -m robust_tamp run --method full --icl paper --variants FINAL.G0 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.G1-n1 --seeds 0-9 --jobs 6 --out runs/main-icl-grill
```

The first command covers all 14 variants. ICL reaches only grill prompts; the final ICL comparison combines the zero-shot kitchen trials with the five ICL grill variants. `--icl paper` selects ROBUST-TAMP's final three-example `examples_v3` prompt. Kitchen prompts remain zero-shot. Do not rerun kitchen tasks and silently substitute a different set of kitchen trials.

## Component ablations

Kitchen: K1–K4, zero-shot. Grill: G1–G3, ICL. Run these commands for each method in the loop:

```sh
for method in no_memory no_if no_where fixed_front fixed_end no_when; do
  python -m robust_tamp run --method "$method" --variants FINAL.K1 FINAL.K2 FINAL.K3 FINAL.K4 --seeds 0-9 --jobs 6 --out "runs/ablations/$method-kitchen"
  python -m robust_tamp run --method "$method" --icl paper --variants FINAL.G1 FINAL.G2 FINAL.G3 --seeds 0-9 --jobs 6 --out "runs/ablations/$method-grill"
done
```

| Method | Evaluated change from full system |
|---|---|
| `no_memory` | Current observation only |
| `no_if` | Correction on every newly visible object |
| `no_where` | Regenerate remaining plan **and suspend concurrent execution** |
| `fixed_front` | Insert every corrective block at the front |
| `fixed_end` | Insert every corrective block at the end |
| `no_when` | Suspend execution during inference |

The configurations live in `configs/experiments.json`; shared flags also fix agent termination, prompt v2, pose jitter, gripper-state confirmation and corrective hints off. The low-level `PipelineFlags()` defaults are historical and are not the full system. The release runner always supplies explicit settings.

For the LLM-planner ablation, serve `qwen3-8b` and repeat the full-system commands on the same seven core variants with `--model qwen3-8b`. It is a model/modality condition, not an external baseline.

## External baselines

```sh
for method in vlm_tamp owl_tamp inner_monologue epog; do
  python -m robust_tamp run --method "$method" --seeds 0-9 --jobs 6 --out "runs/baselines/$method-zero-shot"
  python -m robust_tamp run --method "$method" --icl paper --variants FINAL.G0 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.G1-n1 --seeds 0-9 --jobs 6 --out "runs/baselines/$method-icl-grill"
done
```

Baseline ICL uses the recorded two-example `examples_v2` adaptations in the methods' own interfaces. ROBUST-TAMP uses `examples_v3`. Baseline algorithms, budgets and prompt differences are described in [baselines](baselines.md). `baselines/llm_planner.py` contains shared step-loop machinery and an additional historical comparison; it is not a fifth baseline in Table 5.

For a GPU-free baseline plumbing check, add `--mock` to one baseline trial and use a separate `runs/validation-*` output. It uses oracle answers and cannot establish model performance.

## Model and modality comparisons

List the pinned profiles with `python -m robust_tamp profiles`. Start one desired profile on the GPU server, then:

```sh
python -m robust_tamp run --method full --model qwen3-8b --seeds 0-9 --jobs 6 --out runs/models/qwen3-8b
python -m robust_tamp run --method full --model qwen3-8b --icl paper --variants FINAL.G0 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.G1-n1 --seeds 0-9 --jobs 6 --out runs/models/qwen3-8b-icl
```

Replace the profile in both the server and client commands for each row. The client automatically selects text-only or visual input and the profile's reasoning/sampling settings. FP8 scale-study profiles explicitly end in `-fp8`; they use the published FP8 checkpoints, not a silent conversion of the BF16 weights. See [models](models.md) for hardware and missing records.

## Budgets, seeds and output

The reported main runs use six concurrent trials, a 14,400-second wall limit, 1,800-second request timeout, 24,576 output tokens and ten replans after the initial call. Baseline-specific nested/search budgets are retained. CPU motion planning also has wall-clock limits. Python, NumPy, trial pose jitter, IK/RRT and baseline shuffling receive the trial seed. GPU sampling and time-bounded planning can still vary across runs, scheduling, software and hardware.

Each batch writes `effective_config.json`, a server identity response, and `batch_status.json`. Each trial writes its effective configuration, `record.json`, `trial_log.jsonl`, prompt/exchange records, execution status and stdout. Every trial gets a separate working directory to prevent PDDLStream `temp/output.sas` collisions. Run termination (`NO_ACTIONS`, plan exhausted, budget exhausted) is distinct from evaluator success.

Infrastructure failures are archived as `seed_XX.infra_attemptN` and rerun at most twice. They are excluded from scored denominators. Task failures are kept; rerunning them until success would bias the result. Historical runs superseded after code fixes remain private evidence rather than extra scored trials. A smoke run is not a full reproduction.

## Aggregate fresh runs and preserved records

```sh
python -m robust_tamp aggregate runs/main-zero-shot --out runs/main-zero-shot-report
python -m robust_tamp tables --extended --out runs/paper-tables
python scripts/summarize_trial_results.py reference_results/trial_level/ablations.csv
python scripts/summarize_trial_results.py reference_results/trial_level/planner_selection.csv
```

Fresh reports expose missing/infra trials. Do not interpret an incomplete matrix as a full paper row. The compact CSVs are experimental records, not test fixtures. Table 5 aggregation checks all 140 expected variant/seed keys per row and rejects duplicates or excluded trials. PGC is reconstructed from condition counts rather than rounded CSV fractions. Ordering hard-constraint violations are reported separately: they are insertion errors, not extra goal relations in the paper's SR/PGC denominator.

The `--extended` command also recomputes Tables 2 and 4, including idle time, urgency and insertion analysis, from the preserved event records. It reuses the historical metric functions while selecting the final ICL sources. See [evidence](evidence.md).

## Simulation video

The retained recorder executes the oracle plan; it is not a video of the model planner:

```sh
SIM_BACKEND=mujoco MUJOCO_GL=egl python mujoco_port/tools/record_variant_video.py FINAL.G0 --out runs/oracle-video --size 1280x720 --codec libx264 --seed 0
```

Output is `runs/oracle-video/FINAL.G0/`, with video, first/last frames and trial logs. Choose a fresh output path. The README animations explain the framework and correction placement; they are not evidence of trial success rates.
