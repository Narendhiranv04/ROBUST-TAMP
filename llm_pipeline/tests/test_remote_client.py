import numpy as np

from llm_pipeline import client as client_module
from llm_pipeline.client import RemoteTextLLMPlanner
from llm_pipeline.pipeline_types import PromptBundle
from llm_pipeline.strict_parser import StrictActionParser


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeRequests:
    """Stands in for ``requests`` against a planner server with the job API (/plan/submit, /plan/jobs)."""

    class ConnectionError(Exception):
        pass

    class Timeout(Exception):
        pass

    def __init__(self, health_payload, plan_payload, goal_check_payload=None, settings_payload=None,
                 job_states=None, submit_failures=0):
        self.health_payload = health_payload
        self.plan_payload = plan_payload
        self.goal_check_payload = goal_check_payload or {}
        self.settings_payload = settings_payload
        # Job states returned by successive polls before 'done' (e.g. queued, running).
        self.job_states = list(job_states or [])
        self.submit_failures = int(submit_failures)
        self.get_calls = []
        self.post_calls = []

    def get(self, url, timeout=10):
        self.get_calls.append((url, timeout))
        if url.endswith('/health'):
            return _FakeResponse(payload=self.health_payload)
        if url.endswith('/settings'):
            if self.settings_payload is None:
                return _FakeResponse(status_code=404, text='not found')
            return _FakeResponse(payload=self.settings_payload)
        if '/plan/jobs/' in url:
            if self.job_states:
                return _FakeResponse(payload=self.job_states.pop(0))
            return _FakeResponse(payload={'job_id': 'job1', 'status': 'done', 'queue_wait_s': 1.5,
                                          'generation_time_s': 2.5, 'running_for_s': 2.5,
                                          'result': self.plan_payload, 'error': None})
        if url.endswith('/debug/last-request'):
            return _FakeResponse(payload={'last_request': {'url': url}})
        return _FakeResponse(status_code=404, text='not found')

    def post(self, url, json=None, timeout=300):
        self.post_calls.append((url, json, timeout))
        if url.endswith('/plan/submit'):
            if self.submit_failures > 0:
                self.submit_failures -= 1
                raise self.ConnectionError('connection refused')
            return _FakeResponse(payload={'job_id': 'job1', 'status': 'queued'})
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
                {'action_name': 'place', 'args': ['mug2', 'table_staging_area']},
            ],
            'raw_output': 'pick(mug2)\nplace(mug2, table_staging_area)',
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
            'place(mug2, table_staging_area)',
        ]
        assert fake_requests.post_calls[0][0] == 'http://planner-box:8000/plan/submit'
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
            'raw_output': 'pick(mug2)\nplace(mug2, table_staging_area)',
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
            'place(mug2, table_staging_area)',
        ]
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_sends_runtime_parser_symbols() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen', 'model_name': 'qwen', 'model_type': 'llm', 'prompt_mode': 'text_visible', 'gpu_available': True},
        plan_payload={
            'success': False,
            'actions': [],
            'raw_output': 'pick(plate)\nplace(plate, serving_area)',
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
        planner.parser = StrictActionParser(
            valid_actions=['pick', 'place', 'open', 'close'],
            valid_objects=['plate', 'chicken', 'grill_lid'],
            valid_regions=['serving_area', 'inside_grill', 'plate_top'],
        )

        result = planner.generate_plan(
            system_prompt='system',
            user_prompt='user',
            icl_mode='few_shot_shared_1',
        )

        payload = fake_requests.post_calls[0][1]
        assert payload['valid_actions'] == ['close', 'open', 'pick', 'place']
        assert payload['valid_objects'] == ['chicken', 'grill_lid', 'plate']
        assert payload['valid_regions'] == ['inside_grill', 'plate_top', 'serving_area']
        assert result.success is True
        assert [str(action) for action in result.actions] == [
            'pick(plate)',
            'place(plate, serving_area)',
        ]
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_preserves_server_failure_event() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen-vl', 'model_name': 'qwen-vl', 'model_type': 'vlm', 'prompt_mode': 'text_visible', 'gpu_available': True},
        plan_payload={
            'success': False,
            'actions': [],
            'raw_output': 'Reasoning...\nopen(box_lid)\n' * 300,
            'inference_time': 0.08,
            'error_message': 'Previous planner output was too verbose and not parseable.',
            'failure_event': {
                'failure_id': 'planner_output_too_verbose',
                'failure_layer': 'layer_1',
                'stage': 'before_execution',
                'source': 'parser',
                'action': None,
                'evidence': {'raw_output_chars': 7200},
                'should_replan': True,
                'message': 'Previous planner output was too verbose and not parseable. Reply with only a concise FINAL ACTIONS block.',
            },
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
        assert result.success is False
        assert result.failure_event is not None
        assert result.failure_event.failure_id == 'planner_output_too_verbose'
        assert 'too verbose' in result.failure_event.message
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests


def test_remote_planner_sends_held_object_from_prompt_metadata() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen', 'model_name': 'qwen', 'model_type': 'llm', 'prompt_mode': 'text_visible', 'gpu_available': True},
        plan_payload={
            'success': True,
            'actions': [
                {'action_name': 'place', 'args': ['mug2', 'table_staging_area']},
            ],
            'raw_output': 'place(mug2, table_staging_area)',
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
        planner.parser.valid_regions.update({'table_staging_area'})
        bundle = PromptBundle(
            goal_text='Place the held mug.',
            system_prompt='system',
            user_prompt='user',
            visible_objects=['mug2'],
            valid_regions=['table_staging_area'],
            icl_mode='zero_shot',
            metadata={'held_object': 'mug2', 'max_new_tokens': 777, 'temperature': 0.2},
        )
        result = planner.plan(bundle)

        assert result.success is True
        assert [str(action) for action in result.actions] == [
            'place(mug2, table_staging_area)',
        ]
        assert fake_requests.post_calls[0][1]['held_object'] == 'mug2'
        assert fake_requests.post_calls[0][1]['max_new_tokens'] == 777
        assert fake_requests.post_calls[0][1]['temperature'] == 0.2
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


def test_remote_planner_sends_goal_check_image_payload() -> None:
    fake_requests = _FakeRequests(
        health_payload={'status': 'ok', 'model_loaded': True, 'model_alias': 'qwen-vl', 'model_name': 'qwen-vl', 'model_type': 'vlm', 'prompt_mode': 'segmentation_text_image', 'gpu_available': True},
        plan_payload={},
        goal_check_payload={
            'success': True,
            'goal_satisfied': True,
            'raw_output': 'GOAL_COMPLETE',
            'inference_time': 0.05,
            'reason': '',
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
            image=np.zeros((2, 3, 3), dtype=np.uint8),
        )

        assert result.goal_satisfied is True
        payload = fake_requests.post_calls[0][1]
        assert payload['image_base64']
    finally:
        client_module.requests = old_requests
        client_module.HAS_REQUESTS = old_has_requests
