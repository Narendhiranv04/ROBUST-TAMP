#!/usr/bin/env python3
"""Dump planner prompts without loading or calling an LLM/VLM."""

from __future__ import annotations

import argparse
from datetime import datetime
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from evaluation.canonical_variants import get_variant_spec  # noqa: E402
from llm_pipeline.failures import FailureCode  # noqa: E402
from llm_pipeline.pipeline import ExecutionCycleRecord, LLMPipelineConfig, LLMOnlyReplanningPipeline  # noqa: E402
from llm_pipeline.pipeline_types import FailureEvent, FailureLayer, FailureSource, FailureStage  # noqa: E402


DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "prompt_checks"


class NoOpPlanner:
    loaded = True

    def load_model(self) -> bool:
        return True


class NoOpExecutor:
    held_object = None

    def set_env(self, env) -> None:
        self.env = env

    def set_step_callback(self, callback) -> None:
        self.step_callback = callback

    def set_action_start_callback(self, callback) -> None:
        self.action_start_callback = callback


def _load_env(task_family: str, scene_path: str, headless: bool):
    os.environ["HEADLESS"] = "True" if headless else "False"
    if task_family == "kitchen":
        os.environ["KITCHEN_SCENE_FILE"] = scene_path
        return importlib.import_module("rlbench_kitchen_streams").ENV
    if task_family == "grill":
        grill_dir = REPO_ROOT / "grill_task2"
        sys.path.insert(0, str(grill_dir))
        os.environ["GRILL_SCENE_FILE"] = scene_path
        return importlib.import_module("grill_task_streams").ENV
    raise ValueError(f"Unsupported task family: {task_family}")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _synthetic_discovery_event(args: argparse.Namespace, task_family: str) -> FailureEvent:
    if args.discovery_action:
        action = args.discovery_action
    elif task_family == "grill":
        action = "open(grill_lid)"
    else:
        action = "open(box_lid)"
    objects = ", ".join(args.synthetic_discovery)
    return FailureEvent(
        failure_id=FailureCode.NEW_OBJECT_DISCOVERED,
        stage=FailureStage.AFTER_EXECUTION,
        source=FailureSource.SEGMENTATION,
        action=action,
        evidence={"newly_visible_objects": list(args.synthetic_discovery)},
        failure_layer=FailureLayer.LAYER_2,
        should_replan=True,
        message=f"Newly visible objects require replanning: {objects}",
    )


def _synthetic_failure_event(args: argparse.Namespace) -> FailureEvent:
    return FailureEvent(
        failure_id=args.synthetic_failure_id,
        stage=FailureStage.AFTER_EXECUTION,
        source=FailureSource.EXECUTOR,
        action=args.synthetic_failure_action,
        evidence={"debug_prompt_builder": True},
        failure_layer=FailureLayer.LAYER_2,
        should_replan=True,
        message=args.synthetic_failure_message,
    )


def _synthetic_region_and_description(object_name: str, task_family: str) -> tuple[str, str]:
    if task_family == "grill":
        if object_name == "plate":
            return "serving_area", "in the serving area"
        if object_name == "phone":
            return "inside_grill", "inside the grill cooking area"
        return "inside_grill", "newly visible inside the grill"
    if object_name.startswith("mug"):
        return "inside_box", "newly visible inside the box"
    return "pantry_area", "newly visible in the pantry area"


def _inject_synthetic_discovery_state(state, objects: list[str], task_family: str):
    """Mutate the debug-only state so synthetic discovery is visible in the prompt."""
    if not objects:
        return state

    if task_family == "grill":
        state.lid_states["grill_lid"] = True
        facts = [fact for fact in state.pddl_state if fact != "grill_lid_closed"]
        if "grill_lid_open" not in facts:
            facts.insert(0, "grill_lid_open")
        state.pddl_state = facts
    elif task_family == "kitchen":
        state.lid_states["box_lid"] = True

    visible = list(state.visible_objects)
    for object_name in objects:
        if object_name not in visible:
            visible.append(object_name)
        region, description = _synthetic_region_and_description(object_name, task_family)
        state.object_region_map[object_name] = region
        state.object_region_descriptions[object_name] = description
    state.visible_objects = visible

    snapshot = getattr(state, "_original_snapshot", None)
    if snapshot is not None:
        snapshot.visible_objects = list(visible)
        snapshot.newly_visible_objects = list(objects)
        for object_name in objects:
            region = state.object_region_map.get(object_name, "")
            description = state.object_region_descriptions.get(object_name, "")
            snapshot.object_region_map[object_name] = region
            snapshot.object_region_descriptions[object_name] = description
    return state


def _install_completed_actions(pipeline: LLMOnlyReplanningPipeline, actions: list[str]) -> None:
    if not actions:
        return
    pipeline.cycles = [
        ExecutionCycleRecord(
            cycle_number=1,
            is_replan=False,
            icl_mode=pipeline.config.icl_mode,
            planned_actions=list(actions),
            completed_actions=list(actions),
            success=True,
        )
    ]


def _bundle_record(bundle) -> dict[str, Any]:
    return {
        "goal_text": bundle.goal_text,
        "visible_objects": list(bundle.visible_objects),
        "valid_regions": list(bundle.valid_regions),
        "icl_mode": bundle.icl_mode,
        "previous_actions": list(bundle.previous_actions),
        "failure_context": bundle.failure_context,
        "has_images": bool(bundle.images),
        "system_prompt_chars": len(bundle.system_prompt),
        "user_prompt_chars": len(bundle.user_prompt),
    }


def dump_prompts(args: argparse.Namespace) -> int:
    variant = get_variant_spec(args.variant)
    scene_path = str(Path(args.scene_path).resolve()) if args.scene_path else variant.scene_path
    goal_text = args.goal or variant.goal_text
    output_dir = Path(args.output_dir).resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"{timestamp}_{variant.variant_id}_{args.icl_mode}"

    env = None
    pipeline = None
    try:
        env = _load_env(variant.task_family, scene_path, args.headless)
        config = LLMPipelineConfig(
            headless=args.headless,
            live_segmentation_view=False,
            visible_objects_only=True,
            enable_vision=bool(args.vision),
            text_only=not bool(args.vision),
            model_type="vlm" if args.vision else "llm",
            use_remote_planner=False,
            task_family=variant.task_family,
            scene_path=scene_path,
            icl_mode=args.icl_mode,
        )
        pipeline = LLMOnlyReplanningPipeline(config=config, planner=NoOpPlanner(), executor=NoOpExecutor())
        if not pipeline.initialize(env=env):
            print("[PromptDebug] ERROR: pipeline.initialize() returned False")
            return 1

        if args.settle_steps > 0:
            for _ in range(args.settle_steps):
                env.pr.step()

        state = pipeline._build_scene_state()
        initial_bundle = pipeline.context_builder.build_bundle(
            state=state,
            goal_text=goal_text,
            failure_event=None,
            previous_actions=[],
            icl_mode=args.icl_mode,
        )

        outputs: dict[str, dict[str, Any]] = {
            "initial": _bundle_record(initial_bundle),
        }
        _write_text(output_dir / f"{stem}_initial_system.txt", initial_bundle.system_prompt)
        _write_text(output_dir / f"{stem}_initial_user.txt", initial_bundle.user_prompt)

        if args.synthetic_discovery or args.synthetic_failure:
            completed_actions = list(args.completed_action)
            if not completed_actions and args.synthetic_discovery:
                completed_actions = [args.discovery_action or ("open(grill_lid)" if variant.task_family == "grill" else "open(box_lid)")]
            _install_completed_actions(pipeline, completed_actions)

            if args.synthetic_discovery:
                failure_event = _synthetic_discovery_event(args, variant.task_family)
                label = "synthetic_discovery"
                replan_state = _inject_synthetic_discovery_state(
                    state,
                    list(args.synthetic_discovery),
                    variant.task_family,
                )
            else:
                failure_event = _synthetic_failure_event(args)
                label = "synthetic_failure"
                replan_state = state

            replan_bundle = pipeline.context_builder.build_bundle(
                state=replan_state,
                goal_text=goal_text,
                failure_event=failure_event,
                previous_actions=completed_actions,
                icl_mode=args.icl_mode,
            )
            outputs[label] = {
                **_bundle_record(replan_bundle),
                "failure_event": failure_event.to_dict(),
            }
            _write_text(output_dir / f"{stem}_{label}_system.txt", replan_bundle.system_prompt)
            _write_text(output_dir / f"{stem}_{label}_user.txt", replan_bundle.user_prompt)

        metadata = {
            "variant": variant.variant_id,
            "task_family": variant.task_family,
            "scene_path": scene_path,
            "goal_text": goal_text,
            "icl_mode": args.icl_mode,
            "vision": bool(args.vision),
            "outputs": outputs,
        }
        _write_json(output_dir / f"{stem}_metadata.json", metadata)

        print(f"[PromptDebug] Wrote prompts to {output_dir}")
        print(f"[PromptDebug] Initial system: {output_dir / f'{stem}_initial_system.txt'}")
        print(f"[PromptDebug] Initial user:   {output_dir / f'{stem}_initial_user.txt'}")
        print(f"[PromptDebug] Metadata:       {output_dir / f'{stem}_metadata.json'}")
        return 0
    finally:
        if pipeline is not None:
            pipeline.shutdown()
        elif env is not None:
            env.pr.stop()
            env.pr.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump prompt-builder outputs without loading an LLM.")
    parser.add_argument("--variant", default="G1", choices=["K1", "K2", "K3", "G1", "G2", "G3"])
    parser.add_argument("--scene-path", default="")
    parser.add_argument("--goal", default="")
    parser.add_argument("--icl-mode", choices=["zero_shot", "few_shot_shared_1"], default="zero_shot")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--vision", action="store_true", help="Capture VLM composite image metadata while dumping prompts.")
    parser.add_argument("--settle-steps", type=int, default=0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--synthetic-discovery", nargs="*", default=[], metavar="OBJECT")
    parser.add_argument("--discovery-action", default="")
    parser.add_argument("--completed-action", action="append", default=[])
    parser.add_argument("--synthetic-failure", action="store_true")
    parser.add_argument("--synthetic-failure-id", default=FailureCode.PLACEMENT_FAILED)
    parser.add_argument("--synthetic-failure-action", default="place(object, region)")
    parser.add_argument("--synthetic-failure-message", default="Synthetic failure for prompt inspection.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(dump_prompts(parse_args()))
