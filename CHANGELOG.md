# Changelog

One entry per phase of `plan.md`: what changed, which flags, which tests.

## Phase 2: observation memory (branch `phase-2-memory`)

### Changed (all behind `memory.enabled`, default `false`)
- `llm_pipeline/memory.py`: `MemoryEntry(object_id, last_seen_step, last_region)` and `ObservationMemory`.
  - Updated after every observation: visible objects are created or overwritten; hidden objects keep their entry; entries are never deleted; never-observed objects are never stored.
  - A held object is remembered in region `gripper`.
- Trial log:
  - `memory_snapshot` (the full table) at every observation;
  - `memory_mismatch` (diagnostic only) when a remembered object's last region is visible and open but the object is not seen there.
- Prompt v2: a "Remembered objects (not currently visible): last region, steps since last seen" block after the visible objects. The legacy prompts are unchanged.
- Plan check: remembered objects are known objects. A `pick` of a remembered object whose last region is closed off by a lid that is closed at that point of the plan is rejected (`remembered_object_inaccessible`).
- Pre-action check: a remembered object that is not visible may be picked when its last region is reachable now.

### Tests
`test_memory.py` (10 tests):
- create, overwrite, keep-when-hidden and never-delete;
- never-observed objects are not stored;
- a held object is remembered in the gripper;
- a kitchen object revealed by opening the box stays in memory after it is hidden;
- mismatch conditions;
- plan-check reachability;
- grill: after `close(grill_lid)` the meat stays in memory (`inside_grill`) and appears as remembered in the next prompt;
- remembered picks are allowed only when the region is reachable;
- flag-off regression: no memory events and no remembered block.

`test_prompt_v2.py` gains a golden snapshot of the remembered block.

### Runs
- `results/phase2/oracle_memory/`: oracle planner with `memory.enabled=true`, 6 variants × seeds 0–1, 12/12 successful, no memory mismatches.
- Note: the segmentation detector keeps an object "visible" for up to 30 frames after it was last seen (`LIVE_SEG_PERSIST_FRAMES`), so an object can stay visible for one observation after its container closes.

## Phase 1: repository map, logging, evaluator, prompts (branch `phase-1-logging`)

**Not finished yet:** step 6 (the baseline run) is still to come.

### Changed
- **Step 1:** `docs/ARCHITECTURE.md`, a map of the pipeline with gaps and risks.
- **Step 2:** `llm_pipeline/failures.py`, a single `FailureCode` enum.
  - The values are the existing `failure_id` strings, so `record.json` is unchanged.
  - Each code records its check (plan_check, pre_action_check, execution_failure, trigger, …) and its condition in the failure-taxonomy table (Table II).
  - All `llm_pipeline` and `evaluation` modules report through it.
  - New codes: `unobserved_object`, `planner_call_failed`, `simulator_error`, `replan_budget_exhausted`. Reserved for later phases: `repeated_planner_output`, `memory_mismatch`, `insertion_too_late`, `anchor_already_executed`, `merge_conflict`.
- **Step 3:** `llm_pipeline/trial_log.py`, a per-trial `trial_log.jsonl`.
  - Each trial also gets `prompts/`, one file per planner call.
  - `trial_runner` gains `--seed` (default: the trial index; it seeds `random` and `numpy`) and `--flag`. It logs the git commit and all flags.
  - `run_10_trials_and_aggregate.py` passes `--flag` and `--seed-base` through.
- **Step 4:** `evaluation/labeled_rules.py`, label-based `raw_meat`/`cooked_meat` rules.
  - Covers cooking cycles, overcooked (fails that meat's procedure check), served raw, and the phone vs the box placement area.
  - Applies only to variants listed in `LABELED_RULE_VARIANTS`, which stays empty until the Phase 3 scene files exist. Today's variants keep `llm_pipeline.metrics` unchanged, including phone → table in G1/G3.
- **Step 5:** `evaluation/metric_definitions.py` defines task success rate and partial goal completion as in plan.md. Aggregate summaries gain `task_success_rate`, `partial_goal_completion`, `evaluated_trials` and `infrastructure_trials`.
- **Step 5b (partial observability):**
  - Never-observed objects are no longer sent to the planner server, and the plan check rejects them (`unobserved_object`). The planner sees the same message and code as for a name that does not exist.
  - Lid states from joint and pose values are documented as a stand-in for perception.
- **Step 5c (prompt rewrite):** `llm_pipeline/prompt_v2.py`, documented in `docs/PROMPTS.md` and awaiting approval.
  - The server's VLM path skips its hidden format-repair call for v2 requests (`PlanRequest.prompt_version`).
  - The v2 builder keeps the 5-camera composite image.
- **`termination.mode=agent`:** `_deterministic_goal_completion_from_scene` no longer runs inside the loop.

### Fixed
- **Duplicated completed actions (bug fix).** Replan prompts listed completed actions more than once after two or more cycles. `plan_once` concatenated the executor's cumulative list from every cycle; it now uses the executor's list once.
- **`NO_ACTIONS` on the VLM path.** A bare `NO_ACTIONS` answer was reported as unparseable by the legacy VLM parser. The client now re-parses it with the strict parser.
- **Repeated-runner tests.** Four tests failed because their argparse fixture lacked `quantization` (separate commit).
- **`mujoco_port/tools/` was never committed.** The root `.gitignore` has a blanket `tools/` rule; an exception was added.

### Changed after the STOP POINT 1 review
- `grasp.confirmation=gripper_state`: a pick is confirmed from the gripper's grasp state (grasped or attached object, or finger contact with the fingers not fully open) instead of mask proximity (`failure_logic.held_objects_from_gripper`).
- `scene.randomization=pose_jitter`: seeded +/-3 cm, +/-20 degree jitter of each variant's free objects, overlaps rejected, fixed objects kept (`llm_pipeline/randomization.py`); seeds 0-9 per variant.
- Grill plate-top placements drop for 6 steps instead of 30 before being frozen on the plate (`GRILL_PLATE_TOP_DROP_STEPS`); G3 ground truth 10/10 instead of about 50%.
- Prompt v2 parses only after the last `FINAL ACTIONS:` line; the reasoning is logged (`planning_event.reasoning`).
- `llm_pipeline/run_trial_matrix.py`: seeded oracle/model trial matrices with per-variant summaries.
- Executor fixes found by the executor-ceiling run (oracle planner, target 100%):
  - Kitchen box placements pad by the object's half-footprint plus 1 cm: mugs were placed against the box walls and knocked out by later placements.
  - Kitchen staging-area and cupboard placement branches in `sample_stable_pose` compared against pre-normalization region names and never ran, so those placements ignored occupied spots.
  - Grill plate-top placements lower the released object kinematically until it touches the plate (`GRILL_PLATE_TOP_SETTLE=kinematic`, fallback `drop` = 6-step drop): meat that tipped over in the grill tumbled off the plate.
  - The oracle planner re-picks an object before placing it after a failed place.
- Prompt v2 uses neutral region names (`table_center_area`, `table_right_area`, `grill_side_area`); the parser maps them back, logs keep canonical names.
- plan.md 8.3: external baselines become re-implementations inside our pipeline.

### Flags
| Flag | Values | Default |
|---|---|---|
| `termination.mode` | `agent`, `evaluator` | `agent` |
| `prompt.version` | `v2`, `legacy` | `v2` |
| `grasp.confirmation` | `gripper_state`, `segmentation` | `gripper_state` |
| `scene.randomization` | `pose_jitter`, `off` | `pose_jitter` |

The Section 0.7 flags of later phases accept only their defaults for now. In-context examples are off: `--icl-mode` defaults to `zero_shot`, and v2 refuses few-shot.

### Tests
The suite has 195 tests; 49 are new, with the files below.
- `test_failures_and_flags.py`: covers the taxonomy table, the legacy layers staying unchanged, string serialization, and the flag defaults and rejections.
- `test_phase1_pipeline.py`:
  - JSONL schema validity for a scripted trial;
  - step counting, including plan-check re-queries sharing a step;
  - action ids in replan prompts;
  - no duplicated completed actions;
  - an unseen object cannot appear in any prompt: prompts are byte-identical whether or not it exists in the scene;
  - the plan check rejects unobserved objects;
  - the server payload never contains them;
  - `termination.mode` agent vs evaluator.
- `test_labeled_rules.py`: hand-made histories (correct cycle, served raw, overcooked after two cycles, cooked meat left in the grill, meat removed before closing), grill and kitchen goal scoring, and the metric definitions.
- `test_grasp_and_randomization.py`: gripper-state grasp confirmation (grasped, tip-parented, not held, previous behavior) and seeded, bounded pose jitter with overlap rejection and fixed objects.
- `test_prompt_v2.py`: golden snapshots for the system, initial, replan and goal-check prompts in both scenes; one template for both scenes; no strategy hints or banned content; ICL refused.

Integration checks, with the GT oracle planner and no model:
- `llm_pipeline/oracle_trial_runner.py` ran K1 and G2 through the full pipeline on MuJoCo. Both logs validate.
- G2 succeeded. K1 failed because of the `grasp_failed` misfire (gap 16 in `docs/ARCHITECTURE.md`).
