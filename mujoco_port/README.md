# MuJoCo port

Runs the whole TAMP-PDDL stack (kitchen K1–K3, grill G1–G3 and the legacy grill
scenes, GT orchestrators, `llm_pipeline` executor / trial runner, segmentation)
on MuJoCo instead of CoppeliaSim, with no changes to the task code.

## How it works

```
CoppeliaSim .ttt ──extract_scene.py──▶ extracted/<scene>/ ──build_mjcf.py──▶ scenes/<scene>/scene.xml
                   (real CoppeliaSim)   (json + npz + png)                     + scene_meta.json
```

* `shim/pyrep/` is a drop-in `pyrep` package. PyRep's own Python layer
  (`Object`, `Shape`, `Joint`, `Arm`, `Gripper`, … — MIT, see
  `LICENSE_PyRep.txt`) is vendored unchanged; only `backend/sim.py` (the
  CoppeliaSim C-API surface) and `pyrep.py` are re-implemented on MuJoCo
  (`backend/_world.py`, `_kin.py`, `_render.py`). So gripper actuation, IK
  result ranking, `get_path` fallbacks and every exception type behave exactly
  as with CoppeliaSim.
* `PyRep.launch("task1_variation1.ttt")` loads `scenes/task1_variation1/`
  (dots in names become underscores, e.g. `grill.variation1.ttt` →
  `grill_variation1`). CoppeliaSim handles and names are preserved, so
  handle-encoded segmentation masks and name lookups work unchanged.
* Backend selection: `sim_backend.py` (repo root) activates the shim when
  `SIM_BACKEND=mujoco`; the modules that import `pyrep` import it first.
  Default (unset) is the original CoppeliaSim backend.

## Running

```sh
. mujoco_port/activate_mujoco_env.sh          # SIM_BACKEND=mujoco + PYTHONPATH
python llm_pipeline/debug_execution.py --variant K1 --headless     # one GT replay
python mujoco_port/tools/run_gt_matrix.py --variants K1 K2 K3 G1 G2 G3 --trials 3 --jobs 2
python -m llm_pipeline.trial_runner --variant G2 ... --headless    # model trials, as before
```

`pddlstream` must be available (git submodule with FastDownward built, or
`PDDLSTREAM_DIR=/path/to/pddlstream`).

**The `pddlstream` submodule can be empty.** In a checkout where `git submodule update`
was never run, `pddlstream/` exists but is empty, and every import of
`llm_pipeline.executor` fails with `No module named 'pddlstream.algorithms'` (six test
modules then fail to collect). Either initialize the submodule
(`git submodule update --init pddlstream`, then build FastDownward) or point
`PDDLSTREAM_DIR` at a complete copy before sourcing the env script, e.g.

```sh
export PDDLSTREAM_DIR=$HOME/.cache/tamp_pddl/TAMP-PDDL/pddlstream
. mujoco_port/activate_mujoco_env.sh
```

## Tests

```sh
export PDDLSTREAM_DIR=...            # see above
python -m pytest llm_pipeline/tests diagnostics/tests mujoco_port/tests
```

The root `conftest.py` puts the MuJoCo `pyrep` shim first on `sys.path` before any test is
collected (unless `SIM_BACKEND=coppelia`), so the simulator tests (`mujoco_port/tests`)
pass in the full suite with or without the env script. Without it, a pipeline test could
import the CoppeliaSim `pyrep` from site-packages first and the simulator tests skipped
themselves. `--gui` opens a MuJoCo passive viewer
(`MUJOCO_SHIM_VIEWER=0` disables it). Offscreen rendering uses `MUJOCO_GL`
(`egl` headless, `glfw` with a display, `osmesa` fallback).

Run parallel jobs from separate working directories: pddlstream writes
`./temp/output.sas`, so concurrent runs in one cwd corrupt each other
(`run_gt_matrix.py` and `tools/run_partial.py` already do this).

## Fidelity model (CoppeliaSim semantics that are emulated)

| CoppeliaSim | MuJoCo port |
|---|---|
| Scene geometry, poses, joint frames | Extracted exactly; Panda FK matches CoppeliaSim to < 0.001 mm / 0.0001° (`tools/validate_fk.py`) |
| Pure shapes / convex meshes / compounds | Exact primitives, convex meshes, one geom per compound component; concave respondables (plate) via CoppeliaSim's V-HACD |
| Respondable masks (local/global bytes) | `<exclude>` pairs (e.g. `box_base`/`box_lid`) |
| Dynamic / static, respondable, collidable, model properties | Runtime flags; static shapes rigidly follow their (logical) parent |
| `set_parent`, gripper `grasp()` (attach to force sensor) | Logical parent tree; grasped / static objects follow their parent; dynamic children of passive joints hang on a weld to a native hinge rotor (re-anchored on release) |
| Joint motors (force mode: position P-law, velocity, lock, passive) | Force-limited position servos with the same reference laws; out-of-interval joints are not snapped back |
| Only dynamic shapes carry mass | Static (visual) shapes contribute no inertia; the Panda totals 7.1 kg as in CoppeliaSim |
| `set_joint_positions` resets link dynamics | A teleported arm (and its fingers) is pinned for that step; otherwise joints are force-limited servos (87/12 N·m, P-law targets) with gravity compensation, gains sized from the *effective* joint inertia |
| Grasped objects are rigidly attached | Closing fingers stall at the attached object's surface until the next gripper command |
| Weak (ERP) penetration correction of teleported / robot contacts | Robot contacts and contacts of teleported joint subtrees are compliant; e.g. the grill lid holds while the gripper brushes it, as in CoppeliaSim |
| `simCheckCollision` / `simCheckDistance` / proximity sensors | `mj_geomDistance` on the shapes' own geometry; `Panda_arm` collection = live Panda tree; explicit-entity proximity checks ignore detectable flags (verified vs CoppeliaSim) |
| IK (`simGetConfigForTipPose`, `generateIkPath`), OMPL | Batched damped-least-squares IK over the exact chain, Cartesian linear paths, RRT-Connect |
| Vision sensors, colour-coded render mode | MuJoCo cameras with the same FOV / orientation / flip; colour-coded masks encode CoppeliaSim handles |
| Scene lights, textures | Same lights and textures; the overhead lamp casts shadows, the others are fills; textured surfaces are matte; a gradient skybox fills gaps where a scene has no wall; the floor's coplanar black backing quad (which z-fights in MuJoCo) is dropped. These are visual-only (RGB images); physics and segmentation are unaffected |

Environment switches (defaults are the validated configuration):
`MUJOCO_SHIM_KINEMATIC_ARM=1` (always-kinematic arm),
`MUJOCO_SHIM_SOFT_TELEPORT_ROBOT=0` (stiff robot contacts),
`MUJOCO_SHIM_SOFT_KINEMATIC=0` (stiff teleported-joint contacts),
`MUJOCO_SHIM_SOFT_FOLLOWERS=1`, `MUJOCO_SHIM_SOFT_RELEASE=1` (experimental),
`MUJOCO_SHIM_RRT_TIME` (seconds), `MUJOCO_SCENE_ROOT` (scene directory).

Not supported (raise the same `RuntimeError` CoppeliaSim uses for a failed
call): creating/removing/copying objects at runtime, scripts, paths, octrees,
scene saving.

## Validation

`python mujoco_port/tools/run_gt_matrix.py --trials 3 --jobs 2` replays the GT
action sequences of all six variants (`llm_pipeline/debug_sequences/*_gt_as_is.txt`)
through `DirectPrimitiveExecutor` and the unmodified GT orchestrators. Latest run
(`results/gt_matrix/summary.json`): K1, K2, K3, G1, G2, G3 each 3/3; all 252 GT
actions completed with every GT validation passing (lid angle errors ≤ 0.005 rad).
Keep `--jobs` small: every run is a full physics + rendering process.

## Regenerating scenes

Needs CoppeliaSim + real PyRep (not the shim):

```sh
export COPPELIASIM_ROOT=~/CoppeliaSim LD_LIBRARY_PATH=~/CoppeliaSim QT_QPA_PLATFORM=offscreen
python mujoco_port/tools/extract_scene.py grill_task2/grill.variation2.ttt
python mujoco_port/tools/build_mjcf.py grill_variation2     # or --all
python mujoco_port/tools/validate_fk.py grill_variation2
```

`build_mjcf.py` only needs the extracted bundle, so MJCF changes do not need
CoppeliaSim. Movable-object naming rules and runtime-reparentable shapes are
configured at the top of `build_mjcf.py`.

## Reference tools

* `tools/record_coppelia_settle.py` – object drift over N steps in CoppeliaSim
  (e.g. `mug3` tips in the cupboard in both simulators).
* `tools/probe_proximity.py`, `tools/probe_distance.py`,
  `tools/probe_segmentation.py` – run on either backend for side-by-side checks.
