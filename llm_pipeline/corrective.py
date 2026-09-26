"""WHERE: corrective sub-plans, urgency, insertion and merge (plan.md Phase 5).

With ``replan.output_mode = corrective``, a replan after an IF-rule trigger does not
regenerate the remaining plan. The planner model returns one or more **blocks**:

    FINAL BLOCKS:
    BLOCK
    objects: <trigger objects this block handles, comma-separated>
    urgency: urgent | deferred
    insert: front | after <action id from the remaining plan> | end
    reason: <one short sentence>
    actions:
    <one action per line>
    END BLOCK

The system parses and checks the blocks, inserts them into the remaining plan
(``urgent`` at the front in the order returned; ``deferred`` after their anchor or at
the end) and runs the plan check on the merged plan, including a symbolic check of
placement conflicts: a ``place`` into a region while an overlapping trigger object is
still in that region's placement area is ``insertion_too_late``. The system never
enforces food-related urgency; the evaluator scores it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from llm_pipeline.failures import FailureCode
from llm_pipeline.metrics import parse_action_string
from llm_pipeline.region_aliases import normalize_region_name

URGENT, DEFERRED = 'urgent', 'deferred'
FRONT, END = 'front', 'end'
FINAL_BLOCKS_MARKER = 'FINAL BLOCKS:'
LID_NAMES = frozenset({'box_lid', 'grill_lid'})

BLOCK_OUTPUT_FORMAT_TEXT = (
    'Output format for this request:\n'
    'Reasoning is allowed. End your answer with a line containing only FINAL BLOCKS: followed by one or more '
    'blocks. Each block handles some of the objects listed under "Why a new plan is requested" and has exactly '
    'this form:\n'
    'BLOCK\n'
    'objects: <names of the listed objects this block handles, comma-separated>\n'
    'urgency: urgent or deferred\n'
    'insert: front, or after <action id from the remaining plan>, or end\n'
    'reason: <one short sentence>\n'
    'actions:\n'
    '<one action per line, in execution order>\n'
    'END BLOCK\n'
    'Every listed object must be handled by at least one block. An urgent block must use insert: front. '
    'Write nothing after the last END BLOCK.'
)

_WHAT_TO_PLAN = [
    '## What to plan',
    '- Plan actions only for the objects listed under "Why a new plan is requested". The remaining plan stays as '
    'it is: do not repeat, reorder or remove its actions.',
    '- Do not move objects that are already in their goal state, and do not move objects that are not relevant '
    'to the goal unless they are listed.',
]
# prompt.corrective_hints = off (default; every real-model run): neutral wording only.
URGENCY_NEUTRAL = ('- Decide each block\'s urgency and where it goes in the remaining plan by considering what would '
                   'go wrong if its actions were delayed.')
# prompt.corrective_hints = on: the plan.md 5.2 examples, kept for a hinted-vs-neutral comparison.
# They point at the kitchen (blocking) and grill (cooking again) answers.
URGENCY_HINTED = ('- For each block, decide its urgency and where it goes in the remaining plan by reasoning about '
                  'what would go wrong if its actions were delayed until later in the remaining plan (for example, '
                  'an object lying where other objects will be placed, or food that would be cooked again).')


def corrective_instructions(hints: bool = False) -> List[str]:
    return _WHAT_TO_PLAN + [URGENCY_HINTED if hints else URGENCY_NEUTRAL]


CORRECTIVE_INSTRUCTIONS = corrective_instructions(hints=False)


@dataclass
class CorrectiveBlock:
    objects: List[str]
    actions: List[str]
    urgency: str
    insert: str                      # front / end / after:<id>
    reason: str = ''
    proposed_urgency: str = ''       # the planner model's choice (before an insertion-mode override)
    proposed_insert: str = ''

    @property
    def anchor(self) -> Optional[str]:
        return self.insert.split(':', 1)[1] if self.insert.startswith('after:') else None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class CorrectivePlanError(ValueError):
    """A block list or merged plan the plan check rejects (the planner is re-queried)."""

    def __init__(self, failure_id: str, fact: str):
        super().__init__(fact)
        self.failure_id = failure_id
        self.fact = fact


def _field(line: str) -> Tuple[str, str]:
    key, _, value = line.partition(':')
    return key.strip().lower(), value.strip()


def parse_blocks(
    raw_output: str,
    trigger_objects: Sequence[str],
    remaining_ids: Sequence[str],
    validate_action: Callable[[str], None] = lambda action: None,
) -> List[CorrectiveBlock]:
    """Parse and check the text after ``FINAL BLOCKS:``.

    ``validate_action`` raises for an action with an unknown action, object or region.
    """
    text = raw_output or ''
    marker = text.rfind(FINAL_BLOCKS_MARKER)
    if marker < 0:
        raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'the output has no {FINAL_BLOCKS_MARKER} line')
    lines = [line.strip() for line in text[marker + len(FINAL_BLOCKS_MARKER):].splitlines()]
    lines = [line for line in lines if line and not line.startswith('```')]
    blocks, current, in_actions = [], None, False
    for line in lines:
        upper = line.upper()
        if upper == 'BLOCK':
            if current is not None:
                raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, 'a BLOCK starts before the previous END BLOCK')
            current, in_actions = {'actions': []}, False
            continue
        if upper == 'END BLOCK':
            if current is None:
                raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, 'END BLOCK without BLOCK')
            blocks.append(current)
            current, in_actions = None, False
            continue
        if current is None:
            raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'text outside a block: {line!r}')
        key, value = _field(line)
        if key == 'actions' and not value:
            in_actions = True
            continue
        if in_actions and '(' in line:
            current['actions'].append(line)
            continue
        if key in ('objects', 'urgency', 'insert', 'reason') and not in_actions:
            current[key] = value
            continue
        raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'unexpected line in a block: {line!r}')
    if current is not None:
        raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, 'the last block has no END BLOCK')
    if not blocks:
        raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, 'no blocks')

    triggers = list(trigger_objects)
    remaining = set(remaining_ids)
    handled: List[str] = []
    parsed_blocks = []
    for number, data in enumerate(blocks, start=1):
        where = f'block {number}'
        for key in ('objects', 'urgency', 'insert'):
            if not data.get(key):
                raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'{where} has no {key}')
        objects = [name.strip() for name in data['objects'].split(',') if name.strip()]
        unknown = [name for name in objects if name not in triggers]
        if unknown:
            raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK,
                                      f'{where} handles {", ".join(unknown)}, which is not a listed object')
        urgency = data['urgency'].lower()
        if urgency not in (URGENT, DEFERRED):
            raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'{where} has urgency {urgency!r}')
        insert_text = data['insert'].strip()
        match = re.fullmatch(r'after\s+(\S+)', insert_text, flags=re.IGNORECASE)
        if insert_text.lower() in (FRONT, END):
            insert = insert_text.lower()
        elif match:
            anchor = match.group(1)
            if anchor not in remaining:
                raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK,
                                          f'{where} inserts after {anchor}, which is not in the remaining plan')
            insert = f'after:{anchor}'
        else:
            raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'{where} has insert {insert_text!r}')
        if urgency == URGENT and insert != FRONT:
            raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'{where} is urgent but not inserted at the front')
        if not data['actions']:
            raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'{where} has no actions')
        for action in data['actions']:
            validate_action(action)
            parsed = parse_action_string(action)
            if parsed is None:
                raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'{where}: cannot read {action!r}')
            target = (parsed.get('args') or [None])[0]
            if parsed['action'] in ('pick', 'place') and target not in objects:
                raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK,
                                          f'{where}: {action} acts on {target}, which this block does not handle')
        handled.extend(objects)
        parsed_blocks.append(CorrectiveBlock(objects, list(data['actions']), urgency, insert, data.get('reason', ''),
                                             urgency, insert))
    # An object may appear in several blocks (e.g. moved out of the way now, placed in its goal later).
    missing = [name for name in triggers if name not in handled]
    if missing:
        raise CorrectivePlanError(FailureCode.INVALID_CORRECTIVE_BLOCK, f'no block handles {", ".join(missing)}')
    return parsed_blocks


def apply_insertion_mode(blocks: Sequence[CorrectiveBlock], mode: str) -> List[CorrectiveBlock]:
    """``planner``: keep the model's choice; ``always_front`` / ``always_end``: override it."""
    if mode == 'planner':
        return list(blocks)
    urgency, insert = (URGENT, FRONT) if mode == 'always_front' else (DEFERRED, END)
    return [CorrectiveBlock(b.objects, b.actions, urgency, insert, b.reason, b.proposed_urgency, b.proposed_insert)
            for b in blocks]


@dataclass
class MergeResult:
    merged: List[Tuple[str, str]]                   # (action id, action)
    insertions: List[Dict[str, object]] = field(default_factory=list)
    anchors_already_executed: List[str] = field(default_factory=list)


def merge_blocks(
    remaining: Sequence[Tuple[str, str]],
    blocks: Sequence[CorrectiveBlock],
    new_id: Callable[[], str],
) -> MergeResult:
    """Insert blocks into the remaining plan ((id, action) pairs).

    An anchor that is no longer in the remaining plan (executed meanwhile, Phase 6)
    makes the block go to the front.
    """
    merged = list(remaining)
    remaining_ids = {action_id for action_id, _ in remaining}
    result = MergeResult(merged=[])
    front: List[Tuple[str, str]] = []
    for block in blocks:
        entries = [(new_id(), action) for action in block.actions]
        position = block.insert
        if block.anchor is not None and block.anchor not in remaining_ids:
            result.anchors_already_executed.append(block.anchor)
            position = FRONT
        if position == FRONT:
            front.extend(entries)
        elif position == END:
            merged.extend(entries)
        else:
            index = next(i for i, (action_id, _) in enumerate(merged) if action_id == block.anchor)
            merged[index + 1:index + 1] = entries
        result.insertions.append({'objects': list(block.objects), 'urgency': block.urgency, 'insert': position,
                                  'action_ids': [action_id for action_id, _ in entries]})
    result.merged = front + merged
    return result


def placement_conflict(
    merged_actions: Sequence[str],
    overlapping: Mapping[str, Sequence[str]],
) -> Optional[str]:
    """``insertion_too_late``: a place into region R before an object overlapping R's placement area is picked."""
    blocking = {obj: {normalize_region_name(r) for r in regions} for obj, regions in (overlapping or {}).items() if regions}
    if not blocking:
        return None
    cleared = set()
    for raw in merged_actions:
        parsed = parse_action_string(str(raw))
        if parsed is None:
            continue
        args = list(parsed.get('args') or [])
        if parsed['action'] == 'pick' and args and args[0] in blocking:
            cleared.add(args[0])
        elif parsed['action'] == 'place' and len(args) >= 2:
            region = normalize_region_name(args[1])
            for obj, regions in blocking.items():
                if obj not in cleared and obj != args[0] and region in regions:
                    return f'{raw} places into {region} while {obj} is still in its placement area'
    return None


__all__ = [
    'BLOCK_OUTPUT_FORMAT_TEXT', 'CORRECTIVE_INSTRUCTIONS', 'corrective_instructions', 'CorrectiveBlock', 'CorrectivePlanError', 'DEFERRED', 'END',
    'FINAL_BLOCKS_MARKER', 'FRONT', 'MergeResult', 'URGENT', 'apply_insertion_mode', 'merge_blocks', 'parse_blocks',
    'placement_conflict',
]
