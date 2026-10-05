import math

from llm_pipeline.failure_logic import SegmentationFirstFailureChecker, held_objects_from_gripper
from llm_pipeline.failures import FailureCode
from llm_pipeline.pipeline_types import DirectAction, SegmentationObjectEvidence, SegmentationSnapshot
from llm_pipeline.randomization import FREE_OBJECTS, MOVABLE_OBJECTS, apply_pose_jitter


class Obj:
    _next = 100

    def __init__(self, name, pos=(0.0, 0.0, 0.8), parent=None):
        Obj._next += 1
        self.handle = Obj._next
        self.name = name
        self.pos = list(pos)
        self.ori = [0.0, 0.0, 0.0]
        self.parent = parent
        self.collide_with = set()

    def get_name(self):
        return self.name

    def get_handle(self):
        return self.handle

    def get_parent(self):
        return self.parent

    def get_position(self):
        return list(self.pos)

    def set_position(self, pos):
        self.pos = list(pos)

    def get_orientation(self):
        return list(self.ori)

    def set_orientation(self, ori):
        self.ori = list(ori)

    def get_objects_in_tree(self):
        return []

    def check_collision(self, other):
        return other.name in self.collide_with


class Gripper:
    def __init__(self, grasped=()):
        self.grasped = list(grasped)

    def get_grasped_objects(self):
        return list(self.grasped)


class Env:
    class PR:
        def step(self):
            return None

    def __init__(self, objects, grasped=(), tip=None):
        self.name_to_obj = {obj.name: obj for obj in objects}
        self.gripper = Gripper(grasped)
        self.pr = self.PR()
        tip = tip or Obj('Panda_tip')

        class Robot:
            def get_tip(self_inner):
                return tip

        self.robot = Robot()
        self.tip = tip


def _snapshot(visible):
    return SegmentationSnapshot(
        frame_index=1, visible_objects=list(visible), newly_visible_objects=[],
        object_evidence={name: SegmentationObjectEvidence(name=name, visible=True) for name in visible},
        gripper_evidence={}, supported_regions=['table'], visible_regions=[], object_region_map={},
        object_region_descriptions={},
    )


def test_held_objects_use_the_gripper_grasp_state_and_canonical_names() -> None:
    soup = Obj('soup')
    env = Env([soup], grasped=[soup])
    assert held_objects_from_gripper(env) == {'can_of_beans'}


def test_objects_parented_to_the_tip_count_as_held() -> None:
    tip = Obj('Panda_tip')
    chicken = Obj('chicken', parent=tip)
    env = Env([chicken], tip=tip)
    assert 'chicken' in held_objects_from_gripper(env)


def test_pick_postcheck_uses_gripper_state_not_mask_proximity() -> None:
    soup = Obj('soup')
    checker = SegmentationFirstFailureChecker(adapter=None, env=Env([soup], grasped=[soup]))
    checker.replan_on_new_visibility = False
    # The object is visible and no gripper centroid is known: the mask check would fail.
    assert checker.postcheck(DirectAction('pick', ('can_of_beans',)), 'can_of_beans', _snapshot(['can_of_beans'])) is None
    checker.env = Env([soup], grasped=[])
    failure = checker.postcheck(DirectAction('pick', ('can_of_beans',)), 'can_of_beans', _snapshot(['can_of_beans']))
    assert failure is not None and failure.failure_id == FailureCode.GRASP_FAILED
    checker.grasp_confirmation = 'segmentation'
    failure = checker.postcheck(DirectAction('pick', ('can_of_beans',)), 'can_of_beans', _snapshot(['can_of_beans']))
    assert failure is not None and failure.failure_id == FailureCode.GRASP_FAILED  # previous behavior


def _kitchen_env():
    return Env([Obj(name, pos=(0.1 * i, 0.2, 0.8)) for i, name in enumerate(MOVABLE_OBJECTS['K3'])])


def test_pose_jitter_is_seeded_bounded_and_leaves_fixed_objects() -> None:
    env_a, env_b = _kitchen_env(), _kitchen_env()
    before = {name: obj.get_position() for name, obj in env_a.name_to_obj.items()}
    rec_a = apply_pose_jitter(env_a, 'K3', seed=3)
    rec_b = apply_pose_jitter(env_b, 'K3', seed=3)
    assert rec_a['objects'] == rec_b['objects']
    assert apply_pose_jitter(_kitchen_env(), 'K3', seed=4)['objects'] != rec_a['objects']
    for name, obj in env_a.name_to_obj.items():
        if name in FREE_OBJECTS['K3']:
            entry = rec_a['objects'][name]
            assert entry['status'] == 'jittered'
            assert abs(entry['dx']) <= 0.03 and abs(entry['dy']) <= 0.03 and abs(entry['dyaw_deg']) <= 20
            assert math.isclose(obj.get_position()[0], before[name][0] + entry['dx'], abs_tol=1e-4)
        else:
            assert obj.get_position() == before[name], name
    assert set(rec_a['fixed']) == set(MOVABLE_OBJECTS['K3']) - set(FREE_OBJECTS['K3'])


def test_pose_jitter_rejects_overlaps_and_keeps_the_original_pose_if_needed() -> None:
    env = _kitchen_env()
    env.name_to_obj['sugar'].collide_with = {'mug1'}  # every sample of sugar overlaps mug1
    original = env.name_to_obj['sugar'].get_position()
    record = apply_pose_jitter(env, 'K3', seed=0)
    assert record['objects']['sugar']['status'] == 'kept_original'
    assert record['objects']['sugar']['last_rejection'] == 'touches mug1'
    assert env.name_to_obj['sugar'].get_position() == original
