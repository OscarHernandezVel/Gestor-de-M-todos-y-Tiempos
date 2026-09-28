from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..core import DoublyLinkedList
from .models import LineError


@dataclass
class HistoryEntry:
    id: str
    label: str
    snapshot: Dict[str, Any]


class History:
    def __init__(self, capacity: int = 200) -> None:
        if capacity < 2:
            raise ValueError("History capacity must be at least 2")
        self.capacity = capacity
        self.entries: DoublyLinkedList[HistoryEntry] = DoublyLinkedList("history")
        self._seq = 0

    @property
    def current(self) -> Optional[HistoryEntry]:
        node = self.entries.cursor
        return node.data if node is not None else None

    @property
    def can_undo(self) -> bool:
        node = self.entries.cursor
        return node is not None and node.prev is not None

    @property
    def can_redo(self) -> bool:
        node = self.entries.cursor
        return node is not None and node.next is not None

    def push(self, label: str, snapshot: Dict[str, Any]) -> HistoryEntry:
        # 1) Descartar la rama de rehacer (todo lo que está después del cursor).
        cursor = self.entries.cursor
        while cursor is not None and self.entries.tail is not cursor:
            self.entries.pop_back()
        # 2) Agregar el nuevo estado y mover el cursor a él.
        self._seq += 1
        entry = HistoryEntry(f"H{self._seq}", label, snapshot)
        node = self.entries.append(entry.id, entry)
        self.entries.cursor = node
        # 3) Respetar la capacidad desechando el estado más antiguo.
        while len(self.entries) > self.capacity:
            self.entries.pop_front()
        return entry

    def undo(self) -> HistoryEntry:
        if not self.can_undo:
            raise LineError("Nothing to undo")
        node, _ = self.entries.cursor_prev()
        return node.data  # type: ignore[union-attr]

    def redo(self) -> HistoryEntry:
        if not self.can_redo:
            raise LineError("Nothing to redo")
        node, _ = self.entries.cursor_next()
        return node.data  # type: ignore[union-attr]

    def jump(self, entry_id: str) -> HistoryEntry:
        """Salta a una entrada concreta del historial."""
        return self.entries.set_cursor(entry_id).data

    def to_list(self) -> List[Dict[str, Any]]:
        cursor = self.entries.cursor
        return [
            {"id": node.key, "label": node.data.label, "current": node is cursor}
            for node in self.entries.iter_nodes()
        ]
