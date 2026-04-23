"""Worker functions for Lab 02 process-based experiments.

These functions live in a standalone module so they can be imported by
ProcessPoolExecutor on Windows when the notebook is executed end-to-end.
"""

from __future__ import annotations

import math
import random


def monte_carlo_pi_chunk(task: tuple[int, int]) -> int:
    """Return the count of points inside the unit circle for one chunk."""

    seed, samples = task
    rng = random.Random(seed)
    inside = 0

    for _ in range(samples):
        x = rng.random()
        y = rng.random()
        if x * x + y * y <= 1.0:
            inside += 1

    return inside


def extract_batch_profile(task: tuple[int, int, int]) -> tuple[int, float, float]:
    """Simulate feature extraction over an independent batch.

    Returns:
        batch_id, spectral_score, volatility_score
    """

    batch_id, seed, observations = task
    rng = random.Random(seed)
    running_sum = 0.0
    running_sq = 0.0
    spectral_score = 0.0
    volatility_score = 0.0

    for idx in range(1, observations + 1):
        x = rng.random()
        y = rng.random()
        z = rng.random()

        signal = (
            math.sqrt(x + 1e-12) * math.log1p(y)
            + math.sin(z)
            + math.cos((x + y) * (z + 1.0))
        )

        running_sum += signal
        running_sq += signal * signal

        if idx % 4000 == 0:
            block_mean = running_sum / 4000.0
            block_var = max(running_sq / 4000.0 - block_mean * block_mean, 0.0)
            spectral_score += block_mean * block_mean + math.sqrt(abs(block_mean) + 1e-12)
            volatility_score += math.sqrt(block_var + 1e-12)
            running_sum = 0.0
            running_sq = 0.0

    return batch_id, spectral_score, volatility_score
