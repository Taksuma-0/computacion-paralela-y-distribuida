#!/usr/bin/env python3
"""Tarea: conteo de palabras sobre documentos sinteticos generados por semilla.

merge() de esta tarea = SUMA DE DICCIONARIOS (reduccion clave-valor).

Datos por semilla: el chunk no transporta texto; lleva una semilla y cuantos
documentos generar. run() reconstruye exactamente esos documentos con
random.Random(seed) (Mersenne Twister es determinista e identico entre maquinas),
de modo que el mismo chunk produce siempre el mismo parcial.
"""

import random

VOCAB = [
    "data", "red", "nodo", "chunk", "worker", "tarea", "merge", "split",
    "cluster", "qemu", "socket", "json", "cola", "paralelo", "proceso",
    "latencia", "ancho", "banda", "primo", "token", "modelo", "metrica",
    "escala", "overhead",
]


def derive_seed(master: int, idx: int) -> int:
    """Semilla por chunk: determinista y disjunta. NO usar hash() (aleatorizado)."""
    return (master * 1000003 + idx * 2654435761) & 0xFFFFFFFF


def split(payload: dict, workers: list) -> list:
    master = int(payload.get("seed", 2026))
    num_docs = int(payload["num_docs"])
    n = int(payload.get("n_chunks", max(1, len(workers))))
    lo, hi = payload.get("doc_len", [20, 60])
    base, extra = divmod(num_docs, n)
    chunks = []
    for i in range(n):
        ndocs = base + (1 if i < extra else 0)
        if ndocs:
            chunks.append({"chunk_seed": derive_seed(master, i),
                           "num_docs": ndocs, "doc_len": [lo, hi]})
    return chunks


def run(chunk: dict) -> dict:
    rng = random.Random(chunk["chunk_seed"])
    lo, hi = chunk["doc_len"]
    vsize = len(VOCAB)
    counts = {}
    for _ in range(chunk["num_docs"]):
        length = rng.randint(lo, hi)
        for _ in range(length):
            word = VOCAB[rng.randrange(vsize)]
            counts[word] = counts.get(word, 0) + 1
    return {"counts": counts, "docs": chunk["num_docs"]}


def merge(results: list) -> dict:
    total = {}
    docs = 0
    for r in results:
        docs += r["docs"]
        for word, c in r["counts"].items():
            total[word] = total.get(word, 0) + c
    top10 = sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {"docs": docs, "distinct": len(total),
            "total_tokens": sum(total.values()), "top10": top10}


def self_test():
    chunk = {"chunk_seed": 12345, "num_docs": 3, "doc_len": [5, 5]}
    return chunk, run(chunk)
