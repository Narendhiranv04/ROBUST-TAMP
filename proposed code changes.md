# Proposed Code Changes

## Implementation Status Summary

- **Change 1: Deterministic benchmark success validators** -- implemented for primary task success. The trial runner now sets `episode_success` from deterministic variant validators.
- **Change 2: VLM multimodal backend support** -- implemented at the pipeline/protocol level. Final VLM result aggregation and result claims still require completed experiments.
- **Change 3: Grill objective and `phone` non-target object** -- implemented for the main benchmark path. G1, G2, and G3 now share the same grill goal, G1/G3 use `phone` as the hidden non-target object, and the three grill debug-execution scenes have been run successfully.
- **Change 4: Evaluation protocol and metric aggregation fixes** -- implemented for the maintained code path. Measured trials no longer run preflight, validator relation/procedure counts are exposed, planner-call timing is recorded, structured events and replan trigger categories are aggregated, discovery is excluded from real-failure tables, and G1/G3 implicit phone handling is reported separately.

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

Implemented for the maintained benchmark code path.

`partial_goal_completion` is computed from deterministic validator conditions and included in aggregation. Measured trials call `pipeline.run(...)` directly instead of first running preflight. Top-level trial records now include planner-call timing, relation/procedure condition counts, structured events, replanning trigger counts, real-failure summaries, and the G1/G3 implicit non-target handling metric.

### Current Code State

The maintained trial runner records deterministic task success, canonical subtask-bucket diagnostics, planning cycles, replanning cycles, planner-call time, episode time, and structured events.

- Deterministic validators expose `partial_goal_completion` and separate relation/procedure counts.
- Normal measured trials do not call `pipeline.preflight(...)`; `--preflight-only` remains available for prompt/backend checks.
- `episode_time_s` starts inside `pipeline.run()` before the first measured planner call.
- Top-level records include `planner_invocations`, `total_planner_time_s`, and `mean_planner_time_per_invocation_s`.
- `run_10_trials_and_aggregate.py`, `evaluation.metrics`, and `llm_pipeline/aggregate.py` now aggregate partial goal completion, planner timing, replanning trigger counts, implicit non-target handling, and real failure counts.
- `new_object_discovered` is represented as a discovery-triggered replan event, not as an execution failure.
- Executor-local fallbacks that recover successfully are still not recorded as quantitative failure/recovery events; reported failure distributions are limited to events surfaced to the shared monitoring and replanning layer.
- `raw_episode_success` remains diagnostic and does not establish deterministic task completion.

### Preflight Policy for Final Experiments

Use preflight as a separate debug and prompt-contract check, not as part of measured benchmark trials.

For final measured trials:

- Do not call `pipeline.preflight(...)` before `pipeline.run(...)`.
- Let the measured run build the initial scene state, prompt the model, parse the plan, execute, and replan from a single execution path.
- Keep `--preflight-only` or an equivalent mode for inspecting prompt traces, VLM image presence, parser behavior, and remote model connectivity before running experiments.

This avoids counting the first model invocation zero times or twice, and it prevents a cached preflight plan from being based on a scene state captured before the execution run resets and settles the simulator.

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

The implementation also records the equivalent flat validator-condition counts:

```text
partial_goal_completion =
    satisfied_condition_count / required_condition_count
```

For grill tasks, each required cooking sequence counts as one procedural condition per meat, not as multiple substeps. This prevents cooking-heavy variants from dominating the partial score while still checking the full ordered sequence internally.

Aggregate the mean and standard deviation of `partial_goal_completion` for each model--variant condition. Keep canonical subtask-bucket coverage only as a diagnostic for inspecting execution traces.

### Required Timing Metrics

Record and aggregate the following timing quantities for every measured trial:

- `planner_invocations`: number of LLM/VLM planner calls made during the measured run. This equals `total_cycles` in the maintained pipeline because each cycle corresponds to one planner call.
- `total_planner_time_s`: sum of planner-call latency across all initial-planning and replanning cycles.
- `mean_planner_time_per_invocation_s`: `total_planner_time_s / planner_invocations`.
- `episode_time_s`: end-to-end wall-clock time beginning immediately before the first measured planning call and ending after final execution and deterministic validation.
For final experiments, do not reuse a cached preflight plan. The initial planning query should occur inside the measured run and contribute exactly once to both `planner_invocations` and `total_planner_time_s`.

Report planner time as planner-call latency under the current local/remote planner contract. Do not call it pure model inference time unless the measurement is changed to server-side generation only. A separate execution-only timer is not currently recorded; use `episode_time_s` together with planner timing for total measured runtime analysis.

Record the hardware, inference precision or quantization, generation limit, decoding temperature, model server location, and prompt condition used for the final benchmark.

### Required Replanning Metrics

Continue recording:

- `total_cycles`, interpreted as the number of measured foundation-model planning cycles.
- `total_replans`, interpreted as the number of planning cycles after the initial planning cycle.

Additionally divide replanning events into:

- `discovery_triggered_replans`: replans caused by `new_object_discovered`.
- `failure_triggered_replans`: replans caused by structural, pre-execution, runtime, or post-execution failures.
- `other_triggered_replans`: any remaining replanning causes, if present.

These categories must be mutually exclusive and sum to `total_replans`. Object discovery must not be counted as an execution failure in reported failure distributions.

### Required Structured Event Recording

For each trial, record every surfaced structured event from every planning and execution cycle in a top-level list:

```text
structured_events: [...]
```

Each event should preserve:

- `event_id`
- `event_type`
- `cycle_number`
- `is_failure`
- `is_replan_trigger`
- `failure_id`
- `failure_layer`
- `stage`
- `source`
- `should_replan`
- associated action, when available
- `message`
- auditable evidence

Use the following event-type definitions:

- `discovery`: a previously hidden task object becomes visible and triggers checkpoint replanning. This is not a failure.
- `structural_failure`: parser or strict-interface rejection before execution.
- `pre_execution_failure`: scene-dependent applicability failure before physical execution.
- `runtime_failure`: unrecovered executor, geometry, PDDL, or motion failure during physical execution.
- `post_execution_failure`: monitoring or validation failure after physical execution.
- `goal_validation_failure`: deterministic final task validator fails after execution terminates.

For `new_object_discovered`, record:

```text
event_type = discovery
is_failure = false
is_replan_trigger = true
```

For parser, executor, geometry, and postcheck failures, record:

```text
is_failure = true
is_replan_trigger = should_replan
```

### Required Failure Aggregation

Aggregate every real failure event surfaced in every planning or execution cycle, rather than only the latest event from each trial. Exclude `event_type = discovery` from failure tables.

Report both:

- total occurrences for each category;
- number of trials affected for each category.

Group failure summaries by:

- `event_type`
- `failure_id`
- `failure_layer`
- `stage`
- `source`
- `should_replan`

Structural parser rejections should be reported separately from scene-dependent pre-execution failures, runtime failures, post-execution validation failures, and final deterministic goal-validation failures.

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
- **Secondary metrics:** partial goal completion, planner invocations, replanning counts, total planner time, mean planner time per invocation, and end-to-end episode time.
- **Capability metric:** implicit non-target handling rate for G1 and G3.
- **Replanning-analysis metrics:** discovery-triggered, failure-triggered, and other-triggered replans.
- **Failure-analysis metrics:** real failure events grouped by event type, identifier, layer, stage, source, and replanning requirement.
- **Diagnostics only:** `raw_episode_success`, `completed_gt_subtasks`, `subtask_completion_rate`, raw failure messages, detailed bucket breakdowns, observed subtasks, and extra observed subtasks.

Do not label `raw_episode_success` as task success or foreground it in the main result tables.

### Implementation Locations

- `llm_pipeline/metrics.py` exposes required and satisfied relation/procedure counts, computes `partial_goal_completion`, builds structured events, summarizes real failures, and computes G1/G3 implicit non-target handling.
- `llm_pipeline/trial_runner.py` keeps preflight as a separate `--preflight-only` path and records structured metric fields for measured runs.
- `llm_pipeline/pipeline.py` records top-level planner timing totals from cycle planner latencies.
- `run_10_trials_and_aggregate.py`, `llm_pipeline/aggregate.py`, and `evaluation/metrics.py` aggregate partial goal completion, planner timing, structured events, discovery-triggered replans, failure-triggered replans, and implicit non-target handling.
- `metric_information.md` documents the finalized definitions and distinguishes primary metrics from diagnostics.
- Focused tests cover no-preflight measured runs, partial goal completion relation/procedure counts, planner timing aggregation, event counting across multiple cycles, discovery-versus-failure classification, aggregation, and implicit non-target handling.

### Acceptance Criteria

- Measured benchmark trials do not call preflight before execution; preflight remains available only for prompt/backend debugging and `--preflight-only` inspection.
- `partial_goal_completion` is computed from validator conditions and included in aggregation.
- Relation and procedure condition counts are exposed separately while preserving the validator-aligned partial completion ratio.
- The initial model query contributes exactly once to `planner_invocations`, `total_planner_time_s`, and end-to-end `episode_time_s`.
- Aggregated planner invocations equal `total_cycles`, and replanning-category counts sum to `total_replans`.
- Discovery-triggered replans are not counted as execution failures.
- Every surfaced structured event from every cycle is recorded in trial records.
- Every real failure event contributes to failure aggregates; discovery events contribute only to replanning aggregates.
- Failure summaries report both total occurrences and trials affected.
- G1 and G3 records contain a reproducible implicit non-target handling result.
- Main benchmark success is determined only by the deterministic variant validator.
- Canonical subtask-bucket metrics remain diagnostic-only and are excluded from main result tables.
- `raw_episode_success` remains available for debugging but is not reported as task-completion success.
