#!/usr/bin/env python3
"""Replay a recorded trial (ROBUST-TAMP or an external baseline) in MuJoCo and render it as an
isometric video.

    python record_trial_replay.py --repo <checkout of the trial's code> --framework <name> \
        --trial <run_dir>/<FINAL.V>/seed_XX --variant FINAL.V --seed XX --icl-mode zero_shot \
        --out <dir> [--size 3840x2160] [--crf 18] [--font OpenSans.ttf]

The trial is run again with the code it was recorded with (``--repo``), its seed and its variant; every
foundation-model call is answered with the answer recorded in that trial, so no model is queried:

* baselines (vlm_tamp, owl_tamp, inner_monologue, epog): the recorded ``prompts/*.exchange.json``
  responses, in call order, through the baseline's own pipeline (its ``responder`` hook);
* robust_tamp: the initial answer from its exchange record; each discovery-triggered corrective answer
  rebuilt from the accepted blocks of the trial log (``insertion`` event), released only after the robot
  has executed as many independent actions as it did while the recorded answer was being generated
  (``parallel`` event), so the execution order matches the recorded one. A corrective answer that was
  rejected and re-queried in the recording is answered directly with its accepted revision (the rejected
  text was not recorded); this changes the call count, not the executed actions.

After the run, the executed actions are compared with the recorded ones (``video.json``: ``replay_matches``).
Frames are rendered every ``--every`` simulator steps (default 4 = 50 fps of simulated time) from a fixed
isometric camera framed on the task objects, with 8x multisampling, and encoded with libx265. A caption
shows the framework, variant and seed, and the action being executed. Model inference time is not shown
(answers are available immediately).
"""
from __future__ import annotations

import argparse
import glob
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

NAMES = {'robust_tamp': 'ROBUST-TAMP', 'vlm_tamp': 'VLM-TAMP', 'owl_tamp': 'OWL-TAMP',
         'inner_monologue': 'Inner Monologue', 'epog': 'EPoG'}
FOCUS_KEYWORDS = ('mug', 'spam', 'sugar', 'grocer', 'can', 'phone', 'cupboard', 'box', 'grill', 'plate',
                  'meat', 'chicken', 'steak', 'rack', 'diningtable', 'panda')
CAPTION = {'action': ''}


class Caption:
    """Text overlay drawn into the top-left corner of each frame (re-rendered only when the text changes)."""

    def __init__(self, font_path, width, title):
        from PIL import ImageFont
        scale = width / 3840.0
        self.font_big = ImageFont.truetype(font_path, int(64 * scale)) if font_path else ImageFont.load_default()
        self.font = ImageFont.truetype(font_path, int(50 * scale)) if font_path else ImageFont.load_default()
        self.pad = int(28 * scale)
        self.margin = int(40 * scale)
        self.title = title
        self.key = None
        self.patch = None

    def _render(self, action):
        from PIL import Image, ImageDraw
        lines = [(self.title, self.font_big), (f'Executing: {action}' if action else ' ', self.font)]
        widths = [self.font_big.getbbox(t)[2] if f is self.font_big else self.font.getbbox(t)[2] for t, f in lines]
        heights = [f.getbbox('Ag')[3] for _, f in lines]
        w = max(widths) + 2 * self.pad
        h = sum(heights) + int(0.5 * heights[1]) + 2 * self.pad
        img = Image.new('RGBA', (w, h), (20, 24, 30, 190))
        draw = ImageDraw.Draw(img)
        y = self.pad
        for (text, font), hh in zip(lines, heights):
            draw.text((self.pad, y), text, font=font, fill=(255, 255, 255, 255))
            y += hh + int(0.5 * heights[1])
        arr = np.asarray(img).astype(np.float32)
        self.patch = (arr[..., :3], arr[..., 3:4] / 255.0)

    def apply(self, rgb):
        action = CAPTION['action']
        if action != self.key:
            self.key = action
            self._render(action)
        color, alpha = self.patch
        h, w = color.shape[:2]
        y0 = x0 = self.margin
        region = rgb[y0:y0 + h, x0:x0 + w].astype(np.float32)
        rgb[y0:y0 + h, x0:x0 + w] = (color[:region.shape[0], :region.shape[1]] * alpha[:region.shape[0], :region.shape[1]]
                                     + region * (1 - alpha[:region.shape[0], :region.shape[1]])).astype(np.uint8)
        return rgb


class Recorder:
    def __init__(self, path, size, every, crf, fps, caption, fovy=40.0, lift=0.08):
        self.path, self.size, self.every, self.crf, self.fps = path, size, every, crf, fps
        self.caption, self.fovy, self.lift = caption, fovy, lift
        self.world = self.renderer = self.cam = self.opt = self.proc = None
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
            cam.lookat[2] += self.lift
        else:
            cam.lookat[:] = world.m.stat.center
            cam.distance = 2.3
        cam.azimuth, cam.elevation = -35.0, -35.264
        self.cam = cam
        cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
               '-r', str(self.fps), '-i', '-', '-c:v', 'libx265', '-preset', 'medium', '-crf', str(self.crf),
               '-tag:v', 'hvc1', '-x265-params', 'log-level=error:pools=8', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart', str(self.path)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def _write(self, rgb):
        self.proc.stdin.write(rgb.tobytes())
        self.frames += 1

    def frame(self, world):
        if self.world is None:
            self._setup(world)
        self.steps += 1
        if self.steps % self.every:
            return
        self.renderer.update_scene(world.d, self.cam, scene_option=self.opt)
        rgb = self.caption.apply(np.array(self.renderer.render()))
        if self.first is None:
            self.first = rgb.copy()
            for _ in range(self.fps):              # hold the first frame for 1 s
                self._write(rgb)
        self.last = rgb
        self._write(rgb)

    def close(self, out_dir):
        from PIL import Image
        if self.proc is None:
            return
        if self.last is not None:
            CAPTION['action'] = 'done'
            last = self.caption.apply(self.last.copy())
            for _ in range(2 * self.fps):          # hold the last frame for 2 s
                self._write(last)
            Image.fromarray(self.first).save(out_dir / 'first.png')
            Image.fromarray(last).save(out_dir / 'last.png')
        self.proc.stdin.close()
        self.proc.wait()


# --- recorded answers ------------------------------------------------------------------------------

def baseline_calls(trial: Path):
    calls = []
    for path in sorted(glob.glob(str(trial / 'prompts' / '*.exchange.json'))):
        data = json.loads(Path(path).read_text())
        purpose = Path(path).name[:-len('.exchange.json')].split('_', 2)[2]
        content = data['response']['choices'][0]['message'].get('content') or ''
        calls.append((purpose, content))
    return calls


def block_text(blocks):
    lines = ['FINAL BLOCKS:']
    for b in blocks:
        objects = ', '.join(b['objects'])
        if b.get('no_action'):
            lines += ['BLOCK', f'objects: {objects}', 'actions:', 'NO_ACTIONS', 'END BLOCK']
            continue
        insert = b.get('proposed_insert') or b.get('insert')
        insert = insert.replace('after:', 'after ') if insert else 'end'
        lines += ['BLOCK', f'objects: {objects}', f"urgency: {b.get('proposed_urgency') or b.get('urgency')}",
                  f'insert: {insert}', f"reason: {b.get('reason') or ''}", 'actions:', *b['actions'], 'END BLOCK']
    return '\n'.join(lines)


def robust_tamp_answers(trial: Path):
    events = [json.loads(line) for line in (trial / 'trial_log.jsonl').read_text().splitlines() if line.strip()]
    planning = [e for e in events if e['event'] == 'planning_event']
    insertions = [e for e in events if e['event'] == 'insertion']
    parallel = [e for e in events if e['event'] == 'parallel']
    initial = sorted(glob.glob(str(trial / 'prompts' / '*_initial.exchange.json')))
    answers, notes, ins_i, par_i = [], [], 0, 0
    for event in planning:
        reason = event.get('replan_reason') or ''
        if reason == 'initial':
            data = json.loads(Path(initial[0]).read_text())
            answers.append({'content': data['response']['choices'][0]['message'].get('content') or '', 'wait': 0})
        elif reason.startswith('trigger'):
            wait = len((parallel[par_i] if par_i < len(parallel) else {}).get('independent_actions_executed') or [])
            par_i += 1
            rejected = 0
            while ins_i < len(insertions) and not insertions[ins_i].get('accepted'):
                rejected += 1
                ins_i += 1
            if ins_i >= len(insertions):
                raise RuntimeError('no accepted corrective blocks recorded for a trigger')
            answers.append({'content': block_text(insertions[ins_i]['corrective_sub_plans']), 'wait': wait})
            ins_i += 1
            if rejected:
                notes.append(f'{rejected} rejected corrective answer(s) not reproduced (text not recorded); '
                             f'the accepted revision is given directly')
        elif reason == 'corrective_requery':
            continue
        else:
            raise RuntimeError(f'call type {reason!r} cannot be replayed (answer not recorded)')
    return answers, notes


# --- runs ------------------------------------------------------------------------------------------

def call_run_trial(trial_runner, **kwargs):
    accepted = inspect.signature(trial_runner.run_trial).parameters
    return trial_runner.run_trial(**{k: v for k, v in kwargs.items() if k in accepted})


def run_baseline(args, out_dir, log):
    from baselines.run_baseline_trial import BASELINE_FLAGS, PIPELINES
    from baselines.mock import MockPlanner
    from llm_pipeline import trial_runner
    from llm_pipeline.flags import PipelineFlags

    calls = baseline_calls(Path(args.trial))
    state = {'i': 0}

    def factory(pipeline):
        def respond(purpose, turns):
            i = state['i']
            state['i'] += 1
            if i >= len(calls):
                log.append(f'extra call {i} ({purpose}): no recorded answer')
                return ''
            recorded_purpose, content = calls[i]
            if recorded_purpose != purpose:
                log.append(f'call {i}: purpose {purpose} != recorded {recorded_purpose}')
            return content
        return respond

    base = PIPELINES[args.framework]()

    class ReplayPipeline(base):
        responder = staticmethod(factory)

        def __init__(self, config):
            super().__init__(config=config, planner=MockPlanner())

    original = trial_runner.LLMOnlyReplanningPipeline
    trial_runner.LLMOnlyReplanningPipeline = ReplayPipeline
    try:
        record = call_run_trial(trial_runner, variant_id=args.variant, model_alias='replay', icl_mode=args.icl_mode,
                                headless=True, output_dir=out_dir / 'trial', live_masks=False,
                                flags=PipelineFlags.from_assignments(list(BASELINE_FLAGS)), seed=args.seed,
                                trial_index=args.seed + 1, real_model=False, remote=False, vision=True,
                                model_type='vlm', planner_max_new_tokens=24576)
    finally:
        trial_runner.LLMOnlyReplanningPipeline = original
    if state['i'] != len(calls):
        log.append(f'{state["i"]} calls made, {len(calls)} recorded')
    return record


def run_robust_tamp(args, out_dir, log):
    from llm_pipeline import trial_runner
    from llm_pipeline.flags import PipelineFlags
    from llm_pipeline.pipeline import LLMOnlyReplanningPipeline
    from llm_pipeline.vllm_client import VLLMChatPlanner

    answers, notes = robust_tamp_answers(Path(args.trial))
    log.extend(notes)
    holder = {}

    class ReplayPlanner(VLLMChatPlanner):
        def _check_settings(self):
            return {'fingerprint': 'replay'}

        def chat(self, system_prompt, user_prompt, max_new_tokens, image=None):
            if not answers:
                log.append('extra planner call: no recorded answer')
                content, wait = '', 0
            else:
                answer = answers.pop(0)
                content, wait = answer['content'], answer['wait']
            if wait:
                executor = holder['pipeline'].executor
                start = len(executor.completed_primitive_actions)
                deadline, last_change, seen = time.time() + 3600, time.time(), start
                while len(executor.completed_primitive_actions) < start + wait and time.time() < deadline:
                    n = len(executor.completed_primitive_actions)
                    if n != seen:
                        seen, last_change = n, time.time()
                    if time.time() - last_change > 900:
                        log.append(f'concurrent execution stalled after {n - start} of {wait} actions')
                        break
                    time.sleep(0.2)
            return {'exchange': {'replay': True}, 'image_png': None, 'content': content, 'reasoning': '',
                    'finish_reason': 'stop', 'prompt_tokens': None, 'completion_tokens': None,
                    'generation_time_s': 0.0, 'sampling_preset': 'vl', 'settings_fingerprint': 'replay'}

    class ReplayPipeline(LLMOnlyReplanningPipeline):
        def __init__(self, config):
            super().__init__(config=config, planner=ReplayPlanner(model='qwen3-vl-8b-thinking'))
            holder['pipeline'] = self

    flags = PipelineFlags.from_assignments(['memory.enabled=true', 'replan.trigger_mode=if_rule',
                                            'replan.output_mode=corrective', 'replan.insertion_mode=planner',
                                            'parallel.enabled=true'])
    original = trial_runner.LLMOnlyReplanningPipeline
    trial_runner.LLMOnlyReplanningPipeline = ReplayPipeline
    try:
        record = call_run_trial(trial_runner, variant_id=args.variant, model_alias='qwen3-vl-8b-thinking',
                                icl_mode=args.icl_mode, headless=True, output_dir=out_dir / 'trial', live_masks=False,
                                flags=flags, seed=args.seed, trial_index=args.seed + 1, real_model=False,
                                remote=False, vision=True, model_type='vlm', planner_max_new_tokens=24576)
    finally:
        trial_runner.LLMOnlyReplanningPipeline = original
    if answers:
        log.append(f'{len(answers)} recorded answer(s) not used')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--repo', required=True)
    parser.add_argument('--framework', required=True, choices=sorted(NAMES))
    parser.add_argument('--trial', required=True)
    parser.add_argument('--variant', required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--icl-mode', default='zero_shot')
    parser.add_argument('--out', required=True)
    parser.add_argument('--size', default='3840x2160')
    parser.add_argument('--every', type=int, default=4)
    parser.add_argument('--crf', type=int, default=18)
    parser.add_argument('--font', default='')
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    sys.path[:0] = [str(repo / 'mujoco_port' / 'shim'), str(repo)]
    os.environ.setdefault('SIM_BACKEND', 'mujoco')
    os.environ['TAMP_PDDL_ROOT'] = str(repo)
    variant = args.variant.replace('FINAL.', '')
    stem = f'{args.framework}_{variant}_seed{args.seed:02d}'
    out_dir = Path(args.out).resolve() / args.framework / variant
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    os.chdir(tempfile.mkdtemp(prefix='replay_'))         # pddlstream writes ./temp

    W, H = (int(x) for x in args.size.lower().split('x'))
    fps = int(round(1.0 / (0.005 * args.every)))
    title = f'{NAMES[args.framework]}  |  {variant}  |  seed {args.seed}'
    recorder = Recorder(out_dir / f'{stem}.mp4', (W, H), args.every, args.crf, fps, Caption(args.font or None, W, title))

    import sim_backend  # noqa: F401
    from pyrep import PyRep
    original_step = PyRep.step

    def step(self):
        original_step(self)
        recorder.frame(self._world)
    PyRep.step = step

    from llm_pipeline import executor as executor_module
    original_emit = executor_module.DirectPrimitiveExecutor._emit_event

    def emit(self, event, **fields):
        if event == 'action_start':
            CAPTION['action'] = fields.get('action') or ''
        return original_emit(self, event, **fields)
    executor_module.DirectPrimitiveExecutor._emit_event = emit

    recorded = json.loads((Path(args.trial) / 'record.json').read_text())
    log, started = [], time.time()
    try:
        record = (run_robust_tamp if args.framework == 'robust_tamp' else run_baseline)(args, out_dir, log)
    finally:
        recorder.close(out_dir)
    replayed_actions = list(record.get('completed_actions') or [])
    recorded_actions = list(recorded.get('completed_actions') or [])
    info = {
        'framework': NAMES[args.framework], 'variant': variant, 'seed': args.seed, 'icl_mode': args.icl_mode,
        'source_trial': '/'.join(Path(args.trial).parts[-4:]),
        'recorded': {'success': recorded.get('episode_success'), 'partial_goal_completion': recorded.get('partial_goal_completion'),
                     'planner_invocations': recorded.get('planner_invocations'), 'completed_actions': recorded_actions},
        'replay': {'success': record.get('episode_success'), 'partial_goal_completion': record.get('partial_goal_completion'),
                   'completed_actions': replayed_actions},
        'replay_matches': replayed_actions == recorded_actions, 'notes': log,
        'video': {'file': f'{stem}.mp4', 'size': [W, H], 'fps': fps, 'playback': '1x simulated time',
                  'codec': 'libx265 yuv420p', 'crf': args.crf, 'multisampling': 8, 'frames': recorder.frames,
                  'seconds': round(recorder.frames / fps, 1),
                  'camera': {'lookat': list(map(float, recorder.cam.lookat)) if recorder.cam else None,
                             'distance': float(recorder.cam.distance) if recorder.cam else None,
                             'azimuth': -35.0, 'elevation': -35.264, 'fovy': 40.0}},
        'wall_seconds': round(time.time() - started, 1),
    }
    (out_dir / 'video.json').write_text(json.dumps(info, indent=1, default=str))
    print('REPLAY_RESULT ' + json.dumps({'framework': args.framework, 'variant': variant, 'seed': args.seed,
                                         'matches': info['replay_matches'], 'recorded_success': info['recorded']['success'],
                                         'replay_success': info['replay']['success'], 'seconds': info['video']['seconds'],
                                         'notes': log}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
