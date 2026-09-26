# ROBUST TAMP — Implementation Plan (handoff)

This is the working plan for the final ROBUST TAMP architecture. Work through it **phase by phase, in order**. Each phase ends with a **Definition of Done** and a **STOP** point: do not start the next phase until the user confirms.

---

## 0. Read this first

### 0.1 What the system is
ROBUST TAMP is a VLM/LLM-guided task-and-motion-planning pipeline for manipulation under partial observability:

1. Build a planner-visible scene state (objects, regions, articulation states) from perception.
2. Ask a planner model for an ordered action plan (`pick`, `place`, `open`, `close`).
3. Check the plan before execution.
4. Execute actions through scene-specific execution adapters (motion planning for pick/place, primitives for open/close).
5. Monitor results. When a container is opened (or anything else becomes visible), decide whether a replan is needed.

### 0.2 The final architecture: IF, WHEN, WHERE
The contribution is a structured answer to three questions about replanning:

| Question | Answer in this system | Decided by |
|---|---|---|
| **IF** a replan is needed | Only if an observed object is **(irrelevant AND overlapping)** OR **(relevant AND not goal-attained)**. Everything else is ignored. | System (deterministic rule) |
| **WHEN** the robot acts during a replan | While the planner model is generating the replan, the robot keeps executing remaining actions that do not involve the replan's region(s) and object(s). | System (scheduler) |
| **WHERE** the replanned actions go | The planner model returns a short **corrective sub-plan** for only that subgoal, plus its **urgency** (`urgent` / `deferred`) and **insertion point** in the remaining plan. | Planner model (VLM) |

The rest of the plan is **not** regenerated on a replan. Only the corrective sub-plan is generated and inserted.

### 0.3 Scenes (final versions)
- **Kitchen.** Goal: mugs → box, groceries → cupboard. Opening the box reveals its contents. A **phone** (irrelevant object) may appear **only inside the kitchen box**, either overlapping the box's placement area or not. A grocery (relevant) may also be inside the box, overlapping or not.
- **Grill.** Goal: cook all raw meat in the grill and serve all cooked meat on the plate in the serving area. There is **no phone** in the grill scene anymore. Meat objects are labeled by name: **`cooked_meat`** and **`raw_meat`**. Meat revealed inside the grill is **always non-overlapping** but always relevant.

### 0.4 Scope of this plan
| Phase | Change | Owner |
|---|---|---|
| 0 | Port all scenes to MuJoCo and verify execution | **User only — do not touch** |
| 1 | Repository map, unified logging, evaluator updates, baseline | Claude |
| 2 | Observation memory layer `<object, last_seen_step, last_region>` | Claude |
| 3 | Final variant set: audit, specs, approval, build | Claude (user approves) |
| 4 | **IF**: replan trigger rule | Claude |
| 5 | **WHERE**: corrective sub-plan, urgency, insertion, merge | Claude |
| 6 | **WHEN**: parallel planning and execution | Claude |
| 7 | Diagnostics: 5–8 failure areas with % of trials | Claude |
| 8 | Full evaluation run and ablations | Claude (with user) |

Implementation order is IF → WHERE → WHEN (not IF → WHEN → WHERE) on purpose: insertion must work correctly without concurrency before concurrency is added on top.

### 0.5 Ground rules
- **Never start before the Phase 0 gate is signed off by the user.** Until then, do nothing except read this plan.
- Work on a new branch per phase (`phase-1-logging`, `phase-2-memory`, ...). Small, reviewable commits.
- Every new behavior goes behind a **config flag** so previous behavior can always be reproduced (Section 0.7).
- Do not refactor code unrelated to the current phase.
- Do not modify MuJoCo scene physics or assets. Scene files may only be changed in Phase 3, after the user approves the variant specs.
- Write tests for every new component. Use a **mock planner** (deterministic outputs, configurable delay) so tests don't depend on GPUs.
- Use the terminology in Section 0.6 everywhere: code names, log fields, comments, docs. Do not introduce synonyms.
- When a design question comes up that this plan does not answer, **stop and ask**. Section 10 lists known open questions.
- Keep a `CHANGELOG.md` entry per phase: what changed, which flags, which tests.

### 0.6 Canonical terminology (use exactly these terms)
| Term | Meaning | Do NOT use |
|---|---|---|
| **scene** | An environment: `kitchen` or `grill` | domain, task (for the environment) |
| **variant** | A specific initial configuration of a scene | task variant, scenario |
| **goal** | The natural-language instruction for a scene | task, command, objective |
| **trial** | One run of one variant under one condition, from reset to end | episode, run |
| **condition** | A combination of planner model, prompting, and flags | setting |
| **action** | One symbolic step: `pick(o)`, `place(o, r)`, `open(c)`, `close(c)` | step, command |
| **bundle** | Actions executed together, e.g. `pick(o)`–`place(o, r)` | chunk, macro |
| **plan** | Ordered list of actions | action sequence, skeleton |
| **remaining plan** | The actions of the current plan not yet executed | — |
| **planner model** | The VLM/LLM that produces plans | FM, foundation model |
| **planner call** | One request to the planner model | query, invocation |
| **initial plan** | The first plan of a trial, from the initial visible state | — |
| **replan** | A planner call made after a trigger; it returns a corrective sub-plan | replanning cycle |
| **trigger** | The situation that makes the IF rule fire (Section 4) | cause |
| **trigger object** | An object that made the IF rule fire | — |
| **corrective sub-plan** | The short action list a replan returns for the trigger object(s) only | replanned sequence |
| **urgency** | `urgent` (insert at the front of the remaining plan) or `deferred` (insert later) | priority |
| **insertion point** | Where a corrective sub-plan goes: `front`, `after <action id>`, or `end` | — |
| **merged plan** | Remaining plan with corrective sub-plan(s) inserted | — |
| **plan check** | Checks on a plan or merged plan before execution | L1, parser validation |
| **pre-action check** | Checks just before each action against the current state | L2, scene check |
| **execution failure** | An action or bundle that failed after all local retries | motion failure |
| **local retry** | A retry inside the execution adapter (new grasp, trajectory, placement) | fallback |
| **visible state** | Objects currently observed, their regions, articulation states | s_vis (in code) |
| **memory** | Stored `<object, last_seen_step, last_region>` for every object ever observed | belief, world model |
| **relevant object** | Object whose category is referenced by the goal (mug, grocery, raw_meat, cooked_meat) | target object |
| **irrelevant object** | Object whose category is not referenced by the goal (phone) | non-target, distractor |
| **goal region** | The region an object must end up in | target region |
| **goal-attained object** | Relevant object in its goal region with its procedure complete | done object |
| **placement area** | The part of a region that the remaining plan's `place` actions into that region will use (defined per region in config) | — |
| **overlapping object** | An object whose footprint intersects the placement area of a region the remaining plan will place into | blocking object |
| **accounted-for object** | An object the remaining plan (or a pending replan) already has actions for | — |
| **overcooked** | A cooked meat (a `cooked_meat`, or a `raw_meat` that has completed one cooking cycle) that is inside the grill during another close→reopen cycle | — |

### 0.7 Configuration flags
| Flag | Values | Default until its phase is done |
|---|---|---|
| `memory.enabled` | `true` / `false` | `false` |
| `replan.trigger_mode` | `discovery` (every newly visible object triggers) / `if_rule` | `discovery` |
| `replan.output_mode` | `full_replan` (previous system: regenerate the whole remaining plan) / `corrective` | `full_replan` |
| `replan.insertion_mode` | `planner` (planner model decides urgency and insertion point) / `always_front` / `always_end` | `planner` |
| `parallel.enabled` | `true` / `false` | `false` |
| `termination.mode` | `agent` (the agent alone decides when the trial ends; the evaluator only scores) / `evaluator` (previous system: the evaluator's ground truth may drive the stop condition) | `agent` |
| `prompt.version` | `v2` (rewritten prompts, docs/PROMPTS.md) / `legacy` (previous prompts) | `v2` |
| `grasp.confirmation` | `gripper_state` (a pick is confirmed from the gripper's grasp state: grasped/attached object or finger contact; stand-in for perception) / `segmentation` (previous mask-proximity check) | `gripper_state` |
| `scene.randomization` | `pose_jitter` (seeded ±3 cm, ±20° jitter of each variant's free objects, overlaps rejected) / `off` | `pose_jitter` |
| `prompt.corrective_hints` | `off` (neutral urgency sentence) / `on` (the 5.2 examples; for a hinted-vs-neutral comparison only) | `off` |

With all flags at their defaults, behavior must equal the Phase 1 baseline.

**Run settings that are not flags (Phase 7b):**
- The replan budget is `max_replans = 10` for every run type (model, oracle, matrix, benchmark), set in `LLMPipelineConfig` only and logged in `trial_start`.
- Real-model trials refuse to start on a dirty working tree (modified tracked files), or when the planner does not report thinking mode on and format repair off (`GET /settings` on the planner server). `/no_think` is never added by default.
- `trial_start` logs every flag and setting, including the planner settings and the simulated planner delay (oracle tests only; always off for real models).
- Planner-server errors, connection failures and timeouts are infrastructure: the trial is excluded from scoring and rerun (at most 2 reruns, logged).

Flags are set on the command line with `--flag name=value` (e.g. `--flag termination.mode=evaluator`); values of flags whose phase is not implemented yet are rejected. In-context examples are off (`--icl-mode zero_shot`); `prompt.version=v2` has none. All runs use `--goal-check` off.

---

## Phase 0 — MuJoCo port (USER ONLY)

**Do not work on this phase.** The user is porting the scenes to MuJoCo and will verify execution manually.

**Gate:** proceed to Phase 1 only after the user explicitly confirms, in writing, that:
- [ ] every ported scene and variant loads in MuJoCo,
- [ ] every action type executes correctly,
- [ ] the user has told you where the ported scene files and the MuJoCo execution adapters live.

**STOP.** Ask the user for this confirmation before doing anything else.

---

## Phase 1 — Repository map, unified logging, evaluator updates, baseline

### Steps
1. **Repository map (read-only).** Write `docs/ARCHITECTURE.md` listing, for each part of the pipeline, the file(s), main functions/classes, and inputs/outputs: scene state construction; prompt construction; planner client (remote planner server); plan check; pre-action checks; execution adapters; monitoring and replan loop; task evaluation (**including exactly how procedure checks such as "meat is cooked" are computed**); experiment runner and logging. Show it to the user before continuing.
2. **Failure codes.** One shared enum (single source of truth, e.g. `failures.py`) covering everything in the old paper's Table I plus the new codes introduced in this plan, named with the Section 0.6 terminology. Every module reports failures only through these codes.
3. **Unified trial log.** JSONL, one file per trial, one JSON object per event:

   | Event | Required fields |
   |---|---|
   | `trial_start` | trial_id, scene, variant, condition, seed, all flags, git commit |
   | `observation` | step, visible objects with regions, articulation states, newly visible objects |
   | `memory_snapshot` | step, full memory table (Phase 2) |
   | `if_check` | step, per object: relevant?, goal-attained?, overlapping?, accounted-for?, decision (Phase 4) |
   | `planning_event` | step, kind (`initial` / `replan`), trigger objects, model, prompt hash, prompt path, raw output, parsed output, planner-call latency |
   | `insertion` | corrective sub-plan(s), urgency, insertion point, merged plan, first proposal or re-query (Phase 5) |
   | `plan_check` | result, failure codes |
   | `pre_action_check` | action, result, failure codes |
   | `action_start` / `action_end` | action, bundle id, adapter, local retries used, outcome, failure code, duration |
   | `parallel` | affected set, independent actions executed, robot idle time, merge result (Phase 6) |
   | `trial_end` | success, goal relations satisfied/total, procedure checks satisfied/total, planner calls, planner time, trial time, termination reason |

4. **Evaluator updates** (ground truth, used for scoring only; never by the agent):
   - Meat objects are identified by label: `cooked_meat` starts cooked; `raw_meat` becomes cooked after exactly one close→reopen cycle inside the grill.
   - A `raw_meat` must complete one cooking cycle before it is placed on the plate.
   - **Overcooked** meat fails its procedure check (confirm, Section 10, Q1).
   - Goal: every meat ends on the plate in the serving area, cooked and not overcooked; every mug in the box; every grocery in the cupboard.
   - Irrelevant objects: the phone must not be inside the box's placement area at the end (it may be anywhere else).
5. **Metric definitions (fix the old paper's formulas in code):**
   - **Task success rate** = successful trials / total trials.
   - **Partial goal completion** = (satisfied goal relations + satisfied procedure checks) / (total goal relations + total procedure checks), averaged over trials.
5b. **Partial-observability fixes.** Objects never observed never reach the planner (no names, regions or other information, including the `valid_objects` sent to the planner server), and the plan check rejects actions on never-observed objects (`unobserved_object`, shown to the planner exactly like an unknown name). Lid states from joint values may stay, documented in `docs/ARCHITECTURE.md` as a stand-in for camera perception. A test proves an unseen object cannot appear in any prompt or pass the plan check.
5c. **Prompt rewrite.** Rewrite every planner prompt (initial plan, replan, goal check, system prompt) to contain only: the planner's role; the action set with generic preconditions and effects; the exact output format; the goal verbatim; the current state (visible objects with regions, articulation states, and from Phase 2 remembered objects); and for replans the completed actions, the remaining plan with action ids and the trigger as plain facts. One template for both scenes, no task strategies or hints, no variant-specific content, no expected answers, no in-context examples. Old prompts stay reachable with `prompt.version=legacy`. Deliverable: `docs/PROMPTS.md` (inventory, list of biased content, new templates, one rendered example per scene) and snapshot tests. **The user reviews the new prompts before any trial runs.**
6. **Baseline run.** All flags at defaults, all currently ported variants, the user's chosen planner model(s). Save under `results/baseline/`. Log every trial's seed.

### Definition of Done
- [ ] `docs/ARCHITECTURE.md` reviewed by the user.
- [ ] All modules use the shared failure enum.
- [ ] Every trial produces a complete JSONL log; a test validates the schema.
- [ ] Evaluator updates tested with hand-made action histories (overcooked, raw served early, correct cycle).
- [ ] Baseline results saved and summarized in a short table.

**STOP.** Show the baseline table and wait for confirmation.

---

## Phase 2 — Observation memory layer

Goal: never lose an object once observed. Store exactly `<object, last_seen_step, last_region>` per object.

### Design
- **Entry:** `MemoryEntry(object_id, last_seen_step, last_region)`. Nothing else is stored. "Currently visible" is derived (`last_seen_step == current step`).
- **Step:** the observation counter. An observation is taken at every planning event and after every executed action or bundle; each observation increments `step` (confirm, Section 10, Q7).
- **Update rule (after every observation):** visible objects → create or overwrite entry; objects not visible → leave unchanged; **never delete entries**; never-observed objects are never in memory.
- **Mismatch logging (diagnostic only):** if an object's `last_region` is currently visible and open but the object is not seen there, log `memory_mismatch`. No behavior change.

### Integration
1. **Prompt:** keep the visible-state section; add *"Remembered objects (not currently visible): object, last region, steps since last seen."*
2. **Checks:** objects in memory are known objects. An action on a remembered-but-not-visible object is valid if its `last_region` will be accessible when the action runs (e.g., `open(grill)` precedes `pick(raw_meat_1)`).
3. Memory is also an input to the IF rule (Phase 4): remembered objects are evaluated like visible ones.

### Tests
- [ ] Unit tests: create, overwrite, keep-when-hidden, never-delete.
- [ ] Grill: after `close(grill)`, meat stays in memory with `last_region = grill` and appears in the next prompt as remembered.
- [ ] Kitchen: an object revealed when the box opens enters memory and stays after the box closes.
- [ ] Prompt snapshot test; flag-off regression against baseline.

### Definition of Done
- [ ] Tests pass; short run with `memory.enabled = true` saved under `results/phase2/`.

**STOP.** Show results and wait for confirmation.

---

## Phase 3 — Final variant set

Goal: a set of variants in **three families**. Every variant proves exactly one point, no two variants prove the same point, and within a family **only one thing changes** from one variant to the next.

| Family | Purpose | Variants |
|---|---|---|
| **A. Basic** | Reference: the pipeline with nothing hidden that needs handling | K0, G0 |
| **B. Core** | The IF and WHERE cases | K1–K4, G1–G3 |
| **C. Cardinality** | How the system scales when one count increases | C1: K3-n2, K3-n3, G1-n1, G1-n3 · C2: K1-w2, K1-w4 |

Naming: `-nX` = X trigger objects revealed at once; `-wX` = X extra groceries on the table (extra independent work). Total: 15 variants planned; **14 built** (G1-n3 dropped: three meats do not fit outside the grill placement area; C2 is w = 0, 1, 2 because the cupboard shelf holds about 4 groceries; docs/VARIANTS.md §4, §7, Q12).

### 3.1 Audit first
1. Inventory the currently ported variants from the actual MuJoCo scene files: initial objects and regions, hidden objects, lid states, goal relations.
2. Map each existing variant onto the final set below. **Reuse and adapt existing scene files wherever possible** (e.g., an existing kitchen variant with a hidden grocery in the box becomes K3 or K4 depending on where the grocery sits; an existing grill variant with meat already inside the grill is adapted into G1–G3 by relabeling meats and removing the phone).
3. Record the old → new mapping in `docs/VARIANTS.md`. Old variants not in the final set stay in the repo for regression testing only (confirm, Section 10, Q5).

### 3.2 Shared base layout per scene
All variants of a scene share one **base layout** (the ported scene's usual objects: mugs, groceries, plate, raw meat outside the grill, etc.).
- Families A, B and C1 differ from each other **only in what is hidden inside the box or grill**.
- Family C2 additionally adds groceries on the table; nothing else changes.

The grill base layout must include at least one `raw_meat` outside the grill, so that a cooking cycle is always required. This is what makes leaving cooked meat inside the grill a real mistake.

### 3.3 Family A — Basic

| Variant | Hidden contents | Point it proves | Expected IF | Expected urgency |
|---|---|---|---|---|
| **K0** | Box opens **empty** | Kitchen reference: success, planner calls, and trial time with no replan. Any failure here is unrelated to replanning. | No replan | — |
| **G0** | Grill opens **empty** | Grill reference: the normal cook-and-serve procedure with no replan. | No replan | — |

These are also the subtraction baseline for measuring the time and planner-call cost that replanning adds in every other variant.

### 3.4 Family B — Core

| Variant | Hidden contents revealed on opening | Point it proves | Expected IF | Expected urgency (WHERE) |
|---|---|---|---|---|
| **K1** | Phone inside the box, **overlapping** the box's placement area | An irrelevant object triggers a replan only when it overlaps, and must be cleared before any mug goes in | Replan | `urgent` |
| **K2** | Phone inside the box, **non-overlapping** | An irrelevant object that doesn't overlap is ignored: no replan, no manipulation | **No replan** | — |
| **K3** | Grocery inside the box, **overlapping** | A relevant object that overlaps must be handled before anything else is placed in the box | Replan | `urgent` |
| **K4** | Grocery inside the box, **non-overlapping** | A relevant object that doesn't overlap still needs handling, but has no urgency: it can be done later | Replan | `deferred` |
| **G1** | Two `cooked_meat` inside the grill | All corrective actions urgent: stop the rest of the plan and take both out before continuing | Replan | `urgent` (both) |
| **G2** | One `cooked_meat` and one `raw_meat` inside the grill | One replan with a split urgency: cooked meat out now, raw meat stays to be cooked | Replan | `cooked_meat`: `urgent`; `raw_meat`: `deferred` |
| **G3** | Two `raw_meat` inside the grill | A replan with no urgency: raw meat stays, gets cooked in the normal cycle, and is served later | Replan | `deferred` (both) |

Why no other core variants:
- Phone appears only in the kitchen box (K1, K2).
- Meat is always non-overlapping, so there are no overlapping-meat variants.
- K2 is what separates the IF rule from discovery-triggered replanning. K4 and G3 show the other side: some replans are needed yet not urgent.
- Section 10, Q6 asks whether to add a variant for the "goal-attained object → no replan" branch of the IF rule. Do not add it unless the user says so.

### 3.5 Family C — Cardinality
Each sweep takes one core variant and changes **one count only**. The point is proven by the **trend across the sweep**; each member is one point on that curve.

**C1 — Number of trigger objects in one replan (tests IF + WHERE at scale)**

| Variant | Hidden contents | Sweep position |
|---|---|---|
| K3 (core) | 1 overlapping grocery in the box | n = 1 |
| **K3-n2** | 2 overlapping groceries in the box | n = 2 |
| **K3-n3** | 3 overlapping groceries in the box | n = 3 |
| **G1-n1** | 1 `cooked_meat` in the grill | n = 1 |
| G1 (core) | 2 `cooked_meat` in the grill | n = 2 |
| **G1-n3** | 3 `cooked_meat` in the grill | n = 3 |

Point: all trigger objects revealed at once must be handled in **one** replan with the correct urgency for each. Measure how corrective sub-plan correctness, urgency accuracy, sub-plan length, and planner latency change as n grows. All members of a sweep keep the same urgency (all `urgent`), so only the count varies.

**C2 — Amount of independent work (tests WHEN at scale)**

| Variant | Hidden contents | Extra groceries on the table | Sweep position |
|---|---|---|---|
| K1 (core) | Overlapping phone in the box | 0 (base layout) | w = 0 |
| **K1-w2** | Same | +2 | w = 2 |
| **K1-w4** | Same | +4 | w = 4 |

Point: the time saved by parallel planning and execution grows with the amount of work that is unrelated to the replan. This sweep also measures planner performance on longer plans.

Why K1 and not another variant: the phone's replan involves only the box, the phone, and parking regions. The extra groceries go to the cupboard, so they are genuinely independent. With a grocery trigger (K3/K4), the cupboard would be part of the replan, and the extra groceries would no longer be independent.

Why no grill C2 sweep: grill corrective actions use the grill and the plate, so almost all remaining grill work is part of the replan; adding meat would not add independent work.

**Physical feasibility check (before building):** box capacity (K3-n3), grill capacity (G1-n3 plus the raw meat still to be cooked), and cupboard capacity (K1-w4 plus base groceries). If a top count does not fit, reduce it, keep the sweep at three points if possible, and tell the user.

### 3.6 Specs and approval
Write one spec per variant in `docs/VARIANTS.md`:
- family, and the point it proves (one sentence) and why no other variant proves it (for sweeps: which count changes and what stays fixed),
- base layout reference + hidden contents and exact placement (inside/outside the placement area) + any extra table objects,
- placement area definition for the box and grill (config values),
- goal relations and procedure checks,
- expected IF decision, expected corrective sub-plan (for reference), expected urgency per trigger object,
- hard constraints the evaluator checks (e.g., K1/K3 and C1 kitchen: trigger objects removed before the next `place` into the box; G1/G2 and C1 grill: `cooked_meat` out of the grill before the next `close(grill)`; G2/G3: `raw_meat` cooked before plating),
- success condition.

Also add a **coverage matrix** (points × variants) to `docs/VARIANTS.md`: one variant per point for families A and B; one family per trend for C.

**Do not change any scene file until the user approves `docs/VARIANTS.md`.** Then build/adapt the variants and verify each loads and that the placement-area overlap is as specified (automated check).

### Definition of Done
- [ ] Old → new mapping and coverage matrix approved.
- [ ] All 15 variants load in MuJoCo; overlap status of every hidden object matches its spec (automated test); feasibility check passed or counts adjusted with user approval.
- [ ] Baseline system runs on all variants; results saved under `results/phase3/`.

**STOP.** Show results and wait for confirmation.

---

## Phase 4 — IF: the replan trigger rule

Goal: replan only when needed, with a deterministic rule in the system (not the planner model).

### 4.1 The rule
After every observation, evaluate every visible or remembered object that is **not accounted for** by the remaining plan or a pending replan:

| Relevant? | Goal-attained? | Overlapping? | Decision |
|---|---|---|---|
| No (irrelevant) | — | Yes | **Trigger** (`irrelevant_overlapping`) |
| No (irrelevant) | — | No | Ignore |
| Yes | No | Yes or No | **Trigger** (`relevant_not_goal_attained`) |
| Yes | Yes | — | Ignore |

Definitions used by the rule:
- **Relevant:** the object's category appears in the scene's goal categories (config per scene: kitchen = mug, grocery; grill = raw_meat, cooked_meat). Confirm this source, Section 10, Q8.
- **Goal-attained:** in its goal region with its procedure complete. Use the same procedure logic as the evaluator, fed **only** with information the agent has (action history, visible state, memory), never hidden simulator state.
- **Overlapping:** the object's footprint intersects the placement area of a region that the remaining plan will `place` into. Computed by the system from geometry; raw coordinates are never shown to the planner model.
- **Accounted for:** the remaining plan already contains actions for this object.

All trigger objects found in the same observation are handled in **one** replan.

**Objects evaluated (Phase 7b):** the visible objects, plus the remembered ones when `memory.enabled = true`; overlap uses the object's footprint when it was last visible.

**Discovery mode (Phase 7b):** `discovery` triggers are produced at the same point (after every bundle that leaves the gripper empty) with the same object classifier; every object seen for the first time triggers. They go through the same corrective output, insertion and parallel paths as IF-rule triggers, so the IF ablation (Section 8.1) changes only the trigger rule.

### 4.2 Implementation steps
1. Object classifier: relevant / goal-attained / overlapping / accounted-for.
2. IF check after every observation (`replan.trigger_mode = if_rule`). Log an `if_check` event with the per-object decision.
3. Keep `discovery` mode working (every newly visible object triggers) for the ablation.
4. Replan context sent to the planner model: trigger objects with their labels (relevant/irrelevant, goal-attained or not, overlapping or not), the region, and the remaining plan (with action ids).

### Tests
- [ ] Classifier unit tests for every row of the table, in both scenes.
- [ ] On K1, K3, K4, G1, G2, G3 the rule triggers exactly once, with the right trigger objects; on K0, G0 and K2 it never triggers.
- [ ] On C1 variants all n trigger objects are handled in a single trigger (one replan), not n separate ones.
- [ ] Objects the robot itself placed (e.g., raw meat it put in the grill) are accounted for and never trigger.
- [ ] `discovery` mode triggers on every newly visible object, including K2's phone.

### Definition of Done
- [ ] Tests pass; short run on all variants in both trigger modes saved under `results/phase4/`.

**STOP.** Show results and wait for confirmation.

---

## Phase 5 — WHERE: corrective sub-plan, urgency, insertion

Goal: the planner model plans only for the trigger objects and decides where its actions go, based on urgency. The rest of the plan is not regenerated.

### 5.1 Replan output format (strict; checked by the plan check)
The replan returns a list of **blocks**. Each block has:
- `objects`: the trigger object(s) the block handles,
- `actions`: the corrective sub-plan for those objects only,
- `urgency`: `urgent` or `deferred`,
- `insert`: `front` (required for `urgent`), `after <action id>` (an id from the remaining plan), or `end`,
- `reason`: one short sentence (logged, not used by the system).

One replan may return several blocks with different urgencies (e.g., G2: one `urgent` block for `cooked_meat`, one `deferred` block for `raw_meat`).

**Phase 7b:** a block's actions must end with the gripper empty (plan check `block_ends_holding`). An explicit empty output is valid in both trigger modes: a block whose actions are the single line `NO_ACTIONS` (no urgency or insertion needed), or `NO_ACTIONS` as the only line after `FINAL BLOCKS:`; it is logged as a no-action decision.

### 5.2 Prompt requirements
The replan prompt must:
- give the remaining plan with action ids, visible state, memory, and the trigger objects with their labels,
- instruct the planner model to plan corrective actions **only** for the trigger objects, not to rewrite the remaining plan, and not to move goal-attained objects or non-overlapping irrelevant objects,
- ask it to choose urgency and insertion point by reasoning about what would go wrong if the actions were delayed (e.g., something blocking where objects will be placed; food that would be cooked again),
- **not** contain the expected answers for any variant. Only generic, scene-agnostic in-context examples are allowed. Review the examples with the user; they must not mirror any variant.

### 5.3 Merge
1. Take the remaining plan (minus any actions already executed).
2. Insert blocks: `urgent` blocks at the front (in the order returned), `deferred` blocks after their anchor action or at the end.
3. Run the plan check on the **merged plan**, including a symbolic simulation of placement conflicts: if a `place` into a region occurs while an overlapping object is still in that region's placement area, reject with `insertion_too_late`.
4. On rejection, re-query the planner model with the reason (counts toward the replan budget). Log whether the accepted insertion was the **first proposal** or came after a re-query. Every rejection of a corrective output (format, unknown names, a block ending while holding, an invalid merged plan, `insertion_too_late`, `merge_conflict`, a repeated output) re-queries for a corrective output, never a full replan (Phase 7b); every planning event logs its output format and the reason for the call.
5. The system never enforces food-related urgency (e.g., overcooking). That reasoning is the planner model's job, and the evaluator scores it.

### 5.4 Insertion modes (for the ablation)
- `planner`: use the planner model's urgency and insertion point (full system).
- `always_front`: ignore the model's choice; insert every block at the front.
- `always_end`: ignore the model's choice; insert every block at the end.

Also keep `replan.output_mode = full_replan` (previous system) working.

### Tests (mock planner)
- [ ] Parser accepts valid block lists and rejects malformed ones (missing urgency, `urgent` with a non-front insertion, unknown anchor id).
- [ ] Merge inserts blocks correctly for front / after-id / end, including multiple blocks.
- [ ] Deferring K1's or K3's block past the next box placement → `insertion_too_late` → re-query.
- [ ] Deferring G1's `cooked_meat` block past the next `close(grill)` is **not** blocked by the system, but the evaluator marks the meat overcooked.
- [ ] `always_front` and `always_end` override the model's choice.

### Definition of Done
- [ ] Tests pass; short run on all variants (`output_mode = corrective`, `insertion_mode = planner`) saved under `results/phase5/`, reporting first-proposal urgency accuracy per variant.

**STOP.** Show results and wait for confirmation.

---

## Phase 6 — WHEN: parallel planning and execution

Goal: while the replan is being generated, keep executing remaining actions unrelated to it.

### 6.1 Behavior
1. **Clean point.** Start the replan only when no bundle is mid-execution (gripper empty, no articulation moving). If a trigger appears mid-bundle, finish the bundle first.
2. **Affected set** of a replan:
   - the trigger objects themselves,
   - the region where a trigger object is (its container, e.g. the opened box or grill) **only if the trigger object overlaps that region's placement area** (Phase 7b). A non-overlapping object is not in the way, so placements into its container remain independent (K4: the mugs go into the box while the can's replan is generated; K3: they wait),
   - the lid of a trigger object's container, always (closing it would change the trigger object, e.g. overcook a cooked meat left in the grill),
   - the object of the next action, if that action involves the affected region,
   - the regions the corrective sub-plan may use: goal regions of the trigger objects and the parking/temporary regions (config),
   - (the gripper is shared; handled by running one bundle at a time).
3. **Independent actions:** bundles in the remaining plan whose objects and regions do not intersect the affected set and whose earlier dependencies are done or also independent. Keep their order. (Phase 7b) A bundle intersects the affected set when it uses an affected object, places into an affected region, or picks from an affected region that is not a parking region (taking an object out of a parking area cannot conflict with parking something there). A dependent bundle makes later bundles dependent through its objects and its destination region, not through the region it picks from.
4. **Asynchronous replan.** Send the planner call without blocking. The prompt lists the independent actions that will already have been executed, so the corrective sub-plan doesn't repeat them and the anchors refer to actions still remaining.
5. **Execute independent bundles** one at a time while waiting. After each bundle, check whether the replan has returned. Never interrupt a bundle.
6. **When the replan returns** (after the current bundle): run the Phase 5 merge on the updated remaining plan. `urgent` blocks go to the front, so they execute next: this is the "stop and deal with it now" behavior. If an anchor action was already executed during the wait, treat the block as `front` and log `anchor_already_executed`.
7. **Merge conflict:** if the merged plan fails the plan check because of something done during the wait (e.g., a region just filled), discard it, re-query with the updated state, and log `merge_conflict`.
8. **No independent actions:** wait, as before.
9. **New triggers during the wait** are queued and handled after the merge.
10. Flag: `parallel.enabled`. Must work with every insertion mode.

### 6.2 Logging
Per replan: affected set, independent actions executed, planner-call latency, robot busy time during the call, robot idle time, merge result, total trial time.

### Tests
- [ ] Mock planner with delay: independent actions run during the delay; affected actions do not.
- [ ] `urgent` block executes immediately after the current bundle once the replan returns.
- [ ] Anchor already executed → block moved to front, logged.
- [ ] Injected conflict → `merge_conflict` → re-query.
- [ ] Trigger mid-bundle → bundle finishes first.
- [ ] Flag-off regression against Phase 5.

### Definition of Done
- [ ] Tests pass; runs with `parallel.enabled` on and off saved under `results/phase6/`, reporting robot idle time during replans, total trial time, merge-conflict rate, success rate.
- [ ] Report, per variant, how many independent actions were available per replan, and plot robot idle time saved against that number across the C2 sweep (K1, K1-w2, K1-w4).

**STOP.** Show results and wait for confirmation.

---

## Phase 7 — Diagnostics: where things go wrong

Goal: a simple report of **8 failure areas**, each with the **percentage of total trials**, computed automatically from logs.

### 7.1 Failure areas
| # | Failure area | Plain definition | Detected from |
|---|---|---|---|
| 1 | **Plan format error** | Planner output can't be read, or uses an unknown action, object, region, or block field | plan check (format) |
| 2 | **Plan rule error** | Readable but breaks action rules (place without pick, pick while holding, open while holding, moves a goal-attained object) | plan check (rules) |
| 3 | **Corrective sub-plan error** | The replan's actions don't resolve the trigger (wrong destination, misses a trigger object, moves a non-overlapping irrelevant object) | insertion log + trial end |
| 4 | **Insertion error** | Wrong urgency or position: too late (blocked placement, overcooked meat) or too early (raw meat plated before cooking) | insertion log + evaluator procedure checks |
| 5 | **Task plan error** | The initial plan (not the replan) leads to an unmet goal | trial end, no replan involved |
| 6 | **Motion/grasp error** | An action failed after all local retries | `action_end` codes |
| 7 | **Merge conflict** | Merged plan conflicted with actions executed during the wait and was not resolved | `parallel` events |
| 8 | **Replan budget exhausted** | Replan limit reached, or the same output was produced again for the same state (Phase 7b: hash of abstract state and output; the first repeat is re-queried once with a note that it was already tried and failed, a second repeat stops the trial with termination reason `replan_loop`) | planning events, trial end |

Infrastructure problems (planner server down, errors, connection failures, timeouts; simulator crash) are logged as `infrastructure`, excluded from comparisons, counted separately, and rerun at most twice (Phase 7b).

Separately from failures, report **trigger accuracy**: the % of trials where the IF rule's decisions matched each variant's expected IF decision. This is a system check, not a failure area.

### 7.2 Counting rules
- **Primary cause (sums to 100% with successes):** each failed trial gets exactly one area = the first error never recovered from.
- **Occurrences (can overlap):** % of trials where each error happened at least once, recovered or not (e.g., an `insertion_too_late` fixed by a re-query).
- Report both tables per condition and per variant.

### 7.3 Deliverables
1. `diagnostics/report.py` → `diagnostics_primary.csv`, `diagnostics_occurrences.csv`, a markdown summary, and one stacked bar chart of primary causes per condition.
2. `docs/DIAGNOSTICS.md`: definitions, counting rules, one real log excerpt per area.
3. Unit tests with hand-made logs per area, including a multi-error trial to test the "first unrecovered error" rule.

### Definition of Done
- [ ] Report runs on `results/phase3/`–`results/phase6/`; every failed trial has exactly one primary area (list any leftovers for the user).

**STOP.** Show the tables and wait for confirmation.

---

## Phase 8 — Full evaluation run

Run after the user confirms Phases 1–7. Variants: all 15 (families A, B, C).

### 8.1 Conditions
| Condition | memory | trigger_mode | output_mode | insertion_mode | parallel | Isolates |
|---|---|---|---|---|---|---|
| **Previous system** | off | discovery | full_replan | — | off | reference |
| **Full system** | on | if_rule | corrective | planner | on | — |
| **Ablation: IF** | on | **discovery** | corrective | planner | on | the IF rule |
| **Ablation: WHERE (front)** | on | if_rule | corrective | **always_front** | on | urgency reasoning |
| **Ablation: WHERE (end)** | on | if_rule | corrective | **always_end** | on | urgency reasoning |
| **Ablation: WHEN** | on | if_rule | corrective | planner | **off** | parallel execution |
| Ablation: memory (optional) | **off** | if_rule | corrective | planner | on | memory |

Planner models, prompting, and trials per condition: as chosen by the user (default 10). Randomize initial poses per trial with logged seeds if supported.

To keep compute manageable, not every family runs in every condition:

| Family | Runs in |
|---|---|
| A (K0, G0) and B (K1–K4, G1–G3) | every condition |
| C1 (trigger-count sweep) | Full system, both WHERE ablations |
| C2 (independent-work sweep) | Full system, WHEN ablation |

### 8.2 Metrics (per variant and condition)
- **Overall:** task success rate, partial goal completion, planner calls per trial, total planner time, total trial time.
- **IF:** replans per trial, unnecessary replans (triggered by objects needing no action; K2 is the cleanest case), missed replans.
- **WHERE:** first-proposal urgency accuracy (the model's urgency per trigger object vs the variant spec), `insertion_too_late` re-queries, overcooked-meat rate, raw-served-early rate.
- **WHEN:** robot idle time during replans, trial time saved vs the WHEN ablation, merge-conflict rate.
- **Reference (family A):** success and trial time with no replan; the replan overhead in other variants is measured against these.
- **Cardinality (family C):** for C1, plot success, first-proposal urgency accuracy, corrective sub-plan length, and planner latency against n; for C2, plot robot idle time saved and total trial time against w (and the number of independent actions actually executed).
- Phase 7 diagnostics tables and chart.

### 8.3 External baselines (re-implementations)
VLM-TAMP, OWL-TAMP and EPoG-TAMP are compared against the full system as **re-implementations**, not ports of their original stacks:
- Re-implement each method's planning and replanning logic as a planner module inside our pipeline (VLM-TAMP and OWL-TAMP from their papers, using the GRAB-TAMP code in `external/GRAB-TAMP` only as a reference; EPoG-TAMP from its paper, since no implementation is available).
- They use our robot, executor, scenes, observation and trial-log schema (`llm_pipeline/trial_log.py`), so the same metrics (Phase 1, step 5) and diagnostics (Phase 7) apply.
- Run each on all final variants with the same scenes, trial count and seeds as our conditions, and the same planner model as our full system wherever the method allows.
- Label them "re-implementations" in every table and document every difference from the original method in `docs/BASELINES.md`.
- Not started; implement after Phases 1-7 are confirmed.

### 8.4 Output
`results/final/` with all tables, charts, and `SUMMARY.md` (tables plus a short list of notable findings, no interpretation beyond the numbers).

---

## 9. Notes for the paper (do not implement; for the user)
- The paper's structure can follow IF / WHEN / WHERE directly; each has its own ablation.
- **IF:** K2 shows discovery-triggered replanning wasting a call on an irrelevant, non-overlapping object; the IF rule does not.
- **WHERE:** K1/K3 vs K4 (same object type, different overlap) and G1 vs G2 vs G3 (same object type, different cooked state) show that urgency depends on the situation, not the object type. `always_front` and `always_end` should each fail somewhere (e.g., `always_end` overcooks meat in G1/G2 and blocks placement in K1/K3; `always_front` may plate raw meat too early in G3), which justifies model-decided insertion.
- **WHEN:** related prior work on concurrent planning and execution (e.g., CoPAL, IndoorR2X, ATG) should be cited; the distinguishing point is combining it with corrective sub-plan insertion.
- **Basic variants** (K0, G0) show the pipeline's performance without replanning, so every replan-related cost can be reported as a difference from them.
- **Cardinality:** C1 answers "does one replan still get urgency right when several objects appear at once?"; C2 answers "does the parallel benefit grow with the amount of unrelated work?" Both are natural line plots.
- The coverage matrix in `docs/VARIANTS.md` can go straight into the paper.
- Use the terminology table (Section 0.6) and metric definitions (Phase 1, step 5) in the paper.

---

## 10. Open questions — ask the user before the relevant phase
1. **(Phase 1)** Confirm the overcooked rule: a cooked meat inside the grill during another close→reopen cycle fails the task. This is what makes cooked-meat urgency meaningful. **Answered:** overcooked fails that meat's procedure check (the trial fails; partial goal completion still counts the other meats). "Another cycle" = any close→reopen while an already-cooked meat is inside the grill, so a `cooked_meat` that starts in the grill is overcooked by the first close→reopen.
2. **(Phase 3)** In G1/G2, where should urgently removed `cooked_meat` go: directly onto the plate in the serving area, or any region outside the grill?
3. **(Phase 3)** In K1, where may the phone be moved: any region outside the box's placement area, or a specific parking region?
4. **(Phase 3)** Confirm how the box and grill placement areas are defined (config values), and exact hidden-object positions for "overlapping" vs "non-overlapping".
5. **(Phase 3)** Old variants not in the final set: keep for regression testing only (default), or also report them?
6. **(Phase 3)** Add one variant for the "goal-attained object → no replan" branch of the IF rule (e.g., a mug already in the box)? Default: no.
7. **(Phase 2)** Confirm the definition of `step` (observation counter, incremented at every planning event and after every executed action/bundle). **Answered:** one step per observation; an observation happens after every bundle finishes (success or failure) and at every planning event; plan-check re-queries within one planning event do not add steps.
8. **(Phase 4)** Confirm that "relevant" comes from a per-scene config of goal categories (kitchen: mug, grocery; grill: raw_meat, cooked_meat).
9. **(Phase 1/2)** Should the agent decide on its own that the task is complete (visible state + memory), instead of stopping when the simulator's evaluator reports success? Currently the evaluator's ground truth may drive the stop condition. **Answered:** new flag `termination.mode` (`agent` default, `evaluator` for the previous behavior); all runs use `--goal-check` off; the evaluator only scores.
10. **(Phase 6)** Which regions are parking/temporary regions in each scene?
11. **(Phase 8)** Trials per condition, planner models to include, and whether initial poses can be randomized.
12. **(Phase 3)** Base-layout counts and sweep sizes: how many groceries are on the table in the base layout, and are the proposed counts (C1: n = 1, 2, 3; C2: w = 0, 2, 4) physically feasible and acceptable?
