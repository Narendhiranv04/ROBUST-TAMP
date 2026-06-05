#!/usr/bin/env python3
"""Run a full grill GT debug sequence with phone as the non-target object."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


THIS_DIR = Path(__file__).resolve().parent
ORCHESTRATOR_PATH = THIS_DIR / "ground_truth_orchestrator_variation1 copy.py"
SCENE_BY_VARIANT = {
    "G1": THIS_DIR / "grill.variation1.ttt",
    "G3": THIS_DIR / "grill.variation3.ttt",
}


def _load_orchestrator(scene_path: Path, headless: bool, open_replay_variant: str):
    os.environ["GRILL_ALLOW_SCENE_OVERRIDE"] = "True"
    os.environ["GRILL_SCENE_FILE_OVERRIDE"] = str(scene_path)
    os.environ["GRILL_SCENE_FILE"] = str(scene_path)
    os.environ["HEADLESS"] = "True" if headless else "False"
    os.environ["COPPELIASIM_HEADLESS"] = "1" if headless else "0"
    os.environ["GRILL_PRESERVE_SCENE_LID_POSE"] = "False"
    os.environ["GRILL_LID_CLOSED_ANGLE"] = "1.047198"
    os.environ["GRILL_LID_OPEN_ANGLE"] = "-0.261799"
    os.environ["GRILL_FORCE_MIN_OPEN_TRAVEL"] = "False"
    os.environ.setdefault("GRILL_OPEN_REPLAY_JOINT_TOL", "0.12")
    os.environ["GRILL_OPEN_REPLAY_VARIANT"] = open_replay_variant

    spec = importlib.util.spec_from_file_location("grill_gt_g1_phone_full_debug", ORCHESTRATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load orchestrator from {ORCHESTRATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_call(label: str, fn, default: Any = None) -> Any:
    try:
        return fn()
    except Exception as exc:
        if default is not None:
            return default
        return {"error": f"{label}: {exc}"}


def _object_report(gt, env, object_name: str, target_region: str) -> Optional[Dict[str, Any]]:
    obj = env.get_object(object_name)
    if obj is None:
        return None
    return {
        "name": _safe_call("get_name", obj.get_name),
        "pose": _safe_call("get_pose", obj.get_pose),
        "position": _safe_call("get_position", obj.get_position),
        "quaternion": _safe_call("get_quaternion", obj.get_quaternion),
        "world_bounds": _safe_call("world_bounds", lambda: gt._get_world_bounds(env, obj)),
        "in_target_region": _safe_call(
            "in_target_region",
            lambda: gt._is_in_region(env, obj, target_region, tol_xy=0.05, tol_z=0.08),
        ),
        "is_grasped": _safe_call("is_grasped", lambda: gt._target_is_grasped(env, obj)),
    }


def _target_region_for(object_name: str, non_target_object: str) -> str:
    if object_name == non_target_object:
        return "table"
    if object_name == "plate":
        return "plate_boundary"
    return "plate-top"


def _tracked_report(gt, env, object_names, non_target_object: str) -> Dict[str, Any]:
    return {
        name: _object_report(gt, env, name, _target_region_for(name, non_target_object))
        for name in object_names
    }


def _shutdown_env(env) -> None:
    pr = getattr(env, "pr", None)
    if pr is None:
        return
    try:
        pr.stop()
    except Exception:
        pass
    try:
        pr.shutdown()
    except Exception:
        pass


def _go_home(gt, env, pr) -> None:
    try:
        gt.go_home(env, pr)
    except Exception as exc:
        print(f"[full-g1-phone] go_home warning: {exc}")


def _run_lid(gt, env, pr, *, direction: str, label: str) -> bool:
    ok = gt.run_grill_lid_motion_framework(env, pr, direction=direction, task_name=label)
    _go_home(gt, env, pr)
    return bool(ok)


def _run_transfer(
    gt,
    env,
    pr,
    *,
    obj_name: str,
    region: str,
    label: str,
    is_plate: bool = False,
    slot_idx: int = 0,
    slot_count: int = 1,
) -> bool:
    obj = env.get_object(obj_name)
    if obj is None:
        print(f"[full-g1-phone] missing object: {obj_name}")
        return False
    region_for_pose = "plate_boundary" if region == "serving_area" else region
    pose = gt._region_slot_pose(env, obj, region_for_pose, slot_idx=slot_idx, slot_count=slot_count)
    ok = gt.run_pick_place_framework(
        env,
        pr,
        obj_name=obj_name,
        target_region=region,
        task_name=label,
        is_plate=is_plate,
        target_pose=pose,
    )
    _go_home(gt, env, pr)
    return bool(ok)


def run_full_sequence(args: argparse.Namespace) -> Dict[str, Any]:
    scene_path = args.scene_path or SCENE_BY_VARIANT[args.variant]
    open_replay_variant = args.open_replay_variant or "G2"
    gt = _load_orchestrator(scene_path, headless=not args.gui, open_replay_variant=open_replay_variant)
    env = gt.ENV
    pr = env.pr
    start = datetime.now()

    if args.variant == "G1":
        steps = [
        ("open_initial", lambda: _run_lid(gt, env, pr, direction="open", label="G1 phone full: open grill")),
        (
            "phone_to_table",
            lambda: _run_transfer(
                gt,
                env,
                pr,
                obj_name=args.object,
                region="table",
                label=f"G1 phone full: {args.object} -> table",
            ),
        ),
        (
            "chicken_to_grill",
            lambda: _run_transfer(
                gt,
                env,
                pr,
                obj_name="chicken",
                region="grill-top",
                label="G1 phone full: chicken -> grill",
            ),
        ),
        ("close_grill", lambda: _run_lid(gt, env, pr, direction="close", label="G1 phone full: close grill")),
        (
            "plate_to_serving_area",
            lambda: _run_transfer(
                gt,
                env,
                pr,
                obj_name="plate",
                region="plate_boundary",
                label="G1 phone full: plate -> serving area",
                is_plate=True,
            ),
        ),
        ("open_after_cook", lambda: _run_lid(gt, env, pr, direction="open", label="G1 phone full: reopen grill")),
        (
            "chicken_to_plate",
            lambda: _run_transfer(
                gt,
                env,
                pr,
                obj_name="chicken",
                region="plate-top",
                label="G1 phone full: chicken -> plate",
            ),
        ),
        ]
        tracked_objects = [args.object, "chicken", "plate"]
    else:
        steps = [
            ("open_initial", lambda: _run_lid(gt, env, pr, direction="open", label="G3 phone full: open grill")),
            (
                "phone_to_table",
                lambda: _run_transfer(
                    gt,
                    env,
                    pr,
                    obj_name=args.object,
                    region="table",
                    label=f"G3 phone full: {args.object} -> table",
                ),
            ),
            (
                "plate_to_serving_area",
                lambda: _run_transfer(
                    gt,
                    env,
                    pr,
                    obj_name="plate",
                    region="plate_boundary",
                    label="G3 phone full: plate -> serving area",
                    is_plate=True,
                ),
            ),
            (
                "inside_steak_to_plate",
                lambda: _run_transfer(
                    gt,
                    env,
                    pr,
                    obj_name="steak",
                    region="plate-top",
                    label="G3 phone full: steak -> plate",
                    slot_idx=0,
                    slot_count=3,
                ),
            ),
            (
                "chicken_to_grill",
                lambda: _run_transfer(
                    gt,
                    env,
                    pr,
                    obj_name="chicken",
                    region="grill-top",
                    label="G3 phone full: chicken -> grill",
                    slot_idx=0,
                    slot_count=2,
                ),
            ),
            (
                "steak1_to_grill",
                lambda: _run_transfer(
                    gt,
                    env,
                    pr,
                    obj_name="steak1",
                    region="grill-top",
                    label="G3 phone full: steak1 -> grill",
                    slot_idx=1,
                    slot_count=2,
                ),
            ),
            ("close_grill", lambda: _run_lid(gt, env, pr, direction="close", label="G3 phone full: close grill")),
            ("open_after_cook", lambda: _run_lid(gt, env, pr, direction="open", label="G3 phone full: reopen grill")),
            (
                "chicken_to_plate",
                lambda: _run_transfer(
                    gt,
                    env,
                    pr,
                    obj_name="chicken",
                    region="plate-top",
                    label="G3 phone full: chicken -> plate",
                    slot_idx=1,
                    slot_count=3,
                ),
            ),
            (
                "steak1_to_plate",
                lambda: _run_transfer(
                    gt,
                    env,
                    pr,
                    obj_name="steak1",
                    region="plate-top",
                    label="G3 phone full: steak1 -> plate",
                    slot_idx=2,
                    slot_count=3,
                ),
            ),
        ]
        tracked_objects = [args.object, "steak", "chicken", "steak1", "plate"]

    report: Dict[str, Any] = {
        "created_at": start.isoformat(timespec="seconds"),
        "variant": args.variant,
        "scene_path": str(scene_path),
        "object_name": args.object,
        "open_replay_variant": open_replay_variant,
        "open_replay_path": str(THIS_DIR / "precomputed_paths" / f"grill_open_{open_replay_variant}.json"),
        "success": False,
        "failure_reason": None,
        "steps": [],
        "final_objects": {},
    }

    try:
        for index, (name, fn) in enumerate(steps, start=1):
            before = _tracked_report(gt, env, tracked_objects, args.object)
            ok = bool(fn())
            after = _tracked_report(gt, env, tracked_objects, args.object)
            report["steps"].append({
                "index": index,
                "name": name,
                "success": ok,
                "before": before,
                "after": after,
            })
            if not ok and args.stop_on_failure:
                report["failure_reason"] = f"step_failed:{name}"
                break

        report["final_objects"] = _tracked_report(gt, env, tracked_objects, args.object)
        report["success"] = bool(report["steps"]) and all(step["success"] for step in report["steps"])
        if not report["success"] and report["failure_reason"] is None:
            failed = [step["name"] for step in report["steps"] if not step["success"]]
            report["failure_reason"] = "failed_steps:" + ",".join(failed)
    except Exception as exc:
        report["failure_reason"] = str(exc)
    finally:
        report["execution_time_s"] = (datetime.now() - start).total_seconds()
        _shutdown_env(env)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full grill GT debug sequence with phone non-target.")
    parser.add_argument("--variant", choices=sorted(SCENE_BY_VARIANT), default="G1")
    parser.add_argument("--scene-path", type=Path, default=None)
    parser.add_argument("--object", default="phone")
    parser.add_argument("--open-replay-variant", choices=("G1", "G2", "G3"), default="")
    parser.add_argument("--gui", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--stop-on-failure", action="store_true", default=True)
    parser.add_argument("--continue-on-failure", action="store_false", dest="stop_on_failure")
    args = parser.parse_args()
    if args.report is None:
        args.report = Path(f"outputs/{args.variant.lower()}_phone_full_debug.json")

    report = run_full_sequence(args)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
