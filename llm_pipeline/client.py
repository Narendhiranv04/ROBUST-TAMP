"""Remote client for the maintained text-only LLM planner server.

A planner call is submitted as a job (``POST /plan/submit``) and polled
(``GET /plan/jobs/<id>``). The request timeout (``LLM_REQUEST_TIMEOUT_S``, 300 s)
covers **generation only**; waiting in the server's queue has its own, longer limit
(``LLM_QUEUE_TIMEOUT_S``, 7200 s). Connection errors are retried
(``LLM_CONNECT_RETRIES``); model outputs are never retried here. A server error, a
connection that cannot be re-established or a timeout becomes a ``planner_call_failed``
failure event: the trial ends as ``infrastructure``, is excluded from scoring and is
rerun by the matrix runner.
"""

from __future__ import annotations

import base64
import os
import time
from io import BytesIO
from typing import Any, Dict, Optional

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    import requests
    HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    HAS_REQUESTS = False
    requests = None

from llm_pipeline.failures import FailureCode
from llm_pipeline.region_aliases import planner_region_name
from llm_pipeline.strict_parser import StrictActionParser, StrictParseError
from llm_pipeline.pipeline_types import FailureEvent, FailureLayer, FailureSource, FailureStage, GoalCheckResult, PlanResult


class PlannerServerError(RuntimeError):
    """The planner server could not answer (not a model output): infrastructure."""

    def __init__(self, kind: str, detail: str, timing: Optional[Dict[str, Any]] = None):
        super().__init__(f'{kind}: {detail}')
        self.kind = kind
        self.detail = detail
        self.timing = timing


class RemoteTextLLMPlanner:
    """Drop-in remote planner for the maintained llm_pipeline."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        request_timeout_s: Optional[float] = None,
        expected_model=None,
    ):
        if not HAS_REQUESTS:
            raise ImportError('requests library required for remote planner mode')

        url = (
            server_url
            or os.environ.get('LLM_SERVER_URL')
            or os.environ.get('VLM_SERVER_URL')
            or 'http://localhost:8000'
        )
        if url:
            if not url.startswith(('http://', 'https://')):
                url = f'http://{url}'
            # Add default port if it looks like an IP/hostname without a port
            # e.g. http://10.4.25.26 -> http://10.4.25.26:8000
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if not parsed.port and parsed.hostname and parsed.hostname != 'localhost':
                 url = f"{url.rstrip('/')}:8000"
        
        self.server_url = url
        timeout_env = os.environ.get('LLM_REQUEST_TIMEOUT_S', '').strip()
        if request_timeout_s is not None:
            self.request_timeout_s = float(request_timeout_s)
        elif timeout_env:
            self.request_timeout_s = float(timeout_env)
        else:
            self.request_timeout_s = 300.0
        self.health_timeout_s = float(os.environ.get('LLM_HEALTH_TIMEOUT_S', '60'))
        self.health_retries = max(1, int(os.environ.get('LLM_HEALTH_RETRIES', '5')))
        self.queue_timeout_s = float(os.environ.get('LLM_QUEUE_TIMEOUT_S', '7200'))
        self.connect_retries = max(1, int(os.environ.get('LLM_CONNECT_RETRIES', '5')))
        self.connect_backoff_s = float(os.environ.get('LLM_CONNECT_BACKOFF_S', '2'))
        self.poll_interval_s = float(os.environ.get('LLM_POLL_INTERVAL_S', '0.5'))
        self.http_timeout_s = float(os.environ.get('LLM_HTTP_TIMEOUT_S', '30'))
        self.server_settings: Dict[str, Any] = {}

        self.expected_model = expected_model
        self.loaded = False
        self.model_alias = getattr(expected_model, 'alias', 'remote-llm')
        self.model_name = getattr(expected_model, 'path', 'remote-llm')
        self.parser = StrictActionParser()
        self.server_model_info: Dict[str, Any] = {}
        self.last_request_summary: Dict[str, Any] = {}

    def _encode_image_base64(self, image: Any) -> Optional[str]:
        if image is None or np is None:
            return None
        buffer = BytesIO()
        np.save(buffer, np.asarray(image), allow_pickle=False)
        return base64.b64encode(buffer.getvalue()).decode('ascii')

    def load_model(self) -> bool:
        last_error = ''
        for attempt in range(1, self.health_retries + 1):
            try:
                response = requests.get(
                    f'{self.server_url}/health',
                    timeout=self.health_timeout_s,
                )
                if response.status_code != 200:
                    last_error = f'status={response.status_code} body={response.text[:200]}'
                else:
                    data = response.json()
                    self.loaded = bool(data.get('model_loaded', False))
                    self.server_model_info = data
                    self.model_alias = data.get('model_alias', self.model_alias)
                    self.model_name = data.get('model_name', self.model_name)
                    if self.loaded:
                        self.server_settings = self.fetch_settings()
                        return True
                    last_error = f"model_not_loaded health={data}"
            except Exception as exc:
                last_error = str(exc)

            if attempt < self.health_retries:
                print(
                    f"[RemotePlanner] Health check failed "
                    f"({attempt}/{self.health_retries}): {last_error}. Retrying..."
                )
                time.sleep(5.0)

        self.last_request_summary = {
            'health_error': last_error,
            'health_timeout_s': self.health_timeout_s,
            'health_retries': self.health_retries,
        }
        return False

    def fetch_settings(self) -> Dict[str, Any]:
        """The server's settings (GET /settings); {} for a server that predates them."""
        try:
            response = requests.get(f'{self.server_url}/settings', timeout=self.health_timeout_s)
            if response.status_code == 200:
                return dict(response.json() or {})
        except Exception:
            pass
        return {}

    def planner_settings(self) -> Dict[str, Any]:
        settings = dict(self.server_settings or {})
        settings.setdefault('planner', 'remote')
        settings['server_url'] = self.server_url
        settings['generation_timeout_s'] = self.request_timeout_s
        settings['queue_timeout_s'] = self.queue_timeout_s
        return settings

    # -- HTTP with retries on connection errors (never on model outputs) ------------
    def _with_retries(self, send):
        last = None
        for attempt in range(1, self.connect_retries + 1):
            try:
                return send()
            except (requests.ConnectionError, requests.Timeout) as exc:  # the request never got an answer
                last = exc
                if attempt < self.connect_retries:
                    time.sleep(self.connect_backoff_s * attempt)
        raise PlannerServerError('connection', f'{type(last).__name__}: {last}')

    def _call_server(self, request_data: Dict[str, Any]):
        """Submit a planner call and wait for it. Returns (response data, timing)."""
        submitted = self._with_retries(lambda: requests.post(
            f'{self.server_url}/plan/submit', json=request_data, timeout=self.http_timeout_s))
        if submitted.status_code == 404:
            raise PlannerServerError('server_too_old', 'the planner server has no /plan/submit endpoint')
        if submitted.status_code != 200:
            raise PlannerServerError('http_status', f'{submitted.status_code} - {submitted.text[:300]}')
        job_id = submitted.json().get('job_id')
        started = time.monotonic()
        while True:
            response = self._with_retries(lambda: requests.get(
                f'{self.server_url}/plan/jobs/{job_id}', timeout=self.http_timeout_s))
            if response.status_code != 200:
                raise PlannerServerError('http_status', f'{response.status_code} - {response.text[:300]}')
            state = response.json()
            status = state.get('status')
            timing = {'queue_wait_s': state.get('queue_wait_s'), 'generation_time_s': state.get('generation_time_s')}
            if status == 'done':
                return dict(state.get('result') or {}), timing
            if status == 'error':
                raise PlannerServerError('server_error', str(state.get('error')), timing)
            if status == 'running' and float(state.get('running_for_s') or 0.0) > self.request_timeout_s:
                raise PlannerServerError('generation_timeout',
                                         f'generation ran longer than {self.request_timeout_s:.0f} s', timing)
            if status == 'queued' and time.monotonic() - started > self.queue_timeout_s:
                raise PlannerServerError('queue_timeout', f'queued longer than {self.queue_timeout_s:.0f} s', timing)
            time.sleep(self.poll_interval_s)

    @staticmethod
    def _infrastructure_result(error: 'PlannerServerError', started_at: float) -> PlanResult:
        event = FailureEvent(
            failure_id=FailureCode.PLANNER_CALL_FAILED,
            stage=FailureStage.BEFORE_EXECUTION,
            source=FailureSource.VALIDATION,
            action=None,
            evidence={'kind': error.kind, 'detail': error.detail},
            failure_layer=FailureLayer.LAYER_1,
            should_replan=False,
            message=f'Planner call failed ({error.kind}): {error.detail}',
        )
        return PlanResult(False, [], '', time.time() - started_at, event.message, event, timing=error.timing)

    def plan(self, bundle: Any) -> PlanResult:
        """Unified interface that handles both text and multimodal bundles."""
        metadata = dict(getattr(bundle, 'metadata', {}) or {})
        held_object = metadata.get('held_object')
        if held_object is None and hasattr(bundle, 'state'):
            held_object = bundle.state.gripper_state.get('holding')
        max_new_tokens = int(metadata.get('max_new_tokens', 4096) or 4096)
        temperature = float(metadata.get('temperature', 0.0) or 0.0)
        return self.generate_plan(
            system_prompt=bundle.system_prompt,
            user_prompt=bundle.user_prompt,
            icl_mode=bundle.icl_mode,
            held_object=held_object,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            bundle=bundle # Pass bundle for image extraction
        )

    def generate_plan(
        self,
        system_prompt: str,
        user_prompt: str,
        icl_mode: str,
        max_new_tokens: int = 4096,
        temperature: float = 0.0,
        held_object: Optional[str] = None,
        bundle: Optional[Any] = None,
    ) -> PlanResult:
        started_at = time.time()
        # Support for multimodal images if present in bundle
        image_b64 = getattr(bundle, 'image_base64', None) if hasattr(bundle, 'image_base64') else None
        if not image_b64 and 'image_base64' in getattr(bundle, '__dict__', {}):
             image_b64 = bundle.__dict__['image_base64']
        if not image_b64 and bundle is not None:
            images = getattr(bundle, 'images', None) or []
            if images:
                image_b64 = self._encode_image_base64(images[0])

        # Only objects the robot has observed are sent to the planner server.
        valid_objects = (
            self.parser.planner_visible_objects()
            if hasattr(self.parser, 'planner_visible_objects')
            else sorted(self.parser.valid_objects)
        )
        prompt_version = (getattr(bundle, 'metadata', {}) or {}).get('prompt_version') if bundle is not None else None
        valid_regions = sorted(self.parser.valid_regions)
        if prompt_version == 'v2':
            valid_regions = sorted({planner_region_name(region) for region in valid_regions})
        request_data = {
            'system_prompt': system_prompt,
            'user_prompt': user_prompt,
            'goal': user_prompt, # Alias
            'icl_mode': icl_mode,
            'max_new_tokens': int(max_new_tokens),
            'temperature': float(temperature),
            'held_object': held_object,
            'use_vision': bool(image_b64 is not None),
            'image_present': bool(image_b64 is not None),
            'valid_actions': sorted(self.parser.valid_actions),
            'valid_objects': valid_objects,
            'valid_regions': valid_regions,
        }
        if prompt_version:
            request_data['prompt_version'] = prompt_version
        if image_b64 is not None:
            request_data['image_base64'] = image_b64
        self.last_request_summary = {
            'model_type': getattr(self.expected_model, 'model_type', 'llm'),
            'use_vision': bool(image_b64 is not None),
            'image_present': bool(image_b64 is not None),
            'text_only': image_b64 is None,
            'valid_actions': sorted(self.parser.valid_actions),
            'valid_objects': valid_objects,
            'valid_regions': valid_regions,
            'prompt_version': prompt_version,
        }

        try:
            data, timing = self._call_server(request_data)
        except PlannerServerError as exc:
            return self._infrastructure_result(exc, started_at)
        except Exception as exc:  # anything else on the way to the server is infrastructure too
            return self._infrastructure_result(PlannerServerError('client_error', f'{type(exc).__name__}: {exc}'),
                                               started_at)
        try:
            raw_output = data.get('raw_output', '')
            failure_event = self._decode_failure_event(data.get('failure_event'))
            actions = []

            if prompt_version == 'v2' and (getattr(bundle, 'metadata', {}) or {}).get('output_format') == 'corrective_blocks':
                # Corrective blocks (Phase 5) are parsed and merged by the pipeline.
                return PlanResult(success=bool(raw_output.strip()), actions=[], raw_output=raw_output,
                                  inference_time=float(data.get('inference_time', time.time() - started_at)),
                                  error_message=None if raw_output.strip() else 'empty planner output',
                                  timing=timing)
            if prompt_version == 'v2' and raw_output.strip():
                # v2: the client's parse of the raw output is authoritative (only the text
                # after FINAL ACTIONS: is parsed); the server's own parse is ignored.
                try:
                    actions = self.parser.parse(raw_output, held_object=held_object)
                    failure_event = None
                    parse_ok = True
                except StrictParseError as exc:
                    actions, failure_event, parse_ok = [], self._plan_check_failure(exc, raw_output), False
                return PlanResult(
                    success=parse_ok,
                    actions=actions,
                    raw_output=raw_output,
                    inference_time=float(data.get('inference_time', time.time() - started_at)),
                    error_message=None if parse_ok else failure_event.message,
                    failure_event=failure_event,
                    timing=timing,
                )

            action_lines = [self._action_line(item) for item in data.get('actions', [])]
            if action_lines:
                try:
                    actions = self.parser.parse('\n'.join(action_lines), held_object=held_object)
                except StrictParseError as exc:
                    failure_event = FailureEvent(
                        failure_id=exc.failure_id,
                        stage=FailureStage.BEFORE_EXECUTION,
                        source=FailureSource.VALIDATION,
                        action=None,
                        evidence={'line_number': exc.line_number, 'raw_output': '\n'.join(action_lines), 'fact': exc.fact},
                        failure_layer=FailureLayer.LAYER_1,
                        should_replan=True,
                        message=str(exc),
                    )

            local_parse_ok = False
            if not actions and raw_output.strip() and failure_event is None:
                try:
                    actions = self.parser.parse(raw_output, held_object=held_object)
                    local_parse_ok = True
                except StrictParseError as exc:
                    failure_event = self._plan_check_failure(exc, raw_output)
            elif not actions and raw_output.strip() and failure_event is not None:
                # The server parses against observed objects only, so an unobserved object
                # comes back as unknown_action_token; re-parse locally to report it as
                # unobserved_object. The legacy VLM parser also rejects a bare NO_ACTIONS.
                server_code = str(failure_event.failure_id)
                if server_code in (FailureCode.UNKNOWN_ACTION_TOKEN, FailureCode.PLANNER_OUTPUT_NOT_PARSEABLE):
                    try:
                        parsed = self.parser.parse(raw_output, held_object=held_object)
                    except StrictParseError as exc:
                        if server_code == FailureCode.UNKNOWN_ACTION_TOKEN:
                            failure_event = self._plan_check_failure(exc, raw_output)
                    else:
                        if server_code == FailureCode.UNKNOWN_ACTION_TOKEN or not parsed:
                            actions, failure_event, local_parse_ok = parsed, None, True

            return PlanResult(
                success=bool(data.get('success', False) or actions or local_parse_ok),
                actions=actions,
                raw_output=raw_output,
                inference_time=float(data.get('inference_time', time.time() - started_at)),
                error_message=data.get('error_message'),
                failure_event=failure_event,
                timing=timing,
            )
        except Exception as exc:  # a malformed server response
            return self._infrastructure_result(PlannerServerError('bad_response', f'{type(exc).__name__}: {exc}'),
                                               started_at)

    @staticmethod
    def _plan_check_failure(exc: StrictParseError, raw_output: str) -> FailureEvent:
        return FailureEvent(
            failure_id=exc.failure_id,
            stage=FailureStage.BEFORE_EXECUTION,
            source=FailureSource.VALIDATION,
            action=None,
            evidence={'line_number': exc.line_number, 'raw_output': raw_output, 'fact': exc.fact},
            failure_layer=FailureLayer.LAYER_1,
            should_replan=True,
            message=str(exc),
        )

    def check_goal_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        icl_mode: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        held_object: Optional[str] = None,
        image: Optional[Any] = None,
    ) -> GoalCheckResult:
        started_at = time.time()
        image_b64 = self._encode_image_base64(image)
        request_data = {
            'system_prompt': system_prompt,
            'user_prompt': user_prompt,
            'icl_mode': icl_mode,
            'max_new_tokens': int(max_new_tokens),
            'temperature': float(temperature),
            'held_object': held_object,
        }
        if image_b64 is not None:
            request_data['image_base64'] = image_b64
        try:
            response = requests.post(
                f'{self.server_url}/check-goal',
                json=request_data,
                timeout=self.request_timeout_s,
            )
            if response.status_code != 200:
                return GoalCheckResult(
                    success=False,
                    goal_satisfied=False,
                    raw_output='',
                    inference_time=time.time() - started_at,
                    error_message=f'Server error: {response.status_code} - {response.text}',
                )
            data = response.json()
            return GoalCheckResult(
                success=bool(data.get('success', False)),
                goal_satisfied=bool(data.get('goal_satisfied', False)),
                raw_output=data.get('raw_output', ''),
                inference_time=float(data.get('inference_time', time.time() - started_at)),
                reason=data.get('reason', '') or '',
                error_message=data.get('error_message'),
            )
        except Exception as exc:
            return GoalCheckResult(
                success=False,
                goal_satisfied=False,
                raw_output='',
                inference_time=time.time() - started_at,
                error_message=str(exc),
            )

    def get_debug_info(self) -> Dict[str, Any]:
        info: Dict[str, Any] = {
            'model_alias': self.model_alias,
            'model_name': self.model_name,
            'model_type': self.server_model_info.get(
                'model_type',
                getattr(self.expected_model, 'model_type', 'llm'),
            ),
            'quantization': self.server_model_info.get('quantization'),
            'loaded': self.loaded,
            'server_url': self.server_url,
            'health': dict(self.server_model_info),
            'last_request': dict(self.last_request_summary),
        }
        try:
            health = requests.get(f'{self.server_url}/health', timeout=10)
            if health.status_code == 200:
                info['health'] = health.json()
                info['model_type'] = info['health'].get('model_type', info['model_type'])
                info['quantization'] = info['health'].get('quantization', info.get('quantization'))
        except Exception as exc:
            info['health_error'] = str(exc)

        try:
            debug = requests.get(f'{self.server_url}/debug/last-request', timeout=10)
            if debug.status_code == 200:
                payload = debug.json()
                info['last_request'] = payload.get('last_request', {})
                self.last_request_summary = info['last_request']
        except Exception as exc:
            info['last_request_error'] = str(exc)
        return info

    def _action_line(self, item: Dict[str, Any]) -> str:
        action_name = item.get('action_name', '')
        args = list(item.get('args', []))
        if not args:
            return action_name
        return f"{action_name}({', '.join(args)})"

    def _decode_failure_event(self, payload: Optional[Dict[str, Any]]) -> Optional[FailureEvent]:
        if not payload:
            return None
        try:
            return FailureEvent(
                failure_id=payload['failure_id'],
                stage=FailureStage(payload['stage']),
                source=FailureSource(payload['source']),
                action=payload.get('action'),
                evidence=dict(payload.get('evidence', {})),
                failure_layer=FailureLayer(payload.get('failure_layer', FailureLayer.LAYER_1.value)),
                should_replan=bool(payload.get('should_replan', True)),
                message=payload.get('message', ''),
            )
        except Exception:
            return None


def test_connection(server_url: Optional[str] = None) -> bool:
    """Test connection to the maintained remote LLM planner server."""
    url = server_url or os.environ.get('LLM_SERVER_URL') or os.environ.get('VLM_SERVER_URL') or 'http://localhost:8000'

    print('=' * 60)
    print('TESTING LLM PLANNER SERVER CONNECTION')
    print('=' * 60)
    print(f'Server URL: {url}')

    try:
        response = requests.get(f'{url}/health', timeout=10)
        print(f'Status Code: {response.status_code}')
        if response.status_code == 200:
            data = response.json()
            print(f"Server Status: {data.get('status')}")
            print(f"Model Loaded: {data.get('model_loaded')}")
            print(f"Model Alias: {data.get('model_alias')}")
            print(f"Model Name: {data.get('model_name')}")
            print(f"Model Type: {data.get('model_type')}")
            print(f"Prompt Mode: {data.get('prompt_mode')}")
            print(f"GPU Available: {data.get('gpu_available')}")
            print('=' * 60)
            print('Connection successful')
            return True
        print(f'Server returned error: {response.text}')
        return False
    except Exception as exc:
        print('Connection failed')
        print(f'Error: {exc}')
        print('Make sure the server is running: python -m llm_pipeline.server')
        return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description='Test the maintained remote LLM planner server connection')
    parser.add_argument('--url', type=str, default='', help='Server URL to test')
    args = parser.parse_args()
    test_connection(args.url or None)


if __name__ == '__main__':
    main()
