from __future__ import annotations

import argparse
import csv
import gzip
import json
import statistics
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path


Agg = dict[tuple[str, str], list[float]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark de pipeline concurrente para logs gzip.")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--batch-lines", type=int, default=25_000)
    return parser.parse_args()


def window_5m(ts: str) -> str:
    minute = int(ts[14:16])
    rounded = (minute // 5) * 5
    return f"{ts[:14]}{rounded:02d}:00Z"


def update_agg(agg: Agg, record: dict[str, object]) -> None:
    latency = float(record["latency_ms"])
    status = int(record["status_code"])
    if latency < 0:
        return

    key = (window_5m(str(record["timestamp"])), str(record["endpoint"]))
    bucket = agg[key]
    bucket[0] += 1
    bucket[1] += latency
    bucket[2] = max(bucket[2], latency)
    if status >= 500:
        bucket[3] += 1


def process_lines(lines: list[str]) -> tuple[Agg, int]:
    agg: Agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    parsed = 0
    for line in lines:
        try:
            record = json.loads(line)
            update_agg(agg, record)
            parsed += 1
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return dict(agg), parsed


def process_file(path: Path) -> tuple[Agg, int]:
    agg: Agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    parsed = 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
                update_agg(agg, record)
                parsed += 1
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return dict(agg), parsed


def merge_into(target: Agg, partial: Agg) -> None:
    for key, values in partial.items():
        bucket = target[key]
        bucket[0] += values[0]
        bucket[1] += values[1]
        bucket[2] = max(bucket[2], values[2])
        bucket[3] += values[3]


def run_sequential(paths: list[Path], workers: int, batch_lines: int) -> tuple[Agg, int]:
    del workers, batch_lines
    agg: Agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    total = 0
    for path in paths:
        partial, parsed = process_file(path)
        merge_into(agg, partial)
        total += parsed
    return dict(agg), total


def run_threads(paths: list[Path], workers: int, batch_lines: int) -> tuple[Agg, int]:
    del batch_lines
    agg: Agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    total = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for partial, parsed in pool.map(process_file, paths):
            merge_into(agg, partial)
            total += parsed
    return dict(agg), total


def run_processes(paths: list[Path], workers: int, batch_lines: int) -> tuple[Agg, int]:
    del batch_lines
    agg: Agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    total = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for partial, parsed in pool.map(process_file, paths, chunksize=1):
            merge_into(agg, partial)
            total += parsed
    return dict(agg), total


def batched_lines(paths: list[Path], batch_lines: int):
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            batch: list[str] = []
            for line in handle:
                batch.append(line)
                if len(batch) >= batch_lines:
                    yield batch
                    batch = []
            if batch:
                yield batch


def run_hybrid(paths: list[Path], workers: int, batch_lines: int) -> tuple[Agg, int]:
    agg: Agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    total = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for partial, parsed in pool.map(process_lines, batched_lines(paths, batch_lines), chunksize=1):
            merge_into(agg, partial)
            total += parsed
    return dict(agg), total


def signature(agg: Agg) -> tuple[int, int, int]:
    requests = int(sum(v[0] for v in agg.values()))
    errors = int(sum(v[3] for v in agg.values()))
    groups = len(agg)
    return requests, errors, groups


def timed(fn, paths: list[Path], workers: int, batch_lines: int) -> tuple[float, tuple[int, int, int]]:
    t0 = time.perf_counter()
    agg, _ = fn(paths, workers, batch_lines)
    elapsed = time.perf_counter() - t0
    return elapsed, signature(agg)


def main() -> None:
    args = parse_args()
    paths = sorted(args.input_dir.glob("*.jsonl.gz"))
    if not paths:
        raise SystemExit(f"No se encontraron logs .jsonl.gz en {args.input_dir}")

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    strategies = [
        ("secuencial", run_sequential),
        ("thread_pool", run_threads),
        ("process_pool", run_processes),
        ("hibrido_batches", run_hybrid),
    ]

    rows: list[dict[str, object]] = []
    baseline_mean: float | None = None
    baseline_signature: tuple[int, int, int] | None = None

    for name, fn in strategies:
        worker_values = [1] if name == "secuencial" else args.workers
        for workers in worker_values:
            for _ in range(args.warmups):
                timed(fn, paths, workers, args.batch_lines)

            elapsed_values = []
            sig = None
            for _ in range(args.repeats):
                elapsed, sig = timed(fn, paths, workers, args.batch_lines)
                elapsed_values.append(elapsed)

            mean_s = statistics.mean(elapsed_values)
            stdev_s = statistics.stdev(elapsed_values) if len(elapsed_values) > 1 else 0.0
            if baseline_mean is None:
                baseline_mean = mean_s
                baseline_signature = sig

            if sig != baseline_signature:
                raise RuntimeError(f"La estrategia {name} con {workers} workers no coincide con la linea base")

            speedup = baseline_mean / mean_s
            efficiency = speedup / workers
            requests = sig[0] if sig else 0
            rows.append(
                {
                    "strategy": name,
                    "workers": workers,
                    "repeats": args.repeats,
                    "mean_s": f"{mean_s:.6f}",
                    "stdev_s": f"{stdev_s:.6f}",
                    "speedup": f"{speedup:.6f}",
                    "efficiency": f"{efficiency:.6f}",
                    "requests": requests,
                    "groups": sig[2] if sig else 0,
                    "throughput_req_s": f"{requests / mean_s:.2f}",
                }
            )

    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Benchmark escrito en {args.out_csv}")


if __name__ == "__main__":
    main()
