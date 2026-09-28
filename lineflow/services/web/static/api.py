"""
Tabla de rutas de la API REST (JSON).

Cada ruta traduce la petición HTTP a una llamada del servicio. Las rutas no
contienen lógica de negocio: solo leen y validan la forma del cuerpo JSON.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Pattern, Tuple

from ..domain import LineError
from ..service import LineFlowService

Handler = Callable[[LineFlowService, Tuple[str, ...], Dict[str, Any]], Any]

_MISSING = object()


def _opt(body: Dict[str, Any], key: str, kind: type = str) -> Any:
    value = body.get(key)
    if value is None:
        return None
    if kind is str and not isinstance(value, str):
        raise LineError(f"'{key}' must be text")
    return value


def _req(body: Dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise LineError(f"'{key}' is required")
    return value


def _time_ms(body: Dict[str, Any], base: str) -> Any:
    """Acepta ``<base>_ms`` (milisegundos) o ``<base>_s`` (segundos)."""
    if body.get(f"{base}_ms") is not None:
        return body[f"{base}_ms"]
    seconds = body.get(f"{base}_s")
    if seconds is None:
        return None
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        raise LineError(f"'{base}_s' must be a number")
    return seconds * 1000


def _update_task(svc: LineFlowService, p: Tuple[str, ...], b: Dict[str, Any]) -> Any:
    fields = {
        "name": _opt(b, "name"),
        "time_ms": _time_ms(b, "time"),
        "therblig": _opt(b, "therblig"),
        "notes": _opt(b, "notes"),
    }
    return svc.update_task(p[0], **fields)


def _update_lap(svc: LineFlowService, p: Tuple[str, ...], b: Dict[str, Any]) -> Any:
    element = b["element_id"] if "element_id" in b else ...
    if element is not ... and element is not None and not isinstance(element, str):
        raise LineError("'element_id' must be text or null")
    return svc.update_lap(p[0], split_ms=_time_ms(b, "split"), duration_ms=_time_ms(b, "duration"),
                          element_id=element)


def _add_task(svc: LineFlowService, p: Tuple[str, ...], b: Dict[str, Any]) -> Any:
    time_ms = _time_ms(b, "time")
    if time_ms is None:
        raise LineError("'time_ms' or 'time_s' is required")
    return svc.add_task(_req(b, "station_id"), b.get("name"), time_ms, b.get("therblig", ""),
                        b.get("notes", ""), _opt(b, "before_id"))


def _update_line(svc: LineFlowService, p: Tuple[str, ...], b: Dict[str, Any]) -> Any:
    return svc.update_line(_opt(b, "name"), _time_ms(b, "takt"))


ROUTES: List[Tuple[str, Pattern[str], Handler]] = []


def route(method: str, pattern: str, handler: Handler) -> None:
    ROUTES.append((method, re.compile(f"^{pattern}$"), handler))


ID = r"([A-Za-z0-9_\-]{1,64})"

# --- Estado y datos --------------------------------------------------------
route("GET", "/api/state", lambda s, p, b: s.state())
route("GET", "/api/catalog", lambda s, p, b: s.catalog())
route("GET", "/api/export", lambda s, p, b: s.export_data())
route("POST", "/api/import", lambda s, p, b: s.import_data(b))
route("POST", "/api/demo", lambda s, p, b: s.load_demo())
route("PUT", "/api/line", _update_line)

# --- Estaciones -------------------------------------------------------------
route("POST", "/api/stations", lambda s, p, b: s.add_station(_opt(b, "name"), _opt(b, "before_id")))
route("PATCH", f"/api/stations/{ID}", lambda s, p, b: s.rename_station(p[0], b.get("name")))
route("DELETE", f"/api/stations/{ID}", lambda s, p, b: s.remove_station(p[0]))
route("POST", f"/api/stations/{ID}/move", lambda s, p, b: s.move_station(p[0], _opt(b, "before_id")))

# --- Elementos de trabajo ---------------------------------------------------
route("POST", "/api/tasks", _add_task)
route("PATCH", f"/api/tasks/{ID}", _update_task)
route("DELETE", f"/api/tasks/{ID}", lambda s, p, b: s.remove_task(p[0]))
route("POST", f"/api/tasks/{ID}/move",
      lambda s, p, b: s.move_task(p[0], _req(b, "station_id"), _opt(b, "before_id")))
route("POST", f"/api/tasks/{ID}/shift", lambda s, p, b: s.shift_task(p[0], _req(b, "direction")))
route("POST", "/api/cursor", lambda s, p, b: s.move_cursor(_opt(b, "task_id"), _opt(b, "direction")))

# --- Historial y escenario base --------------------------------------------
route("POST", "/api/history/undo", lambda s, p, b: s.undo())
route("POST", "/api/history/redo", lambda s, p, b: s.redo())
route("POST", "/api/history/jump", lambda s, p, b: s.jump_history(_req(b, "entry_id")))
route("POST", "/api/baseline", lambda s, p, b: s.pin_baseline())
route("DELETE", "/api/baseline", lambda s, p, b: s.clear_baseline())

# --- Cronómetro -------------------------------------------------------------
route("POST", "/api/stopwatch/start", lambda s, p, b: s.stopwatch_start())
route("POST", "/api/stopwatch/pause", lambda s, p, b: s.stopwatch_pause())
route("POST", "/api/stopwatch/reset", lambda s, p, b: s.stopwatch_reset())
route("POST", "/api/stopwatch/lap", lambda s, p, b: s.record_lap())
route("PUT", "/api/stopwatch/settings", lambda s, p, b: s.stopwatch_settings(b.get("auto_advance")))
route("POST", "/api/stopwatch/cursor",
      lambda s, p, b: s.lap_cursor(_opt(b, "lap_id"), _opt(b, "direction")))
route("PATCH", f"/api/stopwatch/laps/{ID}", _update_lap)
route("DELETE", f"/api/stopwatch/laps/{ID}", lambda s, p, b: s.delete_lap(p[0]))
route("POST", f"/api/stopwatch/laps/{ID}/split",
      lambda s, p, b: s.insert_lap(p[0], _time_ms(b, "at"), _opt(b, "element_id")))
route("POST", "/api/stopwatch/apply",
      lambda s, p, b: s.apply_standard_time(_req(b, "task_id"), b.get("rating", 100), b.get("allowance", 0)))
