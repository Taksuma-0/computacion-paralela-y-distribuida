#!/usr/bin/env python3
"""Genera los graficos de la evaluacion experimental (para el informe) desde la tabla
results/tablas/escalabilidad.csv que produce benchmark_escalabilidad.py.

Salida: results/graficos/speedup.png y results/graficos/eficiencia.png
Uso:    python graficos.py
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEMO = os.path.dirname(os.path.abspath(__file__))
TABLAS = os.path.join(DEMO, "results", "tablas")
GRAF = os.path.join(DEMO, "results", "graficos")
os.makedirs(GRAF, exist_ok=True)

GREEN, BLUE, GREY = "#1f8f4d", "#004E9A", "#888888"


def _leer():
    csv_path = os.path.join(TABLAS, "escalabilidad.csv")
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    start = next(i for i, r in enumerate(rows) if r and r[0] == "p")
    ps, sp, ep = [], [], []
    for r in rows[start + 1:]:
        if not r:
            continue
        ps.append(int(r[0])); sp.append(float(r[4])); ep.append(float(r[5]))
    return ps, sp, ep


def main():
    ps, sp, ep = _leer()

    plt.figure(figsize=(6.2, 4.2))
    plt.plot(ps, sp, "o-", color=GREEN, lw=2, ms=7, label="Speedup medido")
    plt.plot(ps, ps, "--", color=GREY, lw=1.4, label="Ideal (lineal)")
    plt.xlabel("Número de nodos  p"); plt.ylabel("Speedup   Sₚ = T₁ / Tₚ")
    plt.title("Escalabilidad: speedup vs. número de nodos")
    plt.xticks(ps); plt.grid(True, alpha=.3); plt.legend()
    plt.tight_layout(); plt.savefig(os.path.join(GRAF, "speedup.png"), dpi=140); plt.close()

    plt.figure(figsize=(6.2, 4.2))
    plt.plot(ps, ep, "s-", color=BLUE, lw=2, ms=7, label="Eficiencia medida")
    plt.axhline(1.0, ls="--", color=GREY, lw=1.4, label="Ideal (1.0)")
    plt.xlabel("Número de nodos  p"); plt.ylabel("Eficiencia   Eₚ = Sₚ / p")
    plt.title("Escalabilidad: eficiencia vs. número de nodos")
    plt.xticks(ps); plt.ylim(0, 1.25); plt.grid(True, alpha=.3); plt.legend()
    plt.tight_layout(); plt.savefig(os.path.join(GRAF, "eficiencia.png"), dpi=140); plt.close()

    print("Graficos: results/graficos/speedup.png  y  eficiencia.png")


if __name__ == "__main__":
    main()
