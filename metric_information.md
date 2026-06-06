# Metric Information

This file describes the benchmark metrics recorded by the maintained `llm_pipeline.trial_runner` path. The purpose is to keep the code, result tables, and paper wording aligned.

## Metric Hierarchy

The metrics should be interpreted in this order:

1. `episode_success`: primary deterministic task success.
2. `partial_goal_completion`: partial deterministic goal satisfaction.
3. Planner and episode timing: efficiency and cost.
4. Replanning trigger counts: why the pipeline replanned.
5. Structured failure summaries: what actually failed.
6. `implicit_non_target_handling_success`: G1/G3 capability metric for handling the hidden `phone`.
7. Subtask buckets and raw pipeline success: diagnostics only.

## Primary Task Success

### `episode_success`

**Description:** Boolean task-completion metric computed from deterministic variant validators.

**How it is computed:**

- Kitchen variants require final object-region relations only, such as mugs in `inside_box` and groceries in `cupboard_shelf`.
- Grill variants require final object-region relations plus ordered cooking procedures for required meats.
- G1 and G3 also require the discovered non-target `phone` to end on `table`.

**Why it matters:** This is the main benchmark success metric because it checks whether the task goal was actually satisfied, independent of whether the model followed the ground-truth action sequence.

**Interpretation:** Use this for primary success-rate tables. A trial with `episode_success = true` completed the deterministic task objective. A trial with `episode_success = false` did not satisfy at least one required final relation or procedure.

### `raw_episode_success`

**Description:** Boolean diagnostic metric from the pipeline's raw execution status.

**How it is computed:** It reflects whether the final pipeline cycle ended without an unrecovered planning or execution error.

**Why it matters:** It helps separate execution/pipeline termination from task completion. A plan can execute cleanly but still leave objects in the wrong final state.

**Interpretation:** Do not call this task success. Use it only to diagnose whether a failure came from execution termination or from deterministic final-goal validation.

## Partial Goal Completion

### `partial_goal_completion`

**Description:** Fraction of deterministic validator conditions satisfied.

```text
partial_goal_completion =
    (satisfied_relation_count + satisfied_procedure_count)
    / (required_relation_count + required_procedure_count)
```

**Why it matters:** This is the main partial-success metric. It gives a graded score when a trial misses some object placements or procedures but still completes part of the goal.

**Interpretation:** Use this to compare near-misses. For example, a model that cooks correctly but forgets to move the plate to the serving area should score higher than a model that never cooks or plates the meat.

### Relation Counts

Fields:

- `required_relation_count`
- `satisfied_relation_count`
- `missing_relation_count`

**Description:** Counts final object-region requirements.

**Examples:**

- Kitchen: `mug2 -> inside_box`, `can_of_beans -> cupboard_shelf`.
- Grill: `chicken -> plate_top`, `plate -> serving_area`, `phone -> table`.

**Why they matter:** They expose whether the model achieved the final spatial arrangement of task objects.

**Interpretation:** If relation counts are low, the issue is final object placement, not necessarily cooking order or planning latency.

### Procedure Counts

Fields:

- `required_procedure_count`
- `satisfied_procedure_count`
- `missing_procedure_count`

**Description:** Counts required temporal procedures. Kitchen variants currently have zero procedural conditions. Grill variants count one cooking procedure per required meat.

**Grill cooking procedure:** The meat must be placed in `inside_grill`, the grill must be closed, the grill must be opened again, and that same meat must later be placed on `plate_top`.

**Why they matter:** Final object placement alone cannot prove that meat was cooked. Procedure counts capture necessary temporal ordering.

**Interpretation:** If relation counts are high but procedure counts are low, the model may have placed objects correctly without following the required cooking process.

### Condition Counts

Fields:

- `required_condition_count`
- `satisfied_condition_count`
- `missing_condition_count`

**Description:** Total validator conditions, combining relations and procedures.

**Why they matter:** These are the direct numerator and denominator used by `partial_goal_completion`.

**Interpretation:** Use the split relation/procedure counts for explanation, and use total condition counts for auditability.

## Planner Timing And Runtime

Measured benchmark trials do not run preflight. The first measured planner call occurs inside `pipeline.run()`.

### `planner_invocations`

**Description:** Number of LLM/VLM planner calls made during the measured trial.

**Why it matters:** It measures how often the foundation model is invoked. More invocations usually mean more replanning, more latency, and higher model cost.

**Interpretation:** In the maintained pipeline, this should equal `total_cycles`, because each planning cycle makes one planner call.

### `total_planner_time_s`

**Description:** Sum of planner-call latencies across all initial-planning and replanning cycles.

**Why it matters:** It captures the model-side cost of planning under the current local/remote contract.

**Interpretation:** Use this when comparing LLM/VLM sizes or families. Larger or multimodal models may improve success but increase planner-call latency.

**Important wording:** This is planner-call latency, not pure model inference time. For remote runs, it is tied to the current client/server timing contract.

### `mean_planner_time_per_invocation_s`

**Description:** Average planner-call latency.

```text
mean_planner_time_per_invocation_s =
    total_planner_time_s / planner_invocations
```

**Why it matters:** It separates model-call cost from the number of replans. Two trials can have the same total planner time for different reasons: many fast calls or a few slow calls.

**Interpretation:** Use this to compare model size or modality while controlling for different numbers of replanning cycles.

### `episode_time_s`

**Description:** End-to-end measured episode time from immediately before the first measured planning call until final pipeline summary generation.

**Why it matters:** It measures the practical runtime cost of the whole trial, including planning, execution, monitoring, and replanning.

**Interpretation:** Use this for overall system efficiency. Compare it with `total_planner_time_s` to understand how much time is spent in planner calls versus execution and simulation overhead.

## Replanning Metrics

### `total_cycles`

**Description:** Total number of planning cycles in a trial.

**Why it matters:** It shows how many times the system constructed state, prompted the model, parsed a plan, and attempted execution.

**Interpretation:** `total_cycles = 1` means the initial plan was sufficient. Higher values indicate replanning.

### `total_replans`

**Description:** Number of planning cycles after the initial cycle.

```text
total_replans = total_cycles - 1
```

**Why it matters:** It measures how often the framework had to revise the plan.

**Interpretation:** Replanning is not inherently bad. In this paper, discovery-triggered replanning is part of the intended capability under partial observability.

### `discovery_triggered_replans`

**Description:** Number of replans caused by a previously hidden task object becoming visible.

**Why it matters:** This directly measures the partial-observability mechanism: hidden objects are not assumed initially and are incorporated when discovered.

**Interpretation:** Discovery-triggered replans should not be counted as failures. For G1/G3, discovery of `phone` is expected behavior.

### `failure_triggered_replans`

**Description:** Number of replans caused by real planning, pre-execution, runtime, post-execution, or goal-validation failures.

**Why it matters:** It measures recovery pressure on the foundation-model planner.

**Interpretation:** High values indicate the model or executor often reaches states that require recovery. This is distinct from discovery-triggered replanning.

### `other_triggered_replans`

**Description:** Replans that are not classified as discovery-triggered or failure-triggered.

**Why it matters:** It preserves accounting completeness.

**Interpretation:** This should usually be low. If it is high, the event taxonomy may need inspection.

## Structured Events And Failure Metrics

### `structured_events`

**Description:** Top-level list of surfaced events from planning and execution cycles, plus final deterministic goal-validation failure when applicable.

Each event includes:

- `event_type`
- `cycle_number`
- `is_failure`
- `is_replan_trigger`
- `failure_id`
- `failure_layer`
- `stage`
- `source`
- `action`
- `should_replan`
- `message`
- `evidence`

**Why it matters:** It provides auditable evidence for why replanning happened and what failed.

**Interpretation:** Use this for case studies, qualitative failure analysis, and debugging individual trials.

### `event_type`

Relevant values:

- `discovery`
- `structural_failure`
- `pre_execution_failure`
- `runtime_failure`
- `post_execution_failure`
- `goal_validation_failure`

**Why it matters:** It separates fundamentally different failure modes.

**Interpretation:** A structural failure means the model produced an invalid plan before execution. A pre-execution failure means the action was structurally valid but not currently applicable. A runtime or post-execution failure means execution or monitoring failed after an action was attempted. A discovery event is not a failure.

### `failure_id`

**Description:** Specific identifier for the event, such as `new_object_discovered`, `unknown_action_token`, or `goal_validation_failed`.

**Why it matters:** It gives finer-grained diagnosis than `event_type`.

**Interpretation:** Use this when identifying recurring model or executor failure patterns.

### `failure_layer`

**Description:** Layer of the framework that surfaced the issue.

**Why it matters:** It helps explain whether a failure came from plan syntax/interface checking, scene-dependent feasibility checking, execution, or final validation.

**Interpretation:** Useful for ablations and debugging. It should not be used as the main task-success metric.

### `stage`

**Description:** When the event occurred, such as before or after physical execution.

**Why it matters:** It distinguishes plans rejected before any robot action from failures observed after attempting execution.

**Interpretation:** Pre-execution failures are usually cheaper and safer than post-execution failures because the robot has not yet acted.

### `source`

**Description:** Component that produced the event, such as validation, segmentation, geometry, executor, PDDL, or goal validation.

**Why it matters:** It identifies which subsystem needs attention.

**Interpretation:** Use this for engineering diagnosis, not for primary claims.

### `is_failure`

**Description:** Boolean indicating whether the event is a real failure.

**Why it matters:** Discovery events trigger replanning but are not failures.

**Interpretation:** Failure tables must include only events with `is_failure = true`.

### `is_replan_trigger`

**Description:** Boolean indicating whether the event actually triggered a later replanning cycle.

**Why it matters:** Some failures may terminate the episode rather than trigger recovery.

**Interpretation:** Use this to count replanning causes. It is stricter than `should_replan`, which describes whether replanning was requested by the event.

### `should_replan`

**Description:** Boolean in the underlying event indicating whether the event is eligible for replanning.

**Why it matters:** It records the framework's intended response to the event.

**Interpretation:** Do not confuse this with `is_replan_trigger`. A final failure can have `should_replan = true` but not produce another replan if the replan limit has been reached.

### `failure_event_counts`

**Description:** Per-trial summary of real failures only.

Fields include:

- `total_real_failures`
- `by_event_type`
- `by_failure_id`
- `by_failure_layer`
- `by_stage`
- `by_source`
- `by_should_replan`

**Why it matters:** It allows failure analysis without counting discovery as an error.

**Interpretation:** Use this for failure tables and discussion of robustness limitations.

## Implicit Non-Target Handling

### `implicit_non_target_handling_success`

**Description:** Capability metric for G1 and G3. It is `None` for all other variants.

For G1/G3 it is true only when:

- `phone` was discovered after being hidden;
- the natural-language goal did not mention `phone`;
- completed actions include `pick(phone)` followed by `place(phone, table)`;
- the final deterministic object-region map places `phone` on `table`.

**Why it matters:** It isolates the behavior that motivated the phone change: the model must infer how to handle a newly revealed non-target object without being directly told to move it.

**Interpretation:** Report separately from `episode_success`. A model can potentially satisfy some task conditions while failing this specific implicit-reasoning behavior.

## Diagnostic Subtask Metrics

### `completed_gt_subtasks`

**Description:** Number of expected canonical subtask buckets matched by completed actions.

**Why it matters:** It helps inspect whether execution followed the expected ground-truth-style procedure.

**Interpretation:** Diagnostic only. It should not determine task success because valid alternative plans may not match the canonical action-bucket structure.

### `gt_total_subtasks`

**Description:** Number of expected canonical subtask buckets for the variant.

**Why it matters:** It is the denominator for `subtask_completion_rate`.

**Interpretation:** Use only with subtask diagnostics.

### `subtask_completion_rate`

**Description:** Canonical subtask bucket coverage.

```text
subtask_completion_rate =
    completed_gt_subtasks / gt_total_subtasks
```

**Why it matters:** It is useful for trace inspection and comparing executed action histories against the curated ground-truth structure.

**Interpretation:** Do not treat this as partial task success. Use `partial_goal_completion` for validator-aligned partial success.

### `bucket_breakdown`

**Description:** Per-bucket expected, observed, and matched counts.

**Why it matters:** It shows which canonical behaviors appeared in the completed action history.

**Interpretation:** Useful for debugging procedural omissions, repeated actions, or unexpected transfers.

### `observed_subtasks`

**Description:** Ordered list of inferred subtask buckets from completed actions.

**Why it matters:** It helps reconstruct what the robot actually did at the task-abstraction level.

**Interpretation:** Useful for qualitative trace analysis.

### `extra_observed_subtasks`

**Description:** Buckets observed more often than expected or not expected for the variant.

**Why it matters:** It can reveal unnecessary or wrong actions.

**Interpretation:** Diagnostic only. Extra actions may explain longer runtime or failed final validation.

## Legacy And Raw Failure Diagnostics

### `raw_failure_occurrences`

**Description:** Older message-based failure categorization collected from cycle error messages and terminal failure reason.

**Why it matters:** It preserves backward-compatible debugging information.

**Interpretation:** Prefer `structured_events` and `failure_event_counts` for final analysis. Use raw failure strings only when debugging older records or unexpected messages.

### `failure_occurrences`

**Description:** Backward-compatible alias for the raw message-based failure diagnostic.

**Why it matters:** Some older aggregation or inspection scripts may still expect this field.

**Interpretation:** Diagnostic only. Do not use it for final failure tables when structured events are available.

## Aggregated Result Fields

Aggregators report per-variant and overall summaries, including:

- `episode_success_rate`
- `raw_execution_success_rate`
- `mean_partial_goal_completion`
- `std_partial_goal_completion`
- `mean_planner_invocations`
- `mean_total_planner_time_s`
- `std_total_planner_time_s`
- `mean_planner_time_per_invocation_s`
- `std_planner_time_per_invocation_s`
- `mean_episode_time_s`
- `std_episode_time_s`
- `discovery_triggered_replans`
- `failure_triggered_replans`
- `other_triggered_replans`
- `implicit_non_target_handling_rate`
- `failure_counts`

Use these aggregated fields for result tables. Keep raw records for case-study inspection.
