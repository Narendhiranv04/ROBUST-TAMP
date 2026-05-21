"""Run one LLM-only kitchen or grill trial and emit a structured JSON record."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.canonical_variants import get_variant_spec
from llm_pipeline.metrics import collect_failure_occurrences, score_variant_completion
from llm_pipeline.pipeline import LLMPipelineConfig, LLMOnlyReplanningPipeline


DEFAULT_RUN_OUTPUT_ROOT = ROOT_DIR / 'llm_pipeline' / 'results' / 'llm_runs'


def _configure_qt() -> None:
    os.environ.setdefault('COPPELIASIM_HEADLESS', '0')
    os.environ.pop('QT_PLUGIN_PATH', None)
    os.environ.setdefault('QT_LOGGING_RULES', '*.debug=false;qt.qpa.*=false')
    coppelia_root = os.environ.get('COPPELIASIM_ROOT') or os.path.expanduser('~/CoppeliaSim')
    for candidate in [
        os.path.join(coppelia_root, 'platforms'),
        os.path.join(coppelia_root, 'Qt', 'plugins', 'platforms'),
    ]:
        if candidate and os.path.isdir(candidate):
            os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH', candidate)
            break


def _repo_setup(headless: bool, variant_spec) -> None:
    os.environ['HEADLESS'] = 'True' if headless else 'False'
    os.environ['COPPELIASIM_HEADLESS'] = '1' if headless else '0'
    pddlstream_path = str(ROOT_DIR / 'pddlstream')
    existing = os.environ.get('PYTHONPATH', '').strip()
    os.environ['PYTHONPATH'] = f"{pddlstream_path}:{existing}" if existing else pddlstream_path

    if variant_spec.task_family == 'grill':
        os.environ['GRILL_SCENE_FILE'] = variant_spec.scene_path
        os.environ['GRILL_ALLOW_SCENE_OVERRIDE'] = 'True'
        os.environ['GRILL_SCENE_FILE_OVERRIDE'] = variant_spec.scene_path
        grill_dir = str(ROOT_DIR / 'grill_task2')
        if grill_dir not in sys.path:
            sys.path.insert(0, grill_dir)
    else:
        os.environ['KITCHEN_SCENE_FILE'] = variant_spec.scene_path


def _load_variant_env(variant_spec, goal_text: str, headless: bool):
    """Return a preconfigured env for variants that need GT-style startup."""
    if variant_spec.task_family != 'grill':
        return None

    # Reuse the same grill startup path that the visual debug sequence suite uses.
    from llm_pipeline.debug_execution import (
        DebugSequence,
        _configure_scene_env,
        _load_env_for_sequence,
    )

    sequence = DebugSequence(
        name=f'{variant_spec.variant_id}_llm_trial',
        variant=variant_spec.variant_id,
        goal=goal_text,
        actions=(),
    )
    _configure_scene_env(sequence, headless=headless)
    return _load_env_for_sequence(sequence)


def _text_only_contract_issues(preflight_record: Dict[str, Any]) -> list[str]:
    issues = list(preflight_record.get('prompt_contract_issues', []))
    prompt_trace = preflight_record.get('prompt_trace', {}) or {}
    bundle = prompt_trace.get('bundle', {}) or {}
    debug_snapshot = preflight_record.get('debug_snapshot', {}) or {}
    if any('image' in key for key in bundle):
        issues.append('image_key_in_prompt_bundle')
    if any('image' in key for key in debug_snapshot):
        issues.append('image_key_in_debug_snapshot')
    for field_name in ('system_prompt', 'user_prompt'):
        if field_name not in prompt_trace:
            issues.append(f'missing_{field_name}')
    return sorted(set(issues))


def _safe_path_token(value: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in {'-', '_'} else '_' for ch in str(value).strip())
    return cleaned.strip('_') or 'run'


def _default_run_dir(
    variant_id: str,
    model_alias: str,
    icl_mode: str,
    trial_index: int,
    output_root: Path,
) -> Path:
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    folder_name = (
        f"{timestamp}_"
        f"{_safe_path_token(variant_id.upper())}_"
        f"{_safe_path_token(model_alias)}_"
        f"{_safe_path_token(icl_mode)}_"
        f"trial_{int(trial_index):03d}"
    )
    return output_root.resolve() / folder_name


def _resolve_output_paths(
    variant_id: str,
    model_alias: str,
    icl_mode: str,
    trial_index: int,
    output_path: Optional[Path],
    output_dir: Optional[Path],
    output_root: Path,
) -> tuple[Path, Path]:
    if output_dir is not None:
        run_dir = output_dir.resolve()
        json_path = run_dir / 'record.json'
        txt_path = run_dir / 'failure_summary.txt'
        return json_path, txt_path

    if output_path is not None:
        json_path = output_path.resolve()
        return json_path, json_path.with_suffix('.txt')

    run_dir = _default_run_dir(
        variant_id=variant_id,
        model_alias=model_alias,
        icl_mode=icl_mode,
        trial_index=trial_index,
        output_root=output_root,
    )
    return run_dir / 'record.json', run_dir / 'failure_summary.txt'


def _latest_failure_event(record: Dict[str, Any]) -> Dict[str, Any]:
    summary = record.get('raw_summary') or {}
    failure_event = summary.get('last_failure_event') or {}
    if failure_event:
        return dict(failure_event)

    for cycle in reversed(summary.get('cycles') or []):
        cycle_failure = (cycle or {}).get('failure_event') or {}
        if cycle_failure:
            return dict(cycle_failure)

    preflight = record.get('preflight') or {}
    return dict(preflight.get('dry_run_failure_event') or {})


def _render_failure_summary(record: Dict[str, Any]) -> str:
    failure_event = _latest_failure_event(record)
    completed_actions = list(record.get('completed_actions') or [])
    remaining_actions = list(record.get('remaining_actions') or [])
    success = bool(record.get('raw_episode_success')) if record.get('raw_episode_success') is not None else bool(record.get('preflight_success'))
    status = 'passed' if success else 'failed'

    if record.get('preflight_only'):
        status = 'preflight_passed' if record.get('preflight_success') else 'preflight_failed'

    lines = [
        f"variant: {record.get('variant_id', '')}",
        f"task_family: {record.get('task_family', '')}",
        f"model: {record.get('model_alias', '')}",
        f"icl_mode: {record.get('icl_mode', '')}",
        f"trial_index: {record.get('trial_index', '')}",
        f"status: {status}",
        f"episode_success: {record.get('episode_success', record.get('preflight_success', ''))}",
        f"raw_episode_success: {record.get('raw_episode_success', '')}",
        f"total_cycles: {record.get('total_cycles', '')}",
        f"total_replans: {record.get('total_replans', '')}",
        f"completed_gt_subtasks: {record.get('completed_gt_subtasks', '')}/{record.get('gt_total_subtasks', '')}",
        f"completed_actions: {len(completed_actions)}",
        f"remaining_actions: {len(remaining_actions)}",
    ]

    if completed_actions:
        lines.append(f"last_completed_action: {completed_actions[-1]}")
    if remaining_actions:
        lines.append(f"next_remaining_action: {remaining_actions[0]}")

    lines.append('')
    lines.append('failure:')
    if failure_event:
        lines.extend([
            f"failure_id: {failure_event.get('failure_id', '')}",
            f"failure_layer: {failure_event.get('failure_layer', '')}",
            f"failure_stage: {failure_event.get('stage', '')}",
            f"failure_source: {failure_event.get('source', '')}",
            f"failure_action: {failure_event.get('action', '')}",
            f"failure_should_replan: {failure_event.get('should_replan', '')}",
            f"failure_message: {failure_event.get('message', '')}",
            f"failure_reason: {record.get('failure_reason', '')}",
            f"failure_evidence: {json.dumps(failure_event.get('evidence', {}) or {}, sort_keys=True, default=str)}",
        ])
    else:
        lines.append('failure_id: none')

    return '\n'.join(lines).rstrip() + '\n'


def run_trial(
    variant_id: str,
    model_alias: str,
    icl_mode: str,
    trial_index: int = 1,
    max_replans: int = 10,
    headless: bool = False,
    remote: bool = False,
    remote_url: str = '',
    replan_mode: str = 'on',
    preflight_only: bool = False,
    output_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    output_root: Path = DEFAULT_RUN_OUTPUT_ROOT,
    goal_override: Optional[str] = None,
    live_masks: bool = True,
    scene_state_trace: bool = False,
) -> Dict[str, Any]:
    variant_spec = get_variant_spec(variant_id)
    if not variant_spec.model_eval_supported:
        raise RuntimeError(
            f'Variant {variant_spec.variant_id} is not supported for the LLM-only runner: '
            f"{variant_spec.model_eval_reason or 'unsupported'}"
        )

    _configure_qt()
    goal_text = goal_override or variant_spec.goal_text
    _repo_setup(headless=headless, variant_spec=variant_spec)
    env = _load_variant_env(variant_spec, goal_text=goal_text, headless=headless)

    replanning_enabled = replan_mode != 'off'
    config = LLMPipelineConfig(
        model_alias=model_alias,
        icl_mode=icl_mode,
        max_replans=max_replans,
        enable_replanning=replanning_enabled,
        headless=headless,
        use_remote_planner=remote,
        remote_planner_url=remote_url,
        text_only=True,
        segmentation_first=True,
        pre_action_checks_enabled=replanning_enabled,
        post_action_checks_enabled=replanning_enabled,
        task_family=variant_spec.task_family,
        scene_path=variant_spec.scene_path,
        live_segmentation_view=bool(live_masks and not headless),
        scene_state_trace=bool(scene_state_trace),
    )
    pipeline = LLMOnlyReplanningPipeline(config=config)

    json_output_path, txt_output_path = _resolve_output_paths(
        variant_id=variant_spec.variant_id,
        model_alias=model_alias,
        icl_mode=icl_mode,
        trial_index=trial_index,
        output_path=output_path,
        output_dir=output_dir,
        output_root=output_root,
    )
    try:
        if not pipeline.initialize(env=env):
            raise RuntimeError('pipeline_initialize_failed')

        preflight = pipeline.preflight(goal_text)
        preflight_issues = _text_only_contract_issues(preflight)
        preflight['prompt_contract_issues'] = preflight_issues
        preflight['prompt_contract_ok'] = not preflight_issues
        preflight['preflight_success'] = (
            bool(preflight.get('loaded'))
            and bool(preflight.get('dry_run_plan_success'))
            and not preflight_issues
            and preflight.get('image_present') is False
        )

        if preflight_only:
            record = {
                'variant_id': variant_spec.variant_id,
                'task_family': variant_spec.task_family,
                'scene_path': variant_spec.scene_path,
                'trial_index': int(trial_index),
                'preflight_only': True,
                'model_alias': model_alias,
                'model_type': 'llm',
                'icl_mode': icl_mode,
                'goal_text': goal_text,
                'text_only': True,
                'segmentation_first': True,
                'replan_mode': replan_mode,
                'use_remote_planner': bool(remote),
                'remote_planner_url': remote_url or None,
                'pre_action_checks_enabled': replanning_enabled,
                'post_action_checks_enabled': replanning_enabled,
                'live_segmentation_view': bool(live_masks and not headless),
                'scene_state_trace': bool(scene_state_trace),
                'preflight_success': bool(preflight['preflight_success']),
                'preflight': preflight,
            }
        else:
            summary = pipeline.run(goal_text)
            completion = score_variant_completion(variant_spec.variant_id, summary.get('completed_actions', []))
            failure_occurrences = collect_failure_occurrences(summary.get('cycles', []), summary.get('failure_reason'))
            execution_skipped = bool(summary.get('execution_skipped', False))
            episode_success = None if execution_skipped else bool(summary.get('success')) and (
                completion['completed_gt_subtasks'] >= completion['gt_total_subtasks']
            )
            record = {
                'variant_id': variant_spec.variant_id,
                'task_family': variant_spec.task_family,
                'scene_path': variant_spec.scene_path,
                'trial_index': int(trial_index),
                'preflight_only': False,
                'action_sequence_length': variant_spec.action_sequence_length,
                'gt_total_subtasks': completion['gt_total_subtasks'],
                'completed_gt_subtasks': completion['completed_gt_subtasks'],
                'subtask_completion_rate': completion['subtask_completion_rate'],
                'bucket_breakdown': completion['bucket_breakdown'],
                'observed_subtasks': completion['observed_subtasks'],
                'extra_observed_subtasks': completion['extra_observed_subtasks'],
                'model_alias': summary.get('model_alias', model_alias),
                'model_type': 'llm',
                'icl_mode': icl_mode,
                'prompt_mode': summary.get('prompt_mode', icl_mode),
                'goal_text': goal_text,
                'text_only': True,
                'segmentation_first': True,
                'replan_mode': summary.get('replan_mode', replan_mode),
                'planning_success': bool(summary.get('success')),
                'execution_skipped': execution_skipped,
                'use_remote_planner': bool(remote),
                'remote_planner_url': remote_url or None,
                'pre_action_checks_enabled': bool(summary.get('pre_action_checks_enabled', replanning_enabled)),
                'post_action_checks_enabled': bool(summary.get('post_action_checks_enabled', replanning_enabled)),
                'live_segmentation_view': bool(live_masks and not headless),
                'scene_state_trace': bool(scene_state_trace),
                'episode_success': episode_success,
                'raw_episode_success': None if execution_skipped else bool(summary.get('success')),
                'total_cycles': int(summary.get('total_cycles', 0)),
                'total_replans': int(summary.get('total_replans', 0)),
                'planned_actions': list(summary.get('planned_actions', [])),
                'completed_actions': list(summary.get('completed_actions', [])),
                'remaining_actions': list(summary.get('remaining_actions', [])),
                'failure_reason': summary.get('failure_reason'),
                'failure_occurrences': failure_occurrences,
                'episode_time_s': summary.get('episode_time_s'),
                'preflight': preflight,
                'raw_summary': summary,
            }

        record['output_json_path'] = str(json_output_path)
        record['failure_summary_path'] = str(txt_output_path)

        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(json.dumps(record, indent=2), encoding='utf-8')
        txt_output_path.parent.mkdir(parents=True, exist_ok=True)
        txt_output_path.write_text(_render_failure_summary(record), encoding='utf-8')
        return record
    finally:
        try:
            pipeline.shutdown()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description='Run one LLM-only kitchen or grill benchmark trial')
    parser.add_argument('--variant', required=True, help='Variant id (K1/K2/K3/G1/G2/G3)')
    parser.add_argument('--model', required=True, help='Registered LLM alias or custom HF path')
    parser.add_argument('--icl-mode', required=True, choices=['zero_shot', 'few_shot_shared_1'], help='Prompt mode to evaluate')
    parser.add_argument('--trial-index', type=int, default=1, help='1-based trial index')
    parser.add_argument('--max-replans', type=int, default=3, help='Maximum replans during execution')
    parser.add_argument('--goal', default='', help='Optional goal override')
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument('--gui', action='store_true', help='Run with simulator GUI (default)')
    display_group.add_argument('--headless', action='store_true', help='Run without simulator GUI')
    parser.add_argument('--no-live-masks', action='store_true', help='Disable the separate live segmentation window')
    parser.add_argument('--scene-state-trace', action='store_true', help='Print scene-state snapshots around execution checks')
    parser.add_argument('--remote', action='store_true', help='Use the maintained remote LLM planner server')
    parser.add_argument('--remote-url', default=os.environ.get('LLM_SERVER_URL', os.environ.get('VLM_SERVER_URL', 'http://localhost:8000')), help='Remote planner server URL')
    parser.add_argument('--replan-mode', choices=['on', 'off'], default='on', help='Use full execution+replanning (on) or first-plan-only mode with no failure checks (off)')
    parser.add_argument('--preflight-only', action='store_true', help='Only run text-only load/prompt validation')
    parser.add_argument('--output', default='', help='Optional JSON output path. Also writes a sibling .txt summary.')
    parser.add_argument('--output-dir', default='', help='Optional run directory. Writes record.json and failure_summary.txt inside it.')
    parser.add_argument('--output-root', default=str(DEFAULT_RUN_OUTPUT_ROOT), help='Root for auto-created run folders when --output/--output-dir are omitted.')
    args = parser.parse_args()

    record = run_trial(
        variant_id=args.variant,
        model_alias=args.model,
        icl_mode=args.icl_mode,
        trial_index=args.trial_index,
        max_replans=args.max_replans,
        headless=args.headless,
        remote=args.remote,
        remote_url=args.remote_url,
        replan_mode=args.replan_mode,
        preflight_only=args.preflight_only,
        output_path=Path(args.output) if args.output else None,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        output_root=Path(args.output_root),
        goal_override=args.goal or None,
        live_masks=not args.no_live_masks,
        scene_state_trace=args.scene_state_trace,
    )
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
