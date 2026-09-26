#!/usr/bin/env python3
"""Remote inference server for the maintained text-only LLM planner.

Requests are served one at a time by a single worker thread (``PlanJobQueue``). A
client submits a job (``POST /plan/submit``) and polls it (``GET /plan/jobs/<id>``);
each job reports how long it waited in the queue and how long generation took, so
the client's timeout covers generation only. ``GET /settings`` reports everything
that changes what the model generates (model and revision, thinking mode, format
repair, server git commit); the trial runner logs it and refuses real-model trials
with thinking off or format repair on.
"""

from __future__ import annotations

import argparse
import base64
import itertools
import os
import queue
import subprocess
import sys
import threading
import time
from io import BytesIO
from typing import Any, Callable, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
    HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    HAS_FASTAPI = False
    FastAPI = None
    HTTPException = None
    CORSMiddleware = None
    BaseModel = object
    uvicorn = None

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from llm_pipeline.planner import TextLLMPlanner
from llm_pipeline.pipeline_types import FailureEvent, PromptBundle
from llm_pipeline.quantization import normalize_quantization
from llm_pipeline.strict_parser import StrictActionParser
from vlm_pipeline.model_registry import format_model_listing as format_planner_model_listing, resolve_model_spec
PROMPT_MODE_LLM_SEGMENTATION = 'segmentation_text_only'
PROMPT_MODE_VLM_MULTIMODAL = 'segmentation_text_image'


def format_model_listing() -> str:
    return format_planner_model_listing()


class PlanRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    goal: str = ''
    icl_mode: str
    max_new_tokens: int = 512
    temperature: float = 0.0
    held_object: Optional[str] = None
    use_vision: bool = False
    image_present: bool = False
    image_base64: Optional[str] = None
    valid_actions: Optional[List[str]] = None
    valid_objects: Optional[List[str]] = None
    valid_regions: Optional[List[str]] = None
    # prompt.version of the client (plan.md Section 0.7). 'v2' disables the
    # legacy VLM format-repair regeneration, so one request is one planner call.
    prompt_version: Optional[str] = None


class ActionResponse(BaseModel):
    action_name: str
    args: List[str]


class FailureEventResponse(BaseModel):
    failure_id: str
    failure_layer: str = 'layer_1'
    stage: str
    source: str
    action: Optional[str] = None
    evidence: Dict[str, Any]
    should_replan: bool = True
    message: str = ''


class PlanResponse(BaseModel):
    success: bool
    actions: List[ActionResponse]
    raw_output: str
    inference_time: float
    error_message: Optional[str] = None
    failure_event: Optional[FailureEventResponse] = None


class GoalCheckRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    icl_mode: str
    max_new_tokens: int = 64
    temperature: float = 0.0
    held_object: Optional[str] = None
    image_base64: Optional[str] = None


class GoalCheckResponse(BaseModel):
    success: bool
    goal_satisfied: bool
    raw_output: str
    inference_time: float
    reason: str = ''
    error_message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_name: str
    model_alias: str
    model_type: str
    quantization: str = 'none'
    prompt_mode: str
    gpu_available: bool


API_VERSION = 2


def server_git_commit(root: str = ROOT_DIR) -> Dict[str, Any]:
    def _git(*args: str) -> str:
        return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, timeout=10).stdout.strip()

    try:
        return {'commit': _git('rev-parse', 'HEAD') or None, 'dirty': bool(_git('status', '--porcelain', '-uno'))}
    except Exception:
        return {'commit': None, 'dirty': None}


class PlanJobQueue:
    """Serial job queue: one worker thread runs one job at a time, in submission order.

    ``submit(handler, payload)`` returns a job id; ``status(job_id)`` reports ``queued``
    (with the queue position), ``running`` (with ``running_for_s``), ``done`` (with the
    result) or ``error``, plus ``queue_wait_s`` and ``generation_time_s``.
    """

    def __init__(self, keep_finished_s: float = 3600.0):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._queue: 'queue.Queue[str]' = queue.Queue()
        self._ids = itertools.count(1)
        self._keep_finished_s = float(keep_finished_s)
        self._worker = threading.Thread(target=self._run, name='plan-worker', daemon=True)
        self._worker.start()

    def submit(self, handler: Callable[[Any], Any], payload: Any) -> str:
        job_id = f'job{next(self._ids)}'
        with self._lock:
            self._forget_old()
            self._jobs[job_id] = {'status': 'queued', 'submitted_at': time.monotonic(), 'started_at': None,
                                  'finished_at': None, 'handler': handler, 'payload': payload,
                                  'result': None, 'error': None}
            self._order.append(job_id)
        self._queue.put(job_id)
        return job_id

    def _forget_old(self) -> None:
        now = time.monotonic()
        for job_id in [j for j, job in self._jobs.items()
                       if job['finished_at'] is not None and now - job['finished_at'] > self._keep_finished_s]:
            self._jobs.pop(job_id, None)
            if job_id in self._order:
                self._order.remove(job_id)

    def _run(self) -> None:
        while True:
            job_id = self._queue.get()
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                job['status'], job['started_at'] = 'running', time.monotonic()
            try:
                result, error = job['handler'](job['payload']), None
            except Exception as exc:  # the model call failed: reported as a server error
                result, error = None, f'{type(exc).__name__}: {exc}'
            with self._lock:
                job['finished_at'] = time.monotonic()
                job['result'], job['error'] = result, error
                job['status'] = 'error' if error is not None else 'done'
                job['payload'] = None

    def status(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            now = time.monotonic()
            started, finished = job['started_at'], job['finished_at']
            queued_ids = [j for j in self._order if self._jobs.get(j, {}).get('status') == 'queued']
            return {
                'job_id': job_id,
                'status': job['status'],
                'queue_position': queued_ids.index(job_id) + 1 if job_id in queued_ids else 0,
                'queue_wait_s': round((started if started is not None else now) - job['submitted_at'], 4),
                'running_for_s': round(((finished if finished is not None else now) - started), 4)
                if started is not None else 0.0,
                'generation_time_s': round(finished - started, 4) if finished is not None else None,
                'result': job['result'],
                'error': job['error'],
            }

    def wait(self, job_id: str, poll_s: float = 0.05) -> Dict[str, Any]:
        while True:
            state = self.status(job_id)
            if state is None or state['status'] in ('done', 'error'):
                return state
            time.sleep(poll_s)


class LLMServer:
    def __init__(
        self,
        model: str = 'qwen',
        use_4bit: bool = False,
        device: str = 'cuda',
        model_type: str = '',
        quantization: str = '',
        format_repair: bool = False,
    ):
        self.model_spec = resolve_model_spec(model, model_type)
        self.quantization = normalize_quantization(quantization, use_4bit=use_4bit)
        self.use_4bit = self.quantization == 'bnb4'
        self.device = device
        # The legacy VLM format-repair regeneration (a second, hidden model call). Off by
        # default; never used for prompt.version=v2 requests.
        self.format_repair = bool(format_repair)
        if self.model_spec.model_type == 'vlm':
            from llm_pipeline.vlm_planner import VLMPlanner

            self.planner = VLMPlanner(
                model_path=self.model_spec.path,
                model_alias=self.model_spec.alias,
                use_4bit=self.use_4bit,
                quantization=self.quantization,
                device=self.device,
            )
        else:
            self.planner = TextLLMPlanner(
                model_name=self.model_spec.path,
                model_alias=self.model_spec.alias,
                use_4bit=self.use_4bit,
                quantization=self.quantization,
                device=self.device,
            )
        self.loaded = False
        self.last_request_summary: Dict[str, Any] = {}

    def load_model(self) -> bool:
        self.loaded = self.planner.load_model()
        if self.loaded and hasattr(self.planner, 'get_debug_info'):
            debug = self.planner.get_debug_info()
            self.last_request_summary = debug.get('last_request', {})
        return self.loaded

    def settings(self) -> Dict[str, Any]:
        """Everything that changes what the model generates (GET /settings)."""
        from llm_pipeline.planner import model_revision, thinking_mode_setting

        model = getattr(self.planner, 'model', None)
        if model is None:
            model = getattr(getattr(self.planner, 'legacy_planner', None), 'model', None)
        return {
            'api_version': API_VERSION,
            'planner': 'remote',
            'model_name': self.model_spec.path,
            'model_alias': self.model_spec.alias,
            'model_type': self.model_spec.model_type,
            'model_revision': model_revision(model),
            'quantization': self.quantization,
            'thinking_mode': thinking_mode_setting(),
            'format_repair': bool(self.format_repair),
            'serving': 'serial',
            'server_git_commit': server_git_commit(),
            'model_loaded': bool(getattr(self, 'loaded', False)),
        }

    def _decode_image_base64(self, payload: Optional[str]):
        if not payload:
            return None
        try:
            import numpy as np

            data = base64.b64decode(payload.encode('ascii'))
            return np.load(BytesIO(data), allow_pickle=False)
        except Exception as exc:
            raise ValueError(f'invalid image_base64 payload: {exc}') from exc

    def _apply_runtime_parser(self, request: PlanRequest) -> Dict[str, Any]:
        runtime_symbols = {
            'valid_actions': list(request.valid_actions or []),
            'valid_objects': list(request.valid_objects or []),
            'valid_regions': list(request.valid_regions or []),
        }
        if not any(runtime_symbols.values()):
            return runtime_symbols

        parser = StrictActionParser(
            valid_actions=request.valid_actions or None,
            valid_objects=request.valid_objects or None,
            valid_regions=request.valid_regions or None,
        )
        if hasattr(self.planner, 'parser'):
            self.planner.parser = parser
        legacy_planner = getattr(self.planner, 'legacy_planner', None)
        if legacy_planner is not None and hasattr(legacy_planner, 'parser'):
            legacy_planner.parser = parser
        return runtime_symbols

    def generate_plan(self, request: PlanRequest) -> PlanResponse:
        runtime_symbols = self._apply_runtime_parser(request)
        image = self._decode_image_base64(request.image_base64) if request.image_base64 else None
        use_vision = bool(request.use_vision or image is not None)
        if self.model_spec.model_type == 'vlm':
            if image is None:
                if use_vision:
                    raise ValueError('VLM planning requires image_base64')
                images = []
            else:
                images = [image]
            bundle = PromptBundle(
                goal_text=request.goal or request.user_prompt,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                visible_objects=list(request.valid_objects or []),
                valid_regions=list(request.valid_regions or []),
                icl_mode=request.icl_mode,
                images=images,
                metadata={
                    'held_object': request.held_object,
                    'max_new_tokens': request.max_new_tokens,
                    'temperature': request.temperature,
                    'prompt_version': request.prompt_version,
                    'allow_format_repair': bool(getattr(self, 'format_repair', False)),
                },
            )
            result = self.planner.plan(bundle)
        else:
            result = self.planner.generate_plan(
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                icl_mode=request.icl_mode,
                max_new_tokens=request.max_new_tokens,
                temperature=request.temperature,
                held_object=request.held_object,
            )
        if hasattr(self.planner, 'get_debug_info'):
            debug = self.planner.get_debug_info()
            self.last_request_summary = debug.get('last_request', {})
        self.last_request_summary.update({
            'model_type': self.model_spec.model_type,
            'prompt_mode': PROMPT_MODE_VLM_MULTIMODAL if use_vision else PROMPT_MODE_LLM_SEGMENTATION,
            'use_vision': use_vision,
            'image_present': image is not None,
            'text_only': not use_vision,
            **runtime_symbols,
        })
        return PlanResponse(
            success=result.success,
            actions=[
                ActionResponse(action_name=action.action_name, args=list(action.args))
                for action in result.actions
            ],
            raw_output=result.raw_output,
            inference_time=result.inference_time,
            error_message=result.error_message,
            failure_event=self._encode_failure_event(result.failure_event),
        )

    def check_goal_completion(self, request: GoalCheckRequest) -> GoalCheckResponse:
        image = self._decode_image_base64(request.image_base64) if request.image_base64 else None
        kwargs = {}
        if image is not None and self.model_spec.model_type == 'vlm':
            kwargs['image'] = image
        result = self.planner.check_goal_completion(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            icl_mode=request.icl_mode,
            max_new_tokens=request.max_new_tokens,
            temperature=request.temperature,
            held_object=request.held_object,
            **kwargs,
        )
        if hasattr(self.planner, 'get_debug_info'):
            debug = self.planner.get_debug_info()
            self.last_request_summary = debug.get('last_request', {})
        return GoalCheckResponse(**result.to_dict())

    def _encode_failure_event(self, failure_event: Optional[FailureEvent]) -> Optional[FailureEventResponse]:
        if failure_event is None:
            return None
        return FailureEventResponse(**failure_event.to_dict())


def create_app(
    model: str = 'qwen',
    use_4bit: bool = False,
    device: str = 'cuda',
    model_type: str = '',
    quantization: str = '',
    format_repair: bool = False,
) -> FastAPI:
    app = FastAPI(
        title='Maintained LLM Planner Server',
        description='Remote inference server for the llm_pipeline text-only planner',
        version='1.0.0',
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    server = LLMServer(
        model=model,
        use_4bit=use_4bit,
        device=device,
        model_type=model_type,
        quantization=quantization,
        format_repair=format_repair,
    )
    jobs = PlanJobQueue()

    @app.on_event('startup')
    async def startup_event():
        server.load_model()

    @app.get('/settings')
    def settings():
        return server.settings()

    @app.get('/health', response_model=HealthResponse)
    async def health_check():
        import torch
        return HealthResponse(
            status='ok' if server.loaded else 'model_not_loaded',
            model_loaded=server.loaded,
            model_name=server.model_spec.path,
            model_alias=server.model_spec.alias,
            model_type=server.model_spec.model_type,
            quantization=server.quantization,
            prompt_mode=PROMPT_MODE_VLM_MULTIMODAL if server.model_spec.model_type == 'vlm' else PROMPT_MODE_LLM_SEGMENTATION,
            gpu_available=torch.cuda.is_available(),
        )

    @app.get('/debug/last-request')
    async def debug_last_request():
        return {
            'model_alias': server.model_spec.alias,
            'model_name': server.model_spec.path,
            'model_type': server.model_spec.model_type,
            'quantization': server.quantization,
            'prompt_mode': PROMPT_MODE_VLM_MULTIMODAL if server.model_spec.model_type == 'vlm' else PROMPT_MODE_LLM_SEGMENTATION,
            'last_request': server.last_request_summary,
        }

    def _job_payload(state):
        payload = {key: state[key] for key in ('job_id', 'status', 'queue_position', 'queue_wait_s',
                                               'running_for_s', 'generation_time_s', 'error')}
        result = state.get('result')
        dump = getattr(result, 'model_dump', None) or getattr(result, 'dict', None)
        payload['result'] = dump() if callable(dump) else result
        return payload

    # Plain (non-async) handlers run in the threadpool, so /health and job polls answer
    # while the worker thread is generating.
    @app.post('/plan/submit')
    def submit_plan(request: PlanRequest):
        if not server.loaded:
            raise HTTPException(status_code=503, detail='Model not loaded')
        job_id = jobs.submit(server.generate_plan, request)
        return {'job_id': job_id, 'status': 'queued'}

    @app.get('/plan/jobs/{job_id}')
    def plan_job(job_id: str):
        state = jobs.status(job_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f'unknown job {job_id}')
        return _job_payload(state)

    @app.post('/plan', response_model=PlanResponse)
    def generate_plan(request: PlanRequest):
        """Blocking form (queued like every other request)."""
        if not server.loaded:
            raise HTTPException(status_code=503, detail='Model not loaded')
        state = jobs.wait(jobs.submit(server.generate_plan, request))
        if state['status'] == 'error':
            raise HTTPException(status_code=500, detail=state['error'])
        return state['result']

    @app.post('/check-goal', response_model=GoalCheckResponse)
    def check_goal_completion(request: GoalCheckRequest):
        if not server.loaded:
            raise HTTPException(status_code=503, detail='Model not loaded')
        state = jobs.wait(jobs.submit(server.check_goal_completion, request))
        if state['status'] == 'error':
            raise HTTPException(status_code=500, detail=state['error'])
        return state['result']

    @app.get('/')
    async def root():
        return {
            'service': 'Maintained LLM Planner Server',
            'model_alias': server.model_spec.alias,
            'model_name': server.model_spec.path,
            'model_type': server.model_spec.model_type,
            'endpoints': {
                '/health': 'GET - Check server health',
                '/settings': 'GET - Model, revision, thinking mode, format repair, server commit',
                '/plan/submit': 'POST - Queue a planner call; returns a job id',
                '/plan/jobs/{id}': 'GET - Job status, queue wait, generation time, result',
                '/plan': 'POST - Generate direct LLM action plan (blocking)',
                '/check-goal': 'POST - Verify whether the goal is complete',
                '/debug/last-request': 'GET - Inspect last request',
            },
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description='Maintained LLM Planner Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind to')
    parser.add_argument('--model', default='qwen', help='Registered LLM alias or Hugging Face path')
    parser.add_argument('--model-type', choices=['', 'llm', 'vlm'], default='', help='Optional explicit model type')
    parser.add_argument('--device', default='cuda', help='Torch device hint')
    parser.add_argument('--quantization', choices=['none', 'bnb8', 'bnb4'], default='', help='Explicit quantization mode. Use bnb4 for native bitsandbytes 4-bit.')
    parser.add_argument('--no-4bit', action='store_true', help='Deprecated alias for --quantization none')
    parser.add_argument('--list-models', action='store_true', help='List registered planner models and exit')
    parser.add_argument('--format-repair', action='store_true',
                        help='Enable the legacy VLM format-repair regeneration (a second model call; never for '
                             'prompt v2). Real-model trials refuse a server with it on.')
    args = parser.parse_args()

    if args.no_4bit and args.quantization:
        parser.error('--no-4bit is deprecated; do not combine it with --quantization. Use --quantization none instead.')

    if args.list_models:
        print(format_model_listing())
        return

    if not HAS_FASTAPI:
        print('ERROR: FastAPI not installed. Install with: pip install fastapi uvicorn')
        sys.exit(1)

    print("=" * 60)
    print("MAINTAINED LLM PLANNER SERVER")
    print("=" * 60)
    print(f"Model: {args.model}")
    model_spec = resolve_model_spec(args.model, args.model_type)
    quantization = normalize_quantization(args.quantization, use_4bit=not args.no_4bit)
    print(f"Model type: {model_spec.model_type}")
    print(f"Quantization: {quantization}")
    print(f"Device hint: {args.device}")
    print(f"Format repair: {'on' if args.format_repair else 'off'}")
    print(f"Server: http://{args.host}:{args.port}")
    print("=" * 60)

    app = create_app(
        model=args.model,
        use_4bit=not args.no_4bit,
        device=args.device,
        model_type=args.model_type,
        quantization=quantization,
        format_repair=args.format_repair,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
