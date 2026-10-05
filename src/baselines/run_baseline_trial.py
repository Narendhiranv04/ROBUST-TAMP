"""Run one baseline trial (VLM-TAMP, OWL-TAMP, LLM-Planner or Inner Monologue) in one of our variants.

    # a real-model trial (vLLM serving the profile's model on 127.0.0.1:8000)
    python -m baselines.run_baseline_trial --baseline vlm_tamp --variant FINAL.K1 --seed 0 \
        --output-dir runs/vlm_tamp/FINAL.K1/seed_00 --model qwen3-vl-8b-thinking --remote-url http://127.0.0.1:8000

    # a mock trial: ground-truth answers, no model server (plumbing test)
    python -m baselines.run_baseline_trial --baseline owl_tamp --variant FINAL.G0 --seed 0 --output-dir /tmp/g0 --mock

The trial goes through ``llm_pipeline.trial_runner.run_trial`` (scene setup, seeding, the
clean-tree and model-settings checks of a real-model trial, trial_start / trial_end logging,
labeled-rule validation), with the baseline's pipeline in place of ours; ``trial_log.jsonl``,
``record.json`` and the prompts/exchanges have the same layout as our runs, so
``evaluation/model_run_report`` and the table scripts read them unchanged.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm_pipeline import trial_runner  # noqa: E402
from llm_pipeline.flags import PipelineFlags  # noqa: E402

# A baseline runs its own loop: our replanning components stay off (memory, parallel planning),
# prompt v2 supplies the scene state view the baselines are given.
BASELINE_FLAGS = ('memory.enabled=false', 'parallel.enabled=false', 'prompt.version=v2')


def _vlm_tamp():
    from baselines.vlm_tamp import VLMTAMPPipeline
    return VLMTAMPPipeline


def _owl_tamp():
    from baselines.owl_tamp import OWLTAMPPipeline
    return OWLTAMPPipeline


def _llm_planner():
    from baselines.llm_planner import LLMPlannerPipeline
    return LLMPlannerPipeline


def _llm_planner_refprompt():
    from baselines.llm_planner import LLMPlannerReferencePromptPipeline
    return LLMPlannerReferencePromptPipeline


def _inner_monologue():
    from baselines.inner_monologue import InnerMonologuePipeline
    return InnerMonologuePipeline


def _epog():
    from baselines.epog import EPoGPipeline
    return EPoGPipeline


def _epog_language_goal():
    from baselines.epog import EPoGLanguageGoalPipeline
    return EPoGLanguageGoalPipeline


# baseline name (--baseline) -> its pipeline class
PIPELINES = {'vlm_tamp': _vlm_tamp, 'owl_tamp': _owl_tamp, 'llm_planner': _llm_planner,
             'llm_planner_refprompt': _llm_planner_refprompt, 'inner_monologue': _inner_monologue,
             'epog': _epog, 'epog_language_goal': _epog_language_goal}


def pipeline_class(baseline: str, mock: bool, gt_exec: bool = False):
    from baselines.gt_exec import GT_EXEC
    from baselines.mock import RESPONDERS, MockPlanner

    base = PIPELINES[baseline]()
    if gt_exec:
        class GTExecPipeline(GT_EXEC[baseline]):
            def __init__(self, config):
                super().__init__(config=config, planner=MockPlanner())

        return GTExecPipeline
    if not mock:
        return base

    class MockPipeline(base):
        responder = staticmethod(RESPONDERS[baseline])

        def __init__(self, config):
            super().__init__(config=config, planner=MockPlanner())

    return MockPipeline


def run(baseline: str, variant: str, output_dir: Path, seed: int, mock: bool, model: str, remote_url: str,
        max_new_tokens: int, headless: bool = True, attempt: int = 1, gt_exec: bool = False,
        icl_mode: str = 'zero_shot') -> dict:
    flags = PipelineFlags.from_assignments(list(BASELINE_FLAGS))
    mock = mock or gt_exec
    original = trial_runner.LLMOnlyReplanningPipeline
    trial_runner.LLMOnlyReplanningPipeline = pipeline_class(baseline, mock, gt_exec)
    try:
        return trial_runner.run_trial(
            variant_id=variant, model_alias='mock_gt' if mock else model, icl_mode=icl_mode,
            headless=headless, output_dir=output_dir, live_masks=False, flags=flags, seed=seed,
            trial_index=seed + 1, real_model=not mock, remote=not mock, remote_url=remote_url, remote_api='openai',
            vision=True, model_type='vlm', planner_max_new_tokens=max_new_tokens, attempt=attempt,
        )
    finally:
        trial_runner.LLMOnlyReplanningPipeline = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--baseline', required=True, choices=tuple(PIPELINES))
    parser.add_argument('--variant', required=True)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--mock', action='store_true', help='ground-truth answers, no model server')
    parser.add_argument('--gt-exec', action='store_true',
                        help="execute the variant's full GT plan through the baseline's execution code (no model)")
    parser.add_argument('--model', default='qwen3-vl-8b-thinking')
    parser.add_argument('--remote-url', default='http://127.0.0.1:8000')
    parser.add_argument('--planner-max-new-tokens', type=int, default=24576)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--icl-mode', default='zero_shot', choices=('zero_shot', 'examples_v2'),
                        help='examples_v2: the in-context examples of our ICL condition, in the baseline\'s format '
                             '(grill scene; baselines/icl_examples.py)')
    parser.add_argument('--gui', action='store_true')
    args = parser.parse_args()
    record = run(args.baseline, args.variant, Path(args.output_dir), args.seed, args.mock, args.model,
                 args.remote_url, args.planner_max_new_tokens, headless=not args.gui, attempt=args.attempt,
                 gt_exec=args.gt_exec, icl_mode=args.icl_mode)
    print(json.dumps({key: record.get(key) for key in (
        'variant_id', 'episode_success', 'partial_goal_completion', 'planner_invocations', 'completed_actions',
        'failure_reason')}, indent=2))


if __name__ == '__main__':
    main()
