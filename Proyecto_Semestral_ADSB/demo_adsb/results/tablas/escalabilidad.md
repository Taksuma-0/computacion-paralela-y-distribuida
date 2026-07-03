# Estudio de escalabilidad — orquestador distribuido (demo ADS-B)

Tarea `task_adsb` (sintetica, computo denso por datos-por-semilla) · num_traj=60000 · n_chunks=40 · R=3 repeticiones + calentamiento · agentes locales en 127.0.0.1.

**T1 (secuencial, media) = 13.027 s**  (desv 0.109 · mejor 12.911)

| p | Tp media (s) | Tp desv (s) | Tp mejor (s) | Speedup Sₚ=T₁/Tₚ | Eficiencia Eₚ=Sₚ/p | Overhead p·Tₚ−T₁ (s) |
|---|---|---|---|---|---|---|
| 1 | 12.963 | 0.050 | 12.892 | 1.00 | 1.00 | -0.064 |
| 2 | 7.345 | 0.032 | 7.307 | 1.77 | 0.89 | +1.663 |
| 4 | 4.192 | 0.045 | 4.147 | 3.11 | 0.78 | +3.741 |
| 8 | 2.331 | 0.035 | 2.292 | 5.59 | 0.70 | +5.618 |

_Nota metodologica:_ el speedup se mide sobre pares baseline↔distribuido que producen **el mismo resultado** (equivalencia verificada). La version con datos **reales** (636 vuelos) es I/O-bound y su Sₚ<1 — es la leccion de **granularidad**: las particiones deben tener suficiente computo para que el reparto valga la pena.
