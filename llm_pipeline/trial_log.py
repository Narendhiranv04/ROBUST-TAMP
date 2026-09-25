"""Unified per-trial JSONL log (plan.md Phase 1, step 3).

One file per trial, one JSON object per line. Every event carries ``event``,
``trial_id``, ``seq`` (0, 1, 2, ...) and ``t`` (seconds since ``trial_start``)
plus the event's required fields in :data:`EVENT_FIELDS`. ``record.json`` is
unchanged; this log sits next to it.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from llm_pipeline.failures import failure_check_for


COMMON_FIELDS = ('event', 'trial_id', 'seq', 't')

# Required fields per event (plan.md Phase 1, step 3). Events marked with a
# phase are defined now so the schema is stable; they are emitted from that
# phase on.
EVENT_FIELDS: Dict[str, tuple] = {
    'trial_start': ('scene', 'variant', 'condition', 'seed', 'flags', 'git_commit'),
    'observation': ('step', 'visible_objects', 'object_regions', 'articulation_states', 'newly_visible_objects'),
    'memory_snapshot': ('step', 'memory'),  # Phase 2
    'if_check': ('step', 'objects'),  # Phase 4
    'planning_event': (
        'step', 'kind', 'trigger_objects', 'model', 'prompt_hash', 'prompt_path',
        'raw_output', 'parsed_output', 'planner_call_latency_s',
    ),
    'insertion': ('corrective_sub_plans', 'urgency', 'insertion_point', 'merged_plan', 'first_proposal'),  # Phase 5
    'plan_check': ('step', 'result', 'failure_codes'),
    'pre_action_check': ('step', 'action', 'result', 'failure_codes'),
    'action_start': ('step', 'action', 'bundle_id', 'adapter'),
    'action_end': (
        'step', 'action', 'bundle_id', 'adapter', 'local_retries_used', 'outcome', 'failure_code', 'duration_s',
    ),
    'parallel': ('affected_set', 'independent_actions_executed', 'robot_idle_time_s', 'merge_result'),  # Phase 6
    'trial_end': (
        'success', 'goal_relations_satisfied', 'goal_relations_total', 'procedure_checks_satisfied',
        'procedure_checks_total', 'planner_calls', 'planner_time_s', 'trial_time_s', 'termination_reason',
    ),
}

CHECK_RESULTS = ('pass', 'fail', 'not_run')
ACTION_OUTCOMES = ('success', 'failure', 'not_executed', 'skipped_already_satisfied')


def prompt_hash(system_prompt: str, user_prompt: str) -> str:
    digest = hashlib.sha256()
    digest.update((system_prompt or '').encode('utf-8'))
    digest.update(b'\x00')
    digest.update((user_prompt or '').encode('utf-8'))
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_jsonable(item) for item in value]
        return sorted(items, key=str) if isinstance(value, (set, frozenset)) else items
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value) if isinstance(value, str) else value
    if hasattr(value, 'tolist'):
        return value.tolist()
    return str(value)


class TrialLogger:
    """Appends schema-checked events to one trial's JSONL file."""

    def __init__(self, path: Optional[Path], trial_id: str, prompts_dir: Optional[Path] = None):
        self.path = Path(path) if path is not None else None
        self.trial_id = str(trial_id)
        self.prompts_dir = Path(prompts_dir) if prompts_dir is not None else (
            self.path.parent / 'prompts' if self.path is not None else None
        )
        self._seq = 0
        self._t0 = time.monotonic()
        self._prompt_count = 0
        self.events: List[Dict[str, Any]] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text('', encoding='utf-8')

    @property
    def enabled(self) -> bool:
        return True

    def emit(self, event: str, **fields: Any) -> Dict[str, Any]:
        required = EVENT_FIELDS.get(event)
        if required is None:
            raise ValueError(f'Unknown trial-log event {event!r}')
        missing = [name for name in required if name not in fields]
        if missing:
            raise ValueError(f'{event} event is missing required fields: {", ".join(missing)}')
        if event == 'trial_start':
            self._t0 = time.monotonic()
        record = {
            'event': event,
            'trial_id': self.trial_id,
            'seq': self._seq,
            't': round(time.monotonic() - self._t0, 4),
            'wall_time': datetime.now(timezone.utc).isoformat(),
        }
        record.update({name: _jsonable(value) for name, value in fields.items()})
        self._seq += 1
        self.events.append(record)
        if self.path is not None:
            with self.path.open('a', encoding='utf-8') as handle:
                handle.write(json.dumps(record, sort_keys=False) + '\n')
        return record

    def save_prompt(self, step: int, system_prompt: str, user_prompt: str, kind: str = 'planning') -> Optional[str]:
        """Write one planner-call prompt to ``prompts/`` and return its path relative to the log."""
        self._prompt_count += 1
        if self.prompts_dir is None:
            return None
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        name = f'{self._prompt_count:03d}_step{int(step):03d}_{kind}.txt'
        path = self.prompts_dir / name
        path.write_text(
            f'=== SYSTEM PROMPT ===\n{system_prompt or ""}\n\n=== USER PROMPT ===\n{user_prompt or ""}\n',
            encoding='utf-8',
        )
        base = self.path.parent if self.path is not None else self.prompts_dir.parent
        try:
            return str(path.relative_to(base))
        except ValueError:
            return str(path)


class NullTrialLogger(TrialLogger):
    """Logger used when no trial log is requested; keeps events in memory only."""

    def __init__(self, trial_id: str = 'untracked'):
        super().__init__(path=None, trial_id=trial_id, prompts_dir=None)

    @property
    def enabled(self) -> bool:
        return False


def failure_code_entries(codes: Iterable[Any]) -> List[str]:
    return [str(code) for code in codes if code]


class LoggingFailureChecker:
    """Wraps a failure checker and logs every pre-action check it runs."""

    def __init__(self, inner, emit: Callable[..., Any], step: Callable[[], int]):
        object.__setattr__(self, '_inner', inner)
        object.__setattr__(self, '_emit', emit)
        object.__setattr__(self, '_step', step)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._inner, name, value)

    def precheck(self, action, held_object, snapshot, last_action_name=None):
        failure = self._inner.precheck(action, held_object, snapshot, last_action_name=last_action_name)
        self._emit(
            'pre_action_check',
            step=self._step(),
            action=str(action),
            result='fail' if failure is not None else 'pass',
            failure_codes=[str(failure.failure_id)] if failure is not None else [],
            failure_checks=[str(failure_check_for(failure.failure_id))] if failure is not None else [],
        )
        return failure


def read_trial_log(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def validate_trial_log(events: Sequence[Dict[str, Any]]) -> List[str]:
    """Return schema problems in a trial log (empty list = valid)."""
    problems: List[str] = []
    if not events:
        return ['log is empty']
    if events[0].get('event') != 'trial_start':
        problems.append('first event must be trial_start')
    if events[-1].get('event') != 'trial_end':
        problems.append('last event must be trial_end')
    trial_ids = {event.get('trial_id') for event in events}
    if len(trial_ids) != 1:
        problems.append(f'events carry {len(trial_ids)} different trial_ids')
    last_step = -1
    open_actions: Dict[tuple, int] = {}
    for index, event in enumerate(events):
        name = event.get('event')
        for field in COMMON_FIELDS:
            if field not in event:
                problems.append(f'event {index} ({name}) missing {field}')
        if event.get('seq') != index:
            problems.append(f'event {index} ({name}) has seq {event.get("seq")}')
        required = EVENT_FIELDS.get(name)
        if required is None:
            problems.append(f'event {index} has unknown type {name!r}')
            continue
        for field in required:
            if field not in event:
                problems.append(f'event {index} ({name}) missing {field}')
        if 'step' in event and isinstance(event['step'], int):
            if event['step'] < last_step:
                problems.append(f'event {index} ({name}) step {event["step"]} < previous step {last_step}')
            last_step = max(last_step, event['step'])
        if name in ('plan_check', 'pre_action_check') and event.get('result') not in CHECK_RESULTS:
            problems.append(f'event {index} ({name}) has result {event.get("result")!r}')
        if name == 'action_start':
            open_actions[(event.get('bundle_id'), event.get('action'))] = index
        if name == 'action_end':
            if event.get('outcome') not in ACTION_OUTCOMES:
                problems.append(f'event {index} (action_end) has outcome {event.get("outcome")!r}')
            key = (event.get('bundle_id'), event.get('action'))
            if event.get('outcome') in ('success', 'failure') and key not in open_actions:
                problems.append(f'event {index} (action_end) {key} has no action_start')
            open_actions.pop(key, None)
    if open_actions:
        problems.append(f'action_start without action_end: {sorted(map(str, open_actions))}')
    return problems


__all__ = [
    'ACTION_OUTCOMES',
    'CHECK_RESULTS',
    'EVENT_FIELDS',
    'LoggingFailureChecker',
    'NullTrialLogger',
    'TrialLogger',
    'failure_code_entries',
    'prompt_hash',
    'read_trial_log',
    'validate_trial_log',
]
