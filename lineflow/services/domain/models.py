"""
Modelos de dominio: elementos de trabajo (tareas), estaciones y catálogo de
Therbligs (micro-movimientos de Gilbreth).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..core import Node

MAX_NAME_LENGTH = 80
MAX_NOTES_LENGTH = 400
MAX_TIME_MS = 24 * 60 * 60 * 1000  # un día: tope de cordura para un elemento


class LineError(ValueError):
    """Error de reglas de negocio de la línea de ensamble."""


# ---------------------------------------------------------------------------
# Therbligs
# ---------------------------------------------------------------------------
# Clasificación usada en el diagrama Yamazumi:
#   value   -> agrega valor (transforma el producto)
#   support -> necesario pero no agrega valor
#   waste   -> no agrega valor (búsquedas, esperas, retenciones)
THERBLIGS: Dict[str, Dict[str, str]] = {
    "A": {"name": "Assemble", "category": "value"},
    "DA": {"name": "Disassemble", "category": "value"},
    "U": {"name": "Use", "category": "value"},
    "TE": {"name": "Transport Empty (Reach)", "category": "support"},
    "TL": {"name": "Transport Loaded (Move)", "category": "support"},
    "G": {"name": "Grasp", "category": "support"},
    "RL": {"name": "Release Load", "category": "support"},
    "P": {"name": "Position", "category": "support"},
    "PP": {"name": "Pre-position", "category": "support"},
    "I": {"name": "Inspect", "category": "support"},
    "SH": {"name": "Search", "category": "waste"},
    "F": {"name": "Find", "category": "waste"},
    "ST": {"name": "Select", "category": "waste"},
    "H": {"name": "Hold", "category": "waste"},
    "PN": {"name": "Plan", "category": "waste"},
    "UD": {"name": "Unavoidable Delay", "category": "waste"},
    "AD": {"name": "Avoidable Delay", "category": "waste"},
    "R": {"name": "Rest (fatigue)", "category": "waste"},
}

CATEGORIES = {
    "value": "Value-adding",
    "support": "Necessary non-value-adding",
    "waste": "Non-value-adding",
    "none": "Unclassified",
}


def therblig_info(code: str) -> Dict[str, str]:
    info = THERBLIGS.get(code)
    if info is None:
        return {"name": "Unclassified", "category": "none"}
    return info


# ---------------------------------------------------------------------------
# Validaciones
# ---------------------------------------------------------------------------
def clean_name(value: Any, what: str = "Name") -> str:
    if not isinstance(value, str):
        raise LineError(f"{what} must be text")
    text = " ".join(value.split())
    if not text:
        raise LineError(f"{what} cannot be empty")
    if len(text) > MAX_NAME_LENGTH:
        raise LineError(f"{what} cannot exceed {MAX_NAME_LENGTH} characters")
    return text


def clean_notes(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LineError("Notes must be text")
    text = value.strip()
    if len(text) > MAX_NOTES_LENGTH:
        raise LineError(f"Notes cannot exceed {MAX_NOTES_LENGTH} characters")
    return text


def clean_time_ms(value: Any, what: str = "Time") -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LineError(f"{what} must be a number")
    if value != value:  # NaN
        raise LineError(f"{what} must be a number")
    ms = int(round(value))
    if ms < 0:
        raise LineError(f"{what} cannot be negative")
    if ms > MAX_TIME_MS:
        raise LineError(f"{what} is too large")
    return ms


def clean_therblig(value: Any) -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise LineError("Therblig code must be text")
    code = value.strip().upper()
    if code and code not in THERBLIGS:
        raise LineError(f"Unknown therblig code '{value}'")
    return code


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------
@dataclass
class WorkElement:
    """Elemento de trabajo (paso operativo) cronometrable.

    El tiempo se guarda en milisegundos enteros para que las cargas de las
    estaciones se sumen y resten sin errores de redondeo.
    """

    id: str
    name: str
    time_ms: int
    station_id: str
    therblig: str = ""
    notes: str = ""

    @property
    def category(self) -> str:
        return therblig_info(self.therblig)["category"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "time_ms": self.time_ms,
            "therblig": self.therblig,
            "notes": self.notes,
        }


@dataclass(eq=False)
class Station:
    """Estación de trabajo.

    Una estación NO guarda una lista propia: sus tareas forman un *segmento
    contiguo* dentro de la única lista doble del proceso. La estación solo
    guarda dos punteros a los extremos de su segmento (``first`` y ``last``),
    la cantidad de nodos y la carga acumulada. Así, la tarea sucesora de la
    última tarea de la estación A es la primera tarea de la estación B.
    """

    id: str
    name: str
    first: Optional[Node[WorkElement]] = field(default=None, repr=False)
    last: Optional[Node[WorkElement]] = field(default=None, repr=False)
    count: int = 0
    load_ms: int = 0

    @property
    def is_empty(self) -> bool:
        return self.first is None

    def iter_nodes(self):
        """Recorre el segmento de la estación siguiendo punteros ``next``. O(k)."""
        node = self.first
        remaining = self.count
        while node is not None and remaining > 0:
            following = node.next
            yield node
            node = following
            remaining -= 1
