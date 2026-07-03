#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ingesta de datos ADS-B REALES -> data/trayectorias_reales.json (formato stdlib).

Aisla lo pesado (red / pandas) en este paso que corre UNA vez en el host. Produce un
JSON que la tarea distribuida (tasks/task_adsb_real.py) consume con stdlib puro.

Fuentes:
  --source opensky (por defecto): OpenSky Network REST /states/all, ANONIMO (sin cuenta).
      Hace polling de un bounding box y agrupa por icao24 -> trayectorias reales de HOY.
      Es la fuente que cita el documento del proyecto semestral.
  --source traffic: 236 vuelos reales embebidos en la libreria `traffic` (si esta instalada:
      `conda install -c conda-forge traffic`). Offline, mejor calidad, pero deps pesadas.

Salida: [{"id":int,"callsign":str,"icao24":str,"path":[[lat,lon,alt_ft],...N_POINTS]}, ...]
Cada trayectoria se resamplea a N_POINTS por interpolacion lineal (features comparables).

Uso:
  python ingesta_adsb.py --source opensky --bbox 47,5,55,15 --snapshots 24 --interval 10
  python ingesta_adsb.py --source traffic
"""
import argparse
import json
import os
import sys
import time

OPENSKY_URL = "https://opensky-network.org/api/states/all"
# indices del state vector de OpenSky
I_ICAO, I_CALL, I_LON, I_LAT, I_BARO, I_ONGND, I_GEO = 0, 1, 5, 6, 7, 8, 13
M_TO_FT = 3.28084


def resample(pts, n):
    """Interpola una lista [(lat,lon,alt),...] a EXACTAMENTE n puntos (lineal por indice)."""
    m = len(pts)
    if m < 2:
        return None
    out = []
    for i in range(n):
        f = i * (m - 1) / (n - 1)
        lo = int(f)
        hi = min(lo + 1, m - 1)
        w = f - lo
        lat = pts[lo][0] * (1 - w) + pts[hi][0] * w
        lon = pts[lo][1] * (1 - w) + pts[hi][1] * w
        alt = pts[lo][2] * (1 - w) + pts[hi][2] * w
        out.append([round(lat, 4), round(lon, 4), round(alt, 1)])
    return out


def fetch_opensky(bbox, snapshots, interval):
    """Polling anonimo de /states/all sobre bbox=(lamin,lomin,lamax,lomax). Devuelve
    dict icao24 -> {"callsign":str, "pts":[(seq,lat,lon,alt_ft)]}."""
    import requests
    lamin, lomin, lamax, lomax = bbox
    params = {"lamin": lamin, "lomin": lomin, "lamax": lamax, "lomax": lomax}
    tracks = {}
    for k in range(snapshots):
        try:
            r = requests.get(OPENSKY_URL, params=params, timeout=40)
            if r.status_code != 200:
                print(f"  snapshot {k+1}/{snapshots}: HTTP {r.status_code} (saltado)")
                time.sleep(interval)
                continue
            states = r.json().get("states") or []
        except Exception as exc:
            print(f"  snapshot {k+1}/{snapshots}: error {exc} (saltado)")
            time.sleep(interval)
            continue
        used = 0
        for s in states:
            lat, lon = s[I_LAT], s[I_LON]
            if lat is None or lon is None or s[I_ONGND]:
                continue
            alt_m = s[I_BARO] if s[I_BARO] is not None else s[I_GEO]
            if alt_m is None:
                continue
            icao = s[I_ICAO]
            rec = tracks.setdefault(icao, {"callsign": (s[I_CALL] or "").strip(), "pts": []})
            rec["pts"].append((k, float(lat), float(lon), float(alt_m) * M_TO_FT))
            if not rec["callsign"] and s[I_CALL]:
                rec["callsign"] = s[I_CALL].strip()
            used += 1
        print(f"  snapshot {k+1}/{snapshots}: {len(states)} aviones, {used} en vuelo  "
              f"(acumulados {len(tracks)} icao24)")
        if k < snapshots - 1:
            time.sleep(interval)
    return tracks


def fetch_traffic():
    """236 vuelos reales embebidos en `traffic` (si esta instalada)."""
    from traffic.data.samples import quickstart
    tracks = {}
    for i, flight in enumerate(quickstart):
        d = flight.data.dropna(subset=["latitude", "longitude", "altitude"])
        if len(d) < 2:
            continue
        icao = str(getattr(flight, "icao24", None) or i)
        pts = [(j, float(la), float(lo), float(al))
               for j, (la, lo, al) in enumerate(zip(d["latitude"], d["longitude"], d["altitude"]))]
        tracks[icao] = {"callsign": (str(flight.callsign) if flight.callsign else icao), "pts": pts}
    return tracks


def main():
    ap = argparse.ArgumentParser(description="Ingesta de trayectorias ADS-B reales -> JSON")
    ap.add_argument("--source", choices=["opensky", "traffic"], default="opensky")
    ap.add_argument("--bbox", default="47,5,55,15",
                    help="lamin,lomin,lamax,lomax (opensky). Default: Europa central (mucho trafico)")
    ap.add_argument("--snapshots", type=int, default=24, help="nº de snapshots (opensky)")
    ap.add_argument("--interval", type=float, default=10.0, help="segundos entre snapshots (opensky, min util 10)")
    ap.add_argument("--min-points", type=int, default=8, help="descartar trayectorias con menos puntos")
    ap.add_argument("--n-points", type=int, default=40, help="resamplear cada trayectoria a N puntos")
    ap.add_argument("--out", default=os.path.join("data", "trayectorias_reales.json"))
    a = ap.parse_args()

    print(f"== Ingesta ADS-B real · fuente={a.source} ==")
    if a.source == "opensky":
        bbox = tuple(float(x) for x in a.bbox.split(","))
        eta = a.snapshots * a.interval
        print(f"bbox={bbox}  snapshots={a.snapshots} x {a.interval}s  (~{eta/60:.1f} min de captura)")
        tracks = fetch_opensky(bbox, a.snapshots, a.interval)
    else:
        print("Cargando 236 vuelos embebidos de `traffic`…")
        tracks = fetch_traffic()

    # Segmentar / limpiar / resamplear
    out = []
    lats, lons = [], []
    for icao, rec in tracks.items():
        pts = rec["pts"]
        # dedup de posiciones consecutivas identicas (snapshots repetidos)
        clean = []
        for p in pts:
            if not clean or (abs(p[1] - clean[-1][1]) > 1e-6 or abs(p[2] - clean[-1][2]) > 1e-6):
                clean.append(p)
        if len(clean) < a.min_points:
            continue
        path = resample([(p[1], p[2], p[3]) for p in clean], a.n_points)
        if not path:
            continue
        out.append({"id": len(out), "callsign": rec["callsign"] or icao, "icao24": icao, "path": path})
        for pt in path:
            lats.append(pt[0]); lons.append(pt[1])

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"\n== LISTO ==")
    print(f"  trayectorias reales: {len(out)}  (>= {a.min_points} pts, resampleadas a {a.n_points})")
    if out:
        print(f"  bbox datos: lat [{min(lats):.2f},{max(lats):.2f}]  lon [{min(lons):.2f},{max(lons):.2f}]")
        print(f"  ejemplo: {out[0]['callsign']}  ({len(out[0]['path'])} pts)  primer punto {out[0]['path'][0]}")
    print(f"  guardado en: {os.path.abspath(a.out)}  ({os.path.getsize(a.out)//1024} KB)")
    if len(out) < 20:
        print("  [aviso] pocas trayectorias; sube --snapshots o usa una bbox con mas trafico")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
