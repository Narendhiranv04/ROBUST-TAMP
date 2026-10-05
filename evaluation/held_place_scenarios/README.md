# Held-object scenarios

Scripted planner outputs (one per planner call, separated by `=====`) for
`python -m llm_pipeline.scripted_trial_runner`. Each scenario picks an object, has its place
refused by a pre-action check (closed lid), and then places the object while it is still held,
a path the ground-truth sequences never take:

| Scenario | Variant | Held place | Expected |
|---|---|---|---|
| `K0_held_to_table.txt` | FINAL.K0 | `place(mug2, table)` | success, 5/5 goal relations |
| `K0_held_to_cupboard.txt` | FINAL.K0 | `place(mug1, cupboard_shelf)` | every action succeeds; 4/5 (mug1 is left in the cupboard on purpose) |
| `G0_held_to_prep_area.txt` | FINAL.G0 | `place(raw_meat_1, grill_side_area)` | success, 2/2 |
