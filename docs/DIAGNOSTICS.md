# Diagnostics: where things go wrong (plan.md Phase 7)

`python -m diagnostics.report <result dirs> --out <dir>` reads every `trial_log.jsonl` (and the `record.json` beside it) and reports, per condition and per variant, the share of trials in each of 8 failure areas. The implementation is `diagnostics/report.py`; the tests with one hand-made log per area are in `diagnostics/tests/test_report.py`.

## 1. Failure areas

| # | Area | Plain definition | Detected from (trial log) |
|---|---|---|---|
| 1 | Plan format error | The planner output can't be read, or uses an unknown action, object, region or block field | `plan_check` fail with a format code: `planner_output_not_parseable`, `planner_output_too_verbose`, `unknown_action_token`, `unobserved_object`, `unsupported_action`, `invalid_corrective_block` |
| 2 | Plan rule error | Readable but breaks the action rules (place without pick, pick while holding, pick from a closed region, ...) | `plan_check` fail with any other plan-check code; `pre_action_check` fail |
| 3 | Corrective sub-plan error | The replan's actions don't resolve the trigger: at the end of the trial a trigger object is not where the goal needs it (wrong destination, missed object, phone left in a placement area) | accepted `insertion` + `trial_end.missing` naming a trigger object |
| 4 | Insertion error | Wrong urgency or position: too late (`insertion_too_late`, overcooked meat, a hard constraint violated) or too early (raw meat plated before cooking) | `insertion` rejections; evaluator procedure checks in `trial_end.missing` after a replan |
| 5 | Task plan error | The plan leads to an unmet goal with no other error to blame (includes a failed trial with no replan) | `trial_end.missing`, nothing else unrecovered |
| 6 | Motion/grasp error | An action failed after all local retries | `action_end` with `outcome = failure` and an execution-failure code |
| 7 | Merge conflict | A merged plan conflicted with what was executed during the wait (Phase 6) and was not resolved | `parallel` with `merge_result = merge_conflict` |
| 8 | Replan budget exhausted | The replan limit was reached (or the same output came back for the same state) with no earlier unrecovered error | `trial_end.termination_reason = replan_budget_exhausted` |

Infrastructure problems (planner server down, simulator crash; `termination_reason = infrastructure`, or no `trial_end`) are excluded from every percentage and counted separately.

## 2. Counting rules

- **Primary cause** (one per trial; rows sum to 100% with successes): the **first error never recovered from**. Errors are taken in log order:
  - a plan-check error is recovered when a later plan check passes;
  - an insertion rejection or merge conflict is recovered when a later insertion is accepted;
  - an action failure is recovered when the same action later succeeds.
  
  A failed trial with no unrecovered error gets:
  - area 4 when an evaluator procedure or hard-constraint check failed after a replan (area 5 without a replan);
  - otherwise area 3 when an accepted corrective sub-plan's trigger object is named in the unmet goal;
  - otherwise area 8 when the replan budget ran out;
  - otherwise area 5.
- **Occurrences** (can overlap): the share of trials in which each area happened at least once, recovered or not (e.g. an `insertion_too_late` fixed by a re-query).
- **Trigger accuracy** (a system check, not a failure area): the share of trials whose triggered objects match the variant spec. Every object with an expected IF decision other than `ignore` triggered, and no `ignore` object triggered. In `discovery` mode the triggered objects are those of `new_object_discovered` replans; in `if_rule` mode, those of the `if_check` events.
- **First-proposal urgency accuracy**: for the first corrective proposal of a trial (accepted or not), the share of trigger objects whose proposed urgency equals the variant spec.

Both tables are written per condition and per variant. A condition is the planner model plus the flags `memory.enabled`, `replan.trigger_mode`, `replan.output_mode`, `replan.insertion_mode`, `parallel.enabled`.

## 3. Log excerpts per area

Real excerpts come from the oracle runs where the area occurred. The oracle planner always outputs readable, rule-abiding plans for the right objects, so areas 1, 2, 3, 5 and 7 did not occur. Their excerpts come from the hand-made logs in `diagnostics/tests/test_report.py` (marked *test log*).

| # | Excerpt | Source |
|---|---|---|
| 1 | `{"event": "plan_check", "result": "fail", "failure_codes": ["planner_output_not_parseable"]}` | test log |
| 2 | `{"event": "plan_check", "result": "fail", "failure_codes": ["orphan_place"]}` | test log |
| 3 | accepted `insertion` for `phone`, then `trial_end.missing = ["phone is in the inside_box placement area"]` | test log |
| 4 | `{"event": "insertion", "step": 5, "urgency": {"phone": "urgent"}, "insertion_point": {"phone": "front"}, "accepted": false, "rejection_code": "insertion_too_late", "rejection": "place(mug1, inside_box) places into inside_box while phone is still in its placement area"}` (the proposal was urgent/front; `always_end` moved it to the end) | `results/phase5/always_end/FINAL.K1/seed_00` |
| 4 | `trial_end.missing = ["cooked_meat_1 overcooked: inside the grill during a close->reopen cycle after it was cooked", "HC-grill violated: cooked_meat_1 inside the grill at close(grill_lid) after it was cooked"]` | `results/phase5/always_end/FINAL.G1/seed_00` |
| 5 | failed trial, no replan, `trial_end.missing = ["mug2 is in table, expected inside_box"]` | test log |
| 6 | `{"event": "action_end", "step": 6, "action": "pick(spam)", "outcome": "failure", "failure_code": "grasp_failed"}` (recovered: the pick succeeded after the replan) | `results/phase3/oracle_ceiling/FINAL.K1-w2/seed_00` |
| 7 | `{"event": "parallel", "merge_result": "merge_conflict"}` | test log (and `llm_pipeline/tests/test_parallel.py`) |
| 8 | `trial_end.termination_reason = "replan_budget_exhausted"` with no unrecovered error before it | test log |

## 4. Results so far (oracle planner)

`results/diagnostics/` (324 trials: the Phase 3 ceiling, Phases 4–6, the old-variant regression). Every failed trial has exactly one primary area; there are none unassigned.
- All failures are in the insertion-mode ablations (area 4).
- Motion/grasp errors occurred and were recovered in 11 kitchen trials.
- Trigger accuracy is 100% in `if_rule` mode and 92.9% in `discovery` mode (the K2 trials).

These numbers check the pipeline, not a planner model; the real distribution comes from the Phase 8 runs.
