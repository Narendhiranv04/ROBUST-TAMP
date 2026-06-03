import numpy as np

from llm_pipeline import client as client_module
from llm_pipeline.client import RemoteTextLLMPlanner
from llm_pipeline.pipeline_types import PromptBundle


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeRequests:
    def __init__(self, health_payload, plan_payload, goal_check_payload=None):
        self.health_payload = health_payload
        self.plan_payload = plan_payload
        self.goal_check_payload = goal_check_payload or {}
        self.get_calls = []
        self.post_calls = []

    def get(self, url, timeout=10):
        self.get_calls.append((url, timeout))
        if url.endswith('/health'):
            return _FakeResponse(payload=self.health_payload)
        if url.endswith('/debug/last-request'):
            return _FakeResponse(payload={'last_request': {'url': url}})
        return _FakeResponse(status_code=404, text='not found')

    def post(self, url, json=None, timeout=300):
        self.post_calls.append((url, json, timeout))
        if url.endswith('/plan'):
            return _FakeResponse(payload=self.plan_payload)
        if url.endswith('/check-goal'):
            return _FakeResponse(payload=self.goal_check_payload)
        return _FakeResponse(status_code=404, text='not found')


def test_remote_planner_loads_from_server_health() -> None:
    fake_requests = _FakeRequests(
        health_payload={
            'status': 'ok',
            'model_loaded': True,
            'model_alias': 'qwen',
            'model_name': 'Qwen/Qwen2.5-7B-Instruct',
            'model_type': 'llm',
            'prompt_mode': 'text_visible',
            'gpu_available': True,
        },
        plan_payload={},
    )
    old_requests = client_module.requests
    old_has_requests = client_module.HAS_REQUESTS
    client_module.requests = fake_requests
    client_module.HAS_REQUESTS = True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner-box:8000')
        assert planner.load_model() is True
        assert planner.loaded is True
        assert planner.model_alias == 'qwen'
        assert planner.model_name == 'Qwen/Qwen2.5-7B-Instruct'
        assert fake_requests.get_calls[0][0] == 'http://planner-box:8000/health'
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_returns_server_actions() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen', 'model_name': 'qwen', 'model_type': 'llm', 'prompt_mode': 'text_visible', 'gpu_available': True},
        plan_payload={
            'success': True,
            'actions': [
                {'action_name': 'pick', 'args': ['mug2']},
                {'action_name': 'place', 'args': ['mug2', 'table_target_area']},
            ],
            'raw_output': 'pick(mug2)\nplace(mug2, table_target_area)',
            'inference_time': 0.12,
            'error_message': None,
            'failure_event': None,
        },
    )
    old_requests = client_module.requests
    old_has_requests = client_module.HAS_REQUESTS
    client_module.requests = fake_requests
    client_module.HAS_REQUESTS = True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner-box:8000')
        result = planner.generate_plan(
            system_prompt='system',
            user_prompt='user',
            icl_mode='zero_shot',
        )
        assert result.success is True
        assert [str(action) for action in result.actions] == [
            'pick(mug2)',
            'place(mug2, table_target_area)',
        ]
        assert fake_requests.post_calls[0][0] == 'http://planner-box:8000/plan'
        assert fake_requests.post_calls[0][1]['icl_mode'] == 'zero_shot'
        assert fake_requests.post_calls[0][1]['use_vision'] is False
        assert 'image_base64' not in fake_requests.post_calls[0][1]
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_sends_vlm_image_payload_from_bundle() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen-vl', 'model_name': 'qwen-vl', 'model_type': 'vlm', 'prompt_mode': 'segmentation_text_image', 'gpu_available': True},
        plan_payload={
            'success': True,
            'actions': [
                {'action_name': 'open', 'args': ['box_lid']},
            ],
            'raw_output': 'open(box_lid)',
            'inference_time': 0.08,
            'error_message': None,
            'failure_event': None,
        },
    )
    old_requests = client_module.requests
    old_has_requests = client_module.HAS_REQUESTS
    client_module.requests = fake_requests
    client_module.HAS_REQUESTS = True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner-box:8000')
        planner.parser.valid_objects.update({'box_lid'})
        bundle = PromptBundle(
            goal_text='Open the lid.',
            system_prompt='system',
            user_prompt='user',
            visible_objects=['box_lid'],
            valid_regions=[],
            icl_mode='zero_shot',
            images=[np.zeros((2, 3, 3), dtype=np.uint8)],
        )

        result = planner.plan(bundle)

        assert result.success is True
        payload = fake_requests.post_calls[0][1]
        assert payload['use_vision'] is True
        assert payload['image_present'] is True
        assert payload['image_base64']
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_falls_back_to_local_parse_when_server_returns_raw_output() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen', 'model_name': 'qwen', 'model_type': 'llm', 'prompt_mode': 'text_visible', 'gpu_available': True},
        plan_payload={
            'success': False,
            'actions': [],
            'raw_output': 'pick(mug2)\nplace(mug2, table_target_area)',
            'inference_time': 0.08,
            'error_message': None,
            'failure_event': None,
        },
    )
    old_requests = client_module.requests
    old_has_requests = client_module.HAS_REQUESTS
    client_module.requests = fake_requests
    client_module.HAS_REQUESTS = True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner-box:8000')
        result = planner.generate_plan(
            system_prompt='system',
            user_prompt='user',
            icl_mode='few_shot_shared_1',
        )
        assert result.success is True
        assert [str(action) for action in result.actions] == [
            'pick(mug2)',
            'place(mug2, table_target_area)',
        ]
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_sends_held_object_from_prompt_metadata() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen', 'model_name': 'qwen', 'model_type': 'llm', 'prompt_mode': 'text_visible', 'gpu_available': True},
        plan_payload={
            'success': True,
            'actions': [
                {'action_name': 'place', 'args': ['mug2', 'table_target_area']},
            ],
            'raw_output': 'place(mug2, table_target_area)',
            'inference_time': 0.08,
            'error_message': None,
            'failure_event': None,
        },
    )
    old_requests = client_module.requests
    old_has_requests = client_module.HAS_REQUESTS
    client_module.requests = fake_requests
    client_module.HAS_REQUESTS = True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner-box:8000')
        planner.parser.valid_objects.update({'mug2'})
        planner.parser.valid_regions.update({'table_target_area'})
        bundle = PromptBundle(
            goal_text='Place the held mug.',
            system_prompt='system',
            user_prompt='user',
            visible_objects=['mug2'],
            valid_regions=['table_target_area'],
            icl_mode='zero_shot',
            metadata={'held_object': 'mug2'},
        )
        result = planner.plan(bundle)

        assert result.success is True
        assert [str(action) for action in result.actions] == [
            'place(mug2, table_target_area)',
        ]
        assert fake_requests.post_calls[0][1]['held_object'] == 'mug2'
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_checks_goal_completion() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen', 'model_name': 'qwen', 'model_type': 'llm', 'prompt_mode': 'text_visible', 'gpu_available': True},
        plan_payload={},
        goal_check_payload={
            'success': True,
            'goal_satisfied': False,
            'raw_output': 'GOAL_INCOMPLETE: one mug remains outside the box',
            'inference_time': 0.05,
            'reason': 'one mug remains outside the box',
            'error_message': None,
        },
    )
    old_requests = client_module.requests
    old_has_requests = client_module.HAS_REQUESTS
    client_module.requests = fake_requests
    client_module.HAS_REQUESTS = True
    try:
        planner = RemoteTextLLMPlanner(server_url='http://planner-box:8000')
        result = planner.check_goal_completion(
            system_prompt='system',
            user_prompt='user',
            icl_mode='zero_shot',
            held_object=None,
        )

        assert result.success is True
        assert result.goal_satisfied is False
        assert result.reason == 'one mug remains outside the box'
        assert fake_requests.post_calls[0][0] == 'http://planner-box:8000/check-goal'
        assert fake_requests.post_calls[0][1]['max_new_tokens'] == 64
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests
