"""Snapshot tests for prompt v2 (docs/PROMPTS.md).

Regenerate the golden files after an approved template change with
``UPDATE_PROMPT_SNAPSHOTS=1 python -m pytest llm_pipeline/tests/test_prompt_v2.py``.
"""

import os
import re
from pathlib import Path

import pytest

from llm_pipeline.executable_symbols import ACTION_SYMBOLS, GRILL_ACTION_SYMBOLS, RuntimeSymbolRegistry
from llm_pipeline.failures import FailureCode
from llm_pipeline.pipeline_types import FailureEvent, FailureSource, FailureStage, SceneState
from llm_pipeline.prompt_v2 import IdentifiedAction, PromptV2Builder, ReplanContext
from llm_pipeline.region_aliases import planner_region_name

SNAPSHOT_DIR = Path(__file__).parent / 'snapshots'

KITCHEN = {
    'registry': RuntimeSymbolRegistry(
        ACTION_SYMBOLS, ('mug1', 'mug2', 'mug3', 'can_of_beans', 'sugar', 'box_lid'),
        ('table', 'table_staging_area', 'cupboard_shelf', 'inside_box', 'pantry_area', 'box_lid_top'),
    ),
    'state': SceneState(
        frame_index=3,
        visible_objects=['mug2', 'mug3', 'sugar', 'box_lid'],
        valid_regions=['table', 'table_staging_area', 'cupboard_shelf', 'inside_box', 'pantry_area', 'box_lid_top'],
        object_region_map={'mug2': 'table', 'mug3': 'cupboard_shelf', 'sugar': 'pantry_area'},
        lid_states={'box_lid': False},
        gripper_state={'status': 'empty', 'holding': None},
    ),
    'goal': 'move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box',
    'trigger': FailureEvent(
        failure_id=FailureCode.NEW_OBJECT_DISCOVERED, stage=FailureStage.AFTER_EXECUTION,
        source=FailureSource.SEGMENTATION, action='open(box_lid)',
        evidence={'newly_visible_objects': ['can_of_beans']}, message='Newly visible objects require replanning',
    ),
    'replan_regions': {'can_of_beans': 'inside_box', 'mug3': 'table_staging_area'},
    'replan_lids': {'box_lid': True},
    'context': ReplanContext(
        completed=[IdentifiedAction('a1', 'pick(mug3)'), IdentifiedAction('a2', 'place(mug3, table_staging_area)'),
                   IdentifiedAction('a3', 'open(box_lid)')],
        remaining=[IdentifiedAction('a4', 'pick(mug2)'), IdentifiedAction('a5', 'place(mug2, inside_box)')],
    ),
}

GRILL = {
    'registry': RuntimeSymbolRegistry(
        GRILL_ACTION_SYMBOLS, ('steak', 'steak1', 'chicken', 'plate', 'grill_lid'),
        ('table', 'prep_area', 'inside_grill', 'plate_top', 'serving_area', 'dish_rack'),
    ),
    'state': SceneState(
        frame_index=5,
        visible_objects=['chicken', 'steak1', 'plate', 'grill_lid'],
        valid_regions=['table', 'prep_area', 'inside_grill', 'plate_top', 'serving_area', 'dish_rack'],
        object_region_map={'chicken': 'prep_area', 'steak1': 'prep_area', 'plate': 'dish_rack'},
        lid_states={'grill_lid': False},
        gripper_state={'status': 'empty', 'holding': None},
    ),
    'goal': 'COOK all raw meat using the grill and SERVE all cooked meat on the PLATE in the serving area.',
    'trigger': FailureEvent(
        failure_id=FailureCode.PLACEMENT_FAILED, stage=FailureStage.AFTER_EXECUTION,
        source=FailureSource.GEOMETRY, action='place(plate, serving_area)',
        evidence={}, message='plate is geometrically resolved in table, not target region serving_area',
    ),
    'replan_regions': {'plate': 'table'},
    'replan_lids': {'grill_lid': True},
    'context': ReplanContext(
        completed=[IdentifiedAction('a1', 'open(grill_lid)'), IdentifiedAction('a2', 'pick(chicken)'),
                   IdentifiedAction('a3', 'place(chicken, inside_grill)'), IdentifiedAction('a4', 'pick(plate)')],
        remaining=[IdentifiedAction('a5', 'place(plate, serving_area)'), IdentifiedAction('a6', 'close(grill_lid)')],
    ),
}

SCENES = {'kitchen': KITCHEN, 'grill': GRILL}


def _render(scene):
    data = SCENES[scene]
    builder = PromptV2Builder()
    builder.set_symbol_registry(data['registry'])
    initial = builder.build_bundle(data['state'], data['goal'])
    replan_state = SceneState(**{**data['state'].__dict__})
    replan_state.object_region_map = {**data['state'].object_region_map, **data['replan_regions']}
    replan_state.visible_objects = list(dict.fromkeys(data['state'].visible_objects + list(data['replan_regions'])))
    replan_state.lid_states = dict(data['replan_lids'])
    if scene == 'grill':
        replan_state.visible_objects.remove('chicken')  # inside the grill, hidden by the open lid from these cameras
        replan_state.object_region_map = {k: v for k, v in replan_state.object_region_map.items() if k != 'chicken'}
    builder.set_replan_context(data['context'])
    replan = builder.build_bundle(replan_state, data['goal'], failure_event=data['trigger'])
    goal_system, goal_user = builder.goal_check_prompts(
        replan_state, data['goal'], [item.action for item in data['context'].completed],
    )
    return {
        'system': initial.system_prompt,
        'initial_user': initial.user_prompt,
        'replan_user': replan.user_prompt,
        'goal_check_system': goal_system,
        'goal_check_user': goal_user,
    }


@pytest.mark.parametrize('scene', sorted(SCENES))
@pytest.mark.parametrize('part', ['system', 'initial_user', 'replan_user', 'goal_check_system', 'goal_check_user'])
def test_prompt_v2_snapshot(scene, part) -> None:
    text = _render(scene)[part]
    path = SNAPSHOT_DIR / f'prompt_v2_{scene}_{part}.txt'
    if os.environ.get('UPDATE_PROMPT_SNAPSHOTS') == '1':
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + '\n', encoding='utf-8')
    assert text + '\n' == path.read_text(encoding='utf-8')


def test_one_template_for_both_scenes() -> None:
    """Scene differences are data only: removing the scene's names gives identical templates."""
    def skeleton(scene, text):
        data = SCENES[scene]
        names = list(data['registry'].objects) + list(data['registry'].regions) + [data['goal']]
        names += [planner_region_name(region) for region in data['registry'].regions]
        for name in sorted(names, key=len, reverse=True):
            text = text.replace(name, '<X>')
        text = re.sub(r'(<X>(, )?)+', '<X>', text)
        text = re.sub(r'(- <X>: <X>\n)+', '- <X>: <X>\n', text)
        text = re.sub(r'(- a\d+: .*\n?)+', '- <ACTION>\n', text)
        return re.sub(r'^- (After|<X>).*$', '- <TRIGGER>', text, flags=re.M)

    kitchen, grill = _render('kitchen'), _render('grill')
    # The system prompts differ only by the actions available in each scene.
    assert kitchen['system'] in grill['system'].replace(
        '\nclose(l): close lid l.\n  Preconditions: the gripper is empty; l is open.\n  Effects: l is closed; the regions l '
        'closes off become unreachable and their contents are no longer visible.', ''
    )
    for part in ('initial_user', 'goal_check_system'):
        assert skeleton('kitchen', kitchen[part]) == skeleton('grill', grill[part])


BANNED_CONTENT = [
    # object-specific strategy, ordering or urgency advice, relevance statements,
    # cooking procedures, example answers, variant ids
    'phone', 'table_staging_area instead', 'DO NOT place', 'CHECK 1', 'CHECK 2', 'first', 'before', 'urgent',
    'important', 'priorit', 'cook', 'raw', 'serve', 'groceries go', 'mugs go', 'K1', 'G1', 'example', 'EXAMPLE',
    'such as chicken', 'blocker', 'OBSTRUCTED',
]


@pytest.mark.parametrize('scene', sorted(SCENES))
def test_prompt_v2_has_no_strategy_hints(scene) -> None:
    rendered = _render(scene)
    goal = SCENES[scene]['goal']
    for part, text in rendered.items():
        text = text.replace(goal, '')  # the goal is included verbatim and may use any words
        for banned in BANNED_CONTENT:
            assert banned not in text, f'{scene}/{part} contains {banned!r}'


def test_v2_rejects_in_context_examples() -> None:
    builder = PromptV2Builder()
    with pytest.raises(ValueError):
        builder.build_bundle(KITCHEN['state'], KITCHEN['goal'], icl_mode='few_shot_shared_1')


def test_prompt_v2_remembered_objects_snapshot() -> None:
    """memory.enabled: remembered (not visible) objects with last region and steps since last seen."""
    data = GRILL
    builder = PromptV2Builder()
    builder.set_symbol_registry(data['registry'])
    builder.set_replan_context(data['context'])
    builder.set_memory_view([('chicken', 'inside_grill', 3), ('steak', 'prep_area', 1)])
    state = SceneState(**{**data['state'].__dict__})
    state.visible_objects = ['steak1', 'plate', 'grill_lid']
    state.object_region_map = {'steak1': 'prep_area', 'plate': 'dish_rack'}
    text = builder.build_bundle(state, data['goal'], failure_event=data['trigger']).user_prompt
    path = SNAPSHOT_DIR / 'prompt_v2_grill_replan_user_memory.txt'
    if os.environ.get('UPDATE_PROMPT_SNAPSHOTS') == '1':
        path.write_text(text + '\n', encoding='utf-8')
    assert text + '\n' == path.read_text(encoding='utf-8')
    assert '- chicken: inside_grill, 3 steps ago' in text and '- steak: grill_side_area, 1 step ago' in text
