# Installation and verification

Run commands from the release root. Linux x86-64 is the supported target. The simulation client needs Python 3.13, CMake, a C++ compiler, Mesa/EGL (or a working desktop OpenGL driver), and FFmpeg for video. It does not need model weights or CUDA. No real robot interface is provided.

## Simulation client

```sh
python3.13 -m venv .venv-sim
. .venv-sim/bin/activate
python -m pip install -r requirements-sim.txt
sh scripts/build_planner.sh
python -m robust_tamp doctor
python -m pytest -q
```

`requirements-sim.txt` preserves the recorded experiment environment, including MuJoCo 3.10.0, NumPy 2.4.0 (a yanked release retained deliberately), SciPy 1.16.3, Pillow 12.0.0 and OpenCV 5.0.0.93. PDDLStream and FastDownward source and their licenses are bundled. Building creates only `pddlstream/downward/builds/`. No submodule initialization or personal checkout is needed.

The planner build explicitly enables compatibility with modern CMake. GCC 16 rejects an unused template body in the bundled historical optional library; the build command suppresses that diagnostic without modifying the planner algorithm. Older compilers may ignore the unrecognized suppression flag.

`doctor` checks imports, model-independent resources, the planner binary and the release content manifest. It does not claim that the renderer or a full trial has succeeded. Run the oracle example next. For a machine without a display, `MUJOCO_GL=egl` is the default of the release runner. If your Mesa setup requires it, use `MUJOCO_GL=osmesa`; this requires the system OSMesa library. `--gui` enables a viewer on a configured desktop.

The content manifest replaces the old requirement for a clean Git checkout. Do not initialize Git merely to pass trial validation. After intentional research modifications, regenerate the manifest with `python scripts/freeze_release.py`; the resulting identity changes and is stored with new runs. Existing batches refuse to resume against changed content.

## Troubleshooting

- `No module named pddlstream…`: build the bundled planner and use the release root. The documented entry point configures its own subprocess import paths.
- `No module named mujoco/cv2/…`: activate the simulation environment and install its requirements.
- EGL/GL initialization error: check the system graphics driver; try OSMesa if installed. GUI sessions need a display.
- Server unavailable or wrong served name: use the GPU instructions and `doctor --endpoint …`. An infrastructure failure is not a scored task failure.
- `.run.lock` already exists: another process owns this output. If a crashed process left it, confirm that the recorded PID is no longer running before removing that lock. Use a different output directory otherwise.
- Out of GPU memory: stop only your own inference process, choose sufficient hardware, or explicitly lower concurrency. Hardware/context changes must be recorded; do not call a changed setting an exact reproduction.

See [verification](verification.md) for the environments actually tested for this release, distinct from the recorded historical pins.
