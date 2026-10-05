#!/usr/bin/env python3
"""Run repeated planner trials and aggregate benchmark metrics."""

# The details of metrics can be read from metric_information.md.
# VLM command: `python3 run_10_trials_and_aggregate.py --pipeline vlm --model <model>` sends a stitched left/right/overhead/wrist/front composite encoded as base64 to the maintained planner server.

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Dict, Iterable, List

from evaluation.metrics import aggregate_model_records
from llm_pipeline.metrics import validate_variant_success


def _record_path(output_dir: Path, trial_index: int) -> Path:
    return output_dir / f"trial_{trial_index:03d}" / "record.json"


def _trial_command(args: argparse.Namespace, trial_index: int, trial_dir: Path) -> List[str]:
    command = [
        sys.executable,
        "-m",
        "llm_pipeline.trial_runner",
        "--variant",
        args.variant,
        "--model",
        args.model,
        "--icl-mode",
        args.icl_mode,
        "--planner-max-new-tokens",
        str(args.planner_max_new_tokens),
        "--goal-check-max-new-tokens",
        str(args.goal_check_max_new_tokens),
        "--trial-index",
        str(trial_index),
        "--output-dir",
        str(trial_dir),
    ]
    if args.quantization:
        command.extend(["--quantization", args.quantization])
    if args.pipeline == "vlm":
        command.append("--vision")
    if args.model_type:
        command.extend(["--model-type", args.model_type])
    if args.show_llm_output:
        command.append("--show-llm-output")

    if args.remote:
        command.extend(["--remote", "--remote-url", args.remote_url])
    if args.goal_check:
        command.append("--goal-check")
    else:
        command.append("--no-goal-check")
    for flag in getattr(args, "flag", None) or []:
        command.extend(["--flag", flag])
    seed_base = getattr(args, "seed_base", None)
    if seed_base is not None:
        command.extend(["--seed", str(int(seed_base) + int(trial_index))])
    command.append("--headless" if args.headless else "--gui")
    return command


def _load_records(output_dir: Path) -> List[Dict[str, Any]]:
    records = []
    for record_file in sorted(output_dir.glob("trial_*/record.json")):
        try:
            records.append(json.loads(record_file.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"Error reading {record_file}: {exc}")
    return records


def _latest_failure_event(record: Dict[str, Any]) -> Dict[str, Any]:
    raw_summary = record.get("raw_summary") or {}
    event = raw_summary.get("last_failure_event") or {}
    if event:
        return dict(event)
    for cycle in reversed(raw_summary.get("cycles") or []):
        event = (cycle or {}).get("failure_event") or {}
        if event:
            return dict(event)
    return {}


def _aggregate_bucket_breakdown(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    buckets: Dict[str, Counter] = defaultdict(Counter)
    for record in records:
        for bucket_name, values in (record.get("bucket_breakdown") or {}).items():
            buckets[bucket_name].update({
                "expected": int(values.get("expected", 0)),
                "observed": int(values.get("observed", 0)),
                "matched": int(values.get("matched", 0)),
            })
    return {name: dict(counter) for name, counter in sorted(buckets.items())}


def _fresh_success_validation(record: Dict[str, Any]) -> Dict[str, Any]:
    variant_id = str(record.get("variant_id") or "")
    if variant_id and ("final_object_region_map" in record or "completed_actions" in record):
        return validate_variant_success(
            variant_id,
            record.get("final_object_region_map") or {},
            record.get("completed_actions") or [],
        )
    return dict(record.get("success_validation") or {})


def _object_region_success(record: Dict[str, Any]) -> bool:
    validation = _fresh_success_validation(record)
    if "success" in validation:
        return bool(validation.get("success"))

    return bool(record.get("episode_success", False))


def _trial_failure_reason(record: Dict[str, Any]) -> str:
    validation = _fresh_success_validation(record)
    missing = validation.get("missing") or []
    if missing:
        return "object_region_goal_not_satisfied"
    return str(record.get("failure_reason") or "no_failure_event")


def _safe_std(values: List[float]) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return 0.0
    return float(stdev(values))


def aggregate_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {}

    canonical = aggregate_model_records(records)
    overall = canonical.get("overall", {}) or {}
    success_count = sum(1 for record in records if _object_region_success(record))
    raw_success_count = sum(1 for record in records if bool(record.get("raw_episode_success", False)))
    coverage = [float(record.get("subtask_completion_rate") or 0.0) for record in records]
    validations = [_fresh_success_validation(record) for record in records]
    partial_goal_completion = [
        float(validation.get("partial_goal_completion") or 0.0)
        for validation in validations
        if validation.get("partial_goal_completion") is not None
    ]
    times = [float(record.get("episode_time_s") or 0.0) for record in records]
    replans = [int(record.get("total_replans") or 0) for record in records]

    failure_ids = Counter()
    failure_layers = Counter()
    failure_sources = Counter()
    failed_trial_reasons = Counter()
    for record in records:
        event = _latest_failure_event(record)
        if event:
            failure_ids[event.get("failure_id") or "unknown"] += 1
            failure_layers[event.get("failure_layer") or "unknown"] += 1
            failure_sources[event.get("source") or "unknown"] += 1
        elif not _object_region_success(record):
            reason = record.get("failure_reason") or "no_failure_event"
            failure_ids[str(reason)] += 1
        if not _object_region_success(record):
            failed_trial_reasons[_trial_failure_reason(record)] += 1

    real_failure_counts = canonical.get("failure_counts", {}) or {}
    return {
        "valid_trials": len(records),
        "episode_successes": success_count,
        "raw_episode_successes": raw_success_count,
        "success_metric": "object_region_validation",
        "display_metric_notes": {
            "mean_task_success": "Object-region validation of final scene state.",
            "mean_raw_task_success": "Pipeline raw execution/planning success before final object-region validation.",
            "real_failure_counts": "Structured failure events only; discovery-triggered replans are excluded.",
            "failed_trial_reasons": "Reasons for trials that failed the object-region success metric.",
        },
        "mean_task_success": success_count / len(records),
        "mean_raw_task_success": raw_success_count / len(records),
        "mean_subtask_coverage": mean(coverage),
        "mean_partial_goal_completion": mean(partial_goal_completion) if partial_goal_completion else None,
        "std_partial_goal_completion": _safe_std(partial_goal_completion),
        "avg_time_s": mean(times),
        "avg_replans": mean(replans),
        "mean_planner_invocations": overall.get("mean_planner_invocations"),
        "mean_total_planner_time_s": overall.get("mean_total_planner_time_s"),
        "mean_planner_time_per_invocation_s": overall.get("mean_planner_time_per_invocation_s"),
        "discovery_triggered_replans": overall.get("discovery_triggered_replans"),
        "failure_triggered_replans": overall.get("failure_triggered_replans"),
        "other_triggered_replans": overall.get("other_triggered_replans"),
        "implicit_non_target_handling_rate": overall.get("implicit_non_target_handling_rate"),
        "real_failure_counts": real_failure_counts,
        "failure_ids": dict(failure_ids),
        "failure_layers": dict(failure_layers),
        "failure_sources": dict(failure_sources),
        "failed_trial_reasons": dict(failed_trial_reasons),
        "bucket_breakdown_totals": _aggregate_bucket_breakdown(records),
    }


def _print_summary(args: argparse.Namespace, summary: Dict[str, Any]) -> None:
    if not summary:
        print("No valid record.json files found. Did the trials fail to run?")
        return

    valid = summary["valid_trials"]
    print("\n===========================================")
    print(f"RESULTS FOR {args.pipeline.upper()} {args.model} - {args.variant} ({valid} trials)")
    print("===========================================")
    print(f"Object-Region Success:     {summary['mean_task_success'] * 100:.1f}% ({summary['episode_successes']}/{valid})")
    print(f"Object-Region Metric:      {summary.get('success_metric', 'episode_success')}")
    print(f"Raw Pipeline Success:      {summary['mean_raw_task_success'] * 100:.1f}% ({summary['raw_episode_successes']}/{valid})")
    print(f"Subtask Coverage:          {summary['mean_subtask_coverage'] * 100:.1f}%")
    if summary.get("mean_partial_goal_completion") is not None:
        print(f"Partial Goal Completion:   {summary['mean_partial_goal_completion'] * 100:.1f}%")
    print(f"Avg. Time (s):             {summary['avg_time_s']:.2f}")
    print(f"Avg. Planner Calls:        {summary.get('mean_planner_invocations')}")
    print(f"Avg. Planner Time (s):     {summary.get('mean_total_planner_time_s')}")
    print(f"Avg. Planner Call (s):     {summary.get('mean_planner_time_per_invocation_s')}")
    print(f"Avg. Replans:              {summary['avg_replans']:.2f}")
    print(
        "Replan Triggers:           "
        f"discovery={summary.get('discovery_triggered_replans')}, "
        f"failure={summary.get('failure_triggered_replans')}, "
        f"other={summary.get('other_triggered_replans')}"
    )
    print(f"Implicit Non-Target Rate:  {summary.get('implicit_non_target_handling_rate')}")
    print(f"Failed Trial Reasons:      {summary.get('failed_trial_reasons', {})}")
    print(f"Real Failure Counts:       {summary.get('real_failure_counts', {})}")
    print(f"Latest Diagnostic IDs:     {summary['failure_ids']}")
    print(f"Latest Event Layers:       {summary['failure_layers']}")
    print(f"Latest Event Sources:      {summary['failure_sources']}")
    print(f"Bucket Totals:             {summary['bucket_breakdown_totals']}")
    print("===========================================")
    print("\nLaTeX Table String:")
    print(
        f"& {summary['mean_task_success'] * 100:.1f} "
        f"& {summary['mean_subtask_coverage'] * 100:.1f} "
        f"& {summary['avg_time_s']:.1f} "
        f"& {summary['avg_replans']:.1f} \\\\"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run repeated LLM/VLM trials and aggregate records.")
    parser.add_argument("--pipeline", choices=["llm", "vlm"], default="llm")
    parser.add_argument("--model", default="devstral-24b")
    parser.add_argument("--model-type", choices=["", "llm", "vlm"], default="")
    parser.add_argument("--quantization", choices=["", "none", "bnb8", "bnb4"], default="", help="Expected/local quantization mode to record/pass to trial_runner.")
    parser.add_argument("--flag", action="append", default=[], metavar="NAME=VALUE", help="plan.md Section 0.7 flag passed to every trial (repeatable)")
    parser.add_argument("--seed-base", type=int, default=None, help="Trial seed = seed-base + trial index (default: trial_runner uses the trial index)")
    parser.add_argument("--variant", default="K1")
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--icl-mode", choices=["zero_shot", "few_shot_shared_1"], default="zero_shot")
    parser.add_argument("--remote-url", default="http://127.0.0.1:8000")
    parser.add_argument("--planner-max-new-tokens", type=int, default=4096)
    parser.add_argument("--goal-check-max-new-tokens", type=int, default=128)
    parser.add_argument("--output-root", default="eval_results_10_trials")
    parser.add_argument("--local", dest="remote", action="store_false", help="Use local model loading instead of a remote server.")
    parser.add_argument("--remote", dest="remote", action="store_true", help="Use a remote planner server.")
    parser.set_defaults(remote=True)
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--headless", action="store_true", default=True)
    display.add_argument("--gui", action="store_false", dest="headless")
    parser.add_argument("--aggregate-only", action="store_true", help="Skip running trials and aggregate existing records.")
    parser.add_argument("--show-llm-output", action="store_true", help="Print raw LLM/VLM planner output for debugging")
    goal_check = parser.add_mutually_exclusive_group()
    goal_check.add_argument("--goal-check", dest="goal_check", action="store_true", help="Enable goal-completion verification during execution.")
    goal_check.add_argument("--no-goal-check", dest="goal_check", action="store_false", help="Disable goal-completion verification during execution.")
    parser.set_defaults(goal_check=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_root) / args.model / args.variant
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.aggregate_only:
        print(f"Starting {args.trials} {args.pipeline} trials for {args.variant} using {args.model}...")
        for i in range(1, args.trials + 1):
            trial_dir = output_dir / f"trial_{i:03d}"
            trial_dir.mkdir(parents=True, exist_ok=True)
            command = _trial_command(args, i, trial_dir)
            print(f"\n--- Running Trial {i}/{args.trials} ---")
            print(" ".join(command))
            subprocess.run(command, check=False)
            print(f"Finished Trial {i}. Results saved to {trial_dir}")

    print("\nAggregating Metrics...")
    records = _load_records(output_dir)
    summary = aggregate_records(records)
    if summary:
        (output_dir / "aggregate_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _print_summary(args, summary)


if __name__ == "__main__":
    main()
