"""The 15 final variants of plan.md Phase 3 (specs: docs/VARIANTS.md).

Each variant is a MuJoCo scene composed from an extracted CoppeliaSim scene by
``mujoco_port/tools/compose_variant.py`` (remove / move / copy objects; scene
files ``mujoco_port/scenes/final_<name>/``). Scene objects keep the names the
executor knows (``chicken``, ``steak2``, ``soup3``); the planner, the trial log and
the evaluator use labels (``raw_meat_1``, ``cooked_meat_2``, ``can_of_beans_3``)
through ``labels`` (scene name -> label).

Variant ids are ``FINAL.<name>`` (``--variant final.K1``); the plain names (K1)
are used in tables. Today's K1-K3 / G1-G3 stay for regression tests only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]
SCENES_DIR = ROOT_DIR / 'mujoco_port' / 'scenes'

KITCHEN_GOAL = 'move ALL THE GROCERIES inside the cupboard and ALL THE MUGS inside the box'
GRILL_GOAL = 'COOK all raw meat using the grill and SERVE all cooked meat on the PLATE in the serving area.'

# Placement areas (docs/VARIANTS.md section 3): world x/y rectangle per region.
# The executor places only inside them; an object overlaps when its footprint intersects one.
BOX_PLACEMENT_AREA = (-0.054, 0.187, 0.111, 0.473)       # robot-side half of the box interior
GRILL_PLACEMENT_AREA = (0.287, -0.189, 0.352, -0.112)    # grill slot nearest the robot
GRILL_PLACEMENT_POSE_XY = (0.3195, -0.150)               # where the executor puts meat into the grill
PLACEMENT_AREAS = {
    'kitchen': {'inside_box': BOX_PLACEMENT_AREA},
    'grill': {'inside_grill': GRILL_PLACEMENT_AREA},
}

# Hidden-object positions (world x, y); z comes from the source object's resting height.
BOX_OVERLAP_XY = (0.03, 0.33)
BOX_FREE_XY = (0.20, 0.33)
BOX_FLOOR_Z = 0.752
GRILL_FAR_SLOTS_2 = [(0.328, -0.295), (0.328, -0.237)]
GRILL_MEAT_Z = 1.046                     # resting height of the steak on the grate (grill_variation2)


@dataclass(frozen=True)
class Edit:
    """One scene edit. op: remove | move | copy."""

    op: str
    name: str
    xy: Optional[Tuple[float, float]] = None
    z: Optional[float] = None          # world z of the object origin (default: keep / source z)
    source_scene: str = ''             # copy: extracted scene to copy from
    source_name: str = ''              # copy: object name there
    rigid_mass: Optional[float] = None # copy: make the copy a respondable dynamic body of this mass (kg)


@dataclass(frozen=True)
class HiddenObject:
    label: str
    region: str                        # inside_box | inside_grill
    overlapping: bool                  # footprint intersects the region's placement area


@dataclass(frozen=True)
class FinalVariant:
    name: str
    family: str
    scene: str                         # kitchen | grill
    base: str                          # extracted scene the variant is composed from
    edits: Tuple[Edit, ...]
    labels: Dict[str, str]
    hidden: Tuple[HiddenObject, ...]
    gt_actions: Tuple[str, ...]
    point: str
    expected_if: Dict[str, str] = field(default_factory=dict)       # label -> trigger kind / ignore
    expected_urgency: Dict[str, str] = field(default_factory=dict)  # label -> urgent / deferred

    @property
    def variant_id(self) -> str:
        return f'FINAL.{self.name}'

    @property
    def scene_dir(self) -> Path:
        return SCENES_DIR / f'final_{self.name.replace("-", "_")}'

    @property
    def goal(self) -> str:
        return KITCHEN_GOAL if self.scene == 'kitchen' else GRILL_GOAL

    @property
    def scene_objects(self) -> List[str]:
        """Movable scene objects the pipeline must know (scene names)."""
        return sorted(self.labels)


# ---------------------------------------------------------------- kitchen
_K_BASE = 'task1_variation3'
_K_LABELS = {'mug1': 'mug1', 'mug2': 'mug2', 'mug3': 'mug3', 'spam': 'spam', 'sugar': 'sugar'}
_K_BASE_EDITS = (
    Edit('remove', 'soup'),                    # the box starts empty in the base layout
    Edit('move', 'spam', xy=(0.27, -0.35), z=0.79),  # spam on the table (K1's table spot)
)
# mug3 (the scripted cupboard pick) is staged first, as in the old K3 ground truth.
_K_BEFORE_OPEN = ('pick(mug3)', 'place(mug3, table_staging_area)',
                  'pick(mug2)', 'place(mug2, table_staging_area)', 'open(box_lid)')
_K_GROCERIES = ('pick(spam)', 'place(spam, cupboard_shelf)', 'pick(sugar)', 'place(sugar, cupboard_shelf)')
_K_MUGS = ('pick(mug1)', 'place(mug1, inside_box)', 'pick(mug2)', 'place(mug2, inside_box)',
           'pick(mug3)', 'place(mug3, inside_box)')


def _phone_edit(xy):
    # The grill scene's phone is a static, non-respondable prop; the kitchen copy is a rigid body.
    return Edit('copy', 'phone', xy=xy, z=BOX_FLOOR_Z + 0.013, source_scene='grill_variation1', source_name='phone',
                rigid_mass=0.15)


def _can_edits(positions):
    """The base scene's soup can moved into place, plus copies soup2, soup3."""
    edits = [Edit('move', 'soup', xy=positions[0], z=0.80)]
    for i, xy in enumerate(positions[1:], start=2):
        edits.append(Edit('copy', f'soup{i}', xy=xy, z=0.80, source_scene=_K_BASE, source_name='soup'))
    return edits


def _kitchen(name, family, extra_edits, extra_labels, hidden, after_open, point, expected_if, urgency,
             tail=(), extra_groceries=()):
    base_edits = list(_K_BASE_EDITS)
    if any(e.name == 'soup' and e.op == 'move' for e in extra_edits):
        base_edits = [e for e in base_edits if not (e.op == 'remove' and e.name == 'soup')]
    gt = _K_BEFORE_OPEN + tuple(after_open) + _K_GROCERIES + tuple(extra_groceries) + _K_MUGS + tuple(tail)
    return FinalVariant(name, family, 'kitchen', _K_BASE, tuple(base_edits) + tuple(extra_edits),
                        {**_K_LABELS, **extra_labels}, tuple(hidden), gt, point, expected_if, urgency)


_CAN = 'can_of_beans'
_C1_LABELS = {'soup': _CAN}
_PHONE_TO_TABLE = ('pick(phone)', 'place(phone, table)')


def _cans_to_cupboard(labels):
    return tuple(a for label in labels for a in (f'pick({label})', f'place({label}, cupboard_shelf)'))


KITCHEN_VARIANTS = [
    _kitchen('K0', 'A', [], {}, [], (), 'Kitchen reference: nothing hidden, no replan.', {}, {}),
    _kitchen('K1', 'B', [_phone_edit(BOX_OVERLAP_XY)], {'phone': 'phone'},
             [HiddenObject('phone', 'inside_box', True)], _PHONE_TO_TABLE,
             'Irrelevant object triggers a replan only when overlapping; cleared before any mug goes in.',
             {'phone': 'irrelevant_overlapping'}, {'phone': 'urgent'}),
    _kitchen('K2', 'B', [_phone_edit(BOX_FREE_XY)], {'phone': 'phone'},
             [HiddenObject('phone', 'inside_box', False)], (),
             'Non-overlapping irrelevant object is ignored: no replan, no manipulation.',
             {'phone': 'ignore'}, {}),
    _kitchen('K3', 'B', _can_edits([(0.07, 0.33)]), _C1_LABELS,
             [HiddenObject(_CAN, 'inside_box', True)], _cans_to_cupboard([_CAN]),
             'Overlapping relevant object handled before anything else goes into the box.',
             {_CAN: 'relevant_not_goal_attained'}, {_CAN: 'urgent'}),
    _kitchen('K4', 'B', _can_edits([BOX_FREE_XY]), _C1_LABELS,
             [HiddenObject(_CAN, 'inside_box', False)], (),
             'Non-overlapping relevant object still handled, without urgency.',
             {_CAN: 'relevant_not_goal_attained'}, {_CAN: 'deferred'}, tail=_cans_to_cupboard([_CAN])),
    _kitchen('K3-n2', 'C1', _can_edits([(0.02, 0.26), (0.02, 0.40)]), {'soup': _CAN, 'soup2': f'{_CAN}_2'},
             [HiddenObject(_CAN, 'inside_box', True), HiddenObject(f'{_CAN}_2', 'inside_box', True)],
             _cans_to_cupboard([_CAN, f'{_CAN}_2']), 'C1 sweep, n = 2.',
             {_CAN: 'relevant_not_goal_attained', f'{_CAN}_2': 'relevant_not_goal_attained'},
             {_CAN: 'urgent', f'{_CAN}_2': 'urgent'}),
    _kitchen('K3-n3', 'C1', _can_edits([(0.02, 0.26), (0.02, 0.40), (0.075, 0.33)]),
             {'soup': _CAN, 'soup2': f'{_CAN}_2', 'soup3': f'{_CAN}_3'},
             [HiddenObject(_CAN, 'inside_box', True), HiddenObject(f'{_CAN}_2', 'inside_box', True),
              HiddenObject(f'{_CAN}_3', 'inside_box', True)],
             _cans_to_cupboard([_CAN, f'{_CAN}_2', f'{_CAN}_3']), 'C1 sweep, n = 3.',
             {f: 'relevant_not_goal_attained' for f in (_CAN, f'{_CAN}_2', f'{_CAN}_3')},
             {f: 'urgent' for f in (_CAN, f'{_CAN}_2', f'{_CAN}_3')}),
]

_W_POSITIONS = [(0.17, -0.46), (0.30, -0.46)]    # on the table, in view of the cameras


def _k1_w(w):
    edits = [_phone_edit(BOX_OVERLAP_XY)]
    labels = {'phone': 'phone'}
    groceries = []
    for i in range(w):
        scene_name = f'soup{i + 1}' if i else 'soup'
        label = _CAN if i == 0 else f'{_CAN}_{i + 1}'
        if i == 0:
            edits.append(Edit('move', 'soup', xy=_W_POSITIONS[0], z=0.80))
        else:
            edits.append(Edit('copy', scene_name, xy=_W_POSITIONS[i], z=0.80, source_scene=_K_BASE, source_name='soup'))
        labels[scene_name] = label
        groceries.append(label)
    return _kitchen(f'K1-w{w}', 'C2', edits, labels, [HiddenObject('phone', 'inside_box', True)], _PHONE_TO_TABLE,
                    f'C2 sweep, w = {w} extra groceries on the table.', {'phone': 'irrelevant_overlapping'},
                    {'phone': 'urgent'}, extra_groceries=_cans_to_cupboard(groceries))


KITCHEN_VARIANTS += [_k1_w(1), _k1_w(2)]

# ---------------------------------------------------------------- grill
_G_BASE = 'grill_variation2'
_G_BASE_EDITS = (Edit('remove', 'steak1'), Edit('remove', 'steak'))   # one raw meat (chicken) outside
_G_LABELS = {'chicken': 'raw_meat_1', 'plate': 'plate'}


def _meat(scene_name, xy):
    if scene_name in ('steak', 'steak1'):
        return Edit('move', scene_name, xy=xy, z=GRILL_MEAT_Z)
    return Edit('copy', scene_name, xy=xy, z=GRILL_MEAT_Z, source_scene=_G_BASE, source_name='steak')


def _grill(name, family, inside, point, cooked_first):
    """inside: list of (scene_name, label) placed in the grill's far slots."""
    slots = GRILL_FAR_SLOTS_2
    keep = {scene for scene, _ in inside}
    edits = [e for e in _G_BASE_EDITS if e.name not in keep] + [_meat(scene, slots[i]) for i, (scene, _) in enumerate(inside)]
    labels = {**_G_LABELS, **{scene: label for scene, label in inside}}
    hidden = tuple(HiddenObject(label, 'inside_grill', False) for _, label in inside)
    cooked = [label for _, label in inside if label.startswith('cooked')]
    raw_inside = [label for _, label in inside if label.startswith('raw')]
    gt = ['open(grill_lid)', 'pick(plate)', 'place(plate, serving_area)']
    gt += [a for label in cooked for a in (f'pick({label})', f'place({label}, plate_top)')]
    gt += ['pick(raw_meat_1)', 'place(raw_meat_1, inside_grill)', 'close(grill_lid)', 'open(grill_lid)']
    gt += [a for label in ['raw_meat_1'] + raw_inside for a in (f'pick({label})', f'place({label}, plate_top)')]
    expected_if = {label: 'relevant_not_goal_attained' for _, label in inside}
    urgency = {label: ('urgent' if label.startswith('cooked') else 'deferred') for _, label in inside}
    return FinalVariant(name, family, 'grill', _G_BASE, tuple(edits), labels, hidden, tuple(gt), point,
                        expected_if, urgency)


GRILL_VARIANTS = [
    _grill('G0', 'A', [], 'Grill reference: normal cook-and-serve, no replan.', False),
    _grill('G1', 'B', [('steak1', 'cooked_meat_1'), ('steak', 'cooked_meat_2')],
           'All corrective actions urgent: both cooked meats out before continuing.', True),
    _grill('G2', 'B', [('steak1', 'raw_meat_2'), ('steak', 'cooked_meat_1')],
           'Split urgency: cooked meat out now, raw meat stays to be cooked.', True),
    _grill('G3', 'B', [('steak1', 'raw_meat_2'), ('steak', 'raw_meat_3')],
           'No urgency: raw meat stays, is cooked in the normal cycle and served later.', False),
    _grill('G1-n1', 'C1', [('steak1', 'cooked_meat_1')], 'C1 sweep, n = 1.', True),
]
# G1-n3 was dropped (Q12): three steaks (5.3 cm each) need 15.9 cm of the grill's 15.4 cm outside the
# placement area; a steak placed past the far wall rides up on it and shows under the lid.

FINAL_VARIANTS: Dict[str, FinalVariant] = {v.variant_id.upper(): v for v in KITCHEN_VARIANTS + GRILL_VARIANTS}
FINAL_VARIANT_ORDER = ['K0', 'G0', 'K1', 'K2', 'K3', 'K4', 'G1', 'G2', 'G3',
                       'K3-n2', 'K3-n3', 'G1-n1', 'K1-w1', 'K1-w2']


def final_subtasks(actions) -> List[str]:
    """Subtasks of a final variant: every place (the pick is implied) and every lid motion."""
    out = []
    for action in actions or ():
        text = str(action).replace(' ', '')
        if text.startswith(('place(', 'open(', 'close(')):
            out.append(text)
    return out


def get_final_variant(variant_id: str) -> Optional[FinalVariant]:
    key = str(variant_id or '').strip().upper()
    if not key.startswith('FINAL.'):
        key = f'FINAL.{key}'
    return FINAL_VARIANTS.get(key)


def is_final_variant(variant_id: str) -> bool:
    return str(variant_id or '').strip().upper().startswith('FINAL.')


__all__ = ['final_subtasks', 'FINAL_VARIANTS', 'FINAL_VARIANT_ORDER', 'FinalVariant', 'HiddenObject', 'Edit',
           'PLACEMENT_AREAS', 'GRILL_PLACEMENT_POSE_XY', 'get_final_variant', 'is_final_variant']
