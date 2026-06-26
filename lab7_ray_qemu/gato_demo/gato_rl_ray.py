#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gato_rl_ray.py  --  "El gato que aprende solo"
================================================

Demo de cómputo distribuido con Ray para el laboratorio de Computación Paralela
y Distribuida (QEMU/Debian/Ray).

En vez de contar primos (demo del Anexo A), aquí un agente de *machine learning*
APRENDE a jugar al gato (tic-tac-toe) por refuerzo, mediante "self-play":
juega miles de partidas contra sí mismo, refuerza las jugadas que llevan a
ganar y castiga las que llevan a perder (control Monte Carlo, política ε-greedy).

El entrenamiento es "vergonzosamente paralelo" y usa EXACTAMENTE el mismo patrón
map-reduce del demo de primos:

    politica_ref = ray.put(politica)                 # 1. broadcast de la política
    refs = [rollout.remote(politica_ref, ...) ...]   # 2. K tareas en paralelo
    parciales = ray.get(refs)                         # 3. recolectar (materializar)
    politica = fusionar(parciales)                    # 4. reduce -> nueva política

Cada generación mejora la política. Al terminar, el programa:
  * imprime en la terminal la curva de aprendizaje y un replay de una partida;
  * genera un archivo HTML interactivo y autocontenido (gato.html) donde puedes
    JUGAR contra la IA, ver la curva de aprendizaje y un replay animado de cómo
    fue mejorando.

Solo usa la librería estándar de Python + Ray (corre en la VM Debian minimal).

USO (en ray0, con Ray ya iniciado):
    python gato_rl_ray.py                       # valores por defecto
    python gato_rl_ray.py 30 2000 8             # generaciones, partidas/tarea, tareas
    python gato_rl_ray.py 40 4000 8 --benchmark # además mide speedup
    python gato_rl_ray.py --backend local 12 500 4   # sin Ray (para probar)

Como Ray Job (reproducible):
    ray job submit --address http://127.0.0.1:8265 --working-dir . \
        -- python gato_rl_ray.py 30 2000 8
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sys
import time


# ============================================================
# 1. MOTOR DEL JUEGO (tic-tac-toe / "el gato")
# ------------------------------------------------------------
# El tablero es un string de 9 caracteres: '.', 'X' u 'O'.
# Posiciones:   0 1 2
#               3 4 5
#               6 7 8
# X siempre juega primero, así que de quién es el turno se deduce contando.
# ============================================================

VACIO = "........."

LINEAS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),   # filas
    (0, 3, 6), (1, 4, 7), (2, 5, 8),   # columnas
    (0, 4, 8), (2, 4, 6),              # diagonales
]


def jugador_en_turno(tablero: str) -> str:
    """X juega primero; si hay igual número de X y O, le toca a X."""
    return "X" if tablero.count("X") == tablero.count("O") else "O"


def jugadas_legales(tablero: str):
    return [i for i, c in enumerate(tablero) if c == "."]


def aplicar_jugada(tablero: str, pos: int, jugador: str) -> str:
    return tablero[:pos] + jugador + tablero[pos + 1:]


def ganador(tablero: str):
    """Devuelve 'X', 'O', 'draw' (empate) o None (partida en curso)."""
    for a, b, c in LINEAS:
        if tablero[a] != "." and tablero[a] == tablero[b] == tablero[c]:
            return tablero[a]
    return "draw" if "." not in tablero else None


# ============================================================
# 2. POLÍTICA Y NÚCLEO DE APRENDIZAJE (Monte Carlo control)
# ------------------------------------------------------------
# La "política" es la tabla Q: { tablero: { jugada: valor } }.
# El valor es la recompensa esperada DESDE LA PERSPECTIVA del jugador en turno,
# así una sola tabla sirve para X y para O.
# ============================================================


def jugada_voraz(politica: dict, tablero: str, legales, rng=None) -> int:
    """Mejor jugada según la tabla Q. Empates: aleatorio si hay rng, si no el
    de menor índice (determinista, útil para replays reproducibles)."""
    q = politica.get(tablero)
    if not q:
        return rng.choice(legales) if rng is not None else legales[0]

    mejor_v = None
    empatadas = []
    for m in legales:
        v = q.get(m, 0.0)
        if mejor_v is None or v > mejor_v:
            mejor_v = v
            empatadas = [m]
        elif v == mejor_v:
            empatadas.append(m)
    return rng.choice(empatadas) if rng is not None else empatadas[0]


def rollout_self_play(politica: dict, n_partidas: int, epsilon: float, semilla: int) -> dict:
    """TAREA PARALELA (el "map"): juega n_partidas de self-play con política
    ε-greedy y devuelve estadísticas Monte Carlo parciales.

    Es una función pura: no comparte estado. Por eso Ray puede correr muchas
    copias a la vez en distintos nodos. Devuelve también el hostname para que
    se vea QUÉ nodo ejecutó el trabajo.
    """
    rng = random.Random(semilla)
    t0 = time.perf_counter()
    # parciales[tablero][jugada] = [suma_de_retornos, conteo]
    parciales: dict = {}

    for _ in range(n_partidas):
        tablero = VACIO
        trayectoria = []  # (tablero, jugada, jugador_que_movio)

        while ganador(tablero) is None:
            jugador = jugador_en_turno(tablero)
            legales = jugadas_legales(tablero)
            if rng.random() < epsilon:
                jugada = rng.choice(legales)          # explorar
            else:
                jugada = jugada_voraz(politica, tablero, legales, rng)  # explotar
            trayectoria.append((tablero, jugada, jugador))
            tablero = aplicar_jugada(tablero, jugada, jugador)

        resultado = ganador(tablero)  # 'X', 'O' o 'draw'

        # Backup Monte Carlo: el retorno final se reparte a cada jugada hecha
        # por el jugador que la realizó (+1 si ganó, -1 si perdió, 0 si empate).
        for (tab, jug, quien) in trayectoria:
            if resultado == "draw":
                r = 0.0
            elif resultado == quien:
                r = 1.0
            else:
                r = -1.0
            d = parciales.setdefault(tab, {})
            agg = d.setdefault(jug, [0.0, 0])
            agg[0] += r
            agg[1] += 1

    return {
        "hostname": socket.gethostname(),
        "n_partidas": n_partidas,
        "segundos": time.perf_counter() - t0,
        "parciales": parciales,
    }


def evaluar_vs_aleatorio(politica: dict, n_partidas: int, semilla: int) -> dict:
    """TAREA PARALELA de evaluación: el agente (voraz, SOLO con lo aprendido)
    juega contra un rival aleatorio, alternando quién parte. Mide cuánto sabe
    realmente la política -> alimenta la curva de aprendizaje.

    Importante: aquí NO hay red de seguridad táctica; es una medición honesta
    de la política aprendida.
    """
    rng = random.Random(semilla)
    g = d = p = 0  # ganadas, empatadas, perdidas (del agente)

    for k in range(n_partidas):
        agente = "X" if k % 2 == 0 else "O"
        tablero = VACIO
        while ganador(tablero) is None:
            turno = jugador_en_turno(tablero)
            legales = jugadas_legales(tablero)
            if turno == agente:
                jugada = jugada_voraz(politica, tablero, legales, rng)
            else:
                jugada = rng.choice(legales)
            tablero = aplicar_jugada(tablero, jugada, turno)

        res = ganador(tablero)
        if res == "draw":
            d += 1
        elif res == agente:
            g += 1
        else:
            p += 1

    return {"ganadas": g, "empatadas": d, "perdidas": p, "n": n_partidas}


def partida_demo(politica: dict, semilla_rival: int = 12345, agente: str = "X") -> dict:
    """Juega UNA partida determinista (agente voraz vs rival con semilla fija)
    y registra la secuencia de tableros. Como el rival es fijo, lo único que
    cambia entre generaciones es lo que aprendió el agente -> sirve de replay
    para "ver cómo mejora"."""
    rng = random.Random(semilla_rival)
    tablero = VACIO
    tableros = [tablero]
    while ganador(tablero) is None:
        turno = jugador_en_turno(tablero)
        legales = jugadas_legales(tablero)
        if turno == agente:
            jugada = jugada_voraz(politica, tablero, legales, None)  # determinista
        else:
            jugada = rng.choice(legales)
        tablero = aplicar_jugada(tablero, jugada, turno)
        tableros.append(tablero)

    res = ganador(tablero)
    etiqueta = "empate" if res == "draw" else ("gana" if res == agente else "pierde")
    return {"tableros": tableros, "resultado": etiqueta}


# ------------------------------------------------------------
# Fusión de estadísticas (el "reduce") y construcción de la política
# ------------------------------------------------------------

def fusionar(totales: dict, parciales: dict) -> None:
    """Acumula las estadísticas parciales de una tarea en los totales globales."""
    for tab, d in parciales.items():
        td = totales.setdefault(tab, {})
        for jug, (suma, cnt) in d.items():
            agg = td.setdefault(jug, [0.0, 0])
            agg[0] += suma
            agg[1] += cnt


def politica_desde_totales(totales: dict) -> dict:
    """Q(s,a) = retorno promedio observado para esa jugada."""
    pol = {}
    for tab, d in totales.items():
        pol[tab] = {jug: (suma / cnt if cnt else 0.0) for jug, (suma, cnt) in d.items()}
    return pol


# ============================================================
# 3. BACKENDS: Ray (paralelo real) y local (secuencial, para probar)
# ------------------------------------------------------------
# Ambos exponen la misma interfaz, así el driver no cambia. El backend "local"
# permite verificar el aprendizaje y el HTML sin tener Ray instalado.
# ============================================================


class BackendLocal:
    nombre = "local (secuencial, sin Ray)"

    def put(self, obj):
        return obj

    def mapear_rollouts(self, politica_ref, specs):
        return [rollout_self_play(politica_ref, n, e, s) for (n, e, s) in specs]

    def mapear_evals(self, politica_ref, specs):
        return [evaluar_vs_aleatorio(politica_ref, n, s) for (n, s) in specs]

    def cerrar(self):
        pass


class BackendRay:
    def __init__(self):
        import ray  # import perezoso: solo si se usa el backend Ray
        self.ray = ray
        if not ray.is_initialized():
            try:
                ray.init(address="auto")              # unirse al clúster ya iniciado
                self.nombre = "Ray (clúster, address=auto)"
            except Exception:
                ray.init()                            # fallback: Ray local en esta máquina
                self.nombre = "Ray (local en esta máquina)"
        else:
            self.nombre = "Ray (sesión ya inicializada)"
        # Versiones remotas de las funciones puras = tasks @ray.remote
        self.rollout = ray.remote(rollout_self_play)
        self.evaluar = ray.remote(evaluar_vs_aleatorio)

    def put(self, obj):
        return self.ray.put(obj)

    def mapear_rollouts(self, politica_ref, specs):
        refs = [self.rollout.remote(politica_ref, n, e, s) for (n, e, s) in specs]
        return self.ray.get(refs)

    def mapear_evals(self, politica_ref, specs):
        refs = [self.evaluar.remote(politica_ref, n, s) for (n, s) in specs]
        return self.ray.get(refs)

    def cerrar(self):
        self.ray.shutdown()


def crear_backend(nombre: str):
    if nombre == "local":
        return BackendLocal()
    return BackendRay()


# ============================================================
# 4. DRIVER DE ENTRENAMIENTO (orquesta las generaciones)
# ============================================================


def epsilon_de_generacion(gen: int, total: int) -> float:
    """ε decae linealmente de 0.9 (mucha exploración) a 0.1 (mucha explotación)."""
    if total <= 1:
        return 0.1
    frac = gen / (total - 1)
    return round(0.9 - 0.8 * frac, 3)


def entrenar(backend, generaciones: int, partidas_por_tarea: int, tareas: int,
             eval_partidas: int, semilla: int, emitir=None) -> dict:
    totales: dict = {}
    politica: dict = {}
    curva = []
    replays = []
    hosts_global = set()
    partidas_totales = 0

    eval_por_tarea = max(1, eval_partidas // tareas)

    print("=" * 64)
    print("  EL GATO QUE APRENDE SOLO  -  entrenamiento distribuido con Ray")
    print("=" * 64)
    print(f"Backend            : {backend.nombre}")
    print(f"Generaciones       : {generaciones}")
    print(f"Tareas por gen.    : {tareas}  (rollouts en paralelo)")
    print(f"Partidas por tarea : {partidas_por_tarea}")
    print(f"Partidas por gen.  : {tareas * partidas_por_tarea}")
    print(f"Evaluación por gen.: {tareas} x {eval_por_tarea} vs rival aleatorio")
    print("-" * 64)
    print(f"{'gen':>3} | {'eps':>5} | {'no-derrota':>10} | "
          f"{'gana/empat/pierde':>18} | {'nodos':>10} | {'seg':>5}")
    print("-" * 64)

    if emitir:
        emitir({"kind": "train_start", "generaciones": generaciones, "tareas": tareas,
                "partidas_por_tarea": partidas_por_tarea})

    t_inicio = time.perf_counter()

    for gen in range(generaciones):
        eps = epsilon_de_generacion(gen, generaciones)
        if emitir:
            emitir({"kind": "gen_start", "gen": gen, "epsilon": eps})
            for _i in range(tareas):
                emitir({"kind": "chunk_assigned", "worker": _i, "gen": gen})

        # ---- MAP: broadcast de la política + rollouts en paralelo ----
        politica_ref = backend.put(politica)
        specs = [(partidas_por_tarea, eps, semilla + gen * 1000 + i) for i in range(tareas)]
        resultados = backend.mapear_rollouts(politica_ref, specs)

        # ---- REDUCE: fusionar estadísticas y recomputar la política ----
        hosts_gen = set()
        seg_tareas = 0.0
        for _i, r in enumerate(resultados):
            fusionar(totales, r["parciales"])
            hosts_gen.add(r["hostname"])
            hosts_global.add(r["hostname"])
            partidas_totales += r["n_partidas"]
            seg_tareas = max(seg_tareas, r["segundos"])
            if emitir:
                emitir({"kind": "chunk_done", "worker": _i, "hostname": r["hostname"],
                        "seconds": round(r["segundos"], 3), "partidas": r["n_partidas"]})
        politica = politica_desde_totales(totales)

        # ---- Evaluación en paralelo vs rival aleatorio (la curva) ----
        politica_ref2 = backend.put(politica)
        eval_specs = [(eval_por_tarea, 7_000_000 + gen * 100 + i) for i in range(tareas)]
        evals = backend.mapear_evals(politica_ref2, eval_specs)
        g = sum(e["ganadas"] for e in evals)
        d = sum(e["empatadas"] for e in evals)
        p = sum(e["perdidas"] for e in evals)
        n = g + d + p
        win = g / n
        draw = d / n
        loss = p / n
        nonloss = (g + d) / n

        curva.append({
            "gen": gen,
            "epsilon": eps,
            "win": round(win, 4),
            "draw": round(draw, 4),
            "loss": round(loss, 4),
            "nonloss": round(nonloss, 4),
            "partidas": tareas * partidas_por_tarea,
        })

        # ---- Replay: una partida demo con la política de esta generación ----
        demo = partida_demo(politica)
        replays.append({"gen": gen, "nonloss": round(nonloss, 4),
                        "resultado": demo["resultado"], "tableros": demo["tableros"]})

        nodos = ",".join(sorted(hosts_gen))
        if len(nodos) > 10:
            nodos = f"{len(hosts_gen)} nodos"
        print(f"{gen:>3} | {eps:>5.2f} | {nonloss * 100:>9.1f}% | "
              f"{g:>5}/{d:>4}/{p:>5} | {nodos:>10} | {seg_tareas:>5.2f}")
        if emitir:
            emitir({"kind": "gen_done", "gen": gen, "epsilon": eps,
                    "nonloss": round(nonloss, 4), "win": round(win, 4),
                    "draw": round(draw, 4), "loss": round(loss, 4),
                    "partidas": tareas * partidas_por_tarea, "hosts": sorted(hosts_gen)})

    segundos = time.perf_counter() - t_inicio
    print("-" * 64)

    res = {
        "politica": politica,
        "curva": curva,
        "replays": replays,
        "meta": {
            "generaciones": generaciones,
            "partidas_por_tarea": partidas_por_tarea,
            "tareas": tareas,
            "partidas_totales": partidas_totales,
            "segundos": round(segundos, 2),
            "estados_aprendidos": len(politica),
            "hosts": sorted(hosts_global),
            "backend": backend.nombre,
        },
    }
    if emitir:
        fin = curva[-1] if curva else {}
        emitir({"kind": "train_done", "meta": res["meta"], "nonloss": fin.get("nonloss"),
                "win": fin.get("win"), "draw": fin.get("draw")})
    return res


# ============================================================
# 5. BENCHMARK DE SPEEDUP (slide 16 del deck)
# ------------------------------------------------------------
# Mide el tiempo de la fase paralelizable (los rollouts) con 1 tarea vs K
# tareas, manteniendo el MISMO total de partidas. Reporta speedup, eficiencia
# y overhead. Solo es significativo con el backend Ray.
# ============================================================


def benchmark(backend, partidas_por_tarea: int, tareas: int, semilla: int) -> dict:
    total = partidas_por_tarea * tareas
    politica_ref = backend.put({})  # política vacía: solo medimos cómputo
    eps = 0.5

    print("Benchmark de speedup (fase de rollouts, mismo total de partidas)...")
    print(f"  Total de partidas: {total}")

    t0 = time.perf_counter()
    backend.mapear_rollouts(politica_ref, [(total, eps, semilla)])      # 1 tarea
    t1 = time.perf_counter() - t0

    t0 = time.perf_counter()
    backend.mapear_rollouts(                                            # K tareas
        politica_ref, [(partidas_por_tarea, eps, semilla + i) for i in range(tareas)])
    tp = time.perf_counter() - t0

    speedup = t1 / tp if tp > 0 else 0.0
    eficiencia = speedup / tareas if tareas else 0.0
    overhead = tareas * tp - t1

    print(f"  T1 (1 tarea)   : {t1:.3f} s")
    print(f"  Tp ({tareas} tareas) : {tp:.3f} s")
    print(f"  Speedup  S = T1/Tp        : {speedup:.2f}x")
    print(f"  Eficiencia E = S/p        : {eficiencia * 100:.0f}%")
    print(f"  Overhead  O = p*Tp - T1   : {overhead:.3f} s")
    print("-" * 64)

    return {"p": tareas, "t1": round(t1, 3), "tp": round(tp, 3),
            "speedup": round(speedup, 2), "eficiencia": round(eficiencia, 3),
            "overhead": round(overhead, 3), "total_partidas": total}


# ============================================================
# 6. REPORTE EN TERMINAL
# ============================================================

BLOQUES = " ▁▂▃▄▅▆▇█"


def sparkline(valores) -> str:
    if not valores:
        return ""
    return "".join(BLOQUES[min(8, max(0, int(round(v * 8))))] for v in valores)


def imprimir_tablero(tablero: str) -> None:
    s = tablero.replace(".", "·")
    for f in range(3):
        print("     " + " ".join(s[f * 3:f * 3 + 3]))


def reporte_terminal(resultado: dict) -> None:
    curva = resultado["curva"]
    meta = resultado["meta"]

    print()
    print("CURVA DE APRENDIZAJE (% de no-derrota vs rival aleatorio)")
    print("  " + sparkline([c["nonloss"] for c in curva]))
    print(f"  inicio: {curva[0]['nonloss'] * 100:.1f}%   ->   "
          f"final: {curva[-1]['nonloss'] * 100:.1f}%")

    print()
    print("REPLAY: partida del agente ya entrenado (X) vs rival aleatorio (O)")
    demo = resultado["replays"][-1]
    for i, tab in enumerate(demo["tableros"]):
        print(f"  jugada {i}:")
        imprimir_tablero(tab)
    print(f"  resultado: el agente {demo['resultado']}")

    print()
    print("RESUMEN")
    print(f"  Partidas jugadas en total : {meta['partidas_totales']:,}")
    print(f"  Estados aprendidos        : {meta['estados_aprendidos']:,}")
    print(f"  Nodos que participaron    : {', '.join(meta['hosts'])}")
    print(f"  Tiempo de cómputo (Ray)   : {meta['segundos']} s")
    print(f"  No-derrota final          : {curva[-1]['nonloss'] * 100:.1f}% "
          f"(gana {curva[-1]['win'] * 100:.0f}% / empata {curva[-1]['draw'] * 100:.0f}%)")
    print("=" * 64)


# ============================================================
# 7. GENERACIÓN DEL HTML INTERACTIVO (autocontenido)
# ============================================================


def mejores_jugadas(politica: dict) -> dict:
    """Para cada tablero conocido, la jugada voraz (determinista). Es lo que
    usa la interfaz para que puedas jugar contra la IA en el navegador."""
    best = {}
    for tab in politica:
        legales = jugadas_legales(tab)
        if legales and ganador(tab) is None:
            best[tab] = jugada_voraz(politica, tab, legales, None)
    return best


def generar_html(resultado: dict, ruta: str, benchmark_res=None) -> None:
    data = {
        "meta": resultado["meta"],
        "bestmove": mejores_jugadas(resultado["politica"]),
        "curva": resultado["curva"],
        "replays": resultado["replays"],
        "benchmark": benchmark_res,
    }
    html = PLANTILLA_HTML.replace("__DATA_JSON__", json.dumps(data))
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(html)


PLANTILLA_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>😺 El gato que aprende solo · Ray</title>
<style>
  :root{
    --bg:#0e1016; --card:#181b25; --card2:#1f2333; --line:#2c3142;
    --txt:#e7e9f0; --muted:#9aa3b8; --x:#5b9dff; --o:#f5a623;
    --ok:#36d399; --bad:#f87272; --accent:#f5a623;
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#1b2030,#0e1016);
       color:var(--txt);font:15px/1.5 system-ui,Segoe UI,Roboto,Arial,sans-serif;padding:28px}
  h1{font-size:30px;margin:0 0 4px} h2{font-size:19px;margin:0 0 14px}
  .sub{color:var(--muted);margin:0 0 18px}
  .wrap{max-width:1080px;margin:0 auto}
  .chips{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 26px}
  .chip{background:var(--card2);border:1px solid var(--line);border-radius:999px;
        padding:6px 14px;font-size:13px;color:var(--muted)}
  .chip b{color:var(--txt)}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}
  @media(max-width:860px){.grid{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px}
  .full{grid-column:1/-1}
  /* tablero */
  .board{display:grid;grid-template-columns:repeat(3,88px);grid-gap:8px;justify-content:center;margin:8px 0}
  .cell{width:88px;height:88px;border-radius:14px;border:1px solid var(--line);background:#11141d;
        font-size:46px;font-weight:800;cursor:pointer;display:flex;align-items:center;justify-content:center;
        transition:transform .08s,background .15s}
  .cell:hover{background:#161a26} .cell:active{transform:scale(.96)}
  .cell.x{color:var(--x)} .cell.o{color:var(--o)} .cell.win{background:#23314a;border-color:var(--x)}
  .cell.dis{cursor:default}
  .status{text-align:center;font-size:17px;min-height:26px;margin:6px 0 10px}
  .row{display:flex;gap:10px;align-items:center;justify-content:center;flex-wrap:wrap}
  button.btn{background:var(--accent);color:#1a1300;border:0;border-radius:10px;padding:9px 16px;
             font-weight:700;cursor:pointer} button.btn:hover{filter:brightness(1.08)}
  button.ghost{background:transparent;color:var(--txt);border:1px solid var(--line)}
  .score{display:flex;gap:18px;justify-content:center;color:var(--muted);margin-top:10px;font-size:14px}
  .score b{color:var(--txt);font-size:18px}
  select,input[type=range]{accent-color:var(--accent)}
  select{background:#11141d;color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
  /* leyenda curva */
  .legend{display:flex;gap:16px;justify-content:center;font-size:13px;color:var(--muted);margin-top:8px}
  .dot{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:6px;vertical-align:middle}
  svg text{fill:var(--muted);font-size:11px}
  .tip{position:fixed;pointer-events:none;background:#000a;border:1px solid var(--line);
       border-radius:8px;padding:6px 9px;font-size:12px;color:#fff;opacity:0;transition:opacity .1s}
  .miniboard{display:grid;grid-template-columns:repeat(3,40px);grid-gap:4px;justify-content:center;margin:10px 0}
  .mc{width:40px;height:40px;border-radius:8px;border:1px solid var(--line);background:#11141d;
      font-size:22px;font-weight:800;display:flex;align-items:center;justify-content:center}
  .mc.x{color:var(--x)} .mc.o{color:var(--o)}
  .badge{display:inline-block;border-radius:8px;padding:3px 10px;font-size:13px;font-weight:700}
  .b-ok{background:#123a2b;color:var(--ok)} .b-mid{background:#3a3612;color:#ffe08a}
  .b-bad{background:#3a1414;color:var(--bad)}
  .foot{color:var(--muted);font-size:12px;text-align:center;margin-top:26px}
  code{background:#11141d;border:1px solid var(--line);border-radius:6px;padding:1px 6px}
</style>
</head>
<body>
<div class="wrap">
  <h1>😺 El gato que aprende solo</h1>
  <p class="sub">Un agente que aprendió a jugar al gato <b>por refuerzo</b>, entrenado <b>en paralelo con Ray</b> sobre el clúster QEMU/Debian.</p>
  <div class="chips" id="chips"></div>

  <div class="grid">
    <!-- JUGAR -->
    <div class="card">
      <h2>🎮 Juega contra la IA</h2>
      <div class="status" id="status">Elige tu ficha y toca el tablero.</div>
      <div class="board" id="board"></div>
      <div class="row" style="margin-top:6px">
        <span style="color:var(--muted)">Tú juegas:</span>
        <button class="btn ghost" id="asX">❌ X (parte)</button>
        <button class="btn ghost" id="asO">⭕ O</button>
        <button class="btn" id="reset">Reiniciar</button>
      </div>
      <div class="score">
        <span>Tú: <b id="sw">0</b></span>
        <span>Empates: <b id="sd">0</b></span>
        <span>Gato 😼: <b id="sl">0</b></span>
      </div>
      <p style="color:var(--muted);font-size:12px;margin-top:10px">La IA usa su política aprendida, con una pequeña red de seguridad táctica para no regalar partidas.</p>
    </div>

    <!-- CURVA -->
    <div class="card">
      <h2>📈 Curva de aprendizaje</h2>
      <div id="chart"></div>
      <div class="legend">
        <span><i class="dot" style="background:var(--ok)"></i>No-derrota</span>
        <span><i class="dot" style="background:var(--x)"></i>Gana</span>
        <span><i class="dot" style="background:var(--o)"></i>Empata</span>
        <span><i class="dot" style="background:var(--bad)"></i>Pierde</span>
      </div>
      <div class="row" style="margin-top:12px">
        <button class="btn" id="anim">▶ Animar aprendizaje</button>
        <span id="animlbl" style="color:var(--muted)"></span>
      </div>
    </div>

    <!-- REPLAY -->
    <div class="card full">
      <h2>🎬 Replay: cómo fue mejorando</h2>
      <p style="color:var(--muted);margin-top:-6px">Misma partida (agente ❌ vs un rival fijo ⭕) en distintas generaciones. Mueve el deslizador para ver cómo cambia lo que juega el agente a medida que aprende.</p>
      <div class="row">
        <span style="color:var(--muted)">Generación</span>
        <input type="range" id="gen" min="0" value="0" style="width:60%">
        <span id="genlbl" style="min-width:60px"></span>
        <span id="genres" class="badge"></span>
      </div>
      <div id="replay"></div>
      <div class="row">
        <button class="btn" id="playmoves">▶ Reproducir jugadas</button>
      </div>
    </div>
  </div>

  <p class="foot">Generado por <code>gato_rl_ray.py</code> · Computación Paralela y Distribuida · Ray + QEMU</p>
</div>

<div class="tip" id="tip"></div>

<script>
const DATA = __DATA_JSON__;

/* ---------- motor del gato (espejo del de Python) ---------- */
const LINES=[[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
const ptm=b=>{let x=0,o=0;for(const c of b){if(c==='X')x++;else if(c==='O')o++;}return x===o?'X':'O';};
const legal=b=>{let r=[];for(let i=0;i<9;i++)if(b[i]==='.')r.push(i);return r;};
const mv=(b,p,pl)=>b.substring(0,p)+pl+b.substring(p+1);
function winner(b){for(const[a,c,d]of LINES){if(b[a]!=='.'&&b[a]===b[c]&&b[c]===b[d])return b[a];}return b.includes('.')?null:'draw';}
function winLine(b){for(const L of LINES){const[a,c,d]=L;if(b[a]!=='.'&&b[a]===b[c]&&b[c]===b[d])return L;}return null;}

/* IA: red de seguridad táctica + política aprendida */
function aiMove(b){
  const pl=ptm(b), opp=pl==='X'?'O':'X', ms=legal(b);
  for(const m of ms){if(winner(mv(b,m,pl))===pl)return m;}      // gana ya
  for(const m of ms){if(winner(mv(b,m,opp))===opp)return m;}    // bloquea
  if(b in DATA.bestmove && ms.includes(DATA.bestmove[b]))return DATA.bestmove[b]; // aprendido
  for(const m of [4,0,2,6,8,1,3,5,7])if(ms.includes(m))return m; // heurística
  return ms[0];
}

/* ---------- chips de metadatos ---------- */
const M=DATA.meta;
const chips=[
  ['Nodos', M.hosts.join(', ')],
  ['Partidas entrenadas', M.partidas_totales.toLocaleString('es')],
  ['Generaciones', M.generaciones],
  ['Tareas Ray / gen', M.tareas],
  ['Estados aprendidos', M.estados_aprendidos.toLocaleString('es')],
  ['Tiempo de cómputo', M.segundos+' s'],
];
if(DATA.benchmark) chips.push(['Speedup', DATA.benchmark.speedup+'x ('+Math.round(DATA.benchmark.eficiencia*100)+'% efic.)']);
document.getElementById('chips').innerHTML=chips.map(c=>`<span class="chip">${c[0]}: <b>${c[1]}</b></span>`).join('');

/* ---------- jugar ---------- */
let human='O', board='.'.repeat(9), over=false, sc={w:0,d:0,l:0};
const boardEl=document.getElementById('board'), statusEl=document.getElementById('status');
function render(){
  const wl=winLine(board);
  boardEl.innerHTML='';
  for(let i=0;i<9;i++){
    const d=document.createElement('div');
    d.className='cell'+(board[i]==='X'?' x':board[i]==='O'?' o':'')+(wl&&wl.includes(i)?' win':'')+(over||board[i]!=='.'?' dis':'');
    d.textContent=board[i]==='X'?'✕':board[i]==='O'?'◯':'';
    d.onclick=()=>play(i);
    boardEl.appendChild(d);
  }
}
function setStatus(){
  const w=winner(board);
  if(w==='draw'){statusEl.textContent='🤝 Empate';}
  else if(w){statusEl.textContent = w===human?'🎉 ¡Ganaste!':'😼 Ganó el gato';}
  else statusEl.textContent = ptm(board)===human?'Tu turno':'Pensando…';
}
function finish(){
  over=true; const w=winner(board);
  if(w==='draw'){sc.d++;} else if(w===human){sc.w++;} else {sc.l++;}
  document.getElementById('sw').textContent=sc.w;
  document.getElementById('sd').textContent=sc.d;
  document.getElementById('sl').textContent=sc.l;
}
function aiTurn(){
  if(winner(board)!==null){setStatus();finish();render();return;}
  setStatus();
  setTimeout(()=>{
    board=mv(board,aiMove(board),ptm(board));
    render();
    if(winner(board)!==null){setStatus();finish();} else setStatus();
  },350);
}
function play(i){
  if(over||board[i]!=='.'||ptm(board)!==human)return;
  board=mv(board,i,human); render();
  if(winner(board)!==null){setStatus();finish();render();return;}
  aiTurn();
}
function newGame(){
  board='.'.repeat(9); over=false; render();
  if(ptm(board)!==human) aiTurn(); else setStatus();
}
document.getElementById('asX').onclick=()=>{human='X';newGame();};
document.getElementById('asO').onclick=()=>{human='O';newGame();};
document.getElementById('reset').onclick=newGame;

/* ---------- curva (SVG) ---------- */
const C=DATA.curva, W=440,H=210,PL=34,PB=24;
function x(i){return PL+(W-PL-8)*(C.length<2?0:i/(C.length-1));}
function y(v){return 8+(H-8-PB)*(1-v);}
function path(key,color){
  let d=C.map((c,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(c[key]).toFixed(1)).join(' ');
  return `<path d="${d}" fill="none" stroke="${color}" stroke-width="2"/>`;
}
function buildChart(marker){
  let g='';
  for(let t=0;t<=100;t+=25){g+=`<line x1="${PL}" y1="${y(t/100)}" x2="${W}" y2="${y(t/100)}" stroke="#2c3142"/><text x="4" y="${y(t/100)+3}">${t}%</text>`;}
  g+=`<text x="${PL}" y="${H-6}">gen 0</text><text x="${W-44}" y="${H-6}">gen ${C.length-1}</text>`;
  g+=path('loss','#f87272')+path('draw','#f5a623')+path('win','#5b9dff')+path('nonloss','#36d399');
  let dots=C.map((c,i)=>`<circle cx="${x(i).toFixed(1)}" cy="${y(c.nonloss).toFixed(1)}" r="8" fill="transparent" data-i="${i}"/>`).join('');
  let mk = marker!=null ? `<line x1="${x(marker)}" y1="6" x2="${x(marker)}" y2="${H-PB}" stroke="#fff6" stroke-dasharray="3 3"/>` : '';
  document.getElementById('chart').innerHTML=`<svg viewBox="0 0 ${W} ${H}" width="100%">${g}${mk}${dots}</svg>`;
  const tip=document.getElementById('tip');
  document.querySelectorAll('#chart circle').forEach(ci=>{
    ci.onmousemove=e=>{const c=C[ci.dataset.i];tip.style.opacity=1;tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px';
      tip.innerHTML=`gen ${c.gen} · ε=${c.epsilon}<br>no-derrota ${(c.nonloss*100).toFixed(1)}%<br>gana ${(c.win*100).toFixed(0)}% · empata ${(c.draw*100).toFixed(0)}% · pierde ${(c.loss*100).toFixed(0)}%`;};
    ci.onmouseleave=()=>tip.style.opacity=0;
  });
}
buildChart(null);
document.getElementById('anim').onclick=()=>{
  let i=0; const lbl=document.getElementById('animlbl');
  const t=setInterval(()=>{
    if(i>=C.length){clearInterval(t);lbl.textContent='';buildChart(null);return;}
    buildChart(i);
    lbl.textContent=`gen ${C[i].gen}: no-derrota ${(C[i].nonloss*100).toFixed(0)}%`;
    i++;
  },Math.max(60,1200/C.length));
};

/* ---------- replay ---------- */
const R=DATA.replays, genEl=document.getElementById('gen');
genEl.max=R.length-1; genEl.value=R.length-1;
function miniBoard(b){
  return '<div class="miniboard">'+[...b].map(c=>`<div class="mc ${c==='X'?'x':c==='O'?'o':''}">${c==='X'?'✕':c==='O'?'◯':''}</div>`).join('')+'</div>';
}
function showReplay(gi,move){
  const r=R[gi];
  const m = move==null? r.tableros.length-1 : move;
  document.getElementById('replay').innerHTML = miniBoard(r.tableros[m]);
  document.getElementById('genlbl').textContent='gen '+r.gen;
  const bd=document.getElementById('genres');
  bd.textContent = r.resultado==='gana'?'el agente gana 🎉':r.resultado==='empate'?'empate 🤝':'el agente pierde';
  bd.className='badge '+(r.resultado==='gana'?'b-ok':r.resultado==='empate'?'b-mid':'b-bad');
}
genEl.oninput=()=>showReplay(+genEl.value,null);
document.getElementById('playmoves').onclick=()=>{
  const r=R[+genEl.value]; let m=0;
  const t=setInterval(()=>{ if(m>=r.tableros.length){clearInterval(t);return;} showReplay(+genEl.value,m); m++; },550);
};

/* init */
render(); newGame(); showReplay(R.length-1,null);
</script>
</body>
</html>
"""


# ============================================================
# 8. CLI / MAIN
# ============================================================


def parse_args():
    p = argparse.ArgumentParser(description="El gato que aprende solo (RL distribuido con Ray)")
    p.add_argument("generaciones", nargs="?", type=int, default=30)
    p.add_argument("partidas_por_tarea", nargs="?", type=int, default=2000)
    p.add_argument("tareas", nargs="?", type=int, default=8)
    p.add_argument("--backend", choices=["ray", "local"], default="ray",
                   help="ray = clúster (por defecto); local = secuencial, sin Ray")
    p.add_argument("--eval-partidas", type=int, default=400,
                   help="partidas de evaluación por generación (repartidas entre tareas)")
    p.add_argument("--benchmark", action="store_true", help="mide speedup/eficiencia/overhead")
    p.add_argument("--salida", default="gato.html", help="ruta del HTML interactivo de salida")
    p.add_argument("--semilla", type=int, default=0)
    p.add_argument("--emit-events", action="store_true",
                   help="imprime lineas 'EVT {json}' (una por evento) para la TUI")
    p.add_argument("--modelo-salida", default=None,
                   help="escribe el modelo entrenado (bestmove+curva+meta) a este JSON")
    return p.parse_args()


def emisor_eventos():
    """Devuelve una función que imprime cada evento como línea 'EVT {json}' (para la TUI)."""
    def emitir(ev):
        try:
            sys.stdout.write("EVT " + json.dumps(ev, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except Exception:
            pass
    return emitir


def main():
    # La terminal de Windows usa cp1252 por defecto y no puede con los caracteres
    # de bloque de la curva ni con las tildes. Forzamos UTF-8 (en Debian ya lo es).
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    a = parse_args()
    emitir = emisor_eventos() if a.emit_events else None
    backend = crear_backend(a.backend)
    try:
        bench = None
        if a.benchmark:
            bench = benchmark(backend, a.partidas_por_tarea, a.tareas, a.semilla)
            if emitir:
                emitir({"kind": "benchmark", **bench})

        resultado = entrenar(backend, a.generaciones, a.partidas_por_tarea, a.tareas,
                             a.eval_partidas, a.semilla, emitir=emitir)
        reporte_terminal(resultado)

        salida = os.path.abspath(a.salida)
        generar_html(resultado, salida, bench)
        print(f"\nInterfaz interactiva generada: {salida}")

        if a.modelo_salida:
            modelo = {
                "bestmove": mejores_jugadas(resultado["politica"]),
                "curva": resultado["curva"],
                "meta": resultado["meta"],
            }
            ruta_modelo = os.path.abspath(a.modelo_salida)
            with open(ruta_modelo, "w", encoding="utf-8") as f:
                json.dump(modelo, f, ensure_ascii=False)
            print(f"Modelo entrenado guardado: {ruta_modelo}")
            if emitir:
                emitir({"kind": "model_ready", "path": os.path.basename(a.modelo_salida),
                        "estados": len(modelo["bestmove"])})

        print("Cópiala a Windows y ábrela en el navegador (desde PowerShell en Windows):")
        print(f"  scp -P 2320 ray@127.0.0.1:~/ray-demo/{os.path.basename(a.salida)} .")
    finally:
        backend.cerrar()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        sys.exit(130)
