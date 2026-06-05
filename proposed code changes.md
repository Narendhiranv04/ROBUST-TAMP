# Proposed Code Changes

## Implementation Status Summary

- **Change 1: Deterministic benchmark success validators** -- implemented for primary task success. The trial runner now sets `episode_success` from deterministic variant validators.
- **Change 2: VLM multimodal backend support** -- implemented at the pipeline/protocol level. Final VLM result aggregation and result claims still require completed experiments.
- **Change 3: Grill objective and `phone` non-target object** -- implemented for the main benchmark path. G1, G2, and G3 now share the same grill goal, G1/G3 use `phone` as the hidden non-target object, and the three grill debug-execution scenes have been run successfully.
- **Change 4: Evaluation protocol and metric aggregation fixes** -- partially implemented. `partial_goal_completion` is computed and aggregated; corrected timing, replanning-trigger categorization, all-event failure aggregation, and a separate implicit non-target handling metric remain open.

## 1. Replace Benchmark Success With Deterministic Domain Validators

### Status

Implemented for primary benchmark task success.

### Previous Code State

Earlier benchmark reporting depended on action-history subtask bucket completion:

- `gt_total_subtasks`
- `completed_gt_subtasks`
- `subtask_completion_rate`
- `bucket_breakdown`
- `observed_subtasks`
- `extra_observed_subtasks`
- `episode_success`

Earlier `episode_success` was computed from:

```python
episode_success = summary["success"] and (
    completed_gt_subtasks >= gt_total_subtasks
)
```

This meant benchmark success depended on:

- `summary["success"]`, which can be influenced by the online LLM goal-completion checker when enabled.
- deterministic subtask bucket coverage computed from completed action strings.

This meant benchmark success could depend on the online pipeline status and canonical subtask-bucket coverage, rather than on deterministic final task validation.

### Implemented Target

Benchmark task success is judged by deterministic domain-specific validators, not by an LLM goal judge and not by subtask bucket coverage alone.

Primary success metric:

- **Kitchen:** final scene-state validator.
  - Compare the final object-region map against the desired goal scene.
  - Required groceries must be in `cupboard_shelf`.
  - Required mugs must be in `inside_box`.

- **Grill:** final scene-state validator plus temporal cooking predicates.
  - Meat that must be cooked must be placed inside `inside_grill`.
  - The grill must be closed while that meat is inside.
  - The grill must be reopened.
  - The same cooked meat must later be placed on `plate_top`.
  - The plate must end in `serving_area` when required.
  - In G1 and G3, the non-target `phone` must end on the table, while cooking predicates apply only to meat.

### Implemented Direction

Deterministic validators for benchmark success are present:

- `validate_kitchen_goal_from_scene(...)`
- `validate_grill_goal_from_scene_and_history(...)`

Benchmark reporting now sets:

- `episode_success` comes from the deterministic validator.
- Online LLM goal checking is not used as the benchmark success judge.

### Related Work Tracked Under Change 4

- `partial_goal_completion` is now computed from validator conditions and aggregated.
- Keep canonical subtask-bucket metrics available for debugging but exclude them from main result tables.

## 2. VLM-Related Code Changes

### Status

Implemented at the pipeline/protocol level. Final benchmark aggregation and paper claims are still pending until VLM experiments are complete.

- Implemented VLM as a multimodal planner backend in the maintained `llm_pipeline`, selected with `enable_vision=True` / `--vision`.
- VLM now receives the same structured geometric scene-state text as the LLM, including valid regions, region semantics, object-region state, lid/access state, completed actions, and structured failure context.
- VLM additionally receives a fresh stitched image composite captured from `left`, `right`, `overhead`, `wrist`, and `front` cameras at every planning and replanning checkpoint.
- Remote VLM requests send the stitched composite as a base64 payload; prompt traces and benchmark records store only image metadata, not raw image arrays.
- The previous image-only VLM baseline is no longer the implemented comparison protocol; it can be treated as a possible future ablation if needed.
- Keep the same strict parser and model-facing action interface for LLM and VLM plans.
- Use the same executor, geometric checks, deterministic success validators, and discovery-triggered replanning mechanism for LLM and VLM runs.
- Record VLM runs as `model_type="vlm"`, `text_only=False`, `use_vision=True`, and `image_present=True`.
- Benchmark support for VLM rows should use the same maintained `llm_pipeline.trial_runner --vision` path as LLM runs.
- Verify VLM result aggregation before reporting VLM-vs-LLM conclusions.

## 3. Unify the Grill Objective and Introduce an Implicitly Handled Non-Target Object

### Status

Implemented for the main benchmark path.

The final non-target object name is `phone`, not `cleaning_sponge`. Kitchen-domain `spam` remains unchanged.

### Previous Code State

The intended grill benchmark asks the model to satisfy the same cooking-and-serving objective across G1--G3 while reasoning about objects revealed inside the grill. The earlier implementation did not test this behavior cleanly:

- `evaluation/canonical_variants.py` defines a different natural-language goal for each grill variant.
- The G1 and G3 goals explicitly instruct the model to keep `spam` on the table.
- `spam` is semantically a food item and is classified as grill meat by the execution and evaluation code.
- Ground-truth sequences, final-state goals, procedural metrics, executable symbols, and tests explicitly encode `spam -> table`.

Consequently, a model can move `spam` to the table by following an explicit instruction rather than by inferring that a newly revealed non-target object does not belong in the grill.

### Implemented Target

1. Replace the grill-scene object named `spam` with a clearly non-food object that does not belong inside the grill.
   - Final object name: `phone`.
   - The object should remain physically manipulable and compatible with the existing transfer executor.
   - G1 and G3 should initially contain the object inside the closed grill.

2. Use the same natural-language task description for G1, G2, and G3.
   - The shared goal should describe only the cooking-and-serving task.
   - It must not mention `phone`, instruct the model to clear the grill, or specify where the non-target object should be placed.

3. Require the model to reason implicitly about the newly revealed object.
   - After opening the grill, discovery-triggered replanning should add `phone` to the visible-object relational state.
   - The model must infer that the object is not part of the cooking task and should not remain inside the grill.
   - The desired behavior is to relocate it to the table before continuing the cooking procedure.
   - The prompt and failure context must not classify the object as irrelevant, obstructive, or requiring relocation.

### Implemented Code and Scene Updates

- G1 and G3 scene files now contain `phone` in place of the grill-domain `spam`.
- `evaluation/canonical_variants.py` uses one shared natural-language grill goal for G1, G2, and G3.
- `phone` is registered as a visible, executable, movable grill-scene object.
- `phone` is excluded from meat aliases, meat discovery, semantic meat facts, and cooking-history predicates.
- G1 and G3 ground-truth and debug sequences move `phone -> table`.
- Deterministic grill validators require `phone -> table` for G1 and G3, while cooking predicates apply only to actual meats.
- The old `meat_to_table` bucket has been replaced by `non_target_to_table`.
- Runtime symbols, segmentation object detection, debug sequences, PDDL runner consistency, metrics, aggregation, and tests have been updated for grill `phone`.
- Kitchen-domain uses of `spam` are preserved.
- G1, G2, and G3 now use the shared G2 grill-lid replay trajectory for open-grill execution.
- The grill executor maps canonical planner regions to simulator regions where needed, including `serving_area -> plate_boundary`.

### Suggested Shared Goal

```text
Cook all raw meat using the grill and serve all cooked meat on the plate in the serving area.
```

This wording specifies the desired cooking outcome without naming the non-target object or prescribing how the grill should be cleared.

### Acceptance Criteria Status

- G1, G2, and G3 send the same natural-language goal to every LLM and VLM planner.
- Initial closed-grill observations should not expose `phone` in G1 or G3.
- Opening the grill should reveal `phone` and trigger checkpoint replanning.
- Neither the goal nor structured replanning context tells the model to move `phone`.
- A successful G1 or G3 run places `phone` on the table and completes the required cooking-and-serving procedure.
- The deterministic validator rejects runs that leave `phone` inside the grill.
- Cooking-history validation never treats `phone` as meat.
- Kitchen behavior and kitchen uses of `spam` remain unchanged.
- The hand-written debug-execution sequences for G1, G2, and G3 have been run successfully after the phone and shared-lid-replay updates.

### Remaining Cleanup

- Some older documentation and diagnostic/debug-trial text files still mention grill `spam`; these are not part of the main benchmark execution path but should be cleaned before final documentation polish.
- The separate implicit non-target handling rate remains tracked under Change 4 as an evaluation metric, not as a blocker for Change 3 execution.

## 4. Evaluation Protocol and Metric Aggregation Fixes

### Status

Partially implemented.

`partial_goal_completion` is now computed from deterministic validator conditions and included in aggregation. Remaining work for final experiments includes corrected timing, replanning-trigger categorization, all-event failure aggregation, and a separate implicit non-target handling metric.

### Current Code State

The maintained trial runner records deterministic task success, canonical subtask-bucket coverage, planning cycles, replanning cycles, per-cycle inference time, episode time, and structured failure events. However, the current aggregation path is not yet sufficient for all claims planned in the paper:

- The deterministic validators now expose a validator-aligned `partial_goal_completion` score for trials that satisfy only some required final relations or procedural predicates.
- `episode_time_s` starts inside `pipeline.run()` after trial preflight. Because the initial plan generated during preflight may be reused during execution, the reported episode time can exclude the initial model query and preflight overhead.
- Each planning cycle records `inference_time_s`, but the repeated-trial aggregator does not report cumulative inference time or mean inference time per planner invocation.
- The repeated-trial aggregator counts only the latest structured failure event from each trial rather than every surfaced event.
- `new_object_discovered` is represented using the structured event interface, but it is a successful discovery-triggered replanning event rather than an execution failure.
- Executor-local fallbacks that recover successfully are generally not recorded as structured recovery events, so their frequency cannot currently be reported reliably.
- Implicit handling of the newly revealed `phone` is included in final task validation but is not reported as a separate capability metric.
- `raw_episode_success` indicates only that the final pipeline cycle ended without an unrecovered error; it does not establish deterministic task completion.

### Required Partial Goal Completion Metric

Status: implemented for the maintained validator and aggregation path.

For every trial, compute `partial_goal_completion` from the same atomic conditions used to determine deterministic task success:

- `required_relation_count` and `satisfied_relation_count` for final object-region relations.
- `required_procedure_count` and `satisfied_procedure_count` for temporal procedural predicates.

Compute:

```text
partial_goal_completion =
    (satisfied_relation_count + satisfied_procedure_count)
    / (required_relation_count + required_procedure_count)
```

The validators should expose the individual satisfied and missing conditions so the score remains auditable. This metric must permit alternative valid plans and must not depend on matching the canonical ground-truth action sequence or subtask buckets.

Aggregate the mean and standard deviation of `partial_goal_completion` for each model--variant condition. Keep canonical subtask-bucket coverage only as a diagnostic for inspecting execution traces.

### Required Timing Metrics

Record and aggregate the following timing quantities for every trial:

- `total_inference_time_s`: the sum of `inference_time_s` across all initial-planning and replanning cycles.
- `mean_inference_time_per_invocation_s`: `total_inference_time_s / total_cycles`.
- `episode_time_s`: end-to-end wall-clock time beginning before initial planning or preflight and ending when the episode terminates.

The initial planning query must be included exactly once in both cumulative inference time and end-to-end episode time, even when its result is generated during preflight and reused by `pipeline.run()`.

Document whether reported `inference_time_s` represents server-side model inference or client-observed request latency, and use the same definition for every model condition. Record the hardware, inference precision or quantization, generation limit, decoding temperature, and prompt condition used for the final benchmark.

### Required Replanning Metrics

Continue recording:

- `total_cycles`, interpreted as the number of foundation-model planner invocations.
- `total_replans`, interpreted as the number of planning cycles after the initial planning cycle.

Additionally divide replanning events into:

- `discovery_triggered_replans`: replans caused by `new_object_discovered`.
- `failure_triggered_replans`: replans caused by structural, pre-execution, runtime, or post-execution failures.
- `other_triggered_replans`: any remaining replanning causes, if present.

These categories must be mutually exclusive and sum to `total_replans`. Object discovery must not be counted as an execution failure in reported failure distributions.

### Required Failure Aggregation

Aggregate every structured event surfaced in every planning or execution cycle, rather than only the latest event from each trial. For each event, preserve and aggregate:

- `failure_id`
- `failure_layer`
- `stage`
- `source`
- `should_replan`
- associated action, when available

Report both the total number of occurrences and the number of trials affected for each category. Structural parser rejections should be reported separately from scene-dependent pre-execution failures, runtime failures, and post-execution validation failures.

If executor-local fallbacks are to be included in the quantitative failure analysis, add explicit structured records for each fallback attempt and whether it recovered the action. Otherwise, limit the reported failure distribution to failures surfaced to the shared monitoring and replanning layer, and state this scope in the paper.

### Required Implicit Non-Target Handling Metric

Add an `implicit_non_target_handling_success` metric for G1 and G3. A trial satisfies this metric when:

- `phone` was initially hidden and later discovered;
- neither the natural-language goal nor structured replanning context explicitly instructed the planner to move it;
- the completed action history contains its relocation from the grill; and
- the final deterministic scene validator confirms that it is on the table.

Report the implicit non-target handling rate as the proportion of valid G1 and G3 trials satisfying these conditions. This metric should be reported separately from overall task success because it isolates the model's ability to infer appropriate treatment of a newly revealed non-target object.

### Reporting Contract

Use the following hierarchy in benchmark tables and analysis:

- **Primary metric:** deterministic `episode_success`.
- **Secondary metrics:** partial goal completion, planner invocations, replanning counts, cumulative inference time, mean inference time per invocation, and end-to-end episode time.
- **Capability metric:** implicit non-target handling rate for G1 and G3.
- **Failure-analysis metrics:** surfaced structured events grouped by identifier, layer, stage, source, and replanning requirement.
- **Diagnostics only:** `raw_episode_success`, `completed_gt_subtasks`, `subtask_completion_rate`, raw failure messages, detailed bucket breakdowns, observed subtasks, and extra observed subtasks.

Do not label `raw_episode_success` as task success or foreground it in the main result tables.

### Suggested Implementation Locations

- Deterministic validators in `llm_pipeline/metrics.py` already expose required and satisfied validator-condition counts and compute `partial_goal_completion`.
- Update `llm_pipeline/pipeline.py` and `llm_pipeline/trial_runner.py` to record partial goal completion, corrected timing totals, and replanning-event categories.
- Update `run_10_trials_and_aggregate.py` and `evaluation/metrics.py` to aggregate partial goal completion, cumulative inference time, all structured events, discovery-triggered replans, failure-triggered replans, and implicit non-target handling.
- Update `metric_information.md` to document the finalized definitions and distinguish primary metrics from diagnostics.
- Add focused tests for partial goal completion, timing aggregation, event counting across multiple cycles, discovery-versus-failure classification, and implicit non-target handling.

### Acceptance Criteria

- `partial_goal_completion` is computed from validator conditions and included in aggregation.
- The initial model query contributes exactly once to cumulative inference time and end-to-end episode time.
- Aggregated planner invocations equal `total_cycles`, and replanning-category counts sum to `total_replans`.
- Discovery-triggered replans are not counted as execution failures.
- Every surfaced structured event from every cycle contributes to the failure aggregates.
- Failure summaries report both total occurrences and trials affected.
- G1 and G3 records contain a reproducible implicit non-target handling result.
- Main benchmark success is determined only by the deterministic variant validator.
- Canonical subtask-bucket metrics remain diagnostic-only and are excluded from main result tables.
- `raw_episode_success` remains available for debugging but is not reported as task-completion success.
