from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


ENDPOINTS = [
    "/api/v1/login",
    "/api/v1/logout",
    "/api/v1/session/refresh",
    "/api/v2/risk/score",
    "/api/v2/files/list",
    "/api/v2/files/download",
    "/api/v2/billing/invoices",
    "/api/v2/admin/audit",
    "/api/v2/search",
    "/api/v2/profile",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera logs comprimidos reproducibles para el benchmark.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--target-mb", type=float, default=64.0, help="Tamano comprimido aproximado en MiB.")
    parser.add_argument("--files", type=int, default=8)
    parser.add_argument("--seed", type=int, default=4128090)
    return parser.parse_args()


def weighted_choice(rng: random.Random, items: list[str]) -> str:
    # Pequena cola larga: endpoints de consulta dominan, administracion aparece poco.
    weights = [13, 4, 9, 8, 12, 7, 3, 1, 15, 10]
    return rng.choices(items, weights=weights, k=1)[0]


def make_record(rng: random.Random, idx: int, start: datetime) -> dict[str, object]:
    endpoint = weighted_choice(rng, ENDPOINTS)
    user_rank = int(rng.paretovariate(1.7)) % 450_000
    user_id = f"u_{user_rank:07d}"
    timestamp = start + timedelta(seconds=idx * rng.randint(1, 4) // 3)

    base_latency = {
        "/api/v1/login": 140,
        "/api/v1/logout": 45,
        "/api/v1/session/refresh": 70,
        "/api/v2/risk/score": 260,
        "/api/v2/files/list": 120,
        "/api/v2/files/download": 420,
        "/api/v2/billing/invoices": 210,
        "/api/v2/admin/audit": 330,
        "/api/v2/search": 180,
        "/api/v2/profile": 95,
    }[endpoint]

    latency = max(1.0, rng.lognormvariate(math.log(base_latency), 0.55))
    if rng.random() < 0.006:
        latency *= rng.uniform(6.0, 18.0)

    status_roll = rng.random()
    if status_roll < 0.925:
        status = 200
    elif status_roll < 0.955:
        status = 304
    elif status_roll < 0.982:
        status = rng.choice([400, 401, 403, 404])
    else:
        status = rng.choice([500, 502, 503, 504])

    return {
        "user_id": user_id,
        "timestamp": timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "endpoint": endpoint,
        "latency_ms": round(latency, 3),
        "status_code": status,
    }


def compressed_size(paths: list[Path]) -> int:
    return sum(path.stat().st_size for path in paths if path.exists())


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    target_bytes = int(args.target_mb * 1024 * 1024)
    paths = [args.out_dir / f"access_{i:02d}.jsonl.gz" for i in range(args.files)]

    handles = [gzip.open(path, "wt", encoding="utf-8", compresslevel=3) for path in paths]
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)

    try:
        idx = 0
        current_size = 0
        while current_size < target_bytes:
            record = make_record(rng, idx, start)
            handles[idx % args.files].write(json.dumps(record, separators=(",", ":")) + "\n")
            idx += 1
            if idx % 100_000 == 0:
                for handle in handles:
                    handle.flush()
                current_size = compressed_size(paths)
    finally:
        for handle in handles:
            handle.close()

    manifest = {
        "seed": args.seed,
        "target_mib": args.target_mb,
        "files": [str(path.name) for path in paths],
        "compressed_bytes": compressed_size(paths),
    }
    (args.out_dir / "manifest_logs.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
