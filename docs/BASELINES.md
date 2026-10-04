# External comparison baselines

The baselines are **re-implemented** as planner policies inside our pipeline: the same robot, executor and pre-action checks, scenes, seeds, planner model (served by vLLM), JSONL logs and evaluator (`trial_runner.run_trial` -> `trial_end` -> `evaluation/model_run_report`). Only the planning and replanning logic differs. They are labeled "re-implementations" everywhere. This file records, for each baseline, what was kept from the original method, what was adapted and why.

| Baseline | Original | Code | Selected with |
|---|---|---|---|
| VLM-TAMP | Yang et al., "Guiding Long-Horizon Task and Motion Planning with Vision Language Models" | `baselines/vlm_tamp.py` | `--baseline vlm_tamp` |
| OWL-TAMP | Kumar et al., "Open-World Task and Motion Planning via Vision-Language Model Inferred Constraints" | `baselines/owl_tamp.py` | `--baseline owl_tamp` |
| LLM-Planner (EPoG implementation) + domain action definitions | Song et al., ICCV 2023, as re-implemented in the EPoG repository | `baselines/llm_planner.py` | `--baseline llm_planner` |
| LLM-Planner (EPoG implementation), reference prompt | the same, prompt verbatim | `baselines/llm_planner.py` | `--baseline llm_planner_refprompt` |
| Inner Monologue (zero-shot, adapted prompt) | Huang et al., CoRL 2022 | `baselines/inner_monologue.py` | `--baseline inner_monologue` |
| EPoG w/o lost-object estimation | Yang et al., ICRA 2026 (arXiv 2602.04419) | `baselines/epog.py` | `--baseline epog` (`epog_language_goal`: goal graph from the language goal) |

The names in the first column are the names to use in the paper: each says how the baseline differs from the original.

`python -m baselines.run_baseline_trial --baseline <name> ...` runs one trial; `server/run_baseline_comparison.sh "<names>"` runs every variant x seed. With `--mock`, a trial gets ground-truth answers instead of the model (a plumbing test, not a result). Every baseline runs with our replanning components off (memory, IF rule, discovery trigger, corrective blocks, parallel planning; `run_baseline_trial.BASELINE_FLAGS`), zero-shot (no in-context examples; the ICL rows: next section), with the selected planner model (`qwen3-vl-8b-thinking`, card sampling, 24,576 output tokens) and the same camera image our planner receives.

## ICL condition (`--icl-mode examples_v2`)

The baselines' ICL rows give each baseline the in-context examples of our ICL condition (`llm_pipeline/icl_examples.py`, `examples_v2`): the laundry-dryer scene, where a wet towel dries only inside the dryer while its door is closed and opened again, and a dry towel inside during another close / open is scorched. Example 1 asks for a full plan; Example 2 comes after the dryer is opened and an already dry towel is found inside. Each example shows a good and a bad answer with what happened afterwards. No rule is stated, and nothing of the grill scene is named. As for our planner, the examples go only to the grill scene. Kitchen prompts are byte-identical to zero-shot, so an ICL row's kitchen columns are the zero-shot run's, and only the five grill variants are run (`BASELINE_ICL_MODE=examples_v2 BASELINE_VARIANTS="FINAL.G0 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.G1-n1"`).

`baselines/icl_examples.py` renders the same examples in each baseline's own input and answer format, so they show the answer that baseline is asked for:

- **LLM-Planner:** its state description and JSON `"Plan"` with `Pick(x, y)` sources, appended to its system prompt.
- **Inner Monologue:** the monologue, the current-state section and `FINAL ACTIONS:`, appended to its system prompt.
- **VLM-TAMP:** its observed-object facts, its formal action history and English intermediate goals, at the end of query 1 (before the image description). Query 2, the translation, is unchanged.
- **OWL-TAMP:** the initial predicate state and a plan of ground operators with descriptions, ending in `achieve_goal`, at the end of the discrete-constraint prompt. The continuous-constraint prompts are unchanged.

Our Example 2 is a corrective block, a format only our planner has. For each baseline it becomes that baseline's own query at the same point: a replan after new objects are observed (LLM-Planner), the next monologue step (Inner Monologue), a query with the history (VLM-TAMP), or a planning problem from that state (OWL-TAMP). The operator descriptions in the OWL-TAMP example only name the action ("close dryer_door"), so they state no rule. **EPoG gets no examples:** the model only resolves motion errors, and its plan comes from the goal graph, which cannot express the close / open cycle. Its ICL row is its zero-shot row.

## Shared adaptations (all baselines)

- **Robot, scenes, actions:** our Panda in MuJoCo with our kitchen and grill variants; the actions are ours (pick, place, open, and close where the scene has it). A pick and the place of the same object run as one executor call (our bundles), with our pre-action checks.
- **Observation:** the visible objects and their regions from our segmentation, the lid states, the gripper and the regions, as our planner receives them (`baselines.common.observe`). Hidden objects are never given; an object enters the state once it has been observed.
- **Model:** the methods used GPT-class models; here every baseline uses our selected planner model, so the comparison is about the method, not the model.
- **Scoring:** success and partial goal completion come from our evaluator on the final simulator state, for every baseline and for our system alike. A baseline ending its own loop (an empty plan, `NO_ACTIONS`, an executed EPoG plan) is not success: the trace records it as `baseline_terminated_normally`, and the record's `planning_success` / `raw_episode_success` (fields shared with our system's records) mean the same, never the scored success.
- **Budgets** are not one shared number: each baseline's budget follows its own replanning structure (below), and the tables report planner calls per trial.

## VLM-TAMP

**Original:** Yang et al., "Guiding Long-Horizon Task and Motion Planning with Vision Language Models" (arXiv 2410.02193); the authors' `vlm_tools` (zt-yang/pybullet_planning: `prompts_gpt4v.py`, `vlm_planning_api.py`, `vlm_utils.py`), planning mode `sequence-reprompt`. Module docstring of `baselines/vlm_tamp.py` for details.

**Kept:** the two-stage query verbatim (English intermediate goals, then the formal subgoals in the same conversation; the five commonsense rules; the annotated two-panel query image from one camera view), the authors' parsing (`preds_rename`, `preds_skipped`, unknown object -> subgoal skipped), subgoals achieved in order, two reprompts (`len(replan_memory) < 2`), and the reprompt's history and failure text from `get_action_history_and_failure`, **including the collision feedback** ("When trying to solve the previous problem in simulation. The robot has collided with these objects: [...]").

**The TAMP refinement:** each subgoal is refined before any of it executes: discretely (the shortest pick / place / open / close sequence, prerequisites included; bounded by the search's expansion budget, no depth cap) and, in the kitchen, geometrically: every pick-place by our planner (the executor's PDDLStream grasp / IK / motion refinement) on the scene as the refinement predicts it, with place poses from the scene's sampler (5 tries per transfer), in a planning model that leaves the trial's scene untouched (`baselines/planning_model.py`). A failed refinement fails the subgoal before execution, and the bodies the robot collided with while planning (`baselines/collisions.py`) go into the reprompt. The refined poses are the ones executed. The grill executor plans each stage while it moves, so grill subgoals are refined discretely before execution and geometrically while executing (their collisions also reach the reprompt).

**Adapted, and why:**
- **A pick subgoal and the subgoal placing the same object run as one executor call** (one refinement, one execution; each subgoal keeps its own result). Our executor plans a pick together with its place; a pick and a place sent as separate calls take its weaker held-object paths. This removes the observation between the two subgoals.
- **Object reduction (`REDUCE-OBJECT`) disabled:** every observed object is passed to each refinement (our scenes have about ten objects).
- **Object types** from each object's benchmark category (`CATEGORY_TYPES`: groceries and meats are food, every object is movable, the plate is also a surface), as the authors' world model gives semantic types.
- **Observed objects only** (the study's protocol): the authors' world model also names objects inside closed storage; hidden objects' identities are not given.
- **A place subgoal holds** when perception sees the object in the target region; an object perception no longer sees after its place counts only if the executor's post-place check confirmed it in the target region (recorded as `confirmed_by`).
- **Camera:** the authors' query camera is "tilted downward"; ours is the scene's `front` camera.

## OWL-TAMP

**Original:** Kumar et al., "Open-World Task and Motion Planning via Vision-Language Model Generated Constraints" (arXiv 2411.08253). No code released; implemented from the paper (Sec. 5, Algorithms 1-2, Appendix A.1, A.6, A.7). Module docstring of `baselines/owl_tamp.py` for details.

**Kept:** the A.7 prompts (discrete sketch with the banana/bowl example, natural-language operator descriptions, mandatory `achieve_goal`; goal constraints with the A.6 helper codebook and few-shot examples; per-operator constraints conditioned on the description and the goal constraints), `Executed(i)` sketch-subsequence search, search-then-sample with 500 samples per operator, skeleton backtracking (at most five skeletons), single-shot open-loop execution.

**Changed after the fidelity review:**
- **Robot feasibility during search-then-sample.** A place pose is accepted only if the operator's constraints hold and our planner refines the operator's pick-place with it (grasp, IK, motion; the executor's PDDLStream refinement) on the predicted scene, in the planning model (kitchen). A failure consumes the sample; an exhausted operator backtracks. At most 20 refinements per operator (a failed refinement takes up to 60 s). The grill executor plans while it moves, so grill operators are checked by their constraints at planning time and for robot feasibility at execution.
- **Samples from the scene's own sampler** (its packing and clearance rules) on the predicted scene, up to the 500 budget; the clearance-ranked grid and the 2-D overlap test are gone.
- **Plan modifications** from the failed operator: the paper's example (a place onto an occupied region: move one object on it elsewhere first) and the same for movable objects the operator's refinement collided with. This is the applicable subset of the authors' engineered strategies.
- **`achieve_goal` missing, or no valid goal constraint function:** a planning failure (they were skipped, which left the goal unconstrained).
- **An operator's constraints restrict its own parameter (Sec. 5.2):** a generated function applies to a place only if it reads the placed object's pose. The model often copies final-goal checks about other objects into an operator's constraints (when placing `mug1` into the box: "the can, the spam and the sugar are on the shelf"), which no pose of the mug can satisfy before they are placed. Applied as generated (a run made after the review, kept as `seed_XX.unfiltered`), 93 of 107 exhausted kitchen operators carried such a check, no sample ever reached the feasibility check, and kitchen success fell to about 5%.
- **Typed operators:** `place_inside` needs a space (inside the box, the cupboard, the grill), `place_ontop` a surface or an object's top (the plate); the prompt lists the ground operators reachable by relaxed planning (delete effects ignored), not every pairing of entities.
- **Helper semantics (A.6):** `modify_pose_bounds_to_be_ontop_of_object` keeps the object touching the support's top (its bottom from 8 cm under to 6 cm over the support box's top: our region boxes are planes up to ~5 cm above the surface, and the plate's box top is its rim); `..._inside_object` keeps x and y within the container and the object's origin within its vertical extent. Predicted boxes keep each object's observed origin-to-box offset.
- **Grill:** each place is executed at its sampled pose (the grill executor otherwise places at fixed slots).

**Caveat (not changed):** the method is single-shot from the initial scene, so an object revealed later never enters its sketch. That is a weakness of the method in this setting; an `OWL-TAMP + requery` extension would be a new method.

## LLM-Planner

**Original:** Song et al., "LLM-Planner: Few-Shot Grounded Planning for Embodied Agents with Large Language Models", ICCV 2023. This is **the EPoG repository's re-implementation** of LLM-Planner, not a port of Song et al.'s own code (which prompts with kNN-retrieved examples organised as task description, completed plans, visible objects and "Next Plans"); the paper names it "LLM-Planner (EPoG implementation)". **Reference code:** the re-implementation in the EPoG repository, https://github.com/buaa-colalab/EPoG, `epog/algorithm/baseline/LLM_Planner.py` (and `base.py`), Apache-2.0, commit `1e7ed52`, read from a local clone in `external/EPoG` (git-ignored). The prompts and the output parsing follow that file.

**Kept:**
- One query generates the full plan from the current state and the goal: the reference's system prompt (role, primitive actions as `Pick(x, y)`, `Place(x, y)`, `Open(x)`, `Close(x)`, "one action at a time", "Pick must be performed before Place") and user prompt (current state, goal, JSON output `{"Plan": [...]}`).
- The reference's parsing: the JSON between the first `{` and the last `}`, the `"Plan"` key; an entry that does not parse is skipped (`BaseLLMPlanner.json_to_actions`); an output without a valid JSON plan yields no plan.
- Global replanning: when a step cannot be executed (the reference's check 2, `roll_out` skipped by the environment), the full remaining plan is regenerated from scratch from the new state.
- Nothing else: no corrective blocks, no urgency, no concurrent execution; a replan replaces the plan. An empty plan ends the episode, as in the reference loop.

**Adapted, and why:**
- **No `Walk`.** Our robot is a fixed arm. The walk action, the "robot current location" prompt line and the reference's check 1 (the robot is not at the receptacle -> replan) are removed.
- **Names instead of numeric node ids.** Our objects and regions have unique names; the reference prefixes names with graph ids ("51 bread") because its scene graphs repeat categories.
- **State text.** The reference's belief-graph text ("x is on y") for the visible objects, plus lines the reference keeps in its graph nodes: lid states (open/closed, the regions each closes off, the lid's top surface), what the gripper holds, and the list of locations (an empty region is on no edge, so it would not appear otherwise).
- **Goal.** The natural-language goal of the variant. The reference gives the task graph's goal edges; LLM-Planner's own input is the language instruction.
- **Action preconditions added to the prompt.** After the reference's action list, the prompt gives the preconditions and effects of the scene's actions, word for word as our planner receives them (`prompt_v2.ACTION_DEFINITIONS`). The reference's domain has none (an open needs nothing), but ours does: a lid cannot be opened with an object on its top or while holding something. Our planner has them in its prompt, and VLM-TAMP and OWL-TAMP have them in their task-level search. Without them (`--baseline llm_planner_refprompt`, the reference prompt verbatim), the model kept planning `Open(box_lid)` with a mug on the lid. LLM-Planner gets no failure message, so it regenerated the same plan until the budget ran out: 1 of 90 kitchen trials succeeded in that run (grill 20 of 50), kept as a record (`seed_XX.reference_prompt`).
- **`Open(container)`.** The reference defines `Open(x): Open container x`, and the model often names the container (`Open(box)`) where our scene has its lid (`box_lid`). The container's name, or the region it closes off, is grounded to its lid (`Open(box)` -> `open(box_lid)`), as `Place(x, plate)` is grounded to the plate's top.
- **Step execution.** `Pick(x, y)` is checked against where `x` is observed: the reference's action is the graph edge (y, x), so a wrong `y` is a wrong action, and the step fails (`wrong_pick_source`), which triggers a replan; `plate` is accepted for what is on `plate_top`, and an object perception does not place is not checked. Our pick then takes only the object. `Place(x, plate)` goes to the plate's top surface (as for VLM-TAMP). A step naming an unknown action, object or region fails like a step the environment skips, and so triggers a replan.
- **Output that is not a JSON plan** triggers a replan with the same state. The reference returns without a plan in this case. A replan is what LLM-Planner's re-planning does on failure, and it is charged to the budget.
- **Budget.** Ours: the initial plan plus at most `max_replans` (10) replans. The reference's loop has a counter of 20 that is never incremented.
- **No initial exploration; replan on a newly observed object (the study's specification).** The reference first explores (it walks every room and opens and closes every unexplored container) and only then plans. Our protocol gives every method partial visibility from the start, with nothing explored for it, so this baseline plans from the visible state, and a newly observed object triggers the full replan (as an execution failure does). The original LLM-Planner re-plans when the agent is stuck or fails; the discovery replan gives this baseline a way to account for revealed objects, which it would otherwise never see in its prompt.
- **Two rows.** The reported row adds the action definitions (above). The reference-prompt row (`llm_planner_refprompt`) is the prompt verbatim, so the effect of the added domain semantics is visible.
- **Few-shot retrieval.** LLM-Planner retrieves in-context examples with kNN from ALFRED training data. There are no training tasks for our scenes, and every baseline runs zero-shot, as does the reference re-implementation.

## Inner Monologue

**Original:** Huang et al., "Inner Monologue: Embodied Reasoning through Planning with Language Models", CoRL 2022. There is no official code; implemented from the paper. The paper's name for it: **Inner Monologue (zero-shot, adapted prompt)**. The emulated instantiation is the paper's tabletop rearrangement, where one step is one execution of a skill (its pick-and-place is one composite skill, with feedback after it); here a step is one skill execution: a pick with the place of the same object, an open, or a close.

**Kept:**
- Closed-loop planning with textual feedback after **every** executed step: success detection ("Success: True/False", with the action that failed) and passive scene description (the visible objects at the start; after each step, the newly visible objects with their regions, or "no new objects"). The feedback accumulates as a running dialogue in the prompt.
- After each executed bundle (a pick with the place of the same object, or an open / close), the planner is asked again with the goal, the dialogue so far and the current visible state. It returns the plan from now on, and only its first bundle is executed.
- The episode ends when the planner says the task is done (`NO_ACTIONS`, the paper's "done").
- No trigger rule, no corrective blocks, no concurrent execution.

**Adapted, and why:**
- **Prompt.** Zero-shot, with our action definitions and output format (the prompt-v2 system prompt, `FINAL ACTIONS:` / `NO_ACTIONS`) and our current-state section, around the paper's running dialogue (`Robot action:`, `Success:`, `Scene:` lines; no `Robot thought:` lines, which the paper uses in some domains). The paper prompts few-shot with task examples in its own format; every baseline runs without in-context examples. So the prompt is ours with Inner Monologue's feedback loop, and is named an adapted prompt. The model is told that the robot runs the first step and then reports back.
- **Feedback sources.** Our executor and checks give the success signal; our segmentation gives the scene description. The paper's active scene description (questions to a human) has no counterpart here and is not used.
- **Unusable answer** (no `FINAL ACTIONS:` list with a valid action): recorded in the dialogue as a step without an action and "Success: False", then asked again.
- **Budget.** Each failed step or unusable answer is followed by a replan, at most `max_replans` (10) of them: the episode ends at the 11th failure (the same 10 replans as our system and LLM-Planner). A query after a successful step is the method's normal loop, not a replan. A step limit of 30 queries (about 3 times the longest ground-truth plan, 11 bundles) bounds an episode that never ends.

## EPoG

**Original:** Yang et al., "EPoG: Integrated Exploration and Sequential Manipulation on Scene Graph with LLM-based Situated Replanning", ICRA 2026 (arXiv 2602.04419). The paper's name for this row: **EPoG w/o lost-object estimation** (the reason is under "Adapted"). **Reference code:** https://github.com/buaa-colalab/EPoG, Apache-2.0, commit `1e7ed52` (local clone in `external/EPoG`): `epog/algorithm/epog/EPoG.py`, `planner_dynamic.py`, `problem_dynamic.py`, `fake_simulator.py`, `llm_prompt/action_replaner.py`, and the POG planner in `pog/planning/` (`ged.py`, `action.py`, `searchNode.py`, `planner.py`). Implemented in `baselines/epog.py`.

**Kept:**
- **Scene graphs.** A belief graph and a goal (task) graph of parent -> child edges: an object on or in a location, or on another object (the meat on the plate).
- **Global planner.** EPoG's graph-edit sequence between belief and goal (`ged_seq`: a delete/add edge pair for each object whose parent differs, an add for an object in the hand); the pick-place action set and partial-order constraints (`Planner.pick_place_constraints`: a pick before its place, an object already in the hand placed first); the POG search (`SearchNode` / `Searcher`: depth-first over the unordered actions under the constraints, a pick followed by a place, at most 10,000 expansions). A unit test checks the edit pairs against networkx's optimal edit path, which the authors' `ged` uses, on random scene trees.
- **Local planner.** Each global step is simulated on the belief graph with `FakeMotionPlanner.simulate_step`'s checks, in its order (accessibility, collision, stability, block). A failed check builds the authors' `MotionError` (reason text, error type, involved nodes, observation, parking place), and the LLM resolve call returns actions that are simulated recursively.
- **Resolve call.** `get_resolve_action_seq`: the authors' system and user messages verbatim (numeric node ids, the worked example), the same JSON schema as `response_format` (`steps`, `final_answer`), retry on invalid output, and `Action.from_func_string` parsing.
- **Global replanning.** After every executed step the observation is compared with the belief graph (`update_belief_graph`). An object seen where the belief does not have it, or an object not seen before, sets the replan flag, and the global plan is recomputed. As in the authors' main loop, the rest of the current local sequence is still executed before the replan.
- **Obstacles.** Objects outside the goal graph are EPoG's obstacle ("virtual") nodes. The graph edit ignores them, so once moved aside they stay where they were put.

**Adapted, and why:**
- **Goal graph from the goal specification, visible objects only.** EPoG is given its task graph (`env.task_graph`); building it is not part of the method. Here it is EPoG's native goal graph translated deterministically from the benchmark's goal specification (`goal_relations`: an object's category -> its goal region, from `evaluation.labeled_rules`, the table our system's IF rule also uses for relevance; the grill's plate -> serving area), with the relation type kept (`in` for the box, the cupboard and the grill, `on` for surfaces and the plate). Only observed objects are given; an object observed later gets its relation when it appears. No model call is involved. The language version (`--baseline epog_language_goal`: one model query, `GOAL_PROMPT`, JSON schema of EPoG's `Relationship` triples, turns the goal sentence and the observed objects into the relations) is kept as a separate adaptation.
- **No lost-object estimation (hence the row's name).** EPoG's task graph contains every task object; `get_lost_nodes` finds those missing from the belief and `insert_lost_nodes` estimates (with the LLM) the room and receptacle each is in, so the global plan explores toward the estimates. That is central to the paper's integrated exploration. Our protocol never tells a method that a hidden object exists, so the goal graph names only observed objects and nothing is estimated: EPoG here plans like the authors' EPoG with no lost nodes. Giving it the hidden objects' identities would give it information our system does not get. No walk actions, exploration actions or visited maps either: the robot is a fixed arm.
- **The checks read our facts** instead of the authors' scene annotations:
  - AccessError: the source or target is a closed container (a lid's inside region; involved: the container).
  - CollisionError: the target region's placement area is occupied, from the system geometry our IF rule uses (an object's footprint intersects it; involved: the occupants). Objects whose goal is that region do not count.
  - StabilityError: objects on the object being picked (the plate).
  - BlockError: objects on a lid's top surface block opening it. The lid is the grasped part; this is our pre-action check `box_lid_obstructed`.
  - The steps are then executed by our executor with its pre-action checks. A pre-action failure of one of these kinds is caught by the same checks once the belief is updated; any other execution failure contradicts the belief and triggers a global replan (EPoG's simulator has no execution failures).
- **Semantic patches, each needed for our scenes** (none in the authors' code; listed so they can be judged one by one):
  - *Resolution effects carry over* (next item).
  - *BlockError for an obstructed open*: the authors' `check_block` is on picks (an object blocking a grasp); here it is the lid's open blocked by objects on the lid, the blocked grasp of our scenes (the study's mapping: a blocked grasp -> BlockError).
  - *Collision occupants exclude goal objects of the region*: the authors' collision nodes are virtual obstacles, never goal objects; mugs already placed in the box (their goal) are not obstacles to the next mug.
- **Resolution effects carry over.** The authors plan a resolution on a copy of the graph and continue the remaining actions on the unchanged graph. With a nested error, such as the resolution's own open blocked by an object on the lid, their version simulates the rest of the resolution with the lid still closed and repeats the access error until the budget runs out. Here the resolution's effects carry over. Their simulator never blocks an open, so the case does not arise in their domain.
- **Two parsing strictnesses of the authors' code relaxed (after the first full run).** (1) The resolve schema marks `explanation` and `output` (and `action`) as required, as the authors' pydantic models do; their JSON schema does not, so constrained decoding let the model leave out the explanation, which their own validator then rejects: 161 of 808 fix answers in the first run were rejected and re-queried, each from the budget, although EPoG only uses `final_answer`. (2) `Action.from_func_string` allows whitespace inside the parentheses: the authors' patterns need exactly `Place(1, 2)` and dropped 28 actions written `Place(1,2)`. The first run is kept (`seed_XX.strict_parse`).
- **Model and parking place.** The resolve call goes to our planner model through the OpenAI-compatible vLLM endpoint, with the same `response_format`. The parking place is the staging area: `table_center_area` in the kitchen and `grill_side_area` (the grill's prep area) for the grill.
- **Budget.** EPoG has two replanning layers, and each is capped separately by `max_replans` (10): resolve calls (including the authors' retries on invalid output) and global replans. The authors have no cap. The trace reports both and the total model calls (`budget_use`); there is no single budget comparable to the other baselines'.
- **Action order.** The authors order the action set as `list(set(actions))`, an arbitrary order that changes with the interpreter's hash seed. Here it is a shuffle seeded by the trial seed. Without navigation every plan has the same cost, so the first plan found is used (`find_min_path` has nothing to choose between).
- **Execution.** A pick and the place of the same object are simulated one at a time and executed as one executor call. `Close` of the kitchen box is skipped: our executor cannot close it, and no kitchen goal needs it closed.
- **Grill (report with this caveat).** The goal graph is the final state only: the meats on the plate, the plate in the serving area. EPoG's goal graph cannot represent the cooking procedure (raw meat into the grill, close, reopen), which our evaluator checks, so a grill failure is largely a representation mismatch, not a planning failure. No workaround is added; the grill numbers are reported with this caveat, apart from the kitchen numbers.
- **Unresolved regions.** An object whose region perception does not resolve (set down between two regions) hangs off the root node, as every node of the authors' graphs does, so the graph edit still moves it if the goal names it.
- **Kept as the authors have it, with its consequence:** the main loop ends when the global plan has been executed, with no final goal check. If a resolution moves a goal object aside (the meat parked so the plate can be picked) and nothing in the observation contradicts the belief, nothing puts it back. EPoG's `is_goal_achieved` is only used in its evaluation.
- **Mock trials** answer the goal query with the variant's ground-truth final regions. Resolves are answered as the authors' prompt example reasons (the held object parked first); `rule_based_replanner` is kept as `rule_based_resolution`, but it ignores the gripper, which the authors' simulator never checks.

## VLM-TAMP and OWL-TAMP: history (initial inspection, superseded by the sections above)

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
