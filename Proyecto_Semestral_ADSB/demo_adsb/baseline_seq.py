#!/usr/bin/env python3
"""Baseline secuencial: ejecuta split -> run(todos los chunks) -> merge en UN solo
proceso, sin red ni SSH. Es el denominador honesto del speedup:

    speedup = elapsed_baseline (este script) / elapsed_distribuido (coordinator_generic)

Uso:
    python3 baseline_seq.py --task tasks/task_primes.py --payload '{"upper":300000,"n_chunks":24}'
"""

import argparse
import importlib.util
import json
import os
import time


def load_task_module(task_path: str):
    """Importa dinamicamente un modulo de tarea y valida el contrato."""
    if not os.path.isfile(task_path):
        raise FileNotFoundError(f"No existe el archivo de tarea: {task_path}")
    name = os.path.splitext(os.path.basename(task_path))[0]
    spec = importlib.util.spec_from_file_location(name, task_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for fn in ("split", "run", "merge"):
        if not hasattr(module, fn) or not callable(getattr(module, fn)):
            raise AttributeError(f"La tarea '{name}' no define la funcion requerida: {fn}()")
    return module, name


def run_baseline(task_path: str, payload: dict) -> dict:
    """Ejecuta split -> run(todos los chunks) -> merge en UN proceso (sin red).
    Entrada programatica que usa el TUI como denominador del speedup.
    Devuelve {mode, task_name, payload, n_chunks, elapsed, result}."""
    task, task_name = load_task_module(task_path)
    chunks = task.split(payload, [{"name": "baseline-local"}])
    t0 = time.perf_counter()
    partials = [task.run(chunk) for chunk in chunks]
    elapsed = time.perf_counter() - t0
    final = task.merge(partials)
    return {
        "mode": "baseline_seq",
        "task_name": task_name,
        "payload": payload,
        "n_chunks": len(chunks),
        "elapsed": round(elapsed, 4),
        "result": final,
    }


def main():
    parser = argparse.ArgumentParser(description="Baseline secuencial para medir speedup.")
    parser.add_argument("--task", required=True, help="Ruta al modulo de tarea (tasks/task_X.py)")
    parser.add_argument("--payload", default="{}", help="Parametros globales en JSON")
    parser.add_argument("--out", default=None, help="Opcional: ruta para guardar el JSON del baseline")
    args = parser.parse_args()

    payload = json.loads(args.payload)
    record = run_baseline(args.task, payload)

    print(f"Baseline secuencial: {record['task_name']}")
    print(f"  payload     : {payload}")
    print(f"  n_chunks    : {record['n_chunks']}")
    print(f"  elapsed (s) : {record['elapsed']:.4f}   <- usar como elapsed_baseline para speedup")
    print(f"  resultado   : {json.dumps(record['result'], ensure_ascii=False, allow_nan=False)}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(record, fh, ensure_ascii=False, allow_nan=False, indent=2)
        print(f"  guardado en : {args.out}")


if __name__ == "__main__":
    main()
