# Metric Information

## raw_episode_success

This means the final action sequence selected by the pipeline executed cleanly without an unrecovered planning, pre-check, runtime, or post-check failure.
- It does not necessarily mean the task goal was completed.
- It does not mean every LLM-proposed sequence executed cleanly, because earlier failed sequences may be followed by successful replanning.
- The primary benchmark task-completion metric is `episode_success`, not `raw_episode_success`.

## completed_gt_subtasks

- `completed_gt_subtasks` is the number of expected canonical subtask buckets matched by the actions completed during LLM/VLM pipeline execution.
- It is computed by converting completed primitive actions into bucket labels, then comparing those observed bucket counts against the expected bucket counts for the variant.

- It only compares against the canonical GT-style bucket summary for the variant.
- For each bucket, the matched count is capped by the expected count. Extra repetitions do not increase `completed_gt_subtasks`.

Example K1 expected buckets:

```python
{
    'mug_to_placement': 1,
    'open_lid': 1,
    'grocery_to_cupboard': 2,
    'mug_to_box': 2,
}
```

These sum to `gt_total_subtasks = 6`. If the executed actions produce one `open_lid`, one `grocery_to_cupboard`, and two `mug_to_box` buckets, then `completed_gt_subtasks = 4`.

Example G3 expected buckets:

```python
{
    'open_grill': 2,
    'close_grill': 1,
    'plate_to_boundary': 1,
    'meat_to_plate': 3,
    'meat_to_grill': 2,
    'meat_to_table': 1,
}
```

These sum to `gt_total_subtasks = 10`.


## gt_total_subtasks

Expected number of canonical buckets for that variant.
Comes from evaluation/canonical_variants.py, e.g. K1 has 6, G3 has 10.


## subtask_completion_rate

completed_gt_subtasks / gt_total_subtasks.
Kept as procedural coverage, not primary success anymore.

## bucket_breakdown

Per-bucket counts:
expected
observed
matched
Buckets include things like mug_to_box, grocery_to_cupboard, open_grill, meat_to_plate, etc.

## observed_subtasks

The ordered list of subtask buckets inferred from completed actions.

## extra_observed_subtasks

Buckets that were observed but not expected, or observed more often than expected.

## total_cycles

Number of planning/replanning execution cycles.

## total_replans

Number of replanning cycles used.
episode_time_s

Total pipeline episode runtime.

## failure_reason

Terminal failure reason string from the pipeline.

## failure_occurrences

Categorized failure messages collected from cycles plus terminal failure reason.