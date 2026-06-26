#!/usr/bin/env python3
"""Tarea: ETL distribuido. Cada worker FABRICA su propia particion de registros
crudos (por semilla), la limpia y la transforma, y devuelve agregados + una
muestra acotada. Es el patron "cada nodo hace lo suyo".

merge() de esta tarea = CONSOLIDACION (union de muestras + agregados globales).
Forma deliberadamente distinta a wordcount (suma de dicts) y gridsearch (argmax).

Nota de diseno: run() devuelve agregados + una muestra pequena en lugar de TODAS
las filas. En un ETL real las filas transformadas se persistirian por nodo; aqui
el coordinador consolida resumen + muestra para la evidencia (mantiene los
mensajes JSON livianos en VMs de 256 MB).
"""

import random


def derive_seed(master: int, idx: int) -> int:
    return (master * 1000003 + idx * 2654435761) & 0xFFFFFFFF


def split(payload: dict, workers: list) -> list:
    master = int(payload.get("seed", 2026))
    num_rows = int(payload["num_rows"])
    n = int(payload.get("n_chunks", max(1, len(workers))))
    null_rate = float(payload.get("null_rate", 0.10))
    invalid_rate = float(payload.get("invalid_rate", 0.05))
    sample_k = int(payload.get("sample_k", 3))
    base, extra = divmod(num_rows, n)
    chunks = []
    offset = 0
    for i in range(n):
        rows = base + (1 if i < extra else 0)
        if rows:
            chunks.append({"chunk_seed": derive_seed(master, i), "num_rows": rows,
                           "row_offset": offset, "null_rate": null_rate,
                           "invalid_rate": invalid_rate, "sample_k": sample_k})
            offset += rows
    return chunks


def run(chunk: dict) -> dict:
    rng = random.Random(chunk["chunk_seed"])
    null_rate = chunk["null_rate"]
    invalid_rate = chunk["invalid_rate"]
    k = chunk.get("sample_k", 3)

    n_valid = n_discarded = 0
    sum_amount = 0.0
    min_amount = max_amount = None
    sample = []

    for j in range(chunk["num_rows"]):
        rid = chunk["row_offset"] + j
        # --- extract: registro CRUDO sintetico (con nulos / invalidos) ---
        amount = None if rng.random() < null_rate else rng.uniform(-50.0, 500.0)
        name = f"  Cliente{rid} " if rng.random() > invalid_rate else ""
        # --- clean: descartar nulos, montos negativos y nombres vacios ---
        if amount is None or amount < 0 or not name.strip():
            n_discarded += 1
            continue
        # --- transform: normalizar ---
        amount = round(amount, 2)
        row = {"id": rid, "name": name.strip().upper(), "amount": amount}
        # --- aggregate ---
        n_valid += 1
        sum_amount += amount
        min_amount = amount if min_amount is None or amount < min_amount else min_amount
        max_amount = amount if max_amount is None or amount > max_amount else max_amount
        if len(sample) < k:
            sample.append(row)

    return {"n_valid": n_valid, "n_discarded": n_discarded,
            "sum_amount": round(sum_amount, 2),
            "min_amount": min_amount, "max_amount": max_amount, "sample": sample}


def merge(results: list) -> dict:
    n_valid = sum(r["n_valid"] for r in results)
    n_discarded = sum(r["n_discarded"] for r in results)
    total = round(sum(r["sum_amount"] for r in results), 2)
    mins = [r["min_amount"] for r in results if r["min_amount"] is not None]
    maxs = [r["max_amount"] for r in results if r["max_amount"] is not None]
    consolidated = []
    for r in results:
        consolidated.extend(r["sample"])
    consolidated.sort(key=lambda x: x["id"])
    return {"n_valid": n_valid, "n_discarded": n_discarded,
            "total_amount": total,
            "avg_amount": round(total / n_valid, 4) if n_valid else 0,
            "min_amount": min(mins) if mins else None,
            "max_amount": max(maxs) if maxs else None,
            "consolidated_sample": consolidated[:10],
            "rows_in_sample": min(len(consolidated), 10)}


def self_test():
    chunk = {"chunk_seed": 999, "num_rows": 50, "row_offset": 0,
             "null_rate": 0.10, "invalid_rate": 0.05, "sample_k": 3}
    return chunk, run(chunk)
