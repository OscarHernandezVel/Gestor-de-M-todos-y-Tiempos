"""
Servicio de aplicación: coordina la línea, el cronómetro, el historial y la
bitácora de operaciones. Es la única puerta de entrada que usa la API web.

Cada operación se ejecuta bajo un candado (el servidor es multi-hilo) y se
instrumenta: se mide el tiempo de la operación estructural y cuántos
punteros se reescribieron, para mostrarlo en la interfaz.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from .core import POINTER_STATS, DoublyLinkedList
from .domain import (
    CATEGORIES,
    THERBLIGS,
    AssemblyLine,
    History,
    LineError,
    Stopwatch,
    build_demo_line,
    compute_metrics,
    standard_time,
    station_views,
)

O1 = "O(1)"


class LineFlowService:
    def __init__(
        self,
        line: Optional[AssemblyLine] = None,
        clock: Callable[[], float] = time.perf_counter,
        history_capacity: int = 200,
        log_capacity: int = 40,
    ) -> None:
        self.lock = threading.RLock()
        self.line = line if line is not None else build_demo_line()
        self.stopwatch = Stopwatch(clock)
        self.history = History(history_capacity)
        self.history.push("Initial state", self.line.to_dict())
        self.log: DoublyLinkedList[Dict[str, Any]] = DoublyLinkedList("operation log")
        self.log_capacity = log_capacity
        self.auto_advance = True
        self.baseline: Optional[Dict[str, Any]] = None
        self._op_seq = 0

    # ------------------------------------------------------------------
    # Núcleo de ejecución
    # ------------------------------------------------------------------
    def _run(
        self,
        name: str,
        complexity: str,
        action: Callable[[], Any],
        history_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        with self.lock:
            POINTER_STATS.begin()
            start = time.perf_counter_ns()
            try:
                detail = action()
            finally:
                elapsed_ns = time.perf_counter_ns() - start
                writes, touched = POINTER_STATS.end()
            if history_label:
                self.history.push(history_label, self.line.to_dict())
            self._op_seq += 1
            op = {
                "id": self._op_seq,
                "name": name,
                "complexity": complexity,
                "pointer_writes": writes,
                "micros": round(elapsed_ns / 1000, 1),
                "detail": detail if isinstance(detail, str) else "",
                "touched": sorted(str(key) for key in touched),
            }
            self.log.append(op["id"], op)
            while len(self.log) > self.log_capacity:
                self.log.pop_front()
            state = self.state()
            state["op"] = op
            return state

    def _restore(self, snapshot: Dict[str, Any]) -> None:
        keep_cursor = self.line.cursor_id
        self.line = AssemblyLine.from_dict(snapshot)
        if keep_cursor is not None and keep_cursor in self.line.process:
            self.line.set_cursor(keep_cursor)

    # ------------------------------------------------------------------
    # Estado para la interfaz
    # ------------------------------------------------------------------
    def state(self) -> Dict[str, Any]:
        with self.lock:
            metrics = compute_metrics(self.line)
            return {
                "line": {
                    "name": self.line.name,
                    "takt_ms": self.line.takt_ms,
                    "cursor": self.line.cursor_id,
                    "head": self.line.process.head.key if self.line.process.head else None,
                    "tail": self.line.process.tail.key if self.line.process.tail else None,
                    "stations": station_views(self.line),
                },
                "metrics": metrics,
                "baseline": self.baseline,
                "stopwatch": {
                    **self.stopwatch.to_dict(),
                    "auto_advance": self.auto_advance,
                    "stats": self.stopwatch.stats(),
                },
                "history": {
                    "can_undo": self.history.can_undo,
                    "can_redo": self.history.can_redo,
                    "entries": self.history.to_list(),
                },
                "log": list(reversed(list(self.log))),
                "server_time": time.time(),
            }

    @staticmethod
    def catalog() -> Dict[str, Any]:
        return {"therbligs": THERBLIGS, "categories": CATEGORIES}

    # ------------------------------------------------------------------
    # Línea
    # ------------------------------------------------------------------
    def update_line(self, name: Any = None, takt_ms: Any = None) -> Dict[str, Any]:
        def action() -> str:
            if name is not None:
                self.line.rename(name)
            if takt_ms is not None:
                self.line.set_takt(takt_ms)
            return "Line settings updated"

        return self._run("update_line", O1, action, "Edit line settings")

    def load_demo(self) -> Dict[str, Any]:
        def action() -> str:
            self.line = build_demo_line()
            self.stopwatch.reset()
            self.baseline = None
            return "Demo line loaded"

        return self._run("load_demo", "O(n)", action, "Load demo line")

    def import_data(self, payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise LineError("Import payload must be an object")
        raw_line = payload.get("line", payload)
        new_line = AssemblyLine.from_dict(raw_line)  # valida antes de reemplazar

        def action() -> str:
            self.line = new_line
            self.stopwatch.reset()
            self.baseline = None
            return f"Imported {new_line.task_count} elements"

        return self._run("import", "O(n)", action, "Import line")

    def export_data(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "format": "lineflow/1",
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "line": self.line.to_dict(),
                "metrics": compute_metrics(self.line),
                "laps": self.stopwatch.to_dict()["laps"],
            }

    # ------------------------------------------------------------------
    # Estaciones
    # ------------------------------------------------------------------
    def add_station(self, name: Any = None, before_id: Any = None) -> Dict[str, Any]:
        def action() -> str:
            station = self.line.add_station(name, before_id)
            return f"Station {station.id} '{station.name}' created"

        return self._run("add_station", O1, action, "Add station")

    def rename_station(self, station_id: str, name: Any) -> Dict[str, Any]:
        def action() -> str:
            station = self.line.rename_station(station_id, name)
            return f"Station {station.id} renamed"

        return self._run("rename_station", O1, action, "Rename station")

    def move_station(self, station_id: str, before_id: Any = None) -> Dict[str, Any]:
        def action() -> str:
            self.line.move_station(station_id, before_id)
            return f"Station {station_id} and its whole segment relinked"

        return self._run("move_station", O1, action, "Reorder station")

    def remove_station(self, station_id: str) -> Dict[str, Any]:
        def action() -> str:
            removed, receiver = self.line.remove_station(station_id)
            if receiver is not None:
                return f"Station {removed.id} removed; elements merged into {receiver.id}"
            return f"Station {removed.id} removed"

        return self._run("remove_station", "O(1) + O(k) relabel", action, "Remove station")

    # ------------------------------------------------------------------
    # Tareas
    # ------------------------------------------------------------------
    def add_task(self, station_id: str, name: Any, time_ms: Any, therblig: Any = "",
                 notes: Any = "", before_id: Any = None) -> Dict[str, Any]:
        def action() -> str:
            element = self.line.add_task(station_id, name, time_ms, therblig, notes, before_id)
            where = f"before {before_id}" if before_id else "at the end"
            return f"{element.id} inserted in {station_id} {where}"

        return self._run("insert_element", O1, action, "Insert element")

    def update_task(self, task_id: str, **fields: Any) -> Dict[str, Any]:
        def action() -> str:
            self.line.update_task(task_id, **fields)
            return f"{task_id} updated"

        return self._run("update_element", O1, action, f"Edit {task_id}")

    def remove_task(self, task_id: str) -> Dict[str, Any]:
        def action() -> str:
            element = self.line.remove_task(task_id)
            return f"{element.id} unlinked; neighbours joined"

        return self._run("delete_element", O1, action, f"Delete {task_id}")

    def move_task(self, task_id: str, station_id: str, before_id: Any = None) -> Dict[str, Any]:
        def action() -> str:
            self.line.move_task(task_id, station_id, before_id)
            where = f"before {before_id}" if before_id else "at the end"
            return f"{task_id} relinked into {station_id} {where}"

        return self._run("move_element", O1, action, f"Move {task_id}")

    def shift_task(self, task_id: str, direction: str) -> Dict[str, Any]:
        def action() -> str:
            element = self.line.shift_task(task_id, direction)
            return f"{task_id} shifted {direction} (now in {element.station_id})"

        return self._run("shift_element", O1, action, f"Move {task_id} {direction}")

    # ------------------------------------------------------------------
    # Cursor de la línea
    # ------------------------------------------------------------------
    def move_cursor(self, task_id: Any = None, direction: Any = None) -> Dict[str, Any]:
        def action() -> str:
            if task_id is not None:
                self.line.set_cursor(task_id)
            elif direction == "next":
                self.line.cursor_next(wrap=True)
            elif direction == "prev":
                self.line.cursor_prev(wrap=True)
            elif direction == "first":
                self.line.cursor_first()
            elif direction == "last":
                self.line.cursor_last()
            else:
                raise LineError("Provide task_id or direction (next, prev, first, last)")
            return f"Cursor on {self.line.cursor_id}"

        return self._run("cursor", O1, action)

    # ------------------------------------------------------------------
    # Historial y escenario base
    # ------------------------------------------------------------------
    def undo(self) -> Dict[str, Any]:
        def action() -> str:
            entry = self.history.undo()
            self._restore(entry.snapshot)
            return f"Back to: {entry.label}"

        return self._run("undo", "O(1) + O(n) restore", action)

    def redo(self) -> Dict[str, Any]:
        def action() -> str:
            entry = self.history.redo()
            self._restore(entry.snapshot)
            return f"Forward to: {entry.label}"

        return self._run("redo", "O(1) + O(n) restore", action)

    def jump_history(self, entry_id: str) -> Dict[str, Any]:
        def action() -> str:
            entry = self.history.jump(entry_id)
            self._restore(entry.snapshot)
            return f"Jumped to: {entry.label}"

        return self._run("history_jump", "O(1) + O(n) restore", action)

    def pin_baseline(self) -> Dict[str, Any]:
        def action() -> str:
            metrics = compute_metrics(self.line)
            self.baseline = {k: v for k, v in metrics.items() if k != "per_station"}
            self.baseline["label"] = time.strftime("%H:%M:%S")
            return "Current scenario pinned as baseline"

        return self._run("pin_baseline", "O(S)", action)

    def clear_baseline(self) -> Dict[str, Any]:
        def action() -> str:
            self.baseline = None
            return "Baseline cleared"

        return self._run("clear_baseline", O1, action)

    # ------------------------------------------------------------------
    # Cronómetro
    # ------------------------------------------------------------------
    def stopwatch_start(self) -> Dict[str, Any]:
        def action() -> str:
            self.stopwatch.start()
            return "Stopwatch running"

        return self._run("stopwatch_start", O1, action)

    def stopwatch_pause(self) -> Dict[str, Any]:
        def action() -> str:
            self.stopwatch.pause()
            return "Stopwatch paused"

        return self._run("stopwatch_pause", O1, action)

    def stopwatch_reset(self) -> Dict[str, Any]:
        def action() -> str:
            self.stopwatch.reset()
            return "Stopwatch reset; all marks cleared"

        return self._run("stopwatch_reset", "O(L)", action)

    def stopwatch_settings(self, auto_advance: Any) -> Dict[str, Any]:
        if not isinstance(auto_advance, bool):
            raise LineError("auto_advance must be true or false")

        def action() -> str:
            self.auto_advance = auto_advance
            return f"Auto-advance {'on' if auto_advance else 'off'}"

        return self._run("stopwatch_settings", O1, action)

    def record_lap(self) -> Dict[str, Any]:
        """Registra una marca para la tarea activa y (opcionalmente) avanza el cursor."""

        def action() -> str:
            element_id = self.line.cursor_id
            lap = self.stopwatch.lap(element_id)
            detail = f"{lap.id} closed {element_id or 'unassigned'}"
            if self.auto_advance and element_id is not None:
                _, wrapped = self.line.cursor_next(wrap=True)
                if wrapped:
                    self.stopwatch.cycle += 1
                    detail += f" · cycle {self.stopwatch.cycle} starts"
            return detail

        return self._run("record_lap", O1, action)

    def lap_cursor(self, lap_id: Any = None, direction: Any = None) -> Dict[str, Any]:
        def action() -> str:
            if lap_id is not None:
                self.stopwatch.set_cursor(lap_id)
            elif direction == "next":
                self.stopwatch.cursor_next()
            elif direction == "prev":
                self.stopwatch.cursor_prev()
            elif direction == "first":
                self.stopwatch.cursor_first()
            elif direction == "last":
                self.stopwatch.cursor_last()
            else:
                raise LineError("Provide lap_id or direction (next, prev, first, last)")
            cursor = self.stopwatch.laps.cursor
            return f"Lap cursor on {cursor.key if cursor else 'none'}"

        return self._run("lap_cursor", O1, action)

    def update_lap(self, lap_id: str, split_ms: Any = None, duration_ms: Any = None,
                   element_id: Any = ...) -> Dict[str, Any]:
        def action() -> str:
            changes = []
            if element_id is not ...:
                if element_id is not None and element_id not in self.line.process:
                    raise LineError(f"Element '{element_id}' does not exist")
                self.stopwatch.assign(lap_id, element_id)
                changes.append("element")
            if split_ms is not None:
                self.stopwatch.adjust_split(lap_id, split_ms)
                changes.append("split")
            elif duration_ms is not None:
                self.stopwatch.set_duration(lap_id, duration_ms)
                changes.append("duration")
            if not changes:
                raise LineError("Nothing to update")
            return f"{lap_id}: corrected {', '.join(changes)}"

        return self._run("correct_mark", O1, action)

    def delete_lap(self, lap_id: str) -> Dict[str, Any]:
        def action() -> str:
            self.stopwatch.delete_mark(lap_id)
            return f"{lap_id} removed; interval merged into successor"

        return self._run("delete_mark", O1, action)

    def insert_lap(self, before_lap_id: str, at_ms: Any, element_id: Any = None) -> Dict[str, Any]:
        def action() -> str:
            if element_id is not None and element_id not in self.line.process:
                raise LineError(f"Element '{element_id}' does not exist")
            lap = self.stopwatch.insert_mark(before_lap_id, at_ms, element_id)
            return f"Missed mark {lap.id} inserted before {before_lap_id}"

        return self._run("insert_mark", O1, action)

    def apply_standard_time(self, task_id: str, rating: Any = 100, allowance: Any = 0) -> Dict[str, Any]:
        for label, value in (("rating", rating), ("allowance", allowance)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise LineError(f"{label.capitalize()} must be a number")
        with self.lock:
            self.line.task(task_id)  # valida que el elemento exista
            durations = self.stopwatch.durations_for(task_id)
            if not durations:
                raise LineError(f"There are no observations for {task_id}")
            mean = sum(durations) / len(durations)
            result = standard_time(mean, float(rating), float(allowance))

            def action() -> str:
                self.line.update_task(task_id, time_ms=round(result["standard_ms"]))
                return (
                    f"{task_id}: {len(durations)} obs, mean {mean / 1000:.2f}s → "
                    f"standard {result['standard_ms'] / 1000:.2f}s"
                )

            return self._run("apply_standard_time", O1, action, f"Standard time {task_id}")
