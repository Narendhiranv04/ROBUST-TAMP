"""Strict direct-action parser with no grounding or extraction layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from llm_pipeline.executable_symbols import ACTION_SYMBOLS, EXECUTABLE_OBJECTS, EXECUTABLE_REGIONS
from llm_pipeline.pipeline_types import DirectAction
from llm_pipeline.region_aliases import normalize_region_name


ACTION_CALL = re.compile(r'^(pick|place|open|close|move)\(([A-Za-z0-9_-]+)(?:,\s*([A-Za-z0-9_-]+))?\)$')


@dataclass
class StrictParseError(ValueError):
    message: str
    line_number: Optional[int] = None
    failure_id: str = 'unknown_action_token'

    def __str__(self) -> str:
        if self.line_number is None:
            return self.message
        return f'Line {self.line_number}: {self.message}'


class StrictActionParser:
    """Parses exact executable lines without repairing or grounding output."""

    def __init__(
        self,
        valid_actions: Optional[Iterable[str]] = None,
        valid_objects: Optional[Iterable[str]] = None,
        valid_regions: Optional[Iterable[str]] = None,
    ):
        self.valid_actions = set(valid_actions or ACTION_SYMBOLS)
        self.valid_objects = set(valid_objects or EXECUTABLE_OBJECTS)
        self.valid_regions = set(valid_regions or EXECUTABLE_REGIONS)

    def parse(self, text: str, held_object: Optional[str] = None) -> List[DirectAction]:
        if text is None:
            raise StrictParseError('Planner output is empty')

        # Strip thought blocks. Some models (DeepSeek-R1) omit the opening <think> tag
        # but include the closing </think> tag. Strip everything up to the closing tag.
        text = re.sub(r'^.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Also catch any lingering <think> blocks if there are multiple or if the regex missed
        text = re.sub(r'<think>.*?(</think>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise StrictParseError('Planner output is empty')

        actions: List[DirectAction] = []
        holding: Optional[str] = held_object

        for index, line in enumerate(lines, start=1):
            # Strip leading numbering/bullets (e.g. "1. move", "2. pick(spam)", "- move")
            # Mistral consistently outputs these despite instructions; be resilient.
            stripped = re.sub(r'^[-*]\s+|^\d+[.)]\s*', '', line).strip()
            if stripped != line:
                line = stripped
            if not line:
                continue

            if line == 'move':
                if 'move' not in self.valid_actions:
                    raise StrictParseError("Unsupported action 'move'", line_number=index)
                actions.append(DirectAction('move', ()))
                continue

            # Skip pure prose lines (e.g. conversational output after </think>)
            if not any(line.startswith(verb) for verb in self.valid_actions):
                continue

            match = ACTION_CALL.fullmatch(line)
            if not match:
                raise StrictParseError(
                    f'Invalid syntax. Expected one of: {", ".join(self.valid_actions)}',
                    line_number=index,
                )

            action_name = match.group(1)
            arg0 = match.group(2)
            arg1 = match.group(3)
            if action_name not in self.valid_actions:
                raise StrictParseError(f"Unsupported action '{action_name}'", line_number=index)

            if action_name == 'move':
                if arg1 is not None:
                    raise StrictParseError('move accepts exactly one target argument', line_number=index)
                if arg0 not in self.valid_objects and arg0 not in self.valid_regions:
                    raise StrictParseError(
                        f"move({arg0}): '{arg0}' is not a known object or region.",
                        line_number=index,
                        failure_id='unknown_action_token'
                    )
                actions.append(DirectAction('move', (arg0,)))
                continue

            if action_name == 'pick':
                if arg1 is not None:
                    raise StrictParseError('pick accepts exactly one object argument', line_number=index)
                if arg0 not in self.valid_objects or arg0 == 'box_lid':
                    raise StrictParseError(
                        f"Unknown or unpickable object '{arg0}'",
                        line_number=index,
                        failure_id='unknown_action_token',
                    )
                if holding is not None:
                    raise StrictParseError(
                        f"Cannot pick '{arg0}' while already holding '{holding}'",
                        line_number=index,
                        failure_id='pick_place_mismatch',
                    )
                holding = arg0
                actions.append(DirectAction('pick', (arg0,)))
                continue

            if action_name == 'place':
                if arg1 is None:
                    raise StrictParseError('place requires object and region arguments', line_number=index)
                target_region = normalize_region_name(arg1)
                if arg0 not in self.valid_objects or arg0 == 'box_lid':
                    raise StrictParseError(
                        f"Unknown or unplaceable object '{arg0}'",
                        line_number=index,
                        failure_id='unknown_action_token',
                    )
                if target_region not in self.valid_regions:
                    raise StrictParseError(
                        f"Unknown target region '{arg1}'",
                        line_number=index,
                        failure_id='unknown_action_token',
                    )
                if holding is None:
                    raise StrictParseError(
                        f"Cannot place '{arg0}' without first picking it",
                        line_number=index,
                        failure_id='orphan_place',
                    )
                if holding != arg0:
                    raise StrictParseError(
                        f"Cannot place '{arg0}' while holding '{holding}'. "
                        f"Did you mean place({holding}, {target_region})? "
                        f"You must place the object you are currently holding.",
                        line_number=index,
                        failure_id='pick_place_mismatch',
                    )
                holding = None
                actions.append(DirectAction('place', (arg0, target_region)))
                continue

            if action_name in ('open', 'close'):
                if arg1 is not None:
                    raise StrictParseError(
                        f'{action_name} accepts exactly {action_name}(lid_object)',
                        line_number=index,
                        failure_id='unknown_action_token',
                    )
                if arg0 not in self.valid_objects or arg0 not in {'box_lid', 'grill_lid', 'lid'}:
                    raise StrictParseError(
                        f"Unknown or unsupported lid object '{arg0}'",
                        line_number=index,
                        failure_id='unknown_action_token',
                    )
                if holding is not None:
                    raise StrictParseError(
                        f"Cannot {action_name}({arg0}) while holding '{holding}'",
                        line_number=index,
                        failure_id='missing_post_pick_place',
                    )
                actions.append(DirectAction(action_name, (arg0,)))
                continue

        if holding is not None:
            raise StrictParseError(
                f"Plan ended while still holding '{holding}'; missing place({holding}, region)",
                failure_id='missing_post_pick_place',
            )

        # Validate: every pick/place/open/close must be preceded by a move
        for i, action in enumerate(actions):
            if action.action_name in ('pick', 'place', 'open', 'close'):
                if i == 0 or actions[i - 1].action_name != 'move':
                    prev = str(actions[i - 1]) if i > 0 else '(start of plan)'
                    raise StrictParseError(
                        f"'{action}' must be preceded by a move action, "
                        f"but the previous action was '{prev}'. "
                        f"Insert move before every pick, place, open, and close.",
                        failure_id='missing_preceding_move',
                    )

        # Validate: no two consecutive move actions
        for i, action in enumerate(actions):
            if action.action_name == 'move' and i + 1 < len(actions):
                if actions[i + 1].action_name == 'move':
                    raise StrictParseError(
                        f"Consecutive move actions at positions {i + 1} and {i + 2}. "
                        f"Every move must be followed by a pick, place, open, or close action.",
                        failure_id='consecutive_moves',
                    )

        # Validate: every move must lead into a concrete executable action.
        for i, action in enumerate(actions):
            if action.action_name == 'move' and i + 1 >= len(actions):
                raise StrictParseError(
                    f"Move action at position {i + 1} has no following pick, place, open, or close action. "
                    f"Every move must be followed by the action it positions for.",
                    failure_id='dangling_move',
                )

        # Validate: move target must match the next action's target.
        for i, action in enumerate(actions):
            if action.action_name == 'move' and action.args:
                target = action.args[0]
                if i + 1 < len(actions):
                    next_action = actions[i + 1]
                    if next_action.action_name in ('pick', 'open', 'close'):
                        expected_target = next_action.args[0] if next_action.args else None
                        if expected_target and target != expected_target:
                            raise StrictParseError(
                                f"move({target}) is followed by {next_action.action_name}({expected_target}), "
                                f"but the move target must match. Expected move({expected_target}).",
                                failure_id='invalid_move_target'
                            )
                    elif next_action.action_name == 'place':
                        expected_target = next_action.args[1] if len(next_action.args) > 1 else None
                        if expected_target and target != expected_target:
                            raise StrictParseError(
                                f"move({target}) is followed by {next_action.action_name}({next_action.args[0]}, {expected_target}), "
                                f"but the move target must match the place region. Expected move({expected_target}).",
                                failure_id='invalid_move_target'
                            )

        # Annotate each move with context from the next action for display
        annotated: List[DirectAction] = []
        for i, action in enumerate(actions):
            if action.action_name == 'move':
                if not action.args:
                    if i + 1 < len(actions):
                        next_name = actions[i + 1].action_name
                        annotated.append(DirectAction('move', (f'→{next_name}',)))
                    else:
                        annotated.append(DirectAction('move', ('→home',)))
                else:
                    annotated.append(action)
            else:
                annotated.append(action)

        return annotated
