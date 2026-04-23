"""Worker functions for Lab 03 concurrency benchmarks.

These helpers live in a standalone module so ProcessPoolExecutor can import
them correctly on Windows when the notebook is executed end-to-end.
"""

from __future__ import annotations


def cpu_chunk_digest(task: tuple[int, int, int]) -> tuple[int, int]:
    """Return a deterministic digest for one synthetic CPU-bound chunk."""

    chunk_id, iterations, salt = task
    acc = salt + (chunk_id + 1) * 104_729
    factor = chunk_id + 7

    for i in range(1, iterations + 1):
        acc = (acc + ((i * factor) % 104_729) * ((i % 97) + 3)) % 2_147_483_647

    return chunk_id, acc
