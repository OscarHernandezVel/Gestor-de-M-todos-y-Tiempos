"""Capa de dominio: línea de ensamble, cronómetro, balanceo e historial."""
from .assembly_line import AssemblyLine, station_views
from .balancing import compute_metrics
from .history import History, HistoryEntry
from .models import CATEGORIES, THERBLIGS, LineError, Station, WorkElement
from .seed import build_demo_line
from .stopwatch import Lap, Stopwatch, describe, standard_time

__all__ = [
    "AssemblyLine",
    "station_views",
    "compute_metrics",
    "History",
    "HistoryEntry",
    "CATEGORIES",
    "THERBLIGS",
    "LineError",
    "Station",
    "WorkElement",
    "build_demo_line",
    "Lap",
    "Stopwatch",
    "describe",
    "standard_time",
]
