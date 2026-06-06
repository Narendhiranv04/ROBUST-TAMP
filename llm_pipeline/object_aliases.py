"""Canonical planner-facing object names and simulator compatibility aliases."""

from __future__ import annotations

from typing import Iterable, Mapping, TypeVar


OBJECT_ALIASES = {
    "soup": "can_of_beans",
}

SCENE_OBJECT_ALIASES = {
    "can_of_beans": "soup",
}


def canonical_object_name(object_name: str | None) -> str:
    token = str(object_name or "").strip()
    return OBJECT_ALIASES.get(token, token)


def canonical_object_names(object_names: Iterable[str]) -> list[str]:
    seen = set()
    ordered = []
    for object_name in object_names:
        canonical = canonical_object_name(object_name)
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        ordered.append(canonical)
    return ordered


def scene_object_for_object(object_name: str, env=None) -> str:
    canonical = canonical_object_name(object_name)
    if env is None:
        return SCENE_OBJECT_ALIASES.get(canonical, canonical)

    for candidate in (canonical, SCENE_OBJECT_ALIASES.get(canonical, canonical)):
        try:
            obj = env.get_object(candidate)
        except Exception:
            obj = None
        if obj is not None:
            return candidate
    return SCENE_OBJECT_ALIASES.get(canonical, canonical)


_T = TypeVar("_T")


def canonicalize_object_mapping(values: Mapping[str, _T]) -> dict[str, _T]:
    return {canonical_object_name(key): value for key, value in (values or {}).items()}
