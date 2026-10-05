"""Strict direct-action parser with no grounding or extraction layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from llm_pipeline.executable_symbols import ACTION_SYMBOLS, EXECUTABLE_OBJECTS, EXECUTABLE_REGIONS
from llm_pipeline.failures import FailureCode
from llm_pipeline.pipeline_types import DirectAction
from llm_pipeline.region_aliases import normalize_region_name


ACTION_CALL = re.compile(r'^(pick|place|open|close)\(([A-Za-z0-9_-]+)(?:,\s*([A-Za-z0-9_-]+))?\)$')
FINAL_ACTIONS_MARKER = re.compile(r'(?im)^\s*(?:#+\s*)?FINAL\s+ACTIONS?\s*:?\s*$')


@dataclass
class StrictParseError(ValueError):
    message: str
    line_number: Optional[int] = None
    failure_id: str = FailureCode.UNKNOWN_ACTION_TOKEN
    # Plain statement of what was wrong, without advice (used by prompt v2).
    fact: str = ''

    def __str__(self) -> str:
        if self.line_number is None:
            return self.message
        return f'Line {self.line_number}: {self.message}'


def has_content(segment: str) -> bool:
    """Whether a section after a final marker has anything besides blank lines and code fences."""
    return any(line.strip() and not line.strip().startswith('```') for line in (segment or '').splitlines())


def last_answer_section(text: str, spans) -> Optional[tuple]:
    """(start, end, answer) of the answer after the last final marker that has content.

    ``spans`` are the markers' (start, end) positions in order. The answer is the section after a
    marker up to the next marker. A marker the model repeats at the very end with nothing after it
    (seen after in-context examples whose answers end with an extra line) is ignored; when no
    marker has content, the last one is used (an empty answer, as before)."""
    if not spans:
        return None
    bounds = [(spans[k][0], spans[k][1], spans[k + 1][0] if k + 1 < len(spans) else len(text)) for k in range(len(spans))]
    for start, end, stop in reversed(bounds):
        if has_content(text[end:stop]):
            return start, end, text[end:stop]
    start, end, stop = bounds[-1]
    return start, end, text[end:stop]


def split_reasoning(text: Optional[str]) -> tuple:
    """Split planner output into (reasoning, answer) at the last FINAL ACTIONS: line with an answer."""
    text = text or ''
    found = last_answer_section(text, [(m.start(), m.end()) for m in FINAL_ACTIONS_MARKER.finditer(text)])
    if found is None:
        return text.strip(), ''
    start, _, answer = found
    return text[:start].strip(), answer.strip()


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
        # Objects the robot has observed so far . When
        # set, actions on any other object are rejected as unobserved_object.
        self.observed_objects: Optional[set] = None
        # prompt.version=v2: only the text after the last FINAL ACTIONS: line is parsed;
        # everything before it is reasoning (logged, never parsed).
        self.require_final_marker = False
        # memory.enabled: remembered-but-not-visible objects -> last region, the regions
        # closed off by currently closed lids, and lid -> regions it closes off.
        self.remembered_regions: Optional[dict] = None
        self.closed_regions: set = set()
        self.lid_regions: dict = {}

    def set_access_context(self, remembered_regions=None, closed_regions=(), lid_regions=None) -> None:
        self.remembered_regions = None if remembered_regions is None else dict(remembered_regions)
        self.closed_regions = set(closed_regions or ())
        self.lid_regions = dict(lid_regions or {})

    def set_observed_objects(self, observed_objects: Optional[Iterable[str]]) -> None:
        self.observed_objects = None if observed_objects is None else set(observed_objects)

    def planner_visible_objects(self) -> List[str]:
        """Object names the planner may be told about."""
        if self.observed_objects is None:
            return sorted(self.valid_objects)
        return sorted(self.valid_objects & self.observed_objects)

    def _check_observed(self, name: str, index: int, line: str, message: str, fact: str) -> None:
        """Reject an unobserved object with exactly the message and fact of an unknown name.

        The planner must not be able to tell a hidden object from a name that does not
        exist, so only the failure code (logged, not shown to the planner) differs.
        """
        if self.observed_objects is not None and name in self.valid_objects and name not in self.observed_objects:
            raise StrictParseError(message, line_number=index, failure_id=FailureCode.UNOBSERVED_OBJECT, fact=fact)

    def parse(self, text: str, held_object: Optional[str] = None) -> List[DirectAction]:
        if text is None:
            raise StrictParseError('Planner output is empty', fact='The output was empty.')

        # Strip thought blocks. Some models (DeepSeek-R1) omit the opening <think> tag
        # but include the closing </think> tag. Strip everything up to the closing tag.
        text = re.sub(r'^.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Also catch any lingering <think> blocks if there are multiple or if the regex missed
        text = re.sub(r'<think>.*?(</think>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)
        final_markers = [(m.start(), m.end()) for m in FINAL_ACTIONS_MARKER.finditer(text)]
        if final_markers:
            # the actions after the last marker that has any (a repeated empty marker at the end is ignored)
            text = last_answer_section(text, final_markers)[2]
        elif self.require_final_marker:
            raise StrictParseError(
                'Planner output has no FINAL ACTIONS: line',
                failure_id=FailureCode.PLANNER_OUTPUT_NOT_PARSEABLE,
                fact='The output has no line containing only FINAL ACTIONS:.',
            )

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise StrictParseError('Planner output is empty', fact='The output contained no action lines.')

        # Explicit terminal token when the current state already satisfies the goal.
        terminal_lines = {
            re.sub(r'^[-*]\s+|^\d+[.)]\s*', '', line).strip().upper()
            for line in lines
        }
        if 'NO_ACTIONS' in terminal_lines:
            if len(terminal_lines) > 1:
                raise StrictParseError(
                    "NO_ACTIONS cannot be mixed with executable actions.",
                    failure_id=FailureCode.UNKNOWN_ACTION_TOKEN,
                    fact='The output contained NO_ACTIONS together with other lines.',
                )
            return []

        actions: List[DirectAction] = []
        holding: Optional[str] = held_object
        closed_regions = set(self.closed_regions)

        for index, line in enumerate(lines, start=1):
            # Strip leading numbering/bullets (e.g. "1. pick(spam)", "2. place(spam, table)", "- open(lid)")
            # Mistral consistently outputs these despite instructions; be resilient.
            stripped = re.sub(r'^[-*]\s+|^\d+[.)]\s*', '', line).strip()
            if stripped != line:
                line = stripped
            if not line:
                continue

            # Skip pure prose lines (e.g. conversational output after </think>)
            if not any(line.startswith(verb) for verb in self.valid_actions):
                continue

            match = ACTION_CALL.fullmatch(line)
            if not match:
                raise StrictParseError(
                    f'Invalid syntax. Expected one of: {", ".join(self.valid_actions)}',
                    line_number=index,
                    fact=f'Line {index} ({line}) is not a valid action line.',
                )

            action_name = match.group(1)
            arg0 = match.group(2)
            arg1 = match.group(3)
            if action_name not in self.valid_actions:
                raise StrictParseError(f"Unsupported action '{action_name}'", line_number=index,
                                       fact=f"Line {index} ({line}) uses action '{action_name}', which is not available in this scene.")



            if action_name == 'pick':
                if arg1 is not None:
                    raise StrictParseError('pick accepts exactly one object argument', line_number=index,
                                           fact=f'Line {index} ({line}) gives pick more than one argument.')
                pick_message = f"Unknown or unpickable object '{arg0}'"
                pick_fact = f"Line {index} ({line}) picks '{arg0}', which is not a pickable object in the state."
                self._check_observed(arg0, index, line, pick_message, pick_fact)
                if arg0 not in self.valid_objects or arg0 == 'box_lid':
                    raise StrictParseError(
                        pick_message,
                        line_number=index,
                        failure_id=FailureCode.UNKNOWN_ACTION_TOKEN,
                        fact=pick_fact,
                    )
                if holding is not None:
                    raise StrictParseError(
                        f"Cannot pick '{arg0}' while already holding '{holding}'",
                        line_number=index,
                        failure_id=FailureCode.PICK_PLACE_MISMATCH,
                        fact=f"Line {index} ({line}) picks '{arg0}' while the gripper holds '{holding}'.",
                    )
                remembered_region = (self.remembered_regions or {}).get(arg0)
                if remembered_region is not None and remembered_region in closed_regions:
                    raise StrictParseError(
                        f"'{arg0}' was last seen in {remembered_region}, which is closed off by a closed lid here",
                        line_number=index,
                        failure_id=FailureCode.REMEMBERED_OBJECT_INACCESSIBLE,
                        fact=(f"Line {index} ({line}) picks '{arg0}', last seen in {remembered_region}; "
                              f"at that point of the plan {remembered_region} is closed off by a closed lid."),
                    )
                holding = arg0
                actions.append(DirectAction('pick', (arg0,)))
                continue

            if action_name == 'place':
                if arg1 is None:
                    raise StrictParseError('place requires object and region arguments', line_number=index,
                                           fact=f'Line {index} ({line}) gives place only one argument.')
                target_region = normalize_region_name(arg1)
                place_message = f"Unknown or unplaceable object '{arg0}'"
                place_fact = f"Line {index} ({line}) places '{arg0}', which is not a placeable object in the state."
                self._check_observed(arg0, index, line, place_message, place_fact)
                if arg0 not in self.valid_objects or arg0 == 'box_lid':
                    raise StrictParseError(
                        place_message,
                        line_number=index,
                        failure_id=FailureCode.UNKNOWN_ACTION_TOKEN,
                        fact=place_fact,
                    )
                if target_region not in self.valid_regions:
                    raise StrictParseError(
                        f"Unknown target region '{arg1}'",
                        line_number=index,
                        failure_id=FailureCode.UNKNOWN_ACTION_TOKEN,
                        fact=f"Line {index} ({line}) uses region '{arg1}', which is not a listed region.",
                    )
                if holding is None:
                    raise StrictParseError(
                        f"Cannot place '{arg0}' without first picking it",
                        line_number=index,
                        failure_id=FailureCode.ORPHAN_PLACE,
                        fact=f"Line {index} ({line}) places '{arg0}' while the gripper is empty.",
                    )
                if holding != arg0:
                    raise StrictParseError(
                        f"Cannot place '{arg0}' while holding '{holding}'. "
                        f"Did you mean place({holding}, {target_region})? "
                        f"You must place the object you are currently holding.",
                        line_number=index,
                        failure_id=FailureCode.PICK_PLACE_MISMATCH,
                        fact=f"Line {index} ({line}) places '{arg0}' while the gripper holds '{holding}'.",
                    )
                holding = None
                actions.append(DirectAction('place', (arg0, target_region)))
                continue

            if action_name in ('open', 'close'):
                if arg1 is not None:
                    raise StrictParseError(
                        f'{action_name} accepts exactly {action_name}(lid_object)',
                        line_number=index,
                        failure_id=FailureCode.UNKNOWN_ACTION_TOKEN,
                        fact=f'Line {index} ({line}) gives {action_name} more than one argument.',
                    )
                lid_message = f"Unknown or unsupported lid object '{arg0}'"
                lid_fact = f"Line {index} ({line}) uses '{arg0}', which is not a lid in the state."
                self._check_observed(arg0, index, line, lid_message, lid_fact)
                if arg0 not in self.valid_objects or arg0 not in {'box_lid', 'grill_lid', 'lid'}:
                    raise StrictParseError(
                        lid_message,
                        line_number=index,
                        failure_id=FailureCode.UNKNOWN_ACTION_TOKEN,
                        fact=lid_fact,
                    )
                if holding is not None:
                    raise StrictParseError(
                        f"Cannot {action_name}({arg0}) while holding '{holding}'",
                        line_number=index,
                        failure_id=FailureCode.MISSING_POST_PICK_PLACE,
                        fact=f"Line {index} ({line}) uses {action_name} while the gripper holds '{holding}'.",
                    )
                if action_name == 'open':
                    closed_regions -= set(self.lid_regions.get(arg0, ()))
                else:
                    closed_regions |= set(self.lid_regions.get(arg0, ()))
                actions.append(DirectAction(action_name, (arg0,)))
                continue

        if holding is not None:
            raise StrictParseError(
                f"Plan ended while still holding '{holding}'; missing place({holding}, region)",
                failure_id=FailureCode.MISSING_POST_PICK_PLACE,
                fact=f"The action list ends while the gripper holds '{holding}'.",
            )

        return actions
