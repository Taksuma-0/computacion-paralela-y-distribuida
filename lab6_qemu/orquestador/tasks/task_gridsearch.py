#!/usr/bin/env python3
"""Tarea: busqueda de hiperparametros (grid search) distribuida.

merge() de esta tarea = SELECCION DEL MEJOR por metrica (ARGMAX). Es la tercera
forma de merge, distinta de la suma (wordcount) y la consolidacion (etl): aqui el
coordinador no reduce ni concatena, ELIGE el mejor parcial.

split reparte la grilla de configuraciones (producto cartesiano) entre los chunks;
run evalua cada configuracion con una funcion objetivo determinista (stdlib puro,
sin librerias de ML) y devuelve su mejor local; merge toma el argmax global.
"""

import itertools
import random


def _stable_int(cfg: dict, seed: int) -> int:
    """Entero estable a partir de una config. NO usar hash() (aleatorizado por proceso)."""
    acc = seed & 0xFFFFFFFF
    for key in sorted(cfg):
        acc = (acc * 1000003 + int(round(float(cfg[key]) * 1000))) & 0xFFFFFFFF
    return acc


def objective(cfg: dict, seed: int) -> float:
    """Superficie suave con maximo cerca de lr=0.1, depth=4, reg=0 + ruido determinista."""
    lr = float(cfg.get("lr", 0.0))
    depth = float(cfg.get("depth", 0.0))
    reg = float(cfg.get("reg", 0.0))
    base = -((lr - 0.1) ** 2) * 10.0 - ((depth - 4.0) ** 2) * 0.2 - reg * 1.5
    noise = random.Random(_stable_int(cfg, seed)).uniform(-0.01, 0.01)
    return round(base + noise, 6)


def split(payload: dict, workers: list) -> list:
    grid = payload["grid"]
    seed = int(payload.get("seed", 2026))
    keys = sorted(grid)
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*[grid[k] for k in keys])]
    n = int(payload.get("n_chunks", max(1, len(workers))))
    n = max(1, min(n, len(combos)))
    chunks = []
    for i in range(n):
        part = combos[i::n]   # reparto round-robin de la grilla
        if part:
            chunks.append({"configs": part, "seed": seed})
    return chunks


def run(chunk: dict) -> dict:
    best = None
    for cfg in chunk["configs"]:
        score = objective(cfg, chunk["seed"])
        if best is None or score > best["score"]:
            best = {"config": cfg, "score": score}
    return {"local_best": best, "evaluated": len(chunk["configs"])}


def merge(results: list) -> dict:
    evaluated = sum(r["evaluated"] for r in results)
    candidates = [r["local_best"] for r in results if r.get("local_best")]
    best = max(candidates, key=lambda b: b["score"]) if candidates else None
    return {"best_config": best["config"] if best else None,
            "best_score": best["score"] if best else None,
            "configs_evaluated": evaluated, "partials": len(results)}


def self_test():
    chunk = {"configs": [{"lr": 0.1, "depth": 4, "reg": 0.0},
                         {"lr": 0.5, "depth": 8, "reg": 0.1}],
             "seed": 2026}
    return chunk, run(chunk)
