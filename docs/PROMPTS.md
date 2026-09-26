# Planner prompts (Phase 1, step 5c)

**Status: approved** (2026-09-25), with the answers in section 5.

- `prompt.version = v2` (the default) selects the new prompts.
- `prompt.version = legacy` reproduces the previous system's prompts exactly.
- In-context examples are off from now on: `--icl-mode` defaults to `zero_shot`, and v2 refuses `few_shot_shared_1`.

Code:
- templates: `llm_pipeline/prompt_v2.py`
- snapshot tests: `llm_pipeline/tests/test_prompt_v2.py`
- golden files: `llm_pipeline/tests/snapshots/prompt_v2_*.txt`

## 1. Inventory of the current (legacy) prompts

| # | Prompt | File / function | When it is used |
|---|---|---|---|
| L1 | Planner system prompt | `llm_pipeline/prompts/system_prompt.txt`, loaded by `GeometricContextBuilder.build_bundle` (`geometric_builder.py:73`) | Every planner call (initial plan and replan) |
| L2 | Planner user prompt | `GeometricContextBuilder.build_bundle`. Sections: Planning Checkpoint, Goal, Visible-Object Relational State, Valid Target Regions (text from `REGION_SEMANTICS`, `region_aliases.py:67`), Articulation State, Access Constraints, Domain Semantic State, Completed Actions, Replanning Event, then `_build_action_contract_lines` and `_action_description_line` | Every planner call. The replan adds the Replanning Event section |
| L3 | Shared few-shot exemplar | `llm_pipeline/prompts/shared_exemplar.txt` (7 examples), appended to L1 | Only with `--icl-mode few_shot_shared_1` |
| L4 | Goal-check prompts | `LLMOnlyReplanningPipeline._build_goal_check_prompts` (`pipeline.py`), a fixed system prompt plus L2's state sections | After a plan completes or on `NO_ACTIONS`, only with `--goal-check` |
| L5 | Format-repair prompt | `vlm_pipeline/vlm_planner.py::_build_format_repair_prompt`, on the planner server | VLM path: a second, hidden model call when the output is not parseable. It is not counted as a planner call |
| L6 | `/no_think` prefix | `planner.py::_build_prompt_text`, `vlm_pipeline/vlm_planner.py::_apply_chat_template` | Prepended to the user prompt when `QWEN_THINKING_MODE` is off (the default) |
| L7 | Failure messages inside prompts | messages in `failure_logic.py` and `strict_parser.py`, rendered as `event_message` in L2 | Every replan after a failure |
| L8 | Alternative text-only builder | `prompt_builder.py::TextOnlyContextBuilder` | Not on the main path (tests only) |
| L9 | Old prompt copies | `llm_pipeline/system_prompt.txt`, `llm_pipeline/shared_exemplar.txt` | Unused |
| L10 | Previous-system prompts | `vlm_pipeline/context_aggregator_v2.py::build_system_prompt`, `vlm_pipeline/vlm_with_replanning.py::build_replan_prompt` | Not used by `llm_pipeline` |
| L11 | Prompt dump tool | `llm_pipeline/debug_prompt_builder.py` | Debugging only; renders L1/L2 |

## 2. Extra or biased content found

Each item shows where it appears and why it is a problem for a fair evaluation.

**Task strategy and ordering hints**
1. L2 Access Constraints: "box_lid is OBSTRUCTED by mug2; before open(box_lid), move mug2 to table_staging_area". This hands over the kitchen solution: which object to move, where, and in what order.
2. L2 Access Constraints: "inside_box is BLOCKED until open(box_lid) is completed". This is ordering advice; the lid state alone implies it.
3. L2 contract: "Multiple raw meats can be cooked together by placing all of them inside_grill before one close(grill_lid) and one open(grill_lid)". This is a batching strategy for the grill.
4. L2 contract: "Cooking status and serving location are separate: cooked meat still must be physically placed on the serving target named by the goal". This tells the model how to read the goal.
5. L2 contract, CHECK 1: "map goal object categories to target regions". This is a reasoning scaffold that directs the answer.
6. L2 contract, CHECK 2: "identify blockers, access constraints, or already-satisfied objects". The same kind of scaffold.
7. L2 actions: "close(grill_lid): close the grill lid when the goal requires it" and "open(box_lid) … when access to the box is needed". These say when to use an action.
8. L2 `repair_rule` / `repair_constraint` lines after plan-check failures. These are repair advice, not facts.

**Cooking procedure beyond the generic action definitions**

9. L1: "Raw meat outside the grill becomes cooked only after it has been placed inside_grill, the grill lid has been closed with that meat inside, and the grill lid has been opened again." This is the grill procedure spelled out.
10. L1: "Meat placed directly on the plate without either cooked(object) or this grill-lid cycle is not cooked." The same procedure again.
11. L1 and L2 `cook_status=raw|cooked` and Domain Semantic State `raw(x)`/`cooked(x)`. This is status the system derives. It marks meat found inside the grill as cooked, which is an expected answer for G2/G3.

**Statements about which objects matter, and region hints**

12. Region text: `table` "DO NOT place objects here (use table_staging_area instead)". This is destination advice.
13. Region text: `cupboard_shelf` "for storing groceries" and `inside_box` "for objects that should be put inside the box". These map categories to goals.
14. Region text: `plate_top` "for placing cooked meat" and `serving_area` "where the plate should be placed". These give away goal regions.
15. Region text: `prep_area` "where uncooked meat starts", `pantry_area` "where groceries start" and `dish_rack` "where the plate starts". These state the initial conditions and categories as facts.
16. L1: names specific meats ("chicken, steak, steak1, or other listed meat names"). This is scene-specific, and it can name an object that is still hidden, as `steak` is in G2.

**Hidden simulator state and format pressure**

17. L2 `tracked_non_visible_objects`, with their live simulator regions. This is information the robot can no longer observe.
18. L1: "Do not write hidden reasoning, chain-of-thought, step-by-step analysis…" and L2 "Do not write additional reasoning…". These suppress reasoning, which penalizes thinking models.

**Advice inside failure messages (L7)**

19. `box_lid_closed`: "…; open(box_lid) first".
20. `box_lid_obstructed`: "move X to table_staging_area first".
21. Parser: "Did you mean place(mug2, …)? You must place the object you are currently holding." This is repair advice.

**In-context examples mirroring variants (L3)**

22. Example 3, "clearing before opening an obstructed lid", mirrors the kitchen mug on the box lid.
23. Example 5, "implicit handling of a visible non-target object … safe_zone", mirrors phone → table in G1/G3.
24. Example 6, "batch processing and serving … process cycle", mirrors the grill procedure.
25. Example 7, "sorting across two target categories", mirrors the kitchen goal.

**Hidden extra model calls and control tokens**

26. L5 format repair: a second generation with its own instructions ("Allowed forms are …"), not logged as a planner call.
27. L6 `/no_think`: forces thinking off. For a thinking-only model such as Qwen3-VL-8B-Thinking, set `QWEN_THINKING_MODE=default` on the server so the prefix is not added.

**Leak of hidden object names outside the prompt text**

28. `valid_objects` in the `/plan` request contained every object in the scene, including hidden ones. The server model never saw it as text, but the plan check accepted hidden objects. This is fixed for both prompt versions (Phase 1, step 5b).

The legacy prompts are kept exactly as they were, behind `prompt.version=legacy`, including items 1–27. The one exception: a never-observed object now gets the same message and code as a name that does not exist, in both versions.

## 3. The new templates (v2)

One template serves both scenes. Only data differs between them: the object, region and lid names, and the available actions (the kitchen has no `close`).

### 3.1 Planner system prompt

The system prompt has three parts:
1. **Role**, one sentence.
2. **Actions available in this scene.** Only the definitions of the scene's actions are included.
3. **Output format.**

```
You are the task planner for a robot arm. Given a goal and the current state of a scene, you output the ordered list of actions that achieves the goal.

Actions available in this scene:
pick(o): grasp object o.
  Preconditions: the gripper is empty; o is a listed object; o is not in a region closed off by a closed lid.
  Effects: the gripper holds o.
place(o, r): put the held object o into region r.
  Preconditions: the gripper holds o; r is a listed region; r is not closed off by a closed lid.
  Effects: o is in r; the gripper is empty.
open(l): open lid l.
  Preconditions: the gripper is empty; l is closed; no object is on the top surface of l.
  Effects: l is open; the regions l closes off become reachable and their contents can become visible.
close(l): close lid l.
  Preconditions: the gripper is empty; l is open.
  Effects: l is closed; the regions l closes off become unreachable and their contents are no longer visible.

Output format:
Reasoning is allowed. End your answer with a line containing only FINAL ACTIONS: followed by one action per line, in execution order, in this form:
FINAL ACTIONS:
pick(o)
place(o, r)
Use only the action names available in this scene and the object, lid and region names given in the state. Write nothing after the last action line. If the goal is already satisfied, write NO_ACTIONS as the only line after FINAL ACTIONS:.
```

### 3.2 Planner user prompt: initial plan

```
## Goal
<goal text, verbatim>

## Current state
Visible objects and the region each one is in:
- <object>: <region>                      (one line per visible object; lids are listed below)
Lids:
- <lid>: open|closed (closes off <regions>[; top surface: <region>])
Gripper: empty | holding <object>
Regions: <every valid region name>
```

Once Phase 2 exists, a `Remembered objects` block will be added after the visible objects (plan.md Phase 2).

### 3.3 Planner user prompt: replan

The replan prompt has the same Goal and Current state sections, followed by:

```
## Completed actions
- a<id>: <action>                          (every executed action of the trial, with its id)

## Remaining plan (not executed yet)
- a<id>: <action>                          (the rest of the current plan, with ids)

## Why a new plan is requested
- <trigger, as plain facts>
```

Trigger lines:

| Trigger | Line |
|---|---|
| Newly visible objects | `After <action>, these objects became visible and had not been seen earlier in this trial: <o> (<region>), …` |
| Execution failure | `<action> failed (failure code <code>).` |
| Plan-check rejection | `The previous planner output was rejected before execution (failure code <code>). <fact>` where `<fact>` quotes the offending line, e.g. `Line 3 (place(mug2, inside_box)) places 'mug2' while the gripper holds 'spam'.` |
| Goal check (only with `--goal-check`) | `A goal check reported that the goal is not satisfied: <reason>` |

Action ids (`a1`, `a2`, …) are assigned once per trial, when a plan is accepted. They are what the Phase 5 `after <action id>` insertion points will refer to.

The replan prompt is built from named sections (`REPLAN_SECTIONS` in `prompt_v2.py`: goal, state, completed_actions, remaining_plan, trigger). Phase 5 can add the corrective-block output format as one more section without touching the others.

### 3.4 Goal-check prompts

The goal check is not used in any run (`--goal-check` is off), but it was rewritten too.

```
System:
You check whether a robot has achieved a goal. You are given the goal, the current state of the scene and the actions the robot has completed.

Output format: answer with exactly one line, either GOAL_COMPLETE or GOAL_INCOMPLETE: <short reason>.

User:
## Goal
<goal text>

## Current state
… (same block as 3.2)

## Completed actions
- <action>
```

### 3.5 What else changed with v2

- **Images unchanged.** With `--vision`, the same 5-camera composite image is attached. Images are perception, not prompt text.
- **No format repair.** The server-side format-repair call (L5) is disabled for v2 requests (`PlanRequest.prompt_version`). An unparseable answer becomes a logged plan-check failure and a counted re-query. From Phase 7b format repair is also a server flag (`--format-repair`, default off), the server reports it in `GET /settings`, and real-model trials refuse a server with it on or without `/settings`.
- **Thinking on (Phase 7b).** `/no_think` is never added by default; only `QWEN_THINKING_MODE=off` on the server adds it, and real-model trials refuse that setting.
- **All lids listed.** Lid states for every lid in the scene come from joint and pose values, not only for visible lids. This stands in for camera perception (`docs/ARCHITECTURE.md`).
- **Neutral plan-check facts.** Plan-check failures are shown as the code plus a plain fact, never with the old advice-bearing messages. A never-observed object is shown exactly like a name that does not exist (`unknown_action_token`); `unobserved_object` appears only in the trial log.

## 4. Rendered examples from real variant states

Both examples were rendered from real observations of the MuJoCo scenes. The state comes from `trial_log.jsonl` of a full-pipeline trial run with the GT oracle planner (`llm_pipeline/oracle_trial_runner.py`).

### 4.1 Kitchen (K1), initial plan

The system prompt is the one in 3.1, without the `close` definition. User prompt:

```
## Goal
move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box

## Current state
Visible objects and the region each one is in:
- mug2: box_lid_top
- mug3: cupboard_shelf
- spam: table_right_area
Lids:
- box_lid: closed (closes off inside_box; top surface: box_lid_top)
Gripper: empty
Regions: table, table_center_area, cupboard_shelf, inside_box, table_right_area, box_lid_top
```

The `can_of_beans` hidden inside the box is not mentioned anywhere, and it is not sent to the server.

For comparison, the legacy prompt for the same state includes these lines:
- "box_lid is OBSTRUCTED by mug2; before open(box_lid), move mug2 to table_staging_area"
- "cupboard_shelf: shelf inside the cupboard for storing groceries"
- "table: … DO NOT place objects here"
- the CHECK 1/CHECK 2 scaffold

### 4.2 Grill (G2), replan after the grill opens

The system prompt is the one in 3.1. User prompt:

```
## Goal
COOK all raw meat using the grill and SERVE all cooked meat on the PLATE in the serving area.

## Current state
Visible objects and the region each one is in:
- steak: inside_grill
- steak1: grill_side_area
- chicken: grill_side_area
- plate: dish_rack
Lids:
- grill_lid: open (closes off inside_grill)
Gripper: empty
Regions: table, grill_side_area, inside_grill, plate_top, serving_area, dish_rack

## Completed actions
- a1: open(grill_lid)

## Remaining plan (not executed yet)
- a2: pick(plate)
- a3: place(plate, serving_area)
- a4: pick(chicken)
- a5: place(chicken, inside_grill)
- a6: pick(steak1)
- a7: place(steak1, inside_grill)
- a8: close(grill_lid)
- a9: open(grill_lid)
- a10: pick(chicken)
- a11: place(chicken, plate_top)
- a12: pick(steak1)
- a13: place(steak1, plate_top)

## Why a new plan is requested
- After open(grill_lid), these objects became visible and had not been seen earlier in this trial: steak (inside_grill).
```

## 5. Decisions (approved)

1. **Cook status is not shown in v2.** With today's grill names (`chicken`, `steak`, `steak1`) the planner cannot tell whether a meat found inside the grill (G2/G3 `steak`) is already cooked. The baseline summary reports this limitation. From Phase 3 the labels (`raw_meat`, `cooked_meat`) carry the status.
2. **`open(l)` precondition** "no object is on the top surface of l": accepted.
3. **Region names only**, without descriptions: accepted. Names that hint at a purpose, with proposed neutral renames (not applied yet):

   | Region | Hint | Proposed name | Why |
   |---|---|---|---|
   | `table_staging_area` | "staging" suggests a temporary holding place, i.e. how to use it | `table_center_area` | centre of the table, in front of the robot |
   | `pantry_area` | "pantry" says groceries belong or start there | `table_right_area` | right side of the table from the robot's view |
   | `prep_area` | "prep" suggests uncooked meat is prepared there (a raw/cooked hint) | `grill_side_area` | the surface beside the grill |
   | `serving_area` | purpose-named, but it is the goal's own wording ("in the serving area") | keep | renaming would break the link to the goal text |
   | `table`, `cupboard_shelf`, `inside_box`, `box_lid_top`, `inside_grill`, `plate_top`, `dish_rack` | none: physical descriptions | keep | — |

   **Applied** (approved 2026-09-25) in prompt v2 only: v2 prompts and the `valid_regions` sent to the server use the neutral names; the parser maps them back (`region_aliases.PLANNER_REGION_NAMES`), and logs, evaluator and executor keep the canonical names. Legacy prompts are unchanged.
4. **Reasoning before `FINAL ACTIONS:`** is allowed. For `prompt.version=v2` the client parses only the text after the last `FINAL ACTIONS:` line; an answer without that line is a plan-check failure (`planner_output_not_parseable`). The text before it is logged as `planning_event.reasoning` in `trial_log.jsonl`, and the full raw output as `raw_output`.

## 6. Corrective replan prompt (Phase 5, `replan.output_mode = corrective`)

Used for a replan after a trigger: an IF-rule trigger, and from Phase 7b also a discovery trigger (`replan.trigger_mode = discovery`), which lists its trigger objects with the same labels so the two modes differ only in which objects are listed. Replans after execution failures keep the full-replan prompt above.

What changes compared with the v2 replan prompt:
- **System prompt:** the output format asks for blocks after a `FINAL BLOCKS:` line (objects, urgency `urgent`/`deferred`, insert `front` / `after <id>` / `end`, one-sentence reason, actions). Everything else is unchanged. From Phase 7b the format also says: "The actions of a block must end with the gripper empty. If a listed object needs no action, handle it with a block whose actions section is the single line NO_ACTIONS; such a block needs no urgency or insert line. If no listed object needs any action, write NO_ACTIONS as the only line after FINAL BLOCKS:." (snapshot `prompt_v2_kitchen_corrective_system.txt`).
- **Why a new plan is requested:** one plain fact per trigger object with the labels plan.md 4.2 asks for: relevant or not, in its goal state or not, and whether it lies where the remaining plan places objects (computed by the system from geometry; no coordinates).
- **What to plan** (new section): plan only for the listed objects; keep the remaining plan; do not move goal-attained or unlisted irrelevant objects; "Decide each block's urgency and where it goes in the remaining plan by considering what would go wrong if its actions were delayed."
- A re-query after a rejected proposal adds one fact: "Your previous blocks were rejected (failure code …): <reason>". From Phase 7b every rejection is re-queried this way, including an unknown name, a block that ends while holding (`block_ends_holding`), an invalid merged plan and a repeated output ("This output was already tried in the same state and it did not work.").
- No in-context examples. Nothing in the prompt names a variant or its expected answer.

**Decision (approved):** the urgency sentence is neutral. The plan.md 5.2 examples ("an object lying where other objects will be placed", "food that would be cooked again") give away the K1/K3 and G1/G2 answers and are removed. They are kept behind `prompt.corrective_hints=on` (default `off`) for a possible hinted-vs-neutral comparison; every real-model run uses the neutral version. Snapshots: `llm_pipeline/tests/snapshots/prompt_v2_kitchen_corrective_{system,user}.txt`.

Rendered example (the kitchen test scene of `llm_pipeline/tests/test_if_where_pipeline.py`: the box opens and reveals a phone in its placement area):

```
## Remaining plan (not executed yet)
- a4: pick(mug2)
- a5: place(mug2, inside_box)

## Why a new plan is requested
- After open(box_lid), these observed objects are not handled by the remaining plan:
  - phone (in inside_box): not relevant to the goal; lies where the remaining plan places objects into inside_box

## What to plan
- Plan actions only for the objects listed under "Why a new plan is requested". The remaining plan stays as it is: do not repeat, reorder or remove its actions.
- Do not move objects that are already in their goal state, and do not move objects that are not relevant to the goal unless they are listed.
- Decide each block's urgency and where it goes in the remaining plan by considering what would go wrong if its actions were delayed.
```

Expected answer form (not shown to the planner):

```
FINAL BLOCKS:
BLOCK
objects: phone
urgency: urgent
insert: front
reason: it lies where the mug will be placed
actions:
pick(phone)
place(phone, table)
END BLOCK
```
