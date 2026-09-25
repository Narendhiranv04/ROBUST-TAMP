"""Run one trial through the full pipeline with a ground-truth oracle planner.

    python -m llm_pipeline.oracle_trial_runner --variant K1 --headless --output-dir /tmp/k1_oracle

This is a smoke test of the trial path (scene state, prompts, plan check,
execution, JSONL log, evaluator) that needs no planner model or GPU. The
oracle answers every planner call with the remaining ground-truth actions from
``llm_pipeline/debug_sequences/<V>_gt_as_is.txt``, leaving out pick/place pairs
for objects the robot has not observed yet, so hidden objects are only planned
for after the replan that reveals them. It is not a model trial.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm_pipeline import trial_runner  # noqa: E402
from llm_pipeline.flags import PipelineFlags  # noqa: E402
from llm_pipeline.metrics import parse_action_string  # noqa: E402
from llm_pipeline.object_aliases import canonical_object_name  # noqa: E402
from llm_pipeline.pipeline import LLMOnlyReplanningPipeline  # noqa: E402
from llm_pipeline.pipeline_types import FailureEvent, FailureSource, FailureStage, PlanResult  # noqa: E402
from llm_pipeline.strict_parser import StrictActionParser, StrictParseError  # noqa: E402

SEQUENCE_DIR = ROOT_DIR / 'llm_pipeline' / 'debug_sequences'


def _canonical_action(line: str) -> str:
    """Use the pipeline's canonical object names (e.g. scene 'soup' is planned as 'can_of_beans')."""
    name, _, rest = line.partition('(')
    args = [arg.strip() for arg in rest.rstrip(')').split(',')]
    args[0] = canonical_object_name(args[0])
    return f"{name.strip()}({', '.join(args)})"


def load_gt_actions(variant_id: str) -> List[str]:
    path = SEQUENCE_DIR / f'{variant_id.upper()}_gt_as_is.txt'
    actions = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if parse_action_string(line) is not None and not line.startswith('#'):
            actions.append(_canonical_action(line))
    return actions


class OraclePlanner:
    """Answers with the remaining ground-truth actions on observed objects."""

    def __init__(self, gt_actions: List[str], executor_ref):
        self.gt_actions = list(gt_actions)
        self._executor_ref = executor_ref
        self.model_alias = 'gt_oracle'
        self.model_name = 'gt_oracle'
        self.quantization = 'none'
        self.loaded = True
        self.parser = StrictActionParser()
        self.prompts = []

    def load_model(self) -> bool:
        return True

    def _remaining(self) -> List[str]:
        executor = self._executor_ref()
        completed = list(getattr(executor, 'completed_primitive_actions', []) or [])
        remaining = list(self.gt_actions)
        for action in completed:
            if action in remaining:
                remaining.remove(action)
        return remaining

    def plan(self, bundle) -> PlanResult:
        self.prompts.append((bundle.system_prompt, bundle.user_prompt))
        visible = set(self.parser.planner_visible_objects())
        remaining = self._remaining()
        chosen: List[str] = []
        index = 0
        while index < len(remaining):
            parsed = parse_action_string(remaining[index])
            obj = (parsed or {}).get('args', [None])[0]
            if parsed and parsed['action'] == 'pick' and obj not in visible:
                index += 2  # skip the pick/place pair of an object the robot has not observed
                continue
            chosen.append(remaining[index])
            index += 1
        raw = 'FINAL ACTIONS:\n' + ('\n'.join(chosen) if chosen else 'NO_ACTIONS')
        held = (bundle.metadata or {}).get('held_object')
        try:
            actions = self.parser.parse(raw, held_object=held)
        except StrictParseError as exc:
            return PlanResult(False, [], raw, 0.0, str(exc), FailureEvent(
                failure_id=exc.failure_id, stage=FailureStage.BEFORE_EXECUTION, source=FailureSource.VALIDATION,
                action=None, evidence={'fact': exc.fact, 'raw_output': raw}, should_replan=True, message=str(exc),
            ))
        return PlanResult(True, actions, raw, 0.0)

    def get_debug_info(self):
        return {'model_alias': self.model_alias, 'model_name': self.model_name, 'quantization': 'none'}


def run_oracle_trial(variant_id: str, output_dir: Path, headless: bool = True,
                     flags: Optional[PipelineFlags] = None, max_replans: int = 10) -> dict:
    gt_actions = load_gt_actions(variant_id)

    class OraclePipeline(LLMOnlyReplanningPipeline):
        def __init__(self, config):
            super().__init__(config=config, planner=OraclePlanner(gt_actions, lambda: self.executor))

    original = trial_runner.LLMOnlyReplanningPipeline
    trial_runner.LLMOnlyReplanningPipeline = OraclePipeline
    try:
        return trial_runner.run_trial(
            variant_id=variant_id,
            model_alias='gt_oracle',
            icl_mode='zero_shot',
            max_replans=max_replans,
            headless=headless,
            output_dir=output_dir,
            live_masks=False,
            flags=flags,
        )
    finally:
        trial_runner.LLMOnlyReplanningPipeline = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--variant', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--flag', action='append', default=[], metavar='NAME=VALUE')
    parser.add_argument('--max-replans', type=int, default=10)
    parser.add_argument('--headless', action='store_true', help='(default)')
    args = parser.parse_args()
    record = run_oracle_trial(args.variant, Path(args.output_dir), headless=not args.gui,
                              flags=PipelineFlags.from_assignments(args.flag), max_replans=args.max_replans)
    print(json.dumps({key: record.get(key) for key in (
        'variant_id', 'episode_success', 'partial_goal_completion', 'total_cycles', 'total_replans',
        'completed_actions', 'failure_reason')}, indent=2))


if __name__ == '__main__':
    main()
