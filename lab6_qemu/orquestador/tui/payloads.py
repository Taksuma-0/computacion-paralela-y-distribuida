"""Presets de tareas y payloads para el launcher (los del README)."""

# (clave, etiqueta, archivo de tarea, payload JSON por defecto)
TASKS = [
    ("primes", "Primos (suma escalar)", "tasks/task_primes.py",
     '{"upper": 300000, "n_chunks": 40}'),
    ("wordcount", "WordCount (suma de dicts)", "tasks/task_wordcount.py",
     '{"seed": 2026, "num_docs": 8000, "n_chunks": 40}'),
    ("etl", "ETL distribuido (consolidacion)", "tasks/task_etl.py",
     '{"seed": 7, "num_rows": 200000, "n_chunks": 40}'),
    ("gridsearch", "Grid search (argmax)", "tasks/task_gridsearch.py",
     '{"seed": 2026, "grid": {"lr": [0.01,0.05,0.1,0.5], "depth": [2,4,8,16], "reg": [0.0,0.1,0.3]}, "n_chunks": 40}'),
    ("adsb", "ADS-B anomalias (ranking top-k)", "tasks/task_adsb.py",
     '{"seed": 7, "num_traj": 60000, "n_chunks": 40, "anomaly_rate": 0.01, "top_k": 10, "n_routes": 6, "z_threshold": 4.0}'),
    ("flaky", "Flaky (demo de reintentos)", "tasks/task_flaky.py",
     '{"n_chunks": 12, "fail_chunks": [3, 7]}'),
]

# task_file -> payload por defecto (para autocompletar el Input al cambiar de tarea)
DEFAULT_PAYLOAD = {t[2]: t[3] for t in TASKS}
