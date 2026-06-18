# Chat Handoff Context - 2026-06-18

This file is a compact handoff for continuing the TAMP/LLM/VLM benchmark work in a new chat.

## Working Directory

Local repo:

```text
/home/boreddog/Documents/RRC/Long_Horizon/Ending_Pipeline
```

Main remote inference server recently used:

```text
GVLab: nav@10.4.25.26
Remote repo path: /ssd_scratch/long-horizon/TAMP-PDDL-2026-06-09
HF cache: /ssd_scratch/long-horizon/huggingface
```

The user is running simulation locally and using remote inference servers over forwarded/local ports.

## Current Benchmark Goal

The immediate goal is to finish **zero-shot** tests for:

```text
Qwen/Qwen3-32B
LLM
bnb8 quantization
thinking mode enabled
remote server on http://127.0.0.1:8032
10 trials per variant across K1 K2 K3 G1 G2 G3
```

Important correction from the user:

- They want **no ICL / zero-shot**, not ICL.
- They wanted **10 trials per variant**, not 6.
- Partial progress reported by user: **K1-K3 have 6 trials each**, **G1 has 4 trials**, and **G2/G3 still need full 10** for the current Qwen3-32B bnb8 zero-shot batch.

Output root for current 32B bnb8 zero-shot:

```text
llm_pipeline/results/final_experiments/llm_zero_shot_bnb8/Qwen/Qwen3-32B/
```

## Run Remaining Qwen3-32B bnb8 Zero-Shot Trials

Use this local command after the 32B server is running on port `8032`:

```bash
export LLM_REQUEST_TIMEOUT_S=3600
export LLM_HEALTH_TIMEOUT_S=120

MODEL="Qwen/Qwen3-32B"
REMOTE_URL="http://127.0.0.1:8032"
ROOT="llm_pipeline/results/final_experiments/llm_zero_shot_bnb8"

run_trial () {
  VARIANT="$1"
  TRIAL="$2"

  python -m llm_pipeline.trial_runner \
    --variant "$VARIANT" \
    --model "$MODEL" \
    --model-type llm \
    --quantization bnb8 \
    --icl-mode zero_shot \
    --remote \
    --remote-url "$REMOTE_URL" \
    --max-replans 10 \
    --planner-max-new-tokens 8192 \
    --goal-check-max-new-tokens 128 \
    --goal-check \
    --trial-index "$TRIAL" \
    --headless \
    --output-dir "$ROOT/$MODEL/$VARIANT/trial_$(printf "%03d" "$TRIAL")"
}

for VARIANT in K1 K2 K3; do
  for TRIAL in 7 8 9 10; do
    run_trial "$VARIANT" "$TRIAL"
  done
done

for TRIAL in 5 6 7 8 9 10; do
  run_trial G1 "$TRIAL"
done

for VARIANT in G2 G3; do
  for TRIAL in 1 2 3 4 5 6 7 8 9 10; do
    run_trial "$VARIANT" "$TRIAL"
  done
done

for VARIANT in K1 K2 K3 G1 G2 G3; do
  python run_10_trials_and_aggregate.py \
    --pipeline llm \
    --model "$MODEL" \
    --model-type llm \
    --quantization bnb8 \
    --variant "$VARIANT" \
    --trials 10 \
    --icl-mode zero_shot \
    --remote \
    --remote-url "$REMOTE_URL" \
    --max-replans 10 \
    --planner-max-new-tokens 8192 \
    --goal-check-max-new-tokens 128 \
    --goal-check \
    --headless \
    --aggregate-only \
    --output-root "$ROOT"
done
```

## Current Qwen3-32B bnb8 Server Setup

Server command on GVLab:

```bash
cd /ssd_scratch/long-horizon/TAMP-PDDL-2026-06-09
source .venv_qwen/bin/activate

export HF_HOME=/ssd_scratch/long-horizon/huggingface
export HF_HUB_CACHE=/ssd_scratch/long-horizon/huggingface/hub
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export CUDA_VISIBLE_DEVICES=0,1
export QWEN_THINKING_MODE=default
unset QWEN_NO_THINK_PROMPT
unset LD_LIBRARY_PATH

python -m llm_pipeline.server \
  --model Qwen/Qwen3-32B \
  --model-type llm \
  --host 127.0.0.1 \
  --port 8032 \
  --device cuda \
  --quantization bnb8
```

Health check:

```bash
curl http://127.0.0.1:8032/health
```

For bnb8, do **not** install/use the `kernels` package in this environment. It caused:

```text
StrictDataclassFieldValidationError: Validation error for field 'import_name'
TypeError: Unsupported type for field 'import_name': str | None
```

The fix was:

```bash
uv pip uninstall -y kernels kernels-data
```

Keep `kernels` only in a separate FP8-specific environment.

Earlier CUDA/NCCL issue was:

```text
libtorch_cuda.so: undefined symbol: ncclCommResume
```

Diagnosis: venv NCCL mismatch, not system `LD_LIBRARY_PATH`. Reinstalling the full PyTorch CUDA stack together fixed imports. Always start with:

```bash
unset LD_LIBRARY_PATH
```

## Important Code Changes Already Made

The working tree is dirty. Do not casually revert. Current changes include both earlier quantization/server work and recent executor bug fixes.

### 1. Explicit Quantization Modes

New file:

```text
llm_pipeline/quantization.py
```

Supports:

```text
none
bnb8
bnb4
```

Wired into:

```text
llm_pipeline/planner.py
llm_pipeline/vlm_planner.py
vlm_pipeline/llm_planner.py
vlm_pipeline/vlm_planner.py
llm_pipeline/server.py
vlm_pipeline/vlm_server.py
vlm_pipeline/planner_factory.py
llm_pipeline/pipeline.py
llm_pipeline/trial_runner.py
run_10_trials_and_aggregate.py
llm_pipeline/benchmark_runner.py
llm_pipeline/client.py
```

Server and trial flags:

```bash
--quantization none
--quantization bnb8
--quantization bnb4
```

Old `--no-4bit` still exists but should be considered deprecated. Do not combine it with `--quantization`.

### 2. Remote Parser Now Receives Runtime Symbols

Bug found: in remote mode the server parsed model output using its own default kitchen parser. For grill variants, the local prompt had `plate`, `chicken`, `grill_lid`, etc., but the server rejected `pick(plate)`.

Fix:

- `llm_pipeline/client.py` now sends:

```json
valid_actions
valid_objects
valid_regions
```

- `llm_pipeline/server.py` applies those to a `StrictActionParser` before parsing.
- `llm_pipeline/tests/test_remote_server.py` was added.
- `llm_pipeline/tests/test_remote_client.py` has a runtime-symbol regression test.

If a new chat sees `Unknown or unpickable object 'plate'` from a remote G variant, it likely means the remote server was not rsynced/restarted with this code.

### 3. Text LLM Parse Failures Now Request Replanning

In `llm_pipeline/planner.py`, `_build_parse_failure(...)` was changed from:

```python
should_replan=False
```

to:

```python
should_replan=True
```

Reason: parser/format failures should allow another LLM attempt rather than hard-stopping before execution.

### 4. Executor Stale Held-Object Bug Fixed

Recent user log showed:

- `pick(mug3)` from cupboard produced `HeightTrace ... grasped=[]`
- but the symbolic state still became `gripper: holding=mug3`
- then replan generated `place(mug3, inside_box)`
- executor later called it "wedged in gripper", but it was not physically wedged. The root issue was stale held-state after failed pick confirmation.

Patch made in `llm_pipeline/executor.py`:

- If bundled transfer postcheck returns `grasp_failed` after a `pick`, restore previous held state and remove the failed pick from `completed`.
- Direct executor comment clarified the same behavior.

Validation after this patch:

```text
python -m py_compile llm_pipeline/executor.py
python -m pytest llm_pipeline/tests/test_executor.py llm_pipeline/tests/test_pipeline.py llm_pipeline/tests/test_failure_logic.py -q
50 passed
```

If the pick fails now, the next replan should say gripper is empty and retry the pick, not place the object.

## Important Testing/Validation Already Run

After parser/quantization changes:

```text
python -m py_compile ...
pytest llm_pipeline/tests/test_pipeline.py llm_pipeline/tests/test_trial_runner.py llm_pipeline/tests/test_remote_client.py llm_pipeline/tests/test_remote_server.py llm_pipeline/tests/test_vlm_contract.py -q
47 passed
```

After executor stale-held fix:

```text
pytest llm_pipeline/tests/test_executor.py llm_pipeline/tests/test_pipeline.py llm_pipeline/tests/test_failure_logic.py -q
50 passed
```

## Rsync Commands

For remote inference server code on GVLab, sync the server-relevant files:

```bash
rsync -avz --relative \
  llm_pipeline/quantization.py \
  llm_pipeline/client.py \
  llm_pipeline/pipeline.py \
  llm_pipeline/planner.py \
  llm_pipeline/server.py \
  llm_pipeline/trial_runner.py \
  llm_pipeline/vlm_planner.py \
  llm_pipeline/strict_parser.py \
  llm_pipeline/executable_symbols.py \
  llm_pipeline/region_aliases.py \
  vlm_pipeline/llm_planner.py \
  vlm_pipeline/planner_factory.py \
  vlm_pipeline/vlm_planner.py \
  vlm_pipeline/vlm_server.py \
  run_10_trials_and_aggregate.py \
  nav@10.4.25.26:/ssd_scratch/long-horizon/TAMP-PDDL-2026-06-09/
```

The recent executor fix is local simulator-side. If simulation is local, it does not need to be synced to the inference server. If simulation is also run remotely, include:

```bash
rsync -avz --relative \
  llm_pipeline/executor.py \
  nav@10.4.25.26:/ssd_scratch/long-horizon/TAMP-PDDL-2026-06-09/
```

## Prompt/Reasoning Policy Context

The user cares about testing whether the LLM can reason on its own. Avoid spoonfeeding highly specific deterministic failure details.

Past decisions:

- Goal-check failure context was made more agnostic: "goal not fully satisfied" rather than listing exact object-region mismatches.
- Grill prompt/user context includes that meat becomes cooked after correct grill sequence, without renaming objects to cooked/raw.
- Any meats already inside grill at start are considered cooked.
- Multiple meats can be cooked at once.
- Phone in grill is an implicit-reasoning benchmark; avoid explicitly telling the LLM to remove the phone if phone is the only mismatch.

## Prompt/Parser Notes

Qwen thinking/no-thinking:

- Thinking mode:

```bash
export QWEN_THINKING_MODE=default
unset QWEN_NO_THINK_PROMPT
```

- No-think mode:

```bash
export QWEN_NO_THINK_PROMPT=1
# or QWEN_THINKING_MODE=off
```

The code injects `/no_think` when no-think mode is active. Some Qwen3 models may still output empty `<think></think>` blocks; parser strips think blocks for parsing, but raw output should still be stored/shown.

## Model/Experiment Plan Context

Models discussed/used:

- `Qwen/Qwen3-8B`
- `Qwen/Qwen3-VL-8B-Thinking`
- `Qwen/Qwen3-32B`
- `Qwen/Qwen3-VL-32B-Thinking`
- 72B models were discussed for bnb4 or AWQ, but 32B bnb8 is the current immediate focus.

Quantization plan:

- 8B: no quantization
- 32B: bitsandbytes 8-bit (`bnb8`)
- 70/72B: bitsandbytes 4-bit (`bnb4`) or AWQ depending model/env

Downloaded/current relevant repos:

```text
Qwen/Qwen3-32B
Qwen/Qwen3-VL-32B-Thinking
```

For normal HF repos, do not look for separate 8-bit repos; load with `--quantization bnb8`.

## Current Result Folders

Known aggregate summaries in local repo include:

```text
llm_pipeline/results/final_experiments/llm_icl/Qwen/Qwen3-8B/{K1,K2,K3,G1,G2,G3}/aggregate_summary.json
llm_pipeline/results/final_experiments/llm_zero_shot/Qwen/Qwen3-8B/{K1,K2,K3,G1,G2,G3}/aggregate_summary.json
llm_pipeline/results/final_experiments/llm_zero_shot/Qwen/Qwen3-32B-FP8/{K1,K2,K3,G1,G2,G3}/aggregate_summary.json
llm_pipeline/results/final_experiments/llm_zero_shot_bnb8/Qwen/Qwen3-32B/{K1,K2,K3,G1}/aggregate_summary.json
```

`llm_zero_shot_bnb8` is incomplete as of this handoff.

There is also:

```text
final_experiments_20260616_111826.tar.gz
```

## Current Dirty Worktree Snapshot

As of this handoff, `git status --short` showed:

```text
 M MODEL_SERVER_REQUIREMENTS.md
 m RLBench
 M SERVER_AND_EVAL_RUNBOOK.md
 M llm_pipeline/LLM_TEST_COMMANDS.md
 M llm_pipeline/benchmark_runner.py
 M llm_pipeline/client.py
 M llm_pipeline/executor.py
 M llm_pipeline/pipeline.py
 M llm_pipeline/planner.py
 M llm_pipeline/server.py
 M llm_pipeline/tests/test_pipeline.py
 M llm_pipeline/tests/test_remote_client.py
 M llm_pipeline/trial_runner.py
 M llm_pipeline/vlm_planner.py
 m pddlstream
 M run_10_trials_and_aggregate.py
 M vlm_pipeline/llm_planner.py
 M vlm_pipeline/planner_factory.py
 M vlm_pipeline/vlm_planner.py
 M vlm_pipeline/vlm_server.py
?? llm_pipeline/quantization.py
?? llm_pipeline/results/final_experiments/llm_icl/
?? llm_pipeline/results/final_experiments/llm_zero_shot_bnb8/
?? llm_pipeline/tests/test_remote_server.py
```

Submodules `RLBench` and `pddlstream` are dirty but were not intentionally edited by the assistant.

## Known Pitfalls

1. If remote G variants reject `plate` or `grill_lid`, server likely lacks runtime-symbol parser patch or was not restarted.
2. If Qwen3-32B bnb8 fails with `import_name` dataclass validation, uninstall `kernels`/`kernels-data`.
3. If Torch import fails with `ncclCommResume`, repair PyTorch/NCCL stack in the env and `unset LD_LIBRARY_PATH`.
4. If logs say object is "wedged" after a failed pick, check whether stale `held_object` state is involved. Executor has now been patched locally.
5. Batch runner `run_10_trials_and_aggregate.py` takes one variant at a time. Use a shell loop for all six variants.
6. Always keep zero-shot and ICL output roots separate:

```text
llm_zero_shot...
llm_icl...
```

## User Preferences / Style

- User wants copy-pasteable commands.
- User often runs commands on fish shell on cstar, but GVLab examples above are bash.
- User prefers debugging with GUI for smoke tests and headless for batch.
- User wants raw LLM output visible during smoke tests.
- User is careful about benchmark fairness and does not want overly specific spoonfeeding in prompts/replan feedback.

