"""A full pipeline trial (flags, checks and prompts as for a model) with a scripted planner.

Planner call k answers with the k-th output of a scenario file (outputs separated by lines
``=====``, planner-facing names; the last one repeats). Used to check execution paths a model can
reach and the ground-truth sequences never do, e.g. a place planned while the object is already
held (its place was refused by a pre-action check). Scenarios: evaluation/held_place_scenarios/.

    python -m llm_pipeline.scripted_trial_runner --variant FINAL.K0 \\
        --scenario evaluation/held_place_scenarios/K0_held_to_table.txt --output-dir /tmp/k0 [--seed 0]
"""
import argparse
import json
from pathlib import Path

from llm_pipeline import oracle_trial_runner, trial_runner
from llm_pipeline.pipeline import LLMOnlyReplanningPipeline
from llm_pipeline.pipeline_types import FailureEvent, FailureSource, FailureStage, PlanResult
from llm_pipeline.strict_parser import StrictParseError

SEPARATOR = '====='


def load_outputs(path) -> list:
    return [block.strip() for block in Path(path).read_text().split(SEPARATOR) if block.strip()]


class ScriptedPlanner(oracle_trial_runner.OraclePlanner):
    def __init__(self, outputs, executor_ref):
        super().__init__([], executor_ref, {}, 0.0, {})
        self.outputs = list(outputs)

    def plan(self, bundle) -> PlanResult:
        self.prompts.append((bundle.system_prompt, bundle.user_prompt))
        raw = self.outputs[min(len(self.prompts), len(self.outputs)) - 1]
        held = (bundle.metadata or {}).get('held_object')
        try:
            actions = self.parser.parse(raw, held_object=held)
        except StrictParseError as exc:
            return PlanResult(False, [], raw, 0.0, str(exc), FailureEvent(
                failure_id=exc.failure_id, stage=FailureStage.BEFORE_EXECUTION, source=FailureSource.VALIDATION,
                action=None, evidence={'fact': exc.fact, 'raw_output': raw}, should_replan=True, message=str(exc)))
        return PlanResult(True, actions, raw, 0.0)


def run_scripted_trial(variant_id: str, scenario, output_dir: Path, seed: int = 0, icl_mode: str = 'zero_shot') -> dict:
    outputs = load_outputs(scenario)

    class ScriptedPipeline(LLMOnlyReplanningPipeline):
        def __init__(self, config):
            super().__init__(config=config, planner=ScriptedPlanner(outputs, lambda: self.executor))

    original = trial_runner.LLMOnlyReplanningPipeline
    trial_runner.LLMOnlyReplanningPipeline = ScriptedPipeline
    try:
        return trial_runner.run_trial(variant_id=variant_id, model_alias='gt_oracle', icl_mode=icl_mode,
                                      headless=True, output_dir=output_dir, live_masks=False, seed=seed,
                                      trial_index=seed + 1, real_model=False)
    finally:
        trial_runner.LLMOnlyReplanningPipeline = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--variant', required=True)
    parser.add_argument('--scenario', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--icl-mode', default='zero_shot')
    args = parser.parse_args()
    record = run_scripted_trial(args.variant, args.scenario, Path(args.output_dir), seed=args.seed, icl_mode=args.icl_mode)
    print(json.dumps({key: record.get(key) for key in ('success', 'termination_reason')}, default=str))


if __name__ == '__main__':
    main()
