# MuJoCo simulation backend

The `shim/pyrep` package maps the retained PyRep API onto MuJoCo. The evaluated controllers remain unchanged. `SIM_BACKEND=mujoco` selects this implementation; the portable release runner sets it automatically.

`scenes/` contains the 14 evaluated final variants and ten legacy scenes retained for regression coverage. Meshes/textures are deduplicated into `scenes/_assets/` by exact content hash; each scene XML references that local directory. No symlink or external checkout is needed. Every compiled numerical model array was compared before and after consolidation (excluding filename buffers/offsets); all 24 models were identical.

`extracted/*/scene.json` preserves the composition metadata used by variant checks. Source CoppeliaSim binaries and unused extraction/development tools are omitted; this release runs the converted scenes rather than promising source-scene regeneration.

Use the root [README](../README.md), [installation guide](../docs/installation.md), and [reproduction guide](../docs/reproduction.md). `tools/record_variant_video.py` records an oracle trajectory; `tools/record_trial_replay.py` replays recorded planner responses and is distinct from fresh inference. `tools/render_semantic_views.py` renders scene views. Legacy `tools/run_gt_matrix.py` supports controller regression; final-paper variants use `python -m robust_tamp run`.

Trial seeds drive pose perturbations, IK/RRT sampling and placement draws. Wall-time budgets still depend on hardware/load. Precomputed controller trajectories remain in `precomputed_paths/` at the root and in `grill_task2/precomputed_paths/`.

The PyRep MIT license is retained under `shim/pyrep/LICENSE_PyRep.txt`. Original scene-asset redistribution terms still require confirmation.
