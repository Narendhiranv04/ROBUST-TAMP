# Diagnostics

292 trials (0 infrastructure, excluded). Definitions: docs/DIAGNOSTICS.md.

## Primary cause (sums to 100% with successes), per condition

| condition | trials | success_pct | plan_format_error_pct | plan_rule_error_pct | corrective_sub_plan_error_pct | insertion_error_pct | task_plan_error_pct | motion_grasp_error_pct | merge_conflict_pct | replan_budget_exhausted_pct | trigger_accuracy_pct | first_proposal_urgency_accuracy_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | 140 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 92.9 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | 6 | 33.3 | 0.0 | 0.0 | 0.0 | 66.7 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | 6 | 66.7 | 0.0 | 0.0 | 0.0 | 33.3 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | 28 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | 28 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | 28 | 96.4 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3.6 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | 28 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | 14 | 92.9 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 7.1 | 92.9 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | 14 | 92.9 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 7.1 | 100.0 | 100.0 |

## Occurrences (at least once, recovered or not), per condition

| condition | trials | plan_format_error_pct | plan_rule_error_pct | corrective_sub_plan_error_pct | insertion_error_pct | task_plan_error_pct | motion_grasp_error_pct | merge_conflict_pct | replan_budget_exhausted_pct |
|---|---|---|---|---|---|---|---|---|---|
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | 140 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.4 | 0.0 | 0.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | 6 | 0.0 | 0.0 | 0.0 | 66.7 | 0.0 | 0.0 | 0.0 | 33.3 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | 6 | 0.0 | 0.0 | 0.0 | 33.3 | 0.0 | 0.0 | 0.0 | 33.3 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | 28 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3.6 | 0.0 | 0.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | 28 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 10.7 | 0.0 | 0.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | 28 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 14.3 | 0.0 | 3.6 |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | 28 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 3.6 | 0.0 | 0.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | 14 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 14.3 | 0.0 | 7.1 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | 14 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 7.1 | 0.0 | 7.1 |

## Primary cause per variant

| condition | variant | trials | success_pct | plan_format_error_pct | plan_rule_error_pct | corrective_sub_plan_error_pct | insertion_error_pct | task_plan_error_pct | motion_grasp_error_pct | merge_conflict_pct | replan_budget_exhausted_pct | trigger_accuracy_pct | first_proposal_urgency_accuracy_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.G0 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.G1 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.G1-n1 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.G2 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.G3 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K0 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K1 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K1-w1 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K1-w2 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K2 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K3 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K3-n2 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K3-n3 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=discovery out=full_replan ins=planner par=false budget=10 | FINAL.K4 | 10 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | FINAL.G1 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | FINAL.G2 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | FINAL.G3 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | FINAL.K1 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | FINAL.K3 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_end par=false budget=10 | FINAL.K4 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | FINAL.G1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | FINAL.G2 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | FINAL.G3 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | FINAL.K1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | FINAL.K3 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=always_front par=false budget=10 | FINAL.K4 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.G0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.G1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.G1-n1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.G2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.G3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K1-w1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K1-w2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K3-n2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K3-n3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 | FINAL.K4 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.G0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.G1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.G1-n1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.G2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.G3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K1-w1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K1-w2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K3-n2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K3-n3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=false budget=10 delay=20s | FINAL.K4 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G1-n1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1-w1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1-w2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3-n2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3-n3 | 2 | 50.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 50.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K4 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.G0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.G1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.G1-n1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.G2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.G3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K0 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K1-w1 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K1-w2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K3-n2 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K3-n3 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=false trig=if_rule out=full_replan ins=planner par=false budget=10 | FINAL.K4 | 2 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G0 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G1-n1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G3 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K0 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1-w1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1-w2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3-n2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3-n3 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=discovery out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K4 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G0 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G1-n1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.G3 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K0 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1-w1 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K1-w2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 |  |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3-n2 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K3-n3 | 1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 | 100.0 |
| gt_oracle mem=true trig=if_rule out=corrective ins=planner par=true budget=10 delay=20s | FINAL.K4 | 1 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 100.0 | 100.0 |

Failed trials without a primary area: 0
