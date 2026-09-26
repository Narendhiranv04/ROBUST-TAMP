#!/bin/sh
# Source from the repository root to run everything on the MuJoCo port:
#
#   . mujoco_port/activate_mujoco_env.sh
#   python llm_pipeline/debug_execution.py --variant K1 --headless
#
# No CoppeliaSim install is needed. `pyrep` resolves to mujoco_port/shim/pyrep,
# a MuJoCo-backed drop-in that loads the converted scenes in mujoco_port/scenes.

SELF_PATH="${BASH_SOURCE:-$0}"
[ -f "$SELF_PATH" ] || SELF_PATH="./mujoco_port/activate_mujoco_env.sh"
case "$SELF_PATH" in
    /*) SCRIPT_PATH="$SELF_PATH" ;;
    *) SCRIPT_PATH="$PWD/$SELF_PATH" ;;
esac
ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$SCRIPT_PATH")/.." && pwd)

# pddlstream: the git submodule, or an explicit override.
PDDLSTREAM_DIR="${PDDLSTREAM_DIR:-$ROOT_DIR/pddlstream}"
if [ ! -f "$PDDLSTREAM_DIR/pddlstream/__init__.py" ] && [ ! -f "$PDDLSTREAM_DIR/pddlstream/language/generator.py" ]; then
    echo "Warning: pddlstream sources not found at $PDDLSTREAM_DIR"
    echo "  Run 'git submodule update --init pddlstream' (and build FastDownward),"
    echo "  or export PDDLSTREAM_DIR=/path/to/pddlstream before sourcing this file"
    echo "  (see mujoco_port/README.md: the submodule directory can exist but be empty)."
fi

export SIM_BACKEND=mujoco
export TAMP_PDDL_ROOT="$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/mujoco_port/shim:$ROOT_DIR:$PDDLSTREAM_DIR${PYTHONPATH:+:$PYTHONPATH}"
export HEADLESS="${HEADLESS:-True}"

# Offscreen rendering backend for vision sensors / segmentation.
if [ -z "${MUJOCO_GL:-}" ]; then
    if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
        export MUJOCO_GL=glfw
    else
        export MUJOCO_GL=egl
    fi
fi

echo "Activated TAMP-PDDL MuJoCo backend"
echo "  SIM_BACKEND=$SIM_BACKEND  MUJOCO_GL=$MUJOCO_GL"
echo "  scenes: $ROOT_DIR/mujoco_port/scenes"
echo "  pddlstream: $PDDLSTREAM_DIR"
