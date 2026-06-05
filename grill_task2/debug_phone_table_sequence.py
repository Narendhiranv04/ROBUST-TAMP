#!/usr/bin/env python3
"""Debug the G1 sequence: open grill, then move a phone-like object to table."""

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
ROOT_DIR = THIS_DIR.parent
ORCHESTRATOR_PATH = THIS_DIR / "ground_truth_orchestrator_variation1 copy.py"
SCENE_BY_VARIANT = {
    "G1": THIS_DIR / "grill.variation1.ttt",
    "G2": THIS_DIR / "grill.variation2.ttt",
    "G3": THIS_DIR / "grill.variation3.ttt",
}


def _load_orchestrator(scene_path: Path, headless: bool):
    os.environ["GRILL_ALLOW_SCENE_OVERRIDE"] = "True"
    os.environ["GRILL_SCENE_FILE_OVERRIDE"] = str(scene_path)
    os.environ["GRILL_SCENE_FILE"] = str(scene_path)
    os.environ["HEADLESS"] = "True" if headless else "False"
    os.environ["COPPELIASIM_HEADLESS"] = "1" if headless else "0"
    # Match the curated grill-open replay convention. The saved
    # grill_open_G*.json paths open from the scene-authored closed pose
    # near +60 deg to the open pose near -15 deg.
    os.environ["GRILL_PRESERVE_SCENE_LID_POSE"] = "False"
    os.environ["GRILL_LID_CLOSED_ANGLE"] = "1.047198"
    os.environ["GRILL_LID_OPEN_ANGLE"] = "-0.261799"
    os.environ["GRILL_FORCE_MIN_OPEN_TRAVEL"] = "False"
    os.environ.setdefault("GRILL_OPEN_REPLAY_JOINT_TOL", "0.12")
    os.environ["GRILL_OPEN_REPLAY_VARIANT"] = os.environ.get("GRILL_OPEN_REPLAY_VARIANT", "G2")

    spec = importlib.util.spec_from_file_location("grill_gt_phone_debug", ORCHESTRATOR_PATH)
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


def _object_report(gt, env, obj, region_name: str) -> Optional[Dict[str, Any]]:
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
            lambda: gt._is_in_region(env, obj, region_name, tol_xy=0.05, tol_z=0.08),
        ),
        "is_grasped": _safe_call("is_grasped", lambda: gt._target_is_grasped(env, obj)),
    }


def _region_report(gt, env, region_name: str) -> Dict[str, Any]:
    region = gt._region_object(env, region_name)
    if region is None:
        return {"name": region_name, "found": False}
    return {
        "name": region_name,
        "found": True,
        "object_name": _safe_call("get_name", region.get_name),
        "position": _safe_call("get_position", region.get_position),
        "world_bounds": _safe_call("world_bounds", lambda: gt._get_world_bounds(env, region)),
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


def run_debug(args: argparse.Namespace) -> Dict[str, Any]:
    scene_path = args.scene_path or SCENE_BY_VARIANT[args.variant]
    gt = _load_orchestrator(scene_path=scene_path, headless=not args.gui)
    open_replay_variant = (args.open_replay_variant or "G2").strip().upper()
    os.environ["GRILL_OPEN_REPLAY_VARIANT"] = open_replay_variant
    env = gt.ENV
    pr = env.pr
    start = datetime.now()

    report: Dict[str, Any] = {
        "created_at": start.isoformat(timespec="seconds"),
        "variant_id": args.variant,
        "open_replay_variant": open_replay_variant,
        "open_replay_path": str(THIS_DIR / "precomputed_paths" / f"grill_open_{open_replay_variant}.json"),
        "scene_path": str(scene_path),
        "object_name": args.object,
        "target_region": args.target_region,
        "success": False,
        "open_success": False,
        "transfer_success": False,
        "final_region_success": False,
        "failure_reason": None,
        "target_pose": None,
        "target_region_report": None,
        "root_object_before": None,
        "object_before": None,
        "object_after_open": None,
        "object_after_transfer": None,
    }

    try:
        obj = env.get_object(args.object)
        if obj is None:
            report["failure_reason"] = f"object not found: {args.object}"
            return report

        root_obj = env.get_object(args.root_object) if args.root_object else None
        report["target_region_report"] = _region_report(gt, env, args.target_region)
        report["root_object_before"] = _object_report(gt, env, root_obj, args.target_region)
        report["object_before"] = _object_report(gt, env, obj, args.target_region)

        open_ok = gt.run_grill_lid_motion_framework(
            env,
            pr,
            direction="open",
            task_name=f"Debug: open grill before moving {args.object}",
        )
        report["open_success"] = bool(open_ok)
        report["object_after_open"] = _object_report(gt, env, obj, args.target_region)
        try:
            gt.go_home(env, pr)
        except Exception:
            pass

        if not open_ok:
            report["failure_reason"] = "open grill returned false"
            return report

        target_pose = gt._region_slot_pose(env, obj, args.target_region, slot_idx=0, slot_count=1)
        report["target_pose"] = list(target_pose)

        transfer_ok = gt.run_pick_place_framework(
            env,
            pr,
            obj_name=args.object,
            target_region=args.target_region,
            task_name=f"Debug: {args.object} -> {args.target_region}",
            is_plate=False,
            target_pose=target_pose,
        )
        report["transfer_success"] = bool(transfer_ok)
        try:
            gt.go_home(env, pr)
        except Exception:
            pass

        report["object_after_transfer"] = _object_report(gt, env, obj, args.target_region)
        report["final_region_success"] = bool(
            gt._is_in_region(env, obj, args.target_region, tol_xy=0.05, tol_z=0.08)
        )
        report["success"] = bool(report["open_success"] and report["transfer_success"] and report["final_region_success"])
        if not report["success"]:
            report["failure_reason"] = (
                f"open={report['open_success']}, "
                f"transfer={report['transfer_success']}, "
                f"final_region={report['final_region_success']}"
            )
    except Exception as exc:
        report["failure_reason"] = str(exc)
    finally:
        report["execution_time_s"] = (datetime.now() - start).total_seconds()
        _shutdown_env(env)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug opening G1 grill and moving phone to table.")
    parser.add_argument("--variant", choices=sorted(SCENE_BY_VARIANT), default="G1")
    parser.add_argument("--scene-path", type=Path, default=None)
    parser.add_argument("--object", default="phone", help="Object to move from the grill to the table.")
    parser.add_argument(
        "--root-object",
        default="phone_root",
        help="Optional parent/root object to report but not manipulate.",
    )
    parser.add_argument("--target-region", default="table")
    parser.add_argument(
        "--open-replay-variant",
        choices=sorted(SCENE_BY_VARIANT),
        default="",
        help="Use another variant's grill_open_G*.json replay while keeping the selected scene.",
    )
    parser.add_argument("--gui", action="store_true", help="Run CoppeliaSim with GUI.")
    parser.add_argument("--report", type=Path, default=None, help="Optional JSON report path.")
    args = parser.parse_args()

    report = run_debug(args)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
