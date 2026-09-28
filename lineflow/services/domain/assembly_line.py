from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ..core import DoublyLinkedList, Node, record_pointer_writes
from .models import (
    LineError,
    Station,
    WorkElement,
    clean_name,
    clean_notes,
    clean_therblig,
    clean_time_ms,
)

DEFAULT_TAKT_MS = 60_000
_ID_NUMBER = re.compile(r"(\d+)$")


class AssemblyLine:
    """Secuencia de tareas agrupadas en estaciones de trabajo."""

    def __init__(self, name: str = "Assembly Line", takt_ms: int = DEFAULT_TAKT_MS) -> None:
        self.name = clean_name(name, "Line name")
        self.takt_ms = self._clean_takt(takt_ms)
        self.process: DoublyLinkedList[WorkElement] = DoublyLinkedList("process line")
        self.stations: DoublyLinkedList[Station] = DoublyLinkedList("stations")
        self._task_seq = 0
        self._station_seq = 0

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_takt(value: Any) -> int:
        ms = clean_time_ms(value, "Takt time")
        if ms <= 0:
            raise LineError("Takt time must be greater than zero")
        return ms

    def _new_task_id(self) -> str:
        while True:
            self._task_seq += 1
            candidate = f"T{self._task_seq}"
            if candidate not in self.process:
                return candidate

    def _new_station_id(self) -> str:
        while True:
            self._station_seq += 1
            candidate = f"S{self._station_seq}"
            if candidate not in self.stations:
                return candidate

    def _left_anchor(self, station_node: Node[Station]) -> Optional[Node[WorkElement]]:
        """Último nodo de la estación no vacía más cercana hacia atrás.

        Es el punto de anclaje para el segmento de una estación: su segmento
        debe comenzar justo después de este nodo (o en la cabeza si es None).
        Normalmente es O(1); solo recorre estaciones vacías intermedias.
        """
        current = station_node.prev
        while current is not None:
            if current.data.last is not None:
                return current.data.last
            current = current.prev
        return None

    def _append_anchors(self, station: Station) -> Tuple[Optional[Node[WorkElement]], Optional[Node[WorkElement]]]:
        """Vecinos (left, right) entre los que se agrega una tarea al final de ``station``."""
        if station.last is not None:
            left: Optional[Node[WorkElement]] = station.last
        else:
            left = self._left_anchor(self.stations.get_node(station.id))
        right = left.next if left is not None else self.process.head
        return left, right

    def _link_into_station(
        self,
        node: Node[WorkElement],
        station: Station,
        left: Optional[Node[WorkElement]],
        right: Optional[Node[WorkElement]],
    ) -> None:
        """Enlaza ``node`` en ``process`` y actualiza los extremos de la estación."""
        self.process.insert_node_between(node, left, right)
        if station.first is None:
            station.first = node
            station.last = node
            record_pointer_writes(2, node)
        else:
            if right is station.first:
                station.first = node
                record_pointer_writes(1, node)
            if left is station.last:
                station.last = node
                record_pointer_writes(1, node)
        station.count += 1
        station.load_ms += node.data.time_ms
        node.data.station_id = station.id

    def _unlink_from_station(self, node: Node[WorkElement], station: Station) -> None:
        """Desenlaza ``node`` de ``process`` y corrige los extremos de su estación."""
        if station.first is node and station.last is node:
            station.first = None
            station.last = None
            record_pointer_writes(2, node)
        elif station.first is node:
            station.first = node.next
            record_pointer_writes(1, node.next)
        elif station.last is node:
            station.last = node.prev
            record_pointer_writes(1, node.prev)
        self.process.detach_node(node)
        station.count -= 1
        station.load_ms -= node.data.time_ms

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def station(self, station_id: str) -> Station:
        return self.stations.get(station_id)

    def task(self, task_id: str) -> WorkElement:
        return self.process.get(task_id)

    def task_node(self, task_id: str) -> Node[WorkElement]:
        return self.process.get_node(task_id)

    def station_of(self, task_id: str) -> Station:
        return self.station(self.task(task_id).station_id)

    def iter_stations(self) -> Iterator[Station]:
        return iter(self.stations)

    @property
    def cursor_id(self) -> Optional[str]:
        node = self.process.cursor
        return node.key if node is not None else None

    @property
    def task_count(self) -> int:
        return len(self.process)

    @property
    def total_ms(self) -> int:
        return sum(st.load_ms for st in self.stations)

    # ------------------------------------------------------------------
    # Configuración de la línea
    # ------------------------------------------------------------------
    def rename(self, name: str) -> None:
        self.name = clean_name(name, "Line name")

    def set_takt(self, takt_ms: Any) -> None:
        self.takt_ms = self._clean_takt(takt_ms)

    # ------------------------------------------------------------------
    # Estaciones
    # ------------------------------------------------------------------
    def add_station(self, name: Optional[str] = None, before_id: Optional[str] = None) -> Station:
        """Crea una estación vacía antes de ``before_id`` (al final si es None). O(1)."""
        if before_id is not None:
            self.stations.get_node(before_id)  # valida antes de modificar
        station_id = self._new_station_id()
        label = clean_name(name, "Station name") if name else f"Station {self._station_seq}"
        station = Station(station_id, label)
        self.stations.insert_at(station_id, station, before_id)
        return station

    def rename_station(self, station_id: str, name: str) -> Station:
        station = self.station(station_id)
        station.name = clean_name(name, "Station name")
        return station

    def move_station(self, station_id: str, before_id: Optional[str] = None) -> Station:
        """Reordena una estación completa con todas sus tareas. O(1).

        1. Se mueve el nodo de la estación en la lista ``stations``.
        2. Se mueve su segmento ``first..last`` en ``process`` reescribiendo
           únicamente los punteros de los bordes (los nodos internos no se
           tocan, sin importar cuántas tareas tenga la estación).
        """
        station_node = self.stations.get_node(station_id)
        if before_id == station_id:
            return station_node.data
        ref = self.stations.get_node(before_id) if before_id is not None else None
        if station_node.next is ref:
            return station_node.data
        self.stations.move(station_id, before_id)
        station = station_node.data
        if station.first is not None and station.last is not None:
            after = self._left_anchor(station_node)
            self.process.move_segment(station.first, station.last, after)
        return station

    def remove_station(self, station_id: str) -> Tuple[Station, Optional[Station]]:
        """Elimina una estación. Sus tareas se fusionan con la estación vecina.

        Como los segmentos de estaciones consecutivas son adyacentes en la
        lista del proceso, fusionar solo requiere mover los punteros
        ``first``/``last`` de la estación receptora (O(1)); reasignar el
        identificador de estación de cada tarea cuesta O(k).
        Devuelve ``(estación_eliminada, estación_receptora)``.
        """
        station_node = self.stations.get_node(station_id)
        station = station_node.data
        receiver: Optional[Station] = None
        if station.count:
            neighbour = station_node.prev if station_node.prev is not None else station_node.next
            if neighbour is None:
                raise LineError("Cannot remove the only station while it still has work elements")
            receiver = neighbour.data
            if neighbour is station_node.prev:
                # El segmento eliminado sigue inmediatamente al del receptor.
                if receiver.first is None:
                    receiver.first = station.first
                receiver.last = station.last
            else:
                # El segmento eliminado precede inmediatamente al del receptor.
                if receiver.last is None:
                    receiver.last = station.last
                receiver.first = station.first
            record_pointer_writes(2, station.first, station.last)
            for node in station.iter_nodes():
                node.data.station_id = receiver.id
            receiver.count += station.count
            receiver.load_ms += station.load_ms
        self.stations.remove(station_id)
        station.first = station.last = None
        station.count = 0
        station.load_ms = 0
        return station, receiver

    # ------------------------------------------------------------------
    # Tareas (elementos de trabajo)
    # ------------------------------------------------------------------
    def add_task(
        self,
        station_id: str,
        name: str,
        time_ms: Any,
        therblig: Any = "",
        notes: Any = "",
        before_id: Optional[str] = None,
    ) -> WorkElement:
        """Inserta una tarea en ``station_id`` antes de ``before_id`` (o al final). O(1)."""
        station_node = self.stations.get_node(station_id)
        station = station_node.data
        clean = clean_name(name, "Element name")
        ms = clean_time_ms(time_ms)
        code = clean_therblig(therblig)
        note = clean_notes(notes)
        ref: Optional[Node[WorkElement]] = None
        if before_id is not None:
            ref = self.process.get_node(before_id)
            if ref.data.station_id != station.id:
                raise LineError(f"Element '{before_id}' is not in station '{station.name}'")
        task_id = self._new_task_id()
        element = WorkElement(task_id, clean, ms, station.id, code, note)
        node: Node[WorkElement] = Node(task_id, element)
        if ref is None:
            left, right = self._append_anchors(station)
        else:
            left, right = ref.prev, ref
        self._link_into_station(node, station, left, right)
        if self.process.cursor is None:
            self.process.cursor = node
        return element

    def update_task(
        self,
        task_id: str,
        *,
        name: Any = None,
        time_ms: Any = None,
        therblig: Any = None,
        notes: Any = None,
    ) -> WorkElement:
        """Edita los datos de una tarea. La carga de la estación se ajusta en O(1)."""
        element = self.task(task_id)
        new_name = clean_name(name, "Element name") if name is not None else element.name
        new_ms = clean_time_ms(time_ms) if time_ms is not None else element.time_ms
        new_code = clean_therblig(therblig) if therblig is not None else element.therblig
        new_notes = clean_notes(notes) if notes is not None else element.notes
        station = self.station(element.station_id)
        station.load_ms += new_ms - element.time_ms
        element.name = new_name
        element.time_ms = new_ms
        element.therblig = new_code
        element.notes = new_notes
        return element

    def remove_task(self, task_id: str) -> WorkElement:
        """Elimina una tarea. Sus vecinos quedan enlazados entre sí. O(1)."""
        node = self.task_node(task_id)
        station = self.station(node.data.station_id)
        self._unlink_from_station(node, station)
        return node.data

    def move_task(self, task_id: str, station_id: str, before_id: Optional[str] = None) -> WorkElement:
        """Mueve una tarea a ``station_id`` antes de ``before_id`` (al final si es None).

        Es la operación de *drag and drop*: desenlazar (4 punteros) +
        enlazar (4 punteros) + ajustar extremos de estación. O(1).
        """
        node = self.task_node(task_id)
        element = node.data
        source = self.station(element.station_id)
        target = self.station(station_id)
        ref: Optional[Node[WorkElement]] = None
        if before_id is not None:
            if before_id == task_id:
                return element
            ref = self.process.get_node(before_id)
            if ref.data.station_id != target.id:
                raise LineError(f"Element '{before_id}' is not in station '{target.name}'")
        if source is target:
            if ref is None and target.last is node:
                return element
            if ref is not None and node.next is ref:
                return element
        was_cursor = self.process.cursor is node
        self._unlink_from_station(node, source)
        if ref is None:
            left, right = self._append_anchors(target)
        else:
            left, right = ref.prev, ref
        self._link_into_station(node, target, left, right)
        if was_cursor:
            self.process.cursor = node
        return element

    def shift_task(self, task_id: str, direction: str) -> WorkElement:
        """Desplaza una tarea una posición respetando la secuencia del proceso.

        * ``up``    : intercambia con su predecesora; si es la primera de su
          estación pasa al final de la estación anterior.
        * ``down``  : intercambia con su sucesora; si es la última de su
          estación pasa al inicio de la estación siguiente.
        * ``left``  : pasa al final de la estación anterior.
        * ``right`` : pasa al inicio de la estación siguiente.
        """
        node = self.task_node(task_id)
        station_node = self.stations.get_node(node.data.station_id)
        station = station_node.data
        if direction not in ("up", "down", "left", "right"):
            raise LineError("Direction must be up, down, left or right")

        if direction == "up" and station.first is not node:
            return self.move_task(task_id, station.id, node.prev.key)  # type: ignore[union-attr]
        if direction == "down" and station.last is not node:
            after_next = node.next.next  # type: ignore[union-attr]
            same_station = after_next is not None and after_next.data.station_id == station.id
            return self.move_task(task_id, station.id, after_next.key if same_station else None)  # type: ignore[union-attr]
        if direction in ("up", "left"):
            if station_node.prev is None:
                raise LineError("There is no previous station")
            return self.move_task(task_id, station_node.prev.key, None)
        # down (última de su estación) o right
        if station_node.next is None:
            raise LineError("There is no next station")
        target = station_node.next.data
        before = target.first.key if target.first is not None else None
        return self.move_task(task_id, target.id, before)

    # ------------------------------------------------------------------
    # Cursor (tarea activa)
    # ------------------------------------------------------------------
    def set_cursor(self, task_id: str) -> WorkElement:
        return self.process.set_cursor(task_id).data

    def cursor_next(self, wrap: bool = True) -> Tuple[Optional[WorkElement], bool]:
        """Avanza a la tarea sucesora (cruza estaciones de forma natural). O(1)."""
        node, wrapped = self.process.cursor_next(wrap)
        return (node.data if node is not None else None), wrapped

    def cursor_prev(self, wrap: bool = True) -> Tuple[Optional[WorkElement], bool]:
        node, wrapped = self.process.cursor_prev(wrap)
        return (node.data if node is not None else None), wrapped

    def cursor_first(self) -> Optional[WorkElement]:
        node = self.process.cursor_to_head()
        return node.data if node is not None else None

    def cursor_last(self) -> Optional[WorkElement]:
        node = self.process.cursor_to_tail()
        return node.data if node is not None else None

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "takt_ms": self.takt_ms,
            "cursor": self.cursor_id,
            "seq": {"task": self._task_seq, "station": self._station_seq},
            "stations": [
                {
                    "id": station.id,
                    "name": station.name,
                    "tasks": [node.data.to_dict() for node in station.iter_nodes()],
                }
                for station in self.stations
            ],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "AssemblyLine":
        """Reconstruye una línea desde un diccionario (importación / deshacer). O(n)."""
        if not isinstance(data, dict):
            raise LineError("Line data must be an object")
        line = cls(data.get("name", "Assembly Line"), data.get("takt_ms", DEFAULT_TAKT_MS))
        stations = data.get("stations")
        if not isinstance(stations, list):
            raise LineError("'stations' must be a list")
        max_task = max_station = 0
        for raw_station in stations:
            if not isinstance(raw_station, dict):
                raise LineError("Each station must be an object")
            sid = raw_station.get("id")
            if not isinstance(sid, str) or not sid.strip():
                raise LineError("Each station needs a text id")
            if sid in line.stations:
                raise LineError(f"Duplicated station id '{sid}'")
            station = Station(sid, clean_name(raw_station.get("name", sid), "Station name"))
            line.stations.append(sid, station)
            max_station = max(max_station, _numeric_suffix(sid))
            tasks = raw_station.get("tasks", [])
            if not isinstance(tasks, list):
                raise LineError("'tasks' must be a list")
            for raw in tasks:
                if not isinstance(raw, dict):
                    raise LineError("Each element must be an object")
                tid = raw.get("id")
                if not isinstance(tid, str) or not tid.strip():
                    raise LineError("Each element needs a text id")
                if tid in line.process:
                    raise LineError(f"Duplicated element id '{tid}'")
                element = WorkElement(
                    id=tid,
                    name=clean_name(raw.get("name", ""), "Element name"),
                    time_ms=clean_time_ms(raw.get("time_ms", 0)),
                    station_id=sid,
                    therblig=clean_therblig(raw.get("therblig", "")),
                    notes=clean_notes(raw.get("notes", "")),
                )
                # Se construye en orden: siempre se enlaza al final del proceso.
                line._link_into_station(Node(tid, element), station, line.process.tail, None)
                max_task = max(max_task, _numeric_suffix(tid))
        seq = data.get("seq") if isinstance(data.get("seq"), dict) else {}
        line._task_seq = max(max_task, _int_or_zero(seq.get("task")))
        line._station_seq = max(max_station, _int_or_zero(seq.get("station")))
        cursor = data.get("cursor")
        if isinstance(cursor, str) and cursor in line.process:
            line.process.set_cursor(cursor)
        elif line.process.head is not None:
            line.process.cursor = line.process.head
        return line

    # ------------------------------------------------------------------
    # Integridad (usado por las pruebas)
    # ------------------------------------------------------------------
    def validate(self) -> None:
        """Verifica punteros, segmentos y cargas. Lanza ``LineError`` si algo falla."""
        self.process.validate()
        self.stations.validate()
        node = self.process.head
        for station in self.stations:
            if station.count == 0:
                if station.first is not None or station.last is not None or station.load_ms != 0:
                    raise LineError(f"Empty station {station.id} has dangling pointers or load")
                continue
            if station.first is not node:
                raise LineError(f"Station {station.id}: 'first' does not match process order")
            load = 0
            last_seen = None
            for _ in range(station.count):
                if node is None:
                    raise LineError(f"Station {station.id}: segment shorter than its count")
                if node.data.station_id != station.id:
                    raise LineError(f"Element {node.key} has wrong station id")
                load += node.data.time_ms
                last_seen = node
                node = node.next
            if station.last is not last_seen:
                raise LineError(f"Station {station.id}: 'last' pointer is wrong")
            if station.load_ms != load:
                raise LineError(f"Station {station.id}: load {station.load_ms} != {load}")
        if node is not None:
            raise LineError(f"Element {node.key} does not belong to any station segment")


def _numeric_suffix(identifier: str) -> int:
    match = _ID_NUMBER.search(identifier)
    return int(match.group(1)) if match else 0


def _int_or_zero(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def station_views(line: AssemblyLine) -> List[Dict[str, Any]]:
    """Vista de estaciones con los punteros ``prev``/``next`` de cada tarea."""
    views = []
    for station in line.stations:
        tasks = []
        for node in station.iter_nodes():
            element = node.data
            tasks.append(
                {
                    **element.to_dict(),
                    "category": element.category,
                    "prev": node.prev.key if node.prev is not None else None,
                    "next": node.next.key if node.next is not None else None,
                }
            )
        views.append(
            {
                "id": station.id,
                "name": station.name,
                "count": station.count,
                "load_ms": station.load_ms,
                "first": station.first.key if station.first is not None else None,
                "last": station.last.key if station.last is not None else None,
                "tasks": tasks,
            }
        )
    return views
