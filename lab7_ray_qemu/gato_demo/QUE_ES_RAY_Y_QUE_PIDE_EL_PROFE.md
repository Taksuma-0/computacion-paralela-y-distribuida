# ¿Qué es Ray? y ¿qué buscaba el profesor?

> Documento de contexto para el demo **"El gato que aprende solo"**
> (Computación Paralela y Distribuida · UTEM). Resume qué es Ray y, según el
> *deck* del curso y el enunciado, qué se está evaluando realmente.

---

# Parte 1 — ¿Qué es Ray?

**Ray es un framework open source de Python para cómputo paralelo y distribuido.**
Te permite tomar código Python normal y ejecutarlo **en paralelo** —en muchos
núcleos de una máquina o en muchas máquinas (un *clúster*)— **sin que tú escribas
la comunicación de bajo nivel** (sockets, colas, serialización). Eso lo diferencia
de MPI, donde el paso de mensajes es explícito.

### El problema que resuelve
Python "normal" corre en un solo proceso y, por el GIL, no aprovecha varios núcleos
para cómputo puro. Para usar muchos núcleos o varias máquinas tendrías que manejar
procesos, conexiones de red, reparto de trabajo y recolección de resultados a mano.
**Ray abstrae todo eso**: tú declaras *unidades de trabajo remotas* y Ray decide
dónde ejecutarlas y cómo mover los datos.

### El modelo mental de Ray (lo más importante para el curso)
| Concepto | Qué es |
|---|---|
| **Driver** | Tu programa principal: el que **orquesta** (reparte y recolecta). |
| **Task** (`@ray.remote` en una función) | Una función que Ray ejecuta **remota y en paralelo**. Es *stateless* (sin estado persistente). |
| **Actor** (`@ray.remote` en una clase) | Un **objeto remoto con estado** (memoria que persiste entre llamadas). Útil para un modelo cargado una vez, una caché o un coordinador. |
| **Object ref** | Una **referencia/promesa** al resultado de una task que quizá aún no terminó. `f.remote()` devuelve un object ref. |
| **`ray.get(ref)`** | **Materializa** el resultado: bloquea hasta que el valor está listo. Es el único punto que espera. |
| **`ray.put(x)`** | Guarda `x` **una sola vez** en el *object store* y lo comparte con todos los workers sin recopiarlo (ideal para hacer *broadcast*). |
| **Object store** | Memoria compartida distribuida donde viven los objetos; cada nodo tiene el suyo. |
| **Scheduler** | Decide **en qué nodo/worker** corre cada task según los recursos disponibles. |
| **Head node vs workers** | El **head** coordina (estado global, scheduling, Dashboard); los **workers** ejecutan tareas y guardan objetos. *No todo pasa por el head.* |

### El patrón fundamental (map-reduce)
```python
import ray
ray.init(address="auto")          # conectarse al clúster

@ray.remote                       # esta función ahora es una "task"
def trabajo(x):
    return computar(x)

refs = [trabajo.remote(t) for t in trozos]   # se lanzan EN PARALELO
resultados = ray.get(refs)                    # se recolectan (materializan)
total = reducir(resultados)                   # se agregan
```
> 👉 Es **exactamente** el patrón que usa nuestro demo del gato (y el demo de primos
> del curso): partir el trabajo → lanzar tasks → `ray.get` → agregar.

### Una advertencia clave: la granularidad
No basta con "ponerle `.remote()`" a todo. Si las tareas son **demasiado pequeñas**,
el costo de coordinar, serializar y comunicar **domina** y no se acelera nada. Las
particiones deben tener **suficiente cómputo** para que valga la pena repartirlas.

### Herramientas que vienen con Ray
- **Dashboard** (`http://127.0.0.1:8265`): observabilidad —nodos, CPUs, *jobs*,
  *tasks*, *actors*, logs, métricas y errores—. Es el puente entre el programa y su
  comportamiento real.
- **Ray Jobs** (`ray job submit --working-dir . -- python prog.py`): separa
  "levantar el runtime" de "enviar una ejecución". Hace la ejecución **reproducible**
  y deja el job registrado con sus logs.

### ¿Cuándo conviene Ray (y cuándo no)?
| Usar… | Cuándo |
|---|---|
| **Ray** | Python arbitrario, ML, tareas heterogéneas, actores con estado, necesidad de Dashboard/Jobs. |
| **Dask / Spark** | Datos tabulares/arrays grandes, APIs tipo *dataframe*, ETL de big data. |
| **MPI** | Comunicación explícita, baja latencia, kernels HPC, control fino de mensajes. |
| **Slurm** | Colas y asignación de recursos en clústeres HPC (no es un runtime de código). |
| **Celery / RQ** | Tareas asíncronas de aplicaciones web. |

> Frase de cierre del curso: *"Ray no reemplaza el razonamiento paralelo; lo hace
> programable y observable desde Python."*

---

# Parte 2 — ¿Qué buscaba el profesor?

Hay **dos niveles**: el enunciado concreto y los objetivos de aprendizaje del curso
(que es lo que en el fondo se evalúa).

### A) El enunciado de la tarea
> **"Hacer funcionar el demo con Ray y con una tarea inventada por ustedes."**

Es decir:
1. **No repetir** el ejemplo de primos del laboratorio.
2. **Inventar una tarea propia** y ejecutarla **sobre el clúster Ray** que corre en
   las VMs QEMU/Debian.
3. Demostrar que el patrón distribuido **funciona de verdad** (no es Python secuencial
   disfrazado).

👉 Nuestra tarea inventada: **un agente que aprende a jugar al gato por refuerzo
(self-play)**, entrenado en paralelo con Ray. El *self-play* es ideal porque cada
partida es independiente → se reparte de forma natural entre tareas.

### B) Los objetivos de aprendizaje (del deck, diapositiva 2)
El profesor declara que, al terminar, el estudiante debe poder:
1. **Explicar el modelo mental de Ray**: driver, tasks, actors, object refs y scheduler.
2. **Arrancar el entorno QEMU/Debian/Ray** (sin interferir con la rama Alpine previa).
3. **Usar Dashboard y Ray Jobs** para observar ejecución, logs, recursos y fallos.
4. **Decidir cuándo usar Ray** frente a Dask, Spark, MPI, Slurm o Celery.

Y el **método** que recalca el curso (diapositivas 2, 16 y 17):
- Entender *qué necesita un runtime distribuido* para **arrancar, programar y observar**
  trabajo paralelo (no "usar una nube").
- **Medir, no solo ejecutar**: speedup `S = T1/Tp`, eficiencia `E = S/p`,
  overhead `O = p·Tp − T1`.
- **Validar Ray local (single-node) antes** de intentar multinodo.

### Cómo este demo cumple cada objetivo
| Lo que pide el profesor | Cómo lo cubre el demo del gato |
|---|---|
| Modelo mental de Ray (tasks, object refs, `ray.get`, `ray.put`) | El driver hace `ray.put(política)` → `rollout.remote(...)` (K tasks) → `ray.get(refs)` → fusiona. Es el patrón canónico, fácil de explicar. |
| Arrancar QEMU/Debian/Ray | `GUIA_EJECUCION.md` levanta ray0 y `ray start --head`; el programa usa `ray.init(address="auto")`. |
| Dashboard y Ray Jobs | Se ejecuta también como `ray job submit --working-dir .` y se observan las *tasks* en el Dashboard. |
| Medir rendimiento | Modo `--benchmark`: reporta T1, Tp, **speedup, eficiencia y overhead**. |
| Granularidad / diseño de particiones | Parámetro `partidas_por_tarea`: subirlo da tareas con más cómputo (mejor speedup); explica el trade-off. |
| Validar local antes de multinodo | El demo corre single-node en ray0; el código ya reporta *hostnames* y queda listo para multinodo sin cambios. |
| ¿Por qué Ray y no otro? | La tarea es Python arbitrario + ML → caso típico de Ray (no big-data tabular ni HPC con MPI). |

### Checklist para "cumplir y lucirse" en la presentación
- [ ] Mostrar el código con el patrón **`ray.put` / `.remote` / `ray.get`**.
- [ ] Correr el demo en **ray0** y, además, como **Ray Job**.
- [ ] Abrir el **Dashboard** y señalar nodos/tasks/logs.
- [ ] Mostrar la **curva de aprendizaje** subiendo (la IA *aprende*).
- [ ] Correr `--benchmark` y comentar **speedup/eficiencia/overhead**.
- [ ] Explicar la **granularidad** (por qué tareas chicas no aceleran).
- [ ] Cerrar diciendo **cuándo conviene Ray** frente a Dask/Spark/MPI.

> En una frase: el profesor no evalúa "que el gato juegue bien", sino que **demuestres
> que entiendes y sabes operar un runtime distribuido** (arrancarlo, programarlo con
> tasks/object refs, observarlo y medirlo) usando una tarea propia con paralelismo real.
