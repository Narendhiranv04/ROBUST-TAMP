"""Unit tests of the baselines' model-independent parts (no simulator)."""

from baselines.common import Observation, SymbolicDomain
from baselines.owl_constraints import Geometry, RavenPose, evaluate, extract_functions
from baselines.owl_tamp import OWLDomain, astar_with_sketch, initial_predicates, parse_sketch
from baselines.vlm_tamp import objects_by_type, observed_descriptions, parse_subgoals, subgoal_test


def kitchen_obs():
    return Observation(objects={'mug1': 'table_right_area', 'mug2': 'box_lid_top', 'spam': 'table_right_area'},
                       lids={'box_lid': False}, holding=None,
                       regions=['table', 'table_center_area', 'cupboard_shelf', 'inside_box', 'table_right_area',
                                'box_lid_top'])


def test_vlm_tamp_parse_renames_skips_and_unknowns():
    obs = kitchen_obs()
    subgoals, skipped = parse_subgoals(
        "['opened-door(box_lid)', 'in(mug1, inside_box)', 'stirred(inside_box, mug1)', 'on(phone, table)']", obs)
    assert subgoals == [('openedjoint', 'box_lid'), ('in', 'mug1', 'inside_box')]
    assert 'stirred(inside_box, mug1)' in skipped and 'on(phone, table)' in skipped


def test_vlm_tamp_world_model_text():
    obs = kitchen_obs()
    assert 'the mug2 is on the box_lid_top' in observed_descriptions(obs)
    assert 'box_lid is fully closed' in observed_descriptions(obs)
    text = objects_by_type(obs)
    assert "'<door>': ['box_lid']" in text and "'<food>': ['spam']" in text and "'<space>'" in text


def test_vlm_tamp_refinement_opens_the_lid_after_clearing_its_top():
    obs = kitchen_obs()
    domain = SymbolicDomain(obs.objects, obs.regions, obs.lids)
    plan = domain.search(obs.symbolic(), subgoal_test(('in', 'mug1', 'inside_box')), max_depth=8)
    names = [a[0] for a in plan]
    assert names.index('open') > names.index('place')          # mug2 moved off the lid first
    assert plan[-1] == ('place', 'mug1', 'inside_box')


def test_owl_domain_supports_and_sketch_search():
    obs = kitchen_obs()
    domain = OWLDomain(obs)
    assert domain.target(('place_inside', 'mug1', 'inside_box')) == 'inside_box'
    assert domain.target(('place_inside', 'mug1', 'table')) == 'table'      # regions are placement areas
    assert domain.target(('place_ontop', 'mug1', 'inside_box')) == 'inside_box'
    assert domain.target(('place_inside', 'mug1', 'box_lid')) is None      # objects: only their top surface
    assert domain.target(('place_ontop', 'mug1', 'box_lid')) == 'box_lid_top'
    assert ('pick', 'table') in domain.ground_actions()        # relaxed grounding over every entity
    text = ("The mug goes in the box.\nPlan:\nopen(box_lid); open it\npick(mug1); grasp\n"
            "place_inside(mug1, inside_box); inside\nachieve_goal(mug1, inside_box); mug1 in the box")
    sketch, achieve, rejected = parse_sketch(text, set(domain.ground_actions()))
    assert [op for op, _ in sketch] == [('open', 'box_lid'), ('pick', 'mug1'), ('place_inside', 'mug1', 'inside_box')]
    assert achieve[0][0] == 'achieve_goal' and not rejected
    plan = astar_with_sketch(domain, obs.symbolic(), [op for op, _ in sketch])
    assert plan[-1] == ('place_inside', 'mug1', 'inside_box')
    assert plan.index(('open', 'box_lid')) > 0                  # mug2 moved off the lid before opening
    assert 'OnTop(mug2, box_lid_top)' in initial_predicates(obs) and 'Closed(box_lid)' in initial_predicates(obs)


def test_owl_constraints_sandbox():
    geo = Geometry({'inside_box': ((0.0, 0.0, 0.7), (0.3, 0.3, 0.9)), 'mug1': ((0.1, 0.1, 0.75), (0.2, 0.2, 0.85))},
                   {'mug1': RavenPose(0.15, 0.15, 0.8, 0, 0, 0)}, (-0.5, 0.0))
    functions, rejected = extract_functions(
        "```python\ndef goal_check0() -> bool:\n    b = modify_pose_bounds_to_be_inside_object(init_state, env, "
        "init_bounds, mug1.category, inside_box.category)\n    return position_within_bounds(mug1.pose, b)\n```\n"
        "```python\ndef goal_check1() -> bool:\n    import os\n    return True\n```")
    assert len(functions) == 1 and rejected
    ok, errors = evaluate(functions, geo, ['mug1', 'inside_box'])
    assert ok and not errors
    geo.poses['mug1'] = RavenPose(0.9, 0.9, 0.8, 0, 0, 0)
    assert not evaluate(functions, geo, ['mug1', 'inside_box'])[0]
    assert not evaluate(['def goal_check0() -> bool:\n    return undefined_name > 0'], geo, ['mug1'])[0]


def test_owl_constraint_scope():
    from baselines.owl_tamp import mentions

    own = "def goal_check0() -> bool:\n    return position_within_bounds(mug1.pose, b)"
    other = "def goal_check1() -> bool:\n    return spam.pose.z > 1.0"
    assert mentions(own, 'mug1') and not mentions(other, 'mug1') and mentions(other, 'spam')


def test_owl_real_constraints_accept_valid_placements():
    """Constraints the model wrote in the server run, on the geometry of those trials (regions are
    flat perception boxes; helpers called with and without init_state/env)."""
    boxes = {'cupboard_shelf': ((0.44, -0.172, 1.293), (0.534, 0.2, 1.293)),
             'inside_box': ((-0.054, 0.187, 0.752), (0.276, 0.473, 0.752)),
             'serving_area': ((-0.10, 0.12, 0.84), (0.16, 0.40, 0.84)),
             'spam': ((0.425, 0.012, 1.242), (0.535, 0.091, 1.322)),
             'mug2': ((0.10, 0.30, 0.76), (0.20, 0.37, 0.84)),
             'plate': ((-0.072, 0.155, 0.856), (0.133, 0.36, 0.906))}
    poses = {'spam': RavenPose(0.48, 0.051, 1.282, 0, 0, 0), 'mug2': RavenPose(0.146, 0.334, 0.8, 0, 0, -1.54),
             'plate': RavenPose(0.03, 0.258, 0.876, 0, 0, 0), 'raw_meat_1': RavenPose(0.007, 0.234, 0.876, 0, 0, 0)}
    geo = Geometry(boxes, poses, (-0.5, 0.0), regions={'cupboard_shelf', 'inside_box', 'serving_area'})
    names = list(boxes) + ['raw_meat_1']
    spam = ("def goal_check0() -> bool:\n    b = modify_pose_bounds_to_be_ontop_of_object(init_state, env, init_bounds, "
            "spam.category, cupboard_shelf.category)\n    return position_within_bounds(spam.pose, b)")
    mug = ("def goal_check0() -> bool:\n    b = get_aabb_bounds(init_state, env, 'inside_box')\n"
           "    return position_within_bounds(mug2.pose, b)")
    meat = ("def goal_check0() -> bool:\n    s = get_aabb_bounds(serving_area)\n    on = position_within_bounds(plate.pose, s)\n"
            "    b = modify_pose_bounds_to_be_ontop_of_object(init_state, env, init_bounds, raw_meat_1.category, plate.category)\n"
            "    return on and position_within_bounds(raw_meat_1.pose, b)")
    for fn in (spam, mug, meat):
        ok, errors = evaluate([fn], geo, names)
        assert ok and not errors, (fn, errors)
    far = ("def goal_check0() -> bool:\n    b = get_aabb_bounds(init_state, env, 'inside_box')\n"
           "    return position_within_bounds(spam.pose, b)")
    assert not evaluate([far], geo, names)[0]          # the spam is not in the box
