"""Configuration flags from experiment specification.

Flags are addressed by their dotted experiment specification names (``termination.mode``) on the
command line (``--flag termination.mode=evaluator``) and in logs. A flag whose
phase is not implemented yet only accepts its default value, so a trial can
never silently run a behavior that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Dict, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class FlagSpec:
    name: str
    attribute: str
    allowed: Tuple[str, ...]
    default: str
    implemented: Tuple[str, ...]
    phase: int


FLAG_SPECS: Tuple[FlagSpec, ...] = (
    FlagSpec('memory.enabled', 'memory_enabled', ('true', 'false'), 'false', ('true', 'false'), 2),
    FlagSpec('replan.trigger_mode', 'replan_trigger_mode', ('discovery', 'if_rule'), 'discovery', ('discovery', 'if_rule'), 4),
    FlagSpec('replan.output_mode', 'replan_output_mode', ('full_replan', 'corrective'), 'full_replan', ('full_replan', 'corrective'), 5),
    FlagSpec(
        'replan.insertion_mode', 'replan_insertion_mode',
        ('planner', 'always_front', 'always_end'), 'planner', ('planner', 'always_front', 'always_end'), 5,
    ),
    FlagSpec('parallel.enabled', 'parallel_enabled', ('true', 'false'), 'false', ('true', 'false'), 6),
    FlagSpec('termination.mode', 'termination_mode', ('evaluator', 'agent'), 'agent', ('evaluator', 'agent'), 1),
    FlagSpec('prompt.version', 'prompt_version', ('legacy', 'v2'), 'v2', ('legacy', 'v2'), 1),
    FlagSpec('prompt.corrective_hints', 'prompt_corrective_hints', ('off', 'on'), 'off', ('off', 'on'), 5),
    FlagSpec(
        'grasp.confirmation', 'grasp_confirmation', ('gripper_state', 'segmentation'), 'gripper_state',
        ('gripper_state', 'segmentation'), 1,
    ),
    FlagSpec('scene.randomization', 'scene_randomization', ('pose_jitter', 'off'), 'pose_jitter', ('pose_jitter', 'off'), 1),
)
FLAG_SPECS_BY_NAME: Dict[str, FlagSpec] = {spec.name: spec for spec in FLAG_SPECS}


@dataclass(frozen=True)
class PipelineFlags:
    memory_enabled: str = 'false'
    replan_trigger_mode: str = 'discovery'
    replan_output_mode: str = 'full_replan'
    replan_insertion_mode: str = 'planner'
    parallel_enabled: str = 'false'
    termination_mode: str = 'agent'
    prompt_version: str = 'v2'
    prompt_corrective_hints: str = 'off'
    grasp_confirmation: str = 'gripper_state'
    scene_randomization: str = 'pose_jitter'

    def __post_init__(self) -> None:
        for spec in FLAG_SPECS:
            value = getattr(self, spec.attribute)
            if value not in spec.allowed:
                raise ValueError(f'{spec.name}={value!r} is not one of {", ".join(spec.allowed)}')
            if value not in spec.implemented:
                raise NotImplementedError(
                    f'{spec.name}={value} is not implemented; '
                    f'only {", ".join(spec.implemented)} is available'
                )

    def get(self, name: str) -> str:
        return getattr(self, FLAG_SPECS_BY_NAME[name].attribute)

    def to_dict(self) -> Dict[str, str]:
        """Flags keyed by their plan.md names, for logs."""
        return {spec.name: getattr(self, spec.attribute) for spec in FLAG_SPECS}

    def with_values(self, values: Mapping[str, str]) -> 'PipelineFlags':
        updates = {}
        for name, value in values.items():
            spec = FLAG_SPECS_BY_NAME.get(name)
            if spec is None:
                raise ValueError(f'Unknown flag {name!r}; known flags: {", ".join(FLAG_SPECS_BY_NAME)}')
            updates[spec.attribute] = str(value).strip().lower()
        return replace(self, **updates)

    @classmethod
    def from_assignments(cls, assignments: Iterable[str] = ()) -> 'PipelineFlags':
        """Parse ``name=value`` strings (the ``--flag`` CLI form)."""
        values = {}
        for item in assignments or ():
            if '=' not in item:
                raise ValueError(f'Flag must be name=value, got {item!r}')
            name, value = item.split('=', 1)
            values[name.strip()] = value.strip()
        return cls().with_values(values)

    def to_assignments(self) -> list[str]:
        return [f'{name}={value}' for name, value in self.to_dict().items()]


assert {spec.attribute for spec in FLAG_SPECS} == {field.name for field in fields(PipelineFlags)}

__all__ = ['FLAG_SPECS', 'FLAG_SPECS_BY_NAME', 'FlagSpec', 'PipelineFlags']
