# Kitchen Failure-Path Audit

Date: 2026-05-17

## Scope

This audit covers the kitchen action-sequence workflow centered on
`llm_pipeline/debug_execution.py`, especially K1/K2/K3 text files under
`llm_pipeline/debug_sequences/`.

The goal was to identify where failures currently surface, how execution stops,
and what is already available for later illogical sequence testing.

## Main Finding

`debug_execution.py` has two different failure surfaces:

- Default `executor-direct` mode executes `DirectPrimitiveExecutor` with no
  failure checker and with pre/post checks disabled. This mostly catches
  physical/GT execution failures, not logical sequence errors.
- `--pipeline-wrapper --with-scene-state` routes through
  `LLMOnlyReplanningPipeline` with real scene-state and failure checking. This is
  the path that can produce structured `FailureEvent` records for missing moves,
  bad executor state, missing objects, bad placement, lid failures, and runtime
  planner errors.

## Existing Stop Points

- Text file loading in `debug_execution.py` rejects invalid syntax only. It
  accepts syntactically valid but logically bad sequences such as orphan place,
  picking while already holding, opening while holding, and unknown object names.
- Kitchen bundling in `llm_pipeline/executor.py` consumes:
  - `[move, pick, move, place]` as one GT transfer ritual.
  - `[move, open]` as one GT open ritual.
- Failed kitchen transfer bundles become generic `TAMP_EXECUTION_ERROR`.
- Failed kitchen open bundles become `TAMP_OPEN_ERROR`.
- Non-bundled primitive failures return `PrimitiveExecutionOutcome(success=False)`
  from `DirectPrimitiveExecutor.execute_actions`.
- In full pipeline mode, failures are written into cycle records and execution
  stops or replans based on `FailureEvent.should_replan` and `--max-replans`.

## Failure Logic Already Present

Pre-execution checks can produce:

- `missing_preceding_move`
- `invalid_executor_state`
- `pick_object_missing`
- `lid_missing`

Post-execution checks can produce:

- `grasp_failed`
- `object_dropped`
- `placement_failed`
- `lid_not_open_enough`
- `new_object_discovered`

Runtime error classification can produce:

- `empty_pick_trajectory`
- `empty_place_trajectory`
- `lid_hover_planning_fail`
- `lid_slide_planning_fail`
- `pddl_no_plan`
- `no_ik_solution`
- `no_motion_plan`
- `no_grasp_found`
- `executor_failure`

## Probe Results

Temporary bad sequence file:

`/tmp/kitchen_failure_audit.7xcurs/bad_sequences.txt`

`debug_execution.load_sequences()` behavior:

| Case | Text loader result |
| --- | --- |
| Missing move before pick | Accepted |
| Orphan place | Accepted |
| Pick while holding | Accepted |
| Impossible target placement | Accepted |
| Open while holding | Accepted |
| Unknown object | Accepted |
| Invalid syntax | Rejected |

`StrictActionParser` behavior:

| Case | Structured result |
| --- | --- |
| Missing move before pick | `missing_preceding_move` |
| Orphan place | `orphan_place` |
| Pick while holding | `pick_place_mismatch` |
| Open while holding | `missing_post_pick_place` |
| Unknown object | `unknown_action_token` |

`SegmentationFirstFailureChecker` behavior:

| Case | Structured result |
| --- | --- |
| Missing move precheck | `missing_preceding_move`, should replan |
| Pick missing object | `pick_object_missing`, should replan |
| Place wrong held object | `invalid_executor_state`, terminal |
| Open while holding | `invalid_executor_state`, terminal |
| Wrong placement region | `placement_failed`, should replan |
| Lid still closed after open | `lid_not_open_enough`, should replan |
| New object discovered | `new_object_discovered`, should replan |

Runtime classification probe:

| Runtime message | Classified as |
| --- | --- |
| `No PDDL plan found` | `pddl_no_plan` |
| `Could not find a valid joint configuration` | `no_ik_solution` |
| `Could not plan motion to hover` | `lid_hover_planning_fail` |
| `Pick has empty trajectory` | `empty_pick_trajectory` |
| `Grasp candidate failed` | `no_grasp_found` |

## Simulator-Backed Probe Status

The project venv Python is currently broken in this shell:

- `python -m pytest ...` failed because system Python has no pytest.
- `.venv/bin/python` and `.venv/bin/python3` fail with missing Python 3.12
  `encodings`.
- `activate_gt_env.sh` correctly selects `/usr/bin/python3` as `GT_PYTHON`.

One headless scene-state probe was attempted:

```sh
. ./activate_gt_env.sh
QT_QPA_PLATFORM=offscreen "$GT_PYTHON" llm_pipeline/debug_execution.py \
  --variant K1 \
  --sequence-file /tmp/kitchen_failure_audit.7xcurs/missing_move_retry.txt \
  --pipeline-wrapper \
  --with-scene-state \
  --max-replans 0 \
  --headless \
  --no-live-masks
```

It initialized the segmentation detector, then CoppeliaSim crashed in offscreen
OpenGL vision-sensor setup before the missing-move precheck could complete.

This means simulator-backed `--with-scene-state` replay needs an environment fix
or a no-vision/no-GL scene-state mode before it can be used reliably from this
headless shell.

## K1 Ground-Truth Log Cross-Check

The open K1 GT log is not the primary target pipeline, but it confirms a related
pattern:

- Task 5 failed at placement validation: object not in target region.
- The GT wrapper continued later tasks.
- Final summary marked `episode_success: false`.
- `failure_reason` stayed `null`.

So GT benchmark failures are mostly per-subtask booleans, while the
`llm_pipeline` path is where structured failure events should be developed.

## Recommendations For Next Step

- Use `debug_execution.py --pipeline-wrapper --with-scene-state` as the intended
  route for logical failure experiments, but fix the headless scene-state crash
  first or add a no-vision state-check path.
- Add validation at the debug text-file layer if illogical sequences should fail
  before simulator startup.
- Preserve temporary sequence files for exploratory audits, because
  `debug_execution.py` writes progress metadata back into whichever sequence file
  it runs.
