"""Preset de la tarea ADS-B para el launcher (TUI exclusiva de esta tarea)."""

# (clave, etiqueta, archivo de tarea, payload JSON por defecto)
TASKS = [
    ("adsb_real", "ADS-B REAL (datos OpenSky)", "tasks/task_adsb_real.py",
     '{"data": "data/trayectorias_reales.json", "n_chunks": 8, "top_k": 12, "inject": 12, "seed": 7, "z_threshold": 4.0}'),
]

# task_file -> payload por defecto (para autocompletar el Input)
DEFAULT_PAYLOAD = {t[2]: t[3] for t in TASKS}
