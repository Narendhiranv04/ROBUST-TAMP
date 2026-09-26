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
    from evaluation.final_variants import get_final_variant, is_final_variant

    if is_final_variant(variant_id):
        return list(get_final_variant(variant_id).gt_actions)
    path = SEQUENCE_DIR / f'{variant_id.upper()}_gt_as_is.txt'
    actions = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if parse_action_string(line) is not None and not line.startswith('#'):
            actions.append(_canonical_action(line))
    return actions


class OraclePlanner:
    """Answers with the remaining ground-truth actions on observed objects."""

    def __init__(self, gt_actions: List[str], executor_ref, urgency: Optional[dict] = None, delay_s: float = 0.0,
                 expected_if: Optional[dict] = None):
        self.gt_actions = list(gt_actions)
        self._executor_ref = executor_ref
        self.urgency = dict(urgency or {})       # final variants: expected urgency per trigger object
        self.expected_if = dict(expected_if or {})   # final variants: expected IF decision per hidden object
        self.delay_s = float(delay_s)            # simulated planner latency (Phase 6)
        self.model_alias = 'gt_oracle'
        self.model_name = 'gt_oracle'
        self.quantization = 'none'
        self.loaded = True
        self.parser = StrictActionParser()
        self.prompts = []

    def load_model(self) -> bool:
        return True

    def planner_settings(self) -> dict:
        return {'planner': 'gt_oracle', 'model_name': 'gt_oracle', 'thinking_mode': None, 'format_repair': False,
                'simulated_planner_delay_s': self.delay_s}

    def _remaining(self) -> List[str]:
        executor = self._executor_ref()
        completed = list(getattr(executor, 'completed_primitive_actions', []) or [])
        remaining = list(self.gt_actions)
        for action in completed:
            if action in remaining:
                remaining.remove(action)
        return remaining

    def _corrective_blocks(self, metadata) -> str:
        """Blocks for the trigger objects: ground-truth actions, the variant spec's urgency.

        An urgent object whose goal is the plate is first parked on the table (urgent,
        front) and plated once the plate is in the serving area (deferred).
        """
        remaining = list(metadata.get('remaining_plan') or [])
        plate_anchor = next((action_id for action_id, action in remaining
                             if action.replace(' ', '') == 'place(plate,serving_area)'), None)
        blocks = []
        triggers = list(metadata.get('trigger_objects') or [])
        # An object the variant spec says to ignore (e.g. K2's phone, listed by the discovery
        # trigger) needs no action.
        ignored = [obj for obj in triggers if self.expected_if.get(obj) == 'ignore']
        if triggers and len(ignored) == len(triggers):
            return 'FINAL BLOCKS:\nNO_ACTIONS'
        for obj in triggers:
            if obj in ignored:
                blocks.append(('no_action', None, obj, []))
                continue
            pairs = []
            for index, action in enumerate(self.gt_actions[:-1]):
                parsed = parse_action_string(action) or {}
                if parsed.get('action') == 'pick' and (parsed.get('args') or [None])[0] == obj:
                    pairs = [action, self.gt_actions[index + 1]]
            if not pairs:
                pairs = [f'pick({obj})', f'place({obj}, table)']
            goal = (parse_action_string(pairs[1]) or {}).get('args', [None, None])[1]
            if self.urgency.get(obj) == 'urgent':
                if goal == 'plate_top':
                    blocks.append(('urgent', 'front', obj, [f'pick({obj})', f'place({obj}, table)']))
                    blocks.append(('deferred', f'after {plate_anchor}' if plate_anchor else 'end', obj, pairs))
                else:
                    blocks.append(('urgent', 'front', obj, pairs))
            else:
                blocks.append(('deferred', 'end', obj, pairs))
        lines = ['FINAL BLOCKS:']
        for urgency, insert, obj, actions in blocks:
            if urgency == 'no_action':
                lines += ['BLOCK', f'objects: {obj}', 'reason: ground-truth oracle', 'actions:', 'NO_ACTIONS',
                          'END BLOCK']
                continue
            lines += ['BLOCK', f'objects: {obj}', f'urgency: {urgency}', f'insert: {insert}',
                      'reason: ground-truth oracle', 'actions:', *actions, 'END BLOCK']
        return '\n'.join(lines)

    def plan(self, bundle) -> PlanResult:
        self.prompts.append((bundle.system_prompt, bundle.user_prompt))
        if self.delay_s > 0:
            import time as _time

            _time.sleep(self.delay_s)
        if (bundle.metadata or {}).get('output_format') == 'corrective_blocks':
            return PlanResult(True, [], self._corrective_blocks(bundle.metadata or {}), self.delay_s)
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
        held = (bundle.metadata or {}).get('held_object')
        # After a failed place the pick is already in the history: pick the object
        # again before placing it (the gripper is empty after a failed place).
        repaired: List[str] = []
        holding = held
        for action in chosen:
            parsed = parse_action_string(action) or {}
            obj = (parsed.get('args') or [None])[0]
            if parsed.get('action') == 'place' and holding != obj:
                repaired.append(f'pick({obj})')
            if parsed.get('action') == 'pick':
                holding = obj
            elif parsed.get('action') == 'place':
                holding = None
            repaired.append(action)
        chosen = repaired
        raw = 'FINAL ACTIONS:\n' + ('\n'.join(chosen) if chosen else 'NO_ACTIONS')
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
                     flags: Optional[PipelineFlags] = None, max_replans: Optional[int] = None,
                     seed: Optional[int] = None, delay_s: float = 0.0, attempt: int = 1) -> dict:
    from evaluation.final_variants import get_final_variant, is_final_variant

    gt_actions = load_gt_actions(variant_id)
    spec = get_final_variant(variant_id) if is_final_variant(variant_id) else None
    urgency = dict(spec.expected_urgency) if spec is not None else {}
    expected_if = dict(spec.expected_if) if spec is not None else {}

    class OraclePipeline(LLMOnlyReplanningPipeline):
        def __init__(self, config):
            super().__init__(config=config, planner=OraclePlanner(gt_actions, lambda: self.executor, urgency, delay_s,
                                                                  expected_if))

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
            seed=seed,
            trial_index=(seed + 1 if seed is not None else 1),
            real_model=False,
            simulated_planner_delay_s=delay_s,
            attempt=attempt,
        )
    finally:
        trial_runner.LLMOnlyReplanningPipeline = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--variant', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--flag', action='append', default=[], metavar='NAME=VALUE')
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--attempt', type=int, default=1, help='Attempt number (infrastructure reruns)')
    parser.add_argument('--headless', action='store_true', help='(default)')
    parser.add_argument('--planner-delay', type=float, default=0.0,
                        help='Simulated planner latency in seconds (Phase 6 tests)')
    args = parser.parse_args()
    record = run_oracle_trial(args.variant, Path(args.output_dir), headless=not args.gui,
                              flags=PipelineFlags.from_assignments(args.flag),
                              seed=args.seed, delay_s=args.planner_delay, attempt=args.attempt)
    print(json.dumps({key: record.get(key) for key in (
        'variant_id', 'episode_success', 'partial_goal_completion', 'total_cycles', 'total_replans',
        'completed_actions', 'failure_reason')}, indent=2))


if __name__ == '__main__':
    main()
