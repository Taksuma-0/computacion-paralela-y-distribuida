from __future__ import annotations

import argparse
import csv
import os
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import shared_memory
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Top-k exacto por bloques para embeddings normalizados.")
    parser.add_argument("--n", type=int, default=20_000)
    parser.add_argument("--dim", type=int, default=128)
    parser.add_argument("--block", type=int, default=1024)
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=4128090)
    return parser.parse_args()


def make_embeddings(n: int, dim: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, size=(n, dim)).astype(np.float32)
    # Un leve sesgo por grupos hace que el top-k no sea completamente uniforme.
    groups = rng.normal(0.0, 0.35, size=(max(8, n // 500), dim)).astype(np.float32)
    for i in range(n):
        x[i] += groups[i % len(groups)]
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.maximum(norms, 1e-12)


def update_topk(current_scores: np.ndarray,
                current_indices: np.ndarray,
                candidate_scores: np.ndarray,
                candidate_indices: np.ndarray,
                topk: int) -> tuple[np.ndarray, np.ndarray]:
    scores = np.concatenate([current_scores, candidate_scores], axis=1)
    indices = np.concatenate([current_indices, candidate_indices], axis=1)
    take = np.argpartition(scores, -topk, axis=1)[:, -topk:]
    row_ids = np.arange(scores.shape[0])[:, None]
    best_scores = scores[row_ids, take]
    best_indices = indices[row_ids, take]
    order = np.argsort(-best_scores, axis=1)
    return best_scores[row_ids, order], best_indices[row_ids, order]


def worker_topk(args: tuple[str, tuple[int, int], str, int, int, int, int]) -> tuple[int, np.ndarray, np.ndarray]:
    shm_name, shape, dtype_name, start, end, block, topk = args
    shm = shared_memory.SharedMemory(name=shm_name)
    try:
        vectors = np.ndarray(shape, dtype=np.dtype(dtype_name), buffer=shm.buf)
        n = shape[0]
        rows = vectors[start:end]
        best_scores = np.full((end - start, topk), -np.inf, dtype=np.float32)
        best_indices = np.full((end - start, topk), -1, dtype=np.int32)

        for j0 in range(0, n, block):
            j1 = min(j0 + block, n)
            sim = rows @ vectors[j0:j1].T
            if j0 <= start < j1 or start <= j0 < end:
                local_i0 = max(start, j0) - start
                local_i1 = min(end, j1) - start
                local_j0 = max(start, j0) - j0
                for offset in range(local_i1 - local_i0):
                    sim[local_i0 + offset, local_j0 + offset] = -np.inf

            take = min(topk, sim.shape[1])
            local_pos = np.argpartition(sim, -take, axis=1)[:, -take:]
            row_ids = np.arange(sim.shape[0])[:, None]
            candidate_scores = sim[row_ids, local_pos]
            candidate_indices = (local_pos + j0).astype(np.int32)
            best_scores, best_indices = update_topk(best_scores, best_indices, candidate_scores, candidate_indices, topk)

        return start, best_scores, best_indices
    finally:
        shm.close()


def exact_topk(vectors: np.ndarray, block: int, topk: int, workers: int) -> tuple[np.ndarray, np.ndarray]:
    n = vectors.shape[0]
    shm = shared_memory.SharedMemory(create=True, size=vectors.nbytes)
    shared = np.ndarray(vectors.shape, dtype=vectors.dtype, buffer=shm.buf)
    shared[:] = vectors

    tasks = []
    row_block = max(block, (n + workers - 1) // workers)
    for start in range(0, n, row_block):
        end = min(start + row_block, n)
        tasks.append((shm.name, vectors.shape, vectors.dtype.name, start, end, block, topk))

    scores = np.empty((n, topk), dtype=np.float32)
    indices = np.empty((n, topk), dtype=np.int32)
    try:
        if workers == 1:
            results = [worker_topk(task) for task in tasks]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(worker_topk, tasks, chunksize=1))

        for start, part_scores, part_indices in results:
            end = start + part_scores.shape[0]
            scores[start:end] = part_scores
            indices[start:end] = part_indices
    finally:
        shm.close()
        shm.unlink()

    return scores, indices


def validate_subset(vectors: np.ndarray, indices: np.ndarray, topk: int, subset: int = 64) -> float:
    subset = min(subset, vectors.shape[0])
    sim = vectors[:subset] @ vectors.T
    for i in range(subset):
        sim[i, i] = -np.inf
    expected = np.argsort(-sim, axis=1)[:, :topk]
    overlap = 0
    for i in range(subset):
        overlap += len(set(expected[i].tolist()) & set(indices[i].tolist()))
    return overlap / float(subset * topk)


def main() -> None:
    args = parse_args()
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    vectors = make_embeddings(args.n, args.dim, args.seed)

    rows = []
    baseline_mean: float | None = None
    expected_recall: float | None = None
    memory_full_gib = (args.n * args.n * 4) / (1024 ** 3)
    memory_blocks_mib = (args.block * args.block * 4) / (1024 ** 2)

    for workers in args.workers:
        elapsed_values = []
        recall_value = 0.0
        for _ in range(args.repeats):
            t0 = time.perf_counter()
            _, indices = exact_topk(vectors, args.block, args.topk, workers)
            elapsed = time.perf_counter() - t0
            recall_value = validate_subset(vectors, indices, args.topk)
            elapsed_values.append(elapsed)

        if expected_recall is None:
            expected_recall = recall_value
        if abs(recall_value - expected_recall) > 1e-9:
            raise RuntimeError("La validacion top-k no coincide entre configuraciones")

        mean_s = statistics.mean(elapsed_values)
        stdev_s = statistics.stdev(elapsed_values) if len(elapsed_values) > 1 else 0.0
        if baseline_mean is None:
            baseline_mean = mean_s
        speedup = baseline_mean / mean_s
        efficiency = speedup / workers
        comparisons = args.n * (args.n - 1)
        rows.append(
            {
                "n": args.n,
                "dim": args.dim,
                "block": args.block,
                "topk": args.topk,
                "workers": workers,
                "repeats": args.repeats,
                "mean_s": f"{mean_s:.6f}",
                "stdev_s": f"{stdev_s:.6f}",
                "speedup": f"{speedup:.6f}",
                "efficiency": f"{efficiency:.6f}",
                "comparisons_per_s": f"{comparisons / mean_s:.2f}",
                "full_matrix_gib": f"{memory_full_gib:.4f}",
                "block_matrix_mib": f"{memory_blocks_mib:.4f}",
                "topk_recall_subset": f"{recall_value:.6f}",
            }
        )

    with args.out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Benchmark escrito en {args.out_csv}")


if __name__ == "__main__":
    main()
