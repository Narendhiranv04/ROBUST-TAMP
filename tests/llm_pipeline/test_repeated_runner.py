import argparse
import sys
from pathlib import Path

from experiments import run_10_trials_and_aggregate as runner


def _args(pipeline="llm"):
    return argparse.Namespace(
        pipeline=pipeline,
        variant="K1",
        model="qwen",
        model_type="",
        quantization="",
        icl_mode="zero_shot",
        max_replans=3,
        planner_max_new_tokens=1024,
        goal_check_max_new_tokens=64,
        show_llm_output=False,
        remote=True,
        remote_url="http://127.0.0.1:8000",
        goal_check=False,
        headless=True,
    )


def test_vlm_repeated_runner_uses_maintained_trial_runner_with_vision() -> None:
    command = runner._trial_command(_args(pipeline="vlm"), 2, Path("trial_002"))

    assert command[:3] == [sys.executable, "-m", "llm_pipeline.trial_runner"]
    assert "--vision" in command
    assert "run_model_trial.py" not in command
    assert "--output-dir" in command
    assert "--planner-max-new-tokens" in command


def test_llm_repeated_runner_stays_text_only_by_default() -> None:
    command = runner._trial_command(_args(pipeline="llm"), 1, Path("trial_001"))

    assert command[:3] == [sys.executable, "-m", "llm_pipeline.trial_runner"]
    assert "--vision" not in command
    assert "--no-goal-check" in command
    assert "1024" in command


def test_repeated_runner_can_enable_raw_llm_output() -> None:
    args = _args()
    args.show_llm_output = True

    command = runner._trial_command(args, 1, Path("trial_001"))

    assert "--show-llm-output" in command


def test_repeated_runner_passes_quantization_when_set() -> None:
    args = _args()
    args.quantization = "bnb8"

    command = runner._trial_command(args, 1, Path("trial_001"))

    assert command[command.index("--quantization") + 1] == "bnb8"
    assert "--quantization" not in runner._trial_command(_args(), 1, Path("trial_001"))


def test_repeated_runner_parse_args_can_enable_goal_check(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_10_trials_and_aggregate.py",
            "--model",
            "qwen",
            "--variant",
            "K1",
            "--goal-check",
        ],
    )

    args = runner.parse_args()

    assert args.goal_check is True


def test_repeated_runner_emits_goal_check_flag_when_enabled() -> None:
    args = _args()
    args.goal_check = True

    command = runner._trial_command(args, 1, Path("trial_001"))

    assert "--goal-check" in command
    assert "--no-goal-check" not in command


def test_aggregate_separates_object_region_success_from_raw_success() -> None:
    records = [
        {
            "variant_id": "K1",
            "success_validation": {
                "success": False,
                "missing": ["spam is in table, expected cupboard_shelf"],
            },
            "raw_episode_success": True,
            "subtask_completion_rate": 1.0,
            "episode_time_s": 10.0,
            "total_replans": 1,
            "discovery_triggered_replans": 1,
            "failure_triggered_replans": 0,
            "other_triggered_replans": 0,
            "structured_events": [
                {
                    "event_type": "discovery",
                    "is_failure": False,
                    "is_replan_trigger": True,
                    "failure_id": "new_object_discovered",
                    "failure_layer": "layer_2",
                    "source": "segmentation",
                }
            ],
        },
        {
            "variant_id": "K1",
            "success_validation": {"success": True, "missing": []},
            "raw_episode_success": True,
            "subtask_completion_rate": 0.5,
            "episode_time_s": 20.0,
            "total_replans": 3,
            "discovery_triggered_replans": 0,
            "failure_triggered_replans": 1,
            "other_triggered_replans": 2,
        },
    ]

    summary = runner.aggregate_records(records)

    assert summary["episode_successes"] == 1
    assert summary["raw_episode_successes"] == 2
    assert summary["mean_task_success"] == 0.5
    assert summary["mean_raw_task_success"] == 1.0
    assert summary["failed_trial_reasons"] == {"object_region_goal_not_satisfied": 1}
    assert summary["discovery_triggered_replans"] == 1
    assert summary["failure_triggered_replans"] == 1
    assert summary["real_failure_counts"]["total_occurrences"] == {}


def test_print_summary_uses_unambiguous_metric_labels(capsys) -> None:
    args = _args()
    summary = {
        "valid_trials": 1,
        "episode_successes": 0,
        "raw_episode_successes": 1,
        "success_metric": "object_region_validation",
        "mean_task_success": 0.0,
        "mean_raw_task_success": 1.0,
        "mean_subtask_coverage": 1.0,
        "avg_time_s": 12.0,
        "avg_replans": 2.0,
        "mean_planner_invocations": 2.0,
        "mean_total_planner_time_s": 4.0,
        "mean_planner_time_per_invocation_s": 2.0,
        "discovery_triggered_replans": 1,
        "failure_triggered_replans": 0,
        "other_triggered_replans": 1,
        "implicit_non_target_handling_rate": None,
        "failed_trial_reasons": {"object_region_goal_not_satisfied": 1},
        "real_failure_counts": {"total_occurrences": {}},
        "failure_ids": {"new_object_discovered": 1},
        "failure_layers": {"layer_2": 1},
        "failure_sources": {"segmentation": 1},
        "bucket_breakdown_totals": {},
    }

    runner._print_summary(args, summary)
    output = capsys.readouterr().out

    assert "Object-Region Success:" in output
    assert "Raw Pipeline Success:" in output
    assert "Real Failure Counts:" in output
    assert "Latest Diagnostic IDs:" in output
    assert "Mean Task Success:" not in output
