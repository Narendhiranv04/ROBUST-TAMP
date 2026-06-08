#!/usr/bin/env python3
"""Remote inference server for the maintained text-only LLM planner."""

from __future__ import annotations

import argparse
import base64
import os
import sys
from io import BytesIO
from typing import Any, Dict, List, Optional

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
    prompt_mode: str
    gpu_available: bool


class LLMServer:
    def __init__(self, model: str = 'qwen', use_4bit: bool = False, device: str = 'cuda', model_type: str = ''):
        self.model_spec = resolve_model_spec(model, model_type)
        self.use_4bit = use_4bit
        self.device = device
        if self.model_spec.model_type == 'vlm':
            from llm_pipeline.vlm_planner import VLMPlanner

            self.planner = VLMPlanner(
                model_path=self.model_spec.path,
                model_alias=self.model_spec.alias,
                use_4bit=self.use_4bit,
                device=self.device,
            )
        else:
            self.planner = TextLLMPlanner(
                model_name=self.model_spec.path,
                model_alias=self.model_spec.alias,
                use_4bit=self.use_4bit,
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

    def _decode_image_base64(self, payload: Optional[str]):
        if not payload:
            return None
        try:
            import numpy as np

            data = base64.b64decode(payload.encode('ascii'))
            return np.load(BytesIO(data), allow_pickle=False)
        except Exception as exc:
            raise ValueError(f'invalid image_base64 payload: {exc}') from exc

    def generate_plan(self, request: PlanRequest) -> PlanResponse:
        image = self._decode_image_base64(request.image_base64) if request.image_base64 else None
        use_vision = bool(request.use_vision or image is not None or self.model_spec.model_type == 'vlm')
        if use_vision:
            if image is None:
                raise ValueError('VLM planning requires image_base64')
            bundle = PromptBundle(
                goal_text=request.goal or request.user_prompt,
                system_prompt=request.system_prompt,
                user_prompt=request.user_prompt,
                visible_objects=[],
                valid_regions=[],
                icl_mode=request.icl_mode,
                images=[image],
                metadata={
                    'held_object': request.held_object,
                    'max_new_tokens': request.max_new_tokens,
                    'temperature': request.temperature,
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
        if image is not None:
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


def create_app(model: str = 'qwen', use_4bit: bool = False, device: str = 'cuda', model_type: str = '') -> FastAPI:
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

    server = LLMServer(model=model, use_4bit=use_4bit, device=device, model_type=model_type)

    @app.on_event('startup')
    async def startup_event():
        server.load_model()

    @app.get('/health', response_model=HealthResponse)
    async def health_check():
        import torch
        return HealthResponse(
            status='ok' if server.loaded else 'model_not_loaded',
            model_loaded=server.loaded,
            model_name=server.model_spec.path,
            model_alias=server.model_spec.alias,
            model_type=server.model_spec.model_type,
            prompt_mode=PROMPT_MODE_VLM_MULTIMODAL if server.model_spec.model_type == 'vlm' else PROMPT_MODE_LLM_SEGMENTATION,
            gpu_available=torch.cuda.is_available(),
        )

    @app.get('/debug/last-request')
    async def debug_last_request():
        return {
            'model_alias': server.model_spec.alias,
            'model_name': server.model_spec.path,
            'model_type': server.model_spec.model_type,
            'prompt_mode': PROMPT_MODE_VLM_MULTIMODAL if server.model_spec.model_type == 'vlm' else PROMPT_MODE_LLM_SEGMENTATION,
            'last_request': server.last_request_summary,
        }

    @app.post('/plan', response_model=PlanResponse)
    async def generate_plan(request: PlanRequest):
        if not server.loaded:
            raise HTTPException(status_code=503, detail='Model not loaded')
        try:
            return server.generate_plan(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post('/check-goal', response_model=GoalCheckResponse)
    async def check_goal_completion(request: GoalCheckRequest):
        if not server.loaded:
            raise HTTPException(status_code=503, detail='Model not loaded')
        return server.check_goal_completion(request)

    @app.get('/')
    async def root():
        return {
            'service': 'Maintained LLM Planner Server',
            'model_alias': server.model_spec.alias,
            'model_name': server.model_spec.path,
            'model_type': server.model_spec.model_type,
            'endpoints': {
                '/health': 'GET - Check server health',
                '/plan': 'POST - Generate direct LLM action plan',
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
    parser.add_argument('--no-4bit', action='store_true', help='Disable 4-bit quantization')
    parser.add_argument('--list-models', action='store_true', help='List registered planner models and exit')
    args = parser.parse_args()

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
    print(f"Model type: {model_spec.model_type}")
    print(f"4-bit quantization: {not args.no_4bit}")
    print(f"Device hint: {args.device}")
    print(f"Server: http://{args.host}:{args.port}")
    print("=" * 60)

    app = create_app(model=args.model, use_4bit=not args.no_4bit, device=args.device, model_type=args.model_type)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
