# External comparison baselines

The baselines are **re-implemented** as planner policies inside our pipeline: the same robot, executor and pre-action checks, scenes, seeds, planner model (served by vLLM), replan budget, JSONL logs and evaluator (`trial_runner.run_trial` -> `trial_end` -> `evaluation/model_run_report`). Only the planning and replanning logic differs. They are labeled "re-implementations" everywhere. This file records, for each baseline, what was kept from the original method, what was adapted and why.

| Baseline | Original | Code | Selected with |
|---|---|---|---|
| VLM-TAMP | Yang et al., "Guiding Long-Horizon Task and Motion Planning with Vision Language Models" | `baselines/vlm_tamp.py` | `--baseline vlm_tamp` |
| OWL-TAMP | Kumar et al., "Open-World Task and Motion Planning via Vision-Language Model Inferred Constraints" | `baselines/owl_tamp.py` | `--baseline owl_tamp` |
| LLM-Planner | Song et al., ICCV 2023 | `baselines/llm_planner.py` | `--baseline llm_planner` (`llm_planner_refprompt`: the reference prompt verbatim) |
| Inner Monologue | Huang et al., CoRL 2022 | `baselines/inner_monologue.py` | `--baseline inner_monologue` |
| EPoG | Yang et al., ICRA 2026 (arXiv 2602.04419) | `baselines/epog.py` | `--baseline epog` |

`python -m baselines.run_baseline_trial --baseline <name> ...` runs one trial; `server/run_baseline_comparison.sh "<names>"` runs every variant x seed. With `--mock`, a trial gets ground-truth answers instead of the model (a plumbing test, not a result). Every baseline runs with our replanning components off (memory, IF rule, discovery trigger, corrective blocks, parallel planning; `run_baseline_trial.BASELINE_FLAGS`), zero-shot (no in-context examples), with the selected planner model (`qwen3-vl-8b-thinking`, card sampling, 24,576 output tokens) and the same camera image our planner receives.

## Shared adaptations (all baselines)

- **Robot, scenes, actions:** our Panda in MuJoCo with our kitchen and grill variants; the actions are ours (pick, place, open, and close where the scene has it). A pick and the place of the same object run as one executor call (our bundles), with our pre-action checks.
- **Observation:** the visible objects and their regions from our segmentation, the lid states, the gripper and the regions, as our planner receives them (`baselines.common.observe`). Hidden objects are never given; an object enters the state once it has been observed.
- **Model:** the methods used GPT-class models; here every baseline uses our selected planner model, so the comparison is about the method, not the model.
- **Scoring:** success and partial goal completion come from our evaluator on the final simulator state, for every baseline and for our system alike.

## LLM-Planner

**Original:** Song et al., "LLM-Planner: Few-Shot Grounded Planning for Embodied Agents with Large Language Models", ICCV 2023. **Reference code:** the re-implementation in the EPoG repository, https://github.com/buaa-colalab/EPoG, `epog/algorithm/baseline/LLM_Planner.py` (and `base.py`), Apache-2.0, commit `1e7ed52`, read from a local clone in `external/EPoG` (git-ignored). The prompts and the output parsing follow that file.

**Kept:**
- One query generates the full plan from the current state and the goal: the reference's system prompt (role, primitive actions as `Pick(x, y)`, `Place(x, y)`, `Open(x)`, `Close(x)`, "one action at a time", "Pick must be performed before Place") and user prompt (current state, goal, JSON output `{"Plan": [...]}`).
- The reference's parsing: the JSON between the first `{` and the last `}`, the `"Plan"` key; an entry that does not parse is skipped (`BaseLLMPlanner.json_to_actions`); an output without a valid JSON plan yields no plan.
- Global replanning: when a step cannot be executed (the reference's check 2, `roll_out` skipped by the environment), the full remaining plan is regenerated from scratch from the new state. LLM-Planner's dynamic re-planning also re-plans when the agent sees an object it had not seen, so a newly observed object triggers the same full replan.
- Nothing else: no corrective blocks, no urgency, no concurrent execution; a replan replaces the plan. An empty plan ends the episode, as in the reference loop.

**Adapted, and why:**
- **No `Walk`.** Our robot is a fixed arm. The walk action, the "robot current location" prompt line and the reference's check 1 (the robot is not at the receptacle -> replan) are removed.
- **Names instead of numeric node ids.** Our objects and regions have unique names; the reference prefixes names with graph ids ("51 bread") because its scene graphs repeat categories.
- **State text.** The reference's belief-graph text ("x is on y") for the visible objects, plus lines the reference keeps in its graph nodes: lid states (open/closed, the regions each closes off, the lid's top surface), what the gripper holds, and the list of locations (an empty region is on no edge, so it would not appear otherwise).
- **Goal.** The natural-language goal of the variant. The reference gives the task graph's goal edges; LLM-Planner's own input is the language instruction.
- **Action preconditions added to the prompt.** After the reference's action list, the prompt gives the preconditions and effects of the scene's actions, word for word as our planner receives them (`prompt_v2.ACTION_DEFINITIONS`). The reference's domain has none (an open needs nothing), but ours does: a lid cannot be opened with an object on its top or while holding something. Our planner has them in its prompt, and VLM-TAMP and OWL-TAMP have them in their task-level search. Without them (`--baseline llm_planner_refprompt`, the reference prompt verbatim), the model kept planning `Open(box_lid)` with a mug on the lid. LLM-Planner gets no failure message, so it regenerated the same plan until the budget ran out: 1 of 90 kitchen trials succeeded in that run (grill 20 of 50), kept as a record (`seed_XX.reference_prompt`).
- **`Open(container)`.** The reference defines `Open(x): Open container x`, and the model often names the container (`Open(box)`) where our scene has its lid (`box_lid`). The container's name, or the region it closes off, is grounded to its lid (`Open(box)` -> `open(box_lid)`), as `Place(x, plate)` is grounded to the plate's top.
- **Step execution.** `y` in `Pick(x, y)` is not used (our pick takes only the object). `Place(x, plate)` goes to the plate's top surface (as for VLM-TAMP). A step naming an unknown action, object or region fails like a step the environment skips, and so triggers a replan.
- **Output that is not a JSON plan** triggers a replan with the same state. The reference returns without a plan in this case. A replan is what LLM-Planner's re-planning does on failure, and it is charged to the budget.
- **Budget.** Ours: the initial plan plus at most `max_replans` (10) replans. The reference's loop has a counter of 20 that is never incremented.
- **Few-shot retrieval.** LLM-Planner retrieves in-context examples with kNN from ALFRED training data. There are no training tasks for our scenes, and every baseline runs zero-shot, as does the reference re-implementation.

## Inner Monologue

**Original:** Huang et al., "Inner Monologue: Embodied Reasoning through Planning with Language Models", CoRL 2022. There is no official code; implemented from the paper.

**Kept:**
- Closed-loop planning with textual feedback after **every** executed step: success detection ("Success: True/False", with the action that failed) and passive scene description (the visible objects at the start; after each step, the newly visible objects with their regions, or "no new objects"). The feedback accumulates as a running dialogue in the prompt.
- After each executed bundle (a pick with the place of the same object, or an open / close), the planner is asked again with the goal, the dialogue so far and the current visible state. It returns the plan from now on, and only its first bundle is executed.
- The episode ends when the planner says the task is done (`NO_ACTIONS`, the paper's "done").
- No trigger rule, no corrective blocks, no concurrent execution.

**Adapted, and why:**
- **Prompt.** Zero-shot, with our action definitions and output format (the prompt-v2 system prompt, `FINAL ACTIONS:` / `NO_ACTIONS`) and our current-state section. The paper prompts few-shot with task examples; every baseline runs without in-context examples. The model is told that the robot runs the first step and then reports back.
- **Feedback sources.** Our executor and checks give the success signal; our segmentation gives the scene description. The paper's active scene description (questions to a human) has no counterpart here and is not used.
- **Unusable answer** (no `FINAL ACTIONS:` list with a valid action): recorded in the dialogue as a step without an action and "Success: False", then asked again.
- **Budget.** At most `max_replans` (10) failed steps or unusable answers. A query after a successful step is the method's normal loop, not a replan. A step limit of 30 queries (about 3 times the longest ground-truth plan, 11 bundles) bounds an episode that never ends.

## EPoG

**Original:** Yang et al., "EPoG: Integrated Exploration and Sequential Manipulation on Scene Graph with LLM-based Situated Replanning", ICRA 2026 (arXiv 2602.04419). **Reference code:** https://github.com/buaa-colalab/EPoG, Apache-2.0, commit `1e7ed52` (local clone in `external/EPoG`): `epog/algorithm/epog/EPoG.py`, `planner_dynamic.py`, `problem_dynamic.py`, `fake_simulator.py`, `llm_prompt/action_replaner.py`, and the POG planner in `pog/planning/` (`ged.py`, `action.py`, `searchNode.py`, `planner.py`). Implemented in `baselines/epog.py`.

**Kept:**
- **Scene graphs.** A belief graph and a goal (task) graph of parent -> child edges: an object on or in a location, or on another object (the meat on the plate).
- **Global planner.** EPoG's graph-edit sequence between belief and goal (`ged_seq`: a delete/add edge pair for each object whose parent differs, an add for an object in the hand); the pick-place action set and partial-order constraints (`Planner.pick_place_constraints`: a pick before its place, an object already in the hand placed first); the POG search (`SearchNode` / `Searcher`: depth-first over the unordered actions under the constraints, a pick followed by a place, at most 10,000 expansions). A unit test checks the edit pairs against networkx's optimal edit path, which the authors' `ged` uses, on random scene trees.
- **Local planner.** Each global step is simulated on the belief graph with `FakeMotionPlanner.simulate_step`'s checks, in its order (accessibility, collision, stability, block). A failed check builds the authors' `MotionError` (reason text, error type, involved nodes, observation, parking place), and the LLM resolve call returns actions that are simulated recursively.
- **Resolve call.** `get_resolve_action_seq`: the authors' system and user messages verbatim (numeric node ids, the worked example), the same JSON schema as `response_format` (`steps`, `final_answer`), retry on invalid output, and `Action.from_func_string` parsing.
- **Global replanning.** After every executed step the observation is compared with the belief graph (`update_belief_graph`). An object seen where the belief does not have it, or an object not seen before, sets the replan flag, and the global plan is recomputed. As in the authors' main loop, the rest of the current local sequence is still executed before the replan.
- **Obstacles.** Objects outside the goal graph are EPoG's obstacle ("virtual") nodes. The graph edit ignores them, so once moved aside they stay where they were put.

**Adapted, and why:**
- **Goal graph from the language goal, visible objects only.** EPoG's tasks are given as goal graphs, and our variants give a sentence. One query of our planner model (`GOAL_PROMPT`, JSON schema of EPoG's `Relationship` triples) turns the goal and the visible objects into goal relations. Objects observed later get theirs from the same query, as they appear; hidden objects are never given. Relations naming unknown objects or locations are dropped (logged), and `plate_top` is the plate node.
- **No "lost node" estimation.** EPoG asks the LLM for the most likely room and receptacle of goal objects not yet seen. Here the goal graph names only observed objects, our scenes have one room, and where a hidden object is is exactly what the robot has to discover. No walk actions, exploration actions or visited maps: the robot is a fixed arm.
- **The checks read our facts** instead of the authors' scene annotations:
  - AccessError: the source or target is a closed container (a lid's inside region; involved: the container).
  - CollisionError: the target region's placement area is occupied, from the system geometry our IF rule uses (an object's footprint intersects it; involved: the occupants). Objects whose goal is that region do not count.
  - StabilityError: objects on the object being picked (the plate).
  - BlockError: objects on a lid's top surface block opening it. The lid is the grasped part; this is our pre-action check `box_lid_obstructed`.
  - The steps are then executed by our executor with its pre-action checks. A pre-action failure of one of these kinds is caught by the same checks once the belief is updated; any other execution failure contradicts the belief and triggers a global replan (EPoG's simulator has no execution failures).
- **Resolution effects carry over.** The authors plan a resolution on a copy of the graph and continue the remaining actions on the unchanged graph. With a nested error, such as the resolution's own open blocked by an object on the lid, their version simulates the rest of the resolution with the lid still closed and repeats the access error until the budget runs out. Here the resolution's effects carry over. Their simulator never blocks an open, so the case does not arise in their domain.
- **Model and parking place.** The resolve call goes to our planner model through the OpenAI-compatible vLLM endpoint, with the same `response_format`. The parking place is the staging area: `table_center_area` in the kitchen and `grill_side_area` (the grill's prep area) for the grill.
- **Budget.** Resolve calls (including the authors' retries on invalid output) are capped by `max_replans` (10), and so are global replans. The authors have no cap.
- **Action order.** The authors order the action set as `list(set(actions))`, an arbitrary order that changes with the interpreter's hash seed. Here it is a shuffle seeded by the trial seed. Without navigation every plan has the same cost, so the first plan found is used (`find_min_path` has nothing to choose between).
- **Execution.** A pick and the place of the same object are simulated one at a time and executed as one executor call. `Close` of the kitchen box is skipped: our executor cannot close it, and no kitchen goal needs it closed.
- **Grill.** The goal graph is the final state only: the meats on the plate, the plate in the serving area. EPoG's goal graph cannot express the cooking procedure (raw meat into the grill, close, reopen). No workaround is added, so EPoG is not expected to complete grill tasks that need cooking.
- **Unresolved regions.** An object whose region perception does not resolve (set down between two regions) hangs off the root node, as every node of the authors' graphs does, so the graph edit still moves it if the goal names it.
- **Kept as the authors have it, with its consequence:** the main loop ends when the global plan has been executed, with no final goal check. If a resolution moves a goal object aside (the meat parked so the plate can be picked) and nothing in the observation contradicts the belief, nothing puts it back. EPoG's `is_goal_achieved` is only used in its evaluation.
- **Mock trials** answer the goal query with the variant's ground-truth final regions. Resolves are answered as the authors' prompt example reasons (the held object parked first); `rule_based_replanner` is kept as `rule_based_resolution`, but it ignores the gripper, which the authors' simulator never checks.

## VLM-TAMP and OWL-TAMP: history

The first two baselines started from the GRAB-TAMP ports (https://github.com/Narendhiranv04/GRAB-TAMP, branch `baseline_executions`, commit `f2976cc`) and were then re-implemented in `baselines/`; their module docstrings record what was kept and adapted. The notes below are from the initial inspection.

### Status per baseline (at inspection)

| Baseline | In GRAB-TAMP | Runs on our scenes today | Main work to get there |
|---|---|---|---|
| VLM-TAMP | `vlm_tamp_baseline/` | No | 1. An observation adapter from our scenes<br>2. An executor adapter onto our primitives<br>3. New PDDL domain and stream files and samplers for our kitchen and grill<br>4. A goal check and JSONL export |
| OWL-TAMP | `owl_tamp_baseline/` (reimplemented from the paper; no official code exists) | No | 1. The observation and executor adapters<br>2. Grounding and constraint-DSL helpers for our geometry<br>3. `--protocol replanning`: the paper's single-shot protocol never discovers hidden objects |
| EPoG-TAMP | **Not present.** "epog" appears nowhere in the repository | No | Implement from the paper, or pick a replacement (see the question below) |

Details are in `docs/ARCHITECTURE.md`, section "External baselines".

## Deviations already present in the GRAB-TAMP ports

These are documented in their `BASELINE_FIDELITY.md` and `CODE_AUDIT.md`:
- **Robot and simulator:** a Google Robot in MuJoCo replaces the papers' PR2 in PyBullet.
- **Model:** Qwen3.5-9B by default replaces GPT-4o-mini. The model is configurable.
- **Model inputs:** the model sees 3 cameras. Semantic aliases come from oracle instance segmentation.
- **Task instruction:** unified on 2026-09-07. Runs before that date are not comparable.
- **Decoding:** `model-native` (thinking on) by default. `--decoding paper` (temperature 0.2, thinking off) is reported separately.
- **OWL-TAMP search:** only 1 skeleton is ever explored.
- **OWL-TAMP execution and protocols:** physical execution goes beyond the paper, which reports plan feasibility only. The `replanning` and `receding_horizon` protocols are extensions beyond the paper.
- **VLM-TAMP refinement:** arm IK and collision checks are lazy, and their failures feed back into the reprompt loop.

## Deviations we will introduce

To be filled in during Phase 8, one line per deviation: what changed, why, and its expected effect. Expected entries:
- the robot, scenes and action primitives are ours (Panda, via the pyrep API shim on MuJoCo), not the ports' Google Robot scenes;
- the planner model is our full system's model, where the method allows it;
- the observation comes from our segmentation, and the regions are ours;
- outputs are converted to our `trial_log.jsonl` schema.

## Open questions

1. EPoG-TAMP is not implemented anywhere we have access to. Should we implement it from the paper, or replace it? The same repository has `llm3_baseline` (LLM3) and `retrieval_baseline` (CLIP retrieval, no LLM).
2. The ports call an OpenAI-compatible `/chat/completions` server. Our planner server exposes `/plan`. Should the baselines use their own vLLM server with the same model, or should our server gain an OpenAI-compatible endpoint?
