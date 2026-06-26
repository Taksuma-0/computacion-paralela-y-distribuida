from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
ANEXOS = ROOT / "anexos_benchmark"
FIGURAS = ROOT / "informe_latex" / "figuras"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str) -> float:
    return float(value.replace(",", "."))


def save_current(name: str) -> None:
    FIGURAS.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(FIGURAS / name, dpi=180)
    plt.close()


def plot_openmp() -> None:
    rows = read_csv(ANEXOS / "openmp_normalizacion_50m.csv")
    threads = [int(row["threads"]) for row in rows]
    speedup = [as_float(row["speedup"]) for row in rows]
    efficiency = [as_float(row["efficiency"]) for row in rows]

    plt.figure(figsize=(7.2, 4.0))
    plt.plot(threads, speedup, marker="o", linewidth=2.2, label="Speedup")
    plt.plot(threads, efficiency, marker="s", linewidth=2.2, label="Eficiencia")
    plt.axhline(1.0, color="#777777", linewidth=0.9, linestyle="--")
    plt.xticks(threads)
    plt.xlabel("Hilos OpenMP")
    plt.ylabel("Valor relativo")
    plt.title("Normalizacion OpenMP 50M x 16: speedup y eficiencia")
    plt.grid(axis="y", alpha=0.25)
    plt.legend()
    save_current("openmp_speedup_eficiencia.png")


def plot_logs() -> None:
    rows = read_csv(ANEXOS / "pipeline_logs_16mib.csv")
    selected = [
        row
        for row in rows
        if (row["strategy"], row["workers"])
        in {
            ("secuencial", "1"),
            ("thread_pool", "4"),
            ("process_pool", "4"),
            ("process_pool", "8"),
            ("hibrido_batches", "4"),
            ("hibrido_batches", "8"),
        }
    ]
    labels = [
        "Secuencial\n1",
        "ThreadPool\n4",
        "ProcessPool\n4",
        "ProcessPool\n8",
        "Hibrido\n4",
        "Hibrido\n8",
    ]
    order = [
        ("secuencial", "1"),
        ("thread_pool", "4"),
        ("process_pool", "4"),
        ("process_pool", "8"),
        ("hibrido_batches", "4"),
        ("hibrido_batches", "8"),
    ]
    by_key = {(row["strategy"], row["workers"]): row for row in selected}
    times = [as_float(by_key[key]["mean_s"]) for key in order]

    plt.figure(figsize=(7.4, 4.1))
    bars = plt.bar(labels, times, color=["#5B6C8F", "#8B6F47", "#2F7D61", "#2F7D61", "#8A4F7D", "#8A4F7D"])
    plt.ylabel("Tiempo medio (s)")
    plt.title("Pipeline de logs: tiempo medio por estrategia")
    plt.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, times):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.18, f"{value:.2f}", ha="center", fontsize=8)
    save_current("logs_tiempo_estrategia.png")


def plot_embeddings() -> None:
    rows = read_csv(ANEXOS / "embeddings_topk_20000.csv")
    workers = [int(row["workers"]) for row in rows]
    times = [as_float(row["mean_s"]) for row in rows]
    speedup = [as_float(row["speedup"]) for row in rows]

    fig, ax1 = plt.subplots(figsize=(7.2, 4.0))
    ax1.bar([w - 0.12 for w in workers], times, width=0.24, color="#4C6A92", label="Tiempo")
    ax1.set_xlabel("Workers")
    ax1.set_ylabel("Tiempo total (s)", color="#4C6A92")
    ax1.tick_params(axis="y", labelcolor="#4C6A92")
    ax1.set_xticks(workers)
    ax1.grid(axis="y", alpha=0.22)

    ax2 = ax1.twinx()
    ax2.plot(workers, speedup, marker="o", color="#9A4D3F", linewidth=2.2, label="Speedup")
    ax2.set_ylabel("Speedup", color="#9A4D3F")
    ax2.tick_params(axis="y", labelcolor="#9A4D3F")
    ax2.set_ylim(0, max(speedup) * 1.25)

    plt.title("Embeddings: top-10 exacto por bloques")
    fig.tight_layout()
    fig.savefig(FIGURAS / "embeddings_tiempo_speedup.png", dpi=180)
    plt.close(fig)


def plot_pipeline_diagram() -> None:
    stages = [
        "Lectura\n.gz",
        "Descompresion",
        "Parseo\nJSON",
        "Limpieza",
        "Agregacion\nparcial",
        "Reduccion\nfinal",
    ]
    colors = ["#5B6C8F", "#5B6C8F", "#8B6F47", "#8B6F47", "#2F7D61", "#2F7D61"]

    fig, ax = plt.subplots(figsize=(8.2, 2.4))
    ax.axis("off")
    for i, (stage, color) in enumerate(zip(stages, colors)):
        x = i * 1.55
        rect = plt.Rectangle((x, 0.55), 1.15, 0.72, facecolor=color, edgecolor="black", linewidth=0.8, alpha=0.92)
        ax.add_patch(rect)
        ax.text(x + 0.575, 0.91, stage, ha="center", va="center", color="white", fontsize=9)
        if i < len(stages) - 1:
            ax.annotate("", xy=(x + 1.42, 0.91), xytext=(x + 1.17, 0.91), arrowprops={"arrowstyle": "->", "lw": 1.4})
    ax.text(0.15, 0.2, "I/O-bound", color="#5B6C8F", fontsize=9, weight="bold")
    ax.text(3.0, 0.2, "CPU-bound / GIL sensible", color="#8B6F47", fontsize=9, weight="bold")
    ax.text(6.0, 0.2, "Combinacion controlada", color="#2F7D61", fontsize=9, weight="bold")
    ax.set_xlim(-0.2, 8.95)
    ax.set_ylim(0.0, 1.65)
    fig.tight_layout()
    fig.savefig(FIGURAS / "pipeline_logs_diagrama.png", dpi=180)
    plt.close(fig)


def main() -> None:
    plot_openmp()
    plot_logs()
    plot_embeddings()
    plot_pipeline_diagram()
    print(f"Figuras generadas en {FIGURAS}")


if __name__ == "__main__":
    main()
