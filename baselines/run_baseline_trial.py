"""Run one baseline trial (VLM-TAMP or OWL-TAMP) in one of our variants.

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


def pipeline_class(baseline: str, mock: bool):
    from baselines.mock import RESPONDERS, MockPlanner
    from baselines.owl_tamp import OWLTAMPPipeline
    from baselines.vlm_tamp import VLMTAMPPipeline

    base = {'vlm_tamp': VLMTAMPPipeline, 'owl_tamp': OWLTAMPPipeline}[baseline]
    if not mock:
        return base

    class MockPipeline(base):
        responder = staticmethod(RESPONDERS[baseline])

        def __init__(self, config):
            super().__init__(config=config, planner=MockPlanner())

    return MockPipeline


def run(baseline: str, variant: str, output_dir: Path, seed: int, mock: bool, model: str, remote_url: str,
        max_new_tokens: int, headless: bool = True, attempt: int = 1) -> dict:
    flags = PipelineFlags.from_assignments(list(BASELINE_FLAGS))
    original = trial_runner.LLMOnlyReplanningPipeline
    trial_runner.LLMOnlyReplanningPipeline = pipeline_class(baseline, mock)
    try:
        return trial_runner.run_trial(
            variant_id=variant, model_alias='mock_gt' if mock else model, icl_mode='zero_shot',
            headless=headless, output_dir=output_dir, live_masks=False, flags=flags, seed=seed,
            trial_index=seed + 1, real_model=not mock, remote=not mock, remote_url=remote_url, remote_api='openai',
            vision=True, model_type='vlm', planner_max_new_tokens=max_new_tokens, attempt=attempt,
        )
    finally:
        trial_runner.LLMOnlyReplanningPipeline = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--baseline', required=True, choices=('vlm_tamp', 'owl_tamp'))
    parser.add_argument('--variant', required=True)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--mock', action='store_true', help='ground-truth answers, no model server')
    parser.add_argument('--model', default='qwen3-vl-8b-thinking')
    parser.add_argument('--remote-url', default='http://127.0.0.1:8000')
    parser.add_argument('--planner-max-new-tokens', type=int, default=24576)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--gui', action='store_true')
    args = parser.parse_args()
    record = run(args.baseline, args.variant, Path(args.output_dir), args.seed, args.mock, args.model,
                 args.remote_url, args.planner_max_new_tokens, headless=not args.gui, attempt=args.attempt)
    print(json.dumps({key: record.get(key) for key in (
        'variant_id', 'episode_success', 'partial_goal_completion', 'planner_invocations', 'completed_actions',
        'failure_reason')}, indent=2))


if __name__ == '__main__':
    main()
