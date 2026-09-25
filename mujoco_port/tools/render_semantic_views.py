#!/usr/bin/env python3
"""Render an isometric view of a scene and the semantic maps of the 5 pipeline cameras.

    python mujoco_port/tools/render_semantic_views.py G2 --out results/visuals/G2

Writes, for the variant's initial state (MuJoCo backend):
- isometric.png: isometric view from behind the robot;
- cameras_rgb.png: the 5 camera images (left, right, overhead, wrist, front);
- semantic_<camera>.png / semantic_<camera>_legend.png: each camera's semantic map alone,
  and with a legend for what appears in it;
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


FONT_FILE = Path(__file__).resolve().parent / 'fonts' / 'OpenSans.ttf'   # Open Sans (OFL, fonts/OFL.txt)
SCALE = 2          # overlays are drawn on the camera image upscaled by this factor (crisper, larger text)
TABLE_REGION = 'table'


def _font(size, bold=False, weight=None):
    from PIL import ImageFont
    try:
        font = ImageFont.truetype(str(FONT_FILE), size)
        font.set_variation_by_name(weight or ('Bold' if bold else 'Regular'))
        return font
    except Exception:
        return ImageFont.load_default()


def load_env(variant):
    os.chdir(tempfile.mkdtemp(prefix='render_'))
    from llm_pipeline import debug_execution as de
    from evaluation.final_variants import is_final_variant

    if is_final_variant(variant):
        from evaluation.canonical_variants import get_variant_spec
        from llm_pipeline.final_variant_setup import configure_env

        spec = get_variant_spec(variant)
        seq = de.DebugSequence(name=variant, variant=spec.variant_id, goal=spec.goal_text, actions=())
    else:
        seq = de._load_default_sequence(variant, de.DEFAULT_SEQUENCE_DIR)
    de._configure_scene_env(seq, headless=True)
    env = de._load_env_for_sequence(seq)
    if is_final_variant(variant):
        configure_env(env, variant)
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


def dimmed(image, factor=0.8):
    """Camera image, slightly darkened so the overlays stand out."""
    return (image.astype(float) * factor).astype(np.uint8)


def outline(mask):
    edge = np.zeros_like(mask)
    edge[1:, :] |= mask[1:, :] != mask[:-1, :]
    edge[:, 1:] |= mask[:, 1:] != mask[:, :-1]
    return edge & mask


def _free_spot(x, y, w, h, bounds, placed):
    """Move a tag down/up until it does not overlap already placed tags."""
    x = int(min(max(x, 2), bounds[0] - w - 2))
    for dy in [0] + [s * k for k in range(1, 12) for s in (1, -1)]:
        yy = int(min(max(y + dy * (h + 2), 2), bounds[1] - h - 2))
        rect = (x, yy, x + w, yy + h)
        if not any(rect[0] < r[2] and r[0] < rect[2] and rect[1] < r[3] and r[1] < rect[3] for r in placed):
            return rect
    return (x, int(min(max(y, 2), bounds[1] - h - 2)), x + w, int(min(max(y, 2), bounds[1] - h - 2)) + h)


def label_chip(draw, xy, text, color, font, bounds, placed=()):
    """Object tag: filled with the object colour, white text."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    w, h = right - left + 20, bottom - top + 14
    rect = _free_spot(xy[0], xy[1] - h - 4, w, h, bounds, placed)
    draw.rounded_rectangle(rect, radius=8, fill=color, outline=(255, 255, 255), width=2)
    draw.text((rect[0] + 10, rect[1] + 7 - top), text, fill=(255, 255, 255), font=font)
    return rect


def outlined_chip(draw, xy, text, color, font, bounds, placed=()):
    """Region tag: white box with a coloured border and coloured text."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    w, h = right - left + 22, bottom - top + 16
    rect = _free_spot(xy[0], xy[1] - h - 6, w, h, bounds, placed)
    draw.rounded_rectangle(rect, radius=8, fill=(255, 255, 255, 235), outline=color, width=3)
    draw.text((rect[0] + 11, rect[1] + 8 - top), text, fill=color, font=font)
    return rect


def main_blob_box(mask, keep=0.15, margin=3):
    """Bounding box of the object's main connected blob(s), ignoring stray pixels."""
    from scipy import ndimage
    labels, count = ndimage.label(mask)
    if count == 0:
        return None
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    big = [i + 1 for i, s in enumerate(sizes) if s >= keep * sizes.max()]
    ys, xs = np.nonzero(np.isin(labels, big))
    return [int(xs.min()) - margin, int(ys.min()) - margin, int(xs.max()) + margin, int(ys.max()) + margin]


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
    # The table region is shown as the whole tabletop, not the executor's drop zone.
    try:
        table_box = detector.get_bounding_box('diningTable')
    except Exception:
        table_box = None
    if table_box:
        region_boxes[TABLE_REGION] = (np.array(table_box[0]), np.array(table_box[1]))
    table_handles = []
    try:
        table_obj = env.get_object('diningTable')
        table_handles = [int(table_obj.get_handle())] + [int(o.get_handle()) for o in table_obj.get_objects_in_tree()]
    except Exception:
        pass
    region_colors = {name: REGION_PALETTE[i % len(REGION_PALETTE)] for i, name in enumerate(region_boxes)}

    def save_single(path, camera, tile, objects, shown_regions):
        """One camera's semantic map with a legend strip for what appears in it."""
        body, head = _font(26), _font(28, bold=True)
        pad, row = 28, 42
        strip = 44 + row * max(len(objects), len(shown_regions), 1)
        strip = 80 + row * max(len(objects), len(shown_regions), 1)
        page = Image.new('RGB', (tile.width + 2 * pad, tile.height + 2 * pad + 64 + strip), BACKGROUND)
        draw = ImageDraw.Draw(page)
        draw.text((pad, pad), f'{args.variant}  ·  {camera} camera', fill=INK, font=_font(34, bold=True))
        page.paste(tile, (pad, pad + 64))
        y0 = pad + 64 + tile.height + 26
        draw.text((pad, y0), 'Objects (resolved region)', fill=INK, font=head)
        draw.text((pad + tile.width // 2, y0), 'Regions', fill=INK, font=head)
        for i, obj in enumerate(objects):
            y = y0 + 52 + i * row
            draw.rounded_rectangle([pad, y + 4, pad + 28, y + 32], radius=6, fill=object_colors[obj], outline=(60, 60, 60))
            region = regions.get(obj)
            draw.text((pad + 44, y), f'{obj}  —  {planner_region_name(region) if region else "lid"}', fill=INK, font=body)
        if not objects:
            draw.text((pad, y0 + 52), 'no task objects visible', fill=MUTED, font=body)
        for i, region in enumerate(shown_regions):
            y = y0 + 52 + i * row
            x = pad + tile.width // 2
            draw.line([(x, y + 18), (x + 28, y + 18)], fill=region_colors[region], width=7)
            draw.text((x + 44, y), planner_region_name(region), fill=INK, font=body)
        page.save(path)

    sensors = camera_sensors(env)
    tag = _font(26, weight='SemiBold')
    rgb_tiles, sem_tiles, pixels = [], [], {}
    for name in CAMERAS:
        cam = sensors.get(name)
        mask = detector._capture_mask(name) if name in detector.cameras else None
        if cam is None or mask is None:
            continue
        image = capture_rgb(cam)
        big_size = (image.shape[1] * SCALE, image.shape[0] * SCALE)
        rgb_tiles.append((name, Image.fromarray(image)))
        base = Image.fromarray(dimmed(image)).resize(big_size, Image.LANCZOS).convert('RGBA')
        mask = np.repeat(np.repeat(mask, SCALE, axis=0), SCALE, axis=1)
        overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        pixels[name] = {}
        object_masks = {}
        for handle, label in detector.handle_to_task_name.items():
            obj = canonical_object_name(label)
            if obj not in object_colors:
                continue
            hit = mask == int(handle)
            if hit.any():
                object_masks[obj] = object_masks.get(obj, np.zeros_like(hit)) | hit
        # Regions first: projected 3D box, translucent top face + full wireframe.
        shown_regions, region_tags = [], []
        for region, (lo, hi) in region_boxes.items():
            corners = np.array([[x, y, z] for z in (lo[2], hi[2]) for x, y in
                                ((lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1]))])
            uv, in_front = project(cam, corners)
            uv = uv * SCALE
            if not in_front.all():
                continue
            if uv[:, 0].max() < 0 or uv[:, 0].min() > base.width or uv[:, 1].max() < 0 or uv[:, 1].min() > base.height:
                continue
            color = region_colors[region]
            bottom, top = [tuple(map(float, p)) for p in uv[:4]], [tuple(map(float, p)) for p in uv[4:]]
            if region == TABLE_REGION:
                # The whole table as the camera sees it (its segmentation pixels, so
                # occluders stay on top): a soft fill and a contour, under everything else.
                tmask = np.isin(mask, table_handles) if table_handles else np.zeros(mask.shape, bool)
                table_layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
                if tmask.any():
                    layer = np.zeros(tmask.shape + (4,), dtype=np.uint8)
                    layer[tmask] = color + (55,)
                    edge = outline(tmask)
                    from scipy import ndimage
                    edge = ndimage.binary_dilation(edge, iterations=2) & tmask
                    layer[edge] = color + (230,)
                    table_layer = Image.fromarray(layer, 'RGBA')
                    ys, xs = np.nonzero(tmask)
                    top_row = ys.min()
                    anchor = (int(xs[ys <= top_row + 4].min()) + 16, int(top_row) + 60)
                else:
                    ImageDraw.Draw(table_layer).polygon(top, fill=color + (45,), outline=color + (220,))
                    anchor = (24, base.height - 24)
                overlay = Image.alpha_composite(table_layer, overlay)
                odraw = ImageDraw.Draw(overlay)
                region_tags.append((anchor, planner_region_name(region), color))
                shown_regions.append(region)
                continue
            odraw.polygon(top, fill=color + (70,))
            for ring in (bottom, top):
                odraw.line(ring + [ring[0]], fill=color + (230,), width=4)
            for a, b in zip(bottom, top):
                odraw.line([a, b], fill=color + (230,), width=4)
            region_tags.append((min(top, key=lambda q: q[1]), planner_region_name(region), color))
            shown_regions.append(region)
        # Objects on top: translucent fill, solid contour, 2D bounding box.
        object_tags = []
        for obj, hit in object_masks.items():
            color = object_colors[obj]
            fill = np.zeros(hit.shape + (4,), dtype=np.uint8)
            fill[hit] = color + (120,)
            fill[outline(hit)] = color + (255,)
            overlay = Image.alpha_composite(overlay, Image.fromarray(fill, 'RGBA'))
            box = main_blob_box(hit)
            ImageDraw.Draw(overlay).rectangle(box, outline=color + (255,), width=4)
            object_tags.append(((box[0], box[1]), obj, color))
            pixels[name][obj] = int(hit.sum()) // (SCALE * SCALE)
        tile = Image.alpha_composite(base, overlay).convert('RGB')
        draw = ImageDraw.Draw(tile)
        placed = []
        for xy, text, color in object_tags:   # objects: filled tag (placed first, on their box)
            placed.append(label_chip(draw, xy, text, color, tag, tile.size, placed))
        for xy, text, color in region_tags:   # regions: outlined tag
            placed.append(outlined_chip(draw, xy, text, color, tag, tile.size, placed))
        sem_tiles.append((name, tile))
        tile.save(out / f'semantic_{name}.png')  # the map alone, no legend
        save_single(out / f'semantic_{name}_legend.png', name, tile, [o for o in object_colors if pixels[name].get(o)],
                    shown_regions)

    def sheet(tiles, title, legend):
        w, h = tiles[0][1].size
        pad, head, cap = 30, 100, 52
        cols = 3
        rows = (len(tiles) + cols - 1) // cols
        width = cols * w + (cols + 1) * pad
        height = head + rows * (h + cap) + (rows + 1) * pad
        page = Image.new('RGB', (width, height), BACKGROUND)
        draw = ImageDraw.Draw(page)
        draw.text((pad, 26), title, fill=INK, font=_font(44, bold=True))
        for i, (name, image) in enumerate(tiles):
            x = pad + (i % cols) * (w + pad)
            y = head + pad + (i // cols) * (h + cap + pad)
            draw.text((x, y), name, fill=MUTED, font=_font(32, weight='SemiBold'))
            page.paste(image, (x, y + cap))
            draw.rectangle([x - 1, y + cap - 1, x + w, y + cap + h], outline=(210, 210, 210))
        if legend and len(tiles) < rows * cols:
            x = pad + (len(tiles) % cols) * (w + pad) + 20
            y = head + pad + (len(tiles) // cols) * (h + cap + pad)
            legend(draw, x, y)
        return page

    def legend(draw, x, y):
        head, body = _font(34, bold=True), _font(30)
        draw.text((x, y), 'Objects  (resolved region)', fill=INK, font=head)
        y += 60
        for obj, color in object_colors.items():
            draw.rounded_rectangle([x, y + 5, x + 34, y + 39], radius=6, fill=color, outline=(60, 60, 60))
            region = regions.get(obj)
            draw.text((x + 52, y), obj, fill=INK, font=body)
            draw.text((x + 330, y), planner_region_name(region) if region else '(lid)', fill=MUTED, font=body)
            y += 52
        y += 30
        draw.text((x, y), 'Regions  (outlines)', fill=INK, font=head)
        y += 60
        for region, color in region_colors.items():
            draw.line([(x, y + 21), (x + 34, y + 21)], fill=color, width=8)
            draw.text((x + 52, y), planner_region_name(region), fill=INK, font=body)
            y += 48

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
