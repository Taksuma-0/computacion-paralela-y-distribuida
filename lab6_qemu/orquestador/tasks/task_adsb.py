#!/usr/bin/env python3
"""Tarea: deteccion de anomalias en trayectorias de aviones (ADS-B), distribuida.

Cada worker FABRICA su propia particion de trayectorias sinteticas (por semilla),
les extrae features de comportamiento (desvio de ruta, curvatura, tasa de descenso)
y las puntua con un detector de outliers NO supervisado (z-score robusto / MAD).
Es el patron "cada nodo hace lo suyo" (como task_etl), pero el merge es distinto.

merge() de esta tarea = RANKING TOP-K GLOBAL (quinta semantica de combinacion,
distinta de: suma escalar [primes], suma de dicts [wordcount], consolidacion [etl]
y argmax [gridsearch]). Aqui el coordinador funde los top-k locales y se queda con
las K trayectorias mas anomalas de todo el dataset, ordenadas por score.

Conecta con el proyecto semestral (deteccion de anomalias ADS-B de OpenSky con un
pipeline distribuido): esta es una PoC de la etapa "scoring embarrassingly-parallel
sobre particiones".

--- Como funciona el scoring (z-score robusto / MAD) ---
Para cada RUTA dentro del chunk se calcula la mediana y la MAD (desviacion absoluta
mediana) de cada feature; el score de una trayectoria es el MAXIMO z-score robusto
|x - mediana| / (1.4826*MAD + eps) sobre sus features, y `reason` es la feature que
dio el maximo. 1.4826*MAD estima la desviacion estandar de una normal, asi que el
score es comparable a un z-score clasico pero resistente a outliers.

SUPUESTO (honesto): cada particion estima su PROPIA linea base robusta por ruta.
Como los chunks son homogeneos por diseno (split reparte la MISMA mezcla uniforme de
rutas a cada chunk), las medianas/MAD son estadisticamente equivalentes entre chunks
y los `score` son comparables -> se pueden fusionar por simple orden global en merge().

--- Metricas ---
- top-k + precision@k: de las K trayectorias mejor rankeadas, cuantas eran realmente
  anomalias inyectadas (ground-truth conocido). Mide la calidad del RANKING.
- recall / FPR a umbral: sobre TODO el dataset, cuantas anomalias (y cuantas normales)
  superan `z_threshold`. Mide la calidad de la DETECCION. (El recall@k crudo seria
  enganoso: hay muchas mas anomalias que K.)

Datos por semilla: los chunks NO transportan trayectorias, llevan `chunk_seed` +
parametros y run() las REGENERA con random.Random(seed) (determinista e identico
entre maquinas). Solo el top-k local viaja con su `path` (para dibujarlo). Solo stdlib.
"""

import math
import random


# ------------------------------------------------------------
# Helpers deterministas (autocontenidos; mismo patron que task_etl.py)
# ------------------------------------------------------------

def derive_seed(master: int, idx: int) -> int:
    """Semilla por sub-unidad: determinista y disjunta. NO usar hash() (aleatorizado)."""
    return (master * 1000003 + idx * 2654435761) & 0xFFFFFFFF


EPS = 1e-9
EARTH_R_KM = 6371.0088
N_WAYPOINTS = 30            # puntos por trayectoria
CRUISE_NOISE_DEG = 0.03     # ruido lateral normal sobre la linea recta (grados)
CRUISE_ALT_JITTER = 80.0    # jitter de altitud en crucero (ft)

# Rutas canonicas (pares origen-destino, Sudamerica). Geometrias variadas
# (cortas/largas, N-S vs E-O) -> las features de una trayectoria NORMAL son estables
# DENTRO de cada ruta pero distintas entre rutas (de ahi el scoring por ruta).
ROUTES = [
    {"name": "SCL-LIM", "o": (-33.39, -70.79), "d": (-12.02, -77.11), "alt": 35000},
    {"name": "SCL-EZE", "o": (-33.39, -70.79), "d": (-34.82, -58.54), "alt": 37000},
    {"name": "SCL-GRU", "o": (-33.39, -70.79), "d": (-23.43, -46.47), "alt": 38000},
    {"name": "LIM-BOG", "o": (-12.02, -77.11), "d": (  4.70, -74.15), "alt": 36000},
    {"name": "SCL-ANF", "o": (-33.39, -70.79), "d": (-23.44, -70.44), "alt": 33000},
    {"name": "EZE-GRU", "o": (-34.82, -58.54), "d": (-23.43, -46.47), "alt": 37000},
]
ANOMALY_TYPES = ["rodeo", "holding", "descenso_anomalo", "go_around"]
FEATS = ("len_ratio", "turn_sum", "vrate_max")


# ------------------------------------------------------------
# Geometria (stdlib math; todo finito -> JSON-safe)
# ------------------------------------------------------------

def haversine_km(lat1, lon1, lat2, lon2):
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


# ------------------------------------------------------------
# Generacion de UNA trayectoria por semilla (normal vs anomala)
# ------------------------------------------------------------

def gen_trajectory(rng, route, anomalous, atype):
    """Polilinea de N_WAYPOINTS puntos [lat, lon, alt] de origen a destino, con ruido
    normal. Si es anomala, se inyecta la perturbacion del tipo `atype` (magnitud tomada
    del rng -> reproducible). El consumo del rng es determinista dado (anomalous, atype)."""
    olat, olon = route["o"]
    dlat, dlon = route["d"]
    alt0 = float(route["alt"])

    # Parametros de la anomalia (se consumen del rng SIEMPRE en el mismo orden).
    bump_mag = rng.uniform(2.5, 4.0)        # rodeo
    loops = rng.randint(2, 3)               # holding
    loop_r = rng.uniform(0.5, 0.8)          # holding
    drop = rng.uniform(8000, 15000)         # descenso_anomalo
    dip = rng.uniform(6000, 12000)          # go_around

    path = []
    for w in range(N_WAYPOINTS):
        t = w / (N_WAYPOINTS - 1)
        lat = olat + (dlat - olat) * t
        lon = olon + (dlon - olon) * t
        alt = alt0
        # ruido normal (siempre)
        lat += rng.gauss(0, CRUISE_NOISE_DEG)
        lon += rng.gauss(0, CRUISE_NOISE_DEG)
        alt += rng.gauss(0, CRUISE_ALT_JITTER)
        # perturbacion anomala (inyectada)
        if anomalous:
            if atype == "rodeo":
                bump = math.sin(math.pi * t) * bump_mag
                lat += bump
                lon += bump * 0.6
            elif atype == "holding":
                if 0.4 <= t <= 0.7:
                    frac = (t - 0.4) / 0.3
                    ang = frac * 2 * math.pi * loops
                    lat += loop_r * math.sin(ang)
                    lon += loop_r * math.cos(ang)
            elif atype == "descenso_anomalo":
                if t > 0.5:
                    alt -= (t - 0.5) * 2 * drop
            elif atype == "go_around":
                alt -= math.sin(math.pi * t) * dip
        path.append([round(lat, 4), round(lon, 4), round(max(alt, 0.0), 1)])
    return path


def features(path):
    """len_ratio (desvio de ruta), turn_sum (curvatura), vrate_max (cambio vertical)."""
    real_len = 0.0
    for i in range(len(path) - 1):
        real_len += haversine_km(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
    direct = haversine_km(path[0][0], path[0][1], path[-1][0], path[-1][1])
    len_ratio = real_len / (direct + EPS)

    turn_sum = 0.0
    prev_b = None
    for i in range(len(path) - 1):
        b = bearing_deg(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1])
        if prev_b is not None:
            d = abs(b - prev_b)
            turn_sum += min(d, 360.0 - d)
        prev_b = b

    vrate_max = 0.0
    for i in range(len(path) - 1):
        vrate_max = max(vrate_max, abs(path[i + 1][2] - path[i][2]))

    return {"len_ratio": round(len_ratio, 4),
            "turn_sum": round(turn_sum, 3),
            "vrate_max": round(vrate_max, 2)}


# ------------------------------------------------------------
# Estadistica robusta (mediana + MAD)
# ------------------------------------------------------------

def _pack(t):
    """Empaqueta una trayectoria para viajar al coordinador (incluye su path para dibujar)."""
    return {"id": t["id"], "route": t["route"], "score": t["score"], "reason": t["reason"],
            "injected": t["injected"], "atype": t["atype"], "feats": t["feats"], "path": t["path"]}


def robust_stats(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0, 0.0
    med = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
    devs = sorted(abs(v - med) for v in values)
    mad = devs[n // 2] if n % 2 else 0.5 * (devs[n // 2 - 1] + devs[n // 2])
    return med, mad


# ------------------------------------------------------------
# Contrato de tarea: split / run / merge / self_test
# ------------------------------------------------------------

def split(payload: dict, workers: list) -> list:
    """Reparte num_traj en n_chunks. Cada chunk cubre TODAS las rutas uniformemente
    (clave: asi cada ruta tiene suficientes trayectorias por chunk -> MAD estable)."""
    master = int(payload.get("seed", 7))
    num_traj = int(payload["num_traj"])
    n = int(payload.get("n_chunks", max(1, len(workers))))
    anomaly_rate = float(payload.get("anomaly_rate", 0.01))
    top_k = int(payload.get("top_k", 10))
    n_routes = min(int(payload.get("n_routes", len(ROUTES))), len(ROUTES))
    z_threshold = float(payload.get("z_threshold", 4.0))

    base, extra = divmod(num_traj, n)
    chunks = []
    offset = 0
    for i in range(n):
        cnt = base + (1 if i < extra else 0)
        if cnt == 0:
            continue
        chunks.append({"chunk_seed": derive_seed(master, i), "num_traj": cnt,
                       "traj_offset": offset, "anomaly_rate": anomaly_rate,
                       "top_k": top_k, "n_routes": n_routes, "z_threshold": z_threshold})
        offset += cnt
    return chunks


def run(chunk: dict) -> dict:
    """Genera su porcion de trayectorias, extrae features, puntua por z-score robusto
    (MAD) por ruta y devuelve el top-k local (con path) + conteos para metricas."""
    cs = int(chunk["chunk_seed"])
    N = int(chunk["num_traj"])
    off = int(chunk["traj_offset"])
    arate = float(chunk["anomaly_rate"])
    k = int(chunk["top_k"])
    nr = min(int(chunk["n_routes"]), len(ROUTES))
    zth = float(chunk.get("z_threshold", 4.0))

    trajs = []
    by_route = {}
    n_injected = 0
    for j in range(N):
        sub = random.Random(derive_seed(cs, j))
        route = ROUTES[sub.randrange(nr)]
        anom = sub.random() < arate
        atype = sub.choice(ANOMALY_TYPES) if anom else None
        path = gen_trajectory(sub, route, anom, atype)
        rec = {"id": off + j, "route": route["name"], "injected": bool(anom),
               "atype": atype, "feats": features(path), "path": path}
        if anom:
            n_injected += 1
        trajs.append(rec)
        by_route.setdefault(route["name"], []).append(rec)

    # Linea base robusta global del chunk (fallback si una ruta tiene pocas muestras).
    global_stats = {}
    for f in FEATS:
        med, mad = robust_stats([t["feats"][f] for t in trajs])
        global_stats[f] = (med, 1.4826 * mad + EPS)

    # Scoring por ruta: z-score robusto, score = maximo sobre features, reason = argmax.
    for group in by_route.values():
        stats = {}
        for f in FEATS:
            if len(group) < 15:
                stats[f] = global_stats[f]
            else:
                med, mad = robust_stats([t["feats"][f] for t in group])
                stats[f] = (med, 1.4826 * mad + EPS)
        for t in group:
            best_z, best_f = -1.0, FEATS[0]
            for f in FEATS:
                med, denom = stats[f]
                z = abs(t["feats"][f] - med) / denom
                if z > best_z:
                    best_z, best_f = z, f
            t["score"] = round(best_z, 4)
            t["reason"] = best_f

    # Metricas a umbral (sobre TODO el chunk).
    tp = sum(1 for t in trajs if t["injected"] and t["score"] >= zth)
    fp = sum(1 for t in trajs if not t["injected"] and t["score"] >= zth)
    n_normal = N - n_injected

    # Top-k local (las unicas que viajan con su path completo).
    top_local = sorted(trajs, key=lambda t: t["score"], reverse=True)[:k]
    top_out = [_pack(t) for t in top_local]

    # Ejemplo mas claro (mayor score) de CADA tipo de anomalia: el top-k por score suele
    # estar dominado por un solo patron (holding), asi el HTML puede mostrar los 4.
    best_by_type = {}
    for t in trajs:
        at = t["atype"]
        if t["injected"] and (at not in best_by_type or t["score"] > best_by_type[at]["score"]):
            best_by_type[at] = _pack(t)

    return {"top_local": top_out, "best_by_type": best_by_type, "n_traj": N,
            "n_injected": n_injected, "n_normal": n_normal, "tp": tp, "fp": fp,
            "top_k": k, "z_threshold": zth}


def merge(results: list) -> dict:
    """RANKING TOP-K GLOBAL: funde los top-k locales y se queda con las K mas anomalas;
    agrega conteos para precision@k, recall y tasa de falsos positivos."""
    if not results:
        return {"top_k": [], "examples_by_type": {}, "n_traj": 0, "n_injected": 0,
                "n_normal": 0, "detected_injected_in_topk": 0, "precision_at_k": 0.0,
                "tp": 0, "fp": 0, "recall": 0.0, "false_positive_rate": 0.0,
                "precision_threshold": 0.0, "z_threshold": 4.0, "k": 0}

    k = max(int(r.get("top_k", 10)) for r in results)
    zth = results[0].get("z_threshold", 4.0)
    n_traj = sum(r["n_traj"] for r in results)
    n_injected = sum(r["n_injected"] for r in results)
    n_normal = sum(r["n_normal"] for r in results)
    tp = sum(r["tp"] for r in results)
    fp = sum(r["fp"] for r in results)

    pool = []
    for r in results:
        pool.extend(r["top_local"])
    pool.sort(key=lambda t: t["score"], reverse=True)
    seen, top = set(), []
    for t in pool:
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        top.append(t)
        if len(top) >= k:
            break

    # Consolida el mejor ejemplo de cada tipo de anomalia entre todos los chunks.
    examples = {}
    for r in results:
        for at, t in r.get("best_by_type", {}).items():
            if at not in examples or t["score"] > examples[at]["score"]:
                examples[at] = t

    detected = sum(1 for t in top if t["injected"])
    return {"top_k": top, "examples_by_type": examples,
            "n_traj": n_traj, "n_injected": n_injected, "n_normal": n_normal,
            "detected_injected_in_topk": detected,
            "precision_at_k": round(detected / len(top), 4) if top else 0.0,
            "tp": tp, "fp": fp,
            "recall": round(tp / n_injected, 4) if n_injected else 0.0,
            "false_positive_rate": round(fp / n_normal, 6) if n_normal else 0.0,
            "precision_threshold": round(tp / (tp + fp), 4) if (tp + fp) else 0.0,
            "z_threshold": zth, "k": len(top)}


def self_test():
    """Health-check funcional: chunk pequeno reproducible (mismo patron que task_gridsearch)."""
    chunk = {"chunk_seed": 12345, "num_traj": 200, "traj_offset": 0, "anomaly_rate": 0.05,
             "top_k": 5, "n_routes": 6, "z_threshold": 4.0}
    return chunk, run(chunk)
