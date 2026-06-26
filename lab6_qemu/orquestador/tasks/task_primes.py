#!/usr/bin/env python3
"""Tarea de paridad con la demo original: contar numeros primos en un rango.

Sirve como tarea de validacion del orquestador: su resultado es verificable
contra un valor conocido, lo que permite confiar en el pipeline (split/run/merge,
despliegue, cola dinamica, reintentos) antes de probar tareas nuevas.

CONTRATO DE TAREA (igual para las 4 tareas del orquestador)
-----------------------------------------------------------
    split(payload: dict, workers: list[dict]) -> list[dict]
        Divide el problema global en "chunks" autosuficientes. NO asigna chunk_id
        (eso lo hace el coordinador enumerando la lista).

    run(chunk: dict) -> dict
        PURA / idempotente. Recibe UN chunk y devuelve el resultado parcial de
        dominio (sin metadatos de transporte). Solo stdlib. El worker_agent
        envuelve el resultado con ok/chunk_id/seconds.

    merge(results: list[dict]) -> dict
        Combina los parciales (en orden de chunk_id) en el resultado final.

    self_test() -> tuple[dict, dict]   (OPCIONAL)
        Devuelve (chunk_trivial, resultado_esperado). El coordinador envia
        chunk_trivial a run() remoto y exige result == resultado_esperado. Es el
        health-check FUNCIONAL (no basta con que el puerto TCP este abierto).

merge() de esta tarea = SUMA escalar (reduccion de un contador).
"""

import math


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    limit = int(math.isqrt(n))
    for d in range(3, limit + 1, 2):
        if n % d == 0:
            return False
    return True


def split_range(start: int, end: int, parts: int):
    """Divide [start, end] en `parts` rangos balanceados (reparto del remainder)."""
    if end < start:
        return []
    total = end - start + 1
    parts = max(1, min(parts, total))
    base, remainder = divmod(total, parts)
    ranges = []
    current = start
    for i in range(parts):
        size = base + (1 if i < remainder else 0)
        r_start = current
        r_end = current + size - 1
        ranges.append((r_start, r_end))
        current = r_end + 1
    return ranges


def split(payload: dict, workers: list) -> list:
    upper = int(payload["upper"])
    n_chunks = int(payload.get("n_chunks", max(1, len(workers))))
    return [{"start": s, "end": e} for s, e in split_range(2, upper, n_chunks)]


def run(chunk: dict) -> dict:
    start = int(chunk["start"])
    end = int(chunk["end"])
    count = 0
    for n in range(start, end + 1):
        if is_prime(n):
            count += 1
    return {"prime_count": count}


def merge(results: list) -> dict:
    total = sum(r["prime_count"] for r in results)
    return {"total_primes": total}


def self_test():
    # Primos entre 2 y 10 = {2, 3, 5, 7} -> 4. Mismo health-check del coordinator_aio.
    return {"start": 2, "end": 10}, {"prime_count": 4}
