# Phase 4: IF rule

Oracle planner (ground-truth actions for observed objects). "Triggers" counts replans caused by a
trigger (`if_rule_trigger` / `new_object_discovered`); "trigger objects" lists them in order.
"Expected" is the variant spec (docs/VARIANTS.md). Trigger accuracy: triggered objects match the spec
(every non-ignored object triggered, no ignored object triggered).

| Variant | Mode | Trials | Triggers per trial | Trigger objects | Expected | Trigger accuracy | Success |
|---|---|---|---|---|---|---|---|
| FINAL.K0 | discovery | 2 | 0 / 0 | — | none | 100% | 100% |
| FINAL.K0 | if_rule | 2 | 0 / 0 | — | none | 100% | 100% |
| FINAL.G0 | discovery | 2 | 0 / 0 | — | none | 100% | 100% |
| FINAL.G0 | if_rule | 2 | 0 / 0 | — | none | 100% | 100% |
| FINAL.K1 | discovery | 2 | 1 / 1 | phone | phone | 100% | 100% |
| FINAL.K1 | if_rule | 2 | 1 / 1 | phone | phone | 100% | 100% |
| FINAL.K2 | discovery | 2 | 1 / 1 | phone | none | 0% | 100% |
| FINAL.K2 | if_rule | 2 | 0 / 0 | — | none | 100% | 100% |
| FINAL.K3 | discovery | 2 | 1 / 1 | can_of_beans | can_of_beans | 100% | 100% |
| FINAL.K3 | if_rule | 2 | 1 / 1 | can_of_beans | can_of_beans | 100% | 100% |
| FINAL.K4 | discovery | 2 | 1 / 1 | can_of_beans | can_of_beans | 100% | 100% |
| FINAL.K4 | if_rule | 2 | 1 / 1 | can_of_beans | can_of_beans | 100% | 100% |
| FINAL.G1 | discovery | 2 | 1 / 1 | cooked_meat_1,cooked_meat_2 | cooked_meat_1, cooked_meat_2 | 100% | 100% |
| FINAL.G1 | if_rule | 2 | 1 / 1 | cooked_meat_1,cooked_meat_2 | cooked_meat_1, cooked_meat_2 | 100% | 100% |
| FINAL.G2 | discovery | 2 | 1 / 1 | cooked_meat_1,raw_meat_2 | cooked_meat_1, raw_meat_2 | 100% | 100% |
| FINAL.G2 | if_rule | 2 | 1 / 1 | cooked_meat_1,raw_meat_2 | cooked_meat_1, raw_meat_2 | 100% | 100% |
| FINAL.G3 | discovery | 2 | 1 / 1 | raw_meat_2,raw_meat_3 | raw_meat_2, raw_meat_3 | 100% | 100% |
| FINAL.G3 | if_rule | 2 | 1 / 1 | raw_meat_2,raw_meat_3 | raw_meat_2, raw_meat_3 | 100% | 100% |
| FINAL.K3-n2 | discovery | 2 | 1 / 1 | can_of_beans,can_of_beans_2 | can_of_beans, can_of_beans_2 | 100% | 100% |
| FINAL.K3-n2 | if_rule | 2 | 1 / 1 | can_of_beans,can_of_beans_2 | can_of_beans, can_of_beans_2 | 100% | 100% |
| FINAL.K3-n3 | discovery | 2 | 1 / 1 | can_of_beans,can_of_beans_2,can_of_beans_3 | can_of_beans, can_of_beans_2, can_of_beans_3 | 100% | 100% |
| FINAL.K3-n3 | if_rule | 2 | 1 / 1 | can_of_beans,can_of_beans_2,can_of_beans_3 | can_of_beans, can_of_beans_2, can_of_beans_3 | 100% | 100% |
| FINAL.G1-n1 | discovery | 2 | 1 / 1 | cooked_meat_1 | cooked_meat_1 | 100% | 100% |
| FINAL.G1-n1 | if_rule | 2 | 1 / 1 | cooked_meat_1 | cooked_meat_1 | 100% | 100% |
| FINAL.K1-w1 | discovery | 2 | 1 / 1 | phone | phone | 100% | 100% |
| FINAL.K1-w1 | if_rule | 2 | 1 / 1 | phone | phone | 100% | 100% |
| FINAL.K1-w2 | discovery | 2 | 1 / 1 | phone | phone | 100% | 100% |
| FINAL.K1-w2 | if_rule | 2 | 1 / 1 | phone | phone | 100% | 100% |
