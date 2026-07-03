# Guía de ejecución — Demo distribuida ADS-B (proyecto semestral)

Detección distribuida de anomalías en trayectorias de vuelo **reales** (OpenSky), con
TUI de torre de control y reporte HTML tipo *scope* de radar. Todo corre sobre el
**orquestador propio** (coordinador + agentes, TCP), sin Dask/Ray.

> Todos los comandos se ejecutan desde esta carpeta: `demo_adsb/`.
> En Windows usa **PowerShell**.

---

## 0. Requisitos (una sola vez)

- **Python 3.11+** (probado en 3.13).
- Dependencias de la **TUI**: `textual`, `rich`, `paramiko` (el lanzador las instala solo).
  - Manual: `python -m pip install -r requirements-tui.txt`
- Dependencia de la **ingesta** (solo si vas a descargar datos): `python -m pip install requests`
- La **tarea, el coordinador y los agentes son stdlib puro** (no requieren nada extra).

Los datos ya vienen incluidos: `data/trayectorias_reales.json` (636 vuelos reales). No
necesitas descargar nada para ejecutar la demo.

---

## 1. La forma fácil: la TUI (recomendada)

```powershell
.\run_adsb.ps1
```

Esto instala dependencias si faltan y abre la interfaz. Dentro de la TUI:

1. **Modo:** deja `Local (host, sin QEMU)` — corre en tu máquina, sin VMs.
2. **Payload:** ya viene relleno con los datos reales (no lo toques).
3. Pulsa **`▶ Ejecutar barrido`**.
   - Verás la **TORRE DE CONTROL** repartir los vuelos a los sectores (fases
     **1 SPLIT → 2 RUN → 3 MERGE**), las trazas viajar y las estaciones puntuar.
4. Al terminar se abre **solo** el reporte HTML (el radar con el ranking y las métricas).

Teclas: `q` = salir. La evidencia de cada corrida queda en `results/<job-id>.json` (+ `.html`).

---

## 2. (Opcional) Descargar/actualizar datos reales

Solo si quieres datos frescos o de otra región (ya hay 636 vuelos incluidos):

```powershell
python -m pip install requests   # una vez
python ingesta_adsb.py --source opensky --bbox 47,5,55,15 --snapshots 24 --interval 10
```

- Descarga vuelos reales de **OpenSky Network** (anónimo, sin cuenta) y los guarda en
  `data/trayectorias_reales.json` (tarda ~4 min: hace 24 *snapshots* cada 10 s).
- `--bbox lat_min,lon_min,lat_max,lon_max` define la zona (por defecto Europa central,
  mucho tráfico). Cámbiala para otra región.

---

## 3. Modo CLÚSTER QEMU (VMs reales)

Para correr sobre las máquinas virtuales QEMU en vez del host:

1. Levanta las VMs `nodo1`/`nodo2` con sus puertos reenviados (agente en `9001`/`9002`,
   SSH en `2221`/`2222`) — ver `lab6_qemu/orquestador/ACCESO_VMS.md`. La topología está
   en `workers.host.json`.
2. En la TUI: **Modo `Clúster QEMU`** → **`⏻ Encender estaciones`** → espera a que la
   línea de estado diga *en línea (2/… )* → **`▶ Ejecutar barrido`**.
3. Para apagarlas: **`⏼ Apagar estaciones`** (o tecla `a` en el dashboard).

El coordinador corre en el host y despliega el agente + la tarea a cada VM por SSH/SFTP.

---

## 4. Por línea de comandos (headless / para evidencia)

**Rápido (un solo proceso, sin red — no genera HTML):**
```powershell
$env:PYTHONIOENCODING="utf-8"
python coordinator_generic.py --task tasks/task_adsb_real.py --local --payload '{"data":"data/trayectorias_reales.json","n_chunks":8,"top_k":12,"inject":12,"seed":7,"z_threshold":4.0}'
```

**Distribuido local (genera `results/<job>.json` y luego el HTML):**
```powershell
# 1) levanta 2 agentes (en dos terminales, o en segundo plano)
python worker_agent.py --port 9101 --task-dir tasks
python worker_agent.py --port 9102 --task-dir tasks

# 2) lanza el coordinador contra ellos
$env:PYTHONIOENCODING="utf-8"
python coordinator_generic.py --task tasks/task_adsb_real.py --workers workers.local.json --no-deploy --payload '{"data":"data/trayectorias_reales.json","n_chunks":8,"top_k":12,"inject":12,"seed":7,"z_threshold":4.0}'

# 3) genera el reporte HTML desde la evidencia
python adsb_report.py results\<job-id>.json
```

(Para el clúster QEMU por CLI: usa `--workers workers.host.json --deploy` con las VMs arriba.)

---

## 5. Estudio de escalabilidad (speedup / eficiencia / overhead)

Mide `Sp = T1/Tp`, `Ep = Sp/p` y overhead para varios números de nodos `p`, sobre la
tarea con cómputo denso (la de datos reales es I/O-bound → no escala, es la lección de
granularidad):

```powershell
python benchmark_escalabilidad.py           # p = 1, 2, 4
python benchmark_escalabilidad.py 1 2 4 8   # a medida
```

Imprime la tabla y la guarda en `results/escalabilidad.md`. Resultado de referencia
(4 núcleos locales): **Sp = 1.12 → 1.85 → 3.29** para p = 1 → 2 → 4 (Ep ≈ 0.82–0.93).

---

## 6. Regenerar el reporte HTML de una corrida

```powershell
python adsb_report.py results\<job-id>.json
# abre el .html generado junto al .json
```

---

## 7. Recompilar el documento del proyecto (PDF)

```powershell
latexmk -pdf ..\documento_proyecto.tex   # requiere MiKTeX / LaTeX
```

---

## Mapa rápido

| Quiero… | Comando |
|---|---|
| Correr la demo con interfaz | `.\run_adsb.ps1` → Ejecutar barrido |
| Datos reales frescos | `python ingesta_adsb.py --source opensky --bbox …` |
| Correr sin interfaz | `python coordinator_generic.py --task tasks/task_adsb_real.py --local --payload '…'` |
| Medir speedup/eficiencia | `python benchmark_escalabilidad.py` |
| Rehacer el HTML de un job | `python adsb_report.py results\<job>.json` |

*Documentación teórica completa: `DOCUMENTACION.md`.*
