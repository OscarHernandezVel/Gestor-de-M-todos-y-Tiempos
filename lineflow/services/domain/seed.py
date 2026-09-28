"""Datos de demostración: línea de ensamble de un ventilador de escritorio."""
from __future__ import annotations

from .assembly_line import AssemblyLine

# (estación, [(elemento, segundos, therblig), ...])
DEMO_LINE = [
    (
        "Base & Motor",
        [
            ("Grasp base housing from bin", 3.2, "G"),
            ("Position base in fixture", 4.1, "P"),
            ("Insert power cord through base", 6.8, "A"),
            ("Mount motor on base", 9.5, "A"),
            ("Drive 4 motor screws", 11.2, "U"),
        ],
    ),
    (
        "Wiring",
        [
            ("Connect cord to switch", 8.4, "A"),
            ("Crimp terminals", 7.9, "U"),
            ("Search for cable tie", 2.6, "SH"),
            ("Secure wires with cable tie", 5.3, "A"),
            ("Continuity test", 12.0, "I"),
        ],
    ),
    (
        "Guard & Blade",
        [
            ("Fit rear guard", 6.2, "P"),
            ("Install blade on shaft", 7.1, "A"),
            ("Tighten spinner cap", 4.5, "U"),
            ("Hold guard while aligning clips", 3.4, "H"),
            ("Clip front guard", 9.8, "A"),
        ],
    ),
    (
        "Test & Pack",
        [
            ("Functional run test", 18.5, "I"),
            ("Apply rating label", 4.2, "A"),
            ("Wait for tester reset", 6.0, "UD"),
            ("Box and seal", 14.6, "A"),
            ("Move box to pallet", 5.5, "TL"),
        ],
    ),
]

DEMO_TAKT_S = 45.0  # 7.5 h disponibles (27 000 s) / 600 unidades


def build_demo_line() -> AssemblyLine:
    line = AssemblyLine("Desk Fan DF-16 final assembly", int(DEMO_TAKT_S * 1000))
    for station_name, elements in DEMO_LINE:
        station = line.add_station(station_name)
        for name, seconds, therblig in elements:
            line.add_task(station.id, name, int(round(seconds * 1000)), therblig)
    line.cursor_first()
    return line
