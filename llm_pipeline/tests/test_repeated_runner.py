import argparse
import sys
from pathlib import Path

import run_10_trials_and_aggregate as runner


def _args(pipeline="llm"):
    return argparse.Namespace(
        pipeline=pipeline,
        variant="K1",
        model="qwen",
        model_type="",
        icl_mode="zero_shot",
        max_replans=3,
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


def test_llm_repeated_runner_stays_text_only_by_default() -> None:
    command = runner._trial_command(_args(pipeline="llm"), 1, Path("trial_001"))

    assert command[:3] == [sys.executable, "-m", "llm_pipeline.trial_runner"]
    assert "--vision" not in command
    assert "--no-goal-check" in command
