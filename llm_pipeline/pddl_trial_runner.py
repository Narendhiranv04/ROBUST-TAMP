#!/usr/bin/env python3
"""Pure PDDLStream trials for grill variants.

This intentionally does not call an LLM. It asks the current grill PDDLStream
domain/streams to solve a symbolic goal, translates the resulting PDDL plan
into the same direct action format used by debug_execution/trial_runner, and
can optionally execute those direct actions through the same pipeline executor.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
GRILL_DIR = ROOT_DIR / "grill_task2"
PDDLSTREAM_DIR = ROOT_DIR / "pddlstream"
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "llm_pipeline" / "results" / "pddl_runs"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(GRILL_DIR) not in sys.path:
    sys.path.insert(0, str(GRILL_DIR))
if str(PDDLSTREAM_DIR) not in sys.path:
    sys.path.insert(0, str(PDDLSTREAM_DIR))

from evaluation.canonical_variants import get_variant_spec  # noqa: E402
from llm_pipeline.pipeline_types import (  # noqa: E402
    DirectAction,
    FailureEvent,
    FailureLayer,
    FailureSource,
    FailureStage,
    PlanResult,
)
from llm_pipeline.region_aliases import normalize_region_name  # noqa: E402
from llm_pipeline.strict_parser import StrictParseError  # noqa: E402
from pddlstream.algorithms.meta import solve  # noqa: E402
from pddlstream.language.generator import from_gen_fn  # noqa: E402
from pddlstream.language.constants import And, PDDLProblem  # noqa: E402
from pddlstream.utils import read  # noqa: E402


VARIANT_OBJECTS = {
    "G1": ("spam", "chicken", "plate"),
    "G2": ("steak", "chicken", "steak1", "plate"),
    "G3": ("spam", "steak", "chicken", "steak1", "plate"),
}

VARIANT_FINAL_REGION_GOALS = {
    "G1": (
        ("in-region", "spam", "table"),
        ("in-region", "chicken", "plate_top"),
        ("in-region", "plate", "plate_boundary"),
    ),
    "G2": (
        ("in-region", "steak", "plate_top"),
        ("in-region", "chicken", "plate_top"),
        ("in-region", "steak1", "plate_top"),
        ("in-region", "plate", "plate_boundary"),
    ),
    "G3": (
        ("in-region", "spam", "table"),
        ("in-region", "steak", "plate_top"),
        ("in-region", "chicken", "plate_top"),
        ("in-region", "steak1", "plate_top"),
        ("in-region", "plate", "plate_boundary"),
    ),
}

VARIANT_RECIPE_PROXY_GOALS = {
    "G1": VARIANT_FINAL_REGION_GOALS["G1"] + (
        ("on-grill", "chicken"),
    ),
    "G2": VARIANT_FINAL_REGION_GOALS["G2"] + (
        ("on-grill", "chicken"),
        ("on-grill", "steak1"),
    ),
    "G3": VARIANT_FINAL_REGION_GOALS["G3"] + (
        ("on-grill", "chicken"),
        ("on-grill", "steak1"),
    ),
}

PLANNER_REGIONS = (
    "table",
    "grill-top",
    "plate_top",
    "plate_boundary",
    "dish_rack",
    "prep_area",
    "placement_boundary",
)

DIRECT_TO_PDDL_REGION = {
    "inside_grill": "grill-top",
}


def _configure_qt(headless: bool) -> None:
    os.environ["HEADLESS"] = "True" if headless else "False"
    os.environ["COPPELIASIM_HEADLESS"] = "1" if headless else "0"
    os.environ.pop("QT_PLUGIN_PATH", None)
    os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false;qt.qpa.*=false")
    coppelia_root = os.environ.get("COPPELIASIM_ROOT") or os.path.expanduser("~/CoppeliaSim")
    for candidate in (
        os.path.join(coppelia_root, "platforms"),
        os.path.join(coppelia_root, "Qt", "plugins", "platforms"),
        os.path.join(coppelia_root, "qt", "plugins", "platforms"),
    ):
        if candidate and os.path.isdir(candidate):
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", candidate)
            break


def _configure_grill_variant(variant_id: str, headless: bool) -> Any:
    variant = get_variant_spec(variant_id)
    from llm_pipeline.debug_execution import DebugSequence, _configure_scene_env, _load_env_for_sequence

    sequence = DebugSequence(
        name=f"{variant.variant_id}_pure_pddl",
        variant=variant.variant_id,
        goal=variant.goal_text,
        actions=(),
    )
    _configure_qt(headless=headless)
    _configure_scene_env(sequence, headless=headless)
    os.environ.setdefault("GRILL_OPEN_USE_ONLINE_STEP3", "True")

    env = _load_env_for_sequence(sequence)
    streams_module = importlib.import_module("grill_task_streams")
    if env is not None:
        # PDDLStream callbacks read the module-level ENV inside
        # grill_task_streams.py. Keep planning facts and stream sampling on the
        # same GT-prepared scene instead of a second default GrillTaskEnv.
        streams_module.ENV = env

    active_env = env or streams_module.ENV
    return active_env, lambda: _make_executor_aligned_stream_map(active_env)


def _as_tuple(value: Any) -> Tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    try:
        return tuple(value.tolist())
    except Exception:
        return tuple(value)


def _is_plate_object(object_name: Any) -> bool:
    return "plate" in str(object_name).lower()


def _get_grill_gt_module() -> Any:
    module = sys.modules.get("grill_gt")
    if module is not None:
        return module
    script_path = GRILL_DIR / "ground_truth_orchestrator_variation1 copy.py"
    module_spec = importlib.util.spec_from_file_location("grill_gt", script_path)
    if module_spec is None or module_spec.loader is None:
        return None
    module = importlib.util.module_from_spec(module_spec)
    sys.modules["grill_gt"] = module
    module_spec.loader.exec_module(module)
    return module


def _executor_aligned_region_poses(env: Any, obj: Any, region_name: str) -> Iterable[Tuple[Any, ...]]:
    """Yield deterministic region poses that mirror the grill bundle executor.

    The grill direct-action executor uses GT slot poses for non-plate objects
    instead of unconstrained random stable poses. Exposing those same slot poses
    to PDDLStream keeps planning-time feasibility closer to execution-time
    feasibility.
    """
    grill_gt = _get_grill_gt_module()
    region_name = _region_for_pddl_goal(region_name)
    seen = set()

    if grill_gt is not None and hasattr(grill_gt, "_region_slot_pose") and not _is_plate_object(getattr(obj, "get_name", lambda: "")()):
        for slot_idx in range(3):
            try:
                pose = grill_gt._region_slot_pose(env, obj, region_name, slot_idx=slot_idx, slot_count=3)
            except Exception:
                continue
            key = tuple(round(float(x), 6) for x in list(pose)[:3])
            if key not in seen:
                seen.add(key)
                yield tuple(pose)
        if seen:
            return

    for _ in range(3):
        try:
            pose = env.sample_stable_pose(obj, region_name)
        except Exception:
            continue
        key = tuple(round(float(x), 6) for x in list(pose)[:3])
        if key not in seen:
            seen.add(key)
            yield tuple(pose)


def _executor_aligned_motion(env: Any, q1: Any, q2: Any) -> Optional[List[Any]]:
    try:
        path = env.compute_motion_plan(q1, q2)
        if path:
            return path
    except Exception:
        pass
    try:
        path = env._interpolate_joint_path(q1, q2, steps=80, check_collisions=True)
        if path:
            return path
    except Exception:
        pass
    try:
        q1_list = [float(x) for x in q1]
        q2_list = [float(x) for x in q2]
        steps = 80
        return [
            [
                (1.0 - (i / float(steps - 1))) * a + (i / float(steps - 1)) * b
                for a, b in zip(q1_list, q2_list)
            ]
            for i in range(steps)
        ]
    except Exception:
        return None


def _make_executor_aligned_stream_map(env: Any) -> Dict[str, Any]:
    """Build PDDLStream streams using the same primitive helpers as execution.

    This is still a planning-time check, not a dry-run execution. The alignment
    is: deterministic GT slot poses for placements, preferred hover orientation
    for picks, executor-style motion fallback, and the same env instance.
    """

    def fn_sample_stable_pose(o, r):
        obj = env.get_object(str(o))
        if not obj:
            return
        for pose in _executor_aligned_region_poses(env, obj, str(r)):
            yield (tuple(pose),)

    def fn_sample_pick_kin(o, p):
        obj = env.get_object(str(o))
        if not obj:
            return
        is_plate = _is_plate_object(o)
        preferred_orientation = None
        try:
            _q_hover, preferred_orientation = env.compute_hover_config(
                obj,
                list(p),
                hover_offset=0.15,
            )
        except Exception:
            preferred_orientation = None
        try:
            grasp, q1, q2, traj_tuple = env.compute_pick_trajectory(
                obj,
                list(p),
                preferred_orientation=preferred_orientation,
                is_plate=is_plate,
            )
            yield (_as_tuple(grasp), _as_tuple(q1), _as_tuple(q2), traj_tuple)
        except Exception:
            return

    def fn_sample_place_kin(o, p, r):
        obj = env.get_object(str(o))
        if not obj:
            return
        region_name = _region_for_pddl_goal(str(r))
        is_plate = _is_plate_object(o)
        try:
            grasp, q1, q2, traj_tuple = env.compute_place_trajectory(
                obj,
                list(p),
                region_name=region_name,
                is_plate=is_plate,
            )
            q_home, traj_home = env.compute_retreat_to_home(q2)
            if traj_home:
                new_traj_tuple = tuple(list(traj_tuple) + [traj_home])
                yield (_as_tuple(grasp), _as_tuple(q1), _as_tuple(q_home), new_traj_tuple)
        except Exception:
            return

    def fn_sample_motion(q1, q2):
        path = _executor_aligned_motion(env, q1, q2)
        if path is None:
            return
        yield (path,)

    def fn_sample_close_grill(o):
        obj = env.get_object(str(o))
        if not obj:
            return
        try:
            grasp, q1, q2, traj = env.compute_close_grill_trajectory(obj)
            yield (_as_tuple(grasp), _as_tuple(q1), _as_tuple(q2), traj)
            return
        except Exception:
            # The executor has a separate GT close primitive even though the
            # PDDLStream close trajectory helper is currently incomplete.
            grill_gt = _get_grill_gt_module()
            if grill_gt is None or not hasattr(grill_gt, "run_grill_lid_motion_framework"):
                return
            q_home = _as_tuple(env.get_home_conf())
            yield (tuple([0] * 7), q_home, q_home, ([],))

    def fn_sample_open_grill(o):
        obj = env.get_object(str(o))
        if not obj:
            return
        try:
            grasp, q1, q2, traj = env.compute_open_grill_trajectory(obj)
            yield (_as_tuple(grasp), _as_tuple(q1), _as_tuple(q2), traj)
        except Exception:
            return

    return {
        "sample-stable-pose": from_gen_fn(fn_sample_stable_pose),
        "sample-pick-kin": from_gen_fn(fn_sample_pick_kin),
        "sample-place-kin": from_gen_fn(fn_sample_place_kin),
        "sample-motion": from_gen_fn(fn_sample_motion),
        "sample-close-grill": from_gen_fn(fn_sample_close_grill),
        "sample-open-grill": from_gen_fn(fn_sample_open_grill),
    }


class FixedActionPlanner:
    """Planner shim that returns PDDL-translated direct actions to the pipeline."""

    def __init__(self, actions: Iterable[DirectAction], raw_output: str):
        self.actions = list(actions)
        self.raw_output = raw_output
        self.loaded = True
        self.parser = None
        self.model_alias = "pure-pddl"
        self.model_name = "pure-pddl"

    def load_model(self) -> bool:
        return True

    def plan(self, bundle) -> PlanResult:
        del bundle
        if self.parser is not None:
            try:
                parsed_actions = self.parser.parse(self.raw_output)
            except StrictParseError as exc:
                return PlanResult(
                    success=False,
                    actions=[],
                    raw_output=self.raw_output,
                    inference_time=0.0,
                    error_message=str(exc),
                    failure_event=FailureEvent(
                        failure_id=exc.failure_id,
                        stage=FailureStage.BEFORE_EXECUTION,
                        source=FailureSource.VALIDATION,
                        action=None,
                        evidence={"line_number": exc.line_number, "raw_output": self.raw_output},
                        failure_layer=FailureLayer.LAYER_1,
                        should_replan=False,
                        message=str(exc),
                    ),
                )
            return PlanResult(
                success=True,
                actions=parsed_actions,
                raw_output=self.raw_output,
                inference_time=0.0,
            )
        return PlanResult(
            success=True,
            actions=list(self.actions),
            raw_output=self.raw_output,
            inference_time=0.0,
        )


def _fact_repr(fact: Sequence[Any]) -> str:
    return "(" + " ".join(str(item) for item in fact) + ")"


def _jsonable(value: Any, max_len: int = 500) -> Any:
    text = repr(value)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def _action_summary(action: Any) -> Dict[str, Any]:
    return {
        "name": str(getattr(action, "name", "")),
        "args": [_jsonable(arg) for arg in getattr(action, "args", ())],
        "repr": _jsonable(action, max_len=1000),
    }


def _direct_action_summary(actions: Iterable[DirectAction]) -> List[str]:
    return [str(action) for action in actions]


def _region_for_direct_action(region_name: Any) -> str:
    return normalize_region_name(str(region_name))


def _region_for_pddl_goal(region_name: Any) -> str:
    direct_region = normalize_region_name(str(region_name))
    return DIRECT_TO_PDDL_REGION.get(direct_region, direct_region)


def _lid_for_direct_action(lid_name: Any) -> str:
    token = str(lid_name)
    if token == "lid":
        return "grill_lid"
    return token


def _transfer_actions(obj_name: str, region_name: str) -> List[DirectAction]:
    return [
        DirectAction("pick", (obj_name,)),
        DirectAction("place", (obj_name, region_name)),
    ]


def _lid_actions(action_name: str, lid_name: str) -> List[DirectAction]:
    return [
        DirectAction(action_name, (lid_name,)),
    ]


def _translate_pddl_plan_to_direct_actions(plan: Optional[Iterable[Any]]) -> List[DirectAction]:
    """Convert PDDLStream operators into direct executable action lines.

    Low-level PDDLStream ``move`` actions carry joint configurations, so they are
    ignored. Pick/place pairs become the same four-line transfer bundles used in
    debug sequences and LLM runs.
    """
    if not plan:
        return []

    direct_actions: List[DirectAction] = []
    pending_pick: Optional[str] = None

    for action in plan:
        name = str(getattr(action, "name", ""))
        args = list(getattr(action, "args", ()))

        if name == "move":
            continue

        if name == "open-grill":
            lid_name = _lid_for_direct_action(args[0] if args else "grill_lid")
            direct_actions.extend(_lid_actions("open", lid_name))
            continue

        if name == "close-grill":
            lid_name = _lid_for_direct_action(args[0] if args else "grill_lid")
            direct_actions.extend(_lid_actions("close", lid_name))
            continue

        if name == "pick":
            pending_pick = str(args[0])
            continue

        if name == "place":
            if len(args) < 4:
                continue
            obj_name = str(args[0])
            region_name = _region_for_direct_action(args[3])
            if pending_pick is not None and pending_pick != obj_name:
                direct_actions.extend(_transfer_actions(pending_pick, region_name))
            direct_actions.extend(_transfer_actions(obj_name, region_name))
            pending_pick = None
            continue

    return direct_actions


def _existing_objects(env: Any, object_names: Iterable[str]) -> Tuple[List[str], List[str]]:
    present: List[str] = []
    missing: List[str] = []
    for name in object_names:
        try:
            obj = env.get_object(name)
        except Exception:
            obj = None
        if obj is None:
            missing.append(name)
        else:
            present.append(name)
    return present, missing


def _build_problem_from_goal_facts(
    env: Any,
    get_stream_map: Any,
    variant_id: str,
    goal_facts: Tuple[Tuple[Any, ...], ...],
    lid_open: bool = False,
) -> Tuple[PDDLProblem, Dict[str, Any]]:
    variant_id = variant_id.upper()
    home_q = tuple(env.get_home_conf())
    env.set_robot_conf(list(home_q))
    try:
        env.gripper.release()
    except Exception:
        pass

    objects, missing_objects = _existing_objects(env, VARIANT_OBJECTS[variant_id])
    if missing_objects:
        raise RuntimeError(f"Missing expected scene objects for {variant_id}: {', '.join(missing_objects)}")

    init: List[Tuple[Any, ...]] = [
        ("conf", home_q),
        ("at-conf", home_q),
        ("is-home", home_q),
        ("hand-empty",),
        ("lid", "lid"),
        ("grill-open" if lid_open else "grill-closed", "lid"),
        ("grill-surface", "grill-top"),
    ]

    for region in PLANNER_REGIONS:
        init.append(("region", region))

    object_poses: Dict[str, Any] = {}
    for name in objects:
        obj = env.get_object(name)
        try:
            obj.set_dynamic(False)
        except Exception:
            pass
        pose = tuple(obj.get_pose())
        object_poses[name] = pose
        init.extend(
            [
                ("movable", name),
                ("pose", pose),
                ("at-pose", name, pose),
            ]
        )

    domain_pddl = read(str(GRILL_DIR / "pddl" / "grill_task_domain.pddl"))
    stream_pddl = read(str(GRILL_DIR / "pddl" / "grill_task_streams.pddl"))
    goal = goal_facts[0] if len(goal_facts) == 1 else And(*goal_facts)
    problem = PDDLProblem(
        domain_pddl=domain_pddl,
        constant_map={},
        stream_pddl=stream_pddl,
        stream_map=get_stream_map(),
        init=init,
        goal=goal,
    )
    problem_info = {
        "objects": objects,
        "regions": list(PLANNER_REGIONS),
        "object_poses": {name: _jsonable(pose) for name, pose in object_poses.items()},
        "init_fact_count": len(init),
        "goal_facts": [_fact_repr(fact) for fact in goal_facts],
        "known_limitations": [
            "The current grill PDDL domain has no cooked/not-cooked predicate.",
            "recipe_proxy uses persistent on-grill facts to require grill visitation, not true cooking.",
            "The current place action does not require grill-open, so closed-grill placement is not symbolically blocked.",
            "Executor-aligned streams use GT slot poses and primitive motion helpers, but planning still does not dry-run the full executor ritual.",
            "Close-grill uses an executor-capability proxy if the standalone close trajectory helper is unavailable; actual close feasibility is still tested during execution.",
        ],
    }
    return problem, problem_info


def _build_problem(env: Any, get_stream_map: Any, variant_id: str, goal_mode: str) -> Tuple[PDDLProblem, Dict[str, Any]]:
    variant_id = variant_id.upper()
    if goal_mode == "open_only":
        goal_facts: Tuple[Tuple[Any, ...], ...] = (("grill-open", "lid"),)
    elif goal_mode == "recipe_proxy":
        goal_facts = tuple(VARIANT_RECIPE_PROXY_GOALS[variant_id]) + (
            ("grill-open", "lid"),
            ("hand-empty",),
        )
    else:
        goal_facts = tuple(VARIANT_FINAL_REGION_GOALS[variant_id]) + (
            ("grill-open", "lid"),
            ("hand-empty",),
        )
    return _build_problem_from_goal_facts(
        env=env,
        get_stream_map=get_stream_map,
        variant_id=variant_id,
        goal_facts=goal_facts,
        lid_open=False,
    )


def _output_paths(variant_id: str, goal_mode: str, output_dir: Path | None, output_root: Path) -> Tuple[Path, Path]:
    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = output_root / f"{stamp}_{variant_id}_pure_pddl_{goal_mode}"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / "record.json", output_dir / "summary.txt"


def _render_summary(record: Dict[str, Any]) -> str:
    lines = [
        f"variant: {record.get('variant_id')}",
        f"task_family: {record.get('task_family')}",
        f"goal_mode: {record.get('goal_mode')}",
        f"status: {record.get('status')}",
        f"plan_found: {record.get('plan_found')}",
        f"execution_enabled: {record.get('execution_enabled')}",
        f"execution_success: {record.get('execution_success')}",
        f"planning_time_s: {record.get('planning_time_s')}",
        f"execution_time_s: {record.get('execution_time_s')}",
        f"total_time_s: {record.get('total_time_s')}",
        f"max_time_s: {record.get('max_time_s')}",
        f"max_planner_time_s: {record.get('max_planner_time_s')}",
        f"plan_length: {record.get('plan_length')}",
        f"direct_action_count: {len(record.get('direct_actions', []))}",
        f"cost: {record.get('cost')}",
        "",
        "goal_facts:",
    ]
    lines.extend(f"- {fact}" for fact in record.get("goal_facts", []))
    lines.extend(["", "plan_actions:"])
    for action in record.get("plan_actions", []):
        lines.append(f"- {action.get('name')}")
    lines.extend(["", "direct_actions:"])
    for action in record.get("direct_actions", []):
        lines.append(f"- {action}")
    if record.get("execution_summary"):
        summary = record["execution_summary"]
        lines.extend(
            [
                "",
                f"completed_actions: {len(summary.get('completed_actions', []))}",
                f"remaining_actions: {len(summary.get('remaining_actions', []))}",
                f"failure_reason: {summary.get('failure_reason')}",
            ]
        )
        failure = summary.get("last_failure_event") or {}
        if failure:
            lines.extend(
                [
                    "failure:",
                    f"failure_id: {failure.get('failure_id')}",
                    f"failure_layer: {failure.get('failure_layer')}",
                    f"failure_stage: {failure.get('stage')}",
                    f"failure_source: {failure.get('source')}",
                    f"failure_action: {failure.get('action')}",
                    f"failure_message: {failure.get('message')}",
                    f"failure_evidence: {json.dumps(failure.get('evidence', {}), default=str)}",
                ]
            )
    if record.get("error_message"):
        lines.extend(["", f"error_message: {record.get('error_message')}"])
    if record.get("known_limitations"):
        lines.extend(["", "known_limitations:"])
        lines.extend(f"- {item}" for item in record.get("known_limitations", []))
    return "\n".join(lines).rstrip() + "\n"


def _execute_direct_actions(
    env: Any,
    variant_id: str,
    goal_text: str,
    direct_actions: List[DirectAction],
    headless: bool,
    live_masks: bool,
    scene_state_trace: bool,
) -> Dict[str, Any]:
    from llm_pipeline.pipeline import LLMPipelineConfig, LLMOnlyReplanningPipeline

    variant = get_variant_spec(variant_id)
    raw_output = "\n".join(str(action) for action in direct_actions)
    planner = FixedActionPlanner(direct_actions, raw_output=raw_output)
    config = LLMPipelineConfig(
        headless=headless,
        visible_objects_only=True,
        enable_vision=False,
        max_replans=0,
        task_family=variant.task_family,
        scene_path=variant.scene_path,
        live_segmentation_view=bool(live_masks and not headless),
        live_view_update_stride=1_000_000,
        scene_state_trace=bool(scene_state_trace),
    )
    pipeline = LLMOnlyReplanningPipeline(config=config, planner=planner)
    try:
        if not pipeline.initialize(env=env):
            raise RuntimeError("pipeline_initialize_failed")
        return pipeline.run(goal_text=goal_text)
    finally:
        pipeline.shutdown()


def _execute_direct_actions_directly(env: Any, direct_actions: List[DirectAction]) -> Dict[str, Any]:
    from llm_pipeline.executor import DirectPrimitiveExecutor

    executor = DirectPrimitiveExecutor(env=env)
    executor.reset_episode()
    execution = executor.execute_actions(
        list(direct_actions),
        failure_checker=None,
        pre_action_checks_enabled=False,
        post_action_checks_enabled=False,
    )
    return {
        "success": bool(execution.success),
        "completed_actions": list(execution.completed_actions),
        "remaining_actions": list(execution.remaining_actions),
        "held_object": execution.held_object,
        "last_failure_event": (
            execution.last_failure_event.to_dict()
            if execution.last_failure_event is not None
            else None
        ),
        "failure_reason": execution.error_message,
    }


def _gt_macro_chunks(variant_id: str) -> List[Dict[str, Any]]:
    from llm_pipeline.debug_execution import BUILTIN_SEQUENCES

    sequence = BUILTIN_SEQUENCES[variant_id.upper()]
    actions = list(sequence.actions)
    chunks: List[Dict[str, Any]] = []
    index = 0
    while index < len(actions):
        action = actions[index]
        if action.action_name in {"open", "close"}:
            lid_action = action
            lid_name = _lid_for_direct_action(lid_action.args[0])
            goal_name = "grill-open" if lid_action.action_name == "open" else "grill-closed"
            chunks.append(
                {
                    "index": len(chunks) + 1,
                    "kind": "lid",
                    "label": f"{lid_action.action_name}({lid_name})",
                    "reference_actions": _direct_action_summary([action]),
                    "goal_facts": ((goal_name, "lid"),),
                    "direct_goal_hint": lid_action.action_name,
                }
            )
            index += 1
            continue

        if (
            action.action_name == "pick"
            and index + 1 < len(actions)
            and actions[index + 1].action_name == "place"
        ):
            pick_action = action
            place_action = actions[index + 1]
            obj_name = pick_action.args[0]
            direct_region = normalize_region_name(place_action.args[1])
            pddl_region = _region_for_pddl_goal(direct_region)
            chunks.append(
                {
                    "index": len(chunks) + 1,
                    "kind": "transfer",
                    "label": f"{obj_name} -> {direct_region}",
                    "reference_actions": _direct_action_summary(actions[index:index + 2]),
                    "goal_facts": (
                        ("in-region", obj_name, pddl_region),
                        ("hand-empty",),
                    ),
                    "direct_goal_hint": f"{obj_name}->{direct_region}",
                }
            )
            index += 2
            continue

        chunks.append(
            {
                "index": len(chunks) + 1,
                "kind": "unknown",
                "label": str(action),
                "reference_actions": [str(action)],
                "goal_facts": tuple(),
                "direct_goal_hint": "",
            }
        )
        index += 1
    return chunks


def _prefix_goal_facts(milestones: Sequence[Dict[str, Any]], count: int) -> Tuple[Tuple[Any, ...], ...]:
    """Return cumulative final-state facts for the first ``count`` GT milestones.

    This asks: from the original initial scene, can PDDL reach the state that
    should hold after this GT prefix? Object regions are overwritten by later
    placements, while on-grill facts persist as a weak "has visited grill" proxy.
    """
    object_regions: Dict[str, Tuple[Any, ...]] = {}
    on_grill: Dict[str, Tuple[Any, ...]] = {}
    lid_fact: Optional[Tuple[Any, ...]] = None
    include_hand_empty = False

    for milestone in milestones[:count]:
        for fact in milestone.get("goal_facts") or ():
            fact = tuple(fact)
            if not fact:
                continue
            predicate = fact[0]
            if predicate == "in-region" and len(fact) >= 3:
                object_regions[str(fact[1])] = fact
                if str(fact[2]) == "grill-top":
                    on_grill[str(fact[1])] = ("on-grill", fact[1])
                continue
            if predicate in {"grill-open", "grill-closed"}:
                lid_fact = fact
                continue
            if predicate == "hand-empty":
                include_hand_empty = True
                continue
            if predicate == "on-grill" and len(fact) >= 2:
                on_grill[str(fact[1])] = fact

    facts: List[Tuple[Any, ...]] = list(object_regions.values())
    facts.extend(on_grill.values())
    if lid_fact is not None:
        facts.append(lid_fact)
    if include_hand_empty:
        facts.append(("hand-empty",))
    return tuple(facts)


def _solve_pddl_problem(
    problem: PDDLProblem,
    max_time: float,
    max_planner_time: float,
    verbose: bool,
) -> Tuple[Any, Any, Any, float]:
    started = time.time()
    plan, cost, evaluations = solve(
        problem,
        algorithm="binding",
        verbose=bool(verbose),
        max_time=float(max_time),
        max_iterations=max(1, int(max(1.0, max_time) // max(1.0, max_planner_time)) + 1),
        max_planner_time=float(max_planner_time),
        unit_costs=True,
    )
    return plan, cost, evaluations, time.time() - started


def _shutdown_env(env: Any) -> None:
    try:
        if env is not None:
            env.pr.stop()
            env.pr.shutdown()
    except Exception:
        pass


def _diagnose_lid_stream(env: Any, direct_goal_hint: str) -> Dict[str, Any]:
    lid = None
    try:
        lid = env.get_object("lid")
    except Exception as exc:
        return {"success": False, "stage": "get_object", "error": str(exc)}
    if lid is None:
        return {"success": False, "stage": "get_object", "error": "env.get_object('lid') returned None"}

    fn_name = "compute_open_grill_trajectory" if direct_goal_hint == "open" else "compute_close_grill_trajectory"
    try:
        fn = getattr(env, fn_name)
    except Exception as exc:
        return {"success": False, "stage": "lookup", "function": fn_name, "error": str(exc)}

    try:
        result = fn(lid)
    except Exception as exc:
        return {
            "success": False,
            "stage": "trajectory",
            "function": fn_name,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    grasp, q_start, q_end, traj = result
    segment_lengths = []
    if isinstance(traj, (list, tuple)):
        for segment in traj:
            try:
                segment_lengths.append(len(segment))
            except Exception:
                segment_lengths.append(None)
    return {
        "success": True,
        "stage": "trajectory",
        "function": fn_name,
        "grasp_dim": len(grasp) if hasattr(grasp, "__len__") else None,
        "q_start": _jsonable(q_start, max_len=160),
        "q_end": _jsonable(q_end, max_len=160),
        "trajectory_segment_lengths": segment_lengths,
    }


def _diagnose_transfer_stream(env: Any, object_name: str, region_name: str, samples: int = 3) -> Dict[str, Any]:
    """Probe the same geometry samplers a transfer PDDL plan depends on."""
    try:
        obj = env.get_object(object_name)
    except Exception as exc:
        return {"success": False, "stage": "get_object", "object": object_name, "error": str(exc)}
    if obj is None:
        return {"success": False, "stage": "get_object", "object": object_name, "error": "object not found"}

    try:
        obj.set_dynamic(False)
    except Exception:
        pass

    result: Dict[str, Any] = {
        "success": False,
        "object": object_name,
        "region": region_name,
        "pick": None,
        "place_attempts": [],
    }

    try:
        pose = list(obj.get_pose())
        grasp, q1, q2, traj = env.compute_pick_trajectory(obj, pose)
        pick_segments = [len(seg) for seg in traj] if isinstance(traj, (list, tuple)) else []
        result["pick"] = {
            "success": True,
            "grasp_dim": len(grasp) if hasattr(grasp, "__len__") else None,
            "q_start": _jsonable(q1, max_len=160),
            "q_end": _jsonable(q2, max_len=160),
            "trajectory_segment_lengths": pick_segments,
        }
    except Exception as exc:
        result["pick"] = {
            "success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

    for attempt in range(max(1, int(samples))):
        item: Dict[str, Any] = {"attempt": attempt + 1}
        try:
            target_pose = list(env.sample_stable_pose(obj, region_name))
            item["sampled_pose"] = _jsonable(target_pose, max_len=180)
            grasp, q1, q2, traj = env.compute_place_trajectory(obj, target_pose, region_name=region_name)
            q_home, traj_home = env.compute_retreat_to_home(q2)
            place_segments = [len(seg) for seg in traj] if isinstance(traj, (list, tuple)) else []
            item.update(
                {
                    "success": bool(traj_home),
                    "grasp_dim": len(grasp) if hasattr(grasp, "__len__") else None,
                    "q_start": _jsonable(q1, max_len=160),
                    "q_end": _jsonable(q2, max_len=160),
                    "trajectory_segment_lengths": place_segments,
                    "retreat_to_home": bool(traj_home),
                    "retreat_waypoints": len(traj_home) if traj_home else 0,
                }
            )
            result["place_attempts"].append(item)
            if item["success"]:
                result["success"] = bool(result.get("pick", {}).get("success"))
                result["stage"] = "pick_and_place" if result["success"] else "place_only"
                break
        except Exception as exc:
            item.update(
                {
                    "success": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            result["place_attempts"].append(item)

    if not result["success"] and "stage" not in result:
        if not result.get("pick", {}).get("success"):
            result["stage"] = "pick"
        else:
            result["stage"] = "place"
    return result


def run_gt_scan(
    variant_id: str,
    max_time: float,
    max_planner_time: float,
    headless: bool,
    verbose: bool,
    execute: bool,
    scan_mode: str,
    lid_stream_precheck: bool,
    transfer_stream_precheck: bool,
    output_dir: Path | None,
    output_root: Path,
) -> Dict[str, Any]:
    variant = get_variant_spec(variant_id)
    env = None
    json_path, txt_path = _output_paths(variant.variant_id, f"gt_scan_{scan_mode}", output_dir, output_root)
    record: Dict[str, Any] = {
        "variant_id": variant.variant_id,
        "task_family": variant.task_family,
        "scene_path": variant.scene_path,
        "goal_mode": f"gt_scan_{scan_mode}",
        "gt_scan_mode": scan_mode,
        "max_time_s": float(max_time),
        "max_planner_time_s": float(max_planner_time),
        "headless": bool(headless),
        "execution_enabled": bool(execute),
        "lid_stream_precheck": bool(lid_stream_precheck),
        "transfer_stream_precheck": bool(transfer_stream_precheck),
        "status": "failed",
        "milestones": [],
        "completed_milestones": 0,
        "known_limitations": [],
    }
    started = time.time()
    lid_open = False
    try:
        milestones = _gt_macro_chunks(variant.variant_id)
        if scan_mode == "sequential":
            env, get_stream_map = _configure_grill_variant(variant.variant_id, headless=headless)
        print("=" * 72)
        print(f"PURE PDDLSTREAM GT SCAN: {variant.variant_id}")
        print("=" * 72)
        print(f"Scene: {variant.scene_path}")
        print(f"GT scan mode: {scan_mode}")
        print(f"Milestones: {len(milestones)}")

        for milestone in milestones:
            print("\n" + "-" * 72)
            print(f"[{milestone['index']}/{len(milestones)}] {milestone['label']}")
            if scan_mode == "initial_prefix":
                env, get_stream_map = _configure_grill_variant(variant.variant_id, headless=headless)
                goal_facts = _prefix_goal_facts(milestones, int(milestone["index"]))
                problem_lid_open = False
            else:
                goal_facts = tuple(milestone.get("goal_facts") or ())
                problem_lid_open = lid_open
            item: Dict[str, Any] = {
                "index": milestone["index"],
                "kind": milestone["kind"],
                "label": milestone["label"],
                "scan_mode": scan_mode,
                "reference_actions": milestone["reference_actions"],
                "goal_facts": [_fact_repr(fact) for fact in goal_facts],
                "plan_found": False,
                "execution_success": None,
            }
            if not goal_facts:
                item["error_message"] = "No PDDL goal mapping for milestone."
                record["milestones"].append(item)
                break

            if lid_stream_precheck and milestone["kind"] == "lid":
                print("[precheck] Probing lid trajectory stream before PDDL solve...")
                diagnostic = _diagnose_lid_stream(env, str(milestone.get("direct_goal_hint", "")))
                item["pre_solve_stream_diagnostic"] = diagnostic
                print(f"[precheck] {diagnostic}")
                if not diagnostic.get("success"):
                    item["error_message"] = "Lid trajectory stream failed before PDDL solve."
                    record["milestones"].append(item)
                    print(f"[STOP] Stream precheck failed for {milestone['label']}")
                    break

            if transfer_stream_precheck and milestone["kind"] == "transfer":
                transfer_fact = next((fact for fact in goal_facts if fact and fact[0] == "in-region"), None)
                if transfer_fact is not None and len(transfer_fact) >= 3:
                    print("[precheck] Probing transfer geometry streams before PDDL solve...")
                    diagnostic = _diagnose_transfer_stream(env, str(transfer_fact[1]), str(transfer_fact[2]))
                    item["pre_solve_transfer_diagnostic"] = diagnostic
                    print(f"[precheck] {diagnostic}")

            problem, _info = _build_problem_from_goal_facts(
                env=env,
                get_stream_map=get_stream_map,
                variant_id=variant.variant_id,
                goal_facts=goal_facts,
                lid_open=problem_lid_open,
            )
            plan, cost, evaluations, planning_time = _solve_pddl_problem(
                problem,
                max_time=max_time,
                max_planner_time=max_planner_time,
                verbose=verbose,
            )
            item["planning_time_s"] = round(planning_time, 3)
            item["cost"] = None if cost is None else _jsonable(cost)
            item["evaluation_count"] = None if evaluations is None else len(evaluations)

            if plan is None:
                item["error_message"] = "No PDDLStream plan found for this GT milestone."
                if milestone["kind"] == "lid":
                    diagnostic = _diagnose_lid_stream(env, str(milestone.get("direct_goal_hint", "")))
                    item["stream_diagnostic"] = diagnostic
                    print(f"[stream diagnostic] {diagnostic}")
                record["milestones"].append(item)
                print(f"[STOP] No PDDL plan for {milestone['label']} in {planning_time:.2f}s")
                break

            pddl_actions = [_action_summary(action) for action in plan]
            direct_actions = _translate_pddl_plan_to_direct_actions(plan)
            item["plan_found"] = True
            item["plan_length"] = len(pddl_actions)
            item["plan_actions"] = pddl_actions
            item["direct_actions"] = _direct_action_summary(direct_actions)
            print(f"[PDDL] Plan found in {planning_time:.2f}s")
            print("[PDDL->direct]")
            for action in direct_actions:
                print(f"  - {action}")

            if not execute:
                item["execution_success"] = None
                record["milestones"].append(item)
                record["completed_milestones"] += 1
                if milestone["kind"] == "lid":
                    lid_open = milestone["direct_goal_hint"] == "open"
                if scan_mode == "initial_prefix":
                    _shutdown_env(env)
                    env = None
                continue

            if not direct_actions:
                item["execution_success"] = False
                item["error_message"] = "PDDL plan produced no translatable direct actions."
                record["milestones"].append(item)
                if scan_mode == "initial_prefix":
                    _shutdown_env(env)
                    env = None
                break

            exec_started = time.time()
            execution_summary = _execute_direct_actions_directly(env, direct_actions)
            item["execution_time_s"] = round(time.time() - exec_started, 3)
            item["execution_summary"] = execution_summary
            item["execution_success"] = bool(execution_summary.get("success"))
            record["milestones"].append(item)

            if not item["execution_success"]:
                item["error_message"] = execution_summary.get("failure_reason") or "Direct execution failed."
                print(f"[STOP] Execution failed: {item['error_message']}")
                break

            record["completed_milestones"] += 1
            if milestone["kind"] == "lid":
                lid_open = milestone["direct_goal_hint"] == "open"
            if scan_mode == "initial_prefix":
                _shutdown_env(env)
                env = None

        record["total_milestones"] = len(milestones)
        record["status"] = "passed" if record["completed_milestones"] == len(milestones) else "stopped"
        if scan_mode == "sequential" and not execute:
            record["known_limitations"].append(
                "sequential mode without --execute only carries lid-open/lid-closed symbolically; object placements are not physically advanced."
            )
        if scan_mode == "initial_prefix":
            record["known_limitations"].append(
                "initial_prefix mode tests cumulative final-state reachability from a fresh initial scene at every milestone; it does not prove the exact GT ordering occurred."
            )
    except Exception as exc:
        record["error_message"] = str(exc)
        print(f"[ERROR] {exc}")
    finally:
        record["total_time_s"] = round(time.time() - started, 3)
        record["output_json_path"] = str(json_path)
        record["summary_path"] = str(txt_path)
        json_path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        txt_path.write_text(_render_gt_scan_summary(record), encoding="utf-8")
        _shutdown_env(env)
    return record


def _render_gt_scan_summary(record: Dict[str, Any]) -> str:
    lines = [
        f"variant: {record.get('variant_id')}",
        f"task_family: {record.get('task_family')}",
        f"goal_mode: {record.get('goal_mode')}",
        f"status: {record.get('status')}",
        f"execution_enabled: {record.get('execution_enabled')}",
        f"completed_milestones: {record.get('completed_milestones')}/{record.get('total_milestones')}",
        f"total_time_s: {record.get('total_time_s')}",
        f"max_time_s: {record.get('max_time_s')}",
        f"max_planner_time_s: {record.get('max_planner_time_s')}",
        "",
        "milestones:",
    ]
    for item in record.get("milestones", []):
        lines.extend(
            [
                f"- {item.get('index')}. {item.get('label')}",
                f"  plan_found: {item.get('plan_found')}",
                f"  planning_time_s: {item.get('planning_time_s')}",
                f"  execution_success: {item.get('execution_success')}",
            ]
        )
        if item.get("direct_actions"):
            lines.append("  direct_actions: " + " | ".join(item.get("direct_actions", [])))
        if item.get("error_message"):
            lines.append(f"  error_message: {item.get('error_message')}")
        if item.get("pre_solve_stream_diagnostic"):
            lines.append(f"  pre_solve_stream_diagnostic: {json.dumps(item.get('pre_solve_stream_diagnostic'), default=str)}")
        if item.get("pre_solve_transfer_diagnostic"):
            lines.append(f"  pre_solve_transfer_diagnostic: {json.dumps(item.get('pre_solve_transfer_diagnostic'), default=str)}")
        if item.get("stream_diagnostic"):
            lines.append(f"  stream_diagnostic: {json.dumps(item.get('stream_diagnostic'), default=str)}")
    if record.get("error_message"):
        lines.extend(["", f"error_message: {record.get('error_message')}"])
    if record.get("known_limitations"):
        lines.extend(["", "known_limitations:"])
        lines.extend(f"- {item}" for item in record.get("known_limitations", []))
    return "\n".join(lines).rstrip() + "\n"


def run_trial(
    variant_id: str,
    goal_mode: str,
    max_time: float,
    max_planner_time: float,
    headless: bool,
    verbose: bool,
    execute: bool,
    live_masks: bool,
    scene_state_trace: bool,
    output_dir: Path | None,
    output_root: Path,
) -> Dict[str, Any]:
    variant = get_variant_spec(variant_id)
    env = None
    record: Dict[str, Any] = {
        "variant_id": variant.variant_id,
        "task_family": variant.task_family,
        "scene_path": variant.scene_path,
        "goal_mode": goal_mode,
        "max_time_s": float(max_time),
        "max_planner_time_s": float(max_planner_time),
        "headless": bool(headless),
        "execution_enabled": bool(execute),
        "execution_success": None,
        "plan_found": False,
        "status": "failed",
    }
    json_path, txt_path = _output_paths(variant.variant_id, goal_mode, output_dir, output_root)
    started = time.time()
    try:
        env, get_stream_map = _configure_grill_variant(variant.variant_id, headless=headless)
        problem, problem_info = _build_problem(env, get_stream_map, variant.variant_id, goal_mode=goal_mode)
        record.update(problem_info)

        print("=" * 72)
        print(f"PURE PDDLSTREAM TRIAL: {variant.variant_id} ({goal_mode})")
        print("=" * 72)
        print(f"Scene: {variant.scene_path}")
        print(f"Max planning time: {max_time:.1f}s")
        print("Goals:")
        for fact in problem_info["goal_facts"]:
            print(f"  {fact}")
        print("Solving...")

        solve_started = time.time()
        plan, cost, evaluations = solve(
            problem,
            algorithm="binding",
            verbose=bool(verbose),
            max_time=float(max_time),
            max_iterations=max(1, int(max(1.0, max_time) // max(1.0, max_planner_time)) + 1),
            max_planner_time=float(max_planner_time),
            unit_costs=True,
        )
        planning_time = time.time() - solve_started

        record["planning_time_s"] = round(planning_time, 3)
        record["cost"] = None if cost is None else _jsonable(cost)
        record["evaluation_count"] = None if evaluations is None else len(evaluations)
        if plan is None:
            record["plan_found"] = False
            record["plan_length"] = 0
            record["plan_actions"] = []
            record["direct_actions"] = []
            record["error_message"] = "No PDDLStream plan found within max_time."
            print(f"[FAILURE] No plan found in {planning_time:.2f}s")
        else:
            actions = [_action_summary(action) for action in plan]
            direct_actions = _translate_pddl_plan_to_direct_actions(plan)
            record["plan_found"] = True
            record["plan_length"] = len(actions)
            record["plan_actions"] = actions
            record["direct_actions"] = _direct_action_summary(direct_actions)
            record["status"] = "planned"
            print(f"[SUCCESS] Plan found in {planning_time:.2f}s, length={len(actions)}, cost={cost}")
            for action in actions:
                print(f"  - {action['name']}")
            print("Translated direct actions:")
            for action in direct_actions:
                print(f"  - {action}")

            if execute:
                if not direct_actions:
                    record["execution_success"] = False
                    record["error_message"] = "PDDL plan produced no translatable direct actions."
                    record["status"] = "failed"
                else:
                    exec_started = time.time()
                    execution_summary = _execute_direct_actions(
                        env=env,
                        variant_id=variant.variant_id,
                        goal_text=f"Execute pure PDDL translated plan for {variant.variant_id}.",
                        direct_actions=direct_actions,
                        headless=headless,
                        live_masks=live_masks,
                        scene_state_trace=scene_state_trace,
                    )
                    record["execution_time_s"] = round(time.time() - exec_started, 3)
                    record["execution_summary"] = execution_summary
                    record["execution_success"] = bool(execution_summary.get("success"))
                    record["status"] = "passed" if record["execution_success"] else "execution_failed"
    except Exception as exc:
        record["error_message"] = str(exc)
        record["planning_time_s"] = round(time.time() - started, 3)
        print(f"[ERROR] {exc}")
    finally:
        record["total_time_s"] = round(time.time() - started, 3)
        record["output_json_path"] = str(json_path)
        record["summary_path"] = str(txt_path)
        json_path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        txt_path.write_text(_render_summary(record), encoding="utf-8")
        try:
            if env is not None:
                env.pr.stop()
                env.pr.shutdown()
        except Exception:
            pass
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a pure PDDLStream grill trial.")
    parser.add_argument("--variant", required=True, choices=["G1", "G2", "G3"], help="Grill variant.")
    parser.add_argument(
        "--goal-mode",
        default="recipe_proxy",
        choices=["recipe_proxy", "final_regions", "open_only"],
        help="PDDL goal to test. recipe_proxy is the closest current cooking-task proxy.",
    )
    parser.add_argument("--max-time", type=float, default=120.0, help="PDDLStream solve timeout in seconds.")
    parser.add_argument(
        "--max-planner-time",
        type=float,
        default=8.0,
        help="Per FastDownward optimistic-search attempt timeout in seconds.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print verbose PDDLStream solver output.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the PDDL-translated direct actions through the same pipeline executor/failure checks.",
    )
    parser.add_argument(
        "--gt-scan",
        action="store_true",
        help="Incrementally test how far PDDL can plan/execute the canonical GT macro sequence.",
    )
    parser.add_argument(
        "--gt-scan-mode",
        default="initial_prefix",
        choices=["initial_prefix", "sequential"],
        help=(
            "How --gt-scan builds each milestone. initial_prefix solves each cumulative GT prefix "
            "from a fresh initial scene. sequential solves the next milestone after prior milestones; "
            "use with --execute when you want the simulator state to carry forward."
        ),
    )
    parser.add_argument(
        "--skip-lid-stream-precheck",
        action="store_true",
        help="Do not directly probe open/close lid trajectory streams before lid GT milestones.",
    )
    parser.add_argument(
        "--skip-transfer-stream-precheck",
        action="store_true",
        help="Do not directly probe pick/place geometry streams before transfer GT milestones.",
    )
    parser.add_argument("--no-live-masks", action="store_true", help="Disable the separate live segmentation window.")
    parser.add_argument("--scene-state-trace", action="store_true", help="Print scene-state snapshots around execution checks.")
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--gui", action="store_true", help="Run with simulator GUI.")
    display.add_argument("--headless", action="store_true", help="Run without simulator GUI.")
    parser.add_argument("--output-dir", default="", help="Optional output directory.")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="Root for auto-created output folders.")
    args = parser.parse_args()

    if args.gt_scan:
        record = run_gt_scan(
            variant_id=args.variant,
            max_time=args.max_time,
            max_planner_time=args.max_planner_time,
            headless=bool(args.headless),
            verbose=bool(args.verbose),
            execute=bool(args.execute),
            scan_mode=args.gt_scan_mode,
            lid_stream_precheck=not args.skip_lid_stream_precheck,
            transfer_stream_precheck=not args.skip_transfer_stream_precheck,
            output_dir=Path(args.output_dir) if args.output_dir else None,
            output_root=Path(args.output_root),
        )
    else:
        record = run_trial(
            variant_id=args.variant,
            goal_mode=args.goal_mode,
            max_time=args.max_time,
            max_planner_time=args.max_planner_time,
            headless=bool(args.headless),
            verbose=bool(args.verbose),
            execute=bool(args.execute),
            live_masks=not args.no_live_masks,
            scene_state_trace=bool(args.scene_state_trace),
            output_dir=Path(args.output_dir) if args.output_dir else None,
            output_root=Path(args.output_root),
        )
    print(json.dumps(record, indent=2, default=str))


if __name__ == "__main__":
    main()
