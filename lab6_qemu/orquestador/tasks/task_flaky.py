#!/usr/bin/env python3
"""TAREA DE PRUEBA (no es entregable): falla de forma determinista en los chunks
indicados por payload["fail_chunks"], para verificar reintentos/estados (V5).
Borrar tras las pruebas de robustez."""


def split(payload, workers):
    n = int(payload.get("n_chunks", 6))
    fail = set(payload.get("fail_chunks", []))
    return [{"i": i, "fail": i in fail} for i in range(n)]


def run(chunk):
    if chunk.get("fail"):
        raise ValueError(f"fallo deterministico forzado en chunk i={chunk['i']}")
    return {"i": chunk["i"], "ok": 1}


def merge(results):
    return {"sum": sum(r["ok"] for r in results), "ids": sorted(r["i"] for r in results)}


def self_test():
    chunk = {"i": -1, "fail": False}
    return chunk, run(chunk)
