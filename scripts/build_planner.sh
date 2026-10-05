#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cmake -S "$ROOT/pddlstream/downward/src" -B "$ROOT/pddlstream/downward/builds/release" \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS=-Wno-template-body
python "$ROOT/pddlstream/downward/build.py" release -j2
