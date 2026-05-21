# Grill Debug Trial Matrix

These files are designed for GUI scene-state debugging:

```sh
python llm_pipeline/debug_execution.py \
  --sequence-file llm_pipeline/debug_sequences/grill_trials/<file>.txt \
  --pipeline-wrapper --with-scene-state --gui
```

Each trial file contains one debug block and intentionally omits progress metadata. The debug runner will append the latest status after execution.

The suite keeps only stable, non-overlapping checks. Runtime/physics failures such as `object_dropped`, `no_ik_solution`, `executor_failure`, and scene-specific placement instability are intentionally left out because they depend on simulator state rather than deterministic parser or segmentation-state logic.

For grill scenes, the suite does not include "pick hidden object" or "lid not visible" trials. Those are generic guardrails in the execution stack, but they are not meaningful planned grill-scene failures when the planner should only use visible objects and `grill_lid` is normally visible.

## Variant Substitutions

| Variant | Primary transfer | Secondary object | Wrong move target | Closed-grill place object | Expected newly visible after open |
|---|---|---|---|---|---|
| `G1` | `chicken -> inside_grill` | `spam` | `plate` | `chicken -> inside_grill` | `spam` |
| `G2` | `plate -> plate_boundary` | `steak` | `chicken` | `chicken -> inside_grill` | `steak` |
| `G3` | `plate -> plate_boundary` | `steak` | `chicken` | `chicken -> inside_grill` | `spam, steak` |

## Expected Failures

| File | Expected failure id | Layer | Stage/source | Why it should stop |
|---|---|---|---|---|
| `G1_L1_parser_missing_preceding_move.txt` | `missing_preceding_move` | layer 1 | before execution / validation | First executable action is not preceded by `move`. |
| `G1_L1_parser_consecutive_moves.txt` | `consecutive_moves` | layer 1 | before execution / validation | Two `move(...)` actions appear back to back. |
| `G1_L1_parser_invalid_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(target)` does not match the next action target. |
| `G1_L1_parser_unknown_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `grill_ghost` is not a valid object or region. |
| `G1_L1_parser_unknown_region.txt` | `unknown_action_token` | layer 1 | before execution / validation | `grill_inside` is not a valid region; correct token is `inside_grill`. |
| `G1_L1_parser_orphan_place.txt` | `orphan_place` | layer 1 | before execution / validation | A place action appears without first picking that object. |
| `G1_L1_parser_pick_place_mismatch.txt` | `pick_place_mismatch` | layer 1 | before execution / validation | The placed object differs from the held object. |
| `G1_L1_parser_missing_post_pick_place.txt` | `missing_post_pick_place` | layer 1 | before execution / validation | Plan ends while still holding an object. |
| `G1_L2_precheck_closed_grill_place.txt` | `grill_lid_closed` | layer 2 | before execution / segmentation | Attempts to place a visible object into `inside_grill` before opening `grill_lid`; this is scene-state dependent. |
| `G1_L2_open_discovers_hidden_object.txt` | `new_object_discovered` | layer 2 | after execution / segmentation | Opening the grill reveals hidden objects and should stop for replanning. |
| `G2_L1_parser_missing_preceding_move.txt` | `missing_preceding_move` | layer 1 | before execution / validation | First executable action is not preceded by `move`. |
| `G2_L1_parser_consecutive_moves.txt` | `consecutive_moves` | layer 1 | before execution / validation | Two `move(...)` actions appear back to back. |
| `G2_L1_parser_invalid_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(target)` does not match the next action target. |
| `G2_L1_parser_unknown_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `grill_ghost` is not a valid object or region. |
| `G2_L1_parser_unknown_region.txt` | `unknown_action_token` | layer 1 | before execution / validation | `grill_inside` is not a valid region; correct token is `inside_grill`. |
| `G2_L1_parser_orphan_place.txt` | `orphan_place` | layer 1 | before execution / validation | A place action appears without first picking that object. |
| `G2_L1_parser_pick_place_mismatch.txt` | `pick_place_mismatch` | layer 1 | before execution / validation | The placed object differs from the held object. |
| `G2_L1_parser_missing_post_pick_place.txt` | `missing_post_pick_place` | layer 1 | before execution / validation | Plan ends while still holding an object. |
| `G2_L2_precheck_closed_grill_place.txt` | `grill_lid_closed` | layer 2 | before execution / segmentation | Attempts to place a visible object into `inside_grill` before opening `grill_lid`; this is scene-state dependent. |
| `G2_L2_open_discovers_hidden_object.txt` | `new_object_discovered` | layer 2 | after execution / segmentation | Opening the grill reveals hidden objects and should stop for replanning. |
| `G3_L1_parser_missing_preceding_move.txt` | `missing_preceding_move` | layer 1 | before execution / validation | First executable action is not preceded by `move`. |
| `G3_L1_parser_consecutive_moves.txt` | `consecutive_moves` | layer 1 | before execution / validation | Two `move(...)` actions appear back to back. |
| `G3_L1_parser_invalid_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(target)` does not match the next action target. |
| `G3_L1_parser_unknown_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `grill_ghost` is not a valid object or region. |
| `G3_L1_parser_unknown_region.txt` | `unknown_action_token` | layer 1 | before execution / validation | `grill_inside` is not a valid region; correct token is `inside_grill`. |
| `G3_L1_parser_orphan_place.txt` | `orphan_place` | layer 1 | before execution / validation | A place action appears without first picking that object. |
| `G3_L1_parser_pick_place_mismatch.txt` | `pick_place_mismatch` | layer 1 | before execution / validation | The placed object differs from the held object. |
| `G3_L1_parser_missing_post_pick_place.txt` | `missing_post_pick_place` | layer 1 | before execution / validation | Plan ends while still holding an object. |
| `G3_L2_precheck_closed_grill_place.txt` | `grill_lid_closed` | layer 2 | before execution / segmentation | Attempts to place a visible object into `inside_grill` before opening `grill_lid`; this is scene-state dependent. |
| `G3_L2_open_discovers_hidden_object.txt` | `new_object_discovered` | layer 2 | after execution / segmentation | Opening the grill reveals hidden objects and should stop for replanning. |

## Added Precision Failures

These additions cover distinct parser branches that were not covered by the first suite. They intentionally reuse some failure IDs only when the failing action position is different.

| File | Expected failure id | Layer | Stage/source | Why it should stop |
|---|---|---|---|---|
| `G1_L1_parser_missing_move_before_place.txt` | `missing_preceding_move` | layer 1 | before execution / validation | `place(...)` follows `pick(...)` directly, so the arm was not moved to the target region before placing. |
| `G1_L1_parser_missing_move_before_open.txt` | `missing_preceding_move` | layer 1 | before execution / validation | `open(grill_lid)` appears without a preceding `move(grill_lid)`. |
| `G1_L1_parser_invalid_place_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(plate)` is followed by `place(chicken, inside_grill)`, so the move target does not match the place region. |
| `G1_L1_parser_invalid_open_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(chicken)` is followed by `open(grill_lid)`, so the move target does not match the lid target. |
| `G1_L1_parser_unknown_pick_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `pick(grill_ghost)` references an unknown object while the preceding move is otherwise valid. |
| `G1_L1_parser_unknown_place_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `place(grill_ghost, inside_grill)` references an unknown object. |
| `G1_L1_parser_unknown_place_region.txt` | `unknown_action_token` | layer 1 | before execution / validation | `place(chicken, grill_inside)` references an unknown region; correct token is `inside_grill`. |
| `G1_L1_parser_unknown_lid_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `open(grill_ghost)` references an unknown lid object. |
| `G1_L1_parser_pick_while_holding.txt` | `pick_place_mismatch` | layer 1 | before execution / validation | A second `pick(...)` is attempted while already holding `chicken`. |
| `G1_L1_parser_open_while_holding.txt` | `missing_post_pick_place` | layer 1 | before execution / validation | The plan tries to open the lid before placing the held object. |
| `G1_L1_parser_dangling_final_move.txt` | `dangling_move` | layer 1 | before execution / validation | The plan ends with `move(chicken)` and no following action. |
| `G2_L1_parser_missing_move_before_place.txt` | `missing_preceding_move` | layer 1 | before execution / validation | `place(...)` follows `pick(...)` directly, so the arm was not moved to the target region before placing. |
| `G2_L1_parser_missing_move_before_open.txt` | `missing_preceding_move` | layer 1 | before execution / validation | `open(grill_lid)` appears without a preceding `move(grill_lid)`. |
| `G2_L1_parser_invalid_place_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(chicken)` is followed by `place(plate, plate_boundary)`, so the move target does not match the place region. |
| `G2_L1_parser_invalid_open_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(plate)` is followed by `open(grill_lid)`, so the move target does not match the lid target. |
| `G2_L1_parser_unknown_pick_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `pick(grill_ghost)` references an unknown object while the preceding move is otherwise valid. |
| `G2_L1_parser_unknown_place_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `place(grill_ghost, plate_boundary)` references an unknown object. |
| `G2_L1_parser_unknown_place_region.txt` | `unknown_action_token` | layer 1 | before execution / validation | `place(plate, grill_inside)` references an unknown region; correct token is `inside_grill`. |
| `G2_L1_parser_unknown_lid_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `open(grill_ghost)` references an unknown lid object. |
| `G2_L1_parser_pick_while_holding.txt` | `pick_place_mismatch` | layer 1 | before execution / validation | A second `pick(...)` is attempted while already holding `plate`. |
| `G2_L1_parser_open_while_holding.txt` | `missing_post_pick_place` | layer 1 | before execution / validation | The plan tries to open the lid before placing the held object. |
| `G2_L1_parser_dangling_final_move.txt` | `dangling_move` | layer 1 | before execution / validation | The plan ends with `move(plate)` and no following action. |
| `G3_L1_parser_missing_move_before_place.txt` | `missing_preceding_move` | layer 1 | before execution / validation | `place(...)` follows `pick(...)` directly, so the arm was not moved to the target region before placing. |
| `G3_L1_parser_missing_move_before_open.txt` | `missing_preceding_move` | layer 1 | before execution / validation | `open(grill_lid)` appears without a preceding `move(grill_lid)`. |
| `G3_L1_parser_invalid_place_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(chicken)` is followed by `place(plate, plate_boundary)`, so the move target does not match the place region. |
| `G3_L1_parser_invalid_open_move_target.txt` | `invalid_move_target` | layer 1 | before execution / validation | `move(plate)` is followed by `open(grill_lid)`, so the move target does not match the lid target. |
| `G3_L1_parser_unknown_pick_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `pick(grill_ghost)` references an unknown object while the preceding move is otherwise valid. |
| `G3_L1_parser_unknown_place_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `place(grill_ghost, plate_boundary)` references an unknown object. |
| `G3_L1_parser_unknown_place_region.txt` | `unknown_action_token` | layer 1 | before execution / validation | `place(plate, grill_inside)` references an unknown region; correct token is `inside_grill`. |
| `G3_L1_parser_unknown_lid_object.txt` | `unknown_action_token` | layer 1 | before execution / validation | `open(grill_ghost)` references an unknown lid object. |
| `G3_L1_parser_pick_while_holding.txt` | `pick_place_mismatch` | layer 1 | before execution / validation | A second `pick(...)` is attempted while already holding `plate`. |
| `G3_L1_parser_open_while_holding.txt` | `missing_post_pick_place` | layer 1 | before execution / validation | The plan tries to open the lid before placing the held object. |
| `G3_L1_parser_dangling_final_move.txt` | `dangling_move` | layer 1 | before execution / validation | The plan ends with `move(plate)` and no following action. |

## Quick Checks

Run one parser trial first:

```sh
python llm_pipeline/debug_execution.py \
  --sequence-file llm_pipeline/debug_sequences/grill_trials/G1_L1_parser_consecutive_moves.txt \
  --pipeline-wrapper --with-scene-state --gui
```

Run one layer-1 scene-state precheck:

```sh
python llm_pipeline/debug_execution.py \
  --sequence-file llm_pipeline/debug_sequences/grill_trials/G1_L2_precheck_closed_grill_place.txt \
  --pipeline-wrapper --with-scene-state --gui
```

Run one layer-2 discovery trial per variant:

```sh
for f in \
  llm_pipeline/debug_sequences/grill_trials/G1_L2_open_discovers_hidden_object.txt \
  llm_pipeline/debug_sequences/grill_trials/G2_L2_open_discovers_hidden_object.txt \
  llm_pipeline/debug_sequences/grill_trials/G3_L2_open_discovers_hidden_object.txt; do
  python llm_pipeline/debug_execution.py --sequence-file "$f" \
    --pipeline-wrapper --with-scene-state --gui
done
```

Optional headless sanity pass:

```sh
for f in llm_pipeline/debug_sequences/grill_trials/G*.txt; do
  python llm_pipeline/debug_execution.py --sequence-file "$f" \
    --pipeline-wrapper --with-scene-state --headless || true
done
```
