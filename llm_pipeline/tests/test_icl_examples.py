"""prompt-v2 in-context examples (icl_mode = examples_v2): grill scene only, appended to the
unchanged zero-shot system prompt."""
import re
from types import SimpleNamespace

import pytest

from llm_pipeline.icl_examples import EXAMPLES_TEXT
from llm_pipeline.pipeline_types import SceneState
from llm_pipeline.prompt_v2 import PromptV2Builder


def _bundle(objects, icl_mode):
    b = PromptV2Builder()
    b.set_symbol_registry(SimpleNamespace(objects=objects, actions=('pick', 'place', 'open', 'close')))
    state = SceneState(frame_index=0, visible_objects=[o for o in objects if 'lid' not in o], valid_regions=['table'],
                       gripper_state={'holding': None})
    return b.build_bundle(state, 'goal', icl_mode=icl_mode)


GRILL = ['grill_lid', 'plate', 'raw_meat_1']
KITCHEN = ['box_lid', 'mug1', 'spam']


def test_grill_prompt_gets_the_examples_after_the_unchanged_zero_shot_prompt() -> None:
    zs, icl = _bundle(GRILL, 'zero_shot'), _bundle(GRILL, 'examples_v2')
    assert icl.system_prompt == zs.system_prompt + '\n\n' + EXAMPLES_TEXT
    assert icl.user_prompt == zs.user_prompt and 'Example' not in zs.system_prompt


def test_kitchen_prompt_is_unchanged_with_examples_v2() -> None:
    assert _bundle(KITCHEN, 'examples_v2').system_prompt == _bundle(KITCHEN, 'zero_shot').system_prompt


def test_the_examples_name_nothing_of_the_grill_scene() -> None:
    text = EXAMPLES_TEXT.lower()
    for word in ('grill', 'meat', 'cook', 'plate', 'serving', 'dish_rack', 'prep'):
        assert word not in text, word
    # both answer formats appear, each with a good and a bad answer
    assert text.count('good answer') == 2 and text.count('bad answer') == 2
    assert 'final actions:' in text and 'final blocks:' in text


def test_an_unknown_icl_mode_is_refused() -> None:
    with pytest.raises(ValueError):
        _bundle(GRILL, 'few_shot_shared_1')
