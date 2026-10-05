"""Unit tests of the EPoG re-implementation: global planner, local planner checks, resolve prompt and
parsing, the replan triggers of the main loop (mock planner and a symbolic fake world)."""

import json
import random

import networkx as nx

from baselines.common import Observation
from baselines.epog import (Action, ActionType, EPoGPipeline, MotionErrorType, NodeIds, SceneGraph, from_func_string,
                            ged_seq, parse_action_seq, parse_goal_relations, pick_place_constraints, pog_search,
                            resolve_user_message, rule_based_resolution, simulate_step,
                            example_resolution)
from baselines.tests.test_closed_loop_baselines import FakeWorld, make


def pick(o, p):
    return Action(ActionType.Pick, del_edge=(p, o))


def place(o, p):
    return Action(ActionType.Place, add_edge=(p, o))


def test_ged_seq_matches_networkx_optimal_edit_path_on_scene_trees():
    rng = random.Random(0)
    locations = ['table', 'shelf', 'box']
    for _ in range(25):
        objects = [f'o{i}' for i in range(rng.randint(1, 4))]
        start = SceneGraph(parent={o: rng.choice(locations) for o in objects})
        goal = SceneGraph(parent={o: rng.choice(locations) for o in objects})

        def tree(g):
            t = nx.DiGraph()
            for n in ['world'] + locations + objects:
                t.add_node(n, name=n)
            for p, c in [('world', loc) for loc in locations] + [(p, c) for c, p in g.parent.items()]:
                t.add_edge(p, c, edge=(p, c))
            return t
        # the authors' ged (pog/planning/ged.py): nodes and edges match by equality
        nodes, edges, cost = next(nx.optimize_edit_paths(
            tree(start), tree(goal), node_match=lambda a, b: a == b, edge_match=lambda a, b: a == b,
            roots=('world', 'world')))
        assert all(u == v for u, v in nodes)
        ours = ged_seq(start, goal)
        moved = sorted(o for o in objects if start.parent[o] != goal.parent[o])
        # a parent change is an edge deletion plus an insertion, which ged_seq pairs per object
        assert sorted(a[1] for _, a in ours) == moved and cost == 2 * len(moved)
        assert sorted(e[0][1] for e in edges if e[0] and not e[1]) == moved
        assert sorted(e[1][1] for e in edges if e[1] and not e[0]) == moved
    held = SceneGraph(parent={}, hand='o1')
    assert ged_seq(held, SceneGraph(parent={'o1': 'box'})) == [(None, ('box', 'o1'))]
    assert ged_seq(SceneGraph(parent={'phone': 'box'}), SceneGraph(parent={})) == []     # obstacles ignored


def test_constraints_and_pog_search_order_the_plan():
    pairs = [(('table', 'mug1'), ('box', 'mug1')), (None, ('shelf', 'spam')), (('shelf', 'mug3'), ('box', 'mug3'))]
    actions, constraints = pick_place_constraints(pairs, random.Random(3))
    plan, _ = pog_search(actions, constraints)
    assert plan[0] == place('spam', 'shelf')                        # the object in the hand is placed first
    for i, a in enumerate(plan):
        if a.action_type == ActionType.Pick:
            assert plan[i + 1] == place(a.child, 'box')            # a pick is followed by its place
    assert len(plan) == 5


def test_simulate_step_errors_in_the_authors_order_and_text():
    ids = NodeIds()
    for n in ['table_center_area', 'inside_box', 'box_lid_top', 'mug1', 'mug2', 'phone', 'plate', 'meat', 'serving_area']:
        ids[n]
    goal = SceneGraph(parent={'mug1': 'inside_box', 'mug2': 'inside_box'})
    g = SceneGraph(parent={'mug1': 'table_center_area', 'mug2': 'box_lid_top', 'phone': 'inside_box'}, closed={'inside_box'},
                   overlaps={'phone': ('inside_box',)})
    err = simulate_step(g.copy(), place('mug1', 'inside_box'), goal, ids)
    assert err.error_type == MotionErrorType.AccessError and err.involved_nodes == ['inside_box']
    assert err.reason == f'object {ids["mug1"]} is not accessible, because [{ids["inside_box"]}] is closed'
    err = simulate_step(g.copy(), Action(ActionType.Open, ('inside_box', 'inside_box'), ('inside_box', 'inside_box')), goal, ids)
    assert err.error_type == MotionErrorType.BlockError and err.involved_nodes == ['mug2']
    g.closed = set()
    err = simulate_step(g.copy(), place('mug1', 'inside_box'), goal, ids)
    assert err.error_type == MotionErrorType.CollisionError and err.involved_nodes == ['phone']
    assert err.observation_involved == [f'{ids["phone"]} on {ids["inside_box"]}']
    g.overlaps = {}                                              # not in the placement area: no collision
    assert simulate_step(g.copy(), place('mug1', 'inside_box'), goal, ids) is None
    plated = SceneGraph(parent={'plate': 'serving_area', 'meat': 'plate'})
    err = simulate_step(plated, pick('plate', 'serving_area'), SceneGraph(), ids)
    assert err.error_type == MotionErrorType.StabilityError and err.involved_nodes == ['meat']
    # an object whose goal is the region is not a collision
    g = SceneGraph(parent={'mug2': 'inside_box'}, overlaps={'mug2': ('inside_box',)})
    assert simulate_step(g, place('mug1', 'inside_box'), goal, ids) is None and g.parent['mug1'] == 'inside_box'


def test_resolve_prompt_parsing_and_rule_based_agent():
    ids = NodeIds()
    for n in ['table_center_area', 'inside_box', 'mug1', 'phone']:
        ids[n]
    g = SceneGraph(parent={'phone': 'inside_box'}, hand='mug1', overlaps={'phone': ('inside_box',)})
    err = simulate_step(g, place('mug1', 'inside_box'), SceneGraph(parent={'mug1': 'inside_box'}), ids)
    err.parking_place = ids['table_center_area']
    text = resolve_user_message(err, ids)
    assert 'The parking place is 1, you can place temporarily place the object here.' in text
    assert f'Your robot is trying to Place {ids["mug1"]} on {ids["inside_box"]} but it failed.' in text
    assert 'Error Type: MotionErrorType.CollisionError' in text
    assert rule_based_resolution(err, ids) == [f'Pick({ids["phone"]}, 2)', 'Place(4, 1)', 'Place(3, 2)']
    assert from_func_string('Place(3, 2)', ids) == place('mug1', 'inside_box')
    assert from_func_string('Pick(4, 2)', ids) == pick('phone', 'inside_box')
    assert from_func_string('Open(2)', ids).action_type == ActionType.Open
    assert from_func_string('Put(3, 2)', ids) is None and from_func_string('Pick(99, 2)', ids) is None
    assert from_func_string('Place(3,2)', ids) == place('mug1', 'inside_box')      # spacing tolerated
    assert from_func_string(' Open( 2 ) ', ids).action_type == ActionType.Open
    assert parse_action_seq('{"steps": [], "final_answer": [{"action": "Pick(4, 2)"}]}') == ['Pick(4, 2)']
    assert parse_action_seq('{"final_answer": []}') is None and parse_action_seq('not json') is None


def test_goal_relations_are_grounded_to_graph_nodes():
    obs = Observation(objects={'meat': 'grill_side_area', 'plate': 'dish_rack', 'mug9': 'table'}, lids={}, holding=None,
                      regions=['dish_rack', 'serving_area', 'plate_top', 'grill_side_area'])
    text = json.dumps({'relations': [{'children': 'meat', 'relationType': 'on', 'parent': 'plate_top'},
                                     {'children': 'plate', 'relationType': 'on', 'parent': 'serving_area'},
                                     {'children': 'ghost', 'relationType': 'on', 'parent': 'serving_area'},
                                     {'children': 'mug9', 'relationType': 'on', 'parent': 'moon'}]})
    goal, rejected = parse_goal_relations(text, ['meat', 'plate', 'mug9'], obs)
    assert goal == {'meat': 'plate', 'plate': 'serving_area'} and len(rejected) == 2


class EPoGWorld(FakeWorld):
    """The fake world with a gripper: a picked object leaves its region; opening needs an empty
    gripper and a clear lid top (our pre-action checks)."""

    holding = None

    def observation(self):
        obs = super().observation()
        obs.regions.append('table_center_area')
        if self.holding:
            obs.objects.pop(self.holding, None)
            obs.objects[self.holding] = None
            obs.holding = self.holding
        return obs

    def execute(self, bundle):
        for a in bundle:
            text = f"{a[0]}({', '.join(a[1:])})"
            if a[0] == 'open' and self.holding:
                return {'success': False, 'failure': 'holding', 'failure_code': 'invalid_executor_state',
                        'failed_action': text}
            if a[0] == 'open' and any(r == 'box_lid_top' for r in self.objects.values()):
                return {'success': False, 'failure': 'lid obstructed', 'failure_code': 'box_lid_obstructed',
                        'failed_action': text}
            if a[0] == 'pick':
                if self.holding:
                    return {'success': False, 'failure': 'holding', 'failure_code': 'invalid_executor_state',
                            'failed_action': text}
                self.holding = a[1]
                self.objects.pop(a[1], None)
                self.hidden.pop(a[1], None)
            elif a[0] == 'place':
                self.holding = None
                self.objects[a[1]] = a[2]
            elif a[0] == 'open':
                self.lid_open = True
            self.executed.append(text)
        return {'success': True, 'failure': None, 'failure_code': None, 'failed_action': None}


def make_epog(world, goal, resolver=None, max_replans=10, cls=EPoGPipeline):
    def respond(purpose, prompt, n):
        if purpose == 'epog_goal_graph':
            wanted = prompt.rsplit('child is one of these objects: ', 1)[1].split(', relationType', 1)[0].split(', ')
            return json.dumps({'relations': [{'children': o, 'relationType': 'in', 'parent': goal[o]}
                                             for o in wanted if o in goal]})
        actions = (resolver or (lambda p: example_resolution(p._last_motion_error, p.ids)))(pipeline)
        return json.dumps({'steps': [], 'final_answer': [{'action': a} for a in actions]})

    pipeline, prompts = make(cls, world, respond, max_replans=max_replans)
    pipeline.config.seed = 0
    pipeline.placement_overlaps = lambda obj: ['inside_box'] if world.observation().objects.get(obj) == 'inside_box' else []
    return pipeline, prompts


def test_epog_kitchen_loop_access_block_collision_and_global_replan():
    # the goal graph from the goal specification: mugs -> inside_box, groceries -> cupboard_shelf;
    # the phone (no goal) is an obstacle on the lid; the hidden can is a grocery in the box
    world = EPoGWorld({'mug1': 'table', 'mug2': 'table', 'phone': 'box_lid_top'}, hidden={'can_of_beans': 'inside_box'})
    pipeline, prompts = make_epog(world, {})
    assert pipeline.run_baseline('move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box') is None
    done = world.executed
    assert done.index('place(phone, table_center_area)') < done.index('open(box_lid)')        # BlockError
    assert world.objects['mug1'] == 'inside_box' and world.objects['mug2'] == 'inside_box'
    assert world.objects['can_of_beans'] == 'cupboard_shelf' and world.objects['phone'] == 'table_center_area'
    trace = pipeline._baseline_trace
    kinds = [r['error_type'] for r in trace['resolves']]
    assert 'AccessError' in kinds and 'BlockError' in kinds
    assert trace['goal_graph'] == {'mug1': 'in inside_box', 'mug2': 'in inside_box'}
    assert trace['final_goal_graph']['can_of_beans'] == 'in cupboard_shelf'      # added when observed
    assert len(trace['global_plans']) >= 2                                      # the can appeared: a global replan
    assert all(p == 'epog_resolve' for p, _ in prompts)                          # no goal-graph model calls
    assert trace['budget_use']['resolve_calls'] == len(trace['resolves'])
    assert trace['baseline_terminated_normally'] if 'baseline_terminated_normally' in trace else True


def test_epog_goal_relations_from_the_goal_specification():
    from baselines.epog import goal_relations

    assert goal_relations(['mug3', 'spam', 'phone', 'can_of_beans_2'], 'kitchen') == {
        'mug3': ('in', 'inside_box'), 'spam': ('in', 'cupboard_shelf'), 'can_of_beans_2': ('in', 'cupboard_shelf')}
    assert goal_relations(['plate', 'raw_meat_1', 'cooked_meat_2'], 'grill') == {
        'plate': ('on', 'serving_area'), 'raw_meat_1': ('on', 'plate'), 'cooked_meat_2': ('on', 'plate')}


def test_epog_language_goal_variant_queries_the_model():
    from baselines.epog import EPoGLanguageGoalPipeline

    world = EPoGWorld({'mug1': 'table'})
    pipeline, prompts = make_epog(world, {'mug1': 'inside_box'}, cls=EPoGLanguageGoalPipeline)
    assert pipeline.run_baseline('put the mug in the box') is None
    assert [p for p, _ in prompts][0] == 'epog_goal_graph' and world.objects['mug1'] == 'inside_box'


def test_epog_resolve_calls_are_capped_by_the_budget():
    world = EPoGWorld({'mug1': 'table'})
    pipeline, prompts = make_epog(world, {'mug1': 'inside_box'}, resolver=lambda p: ['Place(5, 2)'], max_replans=3)
    reason = pipeline.run_baseline('put the mug in the box')
    assert 'replan budget exhausted' in reason and pipeline.termination_reason == 'replan_budget_exhausted'
    assert sum(1 for p, _ in prompts if p == 'epog_resolve') == 3


def test_unresolved_regions_hang_off_the_root_and_are_still_planned():
    from baselines.epog import ROOT, graph_from_observation

    obs = Observation(objects={'mug1': None, 'mug2': 'table'}, lids={'box_lid': True}, holding=None,
                      regions=['table', 'inside_box'])
    belief = graph_from_observation(obs, {})
    assert belief.parent == {'mug1': ROOT, 'mug2': 'table'}
    assert ged_seq(belief, SceneGraph(parent={'mug1': 'inside_box'})) == [((ROOT, 'mug1'), ('inside_box', 'mug1'))]


def test_resolve_calls_carry_the_latest_image():
    world = EPoGWorld({'mug1': 'table', 'phone': 'box_lid_top'})
    pipeline, prompts = make_epog(world, {'mug1': 'inside_box'})
    images = []
    pipeline.query_image = lambda obs: images.append(dict(obs.objects)) or None
    assert pipeline.run_baseline('put the mug in the box') is None
    # the first resolve is planned from the initial observation; later calls see the updated scene
    assert images[0] == {'mug1': 'table', 'phone': 'box_lid_top'}
    assert pipeline.obs.objects == world.observation().objects


def test_resolve_schema_requires_the_fields_the_authors_validator_requires():
    from baselines.epog import RESOLVE_SCHEMA

    schema = RESOLVE_SCHEMA['schema']['properties']
    assert schema['steps']['items']['required'] == ['explanation', 'output']
    assert schema['final_answer']['items']['required'] == ['action']
