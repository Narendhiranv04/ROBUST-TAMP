# Final Running Commands

This file lists the experiment commands to run before final paper reporting, and the exact metrics to read from the resulting JSON files.

Run commands from the repository root:

```bash
cd /home/paddy/rrc/2LLM-TAMP/TAMP-PDDL/April28/TAMP-PDDL
source ../../env_setup.sh
```

The commands below assume the model server is already running and reachable through `--remote-url`. Replace model aliases after the final model list is fixed.

## Shared Settings

```bash
export REMOTE_URL="http://127.0.0.1:8000"
export N_TRIALS=10
export MAX_REPLANS=10
export OUT_ROOT="llm_pipeline/results/final_experiments"

export VARIANTS="K1 K2 K3 G1 G2 G3"

export MODEL_ALIAS="[MODEL-ALIAS]"
export MODEL_TYPE="[llm-or-vlm]"
```

Run one model at a time. Start the remote planner server with the same `MODEL_ALIAS` before running the measured trials. Later, when the final model list is chosen, record the model scale/category next to the model alias in the result spreadsheet or paper table.

Use:

- `zero_shot` for no in-context examples.
- `few_shot_shared_1` for in-context examples.

## Optional Preflight Checks

Preflight is only for prompt/backend validation. It is not part of measured experiments.

### LLM Preflight

```bash
export MODEL_TYPE="llm"

for ICL in zero_shot few_shot_shared_1; do
  python3 -m llm_pipeline.trial_runner \
    --variant K1 \
    --model "$MODEL_ALIAS" \
    --model-type "$MODEL_TYPE" \
    --icl-mode "$ICL" \
    --remote \
    --remote-url "$REMOTE_URL" \
    --headless \
    --preflight-only \
    --output-dir "$OUT_ROOT/preflight/llm/$MODEL_ALIAS/$ICL"
done
```

### VLM Preflight

```bash
export MODEL_TYPE="vlm"

for ICL in zero_shot few_shot_shared_1; do
  python3 -m llm_pipeline.trial_runner \
    --variant K1 \
    --model "$MODEL_ALIAS" \
    --model-type "$MODEL_TYPE" \
    --vision \
    --icl-mode "$ICL" \
    --remote \
    --remote-url "$REMOTE_URL" \
    --headless \
    --preflight-only \
    --output-dir "$OUT_ROOT/preflight/vlm/$MODEL_ALIAS/$ICL"
done
```

Read from each preflight `record.json`:

- `preflight_success`
- `preflight.prompt_contract_ok`
- `image_present`
- `image_metadata`
- `model_type`
- `text_only`
- `use_vision`

For VLM preflight, `image_present` should be `true`. For LLM preflight, `image_present` should be `false`.

## Main Experiment 1: LLM Without In-Context Examples

Purpose: text-only LLM planning under the visible-object relational state, without examples.

```bash
export MODEL_TYPE="llm"

for VARIANT in $VARIANTS; do
  python3 run_10_trials_and_aggregate.py \
    --pipeline llm \
    --model "$MODEL_ALIAS" \
    --model-type "$MODEL_TYPE" \
    --variant "$VARIANT" \
    --trials "$N_TRIALS" \
    --icl-mode zero_shot \
    --max-replans "$MAX_REPLANS" \
    --remote \
    --remote-url "$REMOTE_URL" \
    --headless \
    --no-goal-check \
    --output-root "$OUT_ROOT/llm_zero_shot"
done
```

Read per model and variant from:

```text
$OUT_ROOT/llm_zero_shot/<MODEL_ALIAS>/<VARIANT>/aggregate_summary.json
```

## Main Experiment 2: LLM With In-Context Examples

Purpose: text-only LLM planning with shared in-context examples.

```bash
export MODEL_TYPE="llm"

for VARIANT in $VARIANTS; do
  python3 run_10_trials_and_aggregate.py \
    --pipeline llm \
    --model "$MODEL_ALIAS" \
    --model-type "$MODEL_TYPE" \
    --variant "$VARIANT" \
    --trials "$N_TRIALS" \
    --icl-mode few_shot_shared_1 \
    --max-replans "$MAX_REPLANS" \
    --remote \
    --remote-url "$REMOTE_URL" \
    --headless \
    --no-goal-check \
    --output-root "$OUT_ROOT/llm_few_shot_shared_1"
done
```

Read per model and variant from:

```text
$OUT_ROOT/llm_few_shot_shared_1/<MODEL_ALIAS>/<VARIANT>/aggregate_summary.json
```

## Main Experiment 3: VLM Without In-Context Examples

Purpose: multimodal VLM planning with structured text plus fresh stitched camera image, without examples.

```bash
export MODEL_TYPE="vlm"

for VARIANT in $VARIANTS; do
  python3 run_10_trials_and_aggregate.py \
    --pipeline vlm \
    --model "$MODEL_ALIAS" \
    --model-type "$MODEL_TYPE" \
    --variant "$VARIANT" \
    --trials "$N_TRIALS" \
    --icl-mode zero_shot \
    --max-replans "$MAX_REPLANS" \
    --remote \
    --remote-url "$REMOTE_URL" \
    --headless \
    --no-goal-check \
    --output-root "$OUT_ROOT/vlm_zero_shot"
done
```

Read per model and variant from:

```text
$OUT_ROOT/vlm_zero_shot/<MODEL_ALIAS>/<VARIANT>/aggregate_summary.json
```

## Main Experiment 4: VLM With In-Context Examples

Purpose: multimodal VLM planning with structured text plus fresh stitched camera image and shared in-context examples.

```bash
export MODEL_TYPE="vlm"

for VARIANT in $VARIANTS; do
  python3 run_10_trials_and_aggregate.py \
    --pipeline vlm \
    --model "$MODEL_ALIAS" \
    --model-type "$MODEL_TYPE" \
    --variant "$VARIANT" \
    --trials "$N_TRIALS" \
    --icl-mode few_shot_shared_1 \
    --max-replans "$MAX_REPLANS" \
    --remote \
    --remote-url "$REMOTE_URL" \
    --headless \
    --no-goal-check \
    --output-root "$OUT_ROOT/vlm_few_shot_shared_1"
done
```

Read per model and variant from:

```text
$OUT_ROOT/vlm_few_shot_shared_1/<MODEL_ALIAS>/<VARIANT>/aggregate_summary.json
```

## Metrics To Read For Main Result Tables

From each `aggregate_summary.json`, read:

- `valid_trials`
- `episode_successes`
- `mean_task_success`
- `mean_partial_goal_completion`
- `std_partial_goal_completion`
- `mean_planner_invocations`
- `mean_total_planner_time_s`
- `mean_planner_time_per_invocation_s`
- `avg_time_s`
- `avg_replans`
- `discovery_triggered_replans`
- `failure_triggered_replans`
- `other_triggered_replans`
- `implicit_non_target_handling_rate`
- `real_failure_counts`

Use these as:

- Task success: `mean_task_success`
- Partial success: `mean_partial_goal_completion`
- Planner-call cost: `mean_total_planner_time_s`, `mean_planner_time_per_invocation_s`
- End-to-end runtime: `avg_time_s`
- Replanning behavior: `avg_replans`, `discovery_triggered_replans`, `failure_triggered_replans`, `other_triggered_replans`
- G1/G3 non-target capability: `implicit_non_target_handling_rate`
- Layered recovery and failure analysis: `real_failure_counts`

## Per-Trial Metrics To Inspect

Raw trial records are stored under:

```text
<OUTPUT_ROOT>/<MODEL_ALIAS>/<VARIANT>/trial_XXX/record.json
```

Read these fields for per-trial analysis:

- `episode_success`
- `raw_episode_success`
- `partial_goal_completion`
- `required_relation_count`
- `satisfied_relation_count`
- `missing_relation_count`
- `required_procedure_count`
- `satisfied_procedure_count`
- `missing_procedure_count`
- `planner_invocations`
- `total_planner_time_s`
- `mean_planner_time_per_invocation_s`
- `episode_time_s`
- `total_cycles`
- `total_replans`
- `discovery_triggered_replans`
- `failure_triggered_replans`
- `other_triggered_replans`
- `structured_events`
- `failure_event_counts`
- `implicit_non_target_handling_success`
- `success_validation.missing`
- `success_validation.satisfied`
- `final_object_region_map`
- `completed_actions`

## Layered Recovery Analysis

This analysis uses the same records from the four main experiments. No separate ablation run is required.

Read from each `aggregate_summary.json`:

- `real_failure_counts.total_occurrences`
- `real_failure_counts.trials_affected`

Read from each trial `record.json`:

- `structured_events`
- `failure_event_counts.by_event_type`
- `failure_event_counts.by_failure_id`
- `failure_event_counts.by_failure_layer`
- `failure_event_counts.by_stage`
- `failure_event_counts.by_source`
- `failure_event_counts.by_should_replan`

Report failures grouped by:

- `structural_failure`
- `pre_execution_failure`
- `runtime_failure`
- `post_execution_failure`
- `goal_validation_failure`

Do not count `event_type = discovery` as a failure.

## Implicit Non-Target Handling Analysis

This analysis uses G1 and G3 records from the four main experiments. No separate ablation run is required.

Read from G1/G3 `aggregate_summary.json`:

- `implicit_non_target_handling_rate`

Read from G1/G3 trial `record.json`:

- `implicit_non_target_handling_success`
- `structured_events`
- `completed_actions`
- `final_object_region_map.phone`
- `goal_text`

Interpretation:

- `implicit_non_target_handling_success = true` means the planner was not explicitly told about `phone` in the goal, discovered it after opening the grill, moved it to `table`, and the final scene confirmed `phone -> table`.
- `None` is expected for K1/K2/K3/G2.

## Aggregate-Only Recompute

If trials already exist and only the summary needs to be recomputed, run:

```bash
python3 run_10_trials_and_aggregate.py \
  --pipeline llm \
  --model "$MODEL_ALIAS" \
  --model-type "$MODEL_TYPE" \
  --variant K1 \
  --trials "$N_TRIALS" \
  --icl-mode zero_shot \
  --aggregate-only \
  --output-root "$OUT_ROOT/llm_zero_shot"
```

Change `--pipeline`, `--model`, `--model-type`, `--variant`, `--icl-mode`, and `--output-root` to match the condition being recomputed.

## Collect Final Tables

After the relevant model/condition/variant runs are complete, collect the final paper-facing tables:

```bash
python3 collect_final_results.py \
  --root "$OUT_ROOT" \
  --output-dir "$OUT_ROOT/collected"
```

This writes:

- `final_results_summary.csv` and `final_results_summary.md`
- `layered_failure_summary.csv` and `layered_failure_summary.md`
- `implicit_non_target_summary.csv` and `implicit_non_target_summary.md`

## Notes For Paper Reporting

- Do not report no-replanning as an ablation. It is unfair because the planner is not given hidden objects before discovery.
- Do not report PDDL-only as a main baseline. It is documented as a limitation because the current PDDL domains do not encode the full accessibility, discovery, and cooking semantics.
- Discovery-triggered replanning is a capability event, not a failure.
- `raw_episode_success` and subtask bucket metrics are diagnostics, not primary success metrics.
- Use `planner-call latency` wording for planner timing, not pure inference time.
