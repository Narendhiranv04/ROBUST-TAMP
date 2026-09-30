"""Shared layer for the external baselines (VLM-TAMP, OWL-TAMP) in our kitchen and grill scenes.

The baselines run in the same MuJoCo scenes as our system, with the same executor (PDDLStream
place/pick refinement with stable-pose, IK and motion samplers), the same planner model and
sampling (llm_pipeline/model_profiles.py), and the same scoring (trial_runner._validate_trial ->
trial_end -> evaluation/model_run_report.paper_outcome). Only the planning method differs.

* ``observe``: what a baseline sees, taken from the scene state our planner receives (visible
  objects and their regions, every lid with its state, the gripper, the regions) and the same
  composite camera image. Nothing is read from hidden simulator state.
* ``SymbolicDomain``: pick / place / open / close with exactly the preconditions and effects
  stated to our planner (llm_pipeline/prompt_v2.ACTION_DEFINITIONS). The baselines use it for
  their own task-level search (VLM-TAMP: refining a subgoal; OWL-TAMP: the sketch search).
* ``ModelChat``: multi-turn chat completions through the planner profile's vLLM client, with its
  settings check, card sampling, and the exact request/response saved for every call.
* ``BaselinePipeline``: the trial pipeline with our replanning components switched off (no IF
  rule, no discovery trigger, no memory, no corrective blocks, no parallel planning); a baseline
  implements ``run_baseline`` and returns through ``baseline_summary``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from llm_pipeline.failures import FailureCode, TerminationReason
from llm_pipeline.pipeline import ExecutionCycleRecord, LLMOnlyReplanningPipeline
from llm_pipeline.pipeline_types import (DirectAction, FailureEvent, FailureLayer, FailureSource, FailureStage)
from llm_pipeline.prompt_v2 import ACTION_DEFINITIONS, LID_OBJECTS, LID_REGIONS, LID_TOP_REGIONS
from llm_pipeline.region_aliases import planner_region_name

# ---------------------------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------------------------


@dataclass
class Observation:
    objects: Dict[str, Optional[str]]          # visible movable object -> region (None: in the gripper)
    lids: Dict[str, bool]                      # every lid of the scene -> open
    holding: Optional[str]
    regions: List[str]                         # planner region names
    image: object = None                       # composite RGB (numpy) or None
    poses: Dict[str, tuple] = field(default_factory=dict)          # object -> world pose (x, y, z, ...)
    region_boxes: Dict[str, tuple] = field(default_factory=dict)   # region -> ((x0, y0, z0), (x1, y1, z1))

    def symbolic(self) -> 'SymState':
        return SymState(
            regions=tuple(sorted((o, r) for o, r in self.objects.items() if r is not None and o != self.holding)),
            holding=self.holding,
            open_lids=frozenset(l for l, is_open in self.lids.items() if is_open),
        )

    def to_dict(self) -> dict:
        return {'objects': dict(self.objects), 'lids': dict(self.lids), 'holding': self.holding,
                'regions': list(self.regions)}


def observe(pipeline) -> Observation:
    """The current observation, from the same scene state and image our planner is given."""
    state = pipeline._build_scene_state()
    builder = pipeline.context_builder
    regions = list(builder._regions(state))
    lids = {lid: bool(is_open) for lid, is_open in (getattr(state, 'lid_states', {}) or {}).items()
            if lid in builder._lids()}
    holding = getattr(pipeline.executor, 'held_object', None)
    region_map = dict(getattr(state, 'object_region_map', {}) or {})
    objects = {}
    for name in state.visible_objects:
        if name in LID_OBJECTS:
            continue
        region = region_map.get(name)
        objects[name] = None if name == holding else (planner_region_name(region) if region else None)
    if holding and holding not in objects:
        objects[holding] = None
    boxes = {}
    for region, box in (getattr(state, 'region_map', {}) or {}).items():
        try:
            lo, hi = box
            boxes[planner_region_name(region)] = (tuple(float(v) for v in lo), tuple(float(v) for v in hi))
        except Exception:
            continue
    poses = {name: tuple(float(v) for v in pose) for name, pose in (getattr(state, 'pose_map', {}) or {}).items()}
    image = state.images[0] if getattr(state, 'images', None) else None
    return Observation(objects=objects, lids=lids, holding=holding, regions=regions, image=image,
                       poses=poses, region_boxes=boxes)


def region_closed_by(region: str) -> Optional[str]:
    for lid, closed_off in LID_REGIONS.items():
        if region in {planner_region_name(r) for r in closed_off}:
            return lid
    return None


def lid_top_region(lid: str) -> Optional[str]:
    top = LID_TOP_REGIONS.get(lid)
    return planner_region_name(top) if top else None


# ---------------------------------------------------------------------------------------------
# Symbolic domain (the action semantics stated to our planner)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SymState:
    regions: Tuple[Tuple[str, str], ...]       # sorted (object, region) pairs
    holding: Optional[str]
    open_lids: FrozenSet[str]

    def region_of(self, obj: str) -> Optional[str]:
        return dict(self.regions).get(obj)

    def with_region(self, obj: str, region: Optional[str]) -> Tuple[Tuple[str, str], ...]:
        items = [(o, r) for o, r in self.regions if o != obj]
        if region is not None:
            items.append((obj, region))
        return tuple(sorted(items))


class SymbolicDomain:
    """pick(o), place(o, r), open(l), close(l) over the observed objects, regions and lids."""

    def __init__(self, objects: Iterable[str], regions: Iterable[str], lids: Iterable[str]):
        self.objects = sorted(set(objects))
        self.regions = list(dict.fromkeys(regions))
        self.lids = sorted(set(lids))

    def _reachable(self, state: SymState, region: Optional[str]) -> bool:
        lid = region_closed_by(region) if region else None
        return lid is None or lid in state.open_lids

    def applicable(self, state: SymState, action: Tuple[str, ...]) -> bool:
        name, args = action[0], action[1:]
        if name == 'pick':
            (o,) = args
            # An observed object whose region the observation could not resolve (e.g. set down between
            # two named regions) is still pickable; objects in a region behind a closed lid are not observed.
            return state.holding is None and o in self.objects and self._reachable(state, state.region_of(o))
        if name == 'place':
            o, r = args
            return state.holding == o and r in self.regions and self._reachable(state, r)
        if name == 'open':
            (l,) = args
            top = lid_top_region(l)
            return (state.holding is None and l in self.lids and l not in state.open_lids
                    and not any(r == top for _, r in state.regions))
        if name == 'close':
            (l,) = args
            return state.holding is None and l in self.lids and l in state.open_lids
        return False

    @staticmethod
    def apply(state: SymState, action: Tuple[str, ...]) -> SymState:
        name, args = action[0], action[1:]
        if name == 'pick':
            return SymState(state.with_region(args[0], None), args[0], state.open_lids)
        if name == 'place':
            return SymState(state.with_region(args[0], args[1]), None, state.open_lids)
        if name == 'open':
            return SymState(state.regions, state.holding, state.open_lids | {args[0]})
        if name == 'close':
            return SymState(state.regions, state.holding, state.open_lids - {args[0]})
        raise ValueError(action)

    def ground_actions(self) -> List[Tuple[str, ...]]:
        """All ground actions (the relaxed grounding: every argument combination of the observed symbols)."""
        out = [('pick', o) for o in self.objects]
        out += [('place', o, r) for o in self.objects for r in self.regions]
        out += [('open', l) for l in self.lids] + [('close', l) for l in self.lids]
        return out

    def successors(self, state: SymState):
        for action in self.ground_actions():
            if self.applicable(state, action):
                yield action, self.apply(state, action)

    def search(self, start: SymState, goal: Callable[[SymState], bool], max_expansions: int = 20000,
               max_depth: int = 12) -> Optional[List[Tuple[str, ...]]]:
        """Breadth-first search for the shortest action sequence reaching ``goal``."""
        if goal(start):
            return []
        frontier = [(start, [])]
        seen = {start}
        expansions = 0
        while frontier:
            next_frontier = []
            for state, plan in frontier:
                expansions += 1
                if expansions > max_expansions or len(plan) >= max_depth:
                    return None
                for action, nxt in self.successors(state):
                    if nxt in seen:
                        continue
                    if goal(nxt):
                        return plan + [action]
                    seen.add(nxt)
                    next_frontier.append((nxt, plan + [action]))
            frontier = next_frontier
        return None


def action_text(action: Tuple[str, ...]) -> str:
    return f"{action[0]}({', '.join(action[1:])})"


def parse_action_text(text: str) -> Optional[Tuple[str, ...]]:
    text = text.strip().strip('`').strip()
    if '(' not in text or not text.endswith(')'):
        return None
    name, _, rest = text.partition('(')
    args = tuple(a.strip().strip('\'"') for a in rest[:-1].split(',') if a.strip())
    return (name.strip().lower(),) + args


# ---------------------------------------------------------------------------------------------
# Model access
# ---------------------------------------------------------------------------------------------


class ModelCallError(RuntimeError):
    """The model server did not answer (infrastructure, not a model output)."""


class ModelChat:
    """Chat completions (one or more turns) with the planner profile's client and sampling.

    ``responder`` replaces the server for mock trials: a callable (purpose, messages) -> text.
    """

    def __init__(self, planner, pipeline, max_new_tokens: int, responder=None):
        self.planner = planner
        self.pipeline = pipeline
        self.max_new_tokens = int(max_new_tokens)
        self.responder = responder
        self.calls: List[dict] = []

    def _image_part(self, image):
        from llm_pipeline.vllm_client import encode_image_png_base64

        b64 = encode_image_png_base64(image)
        png = base64.b64decode(b64)
        return b64, png, hashlib.sha256(png).hexdigest()

    def complete(self, turns: Sequence[Tuple[str, str]], image=None, purpose: str = '', system: str = '') -> dict:
        """``turns``: [(role, text)], the last one a user turn; the image goes with the first user turn."""
        planner = self.planner
        text_only = getattr(planner, 'model_type', 'vlm') == 'llm'
        image_b64 = png = sha = None
        if image is not None and not text_only:
            image_b64, png, sha = self._image_part(image)
        messages = []
        profile = getattr(planner, 'profile', None) or {'system_prompt_mode': 'system'}
        first_user = next(i for i, (role, _) in enumerate(turns) if role == 'user')
        for index, (role, text) in enumerate(turns):
            if index == first_user:
                from llm_pipeline.model_profiles import build_messages

                messages.extend(build_messages(profile, system, text, image_b64))
            else:
                messages.append({'role': role, 'content': text})
        started = time.monotonic()
        if self.responder is not None:
            content = self.responder(purpose, turns)
            out = {'content': content, 'reasoning': '', 'finish_reason': 'stop', 'prompt_tokens': None,
                   'completion_tokens': None, 'exchange': {'mock': True, 'purpose': purpose}, 'image_png': png,
                   'sampling_preset': None, 'settings_fingerprint': None}
        else:
            out = self._post(messages, png, sha)
        latency = time.monotonic() - started
        record = self._log(purpose, system, turns, out, latency, image_present=png is not None)
        self.calls.append(record)
        return out

    def _post(self, messages, png, sha) -> dict:
        import requests

        planner = self.planner
        from llm_pipeline.vllm_client import PlannerServerError

        try:
            settings = planner._check_settings()
        except PlannerServerError as exc:
            raise ModelCallError(f'{exc.kind}: {exc.detail}')
        preset = 'vl' if png is not None else 'text'
        body = {'model': planner.served_model, 'messages': messages, 'max_tokens': self.max_new_tokens,
                **dict(planner.sampling_presets.get(preset) or {})}
        if planner.chat_template_kwargs:
            body['chat_template_kwargs'] = dict(planner.chat_template_kwargs)
        started = time.monotonic()
        try:
            response = requests.post(f'{planner.server_url}/v1/chat/completions', json=body,
                                     timeout=(planner.http_timeout_s, planner.request_timeout_s))
        except requests.RequestException as exc:
            raise ModelCallError(f'{type(exc).__name__}: {exc}')
        elapsed = time.monotonic() - started
        if response.status_code != 200:
            raise ModelCallError(f'http {response.status_code}: {response.text[:300]}')
        try:
            data = response.json()
            choice = data['choices'][0]
            message = choice['message']
        except Exception as exc:
            raise ModelCallError(f'bad response: {exc}')
        usage = data.get('usage') or {}
        return {
            'content': message.get('content') or '',
            'reasoning': message.get('reasoning_content') or message.get('reasoning') or '',
            'finish_reason': choice.get('finish_reason'),
            'prompt_tokens': usage.get('prompt_tokens'), 'completion_tokens': usage.get('completion_tokens'),
            'exchange': {'profile_alias': planner.profile.get('alias'), 'served_model': planner.served_model,
                         'server_url': planner.server_url, 'request': planner._loggable_request(body, sha),
                         'response': data, 'http_elapsed_s': round(elapsed, 4), 'image_sha256': sha,
                         'settings_fingerprint': settings['fingerprint']},
            'image_png': png, 'sampling_preset': preset, 'settings_fingerprint': settings['fingerprint'],
        }

    def _log(self, purpose, system, turns, out, latency, image_present) -> dict:
        pipeline = self.pipeline
        logger = pipeline.trial_logger
        user_text = '\n\n'.join(f'=== {role.upper()} ===\n{text}' for role, text in turns)
        prompt_path = logger.save_prompt(pipeline.step, system, user_text, kind=purpose or 'call')
        saved = logger.save_exchange(prompt_path, out.get('exchange'), out.get('image_png'))
        request = ((out.get('exchange') or {}).get('request') or {})
        from llm_pipeline.trial_log import prompt_hash

        record = dict(
            step=pipeline.step, kind=purpose, prompt_hash=prompt_hash(system, user_text), output_format='baseline', replan_reason=purpose,
            plan_check_requery=False, trigger_code=None, trigger_objects=[],
            model=getattr(self.planner, 'model_name', None), prompt_path=prompt_path, image_present=image_present,
            raw_output=out.get('content'), reasoning=out.get('reasoning'), parsed_output=[],
            planner_call_latency_s=round(float(latency), 4), wall_latency_s=round(float(latency), 4),
            queue_wait_s=None, generation_time_s=round(float(latency), 4), finish_reason=out.get('finish_reason'),
            prompt_tokens=out.get('prompt_tokens'), completion_tokens=out.get('completion_tokens'),
            sampling_preset=out.get('sampling_preset'), settings_fingerprint=out.get('settings_fingerprint'),
            profile_alias=(out.get('exchange') or {}).get('profile_alias'),
            request_params={k: v for k, v in request.items() if k != 'messages'} or None,
            exchange_path=saved.get('exchange_path'), image_path=saved.get('image_path'),
            image_sha256=(out.get('exchange') or {}).get('image_sha256'),
            response_id=((out.get('exchange') or {}).get('response') or {}).get('id'),
        )
        pipeline._log_event('planning_event', **record)
        return record

    @property
    def total_latency_s(self) -> float:
        return float(sum(c['planner_call_latency_s'] for c in self.calls))


def strip_reasoning(text: str) -> str:
    """The answer after any inline reasoning block (the server's reasoning parser usually splits it)."""
    if '</think>' in text:
        text = text.rsplit('</think>', 1)[1]
    return text.strip()


# ---------------------------------------------------------------------------------------------
# Trial pipeline
# ---------------------------------------------------------------------------------------------


class BaselinePipeline(LLMOnlyReplanningPipeline):
    """Our trial pipeline (scene, executor, logging, scoring) running a baseline's own loop."""

    baseline_name = 'baseline'
    responder = None           # mock trials: a responder factory (pipeline -> callable)

    def initialize(self, env=None) -> bool:
        ok = super().initialize(env=env)
        if ok:
            # Our system's replanning triggers are not part of a baseline.
            if hasattr(self.executor, 'set_trigger_check'):
                self.executor.set_trigger_check(None)
            inner = getattr(self.failure_checker, 'inner', self.failure_checker)
            if hasattr(inner, 'replan_on_new_visibility'):
                inner.replan_on_new_visibility = False
        return ok

    # -- helpers ---------------------------------------------------------------
    def chat(self) -> ModelChat:
        if not hasattr(self, '_chat'):
            responder = self.responder(self) if self.responder is not None else None
            self._chat = ModelChat(self.planner, self, self.config.planner_max_new_tokens, responder=responder)
        return self._chat

    @staticmethod
    def direct_actions(actions: Sequence[Tuple[str, ...]]) -> List[DirectAction]:
        """Executor actions; planner-facing region names become internal ones, as our parser does."""
        from llm_pipeline.region_aliases import normalize_region_name

        out = []
        for a in actions:
            args = tuple(a[1:])
            if a[0] == 'place':
                args = (args[0], normalize_region_name(args[1]))
            out.append(DirectAction(a[0], args))
        return out

    def execute(self, actions: Sequence[Tuple[str, ...]]):
        """Execute primitive actions with our executor and failure checks; returns the outcome."""
        self.step += 1
        return self.executor.execute_actions(
            self.direct_actions(actions), self.failure_checker,
            pre_action_checks_enabled=True, post_action_checks_enabled=True,
        )

    @staticmethod
    def planning_failure(message: str, code: str = FailureCode.PDDL_NO_PLAN) -> FailureEvent:
        return FailureEvent(failure_id=code, stage=FailureStage.BEFORE_EXECUTION, source=FailureSource.VALIDATION,
                            action=None, evidence={'fact': message}, failure_layer=FailureLayer.LAYER_1,
                            should_replan=True, message=message)

    def record_cycle(self, is_replan: bool, planned: Sequence[str], raw_output: str, inference_time_s: float,
                     success: bool, error: Optional[str] = None, failure_event: Optional[FailureEvent] = None):
        cycle = ExecutionCycleRecord(
            cycle_number=len(self.cycles) + 1, is_replan=is_replan, icl_mode=self.config.icl_mode,
            planned_actions=list(planned), raw_output=raw_output, inference_time_s=float(inference_time_s),
            completed_actions=list(getattr(self.executor, 'completed_primitive_actions', []) or []),
            remaining_actions=list(getattr(self.executor, 'remaining_actions', []) or []),
            success=bool(success), error_message=error,
            failure_event=failure_event.to_dict() if failure_event is not None else None,
        )
        self.cycles.append(cycle)
        return cycle

    # -- run -------------------------------------------------------------------
    def run(self, goal_text: str) -> dict:
        if self.env is None:
            raise RuntimeError('Pipeline is not initialized')
        self.reset_episode_state()
        self._settle_environment()
        if self.segmentation_adapter is not None:
            self.segmentation_adapter.refresh_visibility(event='initial')
        started_at = time.time()
        self._baseline_trace: Dict[str, object] = {'baseline': self.baseline_name}
        failure_reason = None
        try:
            failure_reason = self.run_baseline(goal_text)
        except ModelCallError as exc:
            failure_reason = f'planner call failed: {exc}'
            self._set_termination(TerminationReason.INFRASTRUCTURE)
        self._set_termination(TerminationReason.PLAN_COMPLETED if failure_reason is None
                              else TerminationReason.NON_REPLANNABLE_FAILURE)
        self._log_event('baseline_trace', **json.loads(json.dumps(self._baseline_trace, default=str)))
        return self.baseline_summary(goal_text, started_at, failure_reason)

    def run_baseline(self, goal_text: str) -> Optional[str]:
        """Run the baseline; return None when its plan ran to the end, else why it stopped."""
        raise NotImplementedError

    def baseline_summary(self, goal_text: str, started_at: float, failure_reason: Optional[str]) -> dict:
        chat = self.chat()
        completed = list(getattr(self.executor, 'completed_primitive_actions', []) or [])
        final_scene_state = self._final_scene_state_summary()
        return {
            'success': failure_reason is None,
            'goal_text': goal_text,
            'model_alias': getattr(self.planner, 'model_alias', self.config.model_alias),
            'model_path': getattr(self.planner, 'model_name', self.config.model_alias),
            'model_type': self.config.effective_model_type,
            'quantization': 'none',
            'icl_mode': self.config.icl_mode,
            'prompt_mode': f'baseline:{self.baseline_name}',
            'replan_mode': 'baseline',
            'replanning_enabled': False,
            'execution_skipped': False,
            'text_only': not self.config.enable_vision,
            'use_vision': bool(self.config.enable_vision),
            'image_present': any(c.get('image_present') for c in chat.calls),
            'image_metadata': {},
            'segmentation_first': True,
            'use_remote_planner': bool(self.config.use_remote_planner),
            'remote_planner_url': self.config.remote_planner_url or None,
            'pre_action_checks_enabled': True,
            'post_action_checks_enabled': True,
            'goal_check_enabled': False,
            'planned_actions': list(self.cycles[0].planned_actions) if self.cycles else [],
            'completed_actions': completed,
            'remaining_actions': list(getattr(self.executor, 'remaining_actions', []) or []),
            'held_object': getattr(self.executor, 'held_object', None),
            'final_scene_state': final_scene_state,
            'final_object_region_map': dict(final_scene_state.get('object_region_map', {}) or {}),
            'initial_ground_truth': getattr(self, 'initial_ground_truth', None),
            'final_ground_truth': self._final_variant_ground_truth(),
            'final_lid_states': dict(final_scene_state.get('lid_states', {}) or {}),
            'last_goal_check': None,
            'last_failure_event': None,
            'failure_reason': failure_reason,
            'total_cycles': len(self.cycles),
            'total_replans': sum(1 for c in self.cycles if c.is_replan),
            'planner_invocations': len(chat.calls),
            'total_planner_time_s': chat.total_latency_s,
            'mean_planner_time_per_invocation_s': (chat.total_latency_s / len(chat.calls)) if chat.calls else None,
            'episode_time_s': time.time() - started_at,
            'cycles': [c.to_dict() for c in self.cycles],
            'baseline_trace': json.loads(json.dumps(self._baseline_trace, default=str)),
        }


def action_definitions_text(names=('pick', 'place', 'open', 'close')) -> str:
    return '\n'.join(ACTION_DEFINITIONS[n] for n in names if n in ACTION_DEFINITIONS)


__all__ = ['Observation', 'observe', 'SymState', 'SymbolicDomain', 'ModelChat', 'ModelCallError',
           'BaselinePipeline', 'action_text', 'parse_action_text', 'strip_reasoning', 'region_closed_by',
           'lid_top_region', 'action_definitions_text']
