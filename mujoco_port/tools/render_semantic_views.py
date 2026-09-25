#!/usr/bin/env python3
"""Render an isometric view of a scene and the semantic maps of the 5 pipeline cameras.

    python mujoco_port/tools/render_semantic_views.py G2 --out results/visuals/G2

Writes, for the variant's initial state (MuJoCo backend):
- isometric.png: orthographic isometric view of the whole scene;
- cameras_rgb.png: the 5 camera RGB images (left, right, overhead, wrist, front);
- cameras_semantic.png: per camera, the segmentation-mask pixels the pipeline
  sees, coloured by object, with each visible object labelled by the region the
  pipeline resolves for it (planner-facing names, as in prompt v2);
- semantic_state.json: visible objects, their regions, and pixel counts per camera.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('SIM_BACKEND', 'mujoco')
import sim_backend  # noqa: E402,F401

CAMERAS = ('left', 'right', 'overhead', 'wrist', 'front')
REGION_PALETTE = [(120, 120, 255), (255, 160, 90), (120, 220, 160), (220, 120, 220), (200, 200, 90), (90, 200, 220)]
REGION_COLORS = {}
PALETTE = [
    (230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180),
    (70, 240, 240), (240, 50, 230), (210, 245, 60), (250, 190, 212), (0, 128, 128), (170, 110, 40),
]


def _font(size):
    from PIL import ImageFont
    for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf'):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_env(variant):
    os.chdir(tempfile.mkdtemp(prefix='render_'))
    from llm_pipeline import debug_execution as de
    seq = de._load_default_sequence(variant, de.DEFAULT_SEQUENCE_DIR)
    de._configure_scene_env(seq, headless=True)
    env = de._load_env_for_sequence(seq)
    for _ in range(50):
        env.pr.step()
    return env


def isometric(env, out: Path, size=(1200, 900)):
    import mujoco
    from PIL import Image
    world = env.pr._world
    renderer = mujoco.Renderer(world.m, size[1], size[0])
    opt = mujoco.MjvOption()
    opt.geomgroup[:] = 0
    opt.geomgroup[1] = 1
    opt.geomgroup[2] = 1
    cam = mujoco.MjvCamera()
    bid = mujoco.mj_name2id(world.m, mujoco.mjtObj.mjOBJ_BODY, 'diningTable')
    center = world.m.body_pos[bid] + np.array([0.0, 0.0, 0.45]) if bid >= 0 else world.m.stat.center
    cam.lookat[:] = center
    cam.distance = 2.4  # stays inside the room (walls 2.5 m from the centre)
    cam.azimuth = 225.0
    cam.elevation = -35.264  # isometric elevation; narrow perspective angle below
    world.m.vis.global_.fovy = 32.0
    renderer.update_scene(world.d, cam, scene_option=opt)
    Image.fromarray(renderer.render()).save(out / 'isometric.png')


def camera_sensors(env):
    cams = getattr(env, 'cams', {}) or {}
    aliases = {'left': ('left', 'cam_over_shoulder_left'), 'right': ('right', 'cam_over_shoulder_right'),
               'overhead': ('overhead', 'cam_overhead'), 'wrist': ('wrist', 'cam_wrist'), 'front': ('front', 'cam_front')}
    return {name: next((cams[a] for a in aliases[name] if a in cams), None) for name in CAMERAS}


def project(cam, points):
    """World points -> pixel (u, v) for a PyRep vision sensor (RLBench convention)."""
    K = cam.get_intrinsic_matrix()
    E = np.array(cam.get_matrix()).reshape(4, 4) if np.array(cam.get_matrix()).size == 16 else np.vstack(
        [np.array(cam.get_matrix()).reshape(3, 4), [0, 0, 0, 1]])
    R, C = E[:3, :3], E[:3, 3]
    ext = np.concatenate([R.T, -R.T @ C[:, None]], axis=1)
    homo = np.concatenate([points, np.ones((len(points), 1))], axis=1)
    cam_pts = (ext @ homo.T).T
    ok = cam_pts[:, 2] > 0.01
    uvw = (K @ cam_pts.T).T
    uv = uvw[:, :2] / uvw[:, 2:3]
    return uv, ok


def camera_frames(env):
    cams = getattr(env, 'cams', {}) or {}
    aliases = {'left': ('left', 'cam_over_shoulder_left'), 'right': ('right', 'cam_over_shoulder_right'),
               'overhead': ('overhead', 'cam_overhead'), 'wrist': ('wrist', 'cam_wrist'), 'front': ('front', 'cam_front')}
    frames = {}
    for name in CAMERAS:
        cam = next((cams[a] for a in aliases[name] if a in cams), None)
        if cam is None:
            continue
        cam.handle_explicitly()
        rgb = np.asarray(cam.capture_rgb())
        frames[name] = (np.clip(rgb * 255.0, 0, 255).astype(np.uint8) if rgb.dtype != np.uint8 else rgb)
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('variant')
    parser.add_argument('--out', default='')
    args = parser.parse_args()
    out = Path(args.out or ROOT / 'results' / 'visuals' / args.variant).resolve()
    out.mkdir(parents=True, exist_ok=True)

    from PIL import Image, ImageDraw
    from llm_pipeline.object_aliases import canonical_object_name
    from llm_pipeline.region_aliases import normalize_region_name, planner_region_name
    from llm_pipeline.segmentation_adapter import SegmentationEvidenceAdapter

    env = load_env(args.variant)
    isometric(env, out)
    adapter = SegmentationEvidenceAdapter(env=env, live_segmentation_view=False)
    adapter.refresh_visibility(event='initial')
    snapshot = adapter.capture_snapshot(event='initial')
    detector = adapter.detector
    visible = [name for name in snapshot.visible_objects]
    regions = dict(snapshot.object_region_map or {})
    colors = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(sorted(set(visible) | set(regions)))}

    rgb = camera_frames(env)
    camera_objects = camera_sensors(env)
    from llm_pipeline.region_aliases import scene_object_for_region
    region_boxes = {}
    for region in adapter.symbol_registry.regions:
        try:
            box = detector.get_bounding_box(scene_object_for_region(region))
        except Exception:
            box = None
        if box:
            region_boxes[normalize_region_name(region)] = (np.array(box[0]), np.array(box[1]))
    font, small = _font(18), _font(14)
    rgb_tiles, sem_tiles, pixels = [], [], {}
    for name in CAMERAS:
        mask = detector._capture_mask(name) if name in detector.cameras else None
        image = rgb.get(name)
        if image is None or mask is None:
            continue
        rgb_tiles.append((name, image))
        semantic = (0.35 * image.astype(float) + 0.65 * 60).astype(np.uint8)  # dim background
        pixels[name] = {}
        centroids = {}
        region_centroids = {}
        for handle, label in detector.handle_to_task_name.items():
            obj = canonical_object_name(label)
            if obj not in colors:
                continue
            hit = mask == int(handle)
            count = int(hit.sum())
            if count == 0:
                continue
            semantic[hit] = colors[obj]
            pixels[name][obj] = pixels[name].get(obj, 0) + count
            ys, xs = np.nonzero(hit)
            centroids.setdefault(obj, []).append((xs.mean(), ys.mean(), count))
        tile = Image.fromarray(semantic)
        draw = ImageDraw.Draw(tile)
        cam_obj = camera_objects.get(name)
        if cam_obj is not None:
            for region, (lo, hi) in region_boxes.items():
                corners = np.array([[lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
                uv, ok = project(cam_obj, corners)
                if not ok.all():
                    continue
                color = tuple(int(c) for c in REGION_COLORS.setdefault(region, REGION_PALETTE[len(REGION_COLORS) % len(REGION_PALETTE)]))
                pts = [tuple(map(float, p)) for p in uv]
                draw.line(pts + [pts[0]], fill=color, width=3)
                cx, cy = uv.mean(axis=0)
                if 0 <= cx < tile.width and 0 <= cy < tile.height:
                    draw.text((cx - 30, cy - 8), f'[{planner_region_name(region)}]', fill=color, font=small)
        for obj, points in centroids.items():
            x = sum(p[0] * p[2] for p in points) / sum(p[2] for p in points)
            y = sum(p[1] * p[2] for p in points) / sum(p[2] for p in points)
            region = regions.get(obj)
            text = f'{obj} @ {planner_region_name(region)}' if region else obj
            draw.text((x + 1, y + 1), text, fill=(0, 0, 0), font=small)
            draw.text((x, y), text, fill=(255, 255, 255), font=small)
        sem_tiles.append((name, np.asarray(tile)))

    def grid(tiles, title):
        h, w = tiles[0][1].shape[:2]
        cols = 3
        rows = (len(tiles) + cols - 1) // cols
        canvas = Image.new('RGB', (cols * w, rows * h + 40), (25, 25, 25))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 8), title, fill=(255, 255, 255), font=font)
        for i, (name, image) in enumerate(tiles):
            x, y = (i % cols) * w, 40 + (i // cols) * h
            canvas.paste(Image.fromarray(image), (x, y))
            draw.text((x + 8, y + 6), name, fill=(255, 255, 0), font=font)
        # legend in the empty last cell
        if len(tiles) < rows * cols:
            x, y = (len(tiles) % cols) * w + 20, 40 + (len(tiles) // cols) * h + 20
            draw.text((x, y), 'objects: name @ resolved region', fill=(255, 255, 255), font=font)
            j = 0
            for j, (obj, color) in enumerate(sorted(colors.items())):
                region = regions.get(obj)
                draw.rectangle([x, y + 34 + 26 * j, x + 18, y + 52 + 26 * j], fill=color)
                label = f'{obj} @ {planner_region_name(region)}' if region else f'{obj} (lid)'
                draw.text((x + 28, y + 32 + 26 * j), label, fill=(230, 230, 230), font=small)
            y2 = y + 34 + 26 * (j + 2)
            draw.text((x, y2), '[regions] (projected region boxes)', fill=(255, 255, 160), font=font)
            for k, (region, color) in enumerate(sorted(REGION_COLORS.items())):
                draw.rectangle([x, y2 + 34 + 26 * k, x + 18, y2 + 52 + 26 * k], fill=tuple(int(c) for c in color))
                draw.text((x + 28, y2 + 32 + 26 * k), planner_region_name(region), fill=(230, 230, 230), font=small)
        return canvas

    grid(rgb_tiles, f'{args.variant}: camera RGB (initial state)').save(out / 'cameras_rgb.png')
    grid(sem_tiles, f'{args.variant}: segmentation masks by object (colour) and region boxes (outlines)').save(
        out / 'cameras_semantic.png')
    (out / 'semantic_state.json').write_text(json.dumps({
        'variant': args.variant,
        'visible_objects': visible,
        'object_regions': regions,
        'object_regions_planner_names': {k: planner_region_name(v) for k, v in regions.items()},
        'pixels_per_camera': pixels,
    }, indent=2))
    print(f'wrote {out}', flush=True)
    os._exit(0)


if __name__ == '__main__':
    main()
