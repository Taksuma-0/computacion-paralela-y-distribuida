# Proyecto Semestral — Detección distribuida de anomalías en trayectorias ADS-B

**Curso:** INF8090 · Computación Paralela y Distribuida — Ingeniería Civil en Ciencia de Datos (UTEM)
**Sección:** 412 · **Docente:** Dr. Ing. Michael Miranda Sandoval
**Integrantes:** Welinton Barrera Mondaca (wbarrera@utem.cl) · Joaquín Ignacio Araya Bustos (jarayabu@utem.cl) · Juan Cristóbal Toledo Fierro (jtoledof@utem.cl)

Detección **no supervisada** de anomalías de comportamiento (rodeos, *holdings*, descensos anómalos,
*go-arounds*) en trayectorias de vuelo **reales** (ADS-B, OpenSky Network), ejecutada de forma
**distribuida** sobre un **orquestador de tareas propio** (coordinador + agentes, paso de mensajes por
TCP, cola dinámica y tolerancia a fallos), en modo local y en un clúster de VMs QEMU.

## Entregables
- `informe_final.pdf` — informe técnico (14 secciones).
- `presentacion_final.html` — presentación de defensa **interactiva** (abre offline por doble clic; navegación con ←/→, pantalla completa con `F`; ≤15 min).
- `demo_adsb/` — **código y prototipo reproducible**.
- `demo_adsb/results/tablas/` y `demo_adsb/results/graficos/` — **evidencia experimental** trazable.
- `demo_adsb/DOCUMENTACION.md` (teoría del sistema) · `demo_adsb/GUIA_EJECUCION.md` (guía paso a paso).

## Entorno de ejecución (declarado)
| | |
|---|---|
| Sistema operativo | Windows 11 (build 10.0.26200) |
| CPU | AMD Ryzen 7 6800H — 8 núcleos físicos / 16 hilos lógicos |
| Memoria | ~15 GB RAM |
| Python | 3.13.5 |
| Librerías | textual 8.2.7 · rich 15.0.0 · paramiko 5.0.0 · requests 2.32.3 · numpy 2.1.3 · pandas 2.2.3 · matplotlib 3.10.0 |
| Clúster | QEMU + Debian, 3 nodos (nodo0/1/2), acelerador WHPX |

> La **tarea, el coordinador y los agentes son *stdlib* puro**. `textual/rich/paramiko` son solo para
> la TUI y el clúster; `requests` para la ingesta; `numpy/matplotlib` para el benchmark y los gráficos.

## Estructura del repositorio (mapeo a la pauta)
| Estructura sugerida (pauta) | En este repositorio |
|---|---|
| `codigo/` | `demo_adsb/` — `tasks/`, `coordinator_generic.py`, `worker_agent.py`, `baseline_seq.py`, `tui/` |
| `datos/` | `demo_adsb/data/trayectorias_reales.json` (636 vuelos reales) |
| `resultados/tablas/` | `demo_adsb/results/tablas/` |
| `resultados/graficos/` | `demo_adsb/results/graficos/` |
| `anexos/` | `anexos/` + `demo_adsb/GUIA_EJECUCION.md` |
| `README.md` | este archivo |

## Instalación (una vez)
```powershell
python -m pip install -r demo_adsb/requirements-tui.txt   # textual, rich, paramiko (TUI/clúster)
python -m pip install requests numpy matplotlib           # ingesta + benchmark/gráficos
```

## Comandos de ejecución
Semilla fija **`seed=7`** en toda generación sintética e inyección de anomalías → resultados deterministas.

**Línea base / ejecución local rápida (un proceso, secuencial):**
```powershell
cd demo_adsb
python coordinator_generic.py --task tasks/task_adsb_real.py --local `
  --payload '{"data":"data/trayectorias_reales.json","n_chunks":8,"top_k":12,"inject":12,"seed":7}'
```

**Ejecución distribuida (con interfaz — recomendado):**
```powershell
.\run_adsb.ps1        # Modo "Local (2 agentes)" o "Clúster QEMU" → Ejecutar barrido → se abre el radar HTML
```
(Por CLI headless, ver `demo_adsb/GUIA_EJECUCION.md`.)

**Evaluación experimental (escalabilidad, p = 1,2,4,8, R = 3 repeticiones + calentamiento):**
```powershell
cd demo_adsb
python benchmark_escalabilidad.py     # -> results/tablas/escalabilidad.{csv,md}
python graficos.py                    # -> results/graficos/{speedup,eficiencia}.png
```

**Datos reales frescos (opcional, ya vienen incluidos):**
```powershell
python ingesta_adsb.py --source opensky --bbox 47,5,55,15 --snapshots 24 --interval 10
```

## Reproducibilidad
- **Semillas**: toda generación sintética y la inyección de anomalías usan `seed=7` (`random.Random`).
- **Datos**: 636 vuelos reales incluidos en `demo_adsb/data/`. Regenerar/ampliar con `ingesta_adsb.py`.
- **Trazabilidad**: cada corrida deja evidencia en `demo_adsb/results/<job-id>.json` (+ `.html`). Las
  tablas y gráficos se generan **solo** a partir de esas mediciones (no se editan a mano).
- **Advertencia metodológica de la pauta**: el *speedup* se reporta únicamente sobre pares
  baseline↔distribuido que producen **el mismo resultado** (equivalencia verificada automáticamente).
- **Separación**: datos (`data/`), código (`demo_adsb/`), resultados (`results/`) y gráficos
  (`results/graficos/`) están en carpetas distintas.

## Declaración de uso de IA generativa
En el desarrollo se utilizó un **asistente de programación basado en IA generativa** (Claude Code) como
apoyo para redacción de código, documentación y depuración. El grupo **comprende, validó y defiende**
todo lo entregado: el diseño de la arquitectura, la implementación y la interpretación de los resultados
fueron revisados, ejecutados y verificados por el equipo. Toda medición proviene de ejecuciones reales y
trazables (`demo_adsb/results/`). Ver anexo `anexos/DECLARACION_USO_IA.md`.
