#!/usr/bin/env python3
"""Render an isometric view of a scene and the semantic maps of the 5 pipeline cameras.

    python experiments/recording/render_semantic_views.py G2 --out results/visuals/G2

Writes, for the variant's initial state (MuJoCo backend):
- isometric.png: isometric view from behind the robot;
- isometric_labeled.png: the same view with object masks, region boxes and callout labels
  (rendered at 4x with 8x multisampling, overlays drawn at 4x, saved at 2x: 3200 px wide);
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

ROOT = Path(__file__).resolve().parents[2] / "src"
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
# The isometric figure colours by role, not by item: every task object one colour, every region
# another, and every leader line in one dark ink.
ISO_OBJECT_COLOR = (36, 104, 196)      # movable / articulated objects: solid pills, filled masks
ISO_REGION_COLOR = (214, 128, 0)       # placement regions: outlined pills, wireframe boxes
LEADER_INK = (24, 27, 32)
BACKGROUND = (246, 246, 244)
INK = (40, 40, 40)
MUTED = (120, 120, 120)


FONT_FILE = Path(__file__).resolve().parent / 'fonts' / 'OpenSans.ttf'   # Open Sans (OFL, fonts/OFL.txt)
SCALE = 2          # overlays are drawn on the camera image upscaled by this factor (crisper, larger text)
ISO_SIZE = (1600, 1150)   # isometric figure size at 1x
ISO_RENDER = 4            # render and draw the isometric figure at this factor ...
ISO_OUTPUT = 2            # ... and save it at this one (LANCZOS downsampling anti-aliases lines and text)
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


def isometric(env, out: Path, size=ISO_SIZE, focus=None, render_scale=ISO_RENDER, output_scale=ISO_OUTPUT, hide=()):
    """Isometric view from behind and to the side of the robot, looking over its base.

    focus: world points (task objects, region corners) the view is framed on: the camera
    looks at their centre from a distance at which they fill the frame. The view is
    rendered at ``render_scale`` x ``size`` with 8x multisampling; isometric.png is saved at
    ``output_scale`` x ``size``. hide: body names left out of the render (marker geoms of regions
    the scene does not use). Returns the full-resolution image, handles and projector."""
    import mujoco
    from PIL import Image
    world = env.pr._world
    size = (int(size[0] * render_scale), int(size[1] * render_scale))
    world.m.vis.global_.offwidth = max(int(world.m.vis.global_.offwidth), size[0])
    world.m.vis.global_.offheight = max(int(world.m.vis.global_.offheight), size[1])
    world.m.vis.quality.offsamples = max(int(world.m.vis.quality.offsamples), 8)
    renderer = mujoco.Renderer(world.m, size[1], size[0])
    hidden = [g for g in range(world.m.ngeom)
              if mujoco.mj_id2name(world.m, mujoco.mjtObj.mjOBJ_BODY, int(world.m.geom_bodyid[g])) in set(hide)]
    saved_groups = {g: int(world.m.geom_group[g]) for g in hidden}
    for g in hidden:
        world.m.geom_group[g] = 5              # a group the scene option does not draw
    # Region marker tiles (group 2) are drawn lying on the surface below them: some float at their
    # region's height and would cast a shadow a little away from themselves.
    # (only tiles above the tabletop: a tile over a grate would fall through it)
    saved_xpos = {}
    for g in range(world.m.ngeom):
        if int(world.m.geom_group[g]) != 2:
            continue
        centre = np.array(world.d.geom_xpos[g], dtype=float)
        hit = np.zeros(1, dtype=np.int32)
        groups = np.array([1, 1, 0, 0, 0, 0], dtype=np.uint8)      # visual and collision geoms only
        depth = mujoco.mj_ray(world.m, world.d, centre, np.array([0.0, 0.0, -1.0]), groups, 1,
                              int(world.m.geom_bodyid[g]), hit)
        below = (mujoco.mj_id2name(world.m, mujoco.mjtObj.mjOBJ_BODY, int(world.m.geom_bodyid[hit[0]]))
                 if hit[0] >= 0 else '') or ''
        if depth > 0.01 and below.startswith('diningTable'):
            saved_xpos[g] = centre.copy()
            world.d.geom_xpos[g][2] = centre[2] - depth + 0.002
    opt = mujoco.MjvOption()
    opt.geomgroup[:] = 0
    opt.geomgroup[1] = 1
    opt.geomgroup[2] = 1
    cam = mujoco.MjvCamera()
    bid = mujoco.mj_name2id(world.m, mujoco.mjtObj.mjOBJ_BODY, 'diningTable')
    table = world.m.body_pos[bid] if bid >= 0 else world.m.stat.center
    cam.lookat[:] = np.array([table[0] + 0.05, table[1], table[2] + 0.475])
    cam.distance = 2.3       # stays inside the room (walls 2.5 m from the centre)
    if focus is not None and len(focus):
        pts = np.asarray(focus, float)
        lo, hi = pts.min(axis=0), pts.max(axis=0)
        cam.lookat[:] = (lo + hi) / 2.0
        radius = float(np.linalg.norm(hi - lo)) / 2.0
        cam.distance = float(np.clip(1.15 * radius / np.sin(np.radians(34.0) / 2.0), 1.3, 2.3))
    cam.azimuth = -35.0      # robot base on the -x side facing +x: camera behind its right shoulder
    cam.elevation = -35.264  # isometric elevation, narrow perspective angle below
    world.m.vis.global_.fovy = 34.0
    renderer.update_scene(world.d, cam, scene_option=opt)
    rgb = renderer.render()
    final = (size[0] * output_scale // render_scale, size[1] * output_scale // render_scale)
    Image.fromarray(rgb).resize(final, Image.LANCZOS).save(out / 'isometric.png')
    project_fn = free_camera_projector(renderer, world.m, size)
    renderer.enable_segmentation_rendering()
    renderer.update_scene(world.d, cam, scene_option=opt)
    seg = renderer.render()
    renderer.disable_segmentation_rendering()
    geom_ids, types = seg[:, :, 0], seg[:, :, 1]
    handles = np.full(geom_ids.shape, -1, dtype=np.int64)
    is_geom = (types == int(mujoco.mjtObj.mjOBJ_GEOM)) & (geom_ids >= 0)
    handles[is_geom] = world.geom_handle[geom_ids[is_geom]]
    for g, group in saved_groups.items():
        world.m.geom_group[g] = group
    for g, xpos in saved_xpos.items():
        world.d.geom_xpos[g] = xpos
    return rgb, handles, project_fn


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


def _interior_point(mask):
    """A pixel deep inside the mask's largest blob (label anchor)."""
    from scipy import ndimage
    labels, count = ndimage.label(mask)
    if count == 0:
        return None
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    blob = labels == (int(np.argmax(sizes)) + 1)
    depth = ndimage.distance_transform_edt(blob)
    y, x = np.unravel_index(int(np.argmax(depth)), depth.shape)
    return int(x), int(y)


def _segment_hits_rect(p, q, rect, pad=6):
    """Whether segment p-q passes through rect (sampled)."""
    for s in np.linspace(0.08, 0.92, 24):
        x, y = p[0] + s * (q[0] - p[0]), p[1] + s * (q[1] - p[1])
        if rect[0] - pad <= x <= rect[2] + pad and rect[1] - pad <= y <= rect[3] + pad:
            return True
    return False


def draw_callouts(image, items, font, reserved=()):
    """Callout labels: a dot on the anchor, a leader line, and a label box placed where it
    overlaps no other label and its leader crosses no other label. items: dicts with
    anchor, text, color, kind (object/region). Objects get a filled box in their colour with
    white text; regions a white box with a coloured border and coloured text. All leader
    lines are drawn before the boxes, so no line runs over a label."""
    import math
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image, 'RGBA')
    width, height = image.size
    boxes = [tuple(r) for r in reserved]
    anchors = [it['anchor'] for it in items]
    dots = [(x - 12, y - 12, x + 12, y + 12) for x, y in anchors]
    leaders = []
    layout = []

    def fits(rect, anchor, nearest):
        if not (rect[0] >= 4 and rect[1] >= 4 and rect[2] <= width - 4 and rect[3] <= height - 4):
            return False
        for r in boxes + dots:
            if rect[0] < r[2] + 8 and r[0] < rect[2] + 8 and rect[1] < r[3] + 8 and r[1] < rect[3] + 8:
                return False
        if any(_segment_hits_rect(anchor, nearest, r) for r in boxes):
            return False
        # the new box must not cover an existing leader line
        return not any(_segment_hits_rect(a, b, rect, pad=4) for a, b in leaders)

    for item in items:
        ax, ay = item['anchor']
        left, top, right, bottom = draw.textbbox((0, 0), item['text'], font=font)
        w, h = right - left + 32, bottom - top + 20
        rect = None
        for dist in (70, 110, 160, 220, 300, 380):
            for angle in (-55, -125, -25, -155, 25, 155, -90, 90, 0, 180):
                cx = ax + dist * math.cos(math.radians(angle))
                cy = ay + dist * math.sin(math.radians(angle))
                candidate = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                nearest = (min(max(ax, candidate[0]), candidate[2]), min(max(ay, candidate[1]), candidate[3]))
                if fits(candidate, (ax, ay), nearest):
                    rect = candidate
                    break
            if rect:
                break
        if rect is None:
            cx = min(max(ax, w / 2 + 4), width - w / 2 - 4)
            cy = min(max(ay - 80, h / 2 + 4), height - h / 2 - 4)
            rect = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        nearest = (min(max(ax, rect[0]), rect[2]), min(max(ay, rect[1]), rect[3]))
        boxes.append(rect)
        leaders.append(((ax, ay), nearest))
        layout.append((item, rect, nearest, top))

    for item, rect, nearest, _ in layout:            # pass 1: leaders and dots
        ax, ay = item['anchor']
        color = tuple(item['color'])
        draw.line([(ax, ay), nearest], fill=(255, 255, 255, 230), width=7)
        draw.line([(ax, ay), nearest], fill=color + (255,), width=3)
        draw.ellipse([ax - 9, ay - 9, ax + 9, ay + 9], fill=(255, 255, 255, 255))
        draw.ellipse([ax - 6, ay - 6, ax + 6, ay + 6], fill=color + (255,))
    for item, rect, _, top in layout:                  # pass 2: label boxes on top
        color = tuple(item['color'])
        shadow = (rect[0] + 3, rect[1] + 4, rect[2] + 3, rect[3] + 4)
        draw.rounded_rectangle(shadow, radius=12, fill=(0, 0, 0, 70))
        if item['kind'] == 'object':
            draw.rounded_rectangle(rect, radius=12, fill=color + (255,), outline=(255, 255, 255, 255), width=2)
            ink = (255, 255, 255)
        else:
            draw.rounded_rectangle(rect, radius=12, fill=(255, 255, 255, 240), outline=color + (255,), width=3)
            ink = color
        draw.text((rect[0] + 16, rect[1] + 10 - top), item['text'], fill=ink, font=font)
    return boxes


def _draw_label(draw, rect, item, top, font):
    color = tuple(item['color'])
    shadow = (rect[0] + 3, rect[1] + 4, rect[2] + 3, rect[3] + 4)
    draw.rounded_rectangle(shadow, radius=12, fill=(0, 0, 0, 70))
    if item['kind'] == 'object':
        draw.rounded_rectangle(rect, radius=12, fill=color + (255,), outline=(255, 255, 255, 255), width=2)
        ink = (255, 255, 255)
    else:
        draw.rounded_rectangle(rect, radius=12, fill=(255, 255, 255, 242), outline=color + (255,), width=3)
        ink = color
    draw.text((rect[0] + 16, rect[1] + 10 - top), item['text'], fill=ink, font=font)


def _pill_metrics(font, scale):
    """Pill height and text offsets from the font's cap and x heights, identical for every
    label (so labels with and without descenders sit the same way)."""
    cap = font.getbbox('H')
    xh = font.getbbox('x')
    cap_h, x_h = cap[3] - cap[1], xh[3] - xh[1]
    height = int(round(cap_h * 2.3))
    # The optical centre of mixed lowercase text lies between its x-height and cap-height centres.
    baseline_offset = (cap_h + x_h) / 4.0
    pad_x = int(round(cap_h * 0.95))
    return height, baseline_offset, pad_x


def _draw_pills(image, layout, font, scale):
    """Clean pill labels: one blurred shadow layer, then solid pills (objects: filled, white
    text; regions: white with a coloured border and coloured text), text optically centred."""
    from PIL import Image, ImageDraw, ImageFilter
    height, baseline_offset, pad_x = _pill_metrics(font, scale)
    shadow = Image.new('RGBA', image.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    for _, rect, _, _ in layout:
        r = (rect[3] - rect[1]) / 2
        sdraw.rounded_rectangle((rect[0], rect[1] + 3 * scale, rect[2], rect[3] + 3 * scale), radius=r,
                                fill=(20, 24, 30, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(4 * scale))
    image.alpha_composite(shadow)
    draw = ImageDraw.Draw(image, 'RGBA')
    border = max(1, int(round(1.6 * scale)))
    for item, rect, _, _ in layout:
        color = tuple(item['color'])
        r = (rect[3] - rect[1]) / 2
        if item['kind'] == 'object':
            draw.rounded_rectangle(rect, radius=r, fill=color + (255,))
            ink = (255, 255, 255)
        else:
            draw.rounded_rectangle(rect, radius=r, fill=(255, 255, 255, 250), outline=color + (255,), width=border)
            ink = tuple(int(0.82 * c) for c in color)
        cy = (rect[1] + rect[3]) / 2.0
        draw.text((rect[0] + pad_x, cy + baseline_offset), item['text'], fill=ink, font=font, anchor='ls')


def draw_callouts_gutter(image, items, font, margin=28, gap=14, scale=1, clean=False):
    """Figure-style callouts: labels stacked in a left and a right column (split at the
    median anchor x, ordered by anchor height, never overlapping), each joined to its
    anchor by a leader line. Leaders are drawn first, labels on top. ``clean``: pill labels
    with optically centred text and thin haloed leaders (the isometric figure)."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image, 'RGBA')
    width, height = image.size
    margin, gap = margin * scale, gap * scale
    measured = []
    if clean:
        pill_h, _, pad_x = _pill_metrics(font, scale)
    for item in items:
        left, top, right, bottom = draw.textbbox((0, 0), item['text'], font=font)
        if clean:
            measured.append((item, right - left + 2 * pad_x, pill_h, top))
        else:
            measured.append((item, right - left + 32, bottom - top + 20, top))
    split = float(np.median([m[0]['anchor'][0] for m in measured])) if measured else width / 2
    layout = []
    for side in ('left', 'right'):
        group = [m for m in measured if (m[0]['anchor'][0] <= split) == (side == 'left')]
        group.sort(key=lambda m: m[0]['anchor'][1])
        ys, cursor = [], margin
        for item, w, h, _ in group:
            y = max(item['anchor'][1] - h / 2, cursor)
            ys.append(y)
            cursor = y + h + gap
        overflow = cursor - gap - (height - margin)
        if overflow > 0:
            ys = [max(margin, y - overflow) for y in ys]
        for (item, w, h, top), y in zip(group, ys):
            x = margin if side == 'left' else width - margin - w
            rect = (x, y, x + w, y + h)
            edge = (rect[2], y + h / 2) if side == 'left' else (rect[0], y + h / 2)
            layout.append((item, rect, edge, top))
    if clean:
        paths = []
        for item, rect, edge, _ in layout:
            ax, ay = item['anchor']
            ex, ey = edge
            rise = abs(ay - ey)
            if abs(ax - ex) > rise:            # horizontal from the label, then 45 degrees to the anchor
                kx = ax - rise if ax > ex else ax + rise
                paths.append((item, [(ex, ey), (kx, ey), (ax, ay)]))
            else:
                paths.append((item, [(ex, ey), (ax, ay)]))
        for _, path in paths:                  # solid dark leaders, no halo
            draw.line(path, fill=LEADER_INK + (255,), width=int(round(3.4 * scale)), joint='curve')
        for item, path in paths:               # anchor: a role-coloured dot in a dark ring
            ax, ay = path[-1]
            ring, dot = 8.0 * scale, 5.2 * scale
            draw.ellipse([ax - ring, ay - ring, ax + ring, ay + ring], fill=LEADER_INK + (255,))
            draw.ellipse([ax - dot, ay - dot, ax + dot, ay + dot], fill=tuple(item['color']) + (255,))
        _draw_pills(image, layout, font, scale)
        return
    for item, rect, edge, _ in layout:
        ax, ay = item['anchor']
        color = tuple(item['color'])
        draw.line([(ax, ay), edge], fill=(255, 255, 255, 220), width=7)
        draw.line([(ax, ay), edge], fill=color + (255,), width=3)
        draw.ellipse([ax - 10, ay - 10, ax + 10, ay + 10], fill=(255, 255, 255, 255))
        draw.ellipse([ax - 7, ay - 7, ax + 7, ay + 7], fill=color + (255,))
    for item, rect, _, top in layout:
        _draw_label(draw, rect, item, top, font)


def annotate(base, mask, project_fn, handle_to_label, object_colors, region_boxes, region_colors, table_handles,
             region_name, font, line=4, layout='radial', scale=1, clean=False, region_handles=None):
    """Object masks (fill, contour, box), region boxes (top face, wireframe; the table as its
    segmentation pixels) and callout labels on an RGB image. mask: per-pixel object handle.
    Returns (image, shown_regions, pixel counts per object). ``clean`` (with region_handles: the
    scene geometry of each region): a region is painted on its own geometry where the view sees it
    (a mat, the rack), as a flat footprint where it does not, and not at all when its geometry is a
    task object (the plate's top: the object is already marked)."""
    from PIL import Image, ImageDraw
    from scipy import ndimage
    base = base.convert('RGBA')
    overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
    object_masks = {}
    for handle, obj in handle_to_label.items():
        if obj in object_colors:
            hit = mask == int(handle)
            if hit.any():
                object_masks[obj] = object_masks.get(obj, np.zeros_like(hit)) | hit
    shown, region_items, table_mask = [], [], None
    for region, (lo, hi) in region_boxes.items():
        color = region_colors[region]
        if region == TABLE_REGION:
            tmask = np.isin(mask, table_handles) if table_handles else np.zeros(mask.shape, bool)
            if not tmask.any():
                continue
            layer = np.zeros(tmask.shape + (4,), dtype=np.uint8)
            if not clean:
                layer[tmask] = color + (50,)
            edge = ndimage.binary_dilation(outline(tmask), iterations=(1 if clean else 2) * scale) & tmask
            layer[edge] = color + ((150,) if clean else (230,))
            overlay = Image.alpha_composite(Image.fromarray(layer, 'RGBA'), overlay)
            table_mask = tmask       # its label anchor is chosen once everything else is drawn
            region_items.append({'anchor': None, 'text': region_name(region), 'color': color, 'kind': 'region',
                                 'table': True})
            shown.append(region)
            continue
        if clean and region_handles is not None:
            handles = region_handles.get(region, [])
            on_object = any(handle_to_label.get(h) in object_colors for h in handles)
            seen = np.isin(mask, handles) if handles else np.zeros(mask.shape, bool)
            if seen.sum() > 400 * scale * scale and not on_object:
                layer = np.zeros(seen.shape + (4,), dtype=np.uint8)
                layer[seen] = color + (85,)
                layer[ndimage.binary_dilation(outline(seen), iterations=max(1, int(1.5 * scale))) & seen] = color + (255,)
                overlay = Image.alpha_composite(overlay, Image.fromarray(layer, 'RGBA'))
                region_items.append({'anchor': _interior_point(seen), 'text': region_name(region), 'color': color,
                                     'kind': 'region'})
                shown.append(region)
                continue
        corners = np.array([[x, y, z] for z in (lo[2], hi[2]) for x, y in
                            ((lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]), (lo[0], hi[1]))])
        uv, in_front = project_fn(corners)
        if not in_front.all():
            continue
        if uv[:, 0].max() < 0 or uv[:, 0].min() > base.width or uv[:, 1].max() < 0 or uv[:, 1].min() > base.height:
            continue
        odraw = ImageDraw.Draw(overlay)
        bottom, top = [tuple(map(float, q)) for q in uv[:4]], [tuple(map(float, q)) for q in uv[4:]]
        on_object = clean and region_handles is not None and any(
            handle_to_label.get(h) in object_colors for h in region_handles.get(region, []))
        if clean:                              # a flat footprint (nothing over an object that is marked)
            if not on_object:
                odraw.polygon(top, fill=color + (70,))
                odraw.line(top + [top[0]], fill=color + (255,), width=line, joint='curve')
        else:
            odraw.polygon(top, fill=color + (60,))
            for ring in (bottom, top):
                odraw.line(ring + [ring[0]], fill=color + (220,), width=line)
            for a, b in zip(bottom, top):
                odraw.line([a, b], fill=color + (220,), width=line)
        cx = float(np.clip(np.mean([q[0] for q in top]), 10, base.width - 10))
        cy = float(np.clip(np.mean([q[1] for q in top]), 10, base.height - 10))
        region_items.append({'anchor': (cx, cy), 'text': region_name(region), 'color': color, 'kind': 'region'})
        shown.append(region)
    object_items, pixels, boxes = [], {}, []
    for obj, hit in object_masks.items():
        color = object_colors[obj]
        fill = np.zeros(hit.shape + (4,), dtype=np.uint8)
        fill[hit] = color + (115,)
        fill[ndimage.binary_dilation(outline(hit), iterations=scale) & hit] = color + (255,)
        overlay = Image.alpha_composite(overlay, Image.fromarray(fill, 'RGBA'))
        box = main_blob_box(hit, margin=3 * scale)
        if not clean:                          # the clean figure marks objects by their masks alone
            ImageDraw.Draw(overlay).rounded_rectangle(box, radius=6 * scale, outline=color + (255,),
                                                      width=max(2, line - scale))
        boxes.append(box)
        object_items.append({'anchor': _interior_point(hit), 'text': obj, 'color': color, 'kind': 'object'})
        pixels[obj] = int(hit.sum())
    for item in region_items:
        if item.get('table'):
            # the most open point of the tabletop: far from every object and region overlay
            occupied = np.array(overlay)[:, :, 3] > 80
            free = (ndimage.binary_erosion(table_mask, iterations=3 * scale)
                    & ~ndimage.binary_dilation(occupied, iterations=25 * scale))
            if clean:                          # the central part of the table, clear of the label gutters
                columns = np.arange(free.shape[1])
                free &= ((columns > 0.25 * free.shape[1]) & (columns < 0.65 * free.shape[1]))[None, :]
            if free.any():
                depth = ndimage.distance_transform_edt(free)
                y, x = np.unravel_index(int(np.argmax(depth)), depth.shape)
                item['anchor'] = (int(x), int(y))
            else:
                item['anchor'] = _interior_point(table_mask)
    image = Image.alpha_composite(base, overlay)
    items = [it for it in object_items + region_items if it['anchor'] is not None]
    if layout == 'gutter':
        draw_callouts_gutter(image, items, font, scale=scale, clean=clean)
    else:
        draw_callouts(image, items, font)
    return image.convert('RGB'), shown, pixels


def free_camera_projector(renderer, model, size):
    """Pixel projection for a MuJoCo free camera after renderer.update_scene()."""
    import math
    gl = renderer.scene.camera[0]
    pos, forward, up = (np.array(gl.pos, float), np.array(gl.forward, float), np.array(gl.up, float))
    right = np.cross(forward, up)
    width, height = size
    focal = (height / 2.0) / math.tan(math.radians(model.vis.global_.fovy) / 2.0)

    def project_fn(points):
        v = np.asarray(points, float) - pos
        z = v @ forward
        u = width / 2.0 + focal * (v @ right) / np.maximum(z, 1e-6)
        w = height / 2.0 - focal * (v @ up) / np.maximum(z, 1e-6)
        return np.stack([u, w], axis=1), z > 0.01
    return project_fn


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('variant')
    parser.add_argument('--out', default='')
    parser.add_argument('--only-isometric', action='store_true',
                        help='Write isometric.png and isometric_labeled.png only (leave the camera maps as they are)')
    args = parser.parse_args()
    out = Path(args.out or ROOT.parent / 'runs' / 'visuals' / args.variant).resolve()
    out.mkdir(parents=True, exist_ok=True)

    from PIL import Image, ImageDraw
    from llm_pipeline.object_aliases import canonical_object_name
    from llm_pipeline.region_aliases import normalize_region_name, planner_region_name, scene_object_for_region
    from llm_pipeline.segmentation_adapter import SegmentationEvidenceAdapter
    from pyrep.backend import sim

    env = load_env(args.variant)
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

    handle_to_label = {int(h): canonical_object_name(label) for h, label in detector.handle_to_task_name.items()}
    tag = _font(30, weight='SemiBold')

    # Isometric view framed on the task objects and regions, with every task object the
    # view sees (masks) and every region labelled.
    focus = [corner for region, (lo, hi) in region_boxes.items() if region != TABLE_REGION
             for corner in (lo, hi)]
    for handle, label in handle_to_label.items():
        try:
            focus.append(np.array(sim.simGetObjectPosition(int(handle), -1)))
        except Exception:
            pass
    region_objects = {scene_object_for_region(r) for r in region_boxes}
    hide = [name for name in ('cupboard_boundary', 'box_boundary', 'placement_boundary', 'groceries_boundary',
                              'plate_boundary', 'prep_area', 'grill_boundary')
            if name not in region_objects]
    iso_rgb, iso_handles, iso_project = isometric(env, out, focus=focus, hide=hide)
    region_handles = {}
    for region in region_boxes:
        try:
            obj = env.get_object(scene_object_for_region(region))
            region_handles[region] = [int(obj.get_handle())] + [int(o.get_handle()) for o in obj.get_objects_in_tree()]
        except Exception:
            region_handles[region] = []
    iso_colors = {name: ISO_OBJECT_COLOR for name in object_colors}
    for label in sorted({handle_to_label[h] for h in np.unique(iso_handles).tolist() if h in handle_to_label}):
        if label not in iso_colors and label in detector.task_objects:
            iso_colors[label] = ISO_OBJECT_COLOR
    iso_region_colors = {name: ISO_REGION_COLOR for name in region_boxes}
    k = ISO_RENDER
    iso_image, _, _ = annotate(Image.fromarray(iso_rgb), iso_handles, iso_project, handle_to_label, iso_colors,
                               region_boxes, iso_region_colors, table_handles, planner_region_name,
                               _font(32 * k, weight='SemiBold'), line=3 * k, layout='gutter', scale=k, clean=True,
                               region_handles=region_handles)
    final = (ISO_SIZE[0] * ISO_OUTPUT, ISO_SIZE[1] * ISO_OUTPUT)
    iso_image.resize(final, Image.LANCZOS).save(out / 'isometric_labeled.png', optimize=True)
    if args.only_isometric:
        print(f'wrote {out / "isometric_labeled.png"}', flush=True)
        os._exit(0)

    sensors = camera_sensors(env)
    rgb_tiles, sem_tiles, pixels = [], [], {}
    for name in CAMERAS:
        cam = sensors.get(name)
        mask = detector._capture_mask(name) if name in detector.cameras else None
        if cam is None or mask is None:
            continue
        image = capture_rgb(cam)
        big_size = (image.shape[1] * SCALE, image.shape[0] * SCALE)
        rgb_tiles.append((name, Image.fromarray(image)))
        base = Image.fromarray(dimmed(image)).resize(big_size, Image.LANCZOS)
        mask = np.repeat(np.repeat(mask, SCALE, axis=0), SCALE, axis=1)

        def project_fn(points, cam=cam):
            uv, in_front = project(cam, points)
            return uv * SCALE, in_front

        tile, shown_regions, counts = annotate(base, mask, project_fn, handle_to_label, object_colors, region_boxes,
                                               region_colors, table_handles, planner_region_name, tag)
        pixels[name] = {obj: n // (SCALE * SCALE) for obj, n in counts.items()}
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
