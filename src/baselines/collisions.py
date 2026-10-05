"""The bodies the robot collides with while our planner refines an action (grasp, IK, motion
checks), for the baselines whose methods feed collisions back: VLM-TAMP's reprompt ("The robot has
collided with these objects: ...") and OWL-TAMP's plan modification after a failed operator.

The MuJoCo shim answers every collision query with ``World._geom_pairs_colliding``; while recording,
each colliding geometry pair with one side on the robot (a ``Panda`` body) is counted under the
other side's scene object, reported by its planner name.
"""

from __future__ import annotations

import contextlib
from collections import Counter
from typing import Iterable, List

ROBOT_PREFIX = 'Panda'


@contextlib.contextmanager
def recorded_collisions():
    """Yields a Counter: planner object name -> colliding geometry pairs with the robot."""
    hits: Counter = Counter()
    try:
        from pyrep.backend import sim
        world = sim._w()
    except Exception:
        yield hits
        return
    original = world._geom_pairs_colliding

    def name_of(geom: int):
        handle = world.geom_handle.get(int(geom))
        return world.objs[handle].name if handle is not None and handle in world.objs else None

    def recording(A, B, first_only=True, margin=0.0):
        pairs = original(A, B, first_only, margin)
        for ga, gb, _ in pairs:
            a, b = name_of(ga), name_of(gb)
            if a is None or b is None:
                continue
            robot_a, robot_b = a.startswith(ROBOT_PREFIX), b.startswith(ROBOT_PREFIX)
            if robot_a != robot_b:
                hits[b if robot_a else a] += 1
        return pairs

    world._geom_pairs_colliding = recording
    try:
        yield hits
    finally:
        world._geom_pairs_colliding = original


def collision_bodies(hits: Counter, exclude: Iterable[str] = ()) -> List[str]:
    """The collided bodies by planner name (most frequent first), without the excluded ones."""
    from llm_pipeline.object_aliases import canonical_object_name

    out, excluded = [], {canonical_object_name(x) for x in exclude}
    for scene_name, _ in hits.most_common():
        name = canonical_object_name(scene_name)
        if name not in excluded and name not in out:
            out.append(name)
    return out


__all__ = ['recorded_collisions', 'collision_bodies']
