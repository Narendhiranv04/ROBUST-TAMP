"""3D Geometric utilities for symbolic scene state resolution."""

from __future__ import annotations
import numpy as np
from typing import Dict, Tuple, Optional

from llm_pipeline.region_geometry import is_inside_xy, resolve_region


def compute_dist(p1: Tuple[float, float, float], p2: Tuple[float, float, float]) -> float:
    """Compute Euclidean distance between two 3D points."""
    return float(np.linalg.norm(np.array(p1) - np.array(p2)))


class GeometricReasoner:
    """Consolidated 3D geometric reasoning for state and failure validation."""

    def __init__(self):
        pass

    def is_contained_3d(self, obj_pose, region_name: str, region_pose, detector=None, scene_name: str = None) -> bool:
        """
        Check if an object pose is 'contained' within a region.

        When a *detector* (SegmentationObjectDetector) is provided alongside the
        scene_name of the region, we use the region's world-space bounding box
        for a proper volumetric check with a generous margin.  Otherwise we fall
        back to simplified distance heuristics.
        """
        # ── Volumetric check (preferred) ──
        if detector is not None and scene_name:
            bb = detector.get_bounding_box(scene_name)
            if bb is not None:
                (min_x, min_y, min_z), (max_x, max_y, max_z) = bb
                # Generous margins — box regions are tight so we give more room.
                if 'box' in region_name or 'inside' in region_name:
                    margin_xy, margin_z = 0.08, 0.25
                elif 'cupboard' in region_name:
                    margin_xy, margin_z = 0.08, 0.30
                else:
                    margin_xy, margin_z = 0.10, 0.25
                inside = (
                    (min_x - margin_xy) <= float(obj_pose[0]) <= (max_x + margin_xy)
                    and (min_y - margin_xy) <= float(obj_pose[1]) <= (max_y + margin_xy)
                    and (min_z - margin_z) <= float(obj_pose[2]) <= (max_z + margin_z)
                )
                return inside

        # ── Fallback: distance heuristics ──
        dist = compute_dist(obj_pose, region_pose)

        if 'boundary' in region_name:
            dx = abs(obj_pose[0] - region_pose[0])
            dy = abs(obj_pose[1] - region_pose[1])
            dz = abs(obj_pose[2] - region_pose[2])
            return dx < 0.20 and dy < 0.20 and dz < 0.25

        if 'box' in region_name or 'inside' in region_name:
            return dist < 0.30

        return dist < 0.35

    def resolve_region(self, obj_pos: Tuple[float, float, float], region_map: Dict[str, Tuple[np.ndarray, np.ndarray]]) -> Tuple[str, str]:
        """Wrap the standalone resolve_region logic."""
        return resolve_region(obj_pos, region_map)
