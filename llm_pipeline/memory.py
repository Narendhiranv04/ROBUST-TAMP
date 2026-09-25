"""Observation memory (plan.md Phase 2, ``memory.enabled``).

Stores exactly ``<object, last_seen_step, last_region>`` for every object ever
observed. After every observation, visible objects are created or overwritten;
objects that are not visible keep their entry; entries are never deleted; objects
that were never observed are never in memory. "Currently visible" is derived:
``last_seen_step == current step``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional

HELD_REGION = 'gripper'


@dataclass(frozen=True)
class MemoryEntry:
    object_id: str
    last_seen_step: int
    last_region: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return {'object': self.object_id, 'last_seen_step': self.last_seen_step, 'last_region': self.last_region}


class ObservationMemory:
    def __init__(self) -> None:
        self._entries: Dict[str, MemoryEntry] = {}
        self.current_step = 0

    def update(
        self,
        step: int,
        visible_objects: Iterable[str],
        object_regions: Mapping[str, Optional[str]],
        held_object: Optional[str] = None,
    ) -> List[str]:
        """Record one observation; return the objects that entered memory for the first time."""
        self.current_step = int(step)
        new = []
        for name in visible_objects:
            if name not in self._entries:
                new.append(name)
            region = HELD_REGION if held_object and name == held_object else object_regions.get(name)
            self._entries[name] = MemoryEntry(name, int(step), region)
        return new

    def get(self, object_id: str) -> Optional[MemoryEntry]:
        return self._entries.get(object_id)

    def __contains__(self, object_id: str) -> bool:
        return object_id in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> List[MemoryEntry]:
        return sorted(self._entries.values(), key=lambda entry: entry.object_id)

    def is_visible(self, object_id: str) -> bool:
        entry = self._entries.get(object_id)
        return entry is not None and entry.last_seen_step == self.current_step

    def remembered(self) -> List[MemoryEntry]:
        """Entries of objects that are not visible at the current step."""
        return [entry for entry in self.entries() if entry.last_seen_step != self.current_step]

    def snapshot(self) -> List[Dict[str, object]]:
        return [entry.to_dict() for entry in self.entries()]

    def mismatches(self, visible_regions: Iterable[str], open_regions: Iterable[str]) -> List[MemoryEntry]:
        """Remembered objects whose last region is visible and open but which are not seen there."""
        visible = set(visible_regions or ())
        open_ = set(open_regions or ())
        return [
            entry for entry in self.remembered()
            if entry.last_region and entry.last_region != HELD_REGION
            and entry.last_region in visible and entry.last_region in open_
        ]


__all__ = ['HELD_REGION', 'MemoryEntry', 'ObservationMemory']
