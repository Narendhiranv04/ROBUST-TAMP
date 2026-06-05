"""Aggregate benchmark trial records without touching the simulator."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

from evaluation.metrics import aggregate_model_records
from llm_pipeline.metrics import validate_variant_success


def load_records(output_dir: Path) -> List[Dict[str, Any]]:
    records = []
    for record_file in sorted(output_dir.glob("trial_*/record.json")):
        try:
            records.append(json.loads(record_file.read_text(encoding="utf-8")))
        except Exception as exc:
            print(f"Error reading {record_file}: {exc}")
    return records


def latest_failure_event(record: Dict[str, Any]) -> Dict[str, Any]:
    raw_summary = record.get("raw_summary") or {}
    event = raw_summary.get("last_failure_event") or {}
    if event:
        return dict(event)
    for cycle in reversed(raw_summary.get("cycles") or []):
        event = (cycle or {}).get("failure_event") or {}
        if event:
            return dict(event)
    return {}


def aggregate_bucket_breakdown(records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    buckets: Dict[str, Counter] = defaultdict(Counter)
    for record in records:
        for bucket_name, values in (record.get("bucket_breakdown") or {}).items():
            buckets[bucket_name].update(
                {
                    "expected": int(values.get("expected", 0)),
                    "observed": int(values.get("observed", 0)),
                    "matched": int(values.get("matched", 0)),
                }
            )
    return {name: dict(counter) for name, counter in sorted(buckets.items())}


def object_region_success(record: Dict[str, Any]) -> bool:
    validation = record.get("success_validation") or {}
    if "success" in validation:
        return bool(validation.get("success"))

    variant_id = str(record.get("variant_id") or "")
    if variant_id:
        validation = validate_variant_success(
            variant_id,
            record.get("final_object_region_map") or {},
            record.get("completed_actions") or [],
        )
        return bool(validation.get("success"))

    return bool(record.get("episode_success", False))


def aggregate_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {}

    canonical = aggregate_model_records(records)

    success_count = sum(1 for record in records if object_region_success(record))
    raw_success_count = sum(1 for record in records if bool(record.get("raw_episode_success", False)))
    coverage = [float(record.get("subtask_completion_rate") or 0.0) for record in records]
    partial_goal_completion = [
        float(record.get("partial_goal_completion") or 0.0)
        for record in records
        if record.get("partial_goal_completion") is not None
    ]
    times = [float(record.get("episode_time_s") or 0.0) for record in records]
    replans = [int(record.get("total_replans") or 0) for record in records]

    failure_ids = Counter()
    failure_layers = Counter()
    failure_sources = Counter()
    for record in records:
        event = latest_failure_event(record)
        if event:
            failure_ids[event.get("failure_id") or "unknown"] += 1
            failure_layers[event.get("failure_layer") or "unknown"] += 1
            failure_sources[event.get("source") or "unknown"] += 1
        elif not object_region_success(record):
            reason = record.get("failure_reason") or "no_failure_event"
            failure_ids[str(reason)] += 1

    return {
        "valid_trials": len(records),
        "episode_successes": success_count,
        "raw_episode_successes": raw_success_count,
        "success_metric": "object_region_validation",
        "mean_task_success": success_count / len(records),
        "mean_raw_task_success": raw_success_count / len(records),
        "mean_subtask_coverage": mean(coverage),
        "mean_partial_goal_completion": mean(partial_goal_completion) if partial_goal_completion else None,
        "std_partial_goal_completion": canonical.get("overall", {}).get("std_partial_goal_completion"),
        "avg_time_s": mean(times),
        "avg_replans": mean(replans),
        "mean_planner_invocations": canonical.get("overall", {}).get("mean_planner_invocations"),
        "mean_total_planner_time_s": canonical.get("overall", {}).get("mean_total_planner_time_s"),
        "mean_planner_time_per_invocation_s": canonical.get("overall", {}).get("mean_planner_time_per_invocation_s"),
        "discovery_triggered_replans": canonical.get("overall", {}).get("discovery_triggered_replans"),
        "failure_triggered_replans": canonical.get("overall", {}).get("failure_triggered_replans"),
        "other_triggered_replans": canonical.get("overall", {}).get("other_triggered_replans"),
        "implicit_non_target_handling_rate": canonical.get("overall", {}).get("implicit_non_target_handling_rate"),
        "real_failure_counts": canonical.get("failure_counts", {}),
        "failure_ids": dict(failure_ids),
        "failure_layers": dict(failure_layers),
        "failure_sources": dict(failure_sources),
        "bucket_breakdown_totals": aggregate_bucket_breakdown(records),
    }


__all__ = [
    "aggregate_bucket_breakdown",
    "aggregate_records",
    "latest_failure_event",
    "load_records",
    "object_region_success",
]
