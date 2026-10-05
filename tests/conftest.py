"""pytest setup for the whole repository.

The MuJoCo ``pyrep`` shim is put first on ``sys.path`` before any test module is
collected, so the pipeline tests and the simulator tests (``mujoco_port/tests``) import
the same ``pyrep`` whatever the collection order. Without this, a pipeline test could
import the CoppeliaSim ``pyrep`` from site-packages first (via
``segmentation_object_detector``) and the simulator tests would skip themselves.
``SIM_BACKEND=coppelia`` keeps the CoppeliaSim backend.
"""

import os

os.environ.setdefault('SIM_BACKEND', 'mujoco')

import sim_backend  # noqa: E402

sim_backend.activate()
