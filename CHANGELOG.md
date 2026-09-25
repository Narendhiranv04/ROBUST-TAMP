# Changelog

One entry per phase of `plan.md`: what changed, which flags, which tests.

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

### Flags
| Flag | Values | Default |
|---|---|---|
| `termination.mode` | `agent`, `evaluator` | `agent` |
| `prompt.version` | `v2`, `legacy` | `v2` |

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
- `test_prompt_v2.py`: golden snapshots for the system, initial, replan and goal-check prompts in both scenes; one template for both scenes; no strategy hints or banned content; ICL refused.

Integration checks, with the GT oracle planner and no model:
- `llm_pipeline/oracle_trial_runner.py` ran K1 and G2 through the full pipeline on MuJoCo. Both logs validate.
- G2 succeeded. K1 failed because of the `grasp_failed` misfire (gap 16 in `docs/ARCHITECTURE.md`).
