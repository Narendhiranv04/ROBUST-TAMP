"""In-context examples for the baselines (``icl_mode = examples_v2``), grill scene only.

The same two examples our planner receives in its ICL condition (llm_pipeline/icl_examples.py,
``examples_v2``): a laundry dryer, where a wet towel dries only by being inside the dryer while its
door is closed and opened again, and a dry towel inside during another close / open is scorched.
Example 1 asks for a full plan; Example 2 comes after the dryer is opened and an already dry towel
is found inside. Each shows a good and a bad answer and what happened afterwards; no rule is stated,
and they name no object, lid or region of the grill scene.

Each baseline gets them in its own input and answer format, so the examples show the answer the
baseline is asked for: LLM-Planner a JSON "Plan" with Pick(x, y) sources; Inner Monologue the
monologue and FINAL ACTIONS; VLM-TAMP its observed-object facts, its formal history and English
intermediate goals; OWL-TAMP the initial predicate state and a plan of ground operators ending in
achieve_goal. Our Example 2 is a corrective block (a format only our planner has); here it is the
baseline's own query at that point (a replan after new objects became visible, the next step of
the monologue, a query with the history). EPoG's model only resolves motion errors (its plan comes
from the goal graph, which cannot express the close / open cycle), so its examples are resolve-call
examples: a failed place into the dryer, resolved with or without the close / open cycle.

Placement: appended to the baseline's system prompt where it has one (LLM-Planner, Inner
Monologue), as our planner's are; VLM-TAMP and OWL-TAMP send one user message, so the examples go
at its end (VLM-TAMP: before the image description, which refers to the attached image).
"""

from __future__ import annotations

from typing import Optional

ICL_MODES = ('zero_shot', 'examples_v2')

GOAL = 'DRY all wet towels using the dryer and PUT all dry towels in the BASKET in the laundry area.'
HEADER = 'Examples (from a different scene; its objects, lids and regions are not in your scene):'

# the plans, as (action, object, region) with the region an object is picked from
_FULL_GOOD = [('pick', 'basket', 'shelf'), ('place', 'basket', 'laundry_area'), ('open', 'dryer_door'),
              ('pick', 'wet_towel_1', 'counter'), ('place', 'wet_towel_1', 'inside_dryer'), ('close', 'dryer_door'),
              ('open', 'dryer_door'), ('pick', 'wet_towel_1', 'inside_dryer'), ('place', 'wet_towel_1', 'basket_top')]
_FULL_BAD = [('open', 'dryer_door'), ('pick', 'wet_towel_1', 'counter'), ('place', 'wet_towel_1', 'inside_dryer'),
             ('pick', 'wet_towel_1', 'inside_dryer'), ('place', 'wet_towel_1', 'basket_top')]
_CYCLE = [('pick', 'wet_towel_1', 'counter'), ('place', 'wet_towel_1', 'inside_dryer'), ('close', 'dryer_door'),
          ('open', 'dryer_door'), ('pick', 'wet_towel_1', 'inside_dryer'), ('place', 'wet_towel_1', 'basket_top')]
_DRY_OUT = [('pick', 'dry_towel_2', 'inside_dryer'), ('place', 'dry_towel_2', 'basket_top')]
_CORR_GOOD = _DRY_OUT + _CYCLE
_CORR_BAD = _CYCLE + _DRY_OUT

FULL_GOOD_OUTCOME = 'Outcome: the towel came out dry and is in the basket in the laundry area. Goal met.'
FULL_BAD_OUTCOME = 'Outcome: the towel is still wet, and the basket is still on the shelf. Goal not met.'
CORR_GOOD_OUTCOME = 'Outcome: both towels are dry and in the basket. Goal met.'
CORR_BAD_OUTCOME = ('Outcome: dry_towel_2 was still inside during close(dryer_door) and open(dryer_door) and came '
                    'out scorched. Goal not met.')

REGIONS = ['counter', 'shelf', 'inside_dryer', 'basket_top', 'laundry_area']
# the two states (object -> region), the lid's state
FULL_STATE = {'basket': 'shelf', 'wet_towel_1': 'counter'}
CORR_STATE = {'basket': 'laundry_area', 'wet_towel_1': 'counter', 'dry_towel_2': 'inside_dryer'}


def _lower(a) -> str:
    """Our action text: pick(o), place(o, r), open(l), close(l)."""
    if a[0] == 'pick':
        return f'pick({a[1]})'
    return f'{a[0]}({a[1]}, {a[2]})' if a[0] == 'place' else f'{a[0]}({a[1]})'


# --- LLM-Planner: its state description and JSON "Plan" -------------------------------------------

def _llm_planner_state(objects: dict, door_open: bool) -> str:
    lines = [f'{o} is {"in" if r.startswith("inside") else "on"} {r}' for o, r in objects.items()]
    lines.append(f'dryer_door is {"open" if door_open else "closed"} (it closes off inside_dryer)')
    lines += ['The robot is holding nothing', 'Locations: ' + ', '.join(REGIONS)]
    return '\n'.join(lines)


def _llm_planner_plan(actions) -> str:
    def entry(a):
        if a[0] in ('pick', 'place'):
            return f'"{a[0].capitalize()}({a[1]}, {a[2]})"'
        return f'"{a[0].capitalize()}({a[1]})"'
    return '{"Plan": [' + ', '.join(entry(a) for a in actions) + ']}'


def llm_planner_examples() -> str:
    def example(title, objects, door_open, good, good_outcome, bad, bad_outcome):
        return '\n'.join([title, 'The current state of the environment is given below.',
                          _llm_planner_state(objects, door_open), 'The goal state is given below.', GOAL, '',
                          'Good answer:', _llm_planner_plan(good), good_outcome, '',
                          'Bad answer:', _llm_planner_plan(bad), bad_outcome])
    return '\n\n'.join([
        HEADER,
        example('Example 1 (the first plan)', FULL_STATE, False, _FULL_GOOD, FULL_GOOD_OUTCOME, _FULL_BAD,
                FULL_BAD_OUTCOME),
        example('Example 2 (a new plan after Pick(basket, shelf), Place(basket, laundry_area), Open(dryer_door): '
                'new objects observed: dry_towel_2)', CORR_STATE, True, _CORR_GOOD, CORR_GOOD_OUTCOME, _CORR_BAD,
                CORR_BAD_OUTCOME)])


# --- Inner Monologue: the monologue, prompt v2 state, FINAL ACTIONS -------------------------------

def _v2_state(objects: dict, door_open: bool) -> str:
    lines = ['## Current state', 'Visible objects and the region each one is in:']
    lines += [f'- {o}: {r}' for o, r in objects.items()]
    lines += ['Lids:', f'- dryer_door: {"open" if door_open else "closed"} (closes off inside_dryer)', 'Gripper: empty',
              'Regions: ' + ', '.join(REGIONS)]
    return '\n'.join(lines)


def _final_actions(actions) -> str:
    return 'FINAL ACTIONS:\n' + '\n'.join(_lower(a) for a in actions)


def inner_monologue_examples() -> str:
    first_scene = 'Scene: visible objects: basket (shelf), wet_towel_1 (counter).'
    corr_monologue = [first_scene, 'Robot action: pick(basket), place(basket, laundry_area)', 'Success: True',
                      'Scene: no new objects.', 'Robot action: open(dryer_door)', 'Success: True',
                      'Scene: newly visible objects: dry_towel_2 (inside_dryer).']

    def example(title, monologue, objects, door_open, good, good_outcome, bad, bad_outcome):
        return '\n'.join([title, '## Goal', GOAL, '## Inner monologue so far', *monologue,
                          _v2_state(objects, door_open), '', 'Good answer:', _final_actions(good), good_outcome, '',
                          'Bad answer:', _final_actions(bad), bad_outcome])
    return '\n\n'.join([
        HEADER,
        example('Example 1 (the first request)', [first_scene], FULL_STATE, False, _FULL_GOOD, FULL_GOOD_OUTCOME,
                _FULL_BAD, FULL_BAD_OUTCOME),
        example('Example 2 (a later request)', corr_monologue, CORR_STATE, True, _CORR_GOOD, CORR_GOOD_OUTCOME,
                _CORR_BAD, CORR_BAD_OUTCOME)])


# --- VLM-TAMP: observed facts, formal history, English intermediate goals -------------------------

def _english(a) -> str:
    if a[0] == 'pick':
        return f'Pick up {a[1]} from the {a[2]}'
    if a[0] == 'place':
        return f'Place {a[1]} inside the {a[2]}' if a[2].startswith('inside') else f'Place {a[1]} on the {a[2]}'
    return f'{a[0].capitalize()} the {a[1]}'


def vlm_tamp_examples() -> str:
    def observed(state, door_open):
        lines = [f'the {o} is {"in" if r.startswith("inside") else "on"} the {r}' for o, r in state.items()]
        return ',\n'.join(lines + [f'dryer_door is {"fully open" if door_open else "fully closed"}'])

    def example(title, state, door_open, history, good, good_outcome, bad, bad_outcome):
        names = list(state) + REGIONS + ['dryer_door']
        return '\n'.join([title, f'Goal: ``{GOAL}\'\'.', f'Objects: {names}.',
                          f'Currently, you can see the following objects:\n``{observed(state, door_open)}\'\'',
                          *history, '', 'Good answer:', *[_english(a) for a in good], good_outcome, '',
                          'Bad answer:', *[_english(a) for a in bad], bad_outcome])
    history = ['You have already taken the following actions written in a formal language:',
               '1. on(basket, laundry_area)', '2. openedjoint(dryer_door)']
    return '\n\n'.join([
        HEADER,
        example('Example 1', FULL_STATE, False, [], _FULL_GOOD, FULL_GOOD_OUTCOME, _FULL_BAD, FULL_BAD_OUTCOME),
        example('Example 2', CORR_STATE, True, history, _CORR_GOOD, CORR_GOOD_OUTCOME, _CORR_BAD, CORR_BAD_OUTCOME)])


# --- OWL-TAMP: initial predicates, plan of ground operators with descriptions, achieve_goal -------

def _owl_operator(a) -> str:
    if a[0] == 'pick':
        return f'pick({a[1]}); grasp {a[1]}'
    if a[0] == 'place':
        inside = a[2].startswith('inside')
        return (f'place_{"inside" if inside else "ontop"}({a[1]}, {a[2]}); '
                f'place {a[1]} {"inside" if inside else "on"} {a[2]}')
    return f'{a[0]}({a[1]}); {a[0]} {a[1]}'


def owl_tamp_examples() -> str:
    def predicates(state, door_open):
        atoms = [f'{"Inside" if r.startswith("inside") else "OnTop"}({o}, {r})' for o, r in state.items()]
        return '\n'.join(atoms + [f'{"Open" if door_open else "Closed"}(dryer_door)', 'HandEmpty()'])

    def example(title, state, door_open, good, good_achieve, good_outcome, bad, bad_achieve, bad_outcome):
        return '\n'.join([title, f"Task: ''{GOAL}''", 'Initial predicate state:', predicates(state, door_open), '',
                          'Good answer:', 'Plan:', *[_owl_operator(a) for a in good], good_achieve, good_outcome, '',
                          'Bad answer:', 'Plan:', *[_owl_operator(a) for a in bad], bad_achieve, bad_outcome])
    one = 'achieve_goal(wet_towel_1, basket); wet_towel_1 is dry and in the basket, and the basket is in the laundry area'
    two = ('achieve_goal(wet_towel_1, dry_towel_2, basket); both towels are dry and in the basket, and the basket is '
           'in the laundry area')
    return '\n\n'.join([
        HEADER,
        example('Example 1', FULL_STATE, False, _FULL_GOOD, one, FULL_GOOD_OUTCOME, _FULL_BAD, one, FULL_BAD_OUTCOME),
        example('Example 2', CORR_STATE, True, _CORR_GOOD, two, CORR_GOOD_OUTCOME, _CORR_BAD, two, CORR_BAD_OUTCOME)])


# --- EPoG: the resolve call's worked-example format (numeric node ids, step analysis, action sequence) --

def epog_examples() -> str:
    """The examples as resolve-call examples, with what each node id is (the authors' example has bare ids).
    Example 1: placing the wet towel into the closed dryer fails (access); Example 2: placing it fails
    because the dry towel is inside (collision)."""
    key = ('In these examples, 0 is the parking place (counter), 1 is wet_towel_1, 2 is inside_dryer, 3 is '
           'dryer_door, 4 is dry_towel_2, 5 is basket_top (in the basket, in the laundry area).')

    def seq(actions):
        return 'action sequence: [' + ', '.join(f'"{a}"' for a in actions) + ']'
    one = '\n'.join([
        'Example 1', 'error: "place 1 on 2 is failure and object 2 is in closed container 3"',
        'Good answer:', seq(['Place(1, 0)', 'Open(3)', 'Pick(1, 0)', 'Place(1, 2)', 'Close(3)', 'Open(3)',
                             'Pick(1, 2)', 'Place(1, 5)']),
        FULL_GOOD_OUTCOME,
        'Bad answer:', seq(['Place(1, 0)', 'Open(3)', 'Pick(1, 0)', 'Place(1, 2)', 'Pick(1, 2)', 'Place(1, 5)']),
        'Outcome: the towel is still wet. Goal not met.'])
    two = '\n'.join([
        'Example 2', 'error: "place 1 on 2 is failure and object 1 will be collision with [4]"',
        'Good answer:', seq(['Place(1, 0)', 'Pick(4, 2)', 'Place(4, 5)', 'Pick(1, 0)', 'Place(1, 2)', 'Close(3)',
                             'Open(3)', 'Pick(1, 2)', 'Place(1, 5)']),
        CORR_GOOD_OUTCOME,
        'Bad answer:', seq(['Place(1, 0)', 'Close(3)', 'Open(3)', 'Pick(4, 2)', 'Place(4, 5)', 'Pick(1, 0)',
                            'Place(1, 2)', 'Pick(1, 2)', 'Place(1, 5)']),
        'Outcome: object 4 was still inside during Close(3) and Open(3) and came out scorched, and object 1 is still '
        'wet. Goal not met.'])
    return '\n'.join(['More examples, from a different scene (a laundry dryer: ' + GOAL + ')', key, one, two])


EXAMPLES = {'epog': epog_examples, 'llm_planner': llm_planner_examples, 'inner_monologue': inner_monologue_examples,
            'vlm_tamp': vlm_tamp_examples, 'owl_tamp': owl_tamp_examples}


def examples_for(pipeline, baseline: Optional[str] = None) -> str:
    """The examples text for this pipeline's baseline, or '' (zero-shot, a kitchen scene, or EPoG)."""
    config = pipeline.config
    mode = getattr(config, 'icl_mode', 'zero_shot') or 'zero_shot'
    if mode not in ICL_MODES:
        raise ValueError(f'baselines support icl_mode {ICL_MODES}, got {mode}')
    if mode == 'zero_shot' or (getattr(config, 'task_family', '') or '').lower() != 'grill':
        return ''
    render = EXAMPLES.get(baseline or pipeline.baseline_name)
    return render() if render else ''


__all__ = ['examples_for', 'EXAMPLES', 'ICL_MODES', 'epog_examples', 'llm_planner_examples', 'inner_monologue_examples',
           'vlm_tamp_examples', 'owl_tamp_examples']
