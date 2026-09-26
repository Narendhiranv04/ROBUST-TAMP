# Changelog

One entry per phase of `plan.md`: what changed, which flags, which tests.

## Phase 7: diagnostics (branch `phase-7-diagnostics`)

### Changed
- `diagnostics/report.py`: the 8 failure areas of plan.md 7.1 from the trial logs. It writes `diagnostics_primary.csv` (first unrecovered error; sums to 100% with successes), `diagnostics_occurrences.csv`, `diagnostics_trials.csv`, `summary.md` and `primary_causes.png`, per condition and per variant, plus trigger accuracy and first-proposal urgency accuracy. Infrastructure trials are excluded and counted.
- `docs/DIAGNOSTICS.md`: definitions, counting rules, log excerpts.

### Tests
`diagnostics/tests/test_report.py` (11): one hand-made log per area, a multi-error trial for the first-unrecovered-error rule, success/infrastructure/trigger accuracy, and the report files.

### Runs
- `results/diagnostics/`: 324 oracle trials (Phases 3–6 and the old-variant regression); every failed trial has exactly one primary area (none unassigned). Failures appear only in the insertion-mode ablations (area 4). Recovered motion/grasp errors (area 6 occurrences) in 11 kitchen trials: 7 `grasp_failed`, 4 `pddl_no_plan` on a pick, each fixed by a retry after the replan. Trigger accuracy: 100% in `if_rule` mode, 92.9% in `discovery` (the 10 K2 trials, where discovery replans on the ignored phone).
- `evaluation/phase8_budget.py`: Phase 8 compute estimate from the smoke-test timings (or assumed ones) and a trimmed matrix for a time budget.

## Phase 6: WHEN, parallel planning and execution (branch `phase-6-when`)

### Changed (behind `parallel.enabled`, default `false`; needs `replan.output_mode=corrective`)
- `plan_once` split into `_prepare_planning` (main thread), `_call_planner` (thread-safe) and `_finish_planning` (main thread); behavior unchanged with the flag off.
- `llm_pipeline/parallel.py`: affected set (trigger objects and their regions, their goal regions, parking regions per scene, lids of affected regions) and independent bundles (no affected object or region, no shared object or region with an earlier dependent bundle).
- `pipeline._plan_in_parallel`: independent actions are listed as completed in the prompt; the planner call runs in a background thread; independent bundles execute one at a time until it returns; the merge uses the updated remaining plan (`anchor_already_executed` → front); a merged plan invalidated by what ran meanwhile is `merge_conflict` → re-query; a failed independent bundle is handled first (full replan). New triggers during the wait are evaluated after the merge.
- `parallel` trial-log event: affected set, independent actions available/executed, planner latency, robot busy and idle time, merge result.
- Oracle: `--planner-delay` (simulated planner latency).
- Parking regions (Section 10, Q10) are a default until you decide: kitchen `table`, `table_staging_area`; grill `table`, `prep_area`.

### Tests
`test_parallel.py` (7): affected set and independent bundles for the kitchen phone and the grill; independent actions run during a delayed planner call and affected ones do not; urgent block runs right after the wait; executed anchor → front, logged; injected conflict → `merge_conflict` → re-query; trigger never evaluated while holding; flag-off equals Phase 5.

### Runs (`results/phase6/`, report `results/phase6/report.md`)
- Oracle planner with a simulated 20 s planner latency, 14 variants × seeds 0–1, parallel on and off: 56/56 successful, no merge conflicts.
- Robot idle time per replan, off → on: K1 / K1-w1 / K1-w2 20 → 0 s; grill variants 20 → about 12 s (the plate move runs during the wait); K3, K4, K3-n2/n3 stay at 20 s (the trigger can's goal is the cupboard, so the grocery moves wait).
- C2 sweep: independent bundles available 2 / 3 / 4 (w = 0 / 1 / 2), but 2 are executed in each: two bundles (10–12 s each) cover a 20 s wait. The trend in w needs the real planner latency. Trial times vary by about ±15 s between seeds, so trial-time savings from 2 seeds are noisy.
- Parking regions (Q10, decided): only the dedicated areas (`table_staging_area`, `prep_area`); with the whole table as a parking region, every pick from the table would wait during a replan.

## Phase 5: WHERE, corrective sub-plans, urgency, insertion (branch `phase-5-where`)

### Changed (behind `replan.output_mode`, default `full_replan`, and `replan.insertion_mode`, default `planner`)
- `llm_pipeline/corrective.py`: block format (`FINAL BLOCKS:`), strict parser (listed trigger objects only, urgency, insertion point, urgent ⇒ front, known anchor ids, actions only on the block's objects), insertion modes (`always_front`, `always_end` override the model), merge (urgent blocks at the front in order; deferred after their anchor or at the end; remaining actions keep their ids), placement-conflict check (`insertion_too_late`).
- Prompt v2: corrective system prompt and a "What to plan" section (docs/PROMPTS.md §6, for review). The remote client passes block output through unparsed.
- Pipeline: a replan answering an `if_rule_trigger` is corrective; rejections re-query with the reason (plan-check re-query: same step, counts toward the budget). `insertion` trial-log event per proposal. Execution-failure replans stay full replans.
- New codes: `invalid_corrective_block`; `insertion_too_late`, `anchor_already_executed`, `merge_conflict` are now emitted.
- Oracle: blocks from the ground truth with the variant spec's urgency (an urgent meat is parked on the table and plated after the plate reaches the serving area).

- Prompt (decided): the urgency sentence is neutral; the plan.md 5.2 examples are behind `prompt.corrective_hints=on` (default `off`).

### Tests
`test_corrective.py` (16) and `test_if_where_pipeline.py` (7): valid and malformed block lists; merge front / after-id / end with several blocks; K1/K3 deferral past the next box placement → `insertion_too_late`; G1 deferral past `close(grill_lid)` not blocked by the system but overcooked by the evaluator; `always_front` / `always_end` overrides; re-query after rejection with `first_proposal` logged; neutral prompt by default, hints behind the flag. Golden snapshots of the corrective prompt.

### Runs (`results/phase5/`, report `results/phase5/report.md`)
- `insertion_mode=planner`: 14 variants × seeds 0–1, 28/28 successful; first-proposal urgency accuracy 100% (the oracle takes the spec's urgency, so this checks the mechanics, not a model).
- Ablations on K1, K3, K4, G1, G2, G3 (seed 0): see the report. `always_end` fails K1/K3 (`insertion_too_late` until the budget) and G1/G2 (HC-grill, overcooked); `always_front` fails G2/G3 (raw meat plated before cooking). The rest succeed.

## Phase 4: IF, the replan trigger rule (branch `phase-4-if`)

### Changed (behind `replan.trigger_mode`, default `discovery`)
- `llm_pipeline/if_rule.py`: the rule of plan.md 4.1 (relevant from the scene's goal categories, Q8 default; goal-attained with the evaluator's procedure logic on agent-only inputs; overlapping from system geometry; accounted for = in the remaining plan or a pending replan).
- Executor hook `set_trigger_check`: called after every bundle that leaves the gripper empty (a trigger mid-bundle waits for the bundle to finish).
- Pipeline: `_if_rule_check` logs `if_check` (per-object decision) after every bundle, and returns one `if_rule_trigger` for all trigger objects of the observation. The discovery trigger is switched off in this mode. The v2 replan prompt lists each trigger object with its labels.

- A meat on the plate counts as goal-attained once cooked: overcooking and plating before cooking cannot be undone and are left to the evaluator, instead of triggering replans until the budget runs out.

### Tests
`test_if_rule.py` (14): every row of the rule table in both scenes, overlap only for regions the remaining plan places into, meat procedure for goal-attained (overcooked meat on the plate does not trigger again), objects the robot placed itself are accounted for, all trigger objects of one observation together, pending/held objects, lids. Pipeline tests in `test_if_where_pipeline.py`.

### Runs (`results/phase4/`, report `results/phase4/report.md`)
- `trigger_mode=if_rule`, 14 variants × seeds 0–1: 28/28 successful. The rule triggers exactly once, with the specified objects, on K1, K3, K4, G1, G2, G3 and the C1/C2 variants (all n objects in one trigger); never on K0, G0, K2. Trigger accuracy 100%.
- `discovery` (the Phase 3 ceiling, seeds 0–1): trigger accuracy 100% except K2 (0%), where discovery replans on the non-overlapping phone.

## Phase 3: final variant set (branch `phase-3-variants`)

### Changed
- 14 final variants (`FINAL.<name>`; G1-n3 dropped, Q12), composed scenes, runtime setup, labeled evaluator on simulator ground truth, executor fixes found by the oracle, automated build checks, renderer restyle. Details: commit 5496d4a4, docs/VARIANTS.md, docs/ARCHITECTURE.md "Phase 3 changes".

### Tests
`test_labeled_rules.py` (15): Q2/Q3 rules, HC-box, HC-grill. `evaluation/check_final_variants.py` on all 14 scenes. `mujoco_port/tests/test_sleep.py` (2): resting-object hold.

### Runs
- Build checks 14/14; oracle ceiling 140/140 on the final variants (`results/phase3/`); old K1–K3, G1–G3 regression 60/60 (`results/executor_ceiling_regression/`).

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
