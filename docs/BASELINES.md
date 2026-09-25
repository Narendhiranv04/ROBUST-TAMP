# External comparison baselines

plan.md Phase 8.3 (decision 2026-09-25): VLM-TAMP, OWL-TAMP and EPoG-TAMP are **re-implemented** as planner modules inside our pipeline (their planning and replanning logic on our robot, executor, scenes and log schema), not ported with their original stacks. They are labeled "re-implementations" everywhere. This file records every difference from the original methods. Not started yet.

- **Source:** https://github.com/Narendhiranv04/GRAB-TAMP, branch `baseline_executions`, commit `f2976cc`, cloned read-only into `external/GRAB-TAMP` (git-ignored).
- **Status:** inspected only. Nothing has been run or modified.

## Status per baseline

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
