#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tarea: deteccion de anomalias en trayectorias de aviones REALES (ADS-B), distribuida.

Version robusta de task_adsb.py que usa DATOS REALES (de OpenSky, via ingesta_adsb.py)
en vez de trayectorias sinteticas. Reutiliza la misma geometria, features y scoring
z-robusto/MAD; lo unico que cambia es el ORIGEN de las trayectorias:

  split() carga data/trayectorias_reales.json (vuelos reales ya limpios y resampleados),
  opcionalmente INYECTA unas pocas anomalias controladas sobre vuelos reales (para poder
  medir recall/precision -> evaluacion HIBRIDA), y reparte los vuelos entre los chunks.
  run() calcula features + scoring por chunk; merge() funde el top-k global. Solo stdlib.

Evaluacion HIBRIDA: el top-k mezcla vuelos genuinamente raros (deteccion exploratoria
real) con las anomalias inyectadas (ground-truth medible). Con `inject=0` es deteccion
NO supervisada pura sobre datos reales.
"""
import json
import math
import random

# ------------------------------------------------------------
# Geometria y estadistica (identicas a task_adsb.py; copiadas por autonomia)
# ------------------------------------------------------------
EPS = 1e-9
EARTH_R_KM = 6371.0088
FEATS = ("len_ratio", "turn_sum", "vrate_max")
ANOMALY_TYPES = ["rodeo", "holding", "descenso_anomalo", "go_around"]

# Piso de escala por feature (calibrado a la distribucion real de OpenSky): con datos
# reales muchos vuelos son casi rectos -> MAD ~ 0, lo que dispararia el z-score de
# cualquier vuelo que solo curve un poco. El piso acota la sensibilidad a una escala
# fisica sensata (variabilidad "normal" incluida la cola de aproximaciones/esperas).
FLOORS = {"len_ratio": 0.15, "turn_sum": 80.0, "vrate_max": 150.0}


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


def robust_stats(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0, 0.0
    med = s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])
    devs = sorted(abs(v - med) for v in values)
    mad = devs[n // 2] if n % 2 else 0.5 * (devs[n // 2 - 1] + devs[n // 2])
    return med, mad


def _pack(t):
    return {"id": t["id"], "route": t["route"], "icao24": t.get("icao24", ""),
            "score": t["score"], "reason": t["reason"],
            "injected": t["injected"], "atype": t["atype"], "feats": t["feats"], "path": t["path"]}


# ------------------------------------------------------------
# Inyeccion de una anomalia controlada SOBRE un path real (evaluacion hibrida)
# ------------------------------------------------------------

def inject_anomaly(path, atype, rng):
    """Suma una maniobra de tipo `atype` a una trayectoria real. Mismas magnitudes que la
    version sintetica (calibradas para destacar sobre el ruido de crucero)."""
    n = len(path)
    p = [list(pt) for pt in path]
    # escala espacial del vuelo (grados) -> perturbaciones PROPORCIONALES: destacan de forma
    # uniforme sin explotar en vuelos cortos (evita len_ratio y scores absurdos).
    span = max(0.4, ((path[-1][0] - path[0][0]) ** 2 + (path[-1][1] - path[0][1]) ** 2) ** 0.5)
    bump_mag = span * rng.uniform(1.2, 2.0)     # rodeo: desvio 120-200% de la longitud
    loops = rng.randint(3, 4)
    loop_r = span * rng.uniform(0.35, 0.55)     # holding: bucle proporcional
    drop = rng.uniform(16000, 26000)            # descenso_anomalo (ft, fisico)
    dip = rng.uniform(12000, 20000)             # go_around (ft, fisico)
    for w in range(n):
        t = w / (n - 1) if n > 1 else 0.0
        if atype == "rodeo":
            bump = math.sin(math.pi * t) * bump_mag
            p[w][0] += bump
            p[w][1] += bump * 0.6
        elif atype == "holding":
            if 0.4 <= t <= 0.7:
                frac = (t - 0.4) / 0.3
                ang = frac * 2 * math.pi * loops
                p[w][0] += loop_r * math.sin(ang)
                p[w][1] += loop_r * math.cos(ang)
        elif atype == "descenso_anomalo":
            if t > 0.5:
                p[w][2] = max(0.0, p[w][2] - (t - 0.5) * 2 * drop)
        elif atype == "go_around":
            p[w][2] = max(0.0, p[w][2] - math.sin(math.pi * t) * dip)
    return [[round(x[0], 4), round(x[1], 4), round(x[2], 1)] for x in p]


# ------------------------------------------------------------
# Contrato de tarea: split / run / merge / self_test
# ------------------------------------------------------------

def split(payload: dict, workers: list) -> list:
    """Carga las trayectorias reales, inyecta anomalias hibridas y reparte los vuelos
    (aleatorio uniforme) entre n_chunks. Cada chunk lleva SUS vuelos (path + flags)."""
    data_path = payload["data"]
    with open(data_path, encoding="utf-8") as f:
        trajs = json.load(f)
    n = int(payload.get("n_chunks", max(1, len(workers))))
    top_k = int(payload.get("top_k", 10))
    inject = int(payload.get("inject", 0))
    seed = int(payload.get("seed", 7))
    zth = float(payload.get("z_threshold", 4.0))

    rng = random.Random(seed)
    items = [{"id": tr["id"], "callsign": tr.get("callsign", "") or str(tr["id"]),
              "icao24": tr.get("icao24", ""),
              "injected": False, "atype": None, "path": tr["path"]} for tr in trajs]

    if inject > 0 and items:
        # Inyectar SOLO sobre vuelos reales NORMALES (rectos): asi la anomalia inyectada es
        # LA razon de su deteccion, no un vuelo base ya raro -> recall/precision limpios.
        lr = [features(it["path"])["len_ratio"] for it in items]
        med_lr = sorted(lr)[len(lr) // 2]
        rectos = [i for i, v in enumerate(lr) if v <= med_lr * 1.15]
        pool = rectos if len(rectos) >= inject else list(range(len(items)))
        for i in rng.sample(pool, min(inject, len(pool))):
            atype = rng.choice(ANOMALY_TYPES)
            items[i]["path"] = inject_anomaly(items[i]["path"], atype, rng)
            items[i]["injected"] = True
            items[i]["atype"] = atype

    rng.shuffle(items)                      # reparto aleatorio uniforme
    chunks = []
    for c in range(n):
        part = items[c::n]
        if part:
            chunks.append({"trajs": part, "top_k": top_k, "z_threshold": zth})
    return chunks


def run(chunk: dict) -> dict:
    """Extrae features de sus vuelos reales, los puntua por z-score robusto (MAD global
    del chunk) y devuelve el top-k local + conteos para metricas."""
    k = int(chunk["top_k"])
    zth = float(chunk.get("z_threshold", 4.0))

    trajs = []
    n_injected = 0
    for tr in chunk["trajs"]:
        rec = {"id": tr["id"], "route": tr["callsign"], "icao24": tr.get("icao24", ""),
               "injected": bool(tr["injected"]),
               "atype": tr["atype"], "feats": features(tr["path"]), "path": tr["path"]}
        if tr["injected"]:
            n_injected += 1
        trajs.append(rec)
    N = len(trajs)

    # Scoring z-robusto: linea base MAD GLOBAL del chunk (vuelos reales heterogeneos;
    # las 3 features son adimensionales/comparables entre rutas).
    stats = {}
    for f in FEATS:
        med, mad = robust_stats([t["feats"][f] for t in trajs])
        stats[f] = (med, max(1.4826 * mad, FLOORS[f]))   # piso: evita MAD~0 hipersensible
    for t in trajs:
        best_z, best_f = -1.0, FEATS[0]
        for f in FEATS:
            med, denom = stats[f]
            z = abs(t["feats"][f] - med) / denom
            if z > best_z:
                best_z, best_f = z, f
        # cap: evita scores absurdos si una feature tiene MAD~0 (valores casi identicos)
        t["score"] = round(min(best_z, 9999.0), 4)
        t["reason"] = best_f

    tp = sum(1 for t in trajs if t["injected"] and t["score"] >= zth)
    fp = sum(1 for t in trajs if not t["injected"] and t["score"] >= zth)
    n_normal = N - n_injected

    top_local = sorted(trajs, key=lambda t: t["score"], reverse=True)[:k]
    top_out = [_pack(t) for t in top_local]

    best_by_type = {}
    for t in trajs:
        at = t["atype"]
        if t["injected"] and (at not in best_by_type or t["score"] > best_by_type[at]["score"]):
            best_by_type[at] = _pack(t)

    return {"top_local": top_out, "best_by_type": best_by_type, "n_traj": N,
            "n_injected": n_injected, "n_normal": n_normal, "tp": tp, "fp": fp,
            "top_k": k, "z_threshold": zth}


def merge(results: list) -> dict:
    """RANKING TOP-K GLOBAL de vuelos reales + metricas (identico a task_adsb.merge)."""
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
    """Health-check funcional reproducible: 8 trayectorias con ruido determinista (una
    anomala), sin depender del archivo de datos."""
    trajs = []
    for j in range(8):
        rng = random.Random(1000 + j)
        p = [[round(50.0 + 0.10 * i + rng.gauss(0, 0.02), 4),
              round(8.0 + 0.15 * i + rng.gauss(0, 0.02), 4),
              round(35000.0 + rng.gauss(0, 60), 1)] for i in range(20)]
        inj = (j == 7)
        if inj:
            p = inject_anomaly(p, "rodeo", random.Random(1))
        trajs.append({"id": j, "callsign": f"TST{j}", "injected": inj,
                      "atype": "rodeo" if inj else None, "path": p})
    chunk = {"trajs": trajs, "top_k": 3, "z_threshold": 4.0}
    return chunk, run(chunk)
