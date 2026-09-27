"""Per-model planner profiles (llm_pipeline/model_profiles.py) and the per-call record."""
import json
import re

import numpy as np
import pytest

from llm_pipeline import model_profiles as mp
from llm_pipeline import vllm_client as vllm_module
from llm_pipeline.pipeline_types import PromptBundle
from llm_pipeline.tests.test_phase7c import _FakeVLLM, _completion


@pytest.mark.parametrize('alias', sorted(mp.PROFILES))
def test_every_profile_is_pinned_and_sampled_not_greedy(alias) -> None:
    p = mp.profile(alias)
    assert re.fullmatch(r'[0-9a-f]{40}', p['revision'])
    assert p['model_type'] in ('vlm', 'llm') and p['thinking'] in ('on', 'off') and p['served_name']
    assert p['reasoning'] is (p['thinking'] == 'on')
    presets = p['sampling']
    assert ('vl' in presets) if p['model_type'] == 'vlm' else ('text' in presets)
    for preset in presets.values():
        assert preset['temperature'] > 0.0          # never greedy decoding
        assert set(preset) == {'temperature', 'top_p', 'top_k', 'min_p', 'repetition_penalty', 'presence_penalty'}
    assert p['system_prompt_mode'] in ('system', 'user', 'system_with_card_prompt') and p['source']


def test_the_run_order_covers_every_profile_once() -> None:
    assert sorted(mp.RUN_ORDER) == sorted(mp.PROFILES)


def test_packaging_modes() -> None:
    plain = mp.build_messages(mp.profile('qwen3-8b'), 'SYS', 'USER')
    assert plain == [{'role': 'system', 'content': 'SYS'}, {'role': 'user', 'content': 'USER'}]
    # DeepSeek-R1-Distill: no system message, the same text at the start of the user message.
    assert mp.build_messages(mp.profile('r1-distill-qwen-7b'), 'SYS', 'USER') == [{'role': 'user', 'content': 'SYS\n\nUSER'}]
    # Ministral 3 Reasoning: its card's system prompt appended to ours, [THINK] as a thinking chunk.
    card = mp.card_system_prompt(mp.profile('ministral-3-8b-reasoning'))
    messages = mp.build_messages(mp.profile('ministral-3-8b-reasoning'), 'SYS', 'USER', image_b64='AAAA')
    head, thinking, tail = messages[0]['content']
    assert head['text'].startswith('SYS\n\n# HOW YOU SHOULD THINK AND ANSWER') and thinking['type'] == 'thinking'
    assert head['text'][len('SYS\n\n'):] + '[THINK]' + thinking['thinking'] + '[/THINK]' + tail['text'] == card
    assert messages[1]['content'][0]['type'] == 'image_url' and messages[1]['content'][1]['text'] == 'USER'


def test_the_card_system_prompt_is_checked_against_its_hash() -> None:
    bad = dict(mp.profile('ministral-3-8b-reasoning'), card_system_prompt_sha256='0' * 64)
    with pytest.raises(ValueError):
        mp.card_system_prompt(bad)


def _plan(alias, images=None):
    p = mp.profile(alias)
    fake = _FakeVLLM(_completion('FINAL ACTIONS:\nNO_ACTIONS'), roots=[f'/hf/snapshots/{p["revision"]}'] * 8)
    fake_get = fake.get

    def get(url, timeout=None):
        response = fake_get(url, timeout)
        if url.endswith('/v1/models'):
            response.json()['data'][0]['id'] = p['served_name']
        return response
    fake.get = get
    fake.completion['model'] = p['served_name']
    old = vllm_module.requests
    vllm_module.requests = fake
    try:
        planner = vllm_module.VLLMChatPlanner(server_url='http://127.0.0.1:8000', model=alias)
        planner.connect_backoff_s = 0.0
        assert planner.load_model()
        bundle = PromptBundle(goal_text='g', system_prompt='sys', user_prompt='user', visible_objects=[],
                              valid_regions=[], icl_mode='zero_shot', images=images, metadata={'max_new_tokens': 24576})
        return planner, planner.plan(bundle), fake.posts[0][1]
    finally:
        vllm_module.requests = old


def test_qwen3_think_off_sends_the_switch_and_its_card_sampling() -> None:
    planner, result, body = _plan('qwen3-8b-nothink')
    assert body['model'] == 'qwen3-8b' and body['chat_template_kwargs'] == {'enable_thinking': False}
    assert (body['temperature'], body['top_p'], body['top_k']) == (0.7, 0.8, 20)
    assert planner.server_settings['thinking_mode'] == 'off' and planner.server_settings['profile_alias'] == 'qwen3-8b-nothink'


def test_every_call_records_its_exact_request_response_and_image(tmp_path) -> None:
    from llm_pipeline.trial_log import TrialLogger

    image = np.full((6, 6, 3), 7, dtype=np.uint8)
    _, result, body = _plan('holo2-8b', images=[image])
    exchange = result.exchange
    assert exchange['request']['temperature'] == 1.0 and exchange['request']['max_tokens'] == 24576
    image_part = exchange['request']['messages'][-1]['content'][0]
    assert image_part['image_url']['url'] == f'<png sha256={exchange["image_sha256"]}>'   # no base64 in the log
    assert body['messages'][-1]['content'][0]['image_url']['url'].startswith('data:image/png;base64,')
    assert exchange['response']['usage']['completion_tokens'] == 50 and result.image_png.startswith(b'\x89PNG')

    logger = TrialLogger(path=tmp_path / 'trial_log.jsonl', trial_id='t', prompts_dir=tmp_path / 'prompts')
    prompt_path = logger.save_prompt(1, 'sys', 'user', kind='initial')
    saved = logger.save_exchange(prompt_path, exchange, result.image_png)
    assert json.loads((tmp_path / saved['exchange_path']).read_text())['request']['model'] == 'holo2-8b'
    assert (tmp_path / saved['image_path']).read_bytes() == result.image_png


def test_refusal_uses_the_served_name_of_a_profile() -> None:
    from llm_pipeline.trial_runner import real_model_refusals

    p = mp.profile('qwen3-8b-nothink')
    settings = {'planner': 'vllm', 'model_name': 'qwen3-8b', 'model_revision': p['revision'], 'vllm_version': '0.30.0',
                'thinking_mode': 'off', 'format_repair': False}
    assert real_model_refusals({'commit': 'a', 'dirty': False}, settings, 'qwen3-8b-nothink', p['revision']) == []
    assert any('thinking mode' in x for x in real_model_refusals({'commit': 'a', 'dirty': False},
                                                                 dict(settings, thinking_mode='on'), 'qwen3-8b-nothink', p['revision']))
