#!/usr/bin/env python3
"""Render an isometric view of a scene and the semantic maps of the 5 pipeline cameras.

    python mujoco_port/tools/render_semantic_views.py G2 --out results/visuals/G2

Writes, for the variant's initial state (MuJoCo backend):
- isometric.png: isometric view from behind the robot;
- cameras_rgb.png: the 5 camera images (left, right, overhead, wrist, front);
- cameras_semantic.png: per camera, the objects the segmentation sees (flat colour,
  from the pipeline's masks) and the pipeline's region boxes (outlines), on a
  faded camera image, with one legend (object -> resolved region);
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
CAMERA_ALIASES = {
    'left': ('left', 'cam_over_shoulder_left'), 'right': ('right', 'cam_over_shoulder_right'),
    'overhead': ('overhead', 'cam_overhead'), 'wrist': ('wrist', 'cam_wrist'), 'front': ('front', 'cam_front'),
}
# Objects: saturated fills. Regions: distinct outline colours.
OBJECT_PALETTE = [(230, 57, 70), (29, 120, 200), (46, 170, 90), (255, 170, 0), (0, 185, 190),
                  (240, 110, 170), (150, 200, 40)]
REGION_PALETTE = [(106, 61, 154), (140, 86, 75), (190, 0, 120), (0, 70, 130), (120, 120, 0),
                  (70, 70, 70), (0, 120, 110), (160, 60, 0)]
BACKGROUND = (246, 246, 244)
INK = (40, 40, 40)
MUTED = (120, 120, 120)


def _font(size, bold=False):
    from PIL import ImageFont
    names = ['DejaVuSans-Bold.ttf'] if bold else ['DejaVuSans.ttf']
    for folder in ('/usr/share/fonts/truetype/dejavu', '/usr/share/fonts/dejavu'):
        for name in names:
            path = os.path.join(folder, name)
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


def isometric(env, out: Path, size=(1400, 1000)):
    """Isometric view from behind and to the side of the robot, looking over its base."""
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
    table = world.m.body_pos[bid] if bid >= 0 else world.m.stat.center
    cam.lookat[:] = np.array([table[0] + 0.05, table[1], table[2] + 0.475])
    cam.distance = 2.3       # stays inside the room (walls 2.5 m from the centre)
    cam.azimuth = -35.0      # robot base on the -x side facing +x: camera behind its right shoulder
    cam.elevation = -35.264  # isometric elevation, narrow perspective angle below
    world.m.vis.global_.fovy = 34.0
    renderer.update_scene(world.d, cam, scene_option=opt)
    Image.fromarray(renderer.render()).save(out / 'isometric.png')


def camera_sensors(env):
    cams = getattr(env, 'cams', {}) or {}
    return {name: next((cams[a] for a in CAMERA_ALIASES[name] if a in cams), None) for name in CAMERAS}


def project(cam, points):
    """World points -> pixel (u, v) for a PyRep vision sensor (RLBench convention)."""
    K = cam.get_intrinsic_matrix()
    M = np.array(cam.get_matrix())
    E = M.reshape(4, 4) if M.size == 16 else np.vstack([M.reshape(3, 4), [0, 0, 0, 1]])
    R, C = E[:3, :3], E[:3, 3]
    ext = np.concatenate([R.T, -R.T @ C[:, None]], axis=1)
    cam_pts = (ext @ np.concatenate([points, np.ones((len(points), 1))], axis=1).T).T
    uvw = (K @ cam_pts.T).T
    return uvw[:, :2] / uvw[:, 2:3], cam_pts[:, 2] > 0.01


def capture_rgb(cam):
    cam.handle_explicitly()
    rgb = np.asarray(cam.capture_rgb())
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8) if rgb.dtype != np.uint8 else rgb


def faded(image, amount=0.72):
    """Desaturated, lightened camera image used as quiet context."""
    gray = image.astype(float).mean(axis=2, keepdims=True)
    return (amount * 255 + (1 - amount) * gray).repeat(3, axis=2).astype(np.uint8)


def outline(mask):
    edge = np.zeros_like(mask)
    edge[1:, :] |= mask[1:, :] != mask[:-1, :]
    edge[:, 1:] |= mask[:, 1:] != mask[:, :-1]
    return edge & mask


def label_chip(draw, xy, text, color, font, bounds):
    x, y = xy
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    w, h = right - left + 10, bottom - top + 6
    x = int(min(max(x, 2), bounds[0] - w - 2))
    y = int(min(max(y - h - 3, 2), bounds[1] - h - 2))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=4, fill=color)
    draw.text((x + 5, y + 3 - top), text, fill=(255, 255, 255), font=font)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('variant')
    parser.add_argument('--out', default='')
    args = parser.parse_args()
    out = Path(args.out or ROOT / 'results' / 'visuals' / args.variant).resolve()
    out.mkdir(parents=True, exist_ok=True)

    from PIL import Image, ImageDraw
    from llm_pipeline.object_aliases import canonical_object_name
    from llm_pipeline.region_aliases import normalize_region_name, planner_region_name, scene_object_for_region
    from llm_pipeline.segmentation_adapter import SegmentationEvidenceAdapter

    env = load_env(args.variant)
    isometric(env, out)
    adapter = SegmentationEvidenceAdapter(env=env, live_segmentation_view=False)
    adapter.refresh_visibility(event='initial')
    snapshot = adapter.capture_snapshot(event='initial')
    detector = adapter.detector
    visible = list(snapshot.visible_objects)
    regions = dict(snapshot.object_region_map or {})
    object_colors = {name: OBJECT_PALETTE[i % len(OBJECT_PALETTE)] for i, name in enumerate(visible)}

    region_boxes = {}
    for region in adapter.symbol_registry.regions:
        try:
            box = detector.get_bounding_box(scene_object_for_region(region))
        except Exception:
            box = None
        if box:
            region_boxes[normalize_region_name(region)] = (np.array(box[0]), np.array(box[1]))
    region_colors = {name: REGION_PALETTE[i % len(REGION_PALETTE)] for i, name in enumerate(region_boxes)}

    sensors = camera_sensors(env)
    tag = _font(14, bold=True)
    rgb_tiles, sem_tiles, pixels = [], [], {}
    for name in CAMERAS:
        cam = sensors.get(name)
        mask = detector._capture_mask(name) if name in detector.cameras else None
        if cam is None or mask is None:
            continue
        image = capture_rgb(cam)
        rgb_tiles.append((name, Image.fromarray(image)))
        canvas = faded(image)
        pixels[name] = {}
        for handle, label in detector.handle_to_task_name.items():
            obj = canonical_object_name(label)
            if obj not in object_colors:
                continue
            hit = mask == int(handle)
            if not hit.any():
                continue
            canvas[hit] = object_colors[obj]
            canvas[outline(hit)] = (60, 60, 60)
            pixels[name][obj] = pixels[name].get(obj, 0) + int(hit.sum())
        tile = Image.fromarray(canvas)
        draw = ImageDraw.Draw(tile)
        for region, (lo, hi) in region_boxes.items():
            corners = np.array([[lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]], [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]])
            uv, in_front = project(cam, corners)
            if not in_front.all():
                continue
            if uv[:, 0].max() < 0 or uv[:, 0].min() > tile.width or uv[:, 1].max() < 0 or uv[:, 1].min() > tile.height:
                continue
            points = [tuple(map(float, p)) for p in uv]
            draw.line(points + [points[0]], fill=region_colors[region], width=2, joint='curve')
            top = min(points, key=lambda p: p[1])
            label_chip(draw, top, planner_region_name(region), region_colors[region], tag, tile.size)
        sem_tiles.append((name, tile))

    def sheet(tiles, title, legend):
        w, h = tiles[0][1].size
        pad, head, cap = 18, 64, 30
        cols = 3
        rows = (len(tiles) + cols - 1) // cols
        width = cols * w + (cols + 1) * pad
        height = head + rows * (h + cap) + (rows + 1) * pad
        page = Image.new('RGB', (width, height), BACKGROUND)
        draw = ImageDraw.Draw(page)
        draw.text((pad, 16), title, fill=INK, font=_font(24, bold=True))
        for i, (name, image) in enumerate(tiles):
            x = pad + (i % cols) * (w + pad)
            y = head + pad + (i // cols) * (h + cap + pad)
            draw.text((x, y), name, fill=MUTED, font=_font(17, bold=True))
            page.paste(image, (x, y + cap))
            draw.rectangle([x - 1, y + cap - 1, x + w, y + cap + h], outline=(210, 210, 210))
        if legend and len(tiles) < rows * cols:
            x = pad + (len(tiles) % cols) * (w + pad) + 10
            y = head + pad + (len(tiles) // cols) * (h + cap + pad)
            legend(draw, x, y)
        return page

    def legend(draw, x, y):
        head, body = _font(17, bold=True), _font(16)
        draw.text((x, y), 'Objects  (resolved region)', fill=INK, font=head)
        y += 32
        for obj, color in object_colors.items():
            draw.rounded_rectangle([x, y + 2, x + 18, y + 20], radius=3, fill=color, outline=(60, 60, 60))
            region = regions.get(obj)
            draw.text((x + 30, y), obj, fill=INK, font=body)
            draw.text((x + 150, y), planner_region_name(region) if region else '(lid)', fill=MUTED, font=body)
            y += 28
        y += 18
        draw.text((x, y), 'Regions  (outlines)', fill=INK, font=head)
        y += 32
        for region, color in region_colors.items():
            draw.line([(x, y + 11), (x + 18, y + 11)], fill=color, width=4)
            draw.text((x + 30, y), planner_region_name(region), fill=INK, font=body)
            y += 26

    sheet(rgb_tiles, f'{args.variant}  ·  camera images (initial state)', None).save(out / 'cameras_rgb.png')
    sheet(sem_tiles, f'{args.variant}  ·  what the pipeline sees: objects (segmentation) and regions', legend).save(
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
