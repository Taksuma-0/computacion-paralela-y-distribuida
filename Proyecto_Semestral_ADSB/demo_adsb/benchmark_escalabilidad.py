#!/usr/bin/env python3
"""Estudio de escalabilidad del orquestador (seccion 6/8/10 de la pauta).

Mide, sobre la tarea con computo denso (sintetica, "datos por semilla"), el speedup
Sp = T1/Tp, la eficiencia Ep = Sp/p y el overhead = p*Tp - T1 para varios numeros de
agentes locales p, con REPETICIONES: reporta media, desviacion y mejor-de-R (como pide
la pauta) + una corrida de calentamiento. Guarda las tablas en results/tablas/.

Speedup medido sobre pares baseline<->distribuido EQUIVALENTES (mismo resultado; la
equivalencia se verifica aparte), cumpliendo la advertencia metodologica de la pauta.
La version con datos REALES es I/O-bound (poco computo) -> no escala: es la leccion de
GRANULARIDAD; por eso este estudio usa la tarea densa.

Uso:
    python benchmark_escalabilidad.py            # p = 1, 2, 4, 8   (R=3)
    python benchmark_escalabilidad.py 1 2 4      # p a medida
"""
import csv
import json
import os
import socket
import statistics
import sys
import time

DEMO = os.path.dirname(os.path.abspath(__file__))
os.chdir(DEMO)
sys.path.insert(0, DEMO)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from tui import app as tuiapp
import baseline_seq
import coordinator_generic

TASK = os.path.join(DEMO, "tasks", "task_adsb.py")
PAYLOAD = {"seed": 7, "num_traj": 60000, "n_chunks": 40, "anomaly_rate": 0.01,
           "top_k": 10, "n_routes": 6, "z_threshold": 4.0}
TABLAS = os.path.join(DEMO, "results", "tablas")
REPS = 3
_NULL = lambda *a, **k: None


def _wait_closed(port, tmo=5.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < tmo:
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return
        time.sleep(0.1)


def _measure_baseline(reps):
    baseline_seq.run_baseline(TASK, PAYLOAD)                       # calentamiento (descartado)
    return [baseline_seq.run_baseline(TASK, PAYLOAD)["elapsed"] for _ in range(reps)]


def _measure_p(p, reps):
    base = 9300 + p * 10
    ports = {f"local{i+1}": base + i for i in range(p)}
    workers = [{"name": n, "task_host": "127.0.0.1", "task_port": pt,
                "ssh_host": "127.0.0.1", "ssh_port": 2221 + i}
               for i, (n, pt) in enumerate(ports.items())]
    wf = os.path.join(DEMO, "results", f"_workers_p{p}.json")
    os.makedirs(os.path.dirname(wf), exist_ok=True)
    json.dump({"ssh_user": "root", "remote_dir": "/root/orchestrator", "workers": workers},
              open(wf, "w", encoding="utf-8"))
    agents = tuiapp.LocalAgents(ports, _NULL, DEMO)
    agents.ensure()
    xs = []
    try:
        coordinator_generic.run_job(TASK, PAYLOAD, wf, deploy=False,
                                    on_event=_NULL, log=_NULL, location="host")   # calentamiento
        for _ in range(reps):
            rec = coordinator_generic.run_job(TASK, PAYLOAD, wf, deploy=False,
                                              on_event=_NULL, log=_NULL, location="host")
            xs.append(rec["elapsed"])
    finally:
        agents.stop()
        for pt in ports.values():
            _wait_closed(pt)
        try:
            os.remove(wf)
        except OSError:
            pass
    return xs


def _stats(xs):
    return statistics.mean(xs), (statistics.pstdev(xs) if len(xs) > 1 else 0.0), min(xs)


def main(ps, reps=REPS):
    os.makedirs(TABLAS, exist_ok=True)
    print(f"Baseline secuencial (T1), {reps} repeticiones + calentamiento...", flush=True)
    T1, T1_std, T1_best = _stats(_measure_baseline(reps))
    print(f"T1 = {T1:.3f}s  (desv {T1_std:.3f}, mejor {T1_best:.3f})  "
          f"[num_traj={PAYLOAD['num_traj']}, n_chunks={PAYLOAD['n_chunks']}]\n", flush=True)

    rows = []
    for p in ps:
        tp, tp_std, tp_best = _stats(_measure_p(p, reps))
        sp, ep, ov = T1 / tp, (T1 / tp) / p, p * tp - T1
        rows.append({"p": p, "tp": tp, "tp_std": tp_std, "tp_best": tp_best,
                     "sp": sp, "ep": ep, "ov": ov})
        print(f"p={p}: Tp={tp:.3f}±{tp_std:.3f}s (mejor {tp_best:.3f})  "
              f"Sp={sp:.2f}  Ep={ep:.2f}  overhead={ov:+.3f}s", flush=True)

    with open(os.path.join(TABLAS, "escalabilidad.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["T1_media_s", f"{T1:.4f}", "T1_desv_s", f"{T1_std:.4f}", "T1_mejor_s", f"{T1_best:.4f}"])
        w.writerow([])
        w.writerow(["p", "Tp_media_s", "Tp_desv_s", "Tp_mejor_s", "Speedup_Sp", "Eficiencia_Ep", "Overhead_s"])
        for r in rows:
            w.writerow([r["p"], f'{r["tp"]:.4f}', f'{r["tp_std"]:.4f}', f'{r["tp_best"]:.4f}',
                        f'{r["sp"]:.3f}', f'{r["ep"]:.3f}', f'{r["ov"]:+.4f}'])

    md = [f"# Estudio de escalabilidad — orquestador distribuido (demo ADS-B)\n",
          f"Tarea `task_adsb` (sintetica, computo denso por datos-por-semilla) · "
          f"num_traj={PAYLOAD['num_traj']} · n_chunks={PAYLOAD['n_chunks']} · "
          f"R={reps} repeticiones + calentamiento · agentes locales en 127.0.0.1.\n",
          f"**T1 (secuencial, media) = {T1:.3f} s**  (desv {T1_std:.3f} · mejor {T1_best:.3f})\n",
          "| p | Tp media (s) | Tp desv (s) | Tp mejor (s) | Speedup Sₚ=T₁/Tₚ | Eficiencia Eₚ=Sₚ/p | Overhead p·Tₚ−T₁ (s) |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['p']} | {r['tp']:.3f} | {r['tp_std']:.3f} | {r['tp_best']:.3f} | "
                  f"{r['sp']:.2f} | {r['ep']:.2f} | {r['ov']:+.3f} |")
    md.append("\n_Nota metodologica:_ el speedup se mide sobre pares baseline↔distribuido que "
              "producen **el mismo resultado** (equivalencia verificada). La version con datos "
              "**reales** (636 vuelos) es I/O-bound y su Sₚ<1 — es la leccion de **granularidad**: "
              "las particiones deben tener suficiente computo para que el reparto valga la pena.\n")
    open(os.path.join(TABLAS, "escalabilidad.md"), "w", encoding="utf-8").write("\n".join(md))
    print(f"\nTablas: results/tablas/escalabilidad.csv  y  .md")


if __name__ == "__main__":
    ps = [int(x) for x in sys.argv[1:]] or [1, 2, 4, 8]
    main(ps)
