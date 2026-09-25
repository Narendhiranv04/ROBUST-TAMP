"""Segmentation-first failure checks and structured replanning events."""

from __future__ import annotations

from typing import Iterable, Optional

from llm_pipeline.segmentation_adapter import SegmentationEvidenceAdapter
from llm_pipeline.pipeline_types import (
    DirectAction,
    FailureEvent,
    FailureLayer,
    FailureSource,
    FailureStage,
    SegmentationSnapshot,
)
from llm_pipeline.region_aliases import normalize_region_name, regions_match_for_target, scene_object_for_region
from llm_pipeline.failures import FailureCode, LAYER_1_FAILURE_CODES, LAYER_2_FAILURE_CODES
from llm_pipeline.object_aliases import canonical_object_name, scene_object_for_object


# Legacy layer sets (record.json ``failure_layer``), derived from the shared enum.
LAYER_1_FAILURE_IDS = LAYER_1_FAILURE_CODES
LAYER_2_FAILURE_IDS = LAYER_2_FAILURE_CODES


def held_objects_from_gripper(env) -> Optional[set]:
    """Canonical names of the objects the gripper holds, from the simulator's grasp state.

    An object counts as held when the gripper reports it as grasped (attached to the
    gripper's attach point by ``Gripper.grasp``) or when it is parented to the robot
    tip or the gripper attach point (the grill executor's manual attach). This is a
    stand-in for perception, like the lid states. Returns ``None`` when the env has
    no gripper, so the caller can fall back to the segmentation check.
    """
    gripper = getattr(env, 'gripper', None)
    if gripper is None or not hasattr(gripper, 'get_grasped_objects'):
        return None
    names = set()
    try:
        for obj in gripper.get_grasped_objects() or []:
            names.add(canonical_object_name(obj.get_name()))
    except Exception:
        return None
    holders = set()
    for getter in (lambda: env.robot.get_tip(), lambda: gripper.get_attach_point() if hasattr(gripper, 'get_attach_point') else None):
        try:
            holder = getter()
            if holder is not None:
                holders.add(int(holder.get_handle()))
        except Exception:
            pass
    fingers = _finger_shapes(env)
    closed = _gripper_not_fully_open(gripper)
    for name, obj in (getattr(env, 'name_to_obj', {}) or {}).items():
        try:
            parent = obj.get_parent() if obj is not None else None
            if parent is not None and int(parent.get_handle()) in holders:
                names.add(canonical_object_name(name))
                names.add(canonical_object_name(obj.get_name()))
                continue
            # Scripted picks (e.g. the cupboard mug) close the fingers on the object and
            # carry it kinematically without attaching it: count finger contact.
            if closed and fingers and obj is not None and _finger_distance(fingers, obj) <= FINGER_CONTACT_M:
                names.add(canonical_object_name(name))
                names.add(canonical_object_name(obj.get_name()))
        except Exception:
            continue
    return names


FINGER_CONTACT_M = 0.01
FINGER_SHAPE_NAMES = ('Panda_leftfinger_respondable', 'Panda_rightfinger_respondable')


def _finger_shapes(env) -> list:
    cached = getattr(env, '_grasp_check_finger_shapes', None)
    if cached is not None:
        return cached
    shapes = []
    try:
        from pyrep.objects.shape import Shape

        for name in FINGER_SHAPE_NAMES:
            try:
                shapes.append(Shape(name))
            except Exception:
                pass
    except Exception:
        shapes = []
    try:
        env._grasp_check_finger_shapes = shapes
    except Exception:
        pass
    return shapes


def _gripper_not_fully_open(gripper) -> bool:
    try:
        amounts = [float(v) for v in gripper.get_open_amount()]
    except Exception:
        return False
    return bool(amounts) and min(amounts) < 0.9


def _finger_distance(fingers, obj) -> float:
    best = float('inf')
    for finger in fingers:
        try:
            best = min(best, float(finger.check_distance(obj)))
        except Exception:
            continue
    return best


def failure_layer_for_id(failure_id: str) -> FailureLayer:
    """Return the single logical layer for a known failure id."""
    if failure_id in LAYER_2_FAILURE_IDS:
        return FailureLayer.LAYER_2
    return FailureLayer.LAYER_1


class SegmentationFirstFailureChecker:
    """Produces structured failures from segmentation and low-level runtime signals."""

    def __init__(
        self,
        adapter: SegmentationEvidenceAdapter,
        env=None,
        gripper_threshold: float = 0.4,
        replan_on_new_visibility: bool = True,
    ):
        self.adapter = adapter
        self.env = env
        self.gripper_threshold = gripper_threshold
        self.replan_on_new_visibility = replan_on_new_visibility
        self.discovery_ignore_objects = {'box_lid'}
        # grasp.confirmation flag: 'gripper_state' reads the gripper's grasped-object
        # state (a stand-in for perception, docs/ARCHITECTURE.md); 'segmentation' is
        # the previous mask-proximity check.
        self.grasp_confirmation = 'gripper_state'
        # memory.enabled: callable(object) -> True when a remembered object that is not
        # visible may be picked (its last region is reachable now).
        self.remembered_pick_allowed = None

    def capture_snapshot(self, event: str = '') -> SegmentationSnapshot:
        return self.adapter.capture_snapshot(event=event)

    def precheck(
        self,
        action: DirectAction,
        held_object: Optional[str],
        snapshot: SegmentationSnapshot,
        last_action_name: Optional[str] = None,
    ) -> Optional[FailureEvent]:


        if action.action_name == 'pick':
            object_name = action.args[0]
            if held_object is not None:
                return FailureEvent(
                    failure_id=FailureCode.INVALID_EXECUTOR_STATE,
                    stage=FailureStage.BEFORE_EXECUTION,
                    source=FailureSource.EXECUTOR,
                    action=str(action),
                    evidence={'held_object': held_object, 'expected_empty_gripper': True},
                    failure_layer=FailureLayer.LAYER_1,
                    should_replan=False,
                    message=f'Cannot pick {object_name} while already holding {held_object}',
                )

            evidence = snapshot.object_evidence.get(object_name)
            remembered_ok = callable(self.remembered_pick_allowed) and self.remembered_pick_allowed(object_name)
            if (evidence is None or not evidence.visible) and not remembered_ok:
                return FailureEvent(
                    failure_id=FailureCode.PICK_OBJECT_MISSING,
                    stage=FailureStage.BEFORE_EXECUTION,
                    source=FailureSource.SEGMENTATION,
                    action=str(action),
                    evidence={'object_name': object_name, 'visible_objects': snapshot.visible_objects},
                    failure_layer=FailureLayer.LAYER_1,
                    message=f'Cannot pick {object_name} because it is not visible in the segmentation snapshot',
                )
            return None

        if action.action_name == 'place':
            object_name, target_region = action.args
            target_region = normalize_region_name(target_region)
            if held_object != object_name:
                return FailureEvent(
                    failure_id=FailureCode.INVALID_EXECUTOR_STATE,
                    stage=FailureStage.BEFORE_EXECUTION,
                    source=FailureSource.EXECUTOR,
                    action=str(action),
                    evidence={'held_object': held_object, 'place_object': object_name, 'target_region': target_region},
                    failure_layer=FailureLayer.LAYER_1,
                    should_replan=False,
                    message=f'Cannot place {object_name} while holding {held_object}',
                )
            if target_region == 'inside_box':
                lid_name = 'box_lid'
                lid_evidence = snapshot.object_evidence.get(lid_name)
                if lid_evidence is not None and lid_evidence.visible and not self._is_lid_open(snapshot, lid_name):
                    return FailureEvent(
                        failure_id=FailureCode.BOX_LID_CLOSED,
                        stage=FailureStage.BEFORE_EXECUTION,
                        source=FailureSource.SEGMENTATION,
                        action=str(action),
                        evidence={
                            'object_name': object_name,
                            'target_region': target_region,
                            'lid_name': lid_name,
                            'visible_objects': snapshot.visible_objects,
                        },
                        failure_layer=FailureLayer.LAYER_2,
                        message=f'Cannot place {object_name} into inside_box because box_lid is closed; open(box_lid) first',
                    )
            if target_region == 'inside_grill':
                lid_name = 'grill_lid'
                lid_evidence = snapshot.object_evidence.get(lid_name)
                if lid_evidence is not None and lid_evidence.visible and not self._is_lid_open(snapshot, lid_name):
                    return FailureEvent(
                        failure_id=FailureCode.GRILL_LID_CLOSED,
                        stage=FailureStage.BEFORE_EXECUTION,
                        source=FailureSource.SEGMENTATION,
                        action=str(action),
                        evidence={
                            'object_name': object_name,
                            'target_region': target_region,
                            'lid_name': lid_name,
                            'visible_objects': snapshot.visible_objects,
                        },
                        failure_layer=FailureLayer.LAYER_2,
                        message=f'Cannot place {object_name} into inside_grill because grill_lid is closed; open(grill_lid) first',
                    )
            return None

        if held_object is not None:
            return FailureEvent(
                failure_id=FailureCode.INVALID_EXECUTOR_STATE,
                stage=FailureStage.BEFORE_EXECUTION,
                source=FailureSource.EXECUTOR,
                action=str(action),
                evidence={'held_object': held_object, 'expected_empty_gripper': True},
                failure_layer=FailureLayer.LAYER_1,
                should_replan=False,
                message=f'Cannot {action.action_name} the lid while holding {held_object}',
            )

        lid_name = action.args[0] if action.args else 'box_lid'
        lid_evidence = snapshot.object_evidence.get(lid_name)
        if lid_evidence is None or not lid_evidence.visible:
            return FailureEvent(
                failure_id=FailureCode.LID_MISSING,
                stage=FailureStage.BEFORE_EXECUTION,
                source=FailureSource.SEGMENTATION,
                action=str(action),
                evidence={'object_name': lid_name, 'visible_objects': snapshot.visible_objects},
                failure_layer=FailureLayer.LAYER_1,
                message=f'Cannot {action.action_name} the lid because {lid_name} is not visible in the segmentation snapshot',
            )
        if action.action_name == 'open' and lid_name == 'box_lid':
            blockers = [
                obj_name
                for obj_name, region_name in (getattr(snapshot, 'object_region_map', {}) or {}).items()
                if obj_name != 'box_lid' and normalize_region_name(region_name) == 'box_lid_top'
            ]
            if blockers:
                blockers = sorted(blockers)
                return FailureEvent(
                    failure_id=FailureCode.BOX_LID_OBSTRUCTED,
                    stage=FailureStage.BEFORE_EXECUTION,
                    source=FailureSource.SEGMENTATION,
                    action=str(action),
                    evidence={
                        'lid_name': lid_name,
                        'blocking_objects': blockers,
                        'object_region_map': dict(getattr(snapshot, 'object_region_map', {}) or {}),
                    },
                    failure_layer=FailureLayer.LAYER_2,
                    message=(
                        f'Cannot open box_lid because {", ".join(blockers)} is on box_lid_top; '
                        f'move {", ".join(blockers)} to table_staging_area first'
                    ),
                )
        return None

    def postcheck(
        self,
        action: DirectAction,
        held_object: Optional[str],
        snapshot: SegmentationSnapshot,
    ) -> Optional[FailureEvent]:
        if action.action_name == 'pick':
            object_name = action.args[0]
            evidence = snapshot.object_evidence.get(object_name)
            if self.grasp_confirmation == 'gripper_state':
                held = held_objects_from_gripper(self.env)
                if held is not None:
                    if object_name in held:
                        return self._maybe_new_visibility_failure(action, snapshot)
                    return FailureEvent(
                        failure_id=FailureCode.GRASP_FAILED,
                        stage=FailureStage.AFTER_EXECUTION,
                        source=FailureSource.EXECUTOR,
                        action=str(action),
                        evidence={'held_objects': sorted(held), 'grasp_confirmation': 'gripper_state'},
                        failure_layer=FailureLayer.LAYER_2,
                        message=f'{object_name} is not held by the gripper after pick execution',
                    )
            if self._picked_object_confirmed(evidence):
                return self._maybe_new_visibility_failure(action, snapshot)
            if evidence is None or not evidence.visible:
                return self._maybe_new_visibility_failure(action, snapshot)
            return FailureEvent(
                failure_id=FailureCode.GRASP_FAILED,
                stage=FailureStage.AFTER_EXECUTION,
                source=FailureSource.SEGMENTATION,
                action=str(action),
                evidence=evidence.to_dict(),
                failure_layer=FailureLayer.LAYER_2,
                message=f'{object_name} is not confirmed near the gripper after pick execution',
            )

        if action.action_name == 'place':
            object_name, target_region = action.args
            target_region = normalize_region_name(target_region)
            object_region_map = getattr(snapshot, 'object_region_map', {}) or {}
            observed_region = normalize_region_name(object_region_map.get(object_name))
            if observed_region and regions_match_for_target(observed_region, target_region):
                return self._maybe_new_visibility_failure(action, snapshot)

            evidence = snapshot.object_evidence.get(object_name)
            if evidence is None or not evidence.visible:
                return FailureEvent(
                    failure_id=FailureCode.OBJECT_DROPPED,
                    stage=FailureStage.AFTER_EXECUTION,
                    source=FailureSource.SEGMENTATION,
                    action=str(action),
                    evidence={'object_name': object_name, 'target_region': target_region},
                    failure_layer=FailureLayer.LAYER_2,
                    message=f'{object_name} is no longer visible after place execution',
                )

            return FailureEvent(
                failure_id=FailureCode.PLACEMENT_FAILED,
                stage=FailureStage.AFTER_EXECUTION,
                source=FailureSource.GEOMETRY,
                action=str(action),
                evidence={
                    **evidence.to_dict(),
                    'target_region': target_region,
                    'geometric_region': observed_region or None,
                    'object_region_map': dict(object_region_map),
                },
                failure_layer=FailureLayer.LAYER_2,
                message=f'{object_name} is geometrically resolved in {observed_region or "(unresolved)"}, not target region {target_region}',
            )

        lid_name = action.args[0] if action.args else 'box_lid'
        lid_open = self._is_lid_open(snapshot, lid_name)
        if action.action_name == 'open' and not lid_open:
            lid_evidence = snapshot.object_evidence.get(lid_name)
            return FailureEvent(
                failure_id=FailureCode.LID_NOT_OPEN_ENOUGH,
                stage=FailureStage.AFTER_EXECUTION,
                source=FailureSource.SEGMENTATION,
                action=str(action),
                evidence=lid_evidence.to_dict() if lid_evidence is not None else {},
                failure_layer=FailureLayer.LAYER_2,
                message=f'{lid_name} is still observed closed after the open action completed',
            )
        if action.action_name == 'close' and lid_open:
            lid_evidence = snapshot.object_evidence.get(lid_name)
            return FailureEvent(
                failure_id=FailureCode.LID_NOT_CLOSED_ENOUGH,
                stage=FailureStage.AFTER_EXECUTION,
                source=FailureSource.SEGMENTATION,
                action=str(action),
                evidence=lid_evidence.to_dict() if lid_evidence is not None else {},
                failure_layer=FailureLayer.LAYER_2,
                message='The lid is still observed open after the close action completed',
            )
        return self._maybe_new_visibility_failure(action, snapshot)

    def classify_runtime_error(self, action: DirectAction, message: str) -> FailureEvent:
        lowered = (message or '').lower()
        stage = FailureStage.BEFORE_EXECUTION
        layer = FailureLayer.LAYER_1
        if 'not found after placement' in lowered:
            failure_id = FailureCode.OBJECT_MISSING_AFTER_PLACE
            source = FailureSource.VALIDATION
            stage = FailureStage.AFTER_EXECUTION
            layer = FailureLayer.LAYER_2
        elif "didn't move" in lowered or 'did not move' in lowered:
            failure_id = FailureCode.OBJECT_DID_NOT_MOVE
            source = FailureSource.VALIDATION
            stage = FailureStage.AFTER_EXECUTION
            layer = FailureLayer.LAYER_2
        elif 'fell' in lowered:
            failure_id = FailureCode.OBJECT_DROPPED
            source = FailureSource.VALIDATION
            stage = FailureStage.AFTER_EXECUTION
            layer = FailureLayer.LAYER_2
        elif 'not in target region' in lowered or 'validation failed' in lowered:
            failure_id = FailureCode.PLACEMENT_FAILED
            source = FailureSource.VALIDATION
            stage = FailureStage.AFTER_EXECUTION
            layer = FailureLayer.LAYER_2
        elif 'not closed enough' in lowered or "lid didn't slide closed enough" in lowered:
            failure_id = FailureCode.LID_NOT_CLOSED_ENOUGH
            source = FailureSource.VALIDATION
            stage = FailureStage.AFTER_EXECUTION
            layer = FailureLayer.LAYER_2
        elif "lid didn't slide open enough" in lowered or 'not open enough' in lowered:
            failure_id = FailureCode.LID_NOT_OPEN_ENOUGH
            source = FailureSource.VALIDATION
            stage = FailureStage.AFTER_EXECUTION
            layer = FailureLayer.LAYER_2
        elif 'empty trajectory' in lowered and action.action_name == 'pick':
            failure_id = FailureCode.EMPTY_PICK_TRAJECTORY
            source = FailureSource.GEOMETRY
        elif 'empty trajectory' in lowered and action.action_name == 'place':
            failure_id = FailureCode.EMPTY_PLACE_TRAJECTORY
            source = FailureSource.GEOMETRY
        elif 'motion to hover' in lowered:
            failure_id = FailureCode.LID_HOVER_PLANNING_FAIL
            source = FailureSource.GEOMETRY
        elif 'slide trajectory' in lowered:
            failure_id = FailureCode.LID_SLIDE_PLANNING_FAIL
            source = FailureSource.GEOMETRY
        elif 'no pddl plan' in lowered or 'no solution' in lowered:
            failure_id = FailureCode.PDDL_NO_PLAN
            source = FailureSource.PDDL
        elif 'ik' in lowered or 'configuration' in lowered:
            failure_id = FailureCode.NO_IK_SOLUTION
            source = FailureSource.GEOMETRY
        elif 'motion' in lowered or 'path' in lowered or 'trajectory' in lowered:
            failure_id = FailureCode.NO_MOTION_PLAN
            source = FailureSource.GEOMETRY
        elif 'grasp' in lowered:
            failure_id = FailureCode.NO_GRASP_FOUND
            source = FailureSource.GEOMETRY
        else:
            failure_id = FailureCode.EXECUTOR_FAILURE
            source = FailureSource.EXECUTOR
        return FailureEvent(
            failure_id=failure_id,
            stage=stage,
            source=source,
            action=str(action),
            evidence={'runtime_message': message},
            failure_layer=layer,
            message=message,
        )

    def render_failure_context(
        self,
        failure_event: FailureEvent,
        completed_actions: Optional[Iterable[str]] = None,
        remaining_actions: Optional[Iterable[str]] = None,
    ) -> str:
        layer_value = (
            failure_event.failure_layer.value
            if isinstance(failure_event.failure_layer, FailureLayer)
            else str(failure_event.failure_layer)
        )
        lines = [
            f'failure_id={failure_event.failure_id}',
            f'failure_layer={layer_value}',
            f'stage={failure_event.stage.value}',
            f'action={failure_event.action or "(none)"}',
            f'message={failure_event.message}',
        ]
        # Include truncated raw_output if it's a parsing failure (useful for LLM)
        if failure_event.evidence and 'raw_output' in failure_event.evidence:
            raw = (failure_event.evidence['raw_output'] or '').strip()
            if raw:
                lines.append(f'your_previous_output=\n{raw}')
        if completed_actions is not None:
            joined = ', '.join(
                str(a) for a in completed_actions
            ) or '(none)'
            lines.append(f'completed_actions={joined}')
        if remaining_actions is not None:
            joined = ', '.join(
                str(a) for a in remaining_actions
            ) or '(none)'
            lines.append(f'remaining_actions={joined}')
        return '\n'.join(lines)

    def _maybe_new_visibility_failure(
        self,
        action: DirectAction,
        snapshot: SegmentationSnapshot,
    ) -> Optional[FailureEvent]:
        if not self.replan_on_new_visibility:
            return None

        action_object = action.args[0] if action.args else None
        discovered = [
            name
            for name in snapshot.newly_visible_objects
            if name not in self.discovery_ignore_objects and name != action_object
        ]
        if not discovered:
            return None

        return FailureEvent(
            failure_id=FailureCode.NEW_OBJECT_DISCOVERED,
            stage=FailureStage.AFTER_EXECUTION,
            source=FailureSource.SEGMENTATION,
            action=str(action),
            evidence={
                'newly_visible_objects': discovered,
                'all_newly_visible_objects': list(snapshot.newly_visible_objects),
            },
            failure_layer=FailureLayer.LAYER_2,
            message=f'Newly visible objects require replanning: {", ".join(discovered)}',
        )

    def _picked_object_confirmed(self, evidence) -> bool:
        """Heuristic to check if the object is confirmed in the gripper by mask proximity."""
        if evidence is None or evidence.gripper_proximity is None:
            return False
        return evidence.gripper_proximity <= self.gripper_threshold

    def _is_lid_open(self, snapshot: SegmentationSnapshot, lid_name: str) -> bool:
        try:
            return bool(self.adapter.is_lid_open(snapshot, lid_name=lid_name))
        except TypeError:
            return bool(self.adapter.is_lid_open(snapshot))

from llm_pipeline.geometric_utils import GeometricReasoner

class GeometricFailureChecker(SegmentationFirstFailureChecker):
    """Refined failure checker using 3D geometric reasoning for higher accuracy."""

    def __init__(self, adapter: SegmentationEvidenceAdapter, env=None, gripper_threshold: float = 0.4):
        super().__init__(adapter, env, gripper_threshold)
        self.reasoner = GeometricReasoner()

    def precheck(
        self,
        action: DirectAction,
        held_object: Optional[str],
        snapshot: SegmentationSnapshot,
        last_action_name: Optional[str] = None,
    ) -> Optional[FailureEvent]:
        # Perform base checks first
        base_failure = super().precheck(action, held_object, snapshot, last_action_name)
        if base_failure:
            return base_failure

        # Geometric Pick/Place Validation
        detector = getattr(self.adapter, 'detector', None)
        if not detector: return None

        if action.action_name == 'pick':
            obj_name = action.args[0]
            obj_pose = detector.get_object_pose(scene_object_for_object(obj_name, self.env))
            if not obj_pose:
                return FailureEvent(
                    failure_id=FailureCode.GEOMETRIC_DISCOVERY_FAIL,
                    stage=FailureStage.BEFORE_EXECUTION,
                    source=FailureSource.GEOMETRY,
                    action=str(action),
                    evidence={'object_name': obj_name},
                    failure_layer=FailureLayer.LAYER_1,
                    message=f'Cannot pick {obj_name}: 3D pose could not be resolved from current view.'
                )

        if action.action_name == 'place':
            obj_name, region_name = action.args
            region_name = normalize_region_name(region_name)
            scene_name = scene_object_for_region(region_name)
            region_pose = detector.get_object_pose(scene_name)
            if not region_pose:
                 return FailureEvent(
                    failure_id=FailureCode.GEOMETRIC_DISCOVERY_FAIL,
                    stage=FailureStage.BEFORE_EXECUTION,
                    source=FailureSource.GEOMETRY,
                    action=str(action),
                    evidence={'region_name': region_name, 'scene_name': scene_name},
                    failure_layer=FailureLayer.LAYER_1,
                    message=f'Cannot place in {region_name}: Target region pose could not be resolved.'
                )

        return None

    def postcheck(
        self,
        action: DirectAction,
        held_object: Optional[str],
        snapshot: SegmentationSnapshot,
    ) -> Optional[FailureEvent]:
        # Pick Success Verification (3D Proximity)
        if action.action_name == 'pick':
            obj_name = action.args[0]
            detector = getattr(self.adapter, 'detector', None)
            if detector:
                obj_pose = detector.get_object_pose(scene_object_for_object(obj_name, self.env))
                # If object is too far from gripper, it's a grasp failure
                if obj_pose:
                    # Logic here would involve robot flange pos, simplified for now
                    pass

        # Place Success Verification (3D Containment/Accuracy)
        if action.action_name == 'place':
            obj_name, region_name = action.args
            region_name = normalize_region_name(region_name)
            object_region_map = getattr(snapshot, 'object_region_map', {}) or {}
            observed_region = normalize_region_name(object_region_map.get(obj_name))
            if observed_region and regions_match_for_target(observed_region, region_name):
                return super().postcheck(action, held_object, snapshot)

            detector = getattr(self.adapter, 'detector', None)
            if detector:
                obj_pose = detector.get_object_pose(scene_object_for_object(obj_name, self.env))
                scene_name = scene_object_for_region(region_name)
                region_pose = detector.get_object_pose(scene_name)
                
                if obj_pose and region_pose:
                    is_contained = self.reasoner.is_contained_3d(
                        obj_pose, region_name, region_pose,
                        detector=detector, scene_name=scene_name,
                    )
                    if not is_contained:
                        return FailureEvent(
                            failure_id=FailureCode.GEOMETRIC_PLACEMENT_FAILED,
                            stage=FailureStage.AFTER_EXECUTION,
                            source=FailureSource.GEOMETRY,
                            action=str(action),
                            evidence={'is_contained': False, 'obj_pose': obj_pose, 'region': region_name},
                            failure_layer=FailureLayer.LAYER_2,
                            message=f'Geometric Verification: {obj_name} is NOT contained within {region_name} after placement.'
                        )

        return super().postcheck(action, held_object, snapshot)
