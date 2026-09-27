"""Per-model planner profiles: the single source for the vLLM client, the server script and downloads.

Every model gets the same planner prompt content, the same output limit, context length, seeds,
flags and pipeline. What differs per model is only what its model card prescribes:

* ``repo`` / ``revision``: the pinned Hugging Face snapshot (Hub ``main`` on 2026-09-27);
* ``served_name``: the name vLLM serves it under (two profiles may share one served model, e.g.
  Qwen3-8B with thinking on and off);
* ``model_type``: ``vlm`` (receives the scene image) or ``llm`` (text only);
* ``reasoning``: the Table 2 "Reas." column (a reasoning model / thinking mode on);
* ``thinking``: ``on`` / ``off``, what the served model does with this profile;
* ``sampling``: the model card's recommended sampling (``vl`` with an image, ``text`` without).
  None of them is greedy (temperature 0);
* ``chat_template_kwargs``: sent with every request (Qwen3 thinking off);
* ``system_prompt_mode``: ``system`` (a system message), ``user`` (no system message: the planner's
  system prompt is prepended to the user message, as the DeepSeek-R1-Distill cards require), or
  ``system_with_card_prompt`` (the card's own system prompt is appended to ours, Ministral 3
  Reasoning; its [THINK] part becomes a ``thinking`` content chunk, as in the card's example);
* ``serve``: vLLM arguments (reasoning parser, remote code, Mistral formats), plus the files to
  download (``include``, ``None`` for the whole snapshot);
* ``source``: where the settings come from.

Run ``python3 llm_pipeline/model_profiles.py shell <alias>`` for the variables start_vllm.sh
needs, ``download <alias>`` for the download arguments, ``list`` for all aliases.
This module has no third-party imports (the server script runs it with any Python 3).
"""
import hashlib
import json
import shlex
import sys
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / 'model_prompts'

# Qwen3-VL model card, "Generation Hyperparameters" (thinking: VL / text presets).
_QWEN3_VL_THINKING = {
    'vl': {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0},
    'text': {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 1.5},
}
_QWEN3_VL_INSTRUCT = {
    'vl': {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 1.5},
    'text': {'temperature': 1.0, 'top_p': 1.0, 'top_k': 40, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 2.0},
}
# Qwen3 model card, "Best Practices".
_QWEN3_THINK_ON = {'text': {'temperature': 0.6, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}}
_QWEN3_THINK_OFF = {'text': {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}}
# DeepSeek-R1-Distill model cards, "Usage Recommendations" (temperature 0.6, top_p 0.95).
_R1_DISTILL = {'text': {'temperature': 0.6, 'top_p': 0.95, 'top_k': -1, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}}

_VL_SERVE = ['--limit-mm-per-prompt', '{"image": 2, "video": 0}']
_MISTRAL_FORMAT = ['--tokenizer-mode', 'mistral', '--config-format', 'mistral', '--load-format', 'mistral']
_MISTRAL_FILES = ['consolidated.safetensors', 'params.json', 'tekken.json', '*.txt', '*.md', '*.json']

PROFILES = {
    # ------------------------------------------------------------------ VLM, reasoning
    'qwen3-vl-8b-thinking': {
        'repo': 'Qwen/Qwen3-VL-8B-Thinking', 'revision': '92f3c4b4feadd3a016ef468d103bb5f58b2a2c6b',
        'served_name': 'qwen3-vl-8b-thinking', 'model_type': 'vlm', 'reasoning': True, 'thinking': 'on',
        'sampling': _QWEN3_VL_THINKING, 'system_prompt_mode': 'system',
        'serve': {'args': ['--reasoning-parser', 'qwen3'] + _VL_SERVE},
        'source': 'model card, Generation Hyperparameters (VL preset with an image)',
    },
    'qwen3-vl-4b-thinking': {
        'repo': 'Qwen/Qwen3-VL-4B-Thinking', 'revision': '1de27d8c51f12e819435303b9e84c4e25ba8401e',
        'served_name': 'qwen3-vl-4b-thinking', 'model_type': 'vlm', 'reasoning': True, 'thinking': 'on',
        'sampling': _QWEN3_VL_THINKING, 'system_prompt_mode': 'system',
        'serve': {'args': ['--reasoning-parser', 'qwen3'] + _VL_SERVE},
        'source': 'model card, Generation Hyperparameters (VL preset with an image)',
    },
    'holo2-8b': {
        # Fine-tuned from Qwen3-VL-8B-Thinking (same chat template); its generation_config.json
        # sets top_k 20, top_p 0.95 and no temperature (1.0), as its base model's VL preset.
        'repo': 'Hcompany/Holo2-8B', 'revision': '09cd3b45966f61c8c5ae4bc1424151c682ccc5c8',
        'served_name': 'holo2-8b', 'model_type': 'vlm', 'reasoning': True, 'thinking': 'on',
        'sampling': {'vl': {'temperature': 1.0, 'top_p': 0.95, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}},
        'system_prompt_mode': 'system',
        'serve': {'args': ['--reasoning-parser', 'qwen3'] + _VL_SERVE},
        'source': 'generation_config.json (the card gives no sampling); base model Qwen3-VL-8B-Thinking',
    },
    'ministral-3-8b-reasoning': {
        'repo': 'mistralai/Ministral-3-8B-Reasoning-2512', 'revision': '81eaece1948f3875421d9a45bc55487d10e2d894',
        'served_name': 'ministral-3-8b-reasoning', 'model_type': 'vlm', 'reasoning': True, 'thinking': 'on',
        'sampling': {'vl': {'temperature': 0.7, 'top_p': 0.95, 'top_k': -1, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}},
        'system_prompt_mode': 'system_with_card_prompt',
        'card_system_prompt': 'Ministral-3-8B-Reasoning-2512.SYSTEM_PROMPT.txt',
        'card_system_prompt_sha256': 'aba1efaff0bdc73f4a864139e2c07dce8fc1e3df7b5d5c2b2623df6816697156',
        'serve': {'args': _MISTRAL_FORMAT + ['--reasoning-parser', 'mistral'] + _VL_SERVE, 'include': _MISTRAL_FILES},
        'source': 'model card: temperature 0.7, top_p 0.95, its SYSTEM_PROMPT.txt appended to the custom one, '
                  'vLLM with --reasoning-parser mistral and the Mistral formats (bf16)',
    },
    # ------------------------------------------------------------------ VLM, regular
    'qwen3-vl-8b-instruct': {
        'repo': 'Qwen/Qwen3-VL-8B-Instruct', 'revision': '0c351dd01ed87e9c1b53cbc748cba10e6187ff3b',
        'served_name': 'qwen3-vl-8b-instruct', 'model_type': 'vlm', 'reasoning': False, 'thinking': 'off',
        'sampling': _QWEN3_VL_INSTRUCT, 'system_prompt_mode': 'system',
        'serve': {'args': _VL_SERVE},
        'source': 'model card, Generation Hyperparameters (VL preset with an image)',
    },
    'ministral-3-8b-instruct': {
        # The BF16 release (the main Instruct repo is FP8); every compared model runs in bf16.
        'repo': 'mistralai/Ministral-3-8B-Instruct-2512-BF16', 'revision': 'f6fae9795746f63c9be8344932f01275f3c63734',
        'served_name': 'ministral-3-8b-instruct', 'model_type': 'vlm', 'reasoning': False, 'thinking': 'off',
        'sampling': {'vl': {'temperature': 0.05, 'top_p': 1.0, 'top_k': -1, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}},
        'system_prompt_mode': 'system',
        'serve': {'args': _MISTRAL_FORMAT + _VL_SERVE, 'include': _MISTRAL_FILES},
        'source': 'model card: "a temperature below 0.1" (0.05 here: sampled, not greedy); vLLM with the Mistral formats',
    },
    'internvl3.5-8b': {
        'repo': 'OpenGVLab/InternVL3_5-8B', 'revision': '9bb6a56ad9cc69db95e2d4eeb15a52bbcac4ef79',
        'served_name': 'internvl3.5-8b', 'model_type': 'vlm', 'reasoning': False, 'thinking': 'off',
        'sampling': {'vl': {'temperature': 0.8, 'top_p': 0.8, 'top_k': -1, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}},
        'system_prompt_mode': 'system',
        'serve': {'args': ['--trust-remote-code'] + _VL_SERVE},
        'source': 'model card, "Service" (OpenAI API) example: temperature 0.8, top_p 0.8; default (non-thinking) mode',
    },
    # ------------------------------------------------------------------ LLM, reasoning
    'qwen3-8b': {
        'repo': 'Qwen/Qwen3-8B', 'revision': 'b968826d9c46dd6066d109eabc6255188de91218',
        'served_name': 'qwen3-8b', 'model_type': 'llm', 'reasoning': True, 'thinking': 'on',
        'sampling': _QWEN3_THINK_ON, 'system_prompt_mode': 'system',
        'serve': {'args': ['--reasoning-parser', 'qwen3']},
        'source': 'model card, Best Practices (thinking mode; enable_thinking defaults to true)',
    },
    'qwen3-4b': {
        'repo': 'Qwen/Qwen3-4B', 'revision': '1cfa9a7208912126459214e8b04321603b3df60c',
        'served_name': 'qwen3-4b', 'model_type': 'llm', 'reasoning': True, 'thinking': 'on',
        'sampling': _QWEN3_THINK_ON, 'system_prompt_mode': 'system',
        'serve': {'args': ['--reasoning-parser', 'qwen3']},
        'source': 'model card, Best Practices (thinking mode)',
    },
    'r1-distill-llama-8b': {
        'repo': 'deepseek-ai/DeepSeek-R1-Distill-Llama-8B', 'revision': '6a6f4aa4197940add57724a7707d069478df56b1',
        'served_name': 'r1-distill-llama-8b', 'model_type': 'llm', 'reasoning': True, 'thinking': 'on',
        'sampling': _R1_DISTILL, 'system_prompt_mode': 'user',
        'serve': {'args': ['--reasoning-parser', 'deepseek_r1']},
        'source': 'model card, Usage Recommendations: temperature 0.6, top_p 0.95, no system prompt',
    },
    'r1-distill-qwen-7b': {
        'repo': 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B', 'revision': '916b56a44061fd5cd7d6a8fb632557ed4f724f60',
        'served_name': 'r1-distill-qwen-7b', 'model_type': 'llm', 'reasoning': True, 'thinking': 'on',
        'sampling': _R1_DISTILL, 'system_prompt_mode': 'user',
        'serve': {'args': ['--reasoning-parser', 'deepseek_r1']},
        'source': 'model card, Usage Recommendations: temperature 0.6, top_p 0.95, no system prompt',
    },
    # ------------------------------------------------------------------ LLM, regular
    'qwen3-8b-nothink': {
        # Same weights and served model as qwen3-8b; thinking switched off per request.
        'repo': 'Qwen/Qwen3-8B', 'revision': 'b968826d9c46dd6066d109eabc6255188de91218',
        'served_name': 'qwen3-8b', 'model_type': 'llm', 'reasoning': False, 'thinking': 'off',
        'sampling': _QWEN3_THINK_OFF, 'chat_template_kwargs': {'enable_thinking': False}, 'system_prompt_mode': 'system',
        'serve': {'args': ['--reasoning-parser', 'qwen3']},
        'source': 'model card, Best Practices (non-thinking mode: enable_thinking=false)',
    },
    'llama-3.1-8b-instruct': {
        'repo': 'meta-llama/Llama-3.1-8B-Instruct', 'revision': '0e9e39f249a16976918f6564b8830bc894c89659',
        'served_name': 'llama-3.1-8b-instruct', 'model_type': 'llm', 'reasoning': False, 'thinking': 'off',
        'sampling': {'text': {'temperature': 0.6, 'top_p': 0.9, 'top_k': -1, 'min_p': 0.0, 'repetition_penalty': 1.0, 'presence_penalty': 0.0}},
        'system_prompt_mode': 'system',
        'serve': {'args': []},
        'source': 'generation_config.json (temperature 0.6, top_p 0.9; the card gives no sampling)',
    },
    'qwen2.5-7b-instruct': {
        'repo': 'Qwen/Qwen2.5-7B-Instruct', 'revision': 'a09a35458c702b33eeacc393d103063234e8bc28',
        'served_name': 'qwen2.5-7b-instruct', 'model_type': 'llm', 'reasoning': False, 'thinking': 'off',
        'sampling': {'text': {'temperature': 0.7, 'top_p': 0.8, 'top_k': 20, 'min_p': 0.0, 'repetition_penalty': 1.05, 'presence_penalty': 0.0}},
        'system_prompt_mode': 'system',
        'serve': {'args': []},
        'source': 'generation_config.json (temperature 0.7, top_p 0.8, top_k 20, repetition_penalty 1.05)',
    },
}

# Old server profile names (start_vllm.sh VLLM_MODEL=thinking|instruct|llm).
LEGACY_NAMES = {'thinking': 'qwen3-vl-8b-thinking', 'instruct': 'qwen3-vl-8b-instruct', 'llm': 'qwen3-8b'}

# Run order on this server (Table 2 (b) and the 4B rows of (a); 32B runs elsewhere).
RUN_ORDER = [
    'qwen3-vl-8b-thinking', 'qwen3-8b', 'qwen3-8b-nothink', 'qwen3-vl-8b-instruct',
    'qwen3-vl-4b-thinking', 'qwen3-4b', 'holo2-8b', 'internvl3.5-8b', 'qwen2.5-7b-instruct',
    'r1-distill-qwen-7b', 'r1-distill-llama-8b', 'ministral-3-8b-instruct', 'ministral-3-8b-reasoning',
    'llama-3.1-8b-instruct',
]


def profile(alias: str) -> dict:
    alias = LEGACY_NAMES.get(alias, alias)
    if alias not in PROFILES:
        raise KeyError(f'unknown model profile {alias!r}; known: {", ".join(sorted(PROFILES))}')
    return dict(PROFILES[alias], alias=alias)


def card_system_prompt(prof: dict) -> str:
    """The card's system prompt text for ``system_with_card_prompt`` (checked against its sha256)."""
    name = prof.get('card_system_prompt')
    if not name:
        return ''
    data = (PROMPT_DIR / name).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != prof.get('card_system_prompt_sha256'):
        raise ValueError(f'{name}: sha256 {digest} differs from the pinned {prof.get("card_system_prompt_sha256")}')
    return data.decode('utf-8')


def build_messages(prof: dict, system_prompt: str, user_prompt: str, image_b64=None) -> list:
    """Chat messages for one planner call, packaged as the model's card prescribes."""
    mode = prof.get('system_prompt_mode', 'system')
    user_text = user_prompt
    if mode == 'user' and system_prompt:
        user_text = f'{system_prompt}\n\n{user_prompt}'
    if image_b64:
        user = [{'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + image_b64}},
                {'type': 'text', 'text': user_text}]
    else:
        user = user_text
    messages = []
    if mode == 'system' and system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    elif mode == 'system_with_card_prompt':
        card = card_system_prompt(prof)
        begin, end = card.find('[THINK]'), card.find('[/THINK]')
        head = (system_prompt + '\n\n' if system_prompt else '') + card[:begin]
        messages.append({'role': 'system', 'content': [
            {'type': 'text', 'text': head},
            {'type': 'thinking', 'thinking': card[begin + len('[THINK]'):end], 'closed': True},
            {'type': 'text', 'text': card[end + len('[/THINK]'):]},
        ]})
    messages.append({'role': 'user', 'content': user})
    return messages


def _main(argv) -> int:
    if not argv or argv[0] == 'list':
        for alias in RUN_ORDER:
            p = PROFILES[alias]
            print(f"{alias:28s} {p['model_type']} reasoning={p['reasoning']!s:5s} {p['repo']}@{p['revision'][:12]}")
        return 0
    command, alias = argv[0], argv[1]
    p = profile(alias)
    if command == 'shell':
        args = list(p['serve'].get('args', []))
        print(f"MODEL_ALIAS={shlex.quote(p['alias'])}")
        print(f"MODEL_REPO={shlex.quote(p['repo'])}")
        print(f"MODEL_REVISION={shlex.quote(p['revision'])}")
        print(f"SERVED_NAME={shlex.quote(p['served_name'])}")
        print(f"MODEL_TYPE={shlex.quote(p['model_type'])}")
        print('SERVE_ARGS=(' + ' '.join(shlex.quote(a) for a in args) + ')')
        return 0
    if command == 'download':
        out = ['download', p['repo'], '--revision', p['revision']]
        if p['serve'].get('include'):
            out += ['--include'] + list(p['serve']['include'])
        print(' '.join(shlex.quote(a) for a in out))
        return 0
    if command == 'json':
        print(json.dumps(p, indent=2, sort_keys=True))
        return 0
    print(f'unknown command {command!r}', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
