#!/bin/sh
# Oracle suites of Phases 3-6 (ceiling, IF, WHERE with both ablations, WHEN) plus two
# Phase 8 conditions that had no oracle run (IF ablation, full system with memory), with
# the same variants, seeds and flags as results/phase3-6. GT oracle planner, no model.
#
#   export PDDLSTREAM_DIR=...; . mujoco_port/activate_mujoco_env.sh
#   sh evaluation/rerun_oracle_suites.sh results/phase7b
#
# Run it from a clean checkout of one commit (e.g. a git worktree) so every trial_start
# records that commit with dirty=false. Two simulations at a time (--jobs 2).
set -e
OUT=${1:-results/phase7b}
M="python -m llm_pipeline.run_trial_matrix --planner oracle --jobs 2"
ALL="FINAL.K0 FINAL.G0 FINAL.K1 FINAL.K2 FINAL.K3 FINAL.K4 FINAL.G1 FINAL.G2 FINAL.G3 FINAL.K3-n2 FINAL.K3-n3 FINAL.G1-n1 FINAL.K1-w1 FINAL.K1-w2"
ABL="FINAL.K1 FINAL.K3 FINAL.K4 FINAL.G1 FINAL.G2 FINAL.G3"
IF="--flag replan.trigger_mode=if_rule"
COR="$IF --flag replan.output_mode=corrective"
PAR="--flag parallel.enabled=true"

$M --variants $ALL --seeds 0-9 --out "$OUT/phase3/oracle_ceiling" --title "Phase 3 oracle ceiling (discovery, full replan)"
$M --variants $ALL --seeds 0-1 --out "$OUT/phase4/if_rule" --title "Phase 4 IF rule (oracle)" -- $IF
$M --variants $ALL --seeds 0-1 --out "$OUT/phase5/corrective_planner" --title "Phase 5 corrective, planner insertion (oracle)" -- $COR
$M --variants $ABL --seeds 0 --out "$OUT/phase5/always_front" --title "Phase 5 always_front (oracle)" -- $COR --flag replan.insertion_mode=always_front
$M --variants $ABL --seeds 0 --out "$OUT/phase5/always_end" --title "Phase 5 always_end (oracle)" -- $COR --flag replan.insertion_mode=always_end
$M --variants $ALL --seeds 0-1 --out "$OUT/phase6/parallel_off" --title "Phase 6 parallel off, 20 s simulated planner delay (oracle)" -- $COR --planner-delay 20
$M --variants $ALL --seeds 0-1 --out "$OUT/phase6/parallel_on" --title "Phase 6 parallel on, 20 s simulated planner delay (oracle)" -- $COR $PAR --planner-delay 20
$M --variants $ALL --seeds 0 --out "$OUT/phase8_conditions/if_ablation" --title "Ablation: IF (discovery, corrective, parallel, memory; oracle, 20 s delay)" -- --flag memory.enabled=true --flag replan.trigger_mode=discovery --flag replan.output_mode=corrective $PAR --planner-delay 20
$M --variants $ALL --seeds 0 --out "$OUT/phase8_conditions/full_system" --title "Full system (memory, IF, corrective, parallel; oracle, 20 s delay)" -- --flag memory.enabled=true $COR $PAR --planner-delay 20

python -m evaluation.phase_reports phase4 "$OUT/phase4/if_rule" --discovery "$OUT/phase3/oracle_ceiling"
python -m evaluation.phase_reports phase5 "$OUT/phase5/corrective_planner" "$OUT/phase5/always_front" "$OUT/phase5/always_end"
python -m evaluation.phase_reports phase6 --on "$OUT/phase6/parallel_on" --off "$OUT/phase6/parallel_off"
python -m diagnostics.report "$OUT/phase3/oracle_ceiling" "$OUT/phase4/if_rule" "$OUT/phase5/corrective_planner" \
    "$OUT/phase5/always_front" "$OUT/phase5/always_end" "$OUT/phase6/parallel_off" "$OUT/phase6/parallel_on" \
    "$OUT/phase8_conditions/if_ablation" "$OUT/phase8_conditions/full_system" --out "$OUT/diagnostics"
python -m evaluation.check_place_regions "$OUT"
