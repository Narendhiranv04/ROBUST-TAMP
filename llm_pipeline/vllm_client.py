"""Planner client for a vLLM server's OpenAI-compatible API (the real-model planner).

The lab server (``server/SERVER.md``) serves the pinned Qwen3-VL-8B-Thinking snapshot on
127.0.0.1:8000, reached through an SSH tunnel. One planner call is one
``POST /v1/chat/completions``:

* whether the model thinks is a property of the served model, not a request option
  (``PINNED_MODELS[...]['thinking']``): Qwen3-VL-8B-Thinking always thinks (its chat template
  opens every answer with ``<think>`` and has no switch), Qwen3-VL-8B-Instruct never does. For a
  thinking model vLLM's ``qwen3`` reasoning parser returns the thinking in ``reasoning_content``
  and the answer in ``content``. Only ``content`` is parsed; the thinking is logged separately;
* sampling is the model card's recommended thinking-mode setting (``PINNED_MODELS``):
  the VL preset for a request with an image, the text preset otherwise;
* there is no hidden second call (no format repair) and model outputs are never retried.

Everything that is not a model output is **infrastructure** (``planner_call_failed``: the
trial is excluded from scoring and rerun): connection errors after retries, HTTP errors,
timeouts, malformed responses, and a server whose settings differ from the ones recorded at
the start of the trial. The settings (served model, snapshot revision, context length, vLLM
version) are re-read and compared **before every call** (``settings_fingerprint``).

A timeout closes the HTTP connection; vLLM aborts a request whose client disconnected, so a
timed-out call does not keep generating on the GPU.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

from llm_pipeline.client import PlannerServerError
from llm_pipeline.failures import FailureCode
from llm_pipeline.pipeline_types import FailureEvent, FailureLayer, FailureSource, FailureStage, GoalCheckResult, PlanResult
from llm_pipeline.region_aliases import planner_region_name
from llm_pipeline.strict_parser import StrictActionParser, StrictParseError

# Served models and how each is called: llm_pipeline/model_profiles.py (pinned snapshot, model
# card sampling, thinking on/off, system-prompt packaging, vLLM arguments). Keyed by profile alias.
from llm_pipeline.model_profiles import PROFILES as PINNED_MODELS  # noqa: E402
from llm_pipeline.model_profiles import build_messages  # noqa: E402

SNAPSHOT_REVISION = re.compile(r'/snapshots/([0-9a-f]{40})/?$')
FINGERPRINT_KEYS = ('model_name', 'model_root', 'model_revision', 'max_model_len', 'vllm_version')


def settings_fingerprint(settings: Dict[str, Any]) -> str:
    payload = json.dumps({key: settings.get(key) for key in FINGERPRINT_KEYS}, sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def encode_image_png_base64(image: Any) -> Optional[str]:
    if image is None:
        return None
    from PIL import Image
    import numpy as np

    array = np.asarray(image)
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


class VLLMChatPlanner:
    """Planner backed by vLLM's OpenAI-compatible chat API (see module docstring)."""

    api = 'openai_chat'

    def __init__(self, server_url: Optional[str] = None, model: str = 'qwen3-vl-8b-thinking',
                 expected_revision: Optional[str] = None, request_timeout_s: Optional[float] = None):
        if requests is None:
            raise ImportError('requests library required for the vLLM planner')
        url = server_url or os.environ.get('VLLM_SERVER_URL') or os.environ.get('LLM_SERVER_URL') or 'http://127.0.0.1:8000'
        if not url.startswith(('http://', 'https://')):
            url = f'http://{url}'
        self.server_url = url.rstrip('/')
        pinned = dict(PINNED_MODELS.get(model, {}))
        self.profile = dict(pinned, alias=model) if pinned else {}
        # The profile alias (e.g. qwen3-8b-nothink) and the model vLLM serves (qwen3-8b).
        self.served_model = pinned.get('served_name', model)
        self.chat_template_kwargs = dict(pinned.get('chat_template_kwargs') or {})
        self.expected_revision = expected_revision or pinned.get('revision')
        self.sampling_presets = dict(pinned.get('sampling') or {})
        self.thinking_mode = pinned.get('thinking')     # 'on' / 'off': a property of the model
        self.model_type = pinned.get('model_type', 'vlm')
        self.request_timeout_s = float(request_timeout_s if request_timeout_s is not None
                                       else os.environ.get('LLM_REQUEST_TIMEOUT_S', '900'))
        self.http_timeout_s = float(os.environ.get('LLM_HTTP_TIMEOUT_S', '30'))
        self.connect_retries = max(1, int(os.environ.get('LLM_CONNECT_RETRIES', '5')))
        self.connect_backoff_s = float(os.environ.get('LLM_CONNECT_BACKOFF_S', '2'))
        self.model_alias = model
        self.model_name = pinned.get('repo', model)
        self.quantization = 'none'
        self.loaded = False
        self.parser = StrictActionParser()
        self.server_settings: Dict[str, Any] = {}
        self.start_fingerprint: Optional[str] = None
        self.last_request_summary: Dict[str, Any] = {}

    # -- settings --------------------------------------------------------------------
    def _get(self, path: str):
        last = None
        for attempt in range(1, self.connect_retries + 1):
            try:
                return requests.get(f'{self.server_url}{path}', timeout=self.http_timeout_s)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = exc
                if attempt < self.connect_retries:
                    time.sleep(self.connect_backoff_s * attempt)
        raise PlannerServerError('connection', f'{type(last).__name__}: {last}')

    def fetch_settings(self) -> Dict[str, Any]:
        """The server's settings from GET /v1/models and /version ({} if unreachable)."""
        try:
            models = self._get('/v1/models')
            version = self._get('/version')
            if models.status_code != 200 or version.status_code != 200:
                return {}
            entry = next((m for m in models.json().get('data', []) if m.get('id') == self.served_model), None)
            vllm_version = (version.json() or {}).get('version')
        except Exception:
            return {}
        root = (entry or {}).get('root') or ''
        match = SNAPSHOT_REVISION.search(root)
        settings = {
            'planner': 'vllm',
            'api': self.api,
            'server_url': self.server_url,
            'model_name': (entry or {}).get('id'),
            'model_root': root or None,
            'model_revision': match.group(1) if match else None,
            'max_model_len': (entry or {}).get('max_model_len'),
            'vllm_version': vllm_version,
            # The served model's own behaviour (pinned); vLLM has no repair call.
            'thinking_mode': self.thinking_mode,
            'format_repair': False,
            'sampling': dict(self.sampling_presets),
            'request_timeout_s': self.request_timeout_s,
            # How this profile calls the served model (logged with every trial).
            'profile_alias': self.profile.get('alias'),
            'model_type': self.model_type,
            'reasoning': self.profile.get('reasoning'),
            'system_prompt_mode': self.profile.get('system_prompt_mode', 'system'),
            'chat_template_kwargs': dict(self.chat_template_kwargs),
            'card_system_prompt': self.profile.get('card_system_prompt'),
            'card_system_prompt_sha256': self.profile.get('card_system_prompt_sha256'),
            'sampling_source': self.profile.get('source'),
        }
        settings['fingerprint'] = settings_fingerprint(settings)
        return settings

    def load_model(self) -> bool:
        self.server_settings = self.fetch_settings()
        self.loaded = bool(self.server_settings.get('model_name'))
        if self.loaded:
            self.start_fingerprint = self.server_settings['fingerprint']
        return self.loaded

    def planner_settings(self) -> Dict[str, Any]:
        return dict(self.server_settings or self.fetch_settings())

    def _check_settings(self) -> Dict[str, Any]:
        """Re-read the server's settings before a call; a change mid-trial is infrastructure."""
        current = self.fetch_settings()
        if not current:
            raise PlannerServerError('connection', 'the vLLM server does not answer GET /v1/models and /version')
        if not current.get('model_name'):
            raise PlannerServerError('model_missing', f'the server does not serve {self.served_model!r}')
        if self.start_fingerprint is not None and current['fingerprint'] != self.start_fingerprint:
            raise PlannerServerError('settings_changed',
                                     f'server settings changed during the trial (fingerprint '
                                     f'{self.start_fingerprint} -> {current["fingerprint"]})')
        return current

    # -- planner calls ----------------------------------------------------------------
    @staticmethod
    def _infrastructure_result(error: PlannerServerError, started_at: float, timing=None) -> PlanResult:
        event = FailureEvent(
            failure_id=FailureCode.PLANNER_CALL_FAILED, stage=FailureStage.BEFORE_EXECUTION,
            source=FailureSource.VALIDATION, action=None, evidence={'kind': error.kind, 'detail': error.detail},
            failure_layer=FailureLayer.LAYER_1, should_replan=False,
            message=f'Planner call failed ({error.kind}): {error.detail}',
        )
        return PlanResult(False, [], '', time.time() - started_at, event.message, event, timing=timing or error.timing)

    def _messages(self, system_prompt: str, user_prompt: str, image_b64: Optional[str]) -> List[Dict[str, Any]]:
        return build_messages(self.profile or {'system_prompt_mode': 'system'}, system_prompt, user_prompt, image_b64)

    @staticmethod
    def _loggable_request(body: Dict[str, Any], image_sha256: Optional[str]) -> Dict[str, Any]:
        """The request body as sent, with the image's base64 replaced by its sha256 (the PNG is saved)."""
        logged = json.loads(json.dumps(body))
        for message in logged.get('messages', []):
            content = message.get('content')
            if isinstance(content, list):
                for part in content:
                    if part.get('type') == 'image_url':
                        part['image_url'] = {'url': f'<png sha256={image_sha256}>'}
        return logged

    def chat(self, system_prompt: str, user_prompt: str, max_new_tokens: int, image: Any = None) -> Dict[str, Any]:
        """One chat completion. Raises PlannerServerError for anything that is not a model output."""
        settings = self._check_settings()
        if self.model_type == 'llm':
            image = None             # a text-only model never receives the image
        image_b64 = encode_image_png_base64(image) if image is not None else None
        image_png = base64.b64decode(image_b64) if image_b64 else None
        image_sha256 = hashlib.sha256(image_png).hexdigest() if image_png else None
        preset = 'vl' if image_b64 else 'text'
        sampling = dict(self.sampling_presets.get(preset) or {})
        body = {
            'model': self.served_model,
            'messages': self._messages(system_prompt, user_prompt, image_b64),
            'max_tokens': int(max_new_tokens),
            **sampling,
        }
        if self.chat_template_kwargs:
            body['chat_template_kwargs'] = dict(self.chat_template_kwargs)
        started = time.monotonic()
        try:
            response = requests.post(f'{self.server_url}/v1/chat/completions', json=body,
                                     timeout=(self.http_timeout_s, self.request_timeout_s))
        except requests.Timeout as exc:
            # Closing the connection makes vLLM abort the request (no orphaned generation).
            raise PlannerServerError('generation_timeout', f'no answer within {self.request_timeout_s:.0f} s: {exc}')
        except requests.ConnectionError as exc:
            raise PlannerServerError('connection', f'{type(exc).__name__}: {exc}')
        elapsed = time.monotonic() - started
        if response.status_code != 200:
            raise PlannerServerError('http_status', f'{response.status_code} - {response.text[:300]}')
        try:
            data = response.json()
            choice = data['choices'][0]
            message = choice['message']
        except Exception as exc:
            raise PlannerServerError('bad_response', f'{type(exc).__name__}: {exc}')
        if data.get('model') not in (None, self.served_model):
            raise PlannerServerError('settings_changed', f'response from model {data.get("model")!r}')
        usage = data.get('usage') or {}
        exchange = {
            'profile_alias': self.profile.get('alias'),
            'served_model': self.served_model,
            'server_url': self.server_url,
            'request': self._loggable_request(body, image_sha256),
            'response': data,
            'http_elapsed_s': round(elapsed, 4),
            'image_sha256': image_sha256,
            'settings_fingerprint': settings['fingerprint'],
        }
        return {
            'exchange': exchange,
            'image_png': image_png,
            'content': message.get('content') or '',
            'reasoning': message.get('reasoning_content') or message.get('reasoning') or '',
            'finish_reason': choice.get('finish_reason'),
            'prompt_tokens': usage.get('prompt_tokens'),
            'completion_tokens': usage.get('completion_tokens'),
            'generation_time_s': round(elapsed, 4),
            'sampling_preset': preset,
            'settings_fingerprint': settings['fingerprint'],
        }

    def plan(self, bundle: Any) -> PlanResult:
        metadata = dict(getattr(bundle, 'metadata', {}) or {})
        held_object = metadata.get('held_object')
        max_new_tokens = int(metadata.get('max_new_tokens', 4096) or 4096)
        images = list(getattr(bundle, 'images', None) or [])
        image = images[0] if (images and metadata.get('use_vision', True)) else None
        if self.model_type == 'llm':
            image = None
        started_at = time.time()
        self.last_request_summary = {
            'valid_objects': self.parser.planner_visible_objects() if hasattr(self.parser, 'planner_visible_objects')
            else sorted(self.parser.valid_objects),
            'valid_regions': sorted({planner_region_name(r) for r in self.parser.valid_regions}),
            'image_present': image is not None,
        }
        try:
            out = self.chat(bundle.system_prompt, bundle.user_prompt, max_new_tokens, image=image)
        except PlannerServerError as exc:
            return self._infrastructure_result(exc, started_at)
        except Exception as exc:  # anything else on the way to the server is infrastructure too
            return self._infrastructure_result(PlannerServerError('client_error', f'{type(exc).__name__}: {exc}'), started_at)
        timing = {'queue_wait_s': None, 'generation_time_s': out['generation_time_s'],
                  'finish_reason': out['finish_reason'], 'prompt_tokens': out['prompt_tokens'],
                  'completion_tokens': out['completion_tokens'], 'sampling_preset': out['sampling_preset'],
                  'settings_fingerprint': out['settings_fingerprint']}
        raw_output = out['content']
        inference_time = time.time() - started_at
        if metadata.get('output_format') == 'corrective_blocks':
            # Corrective blocks are parsed and merged by the pipeline; an empty answer is a
            # model output (an invalid block list), not an infrastructure failure.
            return PlanResult(success=bool(raw_output.strip()), actions=[], raw_output=raw_output,
                              inference_time=inference_time,
                              error_message=None if raw_output.strip() else self._empty_reason(out),
                              timing=timing, reasoning=out['reasoning'],
                              exchange=out['exchange'], image_png=out['image_png'])
        try:
            actions = self.parser.parse(raw_output, held_object=held_object)
            return PlanResult(True, actions, raw_output, inference_time, timing=timing, reasoning=out['reasoning'],
                              exchange=out['exchange'], image_png=out['image_png'])
        except StrictParseError as exc:
            fact = exc.fact
            if out['finish_reason'] == 'length':
                fact = (fact or '') + ' The answer was cut off at the output token limit.'
            event = FailureEvent(
                failure_id=exc.failure_id, stage=FailureStage.BEFORE_EXECUTION, source=FailureSource.VALIDATION,
                action=None, evidence={'line_number': exc.line_number, 'raw_output': raw_output, 'fact': fact,
                                       'finish_reason': out['finish_reason']},
                failure_layer=FailureLayer.LAYER_1, should_replan=True, message=str(exc),
            )
            return PlanResult(False, [], raw_output, inference_time, event.message, event, timing=timing,
                              reasoning=out['reasoning'], exchange=out['exchange'], image_png=out['image_png'])

    @staticmethod
    def _empty_reason(out: Dict[str, Any]) -> str:
        if out.get('finish_reason') == 'length':
            return 'empty planner answer (cut off at the output token limit while thinking)'
        return 'empty planner answer'

    def generate_plan(self, system_prompt: str, user_prompt: str, icl_mode: str, max_new_tokens: int = 4096,
                      temperature: float = 0.0, held_object: Optional[str] = None, bundle: Any = None) -> PlanResult:
        from llm_pipeline.pipeline_types import PromptBundle

        bundle = bundle or PromptBundle(goal_text=user_prompt, system_prompt=system_prompt, user_prompt=user_prompt,
                                        visible_objects=[], valid_regions=[], icl_mode=icl_mode,
                                        metadata={'held_object': held_object, 'max_new_tokens': max_new_tokens})
        return self.plan(bundle)

    def check_goal_completion(self, system_prompt: str, user_prompt: str, icl_mode: str, max_new_tokens: int = 128,
                              temperature: float = 0.0, held_object: Optional[str] = None,
                              image: Any = None) -> GoalCheckResult:
        started = time.time()
        try:
            out = self.chat(system_prompt, user_prompt, max_new_tokens, image=image)
        except PlannerServerError as exc:
            return GoalCheckResult(False, False, '', time.time() - started, error_message=f'{exc.kind}: {exc.detail}')
        text = out['content'].strip()
        satisfied = text.upper().startswith('GOAL_COMPLETE')
        return GoalCheckResult(bool(text), satisfied, text, time.time() - started,
                               reason=text.partition(':')[2].strip())

    def get_debug_info(self) -> Dict[str, Any]:
        return {'model_alias': self.model_alias, 'model_name': self.model_name, 'model_type': self.model_type,
                'quantization': 'none', 'loaded': self.loaded, 'server_url': self.server_url,
                'settings': dict(self.server_settings), 'last_request': dict(self.last_request_summary)}
