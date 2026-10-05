"""A place planned while the object is already held, and what the planner is told about it."""
from llm_pipeline.failures import FailureCode
from llm_pipeline.pipeline_types import SceneState
from llm_pipeline.prompt_v2 import state_section
from llm_pipeline.tests.test_failure_logic import checker
from llm_pipeline.executor import DirectAction


def _state(holding=None):
    return SceneState(
        frame_index=0,
        visible_objects=['mug1', 'mug2'],
        valid_regions=['table', 'inside_box'],
        gripper_state={'status': 'holding' if holding else 'empty', 'holding': holding},
        object_region_map={'mug1': 'pantry_area', 'mug2': 'table'},
    )


def test_held_object_is_shown_in_the_gripper_not_at_the_fallback_region():
    lines = state_section(_state(holding='mug2'), ['table', 'inside_box'], [])
    assert '- mug2: in the gripper' in lines
    assert '- mug2: table' not in lines
    assert 'Gripper: holding mug2' in lines


def test_objects_not_held_keep_their_region():
    lines = state_section(_state(), ['table', 'inside_box'], [])
    assert '- mug2: table' in lines
    assert 'Gripper: empty' in lines


def test_motion_planning_failures_carry_a_plain_fact():
    event = checker.classify_runtime_error(DirectAction('place', ('mug2', 'table')),
                                           'No PDDL plan found for place(mug2, table)')
    assert event.failure_id == FailureCode.PDDL_NO_PLAN
    assert event.evidence['fact'] == 'The motion planner found no feasible motion for this action in the current scene.'
    assert event.evidence['runtime_message'] == 'No PDDL plan found for place(mug2, table)'
    other = checker.classify_runtime_error(DirectAction('pick', ('mug2',)), 'something unexpected')
    assert 'fact' not in other.evidence


# ------------------------------------------------------------------- the text-only LLM (Qwen3-8B)
def test_the_text_only_llm_never_receives_the_image_and_uses_its_card_sampling() -> None:
    import numpy as np
    from llm_pipeline import vllm_client as vllm_module
    from llm_pipeline.pipeline_types import PromptBundle
    from llm_pipeline.tests.test_phase7c import _FakeVLLM, _completion

    revision = vllm_module.PINNED_MODELS['qwen3-8b']['revision']
    fake = _FakeVLLM(_completion('FINAL ACTIONS:\nNO_ACTIONS'), roots=[f'/hf/snapshots/{revision}'] * 8)
    fake_get = fake.get

    def get(url, timeout=None):   # serve qwen3-8b instead of the VL model
        response = fake_get(url, timeout)
        if url.endswith('/v1/models'):
            response.json()['data'][0]['id'] = 'qwen3-8b'
        return response
    fake.get = get
    fake.completion['model'] = 'qwen3-8b'
    old = vllm_module.requests
    vllm_module.requests = fake
    try:
        planner = vllm_module.VLLMChatPlanner(server_url='http://127.0.0.1:8000', model='qwen3-8b')
        planner.connect_backoff_s = 0.0
        assert planner.load_model()
        bundle = PromptBundle(goal_text='g', system_prompt='sys', user_prompt='user', visible_objects=[],
                              valid_regions=[], icl_mode='zero_shot', images=[np.zeros((8, 8, 3), dtype=np.uint8)],
                              metadata={'max_new_tokens': 24576})
        result = planner.plan(bundle)
    finally:
        vllm_module.requests = old
    body = fake.posts[0][1]
    assert body['model'] == 'qwen3-8b' and body['messages'][-1]['content'] == 'user'   # text only, no image part
    assert (body['temperature'], body['top_p'], body['top_k'], body['presence_penalty']) == (0.6, 0.95, 20, 0.0)
    assert 'chat_template_kwargs' not in body          # thinking stays on (the template's default)
    assert result.success is True and planner.get_debug_info()['model_type'] == 'llm'
    assert planner.server_settings['thinking_mode'] == 'on' and planner.server_settings['model_revision'] == revision
