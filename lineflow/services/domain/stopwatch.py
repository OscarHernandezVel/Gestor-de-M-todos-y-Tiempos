from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from ..core import DoublyLinkedList, Node
from .models import LineError, clean_time_ms


@dataclass
class Lap:
    """Marca del cronómetro (lectura acumulada + elemento asociado)."""

    id: str
    split_ms: int
    element_id: Optional[str] = None
    cycle: int = 1


class Stopwatch:
    """Cronómetro con marcas navegables hacia adelante y hacia atrás."""

    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self.laps: DoublyLinkedList[Lap] = DoublyLinkedList("laps")
        self.running = False
        self._started_at: Optional[float] = None
        self._accumulated_ms = 0
        self.cycle = 1
        self._seq = 0

    # ------------------------------------------------------------------
    # Reloj
    # ------------------------------------------------------------------
    @property
    def elapsed_ms(self) -> int:
        if self.running and self._started_at is not None:
            return self._accumulated_ms + int((self._clock() - self._started_at) * 1000)
        return self._accumulated_ms

    def start(self) -> None:
        """Inicia o reanuda el cronómetro."""
        if self.running:
            return
        self._started_at = self._clock()
        self.running = True

    def pause(self) -> None:
        if not self.running:
            return
        self._accumulated_ms = self.elapsed_ms
        self._started_at = None
        self.running = False

    def reset(self) -> None:
        """Detiene el cronómetro y borra todas las marcas."""
        self.running = False
        self._started_at = None
        self._accumulated_ms = 0
        self.laps.clear()
        self.cycle = 1
        self._seq = 0

    # ------------------------------------------------------------------
    # Marcas
    # ------------------------------------------------------------------
    def _new_id(self) -> str:
        self._seq += 1
        return f"L{self._seq}"

    @staticmethod
    def duration_of(node: Node[Lap]) -> int:
        """Duración del intervalo que termina en ``node`` (usa el puntero prev). O(1)."""
        previous = node.prev.data.split_ms if node.prev is not None else 0
        return node.data.split_ms - previous

    def lap(self, element_id: Optional[str] = None) -> Lap:
        """Registra una marca al final (O(1)) y mueve el cursor a ella."""
        if not self.running:
            raise LineError("Start the stopwatch before recording a lap")
        split = self.elapsed_ms
        last = self.laps.tail
        if last is not None and split <= last.data.split_ms:
            split = last.data.split_ms + 1  # dos toques en el mismo milisegundo
        lap = Lap(self._new_id(), split, element_id, self.cycle)
        node = self.laps.append(lap.id, lap)
        self.laps.cursor = node
        return lap

    def _bounds(self, node: Node[Lap]) -> tuple:
        """Límites válidos (exclusivos) para la lectura de ``node``."""
        low = node.prev.data.split_ms if node.prev is not None else 0
        if node.next is not None:
            high = node.next.data.split_ms
        else:
            high = self.elapsed_ms + 1  # la última marca no puede superar el reloj
        return low, high

    def adjust_split(self, lap_id: str, split_ms: Any) -> Lap:
        """Corrige la lectura de una marca entre sus vecinas. O(1)."""
        node = self.laps.get_node(lap_id)
        value = clean_time_ms(split_ms, "Split time")
        low, high = self._bounds(node)
        if not (low < value < high):
            raise LineError(
                f"Split must be between {low / 1000:.2f}s and {high / 1000:.2f}s (exclusive) "
                "to keep the sequence ordered"
            )
        node.data.split_ms = value
        return node.data

    def set_duration(self, lap_id: str, duration_ms: Any) -> Lap:
        """Corrige la duración de una marca moviendo su lectura. O(1).

        El sucesor absorbe la diferencia (es lo que ocurre cuando el analista
        marcó tarde o temprano el fin de un elemento).
        """
        node = self.laps.get_node(lap_id)
        duration = clean_time_ms(duration_ms, "Duration")
        start = node.prev.data.split_ms if node.prev is not None else 0
        return self.adjust_split(lap_id, start + duration)

    def delete_mark(self, lap_id: str) -> Lap:
        """Elimina una marca; su intervalo se fusiona con el del sucesor. O(1)."""
        return self.laps.remove(lap_id)

    def insert_mark(self, before_lap_id: str, at_ms: Any, element_id: Optional[str] = None) -> Lap:
        """Inserta una marca olvidada antes de ``before_lap_id``. O(1)."""
        ref = self.laps.get_node(before_lap_id)
        value = clean_time_ms(at_ms, "Split time")
        low = ref.prev.data.split_ms if ref.prev is not None else 0
        if not (low < value < ref.data.split_ms):
            raise LineError(
                f"The missed mark must be between {low / 1000:.2f}s and "
                f"{ref.data.split_ms / 1000:.2f}s"
            )
        lap = Lap(self._new_id(), value, element_id, ref.data.cycle)
        node = self.laps.insert_before(before_lap_id, lap.id, lap)
        self.laps.cursor = node
        return lap

    def assign(self, lap_id: str, element_id: Optional[str]) -> Lap:
        lap = self.laps.get(lap_id)
        lap.element_id = element_id
        return lap

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------
    def set_cursor(self, lap_id: str) -> Lap:
        return self.laps.set_cursor(lap_id).data

    def cursor_next(self) -> Optional[Lap]:
        node, _ = self.laps.cursor_next()
        return node.data if node is not None else None

    def cursor_prev(self) -> Optional[Lap]:
        node, _ = self.laps.cursor_prev()
        return node.data if node is not None else None

    def cursor_first(self) -> Optional[Lap]:
        node = self.laps.cursor_to_head()
        return node.data if node is not None else None

    def cursor_last(self) -> Optional[Lap]:
        node = self.laps.cursor_to_tail()
        return node.data if node is not None else None

    # ------------------------------------------------------------------
    # Estadística
    # ------------------------------------------------------------------
    def durations_for(self, element_id: str) -> List[int]:
        """Duraciones observadas para un elemento (recorrido O(L))."""
        return [
            self.duration_of(node)
            for node in self.laps.iter_nodes()
            if node.data.element_id == element_id
        ]

    def stats(self) -> Dict[str, Dict[str, float]]:
        """Estadísticos por elemento: n, media, desviación, mínimo y máximo."""
        buckets: Dict[str, List[int]] = {}
        for node in self.laps.iter_nodes():
            element = node.data.element_id
            if element:
                buckets.setdefault(element, []).append(self.duration_of(node))
        return {element: describe(values) for element, values in buckets.items()}

    # ------------------------------------------------------------------
    # Vista
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        laps = []
        for number, node in enumerate(self.laps.iter_nodes(), start=1):
            lap = node.data
            laps.append(
                {
                    "id": lap.id,
                    "number": number,
                    "cycle": lap.cycle,
                    "split_ms": lap.split_ms,
                    "duration_ms": self.duration_of(node),
                    "element_id": lap.element_id,
                    "prev": node.prev.key if node.prev is not None else None,
                    "next": node.next.key if node.next is not None else None,
                }
            )
        cursor = self.laps.cursor
        return {
            "running": self.running,
            "elapsed_ms": self.elapsed_ms,
            "cycle": self.cycle,
            "cursor": cursor.key if cursor is not None else None,
            "laps": laps,
        }


def describe(values: List[int]) -> Dict[str, float]:
    n = len(values)
    if n == 0:
        return {"n": 0, "mean_ms": 0.0, "std_ms": 0.0, "min_ms": 0, "max_ms": 0}
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    return {
        "n": n,
        "mean_ms": round(mean, 1),
        "std_ms": round(math.sqrt(variance), 1),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def standard_time(mean_ms: float, rating_pct: float, allowance_pct: float) -> Dict[str, float]:
    """Tiempo normal y estándar a partir del tiempo observado promedio.

    * Tiempo normal   = TO × (valoración / 100)
    * Tiempo estándar = TN × (1 + suplementos / 100)
    """
    if rating_pct <= 0 or rating_pct > 200:
        raise LineError("Performance rating must be between 1% and 200%")
    if allowance_pct < 0 or allowance_pct > 100:
        raise LineError("Allowances must be between 0% and 100%")
    normal = mean_ms * rating_pct / 100
    standard = normal * (1 + allowance_pct / 100)
    return {"normal_ms": round(normal, 1), "standard_ms": round(standard, 1)}
