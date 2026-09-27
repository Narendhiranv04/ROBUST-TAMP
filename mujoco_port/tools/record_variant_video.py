#!/usr/bin/env python3
"""Record a variant's ground-truth run (oracle planner, full system) from a fixed isometric view.

    python mujoco_port/tools/record_variant_video.py FINAL.K0 --out results/visuals/videos [--size 3840x2160]

Every ``--every`` simulator steps (default 4: 5 ms timestep -> 50 fps in simulated real time) the
scene is rendered with MuJoCo's offscreen renderer (8x multisampling) from an isometric camera
framed on the scene's task objects and fixtures (fixed for the whole video), and piped to ffmpeg
(H.264, ``--crf``, yuv420p). Writes ``<out>/<variant>/{<variant>.mp4, first.png, last.png,
trial/ (the oracle trial's logs), video.json}``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('SIM_BACKEND', 'mujoco')

FOCUS_KEYWORDS = ('mug', 'spam', 'sugar', 'grocer', 'can', 'phone', 'cupboard', 'box', 'grill', 'plate',
                  'meat', 'chicken', 'steak', 'rack', 'diningtable', 'panda')   # the robot too: its arm stays in frame


class Recorder:
    def __init__(self, path: Path, size, every: int, crf: int, fps: int, codec: str = 'libx264',
                 fovy: float = 40.0, lift: float = 0.08):
        self.path, self.size, self.every, self.crf, self.fps = path, size, every, crf, fps
        self.codec, self.fovy, self.lift = codec, fovy, lift
        self.world = None
        self.renderer = self.cam = self.opt = self.proc = None
        self.steps = self.frames = 0
        self.first = self.last = None

    def _setup(self, world):
        import mujoco
        self.world = world
        W, H = self.size
        world.m.vis.global_.offwidth = max(int(world.m.vis.global_.offwidth), W)
        world.m.vis.global_.offheight = max(int(world.m.vis.global_.offheight), H)
        world.m.vis.quality.offsamples = 8
        world.m.vis.global_.fovy = self.fovy
        self.renderer = mujoco.Renderer(world.m, H, W)
        self.opt = mujoco.MjvOption()
        self.opt.geomgroup[:] = 0
        self.opt.geomgroup[1] = 1
        self.opt.geomgroup[2] = 1
        # Frame on the task objects and fixtures, as the isometric stills (render_semantic_views).
        pts = []
        for b in range(world.m.nbody):
            name = (mujoco.mj_id2name(world.m, mujoco.mjtObj.mjOBJ_BODY, b) or '').lower()
            if any(k in name for k in FOCUS_KEYWORDS):
                pts.append(np.array(world.d.xpos[b]))
        cam = mujoco.MjvCamera()
        if pts:
            pts = np.asarray(pts)
            lo, hi = np.percentile(pts, 3, axis=0), np.percentile(pts, 97, axis=0)
            cam.lookat[:] = (lo + hi) / 2.0
            radius = float(np.linalg.norm(hi - lo)) / 2.0
            cam.distance = float(np.clip(1.15 * radius / np.sin(np.radians(self.fovy) / 2.0), 1.3, 2.3))
            cam.lookat[2] += self.lift            # keep the cupboard top and the robot's head in frame
        else:
            cam.lookat[:] = world.m.stat.center
            cam.distance = 2.3
        cam.azimuth = -35.0
        cam.elevation = -35.264
        self.cam = cam
        if self.path is None:                     # preview: no video
            return
        codec = ['-c:v', 'libx265', '-preset', 'medium', '-crf', str(self.crf), '-tag:v', 'hvc1',
                 '-x265-params', 'log-level=error:pools=8'] if self.codec == 'libx265' else \
                ['-c:v', 'libx264', '-preset', 'slow', '-crf', str(self.crf), '-threads', '8']
        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
               '-r', str(self.fps), '-i', '-'] + codec + ['-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(self.path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def frame(self, world, force=False):
        if self.world is None:
            self._setup(world)
        self.steps += 1
        if not force and self.steps % self.every:
            return
        self.renderer.update_scene(world.d, self.cam, scene_option=self.opt)
        rgb = self.renderer.render()
        if self.first is None:
            self.first = rgb.copy()
            for _ in range(self.fps):              # hold the first frame for 1 s
                self.proc.stdin.write(rgb.tobytes())
                self.frames += 1
        self.last = rgb
        self.proc.stdin.write(rgb.tobytes())
        self.frames += 1

    def close(self, out_dir: Path):
        from PIL import Image
        if self.proc is None:
            return
        if self.last is not None:
            for _ in range(2 * self.fps):              # hold the last frame for 2 s
                self.proc.stdin.write(self.last.tobytes())
                self.frames += 1
            Image.fromarray(self.first).save(out_dir / 'first.png')
            Image.fromarray(self.last).save(out_dir / 'last.png')
        self.proc.stdin.close()
        self.proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('variant')
    parser.add_argument('--out', default=str(ROOT / 'results' / 'visuals' / 'videos'))
    parser.add_argument('--size', default='3840x2160')
    parser.add_argument('--every', type=int, default=4)
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--codec', choices=['libx264', 'libx265'], default='libx265')
    parser.add_argument('--fovy', type=float, default=40.0)
    parser.add_argument('--lift', type=float, default=0.08, help='raise the look-at point (m)')
    parser.add_argument('--preview', action='store_true', help='only render the start frame to <out>/<variant>_preview.png')
    args = parser.parse_args()
    W, H = (int(x) for x in args.size.lower().split('x'))
    fps = int(round(1.0 / (0.005 * args.every)))
    if args.preview:
        from PIL import Image
        from mujoco_port.tools.render_semantic_views import load_env
        env = load_env(args.variant)
        rec = Recorder(None, (W, H), 1, args.crf, fps, fovy=args.fovy, lift=args.lift)
        rec._setup(env.pr._world)
        rec.renderer.update_scene(env.pr._world.d, rec.cam, scene_option=rec.opt)
        Path(args.out).mkdir(parents=True, exist_ok=True)
        Image.fromarray(rec.renderer.render()).save(Path(args.out).resolve() / f'{args.variant}_preview.png')
        return 0
    out_dir = Path(args.out).resolve() / args.variant
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    os.chdir(tempfile.mkdtemp(prefix='record_'))        # pddlstream writes ./temp

    import sim_backend  # noqa: F401
    from pyrep import PyRep
    recorder = Recorder(out_dir / f'{args.variant}.mp4', (W, H), args.every, args.crf, fps, codec=args.codec,
                        fovy=args.fovy, lift=args.lift)
    original_step = PyRep.step

    def step(self):
        original_step(self)
        recorder.frame(self._world)
    PyRep.step = step

    from llm_pipeline.oracle_trial_runner import run_oracle_trial
    from llm_pipeline.flags import PipelineFlags
    flags = PipelineFlags.from_assignments(['memory.enabled=true', 'replan.trigger_mode=if_rule',
                                            'replan.output_mode=corrective', 'parallel.enabled=true'])
    started = time.time()
    try:
        record = run_oracle_trial(args.variant, out_dir / 'trial', headless=True, flags=flags, seed=args.seed)
    finally:
        recorder.close(out_dir)
    info = {
        'variant': args.variant, 'seed': args.seed, 'size': [W, H], 'fps': fps, 'every_steps': args.every,
        'crf': args.crf, 'codec': args.codec + ' yuv420p', 'multisampling': 8, 'frames': recorder.frames,
        'sim_steps': recorder.steps, 'video_seconds': round(recorder.frames / fps, 1),
        'wall_seconds': round(time.time() - started, 1),
        'camera': {'lookat': list(map(float, recorder.cam.lookat)) if recorder.cam else None,
                   'distance': float(recorder.cam.distance) if recorder.cam else None,
                   'azimuth': -35.0, 'elevation': -35.264, 'fovy': args.fovy},
        'success': record.get('episode_success'), 'completed_actions': record.get('completed_actions'),
        'bytes': (out_dir / f'{args.variant}.mp4').stat().st_size if (out_dir / f'{args.variant}.mp4').exists() else None,
    }
    (out_dir / 'video.json').write_text(json.dumps(info, indent=1, default=str))
    print(json.dumps({k: info[k] for k in ('variant', 'success', 'frames', 'video_seconds', 'wall_seconds', 'bytes')}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
