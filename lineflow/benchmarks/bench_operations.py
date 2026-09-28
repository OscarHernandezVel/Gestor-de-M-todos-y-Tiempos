#!/usr/bin/env python3
"""
Benchmark: mover un elemento en la lista doblemente enlazada vs. en una
lista de Python (arreglo dinámico).

Uso:  python benchmarks/bench_operations.py

La lista doble reubica el nodo reescribiendo 8 punteros (O(1)). La lista de
Python debe localizar el elemento (index, O(n)) y desplazar los demás en
``pop``/``insert`` (O(n)). El índice id->nodo permite a la lista doble
localizar el nodo en O(1).
"""
from __future__ import annotations

import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lineflow.core import POINTER_STATS, DoublyLinkedList  # noqa: E402
from lineflow.domain import AssemblyLine  # noqa: E402

REPEATS = 2000


def bench_dll(size: int, rng: random.Random) -> tuple:
    dll: DoublyLinkedList[int] = DoublyLinkedList("bench")
    for i in range(size):
        dll.append(i, i)
    pairs = [(rng.randrange(size), rng.randrange(size)) for _ in range(REPEATS)]
    POINTER_STATS.writes = 0
    start = time.perf_counter()
    for key, before in pairs:
        dll.move(key, before)
    elapsed = time.perf_counter() - start
    return elapsed / REPEATS * 1e6, POINTER_STATS.writes / REPEATS


def bench_pylist(size: int, rng: random.Random) -> float:
    items = list(range(size))
    pairs = [(rng.randrange(size), rng.randrange(size)) for _ in range(REPEATS)]
    start = time.perf_counter()
    for key, before in pairs:
        if key == before:
            continue
        items.pop(items.index(key))
        items.insert(items.index(before), key)
    return (time.perf_counter() - start) / REPEATS * 1e6


def bench_line(size: int, rng: random.Random) -> float:
    line = AssemblyLine("bench", 60_000)
    stations = [line.add_station().id for _ in range(10)]
    ids = [line.add_task(stations[i % 10], f"E{i}", 1000).id for i in range(size)]
    moves = [(rng.choice(ids), rng.choice(stations)) for _ in range(REPEATS)]
    start = time.perf_counter()
    for task_id, station_id in moves:
        line.move_task(task_id, station_id)
    return (time.perf_counter() - start) / REPEATS * 1e6


def main() -> None:
    rng = random.Random(42)
    print(f"{'n':>9} | {'DLL move (µs)':>14} | {'ptr/op':>7} | {'list move (µs)':>15} | {'line move_task (µs)':>20}")
    print("-" * 78)
    for size in (1_000, 10_000, 100_000):
        dll_us, writes = bench_dll(size, rng)
        list_us = bench_pylist(size, rng)
        line_us = bench_line(size, rng)
        print(f"{size:>9,} | {dll_us:>14.2f} | {writes:>7.1f} | {list_us:>15.2f} | {line_us:>20.2f}")


if __name__ == "__main__":
    main()
