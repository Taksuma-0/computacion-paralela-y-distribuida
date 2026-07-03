# Sistema de detección distribuida de anomalías ADS-B — Documentación técnica

> Documento de **fundamento y funcionamiento** (teoría + práctica) del sistema.
> Computación Paralela y Distribuida · Ingeniería Civil en Ciencia de Datos · UTEM.
> Acompaña a `GUIA_ADSB.md` (cómo ejecutarlo). Aquí se explica **qué hace, cómo
> funciona por dentro, la teoría que lo sustenta, y qué muestran la TUI y el HTML.**

---

## 0. Resumen ejecutivo

El sistema toma **trayectorias de vuelos** (secuencias de posición/altitud, en el formato
conceptual de **ADS-B**), les calcula rasgos de comportamiento y **detecta las más
anómalas** con un método estadístico **no supervisado** (z-score robusto / MAD). El
cómputo se **reparte entre varias máquinas** (procesos en el host o VMs QEMU) mediante un
**orquestador de tareas distribuidas** propio, se **mide el speedup** contra una ejecución
secuencial, y los resultados se presentan en una **TUI** (en vivo) y en un **HTML
interactivo** con forma de *scope* de radar de control aéreo.

Tres ideas centrales:
1. **Separación plataforma/dominio.** La plataforma (coordinador + agentes) no sabe de
   aviones; la lógica ADS-B es un *plugin* (`tasks/task_adsb.py`) con un contrato fijo.
2. **Paralelismo de datos vergonzosamente paralelo.** Cada trozo de trayectorias se puntúa
   de forma independiente → reparto natural entre nodos.
3. **Evidencia reproducible.** Los datos se regeneran por **semilla** (no se transfieren),
   así el resultado es idéntico en cualquier máquina y se puede auditar.

---

## 1. Qué hace hoy el sistema (estado real)

| Capacidad | Estado |
|---|---|
| Generar trayectorias sintéticas (normales + anómalas con *ground-truth*) | ✅ |
| Extraer *features* de comportamiento (desvío de ruta, curvatura, tasa vertical) | ✅ |
| Puntuar anomalías sin supervisión (z-robusto / MAD) | ✅ |
| Repartir el cómputo entre 2+ workers (local) o 2 VMs QEMU (clúster) | ✅ |
| Tolerancia a fallos (reintentos, health-check, reparación) | ✅ (heredada del motor) |
| Medir speedup vs baseline secuencial | ✅ |
| TUI en vivo (reparto, progreso, speedup) | ✅ |
| Reporte HTML interactivo (radar, ranking, métricas) | ✅ |
| Datos reales de OpenSky a escala TB | ❌ (es el objetivo del proyecto final; aquí es PoC sintética) |

**Importante:** trabaja sobre **datos sintéticos** generados por semilla, con anomalías
**inyectadas a propósito** (sabemos cuáles son). Eso permite medir la calidad de la
detección (recall/precisión) de forma honesta. No usa todavía datos reales ni entrena un
modelo de ML clásico (ver §8).

---

## 2. El problema: anomalías en trayectorias ADS-B

**ADS-B** (*Automatic Dependent Surveillance–Broadcast*) es el sistema por el cual cada
aeronave **emite periódicamente** su estado: identificador, posición (lat/lon), altitud,
velocidad, rumbo, etc. De esa emisión se reconstruye la **trayectoria** de cada vuelo.

Una **anomalía de comportamiento** es una trayectoria que se desvía del patrón esperado
para su ruta. El sistema modela cuatro patrones:

| Tipo | Qué es | Cómo se ve |
|---|---|---|
| **rodeo** | Desvío lateral grande respecto a la ruta directa | "joroba" hacia un lado |
| **holding** | Espera dando vueltas (circuito de espera) | rizo / bucle |
| **descenso_anómalo** | Caída de altitud sostenida fuera de lo normal | perfil vertical roto |
| **go_around** | Aproximación frustrada: baja y vuelve a subir | descenso + reascenso |

Detectarlas y **rankearlas** habilita análisis de seguridad operacional, eficiencia de
rutas y caracterización de tráfico no rutinario.

---

## 3. Arquitectura general

```
        ┌─────────────────────────── HOST (tu PC) ───────────────────────────┐
        │                                                                     │
        │   TUI (Textual)  ──lanza──►  COORDINADOR (coordinator_generic.py)   │
        │   tui/app.py                 - split() -> N chunks                   │
        │   - launcher                 - cola dinámica + reintentos           │
        │   - dashboard (vivo)         - merge() -> resultado final           │
        │   - abre el HTML al final    - mide speedup vs baseline             │
        │        ▲                              │   mensajes JSON (TCP)        │
        │        │ eventos (EventBus)           ▼                             │
        └────────┼──────────────────────────────┼─────────────────────────────┘
                 │                               │
        ┌────────┴───────┐            ┌──────────┴───────────┐   ... (N workers)
        │ adsb_report.py │            │  AGENTE (worker_agent)│
        │  genera el HTML│            │  - servidor TCP :9000 │
        └────────────────┘            │  - importa la tarea   │
                                      │  - ejecuta run(chunk) │
                                      └───────────┬───────────┘
                                                  │  usa
                                       ┌──────────┴───────────┐
                                       │  tasks/task_adsb.py   │  ← ÚNICO código de dominio
                                       │  split / run / merge  │
                                       └──────────────────────┘
```

**Piezas:**

| Pieza | Archivo | Rol |
|---|---|---|
| Coordinador | `coordinator_generic.py` | Parte el trabajo, reparte, reintenta, combina, mide. **No conoce el dominio.** |
| Agente | `worker_agent.py` | Corre en cada worker/VM; recibe un chunk, ejecuta `run`, devuelve el parcial. **No conoce el dominio.** |
| Tarea | `tasks/task_adsb.py` | La lógica ADS-B (generación + *features* + *scoring*). **Único código de dominio.** |
| Baseline | `baseline_seq.py` | Ejecuta todo secuencial: denominador honesto del speedup. |
| TUI | `tui/app.py` (+ paquete) | Interfaz: menú + tablero en vivo; abre el HTML al terminar. |
| Reporte | `adsb_report.py` | Genera el HTML autocontenido (radar). |
| Evidencia | `results/<job_id>.json` (+ `.html`) | Registro reproducible de cada corrida. |

---

## 4. Teoría: computación paralela y distribuida

### 4.1 Descomposición y reducción (MapReduce simplificado)
El patrón es **dividir → procesar en paralelo → combinar**:
- **split** (descomposición de dominio): parte el problema en `N` *chunks* independientes.
- **run** (*map*): procesa un chunk de forma pura e idempotente.
- **merge** (*reduce*): combina los parciales en el resultado final.

Es paralelismo **de datos**: la misma operación (`run`) sobre porciones distintas de datos.

### 4.2 Por qué es "vergonzosamente paralelo"
Cada chunk se puntúa **sin comunicación** con los demás (no hay estado compartido durante
`run`). Esto elimina la sincronización fina y hace el reparto trivial y escalable — el caso
ideal del paralelismo de datos.

### 4.3 Balanceo: cola dinámica (modelo *pull* / *work-stealing*)
En vez de repartir los chunks de forma fija, hay **una cola** y **un hilo por worker** que
**tira** (saca) un chunk cuando queda libre. El worker más rápido procesa más chunks →
**balanceo automático**, sin asumir que todos van al mismo ritmo (clave cuando las VMs son
heterogéneas o el host tiene otra carga).

### 4.4 Paso de mensajes (no memoria compartida)
Los workers son **procesos/máquinas separados**: no comparten memoria. Se comunican por
**TCP con JSON**, un mensaje por línea (terminado en `\n`):

```jsonc
// coordinador -> agente
{"job_id":"...", "chunk_id":7, "task_name":"task_adsb", "chunk":{...}}
// agente -> coordinador
{"ok":true, "chunk_id":7, "worker":"nodo1", "result":{...}, "seconds":0.13}
```

Se usa **TCP** (no UDP) porque los chunks y parciales **no pueden perderse ni
desordenarse**: TCP da entrega garantizada, orden e integridad sin reimplementarlos. Es un
**sistema distribuido real** (paso de mensajes), no hilos sobre memoria común.

### 4.5 Tolerancia a fallos
- **Health-check funcional:** antes de repartir, el coordinador manda un `self_test` al
  worker y **exige el resultado correcto** (no basta con que el puerto esté abierto).
- **Reintentos:** si `run` lanza excepción, el chunk se reintenta hasta `max_retries`; si
  se agota, se **abandona** sin invalidar el job.
- **Reparación / degradación:** si cae la VM, el coordinador la **repara por SSH** o
  reparte su trabajo entre las vivas (los chunks se re-encolan; no se pierden ni duplican).

### 4.6 Datos por semilla (determinismo)
Los chunks **no transportan datos**; llevan una **semilla** + parámetros, y `run` los
**regenera** con `random.Random(semilla)`. El generador (Mersenne Twister) es determinista
e **idéntico entre máquinas** → cero transferencia de datos + **resultado 100%
reproducible**. La semilla por chunk se deriva con una mezcla aritmética estable
(`derive_seed`), **no** con `hash()` (que Python aleatoriza por proceso).

### 4.7 Medición: speedup, eficiencia, overhead
Con `T₁` = tiempo secuencial (baseline) y `Tₚ` = tiempo con `p` workers:

```
Speedup     Sₚ = T₁ / Tₚ
Eficiencia  Eₚ = Sₚ / p
Overhead    O  = p · Tₚ − T₁      (coste de coordinar/comunicar)
```

**Ley de Amdahl** (límite teórico): si una fracción `f` del trabajo es serial,
`Sₚ ≤ 1 / (f + (1−f)/p)`. Por eso, y por el **overhead de red**, el speedup no crece sin
límite ni es necesariamente `> 1`: si el cómputo por chunk es pequeño, la comunicación
domina y `Sₚ < 1`. **Subir `num_traj`** (más cómputo por chunk) amortiza el overhead y
sube el speedup. *Reportar un speedup bajo cuando el cómputo es liviano es un resultado
honesto, no un fallo.*

---

## 5. El contrato de tarea (corazón del diseño)

Toda tarea `tasks/task_*.py` implementa cuatro funciones puras:

```python
def split(payload: dict, workers: list) -> list[dict]   # divide en chunks autosuficientes
def run(chunk: dict) -> dict                             # procesa UN chunk (puro, stdlib)
def merge(results: list[dict]) -> dict                   # combina los parciales
def self_test() -> tuple[dict, dict]                     # (chunk_trivial, resultado_esperado)
```

La plataforma es **agnóstica**: el mismo coordinador y agente sirven para contar primos,
WordCount, ETL o **detectar anomalías**, sin cambiar una línea. La tarea ADS-B aporta una
**quinta semántica de `merge`**: *ranking top-k* (las otras cuatro del proyecto son suma
escalar, suma de diccionarios, consolidación y argmax).

---

## 6. La tarea ADS-B en profundidad

### 6.1 Generación de datos por semilla
- **6 rutas canónicas** (pares origen-destino con coordenadas y altitud de crucero):
  `SCL-LIM, SCL-EZE, SCL-GRU, LIM-BOG, SCL-ANF, EZE-GRU`. Geometrías variadas para que las
  *features* "normales" sean estables **dentro de cada ruta** pero distintas entre rutas.
- **Una trayectoria** = polilínea de `N_WAYPOINTS = 30` puntos `(lat, lon, alt)`,
  interpolando origen→destino + **ruido gaussiano** (lateral ~0.03°, altitud ~80 ft).
- Con probabilidad `anomaly_rate` (≈ 1%), la trayectoria se marca anómala y se le
  **inyecta** la perturbación de uno de los 4 tipos (magnitud tomada del propio RNG →
  reproducible). El generador **sabe** cuáles inyectó → eso es el ***ground-truth***.

Cada trayectoria `j` usa su propio `random.Random(derive_seed(chunk_seed, j))`, así el
resultado no depende del orden ni del número de workers.

### 6.2 Features de comportamiento (sólo `math`)
Sobre los 30 puntos de cada trayectoria se calculan tres rasgos:

| Feature | Fórmula (idea) | Qué captura |
|---|---|---|
| `len_ratio` | `Σ haversine(pᵢ,pᵢ₊₁) / haversine(p₀,p_fin)` | **Desvío de ruta**: longitud real ÷ distancia directa. Normal ≈ 1.0; rodeo/holding ↑ |
| `turn_sum` | `Σ |Δ rumbo|` entre segmentos | **Curvatura/zigzag**: un holding da cientos de grados |
| `vrate_max` | `máx |Δ altitud|` entre puntos | **Tasa vertical**: descenso/go-around la disparan |

- **haversine** (distancia sobre la esfera): 
  `d = 2R·asin(√(sin²(Δφ/2) + cosφ₁·cosφ₂·sin²(Δλ/2)))`.
- **rumbo** (*bearing*) entre dos puntos: `atan2(sinΔλ·cosφ₂, cosφ₁·sinφ₂ − sinφ₁·cosφ₂·cosΔλ)`.
- La diferencia angular usa `min(d, 360−d)` para no contar el "salto" 359°→0°.
- Todo se acota (`+ε`, `min(1,·)`, `max(alt,0)`) para que **nunca** salga NaN/Inf
  (el protocolo serializa con `allow_nan=False`).

### 6.3 Scoring: z-score robusto / MAD (la "teoría dura")
**Objetivo:** medir cuán "rara" es cada trayectoria respecto a sus pares, sin etiquetas.

El z-score clásico `(x − media) / desviación_estándar` **falla** aquí: la media y la
desviación estándar son **sensibles a outliers** — y los outliers son justo lo que
queremos detectar. Una sola anomalía contamina los estadísticos y "esconde" a las demás
(efecto *masking*).

Solución: estadísticos **robustos**.
- **Mediana** `med`: estimador de centro con punto de ruptura del 50% (la mitad de los
  datos pueden ser basura y sigue siendo válida).
- **MAD** (*Median Absolute Deviation*): `MAD = mediana(|xᵢ − med|)`. Estimador robusto de
  escala (dispersión).
- **Factor de consistencia 1.4826:** para datos normales, `1.4826 · MAD ≈ σ`. Así el score
  robusto queda en "unidades de desviación estándar" comparables a un z clásico.

**Score de una trayectoria:**
```
z_f(x) = |x − med_f| / (1.4826 · MAD_f + ε)        para cada feature f
score  = máx_f  z_f(x)        ;     reason = argmax_f  z_f(x)
```
Se toma el **máximo** sobre las 3 features (basta con ser extremo en **una** para ser
anómalo), y se guarda **qué feature** lo disparó (`reason`), que es interpretable.

**Cómputo por ruta dentro del chunk.** `med` y `MAD` se calculan **por ruta** (no
mezclando rutas con geometrías distintas) y **dentro de cada chunk**.

> **Supuesto explícito (honesto):** cada partición estima su **propia** línea base robusta
> por ruta. Como `split` reparte la **misma mezcla uniforme de rutas** a cada chunk, las
> medianas/MAD son estadísticamente equivalentes entre chunks → los `score` son
> **comparables** y se pueden fusionar por simple orden global en `merge`. Si un chunk
> tuviera pocas muestras de una ruta (< 15), se usa como respaldo la estadística global del
> chunk para esa feature (evita un MAD inestable).

### 6.4 `run` → `merge` (ranking top-k global)
- **`run(chunk)`** devuelve: el **top-k local** (las `k` de mayor score, **con su `path`**
  para dibujarlas), el **mejor ejemplo de cada tipo** (`best_by_type`, para que el HTML
  muestre los 4 patrones aunque el top esté dominado por uno), y **conteos** (`n_traj`,
  `n_injected`, `n_normal`, `tp`, `fp`).
- **`merge(results)`** funde los top-k locales, ordena por score y se queda con las `k`
  globales; consolida un ejemplo por tipo; y agrega las métricas (abajo).

> Solo el top-k transporta la polilínea completa (≈ 16 KB por chunk) → mensajes livianos.

### 6.5 Métricas (qué significan)
| Métrica | Definición | Qué mide |
|---|---|---|
| `precision_at_k` | (inyectadas dentro del top-k) / k | Calidad del **ranking**: de las k mostradas, cuántas eran reales |
| `recall` | `tp / n_injected` con `score ≥ z_threshold` | Calidad de la **detección**: qué fracción de las anomalías reales se detecta |
| `false_positive_rate` | `fp / n_normal` | Cuántos vuelos normales se marcan por error |
| `precision_threshold` | `tp / (tp + fp)` | Precisión del detector a ese umbral |

Se reportan **dos** miradas a propósito: el **top-k** (ranking, lo visual) y las métricas
**a umbral** (`z_threshold = 4.0`) sobre todo el dataset. El `recall@k` "crudo" sería
engañoso porque suele haber **muchas más** anomalías que `k`.

---

## 7. ¿Se "entrena"? — qué pasa exactamente al ejecutar un job

**Aclaración importante.** En sentido estricto **no hay entrenamiento** (no es ML
supervisado, no hay épocas ni pesos que se ajustan). Es **detección no supervisada de una
sola pasada**: el "modelo" es la **estadística robusta (mediana/MAD) estimada de los
propios datos** en el momento. Por eso decimos "ejecutar un job" más que "entrenar".

**Ciclo de un job, paso a paso:**
1. **Baseline.** El coordinador corre `split → run(todos) → merge` **secuencial** en el
   host y cronometra `T₁` (denominador del speedup).
2. **Preparar workers.** (Local: levanta 2 agentes; Clúster: despliega por SFTP el agente
   + la tarea y los arranca por SSH.) **Health-check funcional** con `self_test`.
3. **split.** Se generan `N = n_chunks` chunks (cada uno con `chunk_seed`, `num_traj`,
   `traj_offset`, `anomaly_rate`, `top_k`, `n_routes`, `z_threshold`).
4. **Reparto (cola dinámica).** Cada worker tira un chunk, ejecuta `run` (genera sus
   trayectorias, calcula features, puntúa por MAD, arma su top-k) y devuelve el parcial.
5. **merge.** Se fusionan los top-k → ranking global + métricas; se calcula `Sₚ = T₁/Tₚ`.
6. **Evidencia + reporte.** Se escribe `results/<job_id>.json` y, desde la TUI, se genera y
   **abre el HTML**.

---

## 8. Modos de ejecución

| Modo | Cómo | Para qué |
|---|---|---|
| `--local` (1 proceso) | `coordinator_generic.py --local` | Validar correctitud (sin red) |
| **Local (2 agentes)** | TUI modo *Local* / `--workers workers.local.json --no-deploy` | Speedup real **sin** QEMU (2 procesos en el host, puertos 9101/9102) |
| **Clúster QEMU** | TUI modo *Cluster* / `--workers workers.host.json --deploy` | Distribución real en 2 VMs Alpine (deploy SFTP, puertos 9001/9002) |

El **código de la tarea no cambia** entre modos: es la prueba de que la plataforma es
genérica y de que el paralelismo es real (los *hostnames* de los workers aparecen en la
evidencia).

---

## 9. Qué muestra la TUI

La TUI (Textual) tiene **dos pantallas** y consume un **EventBus** (cola *thread-safe*) que
los hilos de trabajo alimentan; la app lo drena cada 100 ms y actualiza los widgets.

### 9.1 Launcher (menú)
- **Banner:** logo de **avión** (vista de planta, verde/ámbar) + **escudo UTEM** + wordmark
  *ADS-B ANOMALY SCOPE*.
- **Tarea:** fija en *ADS-B* (esta TUI es exclusiva de la tarea).
- **Modo:** Local / Cluster QEMU.
- **Payload:** JSON editable (parámetros del job).
- **Botones:** ⏻ Despertar clúster · ▶ Ejecutar · ⏼ Apagar clúster · Salir.
- **Línea de estado** del clúster y **log**.

### 9.2 Dashboard (durante el job)
| Widget | Qué muestra |
|---|---|
| **WorkerPanel** (uno por worker) | Estado, nº de chunks hechos, tiempo ocupado, chunk actual y la **salida real** del worker |
| **ClusterFlow** | Animación de los **paquetes** viajando (chunk → worker en verde, parcial ← en azul) + *sparkline* de throughput |
| **GlobalProgress** | Barra de progreso (chunks completados / total) |
| **SpeedupCard** | Speedup (verde si > 1) |
| **event-log** | Traza de eventos del coordinador |

**Eventos** que mueven el tablero: `job_start → worker_ready → chunk_assigned →
chunk_done (×N) → [chunk_retry / worker_repair / worker_dropped] → job_done`. Al recibir
`job_done` con `task_name == "task_adsb"`, la app **genera y abre el HTML** (en un hilo,
desde el `record` en memoria, sin congelar la interfaz).

---

## 10. Qué muestra el HTML

`adsb_report.py` produce un **único `.html` autocontenido** (CSS + JS *vanilla*, **sin
CDNs** → abre sin internet). Estética de **scope de radar de control aéreo** (oscuro,
fósforo verde, acentos por tipo de anomalía).

| Componente | Qué es |
|---|---|
| **Barra de estado** | Contactos, inyectadas, nodos, chunks, tiempo, `job_id` |
| **Radar PPI** | Anillos de rango + azimut 000–360 + **barrido** giratorio; las trayectorias top-k **se trazan** (animación `stroke-dashoffset`) y un **avión ✈** las recorre (orientado por su rumbo); **halo pulsante** en el punto de la maniobra; color por tipo |
| **Flight strips** | Ranking top-k estilo torre de control (id, ruta, tipo, `reason`, score, barra). *Hover* ↔ resalta la trayectoria en el radar y muestra su *datablock* |
| **Tarjetas de métricas** | `precision@k`, `recall`, `FPR`, `speedup`, `TP/FP` con animación *count-up* |
| **Patrones de maniobra** | Mini-scope con **un ejemplo de cada tipo** (rodeo / holding / descenso / go-around) |
| **Cómputo distribuido** | Barras de **chunks por worker** + *sparkline* de **tiempo por chunk** (evidencia del reparto) |

Animaciones (JS estándar del navegador): trazado progresivo de rutas, avión moviéndose
(`getPointAtLength`), halo (`@keyframes`), barrido del radar y *count-up* de métricas.
Respeta `prefers-reduced-motion`.

---

## 11. Resultados medidos (en este equipo)

| Modo | `num_traj` | speedup | recall | precision@10 | FPR | reparto |
|---|---|---|---|---|---|---|
| Local (2 agentes) | 60 000 | **1.68×** | 1.0 | 1.0 | ~0.4 % | 20/20 chunks |
| Local autónomo (demo_adsb) | 4 000 | **1.97×** | 1.0 | 1.0 | — | 8 chunks |
| Clúster QEMU (2 VMs Alpine) | 6 000 | **1.29×** | 1.0 | 1.0 | ~0.5 % | 6/6 chunks |

En **todos** los modos el resultado (top-k, recall, precisión) es **idéntico** al baseline
secuencial → confirma **correctitud** además de velocidad. El recall alto y el FPR bajo se
deben a que las anomalías inyectadas quedan a **muchos MAD** de la mediana de su ruta,
mientras que el ruido normal raramente supera `z = 4`.

---

## 12. Limitaciones y supuestos honestos

- **Datos sintéticos**, no OpenSky real: las magnitudes de anomalía están calibradas para
  ser detectables; con datos reales el problema es más difícil (ruido, cobertura, etc.).
- **Scoring por partición**: depende del supuesto de homogeneidad entre chunks (§6.3); con
  datos reales habría que estimar la línea base de forma global o por ventana.
- **Speedup acotado** por Amdahl + overhead de red; en VMs de 1 vCPU emulado el margen es
  menor. Es esperable y honesto.
- **El top-k suele dominarlo el *holding*** (estadísticamente el más extremo); por eso se
  reporta además un ejemplo de cada tipo.
- No hay persistencia de las trayectorias completas (solo del top-k), para mantener los
  mensajes livianos (las VMs tienen 256 MB).

---

## 13. Glosario

- **ADS-B:** emisión periódica del estado de la aeronave (posición, altitud, …).
- **Chunk:** porción autosuficiente del trabajo (lleva semilla + parámetros).
- **MapReduce:** patrón dividir (*map*) → combinar (*reduce*).
- **Cola dinámica / *work-stealing*:** reparto *pull* donde cada worker tira trabajo al quedar libre.
- **MAD:** *Median Absolute Deviation*, estimador robusto de dispersión.
- **z-score robusto:** `|x − mediana| / (1.4826·MAD)`, número de "desviaciones robustas".
- **Ground-truth:** etiquetas verdaderas (aquí, qué trayectorias se inyectaron como anómalas).
- **precision@k / recall / FPR:** métricas de calidad de ranking y detección.
- **Speedup / eficiencia / overhead:** `T₁/Tₚ`, `Sₚ/p`, `p·Tₚ − T₁`.
- **PPI:** *Plan Position Indicator*, la pantalla circular clásica de un radar.

---

## 14. Relación con el proyecto semestral

Esta demo es una **prueba de concepto** de la etapa de *scoring* del proyecto semestral
(detección de anomalías ADS-B de OpenSky con pipeline distribuido). Valida el **patrón de
paralelización** (inferencia *embarrassingly-parallel* sobre particiones) y la **medición**
(speedup honesto, evidencia reproducible). El proyecto final escalará a **datos reales** y
evaluará **Dask/Ray** frente a este orquestador propio para esa etapa.

---

## 15. Versión con DATOS REALES (`task_adsb_real`)

Además de la versión sintética, el sistema incluye una variante que corre sobre **vuelos
reales de ADS-B** descargados de **OpenSky Network** (la fuente que cita el documento del
proyecto).

- **Ingesta** (`ingesta_adsb.py`, una vez, en el host): *polling* anónimo del endpoint
  `/states/all` de OpenSky sobre un *bounding box* (por defecto Europa central, mucho
  tráfico), agrupa los estados por `icao24` en trayectorias, limpia y **resamplea** cada
  vuelo a 40 puntos → `data/trayectorias_reales.json`. En una corrida se capturaron
  **636 vuelos reales**. (La librería `traffic` queda como fuente alternativa offline.)
- **Tarea** (`tasks/task_adsb_real.py`, stdlib): reutiliza las mismas *features* y el
  scoring z-robusto/MAD; `split()` carga los vuelos reales, **inyecta ~12 anomalías
  controladas sobre vuelos rectos** (evaluación *híbrida*) y reparte; `run()`/`merge()`
  producen el mismo `result` → **el HTML radar no cambia**.
- **Calibración para datos reales:** los vuelos reales son casi rectos → la MAD tiende a 0;
  se añade un **piso de escala por feature** (`FLOORS`) para no disparar el z-score de
  cualquier vuelo que solo curve un poco.

**Cómo leer las métricas con datos reales (honesto):**
- **RECALL** (sobre las inyectadas) = validación medible → **100 %** en la corrida.
- **HALLAZGOS** = vuelos reales genuinamente anómalos que aparecen en el top-k (holdings,
  aproximaciones). Es el valor de usar datos reales: en 636 vuelos de Europa el detector
  halló ~8 en el top-12.
- **precision@k / FPR**: con datos reales los "no inyectados" del top **no son errores**
  sino hallazgos; por eso `precision@k` sale baja aunque el detector funcione. Se reporta
  con esa salvedad (el HTML rotula "HALLAZGOS" en vez de "falsos positivos").
- **SPEEDUP < 1**: con solo 636 vuelos el cómputo es minúsculo → domina la red (esperado y
  honesto). El speedup se demuestra con la versión **sintética** (60.000 trayectorias, ~1.7×).

**Ejecutar:**
```powershell
python ingesta_adsb.py --source opensky --bbox 47,5,55,15 --snapshots 24 --interval 10
# en la TUI: elegir "ADS-B REAL (datos OpenSky)"; o por CLI:
python coordinator_generic.py --task tasks/task_adsb_real.py --local ^
  --payload '{"data":"data/trayectorias_reales.json","n_chunks":8,"top_k":12,"inject":12,"seed":7}'
```

---

### Mapa de archivos (referencia rápida)
```
demo_adsb/
├─ ingesta_adsb.py      # descarga datos REALES (OpenSky) -> data/trayectorias_reales.json
├─ tasks/task_adsb.py       # version sintetica (genera + features + scoring)
├─ tasks/task_adsb_real.py  # version REAL (lee vuelos reales + inyeccion hibrida)
├─ adsb_report.py       # genera el HTML (radar) — comun a ambas
├─ coordinator_generic.py / worker_agent.py / baseline_seq.py  # motor (agnóstico)
├─ tui/                 # interfaz (banner avión, dashboard; menú: sintética | REAL)
├─ data/trayectorias_reales.json   # vuelos reales ingeridos
└─ results/<job>.json   # evidencia (+ .html del reporte)
```
*Documento complementario:* `GUIA_ADSB.md` (comandos paso a paso para ejecutarlo).
