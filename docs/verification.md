# Release verification

This report separates logic checks, simulation execution, preserved-record aggregation and fresh model inference. Validation outputs are stored privately outside the release's reference records.

## Completed checks

- Recorded simulation requirements installed into a new isolated Python 3.13 environment. No shared environment was modified. MuJoCo 3.10.0, NumPy 2.4.0 and SciPy 1.16.3 match the experiment pins.
- Unit/integration suite: **425 passed, 1 skipped** at the latest check. Tests cover observation memory/occlusion, IF decisions, parallel eligibility and dependency propagation, corrective parsing, urgent/deferred anchors, remaining order, NO_ACTIONS acknowledgment, failure recovery, termination versus scoring, baseline interfaces, explicit ablation settings, duplicate/missing metric inputs and configuration compatibility. The skipped historical phase-7b check requires an absent development-results directory.
- All **14 final scene checks passed**: scene loading, expected objects, stable heights, initial occlusion, regions and placement-area overlap.
- All **24 retained MJCF models** compiled before and after asset deduplication with identical numerical arrays, excluding filename buffers/offsets. Mesh/texture bytes are unchanged.
- Ground-truth G0 trial: scored success through the actual MuJoCo execution pipeline. Full one-seed variant matrix and baseline plumbing outcomes are listed in the final execution summary below.
- Table 5: **70/70 available aggregate cells match**, using 950 unique scored trials. Ten latency cells are paper transcriptions, because final per-call logs are unavailable locally.
- Table 2: **16/16 kitchen/grill ablation rows match**, including insertion, unnecessary replans and idle time. Table 4: **14/14 variant rows match** every reported per-variant metric.
- Both HTML animations opened in a browser and supported GIF previews rendered. Submission-author text scans cover source/documentation/records and decoded embedded HTML resources. Image EXIF/XMP/C2PA metadata was removed without changing decoded image pixels.

## Final execution summary

| Check | Outcome |
|---|---|
| Independent relocated copy: planner build, dependency/resource doctor, tests | Passed; 425 tests passed, one historical-results check skipped |
| Relocated copy: G0 oracle, pinned environment | Evaluated success; all six ground-truth subtasks completed |
| Oracle, all 14 final variants, seed 0 | 14/14 evaluated successes |
| Mocked baseline plumbing, G0 seed 0 | VLM-TAMP, OWL-TAMP and Inner Monologue succeeded; EPoG terminated normally but failed the cooking predicate |
| Video recording, G0, exact pinned simulation environment | Evaluated success; 2,992 frames, 59.8 seconds, 2.2 MB; renderer closed cleanly |
| GPU inference | Unavailable; no fresh model or ablation results claimed |

The 14-variant oracle matrix and mocked baseline checks used the temporary validation environment described below. The relocated build/tests and final video used the exact pinned installation. Mocked planning checks exercise interfaces and execution, not baseline scientific performance. The EPoG mock's task failure is preserved as a scored failure, not hidden as an infrastructure exclusion. These smoke checks do not reproduce the full seed matrix.

## Baseline and existing-environment findings

The initial copied tree failed test collection because PDDLStream source was absent. After restoring the recorded submodule revision and building it, the source suite was operational. A test that initially appeared to be a prompt-snapshot failure was another dependency-import failure; no prompt or golden snapshot was changed to make it pass.

The historical planner source failed with modern CMake and GCC's unused-template diagnostic. The release build script supplies compatibility flags; no planner algorithm was replaced. The original video recorder overwrote an existing output directory and left an EGL renderer for interpreter teardown. Release packaging now refuses existing video outputs and closes the recorder explicitly. Scientific controller logic is unchanged.

A temporary validation environment made from independent copies of installed packages also passed before the exact pinned environment finished installing. Its package list and runs are recorded privately; it is not mislabelled as the exact historical environment. Both used the same pinned MuJoCo/NumPy/SciPy versions.

## Not verified here

- GPU-backed ROBUST-TAMP, component-ablation and baseline trials. No NVIDIA tooling was available, no inference endpoint was configured, and localhost:8000 refused connection. No remote credentials were inferred and no existing GPU jobs were interrupted.
- A fresh 10-seed experimental reproduction or numerical equivalence across GPUs, drivers and inference engines.
- Missing final planner-comparison records and final Table 5 median latency aggregation.
- Real-robot operation or reproduction. No real robot was launched.
- Original scene-asset/prompt redistribution rights and the project's licensing choice.

The [GPU guide](models.md) and [experiment guide](reproduction.md) provide the remaining commands. A health check, an oracle run, a mocked planner or matching historical tables is not a GPU reproduction.

## Sharing status

The technical artifacts are prepared for anonymous review, subject to the execution summary and limitations above. Treat this as a **release candidate**, pending the authors' project-license and source-asset redistribution decisions. Nothing was published or pushed.
