#!/usr/bin/env python3
"""Collect final experiment summaries into paper-friendly tables.

This script reads outputs produced by run_10_trials_and_aggregate.py. It does
not run the simulator or contact the planner server.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


CONDITION_NAMES = {
    "llm_zero_shot": ("llm", "zero_shot"),
    "llm_few_shot_shared_1": ("llm", "few_shot_shared_1"),
    "vlm_zero_shot": ("vlm", "zero_shot"),
    "vlm_few_shot_shared_1": ("vlm", "few_shot_shared_1"),
}

MAIN_FIELDS = [
    "pipeline",
    "icl_mode",
    "model_alias",
    "model_type",
    "variant",
    "valid_trials",
    "episode_successes",
    "mean_task_success",
    "mean_partial_goal_completion",
    "std_partial_goal_completion",
    "mean_planner_invocations",
    "mean_total_planner_time_s",
    "mean_planner_time_per_invocation_s",
    "avg_time_s",
    "avg_replans",
    "discovery_triggered_replans",
    "failure_triggered_replans",
    "other_triggered_replans",
    "implicit_non_target_handling_rate",
]

FAILURE_FIELDS = [
    "pipeline",
    "icl_mode",
    "model_alias",
    "model_type",
    "variant",
    "event_type",
    "failure_id",
    "failure_layer",
    "stage",
    "source",
    "should_replan",
    "occurrences",
    "trials_affected",
]

NON_TARGET_FIELDS = [
    "pipeline",
    "icl_mode",
    "model_alias",
    "model_type",
    "variant",
    "valid_trials",
    "applicable_trials",
    "successes",
    "implicit_non_target_handling_rate",
]


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Skipping unreadable JSON {path}: {exc}")
        return None


def _condition_from_path(path: Path, root: Path) -> tuple[str, str]:
    try:
        condition = path.relative_to(root).parts[0]
    except Exception:
        condition = path.parts[-4] if len(path.parts) >= 4 else ""
    return CONDITION_NAMES.get(condition, ("", ""))


def _record_files(variant_dir: Path) -> List[Path]:
    return sorted(variant_dir.glob("trial_*/record.json"))


def _iter_summary_files(root: Path) -> Iterable[Path]:
    yield from sorted(root.glob("*/*/*/aggregate_summary.json"))


def _model_and_variant(summary_file: Path) -> tuple[str, str]:
    variant = summary_file.parent.name
    model_alias = summary_file.parent.parent.name
    return model_alias, variant


def _get(summary: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in summary:
            return summary.get(key)
    return None


def _main_row(summary_file: Path, root: Path, summary: Dict[str, Any]) -> Dict[str, Any]:
    pipeline, icl_mode = _condition_from_path(summary_file, root)
    model_alias, variant = _model_and_variant(summary_file)
    return {
        "pipeline": pipeline,
        "icl_mode": icl_mode,
        "model_alias": model_alias,
        "model_type": pipeline or summary.get("model_type"),
        "variant": variant,
        "valid_trials": summary.get("valid_trials"),
        "episode_successes": summary.get("episode_successes"),
        "mean_task_success": summary.get("mean_task_success"),
        "mean_partial_goal_completion": summary.get("mean_partial_goal_completion"),
        "std_partial_goal_completion": summary.get("std_partial_goal_completion"),
        "mean_planner_invocations": summary.get("mean_planner_invocations"),
        "mean_total_planner_time_s": summary.get("mean_total_planner_time_s"),
        "mean_planner_time_per_invocation_s": summary.get("mean_planner_time_per_invocation_s"),
        "avg_time_s": summary.get("avg_time_s"),
        "avg_replans": summary.get("avg_replans"),
        "discovery_triggered_replans": summary.get("discovery_triggered_replans"),
        "failure_triggered_replans": summary.get("failure_triggered_replans"),
        "other_triggered_replans": summary.get("other_triggered_replans"),
        "implicit_non_target_handling_rate": summary.get("implicit_non_target_handling_rate"),
    }


def _trial_failure_rows(
    summary_file: Path,
    root: Path,
    record_files: List[Path],
) -> List[Dict[str, Any]]:
    pipeline, icl_mode = _condition_from_path(summary_file, root)
    model_alias, variant = _model_and_variant(summary_file)
    counts: Counter[tuple[Any, ...]] = Counter()
    trials_affected: Dict[tuple[Any, ...], set[str]] = defaultdict(set)

    for record_file in record_files:
        record = _load_json(record_file)
        if not record:
            continue
        trial_id = record_file.parent.name
        for event in record.get("structured_events") or []:
            if not event.get("is_failure"):
                continue
            key = (
                event.get("event_type") or "unknown",
                event.get("failure_id") or "unknown",
                event.get("failure_layer") or "unknown",
                event.get("stage") or "unknown",
                event.get("source") or "unknown",
                event.get("should_replan"),
            )
            counts[key] += 1
            trials_affected[key].add(trial_id)

    rows: List[Dict[str, Any]] = []
    for key, occurrences in sorted(counts.items()):
        event_type, failure_id, failure_layer, stage, source, should_replan = key
        rows.append(
            {
                "pipeline": pipeline,
                "icl_mode": icl_mode,
                "model_alias": model_alias,
                "model_type": pipeline,
                "variant": variant,
                "event_type": event_type,
                "failure_id": failure_id,
                "failure_layer": failure_layer,
                "stage": stage,
                "source": source,
                "should_replan": should_replan,
                "occurrences": occurrences,
                "trials_affected": len(trials_affected[key]),
            }
        )
    return rows


def _non_target_row(
    summary_file: Path,
    root: Path,
    summary: Dict[str, Any],
    record_files: List[Path],
) -> Optional[Dict[str, Any]]:
    model_alias, variant = _model_and_variant(summary_file)
    if variant not in {"G1", "G3"}:
        return None

    pipeline, icl_mode = _condition_from_path(summary_file, root)
    applicable = 0
    successes = 0
    for record_file in record_files:
        record = _load_json(record_file)
        if not record:
            continue
        value = record.get("implicit_non_target_handling_success")
        if value is None:
            continue
        applicable += 1
        if value:
            successes += 1

    return {
        "pipeline": pipeline,
        "icl_mode": icl_mode,
        "model_alias": model_alias,
        "model_type": pipeline,
        "variant": variant,
        "valid_trials": summary.get("valid_trials"),
        "applicable_trials": applicable,
        "successes": successes,
        "implicit_non_target_handling_rate": summary.get("implicit_non_target_handling_rate"),
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _write_markdown(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join(["---"] * len(fields)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_format_value(row.get(field)) for field in fields) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def collect(root: Path) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    main_rows: List[Dict[str, Any]] = []
    failure_rows: List[Dict[str, Any]] = []
    non_target_rows: List[Dict[str, Any]] = []

    for summary_file in _iter_summary_files(root):
        summary = _load_json(summary_file)
        if not summary:
            continue
        record_files = _record_files(summary_file.parent)
        main_rows.append(_main_row(summary_file, root, summary))
        failure_rows.extend(_trial_failure_rows(summary_file, root, record_files))
        non_target = _non_target_row(summary_file, root, summary, record_files)
        if non_target:
            non_target_rows.append(non_target)

    return main_rows, failure_rows, non_target_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect final Robust TAMP experiment tables.")
    parser.add_argument(
        "--root",
        default="llm_pipeline/results/final_experiments",
        help="Root containing condition/model/variant experiment folders.",
    )
    parser.add_argument(
        "--output-dir",
        default="llm_pipeline/results/final_experiments/collected",
        help="Directory for collected CSV and Markdown tables.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.root)
    output_dir = Path(args.output_dir)

    main_rows, failure_rows, non_target_rows = collect(root)

    _write_csv(output_dir / "final_results_summary.csv", main_rows, MAIN_FIELDS)
    _write_markdown(output_dir / "final_results_summary.md", main_rows, MAIN_FIELDS)
    _write_csv(output_dir / "layered_failure_summary.csv", failure_rows, FAILURE_FIELDS)
    _write_markdown(output_dir / "layered_failure_summary.md", failure_rows, FAILURE_FIELDS)
    _write_csv(output_dir / "implicit_non_target_summary.csv", non_target_rows, NON_TARGET_FIELDS)
    _write_markdown(output_dir / "implicit_non_target_summary.md", non_target_rows, NON_TARGET_FIELDS)

    print(f"Wrote {len(main_rows)} main rows to {output_dir / 'final_results_summary.csv'}")
    print(f"Wrote {len(failure_rows)} failure rows to {output_dir / 'layered_failure_summary.csv'}")
    print(f"Wrote {len(non_target_rows)} non-target rows to {output_dir / 'implicit_non_target_summary.csv'}")


if __name__ == "__main__":
    main()
