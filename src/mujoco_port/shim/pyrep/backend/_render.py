"""Offscreen rendering of CoppeliaSim-style vision sensors with MuJoCo."""

from __future__ import annotations

import os
import sys
import warnings

import numpy as np


def configure_gl_backend():
    """Pick a MuJoCo GL backend before `mujoco` renders anything."""
    if os.environ.get('MUJOCO_GL'):
        return os.environ['MUJOCO_GL']
    if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
        backend = 'glfw'
    else:
        backend = 'egl'
    os.environ['MUJOCO_GL'] = backend
    if backend in ('egl', 'osmesa'):
        os.environ.setdefault('PYOPENGL_PLATFORM', backend)
    return backend


class SensorRenderer:
    """Renders RGB / depth / colour-coded handle images for named cameras."""

    VISION_GROUP = 1

    def __init__(self, model, geom_handle: np.ndarray):
        self.model = model
        self.geom_handle = geom_handle  # geom id -> CoppeliaSim shape handle (-1 if none)
        self._renderers = {}
        self._failed = False
        self._warned = False

    def _renderer(self, width, height):
        key = (width, height)
        if key in self._renderers:
            return self._renderers[key]
        import mujoco
        vis = self.model.vis.global_
        if width > vis.offwidth or height > vis.offheight:
            vis.offwidth = max(vis.offwidth, width)
            vis.offheight = max(vis.offheight, height)
        r = mujoco.Renderer(self.model, height=height, width=width)
        self._renderers[key] = r
        return r

    def _scene_option(self):
        import mujoco
        opt = mujoco.MjvOption()
        opt.geomgroup[:] = 0
        opt.geomgroup[self.VISION_GROUP] = 1
        opt.sitegroup[:] = 0
        opt.flags[mujoco.mjtVisFlag.mjVIS_TEXTURE] = 1
        return opt

    def render(self, data, cam_id, width, height, mode='rgb', near=0.01, far=10.0):
        """mode: 'rgb' -> float32 HxWx3 in [0,1]; 'depth' -> metres HxW; 'coded' -> float32 RGB handle code."""
        if self._failed:
            return self._blank(width, height, mode)
        try:
            r = self._renderer(width, height)
            opt = self._scene_option()
            if mode == 'depth':
                r.enable_depth_rendering()
            elif mode == 'coded':
                r.enable_segmentation_rendering()
            r.update_scene(data, camera=int(cam_id), scene_option=opt)
            img = r.render()
            if mode == 'depth':
                r.disable_depth_rendering()
                return np.asarray(img, dtype=np.float32)
            if mode == 'coded':
                r.disable_segmentation_rendering()
                ids = img[..., 0].astype(np.int64)
                types = img[..., 1]
                handles = np.zeros(ids.shape, dtype=np.int64)
                valid = (ids >= 0) & (types == 5)  # mjOBJ_GEOM
                handles[valid] = np.maximum(self.geom_handle[ids[valid]], 0)
                rgb = np.stack([handles & 0xFF, (handles >> 8) & 0xFF, (handles >> 16) & 0xFF], axis=-1)
                return (rgb.astype(np.float32) / 255.0)
            return np.asarray(img, dtype=np.float32) / 255.0
        except Exception as exc:  # pragma: no cover - depends on GL availability
            self._failed = True
            if not self._warned:
                self._warned = True
                print(f'[mujoco-shim] WARNING: offscreen rendering unavailable ({exc!r}); '
                      f'vision sensors return blank images. Set MUJOCO_GL=egl|glfw|osmesa.',
                      file=sys.stderr)
            return self._blank(width, height, mode)

    @staticmethod
    def _blank(width, height, mode):
        if mode == 'depth':
            return np.full((height, width), 10.0, dtype=np.float32)
        return np.zeros((height, width, 3), dtype=np.float32)

    def close(self):
        for r in self._renderers.values():
            try:
                r.close()
            except Exception:
                pass
        self._renderers = {}
