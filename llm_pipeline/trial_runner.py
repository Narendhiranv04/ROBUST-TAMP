"""Run one maintained LLM/VLM kitchen or grill trial and emit a structured JSON record."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from evaluation.canonical_variants import get_variant_spec
from llm_pipeline.metrics import (
    build_trial_metric_events,
    collect_failure_occurrences,
    implicit_non_target_handling_success,
    score_variant_completion,
    validate_variant_success,
)
from llm_pipeline.failures import TerminationReason
from llm_pipeline.flags import PipelineFlags
from llm_pipeline.pipeline import LLMPipelineConfig, LLMOnlyReplanningPipeline
from llm_pipeline.trial_log import TrialLogger


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
        os.environ['GRILL_OPEN_REPLAY_VARIANT'] = 'G2'
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


def _vision_contract_issues(preflight_record: Dict[str, Any]) -> list[str]:
    issues = list(preflight_record.get('prompt_contract_issues', []))
    prompt_trace = preflight_record.get('prompt_trace', {}) or {}
    bundle = prompt_trace.get('bundle', {}) or {}
    image_metadata = bundle.get('image_metadata') or preflight_record.get('image_metadata') or {}
    if not image_metadata.get('image_present'):
        issues.append('missing_image_in_prompt_bundle')
    if 'images' in bundle:
        issues.append('raw_images_in_prompt_trace')
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


def git_commit_info(root: Path = ROOT_DIR) -> Dict[str, Any]:
    import subprocess

    def _git(*args: str) -> str:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=10).stdout.strip()

    try:
        return {'commit': _git('rev-parse', 'HEAD') or None, 'dirty': bool(_git('status', '--porcelain', '-uno'))}
    except Exception:
        return {'commit': None, 'dirty': None}


def seed_everything(seed: int) -> None:
    import random

    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed % (2 ** 32))
    except Exception:
        pass


def trial_log_path_for(json_output_path: Path) -> Path:
    if json_output_path.name == 'record.json':
        return json_output_path.parent / 'trial_log.jsonl'
    return json_output_path.with_suffix('.trial_log.jsonl')


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
        f"quantization: {record.get('quantization', '')}",
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


def _validate_trial(variant_spec, summary: Dict[str, Any]) -> Dict[str, Any]:
    """Final variants: labeled rules on simulator ground truth; today's variants: llm_pipeline.metrics."""
    from evaluation.final_variants import get_final_variant
    from evaluation.labeled_rules import uses_labeled_rules, validate_labeled_goal

    completed = summary.get('completed_actions', [])
    if not uses_labeled_rules(variant_spec.variant_id):
        return validate_variant_success(variant_spec.variant_id, summary.get('final_object_region_map', {}), completed)
    spec = get_final_variant(variant_spec.variant_id)
    initial = summary.get('initial_ground_truth') or {}
    final = summary.get('final_ground_truth') or {}
    result = validate_labeled_goal(
        spec.scene,
        spec.variant_id,
        final.get('object_region_map', {}),
        completed,
        initial.get('object_region_map', {}),
        placement_area_objects=final.get('placement_area_objects', {}),
        box_trigger_objects=[h.label for h in spec.hidden if h.region == 'inside_box' and h.overlapping],
    )
    result['details']['initial_ground_truth'] = initial
    result['details']['final_ground_truth'] = final
    return result


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
    show_llm_output: bool = False,
    goal_check: bool = False,
    vision: bool = False,
    model_type: str = '',
    quantization: str = '',
    planner_max_new_tokens: int = 4096,
    goal_check_max_new_tokens: int = 128,
    flags: Optional[PipelineFlags] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    variant_spec = get_variant_spec(variant_id)
    flags = flags or PipelineFlags()
    seed = int(trial_index if seed is None else seed)
    seed_everything(seed)
    if not variant_spec.model_eval_supported:
        raise RuntimeError(
            f'Variant {variant_spec.variant_id} is not supported for the maintained planner runner: '
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
        text_only=not vision,
        enable_vision=bool(vision),
        model_type=model_type or ('vlm' if vision else 'llm'),
        quantization=quantization,
        planner_max_new_tokens=int(planner_max_new_tokens),
        goal_check_max_new_tokens=int(goal_check_max_new_tokens),
        prompt_mode='segmentation_text_image' if vision else 'segmentation_text_only',
        segmentation_first=True,
        pre_action_checks_enabled=replanning_enabled,
        post_action_checks_enabled=replanning_enabled,
        task_family=variant_spec.task_family,
        scene_path=variant_spec.scene_path,
        variant_id=variant_spec.variant_id,
        live_segmentation_view=bool(live_masks and not headless),
        scene_state_trace=bool(scene_state_trace),
        show_llm_output=bool(show_llm_output),
        enable_goal_check=bool(goal_check),
        flags=flags,
        seed=seed,
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
    trial_id = (
        f'{variant_spec.variant_id}_{_safe_path_token(model_alias)}_{_safe_path_token(icl_mode)}'
        f'_{flags.prompt_version}_trial{int(trial_index):03d}'
    )
    condition = {
        'planner_model': model_alias,
        'model_type': model_type or ('vlm' if vision else 'llm'),
        'quantization': quantization or 'none',
        'vision': bool(vision),
        'icl_mode': icl_mode,
        'prompt_version': flags.prompt_version,
        'goal_check': bool(goal_check),
        'replan_mode': replan_mode,
        'max_replans': int(max_replans),
        'planner_max_new_tokens': int(planner_max_new_tokens),
        'flags': flags.to_dict(),
    }
    trial_logger = TrialLogger(trial_log_path_for(json_output_path), trial_id=trial_id)
    if hasattr(pipeline, 'set_trial_logger'):
        pipeline.set_trial_logger(trial_logger)
    trial_started = time.monotonic()
    trial_start_logged = False
    trial_end_logged = False

    def _log_trial_start() -> None:
        nonlocal trial_start_logged, trial_started
        if trial_start_logged:
            return
        trial_start_logged = True
        trial_logger.emit(
            'trial_start',
            scene=variant_spec.task_family,
            variant=variant_spec.variant_id,
            condition=condition,
            seed=seed,
            flags=flags.to_dict(),
            git_commit=git_commit_info(),
            trial_index=int(trial_index),
            goal=goal_text,
            backend=os.environ.get('SIM_BACKEND', 'coppelia'),
            remote_planner_url=remote_url or None,
            randomization=getattr(pipeline, 'randomization_record', None),
        )
        trial_started = time.monotonic()

    def _log_trial_end(success, validation, planner_calls, planner_time_s, termination_reason) -> None:
        nonlocal trial_end_logged
        if trial_end_logged:
            return
        _log_trial_start()
        trial_end_logged = True
        validation = validation or {}
        trial_logger.emit(
            'trial_end',
            success=success,
            goal_relations_satisfied=validation.get('satisfied_relation_count'),
            goal_relations_total=validation.get('required_relation_count'),
            procedure_checks_satisfied=validation.get('satisfied_procedure_count'),
            procedure_checks_total=validation.get('required_procedure_count'),
            partial_goal_completion=validation.get('partial_goal_completion'),
            planner_calls=planner_calls,
            planner_time_s=planner_time_s,
            trial_time_s=round(time.monotonic() - trial_started, 3),
            termination_reason=termination_reason,
            missing=list(validation.get('missing') or []),
        )

    try:
        if not pipeline.initialize(env=env):
            planner = getattr(pipeline, 'planner', None)
            debug_info = planner.get_debug_info() if hasattr(planner, 'get_debug_info') else {}
            print(f"[TrialRunner] Pipeline initialization failed. Planner debug: {debug_info}")
            _log_trial_end(None, None, 0, 0.0, TerminationReason.INFRASTRUCTURE)
            raise RuntimeError('pipeline_initialize_failed')
        _log_trial_start()

        effective_model_type = model_type or ('vlm' if vision else 'llm')
        text_only = not bool(vision)

        if preflight_only:
            preflight = pipeline.preflight(goal_text)
            preflight_issues = _vision_contract_issues(preflight) if vision else _text_only_contract_issues(preflight)
            preflight['prompt_contract_issues'] = preflight_issues
            preflight['prompt_contract_ok'] = not preflight_issues
            preflight['preflight_success'] = (
                bool(preflight.get('loaded'))
                and bool(preflight.get('dry_run_plan_success'))
                and not preflight_issues
                and bool(preflight.get('image_present')) is bool(vision)
            )
            effective_model_type = preflight.get('model_type') or effective_model_type
            record = {
                'variant_id': variant_spec.variant_id,
                'task_family': variant_spec.task_family,
                'scene_path': variant_spec.scene_path,
                'trial_index': int(trial_index),
                'preflight_only': True,
                'model_alias': model_alias,
                'model_type': effective_model_type,
                'quantization': preflight.get('quantization', quantization or 'none'),
                'icl_mode': icl_mode,
                'goal_text': goal_text,
                'text_only': text_only,
                'use_vision': bool(vision),
                'image_present': bool(preflight.get('image_present', False)),
                'image_metadata': dict(preflight.get('image_metadata', {}) or {}),
                'segmentation_first': True,
                'replan_mode': replan_mode,
                'use_remote_planner': bool(remote),
                'remote_planner_url': remote_url or None,
                'pre_action_checks_enabled': replanning_enabled,
                'post_action_checks_enabled': replanning_enabled,
                'live_segmentation_view': bool(live_masks and not headless),
                'scene_state_trace': bool(scene_state_trace),
                'goal_check_enabled': bool(goal_check),
                'preflight_success': bool(preflight['preflight_success']),
                'preflight': preflight,
            }
        else:
            summary = pipeline.run(goal_text)
            completion = score_variant_completion(variant_spec.variant_id, summary.get('completed_actions', []))
            success_validation = _validate_trial(variant_spec, summary)
            execution_skipped = bool(summary.get('execution_skipped', False))
            episode_success = None if execution_skipped else bool(success_validation.get('success', False))
            total_replans = int(summary.get('total_replans', 0))
            event_metrics = build_trial_metric_events(
                summary.get('cycles', []),
                success_validation=None if execution_skipped else success_validation,
                total_replans=total_replans,
            )
            implicit_non_target_success = implicit_non_target_handling_success(
                variant_spec.variant_id,
                event_metrics['structured_events'],
                summary.get('completed_actions', []),
                summary.get('final_object_region_map', {}),
                goal_text,
            )
            raw_failure_occurrences = collect_failure_occurrences(
                summary.get('cycles', []),
                summary.get('failure_reason'),
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
                'success_validation': success_validation,
                'partial_goal_completion': success_validation.get('partial_goal_completion'),
                'required_relation_count': success_validation.get('required_relation_count'),
                'satisfied_relation_count': success_validation.get('satisfied_relation_count'),
                'missing_relation_count': success_validation.get('missing_relation_count'),
                'required_procedure_count': success_validation.get('required_procedure_count'),
                'satisfied_procedure_count': success_validation.get('satisfied_procedure_count'),
                'missing_procedure_count': success_validation.get('missing_procedure_count'),
                'required_condition_count': success_validation.get('required_condition_count'),
                'satisfied_condition_count': success_validation.get('satisfied_condition_count'),
                'missing_condition_count': success_validation.get('missing_condition_count'),
                'model_alias': summary.get('model_alias', model_alias),
                'model_type': summary.get('model_type', effective_model_type),
                'quantization': summary.get('quantization', quantization or 'none'),
                'icl_mode': icl_mode,
                'prompt_mode': summary.get('prompt_mode', icl_mode),
                'goal_text': goal_text,
                'text_only': bool(summary.get('text_only', text_only)),
                'use_vision': bool(summary.get('use_vision', vision)),
                'image_present': bool(summary.get('image_present', False)),
                'image_metadata': dict(summary.get('image_metadata', {}) or {}),
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
                'goal_check_enabled': bool(summary.get('goal_check_enabled', goal_check)),
                'last_goal_check': summary.get('last_goal_check'),
                'episode_success': episode_success,
                'raw_episode_success': None if execution_skipped else bool(summary.get('success')),
                'total_cycles': int(summary.get('total_cycles', 0)),
                'total_replans': total_replans,
                'discovery_triggered_replans': event_metrics['discovery_triggered_replans'],
                'failure_triggered_replans': event_metrics['failure_triggered_replans'],
                'other_triggered_replans': event_metrics['other_triggered_replans'],
                'planner_invocations': int(summary.get('planner_invocations', 0)),
                'total_planner_time_s': summary.get('total_planner_time_s'),
                'mean_planner_time_per_invocation_s': summary.get('mean_planner_time_per_invocation_s'),
                'planned_actions': list(summary.get('planned_actions', [])),
                'completed_actions': list(summary.get('completed_actions', [])),
                'remaining_actions': list(summary.get('remaining_actions', [])),
                'final_object_region_map': dict(summary.get('final_object_region_map', {}) or {}),
                'final_lid_states': dict(summary.get('final_lid_states', {}) or {}),
                'failure_reason': summary.get('failure_reason'),
                'structured_events': event_metrics['structured_events'],
                'failure_event_counts': event_metrics['failure_event_counts'],
                'raw_failure_occurrences': raw_failure_occurrences,
                'failure_occurrences': raw_failure_occurrences,
                'implicit_non_target_handling_success': implicit_non_target_success,
                'episode_time_s': summary.get('episode_time_s'),
                'preflight': None,
                'raw_summary': summary,
            }

        if preflight_only:
            _log_trial_end(None, None, 1, None, TerminationReason.PREFLIGHT_ONLY)
        else:
            _log_trial_end(
                episode_success,
                None if execution_skipped else success_validation,
                int(summary.get('planner_invocations', 0)),
                summary.get('total_planner_time_s'),
                getattr(pipeline, 'termination_reason', None) or TerminationReason.PLAN_COMPLETED,
            )

        record['output_json_path'] = str(json_output_path)
        record['failure_summary_path'] = str(txt_output_path)

        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(json.dumps(record, indent=2), encoding='utf-8')
        txt_output_path.parent.mkdir(parents=True, exist_ok=True)
        txt_output_path.write_text(_render_failure_summary(record), encoding='utf-8')
        return record
    except Exception as exc:
        _log_trial_end(None, None, None, None, TerminationReason.INFRASTRUCTURE)
        raise
    finally:
        if not trial_end_logged:
            _log_trial_end(None, None, None, None, TerminationReason.INFRASTRUCTURE)
        try:
            pipeline.shutdown()
        except Exception:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description='Run one maintained LLM/VLM kitchen or grill benchmark trial')
    parser.add_argument('--variant', required=True, help='Variant id (K1/K2/K3/G1/G2/G3)')
    parser.add_argument('--model', required=True, help='Registered planner alias or custom HF path')
    parser.add_argument('--model-type', choices=['', 'llm', 'vlm'], default='', help='Optional explicit model type')
    parser.add_argument('--quantization', choices=['', 'none', 'bnb8', 'bnb4'], default='', help='Expected/local quantization mode. Remote runs read the real mode from server health when available.')
    parser.add_argument('--vision', action='store_true', help='Use the maintained multimodal VLM backend')
    parser.add_argument('--icl-mode', default='zero_shot', choices=['zero_shot', 'few_shot_shared_1'], help='Prompt mode (ICL is off by default; few_shot_shared_1 needs --flag prompt.version=legacy)')
    parser.add_argument('--trial-index', type=int, default=1, help='1-based trial index')
    parser.add_argument('--max-replans', type=int, default=3, help='Maximum replans during execution')
    parser.add_argument('--planner-max-new-tokens', type=int, default=4096, help='Maximum generation tokens for each planner call')
    parser.add_argument('--goal-check-max-new-tokens', type=int, default=128, help='Maximum generation tokens for each goal-check call')
    parser.add_argument('--goal', default='', help='Optional goal override')
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument('--gui', action='store_true', help='Run with simulator GUI (default)')
    display_group.add_argument('--headless', action='store_true', help='Run without simulator GUI')
    parser.add_argument('--no-live-masks', action='store_true', help='Disable the separate live segmentation window')
    parser.add_argument('--scene-state-trace', action='store_true', help='Print scene-state snapshots around execution checks')
    parser.add_argument('--show-llm-output', action='store_true', help='Print raw LLM/VLM planner output in the local terminal')
    goal_check_group = parser.add_mutually_exclusive_group()
    goal_check_group.add_argument('--goal-check', action='store_true', help='Enable LLM goal-completion verification during execution')
    goal_check_group.add_argument('--no-goal-check', action='store_true', help='Keep LLM goal-completion verification disabled during execution')
    parser.add_argument('--remote', action='store_true', help='Use the maintained remote planner server')
    parser.add_argument('--remote-url', default=os.environ.get('LLM_SERVER_URL', os.environ.get('VLM_SERVER_URL', 'http://localhost:8000')), help='Remote planner server URL')
    parser.add_argument('--replan-mode', choices=['on', 'off'], default='on', help='Use full execution+replanning (on) or first-plan-only mode with no failure checks (off)')
    parser.add_argument('--preflight-only', action='store_true', help='Only run load/prompt validation')
    parser.add_argument('--output', default='', help='Optional JSON output path. Also writes a sibling .txt summary.')
    parser.add_argument('--output-dir', default='', help='Optional run directory. Writes record.json and failure_summary.txt inside it.')
    parser.add_argument('--output-root', default=str(DEFAULT_RUN_OUTPUT_ROOT), help='Root for auto-created run folders when --output/--output-dir are omitted.')
    parser.add_argument('--flag', action='append', default=[], metavar='NAME=VALUE',
                        help='plan.md Section 0.7 flag, e.g. --flag termination.mode=evaluator (repeatable)')
    parser.add_argument('--seed', type=int, default=None, help='Trial seed (default: the trial index); logged in trial_log.jsonl')
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
        show_llm_output=bool(args.show_llm_output),
        goal_check=bool(args.goal_check and not args.no_goal_check),
        vision=bool(args.vision),
        model_type=args.model_type,
        quantization=args.quantization,
        planner_max_new_tokens=args.planner_max_new_tokens,
        goal_check_max_new_tokens=args.goal_check_max_new_tokens,
        flags=PipelineFlags.from_assignments(args.flag),
        seed=args.seed,
    )
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
