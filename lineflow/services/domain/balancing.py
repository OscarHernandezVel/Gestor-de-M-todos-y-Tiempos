from __future__ import annotations

import math
from typing import Any, Dict, List

from .assembly_line import AssemblyLine


def compute_metrics(line: AssemblyLine) -> Dict[str, Any]:
    stations = list(line.stations)
    loads: List[int] = [st.load_ms for st in stations]
    n = len(stations)
    total = sum(loads)
    takt = line.takt_ms
    cycle = max(loads) if loads else 0

    efficiency = (total / (n * cycle) * 100) if n and cycle else 0.0
    takt_efficiency = (total / (n * takt) * 100) if n and takt else 0.0
    smoothness = math.sqrt(sum((cycle - load) ** 2 for load in loads)) if loads else 0.0
    bottleneck = None
    if stations and cycle > 0:
        bottleneck = stations[loads.index(cycle)].id

    per_station = []
    for st in stations:
        per_station.append(
            {
                "id": st.id,
                "name": st.name,
                "load_ms": st.load_ms,
                "count": st.count,
                "idle_ms": cycle - st.load_ms,
                "utilization_pct": round(st.load_ms / takt * 100, 1) if takt else 0.0,
                "over_takt": st.load_ms > takt,
            }
        )

    return {
        "takt_ms": takt,
        "cycle_ms": cycle,
        "total_work_ms": total,
        "stations": n,
        "elements": line.task_count,
        "efficiency_pct": round(efficiency, 1),
        "balance_delay_pct": round(100 - efficiency, 1) if n and cycle else 0.0,
        "takt_efficiency_pct": round(takt_efficiency, 1),
        "smoothness_index_s": round(smoothness / 1000, 2),
        "min_stations": math.ceil(total / takt) if takt and total else 0,
        "throughput_per_hour": round(3_600_000 / cycle, 1) if cycle else 0.0,
        "bottleneck_id": bottleneck,
        "over_takt_count": sum(1 for s in per_station if s["over_takt"]),
        "per_station": per_station,
    }
