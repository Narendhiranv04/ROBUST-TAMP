# ROBUST TAMP — Architecture map (Phase 1, step 1)

Map of the repository, written read-only at branch `phase-1-logging` (base
`naren/variants-scenes-execution`, commit `380d04ad`), and updated after
Phase 1 steps 2–5c (see "Phase 1 changes" below). Terminology follows `plan.md` Section 0.6; where the
code uses a different word, the code identifier is quoted and the conflict is
listed in [Terminology conflicts](#terminology-conflicts-with-plan-md-06).

Paths are relative to the repo root. `file:line` references point at the
definition.

## Overview

The maintained pipeline is `llm_pipeline/`. `vlm_pipeline/` is the previous
system; `llm_pipeline` only reuses `vlm_pipeline/model_registry.py`,
`vlm_pipeline/vlm_planner.py` (VLM prompt/parse path) and
`vlm_pipeline/vlm_executor_v2.py` (executor base class). `vlm_server.py`,
`vlm_client.py`, `planner_factory.py` and `llm_planner.py` are not used.

```
trial_runner.main ─▶ run_trial ─▶ LLMOnlyReplanningPipeline.run (loop)
                                   ├─ _build_scene_state        (scene state)
                                   ├─ GeometricContextBuilder   (prompt)
                                   ├─ planner.plan              (planner client ─▶ remote planner server)
                                   ├─ StrictActionParser        (plan check)
                                   ├─ DirectPrimitiveExecutor   (pre-action check ─▶ execution adapter ─▶ post-check)
                                   └─ goal check / stop
                  ◀─ summary ─ validate_variant_success          (evaluator, scoring)
                  ─▶ record.json + failure_summary.txt           (logging)
```

Simulator: CoppeliaSim/PyRep by default, or MuJoCo via `SIM_BACKEND=mujoco`
(`sim_backend.py`, `mujoco_port/`). The pipeline code is identical for both.

Variant registry: `evaluation/canonical_variants.py` — `VariantSpec`
(:14; `variant_id, task_family, scene_path, goal_text,
expected_subtask_buckets, gt_runner_path, ...`), `VARIANTS` (K1–K3, G1–G3),
`get_variant_spec` (:163). All kitchen variants share one goal string, all grill
variants another (:43–49).

Current variant contents (movable objects in the ported scenes):

| Variant | Scene file | Objects |
|---|---|---|
| K1 | `task1_variation1.ttt` | mug2, mug3, soup, spam (+ box_lid) |
| K2 | `task1_variation2.ttt` | mug1, mug2, mug3, soup, sugar |
| K3 | `task1_variation3.ttt` | mug1, mug2, mug3, soup, spam, sugar |
| G1 | `grill_task2/grill.variation1.ttt` | chicken, phone, plate |
| G2 | `grill_task2/grill.variation2.ttt` | chicken, steak, steak1, plate |
| G3 | `grill_task2/grill.variation3.ttt` | chicken, steak, steak1, phone, plate |

---

## 1. Scene state construction (visible state)

| | |
|---|---|
| Files | `llm_pipeline/pipeline.py`, `segmentation_adapter.py`, `region_geometry.py`, `region_aliases.py`, `grill_geometry.py`, `executable_symbols.py`, `pipeline_types.py`; root `segmentation_object_detector.py` |
| Entry | `LLMOnlyReplanningPipeline._build_scene_state` (pipeline.py:518) |
| Output | `SceneState` (pipeline_types.py:211): `frame_index, visible_objects, valid_regions, pddl_state, pose_map, images, gripper_state{status, holding}, region_map, object_region_map, object_region_descriptions, lid_states` |

How it is built:

1. **Visibility — from segmentation masks.** `SegmentationObjectDetector`
   (segmentation_object_detector.py:27) decodes colour-coded handle masks per
   camera. Thresholds: ≥10 px (kitchen) / ≥50 px (grill) per camera
   (`LIVE_SEG_MIN_PIXELS`); an object stays visible for 30 frames after last
   seen (`LIVE_SEG_PERSIST_FRAMES`).
2. **Snapshot.** `SegmentationEvidenceAdapter.capture_snapshot`
   (segmentation_adapter.py:219) → `SegmentationSnapshot` (pipeline_types.py:138:
   `visible_objects, newly_visible_objects, object_evidence, supported_regions,
   object_region_map, object_region_descriptions`).
   Newly visible objects = `visible_now − known_visible` (segmentation_adapter.py:313).
3. **Regions — from simulator geometry.** `_resolve_geometric_regions`
   (segmentation_adapter.py:380) takes each visible or previously seen object's
   **simulator pose** (`detector.get_object_pose`, segmentation_object_detector.py:391
   — "detected via vision but get pose from backend") and each region shape's
   simulator AABB, then `resolve_object_regions` (region_geometry.py:149):
   first region in `PRIMARY_REGION_PRIORITY` whose padded AABB contains the
   pose point (`point_matches_region` :119, `REGION_PADDING` :55,
   `REGION_Z_MARGIN` :71), default `table`.
   `_apply_container_bbox_overrides` (:415) sets `inside_box` when ≥35 % of the
   object's AABB footprint overlaps the box interior.
4. **Articulation states.** Kitchen box lid: `is_lid_open`
   (segmentation_adapter.py:484), open when `|lid.x − box_base.x| > 0.10`
   (simulator positions). Grill lid: `infer_grill_lid_open` (grill_geometry.py:194),
   open when `|joint − _closed_lid_angle| > 0.25` rad. `lid_states` only lists
   visible lids (pipeline.py:580), but the grill lid fact enters `pddl_state`
   regardless (:574).
   **Stand-in for perception (decision, Phase 1 step 5b):** lid open/closed
   states are read from the simulator's joint and pose values instead of
   being estimated from camera images. This is the one piece of simulator
   state the planner may see about objects it cannot currently observe. With
   `prompt.version=v2` every lid of the scene is reported this way (legacy:
   visible lids only).
   **Grasp confirmation, same stand-in (decision, Phase 1):** with
   `grasp.confirmation=gripper_state` (default) the pick post-check confirms a
   grasp from the gripper's state (`failure_logic.held_objects_from_gripper`):
   the object is in `gripper.get_grasped_objects()`, is parented to the robot
   tip or gripper attach point, or both fingers are not fully open and a finger
   is within 1 cm of it (the scripted cupboard pick carries the mug this way).
   The previous mask-proximity check (`segmentation`) misfired on MuJoCo when the
   object was visible only in the wrist camera.
   **Initial poses (Phase 1):** with `scene.randomization=pose_jitter` (default)
   each trial jitters its variant's free objects from the trial seed
   (`llm_pipeline/randomization.py`); the record is logged in
   `trial_start.randomization`.
5. **Grill semantic facts.** `derive_grill_semantic_facts` (grill_geometry.py:138)
   → `SceneState.pddl_state`: `grill_lid_open/closed`, `inside_grill(m)`,
   `on_plate(m)`, `in_prep_area(m)`, `on_table(m)`, `cooked(m)`/`raw(m)`,
   `plate_at_boundary`, `plate_at_dish_rack` (cooking rule: see §8).
6. **Symbol registry.** `build_runtime_symbol_registry` (executable_symbols.py:164)
   → `RuntimeSymbolRegistry(actions, objects, regions)` from the env's object
   table plus the detector's object list, and `env.regions` from the scene.

Region vocabulary and aliases: `region_aliases.py` (`KITCHEN_REGION_ALIASES` :7,
`GRILL_REGION_ALIASES` :24, canonical orders :33/:42,
`CANONICAL_REGION_SCENE_OBJECTS` :55 e.g. `inside_box → box_boundary`,
`serving_area → plate_boundary`, prompt semantics `REGION_SEMANTICS` :66).

**No per-scene object-category config exists.** Categories appear only as
hard-coded name sets in the evaluator (metrics.py:16–20: `MUG_OBJECTS`,
`GROCERY_OBJECTS`, `MEAT_OBJECTS`, `GRILL_NON_TARGET_OBJECTS={'phone'}`) and as
name prefixes (`steak*`, `chicken*`) in `grill_geometry._is_grill_meat`.
**No placement-area config exists** (region = whole region AABB).

Not on the main path: `debug_state_builder.py` (`debug_state_recognition` :346),
`live_state_monitor.py` (`monitor_live_state` :218, manual poller).

## 2. Prompt construction

| | |
|---|---|
| Files | `llm_pipeline/geometric_builder.py` (default), `prompt_builder.py` (text-only builder, only `PROMPTS_DIR` reused), `prompts/system_prompt.txt`, `prompts/shared_exemplar.txt` |
| Entry | `GeometricContextBuilder.build_bundle(state, goal_text, failure_event, previous_actions, icl_mode)` (geometric_builder.py:73), called from `plan_once` (pipeline.py:395) |
| Output | `PromptBundle` (pipeline_types.py:81): system prompt, user prompt, images, metadata |

- System prompt: `prompts/system_prompt.txt`; with `icl_mode = few_shot_shared_1`
  the shared exemplar (7 toy-name examples) is appended (geometric_builder.py:225).
  `llm_pipeline/system_prompt.txt` and `llm_pipeline/shared_exemplar.txt` are
  older unused copies.
- User prompt sections, in order: `### Planning Checkpoint` (checkpoint_type
  initial/replanning, gripper, visible objects, `tracked_non_visible_objects`,
  newly visible objects) · `### Goal` · `### Visible-Object Relational State`
  (region, cook_status, visibility, description) · `### Valid Target Regions` ·
  `### Articulation State` · `### Access Constraints` (BLOCKED/OBSTRUCTED) ·
  `### Domain Semantic State` · `### Completed Actions` · `### Replanning Event`
  (replans only: event_type discovery/failure, id, stage, source, layer, failed
  action, message; plus repair rules for `layer_1`) · `### Executable Interface`
  / `### Actions` (`_build_action_contract_lines` :257).
- **Initial plan vs replan prompt** differ only in checkpoint type, the
  newly-visible list and the Replanning Event block. The **remaining plan and the
  previous plan are not included**; the replan asks for a new plan from the
  current state (`failure_logic.render_failure_context` :380 is unused).
- Goal text: `VariantSpec.goal_text` unless `--goal` overrides.
- VLM images: with `--vision`, `_capture_rgb_frames` (pipeline.py:475) grabs
  left/right/overhead/wrist/front, `stitch_frames` (geometric_builder.py:49)
  tiles them; `VLMPlanner.plan` (llm_pipeline/vlm_planner.py:81) sends the
  first image.
- Goal-check prompt: `_build_goal_check_prompts` (pipeline.py:608) — "strict
  robotic goal-completion verifier … GOAL_COMPLETE or GOAL_INCOMPLETE: <reason>".

## 3. Planner client and remote planner server

| Part | File / class | Interface |
|---|---|---|
| Client | `llm_pipeline/client.py` `RemoteTextLLMPlanner` (:27) | `plan(bundle)` :117 → `generate_plan` :135 POST `/plan`; `check_goal_completion` :249 POST `/check-goal`; `load_model` :81 GET `/health` |
| Server | `llm_pipeline/server.py` `LLMServer` (:115), FastAPI `create_app` (:271) | `GET /health`, `GET /debug/last-request`, `POST /plan`, `POST /check-goal` |
| Local LLM | `llm_pipeline/planner.py` `TextLLMPlanner` (:36) | HF causal LM; `generate_plan` :273, `check_goal_completion` :322 |
| Local VLM | `llm_pipeline/vlm_planner.py` `VLMPlanner` (:19) | wraps `vlm_pipeline.vlm_planner` |
| Mock | `planner.py` `MockTextLLMPlanner` (:368) | `scripted_output`, `goal_check_output`; tests also use `QueuePlanner` (tests/test_pipeline.py:35) |

- `/plan` request (`PlanRequest` server.py:44): `system_prompt, user_prompt, goal,
  icl_mode, max_new_tokens, temperature, held_object, use_vision, image_present,
  valid_actions, valid_objects, valid_regions, image_base64?`.
  Response (`PlanResponse` :76): `success, actions[{action_name, args}],
  raw_output, inference_time, error_message, failure_event`.
- Server selects the model with `--model` (alias via
  `vlm_pipeline.model_registry.resolve_model_spec`), `--model-type llm|vlm`,
  `--quantization none|bnb8|bnb4` (default **bnb4**). Thinking mode: env
  `QWEN_THINKING_MODE` (default off → `/no_think`).
- Timeouts: `LLM_REQUEST_TIMEOUT_S` (300 s), `LLM_HEALTH_TIMEOUT_S` (60 s),
  `LLM_HEALTH_RETRIES` (5). Planner calls are **not retried**.
- Planner-call latency: server `inference_time` (falls back to client wall time).
  Decoding is greedy (sampling only if temperature ≥ 0.3, planner.py:236).
- Raw output is kept per cycle (`ExecutionCycleRecord.raw_output`); full prompts
  are kept in `prompt_bundle` and on the server (`last_request_summary`).

## 4. Plan check

| | |
|---|---|
| Files | `llm_pipeline/strict_parser.py`, `executable_symbols.py` |
| Entry | `StrictActionParser.parse(text, held_object)` (strict_parser.py:44); run by the client/planner after each planner call |
| Output | `List[DirectAction]` or `StrictParseError(message, line_number, failure_id)` → `FailureEvent(source=validation/parser, layer_1, should_replan=True)` |

Rules (strict_parser.py): strip `<think>`, keep text after the last
`FINAL ACTIONS:`; `NO_ACTIONS` → empty plan. Unknown verb/object/region, or
`pick(box_lid)` → `unknown_action_token`; `pick` while holding and
`place` of a different object → `pick_place_mismatch`; `place` with empty
gripper → `orphan_place`; `open`/`close` while holding, or plan ends holding →
`missing_post_pick_place`. Allowed actions: `pick, place, open` (+ `close` in
grill scenes, executable_symbols.py:16–17). VLM path adds
`planner_output_too_verbose` / `planner_output_not_parseable`
(llm_pipeline/vlm_planner.py:57–79) and one format-repair regeneration inside
`vlm_pipeline/vlm_planner.py:731`.

## 5. Pre-action checks

`GeometricFailureChecker` (failure_logic.py:459, built at pipeline.py:229) extends
`SegmentationFirstFailureChecker` (:68). `precheck` (:87, :466) runs before each
action stage:

| Action | Check | Failure id |
|---|---|---|
| pick | gripper empty | `invalid_executor_state` (should_replan=False) |
| pick | object visible | `pick_object_missing` |
| pick | object pose resolvable | `geometric_discovery_fail` |
| place | holding that object | `invalid_executor_state` |
| place | `inside_box` needs box lid open | `box_lid_closed` |
| place | `inside_grill` needs grill lid open | `grill_lid_closed` |
| place | region pose resolvable | `geometric_discovery_fail` |
| open/close | gripper empty | `invalid_executor_state` |
| open/close | lid visible | `lid_missing` |
| open(box_lid) | nothing on the lid | `box_lid_obstructed` |

Post-action checks (`postcheck` :225, :514): `grasp_failed`, `object_dropped`,
`placement_failed`, `geometric_placement_failed`, `lid_not_open_enough`,
`lid_not_closed_enough`, and **`new_object_discovered`** (see §7).

## 6. Execution adapters

| | |
|---|---|
| Files | `llm_pipeline/executor.py`; root `ground_truth_orchestrator.py`, `rlbench_kitchen_env.py`, `rlbench_kitchen_streams.py`; `grill_task2/ground_truth_orchestrator_variation1 copy.py`, `grill_task2/grill_task_env.py`; `vlm_pipeline/vlm_executor_v2.py` (base) |
| Entry | `DirectPrimitiveExecutor.execute_actions(actions, failure_checker, pre_action_checks_enabled, post_action_checks_enabled)` (executor.py:1099) |
| Output | `PrimitiveExecutionOutcome` (:72): `success, completed_actions, remaining_actions, held_object, last_failure_event, error_message` |

- **Bundles.** `UnifiedActionBundler.try_execute_bundle` (:338) forms bundles:
  `[pick(o), place(o, r)]` → `_execute_transfer_bundle` (:376, consumes 2; skipped
  if `o` is already in `r`); `open`/`close` → `_execute_lid_bundle` (:643).
  Returns `BundleExecutionOutcome` (:82). Each action is unrolled into GT stages
  (`move`, `pick`/`place`), each with pre- and post-check.
- **Kitchen adapter** `KitchenBundlingHandler` (:110): transfers via
  `ground_truth_orchestrator.create_primitive_transfer_executor` (:2327) →
  `PDDLPrimitiveTransferExecutor` (:1482, pddlstream `solve(..., algorithm='adaptive',
  max_time=60)`) or `CupboardPrimitiveTransferExecutor` (:1897); `open` →
  `run_open_box` (:2489, slide, precomputed path replay when available);
  `close` → not supported in the kitchen.
- **Grill adapter** `GrillBundlingHandler` (:179): loads
  `grill_task2/ground_truth_orchestrator_variation1 copy.py` as `grill_gt`;
  transfers via `GrillPrimitiveTransferExecutor` (copy.py:4231; slot poses
  `_region_slot_pose`); `open`/`close` via `run_grill_lid_motion_framework`
  (copy.py:5460) → `GrillLidPrimitiveExecutor` (:4894). No pddlstream: PyRep
  `get_path` / IK sampling, with linear-interpolation fallback
  (`_plan_or_interpolate` copy.py:4339).
- **Local retries** (inside adapters only; no action-level retry in
  `llm_pipeline`): grill grasp 5×/3× (copy.py:890), plate attach 6×, handle
  attach 8–10×, hinge re-lock 1×; kitchen release 3× (root :751), cupboard pick
  over 3 hover distances × grasp orientations (executor.py:1676), forced and
  z-drift re-release in `_execute_place_pddl` (:1589, :1640).
  `VLMExecutorV2._execute_with_retry` is unused.
- **Execution failure reporting.** Adapters return `(bool, str)`;
  `_runtime_failure` (:811) → `classify_runtime_error` (failure_logic.py:309) maps
  the message by keyword to `pddl_no_plan, no_ik_solution, no_motion_plan,
  no_grasp_found, placement_failed, object_dropped, object_did_not_move,
  lid_not_open_enough, executor_failure, …`; `evidence.legacy_failure_id` ∈
  `TAMP_EXECUTION_ERROR/TAMP_OPEN_ERROR/TAMP_CLOSE_ERROR`.
- **Timing:** none per action or bundle; only trial time.

## 7. Monitoring and replan loop

| | |
|---|---|
| File | `llm_pipeline/pipeline.py` |
| Classes | `LLMPipelineConfig` (:59), `ExecutionCycleRecord` (:116), `LLMOnlyReplanningPipeline` (:149) |
| Entry | `run(goal_text)` (:791) → summary dict |

Loop (`run`, :833 `while len(self.cycles) <= max_replans`): `plan_once` (scene
state → prompt → planner call → plan check) → `execute_actions` → on failure,
the `FailureEvent` becomes `pending_failure` and the next cycle is a replan.

- **Triggers today:** any `FailureEvent` with `should_replan=True` — plan-check
  failures, pre/post-check failures, runtime failures, `goal_not_satisfied`, and
  **every newly visible object** (`_maybe_new_visibility_failure`,
  failure_logic.py:415 → `new_object_discovered`, excluding `box_lid` and the
  action's own object). Gate: `replan_on_new_visibility=True` (failure_logic.py:76),
  hard-coded, no CLI flag. This is plan.md's `replan.trigger_mode = discovery`.
- **Output mode today:** the whole remaining plan is regenerated
  (plan.md's `replan.output_mode = full_replan`). Insertion, urgency, memory and
  parallel execution do not exist.
- **Replan budget:** `max_replans` (config default 10, `trial_runner` CLI default
  3, `run_10_trials_and_aggregate.py` default 10); up to `max_replans + 1` planner
  calls; plan-check failures consume budget. **No repeated-output detection.**
- **Stop conditions:** (a) plan executed and goal check off (the trial default)
  → success (:952); (b) goal check on → `_check_goal_completion_with_deterministic_override`
  (:734): the evaluator's `validate_variant_success` (§8) runs on the current
  scene state and **overrides the planner model's goal check whenever they
  disagree** (:745); (c) `NO_ACTIONS` (:852–895); (d) non-replannable failure
  (`invalid_executor_state`); (e) budget exhausted. Trial `success` =
  `cycles[-1].success`, later recomputed by the evaluator in `trial_runner`.

## 8. Task evaluation (evaluator)

| | |
|---|---|
| Files | `llm_pipeline/metrics.py` (per trial), `evaluation/metrics.py` + `llm_pipeline/aggregate.py` (aggregates), `evaluation/canonical_variants.py` |
| Entry | `validate_variant_success(variant_id, object_region_map, completed_actions)` (metrics.py:629), called in `trial_runner.run_trial` (:362) and inside the loop (pipeline.py:692) |
| Inputs | `final_object_region_map` = the pipeline's own final `SceneState.object_region_map` (pipeline.py:771/1008: segmentation-visible or previously seen objects, regions from simulator poses); `completed_actions` = executed actions in order |
| Output | `_validator_result` (:222): `success, missing/satisfied_relations, missing/satisfied_procedures, *_count, partial_goal_completion, details` |

**Goal relations.** Hard-coded per variant: `KITCHEN_FINAL_GOALS` (:29) and
`GRILL_FINAL_GOALS` (:44). Each `(object, region)` pair is one relation;
satisfied iff the object's normalized region in `final_object_region_map`
equals the goal region (`_normalize_region` :87 collapses aliases, e.g. all box
regions → `inside_box`, all cupboard regions → `cupboard_shelf`). An object
missing from the map counts as `unknown` → unsatisfied. G1/G3 require
`phone → table`.

**Procedure checks — exactly how "meat is cooked" is computed.** Only for the
meats in `GRILL_OUTSIDE_COOKED_MEATS` (:61: G1 `chicken`; G2/G3 `chicken`,
`steak1`), i.e. meats that start **outside** the grill. For each such meat,
`_has_cooking_sequence(parsed_actions, meat)` (:354) searches the executed
action history, in order:

1. first `place(meat, r)` with `normalize(r) == inside_grill`, at index *i*;
2. any later `close(grill_lid)` (index > *i*) — normalized to `close_lid`;
3. any later `open(grill_lid)` after that close — normalized to `open_lid`;
4. any later `place(meat, r)` with `normalize(r) == plate_top`.

All four found → `"<meat> cooked before plating"` satisfied; otherwise a missing
procedure. Properties of this rule:

- It is **purely action-history based**: no simulator cooking state, timer, or
  check that the meat was still inside the grill during the close→open cycle
  (a meat removed before the close still counts if it was placed in first).
- Meats that **start inside the grill** (G2/G3 `steak`) are never
  procedure-checked; they are implicitly treated as cooked.
- There is **no overcooked check**, and no check that a cooked meat left the
  grill before another close.
- The agent-side counterpart `grill_geometry.derive_grill_semantic_facts`
  (:138; `_has_completed_cooking_cycle` :101) uses the same place→close→open
  rule **without** the plating step, and also marks any meat found inside the
  grill that the robot did not place there as `cooked` (:170). This is what the
  planner model sees as `cook_status`. The two implementations are separate code.

**Metrics.**
- Per trial: `partial_goal_completion = (satisfied relations + satisfied
  procedures) / (total relations + total procedures)` (metrics.py:276) — already
  matches plan.md Phase 1 step 5. The old metric `subtask_completion_rate`
  (`score_variant_completion` :178, bucket counts from
  `VariantSpec.expected_subtask_buckets`) is still reported alongside.
- Aggregates: `evaluation/metrics.py` `aggregate_model_records` (:343) →
  `episode_success_rate` (mean of `episode_success`), `mean_partial_goal_completion`,
  `raw_execution_success_rate`, planner-call counts/times, `mean_episode_time_s`.
- `implicit_non_target_handling_success` (metrics.py:562): G1/G3 only — phone was
  discovered, moved to the table and ends there.

## 9. Experiment runner and logging

| Runner | File | Output |
|---|---|---|
| Single trial | `llm_pipeline/trial_runner.py` `main` (:473) → `run_trial` (:235) | `<output-dir>/record.json` + `failure_summary.txt`; default `results/llm_runs/<ts>_<VAR>_<model>_<icl>_trial_NNN/` (`_resolve_output_paths` :139) |
| N trials + aggregate | `run_10_trials_and_aggregate.py` `main` (:277) | subprocess per trial → `<root>/<model>/<variant>/trial_NNN/`, `aggregate_summary.json` |
| Benchmark | `llm_pipeline/benchmark_runner.py` | `results/benchmarks/<ts>/{preflight,trials}/…`, `benchmark_summary.json` |
| Aggregation | `llm_pipeline/aggregate.py` `aggregate_records` (:78) | summary dicts |
| PDDL baseline | `llm_pipeline/pddl_trial_runner.py` `run_trial` (:1230) | separate baseline |
| GT replay | `llm_pipeline/debug_execution.py`, `mujoco_port/tools/run_gt_matrix.py` | GT action sequences, not planner-driven |

Key `trial_runner` flags: `--variant, --model, --model-type, --quantization,
--vision, --icl-mode, --trial-index, --max-replans, --goal-check/--no-goal-check
(default off), --remote/--remote-url, --replan-mode on|off, --headless`.

Logging: `record.json` is one indented JSON document written at the end of the
trial (top-level keys: variant/scene/model/prompt settings, success fields,
relation/procedure counts, planner-call counts and times, planned/completed/
remaining actions, final regions and lid states, `structured_events`,
`failure_event_counts`, `episode_time_s`, `raw_summary.cycles[]` with each
cycle's prompt bundle, raw output, parsed actions and failure event). Everything
else is `print` to stdout. **No JSONL, no per-event timestamps, no seed, no git
commit, `max_replans` not recorded.**

Configuration: no config system. `LLMPipelineConfig` (pipeline.py:59) + argparse
in `trial_runner.py` are the natural home for the plan.md Section 0.7 flags;
`configs/benchmark_defaults.json` exists but is not read by `trial_runner`.

## 10. Failure codes in use

Defined as strings in `failure_logic.py` (`LAYER_1_FAILURE_IDS` :19,
`LAYER_2_FAILURE_IDS` :44, `failure_layer_for_id` :61) and emitted from
several modules; types in `pipeline_types.py` (`FailureStage` :16,
`FailureSource` :21, `FailureLayer` :31, `FailureEvent` :174).

- Layer 1 (emitted): `pick_object_missing, lid_missing, geometric_discovery_fail,
  invalid_executor_state, empty_pick_trajectory, empty_place_trajectory,
  lid_hover_planning_fail, lid_slide_planning_fail, pddl_no_plan, no_ik_solution,
  no_motion_plan, no_grasp_found, executor_failure, unknown_action_token,
  pick_place_mismatch, orphan_place, missing_post_pick_place`.
  Listed but never emitted: `missing_preceding_move, invalid_move_target,
  unsupported_action, consecutive_moves, dangling_move`.
- Layer 2: `grasp_failed, object_dropped, object_did_not_move,
  object_missing_after_place, placement_failed, geometric_placement_failed,
  lid_not_open_enough, lid_not_closed_enough, new_object_discovered,
  grill_lid_closed, box_lid_closed, box_lid_obstructed, goal_not_satisfied`.
- Outside both sets: `planner_output_too_verbose, planner_output_not_parseable`
  (vlm_planner.py), `goal_validation_failed` (metrics.py:499),
  `TAMP_EXECUTION_ERROR / TAMP_OPEN_ERROR / TAMP_CLOSE_ERROR` (evidence only),
  `DEBUG_EXECUTION_ERROR`, cycle `error_message` values `planning_failed`,
  `planner_returned_no_actions`.
- Event classification for metrics: `metrics._event_type_for_failure_event`
  (:438) → `discovery, goal_validation_failure, structural_failure,
  pre_execution_failure, runtime_failure, post_execution_failure`.

The paper's failure taxonomy (15 conditions in 4 families: motion planning,
scene accessibility, execution deviation, plan inconsistency) is **Table II** in
both `IROS_Project-5.pdf` and `RA_L_Project-1.pdf` (Table I there compares
frameworks). Every condition in it has a matching code above.

## Phase 1 changes (steps 2–5c)

| Area | What changed | Where |
|---|---|---|
| Failure codes | One `FailureCode` enum. Code values equal the `failure_id` strings in `record.json`. Each code records its check (`plan_check`, `pre_action_check`, `execution_failure`, `trigger`, `goal_check`, `evaluation`, `replan`, `infrastructure`, later-phase checks) and its failure-taxonomy condition (Table II). `LAYER_1/2_FAILURE_IDS` are derived from it, and all `llm_pipeline`/`evaluation` modules use it | `llm_pipeline/failures.py` |
| Flags | plan.md Section 0.7 flags plus `termination.mode` and `prompt.version`. Set with `--flag name=value`. Values of flags whose phase is not built yet are rejected | `llm_pipeline/flags.py`, `LLMPipelineConfig.flags` |
| Trial log | `trial_log.jsonl` next to `record.json`, plus `prompts/` holding one file per planner call. Events: `trial_start`, `observation` (one `step` per observation: at every planning event except a plan-check re-query, and after every bundle), `planning_event`, `plan_check`, `pre_action_check` (via `LoggingFailureChecker`), `action_start`/`action_end` (executor hooks), `trial_end`. `validate_trial_log` checks the schema. `record.json` is unchanged | `llm_pipeline/trial_log.py`, `pipeline.py`, `executor.py`, `trial_runner.py` |
| Termination | `termination.mode=agent` (default): `_deterministic_goal_completion_from_scene` returns `None`, so the evaluator never runs inside the loop. `evaluator` keeps the previous override. The reason a trial ended is recorded as `pipeline.termination_reason` | `pipeline.py` |
| Completed actions | Replan prompts take the executor's cumulative list, instead of concatenating the per-cycle cumulative lists, which duplicated actions | `pipeline.plan_once` |
| Partial observability | Before every planner call the parser gets `observed_objects()`: the adapter's `known_visible`, plus the objects of earlier observations, plus the scene's lids. Only those names go to the planner server (`valid_objects`). Actions on other scene objects are rejected as `unobserved_object`, shown to the planner exactly like an unknown name | `strict_parser.py`, `client.py`, `pipeline.py` |
| Evaluator | Label-based rules for the Phase 3 scene files: `raw_meat`/`cooked_meat`, cooking cycles, overcooked, served raw, and the phone vs the placement area. They are used only for variants in `LABELED_RULE_VARIANTS`, which is empty today. `meat_procedure_status` is the single procedure implementation, for Phase 4 to reuse with agent-only inputs | `evaluation/labeled_rules.py` |
| Metrics | Task success rate and partial goal completion as plan.md defines them, over evaluated trials. Infrastructure trials are excluded and counted. Both are added to the aggregate summaries | `evaluation/metric_definitions.py`, `evaluation/metrics.py` |
| Prompts | `prompt.version=v2` (`PromptV2Builder`) is the default; legacy stays available. v2 requests disable the server-side format-repair call | `llm_pipeline/prompt_v2.py`, `docs/PROMPTS.md` |
| Smoke test | Full-pipeline trial with a ground-truth oracle planner, no GPU | `llm_pipeline/oracle_trial_runner.py` |

## External baselines

Source: `https://github.com/Narendhiranv04/GRAB-TAMP`, branch `baseline_executions`, commit `f2976cc`. It is cloned read-only into `external/GRAB-TAMP`, which is git-ignored. Nothing was run or modified.

| | VLM-TAMP | OWL-TAMP | EPoG-TAMP |
|---|---|---|---|
| Where | `vlm_tamp_baseline/` (`planner.py`, `prompt.py`, `executive.py`, `pddlstream_refiner.py`, `pddl/*.pddl`) | `owl_tamp_baseline/` (`planner.py`, `domain.py`, `constraints.py`, `refinement.py`, `replanning.py`, `receding_horizon.py`); reimplemented from arXiv:2411.08253, no official code | **Not in the repository** (no match for "epog"). Closest: `llm3_baseline/` (LLM3, kitchen only) and `retrieval_baseline/` (CLIP, no LLM) |
| One episode | `python -m vlm_tamp_baseline.run_kitchen --variant K1 --output-dir <dir> --seed 0 [--camera-count 1\|3\|5] [--physical-execution]` | `python -m owl_tamp_baseline.run_kitchen --variant K1 --output-dir <dir> --seed 1 [--protocol native\|replanning\|receding_horizon]` | — |
| Method | 1. The VLM turns images plus the goal into English subgoals.<br>2. A second call turns those into formal predicates.<br>3. PDDLStream refines each subgoal.<br>4. On a failure, it re-prompts with a typed failure code | 1. One VLM call gives an action sketch plus goal literals.<br>2. One constraint call per action (a geometric DSL).<br>3. Search, then sampling.<br>4. The native protocol is single-shot (never replans) | — |
| Planner model | Any OpenAI-compatible `/chat/completions` server (`VLM_TAMP_MODEL_BASE_URL`, `--model`). Default `qwen35-9b`; `qwen3-vl-8b-thinking` is available in `inference_server/models.json` | Same (`OWL_TAMP_*`) | — |
| Scenes and robot | Their own MuJoCo scenes (kitchen K1–K12, living room L1–L10, workshop W1–W10; YAML variant configs in `mujoco_scenes/configs/`) with a Google Robot and their own skills (`mujoco_scenes/tamp/`) | Same | — |
| Output | Per-episode directory: `model_calls/`, `episode_result.json`, `benchmark_execution_result.json`, a plan-vs-GT comparison. Distilled into `logs/*_action_sequences.jsonl` | Same (`model_trace.json`) | — |

What it would take to run them on our final variants and log in our JSONL schema:
1. **Observation adapter** from our scenes to their `baseline_common.models.Observation`: alias-annotated camera images from our segmentation, plus the textual state.
2. **Executor adapter** implementing their `Executor` protocol on top of our `DirectPrimitiveExecutor` (pick/place/open/close). `baseline_common/execution.py` imports their MuJoCo skills directly, and `physical_benchmark.write_execution_result` rejects scenes other than kitchen, living_room and workshop.
3. **VLM-TAMP:** new PDDL domain and stream files and samplers for our kitchen and grill. This is the largest item.
4. **OWL-TAMP:** grounding and constraint helpers for our geometry. It must run with `--protocol replanning` to ever see hidden objects.
5. **Model access:** either their own vLLM server with our planner model, or an OpenAI-compatible endpoint on our planner server.
6. **Export** of each episode to `trial_log.jsonl` (`trial_start` … `trial_end`) so our metrics and diagnostics apply.
7. **EPoG-TAMP:** implement from the paper, or choose a replacement (question in `docs/BASELINES.md`).

---

## Gaps and risks

1. **(Resolved: `termination.mode=agent`, goal check off.) Evaluator ground truth drives the stop condition.** With `--goal-check`,
   `_check_goal_completion_with_deterministic_override` (pipeline.py:734) runs
   the evaluator inside the loop and overrides the planner model; a failed
   evaluation also becomes a `goal_not_satisfied` replan trigger. This conflicts
   with plan.md Phase 1 step 4 ("scoring only; never by the agent"). Open
   question 9.
2. **Evaluator input is the agent's own final scene state, not independent
   ground truth.** `final_object_region_map` only contains objects the
   segmentation has seen; unseen objects score as `unknown`. Regions do come from
   simulator poses.
3. **(Partly resolved in step 5b: never-observed objects no longer reach the planner or pass the plan check; lid states stay as a documented stand-in; previously seen but now hidden objects still carry live simulator regions in the legacy prompt, which Phase 2 memory replaces.) Simulator state leaks into the planner-visible state.** Regions of all
   seen objects use simulator poses and AABBs; objects no longer visible keep
   live simulator regions (`tracked_non_visible_objects`, pipeline.py:551–561);
   lid states come from simulator joint and pose values; the symbol registry
   includes hidden objects, so the plan check accepts actions on never-observed
   objects. Phase 2 memory and the Phase 4 IF rule require agent-only
   information.
4. **Scene contents do not match plan.md 0.3.** The phone is in the grill
   scenes (G1, G3) and not in the kitchen; meats are named `chicken`, `steak`,
   `steak1`, not `raw_meat`/`cooked_meat`; the evaluator requires
   `phone → table` in G1/G3. Scene changes are Phase 3 (after `docs/VARIANTS.md`
   approval); Phase 1 evaluator updates must therefore work on the current
   names, or wait.
5. **Cooking exists only as action-history inference, in two separate
   implementations** (metrics.py:354 evaluator, grill_geometry.py:101 agent).
   No overcooked logic; meats starting inside the grill are assumed cooked; the
   cycle does not check that the meat stayed inside during the close→open.
   Phase 1 step 4 and Phase 4 "goal-attained" need one shared function fed with
   different inputs.
6. **(Resolved: `trial_log.jsonl`; `local_retries_used` is logged as null because adapter-internal retries are not counted yet.) No structured logging.** One JSON at trial end; no events, timestamps,
   per-action durations, adapter or local-retry counts, seeds, git commit, or
   flags such as `max_replans`. The JSONL log must be threaded through the
   pipeline, executor and checkers.
7. **(Resolved: `llm_pipeline/failures.py`; the keyword classifier `classify_runtime_error` is unchanged.) Failure codes are scattered strings** in 5+ modules, some defined but never
   emitted, and many runtime codes come from keyword matching on free-text
   adapter errors (`classify_runtime_error`); mapping these onto one enum
   without changing behavior needs care.
8. **Discovery trigger is hard-coded** (`replan_on_new_visibility=True`) and
   fires inside `postcheck`, mixed with failure detection. The IF rule (Phase 4)
   has to be separated from failure checking.
9. **(Resolved in prompt v2 and the completed-actions fix.) Full-replan prompt has no remaining plan or action ids**, which Phase 5
   insertion needs; `Completed Actions` in replan prompts contains duplicates
   because cumulative per-cycle lists are concatenated (pipeline.py:408–412 with
   :922) — a baseline behavior bug to confirm before fixing.
10. **No repeated-output detection** (plan.md Phase 7 area 8); e.g. a K3 trial
    repeats `pddl_no_plan` until the budget runs out.
11. **No placement-area definition or category config**; both are new config
    that Phase 3/4 require.
12. **Grill adapter is a 6 090-line file named `ground_truth_orchestrator_variation1 copy.py`**
    loaded dynamically by path; it is both the GT runner and the execution
    adapter, and hard to change safely.
13. **Unseeded, but decoding is greedy**; trial-to-trial variation comes from
    physics and segmentation timing. "Seed" in the log will mostly be nominal
    unless initial poses are randomized (open question 11).
14. **(Resolved.) Four unit tests fail on this base** (`test_repeated_runner.py`,
    `args.quantization` missing in `run_10_trials_and_aggregate.py`), on both
    simulator backends; unrelated to the MuJoCo port.
15. **Scene paths in `VariantSpec`** point at root-level `task1_variation*.ttt`;
    the MuJoCo port resolves them by file name, so moving scene files breaks both
    backends.

## Terminology conflicts with plan.md 0.6

Not renamed (Phase 1 step 1 is read-only).

| plan.md term | Code uses | Where (examples) |
|---|---|---|
| scene | `task_family` (`kitchen`/`grill`), `task_objects`, `grill_task*` modules | pipeline.py:85, canonical_variants.py:16, segmentation_object_detector.py:81 |
| trial | `episode` (`reset_episode_state`, `reset_episode`, `episode_success`, `episode_time_s`, `episode_success_rate`); `run` (`pipeline.run`, `run_dir`) | pipeline.py:306, executor.py:875, trial_runner.py:432, aggregate.py:67, evaluation/metrics.py:384 |
| replan | `cycle` (`ExecutionCycleRecord`, `cycle_number`, `total_cycles`), `checkpoint_type: replanning` | pipeline.py:116 |
| planner call | `planner_invocations`, `mean_planner_time_per_invocation_s` | pipeline.py:979, trial_runner.py:439, aggregate.py:121 |
| plan | `planned_actions`; `action_sequence_length`, `set_live_action_sequence`; legacy `skeleton`/`ActionSkeleton` | canonical_variants.py:18, segmentation_adapter.py:150, vlm_planner.py:128 |
| bundle | `chunks`, `_gt_macro_chunks` | pddl_trial_runner.py:738, debug_execution.py:274 |
| plan check / pre-action check | `FailureLayer.LAYER_1` / `LAYER_2`, `layer_1`/`layer_2` in logs and prompts, `structural_failure`, `precheck`/`postcheck` | pipeline_types.py:31, failure_logic.py:19/44 |
| irrelevant object | `non_target`, `GRILL_NON_TARGET_OBJECTS`, `implicit_non_target_handling_success` | metrics.py:19/562, aggregate.py:127 |
| overlapping object | `BLOCKED`/`OBSTRUCTED`, `blocking_objects_for_lid`, `box_lid_obstructed` (lid access, not placement areas) | geometric_builder.py:167, segmentation_adapter.py:514 |
| local retry | "Fallback" (home pose, full PDDL solve, interpolation), `_execute_with_retry` | executor.py:1296/1444, copy.py:4344 |
| execution failure | "motion planner failed", `TAMP_EXECUTION_ERROR` | copy.py:4344, executor.py:388 |
| action | `subtask`/`bucket` in the old metric; GT `stage`s (`move`, `pick`, …) inside an action | metrics.py:140, executor.py:489 |
| step | `step` means simulator step (`_on_sim_step`, `_sim_step_counter`, `step(pr, n)`) — plan.md uses it for the observation counter | pipeline.py:1086, copy.py:181 |
| goal | `goal_text` (consistent); GT orchestrators print "TASK: …" headers | ground_truth_orchestrator.py |

New gaps found during Phase 1 (details in the Phase 1 report):

16. **(Resolved: `grasp.confirmation=gripper_state`.) The grasp post-check misfires on MuJoCo.** `grasp_failed` is reported when the grasped object is visible only in the wrist camera, because the gripper never appears in the wrist camera's mask. The robot then holds the object while the pipeline believes the gripper is empty, and later picks of that object fail with `pddl_no_plan` until the replan budget runs out. It was observed in K1 (`can_of_beans`). It is rare on CoppeliaSim.
17. **(Resolved for the plate: G3 GT 10/10 after the fix.) G3 ground-truth execution was flaky on MuJoCo.** Root cause: after release the grill executor let the object fall freely for 30 steps (1.5 s) before freezing it and attaching it to the plate; the drumstick (convex pieces, no rolling resistance) rolled off the small convex plate in about half of the runs. Plate-top placements now use a 6-step drop (`GRILL_PLATE_TOP_DROP_STEPS`). `place(mug3, table_staging_area)` is occasionally rejected by the geometric containment post-check.
18. **(Resolved: pushed to `naren/variants-scenes-execution` as 748a27ba.) `mujoco_port/tools/` was not pushed** with the MuJoCo port (the root `.gitignore` has a blanket `tools/` rule). It is committed on `phase-1-logging` and missing from `naren/variants-scenes-execution`.
19. **EPoG-TAMP is missing** from the external baseline repository, and the other ports are tied to their own scenes and robot.
