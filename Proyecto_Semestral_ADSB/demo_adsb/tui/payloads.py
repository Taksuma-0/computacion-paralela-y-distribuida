"""Preset de la tarea ADS-B para el launcher (TUI exclusiva de esta tarea)."""

# (clave, etiqueta, archivo de tarea, payload JSON por defecto)
TASKS = [
    ("adsb", "ADS-B anomalias (ranking top-k)", "tasks/task_adsb.py",
     '{"seed": 7, "num_traj": 60000, "n_chunks": 40, "anomaly_rate": 0.01, "top_k": 10, "n_routes": 6, "z_threshold": 4.0}'),
]

# task_file -> payload por defecto (para autocompletar el Input)
DEFAULT_PAYLOAD = {t[2]: t[3] for t in TASKS}
