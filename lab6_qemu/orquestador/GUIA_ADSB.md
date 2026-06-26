# Guía de ejecución — Demo ADS-B (detección de anomalías de vuelos)

Detección **distribuida** de anomalías en trayectorias de aviones (ADS-B) sobre el
orquestador de tareas QEMU. Es una **tarea enchufable** (`tasks/task_adsb.py`) más un
**reporte HTML animado** (`adsb_report.py`); el motor (coordinador, agente, baseline,
TUI) no se modificó.

**Qué hace:** genera trayectorias sintéticas (vuelos normales + anomalías inyectadas:
*rodeo, holding, descenso anómalo, go-around*), les calcula *features* de comportamiento
(desvío de ruta, curvatura, tasa vertical) y las puntúa con un detector **no
supervisado z-robusto (MAD)**. Devuelve el **ranking top-k** de los vuelos más anómalos
y, al terminar desde la TUI, **abre un HTML** con un *scope* de radar.

> Todo es **Python stdlib puro** y **reproducible por semilla**. Probado en Python 3.13.

---

## 0. Prerrequisitos

```powershell
cd C:\Users\welin\Desktop\universidad\Paralela\Paralelismo_con_qemu\orquestador
python -m pip install -r requirements-tui.txt   # solo para la TUI: textual, rich, paramiko
```

- Para los modos **Local** no necesitas QEMU.
- Para el modo **Cluster** necesitas el clúster QEMU extraído en `C:\qemu-cluster-demo`
  y la llave `C:\Users\welin\.ssh\qemu_cluster` (ya presentes en este equipo).

---

## 1. Forma rápida y recomendada — desde la TUI

```powershell
cd C:\Users\welin\Desktop\universidad\Paralela\Paralelismo_con_qemu\orquestador
.\run_tui.ps1
```

En el menú (Launcher):

1. **Tarea:** `ADS-B anomalias (ranking top-k)`
2. **Modo:**
   - `Local (host, sin QEMU)` → levanta 2 agentes en tu PC (sin VMs). **El más simple.**
   - `Cluster QEMU (nodo1/nodo2)` → usa las VMs (pulsa antes **⏻ Despertar clúster QEMU**).
3. **Payload:** se autocompleta; puedes editarlo (ver §3).
4. Pulsa **▶ Ejecutar**.

Verás en vivo: el reparto de *chunks* entre los workers, el flujo de datos, la barra de
progreso y el **speedup**. **Al terminar, el HTML se genera y se abre solo** en el
navegador (la ruta también aparece en el *event-log*: `results\<job_id>.html`).

> Para el modo Cluster: primero **⏻ Despertar clúster QEMU** (aparecen/arrancan las VMs;
> ~20 s con WHPX), espera a `✓ nodo0 ✓ nodo1 ✓ nodo2`, y luego **▶ Ejecutar**. Al final,
> **⏼ Apagar clúster**.

---

## 2. Por línea de comandos (sin TUI)

Todos los comandos van desde `...\Paralelismo_con_qemu\orquestador`.

### 2.1 Prueba mínima (health-check de la tarea)
```powershell
python -c "import importlib.util as u;s=u.spec_from_file_location('t','tasks/task_adsb.py');m=u.module_from_spec(s);s.loader.exec_module(m);c,e=m.self_test();print('self_test:', 'OK' if m.run(c)==e else 'FALLO')"
```

### 2.2 Baseline secuencial (denominador del speedup)
```powershell
python baseline_seq.py --task tasks/task_adsb.py --payload '{"seed":7,"num_traj":60000,"n_chunks":40,"anomaly_rate":0.01,"top_k":10,"n_routes":6,"z_threshold":4.0}'
```
Anota el valor `elapsed (s)` que imprime: es el `<BASE>` de los pasos siguientes.

### 2.3 Local en un proceso (sin red — valida correctitud)
```powershell
python coordinator_generic.py --task tasks/task_adsb.py --local --payload '{"seed":7,"num_traj":60000,"n_chunks":40,"anomaly_rate":0.01,"top_k":10,"n_routes":6,"z_threshold":4.0}'
```

### 2.4 Distribuido en el host (2 agentes — speedup real, sin QEMU)
Abre **3 terminales** en la misma carpeta:
```powershell
# Terminal A
python worker_agent.py --port 9101 --task-dir tasks
# Terminal B
python worker_agent.py --port 9102 --task-dir tasks
# Terminal C (coordinador) — reemplaza <BASE> por el elapsed del baseline
python coordinator_generic.py --task tasks/task_adsb.py --workers workers.local.json --no-deploy --baseline <BASE> --payload '{"seed":7,"num_traj":60000,"n_chunks":40,"anomaly_rate":0.01,"top_k":10,"n_routes":6,"z_threshold":4.0}'
```

### 2.5 Distribuido en el clúster QEMU (2 VMs Alpine)
```powershell
# 1) Levantar las VMs (una vez). Más fácil con el botón de la TUI; o:
powershell -ExecutionPolicy Bypass -File C:\qemu-cluster-demo\scripts\start-all.ps1
# 2) Desplegar la tarea por SFTP y ejecutar (reemplaza <BASE>)
python coordinator_generic.py --task tasks/task_adsb.py --workers workers.host.json --deploy --ssh-key C:\Users\welin\.ssh\qemu_cluster --baseline <BASE> --payload '{"seed":7,"num_traj":60000,"n_chunks":40,"anomaly_rate":0.01,"top_k":10,"n_routes":6,"z_threshold":4.0}'
```
`--deploy` copia `worker_agent.py` + `task_adsb.py` a cada VM (solo si cambió el `sha256`),
arranca el agente y hace un *health-check* funcional antes de repartir.

### 2.6 Generar el HTML desde una corrida (los modos CLI no lo abren solo)
```powershell
python adsb_report.py results\<job_id>.json     # crea results\<job_id>.html
.\results\<job_id>.html                          # o doble clic
```

---

## 3. Parámetros del payload

| Clave | Significado | Sugerido |
|---|---|---|
| `seed` | Semilla maestra (reproducibilidad total) | `7` |
| `num_traj` | Nº de trayectorias a generar y analizar | `60000` (sube para más cómputo/speedup) |
| `n_chunks` | En cuántos trozos se divide (granularidad del paralelismo) | `40` |
| `anomaly_rate` | Fracción de vuelos anómalos inyectados | `0.01` (1 %) |
| `top_k` | Cuántas anomalías top se rankean y dibujan | `10` |
| `n_routes` | Rutas canónicas a usar (máx. 6) | `6` |
| `z_threshold` | Umbral de score robusto para contar una detección | `4.0` |

> **Para que el speedup se note:** sube `num_traj` (p. ej. `120000`). Con poco cómputo
> por *chunk*, la red/overhead domina y el speedup baja — es un resultado normal y honesto.

---

## 4. Cómo leer los resultados

**En la terminal / `results\<job_id>.json`** (clave `result`):

| Métrica | Qué mide |
|---|---|
| `precision_at_k` | De las top-k mostradas, fracción que son anomalías reales (≈ 1.0) |
| `recall` | De todas las anomalías inyectadas, cuántas superan `z_threshold` |
| `false_positive_rate` | Vuelos normales marcados por error |
| `speedup` | `baseline / distribuido` |
| `top_k` | Las k trayectorias más anómalas (id, ruta, score, tipo, *path*) |
| `examples_by_type` | Un ejemplo de cada patrón (rodeo/holding/descenso/go-around) |

**En el HTML** (`results\<job_id>.html`): un *scope* de radar con las trayectorias
trazándose y aviones recorriéndolas (halo en la maniobra), **flight strips** con el
ranking (pasa el cursor para fijar un contacto), tarjetas de métricas, los 4 patrones y
el reparto de *chunks* por worker. Es autocontenido: **abre sin internet**.

---

## 5. Resultados de referencia (medidos en este equipo)

| Modo | speedup | recall | precision@10 | notas |
|---|---|---|---|---|
| Local 2 agentes (`num_traj=60000`) | **1.68×** | 1.0 | 1.0 | reparto 20/20 chunks |
| Cluster QEMU 2 VMs (`num_traj=6000`) | **1.29×** | 1.0 | 1.0 | reparto 6/6, VMs 1 vCPU |

El **top-k** suele estar dominado por *holdings* (son los más extremos
estadísticamente); por eso el HTML muestra además un ejemplo de **cada** patrón.

---

## 6. Qué demuestra (para la presentación)

- **Tarea propia no trivial** sobre el orquestador, sin tocar la plataforma.
- **5ª semántica de `merge`**: *ranking top-k* (las otras 4: suma escalar, suma de
  dicts, consolidación, argmax) → refuerza que la plataforma es genérica.
- **Datos por semilla** → cero transferencia y evidencia reproducible.
- **Detección de anomalías no supervisada** (z-robusto/MAD) con métricas honestas.
- Hereda del motor: **cola dinámica, tolerancia a fallos, speedup vs baseline**.
- Conecta con el **proyecto semestral** (etapa de *scoring* embarrassingly-parallel).

---

## 7. Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `ModuleNotFoundError: textual` | `python -m pip install -r requirements-tui.txt` |
| El HTML no se abrió solo (modo CLI) | normal: genera con `python adsb_report.py results\<job_id>.json` y ábrelo |
| `speedup` < 1 | sube `num_traj`; con poco cómputo la red domina |
| Cluster: `nodoX: no respondió SSH` | espera el boot; revisa la llave `qemu_cluster` y que WHPX esté activo |
| Payload inválido | en PowerShell usa comillas simples: `--payload '{"...":...}'` |
| El menú no muestra ADS-B | confirma que `tasks/task_adsb.py` existe y reabre la TUI |

---

## 8. Archivos de la demo

```
orquestador/
├─ tasks/task_adsb.py     # la tarea (split/run/merge/self_test) — stdlib puro
├─ adsb_report.py         # generador del HTML (radar animado, autocontenido)
├─ tui/payloads.py        # +1 línea: registro en el menú
├─ tui/app.py             # +bloque: al terminar un job ADS-B genera y abre el HTML
└─ results/<job_id>.json  # evidencia de cada corrida (+ .html del reporte)
```
