# Guion de presentación — "El gato que aprende solo" (Ray + QEMU)
### Computación Paralela y Distribuida · UTEM · **2 expositores**

> **Expositores:** **Joaquín** (marco conceptual: qué es Ray y la tarea) ·
> **Welinton** (el trabajo: implementación, distribución del clúster y demo).
> **Duración objetivo de la exposición:** **5–8 minutos** (≈ 3–4 min c/u).
> **Formato de cada bloque:** ⏱ tiempo · **[DICE]** lo que se dice · **[MUESTRA]** lo que se proyecta.

> **Frase ancla del equipo:** *"Tomamos el demo del laboratorio que **cuenta** primos
> y lo cambiamos por uno que **aprende**: en vez de repartir números, repartimos
> partidas; en vez de contar, el sistema mejora solo."*

---

# PARTE PRELIMINAR — Material a saber (marco conceptual)

> Esta parte es la **base teórica** que ambos deben dominar. No se lee entera en voz
> alta: se **estudia antes** y alimenta las Secciones 1 y 2. Lo esencial (A, B, C, G, H)
> se dice; el resto queda como respaldo para preguntas.

## A. ¿Qué es Ray?

**Ray es un framework open source de Python para cómputo paralelo y distribuido.**
Permite tomar código Python normal y ejecutarlo **en paralelo** —en muchos núcleos de
una máquina o en muchas máquinas (un *clúster*)— **sin escribir la comunicación de bajo
nivel** (sockets, colas, serialización). Esa es su gran diferencia con **MPI**, donde el
paso de mensajes es explícito.

**El problema que resuelve:** Python "normal" corre en un solo proceso y, por el **GIL**,
no aprovecha varios núcleos para cómputo puro. Para usar muchos núcleos o varias máquinas
tendrías que manejar procesos, conexiones de red, reparto de trabajo y recolección de
resultados a mano. **Ray abstrae todo eso:** tú declaras *unidades de trabajo remotas* y
Ray decide dónde ejecutarlas y cómo mover los datos.

## B. El modelo mental de Ray (lo más importante del curso)

| Concepto | Qué es |
|---|---|
| **Driver** | El programa principal: **orquesta** (reparte y recolecta). |
| **Task** (`@ray.remote` en una función) | Función que Ray ejecuta **remota y en paralelo**. Es *stateless* (sin estado). |
| **Actor** (`@ray.remote` en una clase) | Objeto remoto **con estado** (memoria que persiste entre llamadas). |
| **Object ref** | Una **referencia/promesa** al resultado de una task que quizá aún no termina. |
| **`ray.put(x)`** | Guarda `x` **una sola vez** en el *object store* y lo comparte con todos los workers (ideal para *broadcast*). |
| **`ray.get(ref)`** | **Materializa** el resultado: bloquea hasta que el valor está listo. Es el único punto que espera. |
| **Object store** | Memoria compartida distribuida donde viven los objetos; cada nodo tiene el suyo. |
| **Scheduler** | Decide **en qué nodo/worker** corre cada task según los recursos. |
| **Head vs workers** | El **head** coordina (estado global, scheduling, Dashboard); los **workers** ejecutan tareas. *No todo pasa por el head.* |

## C. El patrón fundamental (map-reduce)

```python
import ray
ray.init(address="auto")              # conectarse al clúster

@ray.remote                           # esta función ahora es una "task"
def trabajo(x):
    return computar(x)

refs = [trabajo.remote(t) for t in trozos]   # MAP: se lanzan EN PARALELO
resultados = ray.get(refs)                    # se recolectan (materializan)
total = reducir(resultados)                   # REDUCE: se agregan
```

> 👉 Es **exactamente** el patrón de nuestro demo (y del demo de primos del laboratorio):
> partir el trabajo → lanzar tasks → `ray.get` → agregar.

## D. Granularidad (la advertencia clave)

No basta con ponerle `.remote()` a todo. Si las tareas son **demasiado pequeñas**, el
costo de coordinar, serializar y comunicar **domina** y no se acelera nada. Las
particiones deben tener **suficiente cómputo** para que valga la pena repartirlas.

## E. Herramientas que vienen con Ray

- **Dashboard** (`http://127.0.0.1:8265`): observabilidad —nodos, CPUs, *jobs*, *tasks*,
  *actors*, logs y métricas—. Es el puente entre el programa y su comportamiento real.
- **Ray Jobs** (`ray job submit --working-dir . -- python prog.py`): separa "levantar el
  runtime" de "enviar una ejecución". La hace **reproducible** y deja el job con sus logs.

## F. ¿Cuándo conviene Ray (y cuándo no)?

| Usar… | Cuándo |
|---|---|
| **Ray** | Python arbitrario, ML, tareas heterogéneas, actores con estado, necesidad de Dashboard/Jobs. |
| **Dask / Spark** | Datos tabulares/arrays grandes, APIs tipo *dataframe*, ETL de big data. |
| **MPI** | Comunicación explícita, baja latencia, kernels HPC, control fino de mensajes. |
| **Slurm** | Colas y asignación de recursos en clústeres HPC (no es un runtime de código). |
| **Celery / RQ** | Tareas asíncronas de aplicaciones web. |

## G. ⭐ Cómo se DISTRIBUYÓ Ray en NUESTRO caso (infraestructura)

Esto es lo propio del trabajo: **no usamos una nube**, montamos el clúster nosotros sobre
**máquinas virtuales QEMU con Debian**, cada una con Ray instalado en un entorno `~/ray-env`.

**Topología:**
- **`ray0` = head** (coordina + Dashboard). **`ray1` y `ray2` = workers.**
- Cada VM tiene **2 CPUs** (`-smp 2`) → en multinodo el clúster suma **3 nodos / 6 CPU**.
- Acceso por **llave SSH propia** inyectada en los discos `qcow2` *offline* (sin contraseña).

**Dos modos:**

1. **Single-node (1 VM, ray0):** rápido. El head es también worker. Se arranca con:
   ```bash
   ray start --head --node-ip-address=127.0.0.1 --port=6379 \
             --dashboard-host=0.0.0.0 --dashboard-port=8265
   ```

2. **Multinodo real (ray0 + ray1 + ray2):** el clúster de verdad. Aquí está el **problema
   técnico interesante**:
   - La red de QEMU es **NAT (user-mode): aísla las VMs entre sí** y el **multicast no
     funciona en Windows**, así que las VMs no se "ven" para formar un clúster.
   - **Solución:** a cada VM le conectamos una **2ª tarjeta de red (NIC)** a un **hub
     Ethernet que corre en el host de Windows** (`netbus.py`, un hub por sockets). Eso crea
     una **LAN interna `10.10.0.0/24`** → `ray0=10.10.0.10`, `ray1=.11`, `ray2=.12`.
   - Con esa red interna, el head se levanta en su IP interna y los workers se **unen** a él:
     ```bash
     # ray0 (head):
     ray start --head --node-ip-address=10.10.0.10 --port=6379 ...
     # ray1 y ray2 (workers):
     ray start --address=10.10.0.10:6379 --node-ip-address=10.10.0.11   # ray1
     ray start --address=10.10.0.10:6379 --node-ip-address=10.10.0.12   # ray2
     ```
   - El **Dashboard** (puerto 8265 de ray0) se reenvía al host por NAT → se abre en
     `http://127.0.0.1:8265`. El SSH de cada VM también: ray0→2320, ray1→2321, ray2→2322.

> **Punto clave:** **el código de entrenamiento NO cambia** entre single y multinodo. Usa
> `ray.init(address="auto")` y reporta el *hostname* de cada tarea; lo único que cambia es
> la infraestructura debajo. Por eso al pasar a 3 nodos, las mismas tareas se reparten
> solas y el Dashboard muestra **3 nodos / 6 CPU**.

## H. La tarea que inventamos

El enunciado pedía: **"hacer funcionar el demo con Ray con una tarea inventada por nosotros"**
(no repetir el ejemplo de primos). La nuestra: **"El gato que aprende solo"** — un agente
que **aprende a jugar al gato (tic-tac-toe) por refuerzo**, jugando **miles de partidas
contra sí mismo** (*self-play*) con el método de **Monte Carlo**:

- Empieza sabiendo **nada** (juega al azar).
- Cada jugada que lleva a **ganar se refuerza (+1)**; a **perder se castiga (−1)**; empate, **0**.
- Su "memoria" es una **tabla (política Q)**: para cada posición, qué tan buena fue cada jugada.
- Es **vergonzosamente paralelo**: cada partida de self-play es **independiente** → se reparte
  natural entre tareas Ray, y después se **fusiona** lo aprendido. Encaja perfecto en map-reduce.

---

# SECCIÓN 1 — JOAQUÍN: ¿Qué es Ray y cuál es la tarea? (⏱ ~3–4 min)

> Objetivo de Joaquín: que el público entienda **Ray** y **qué problema resolvimos**, sin
> entrar todavía al código. Apoyarse en A, B, C, G y H del material preliminar.

### 1.1 · Gancho (⏱ 0:30)

**[DICE]**
> "Buenas. ¿Y si una máquina aprendiera a jugar al gato **sola**, sin que le programemos
> ninguna estrategia? Y además, ¿y si la pusiéramos a aprender **más rápido** repartiendo
> el trabajo entre varias máquinas? Eso es justo lo que hicimos: usamos **Ray** sobre un
> clúster de máquinas virtuales para entrenar un agente que aprende por refuerzo."

**[MUESTRA]** Portada / la interfaz `gato.html` abierta (sin jugar aún).

### 1.2 · ¿Qué es Ray? (⏱ 1:00)

**[DICE]**
> "**Ray es un framework de Python para cómputo paralelo y distribuido.** Toma código
> Python normal y lo ejecuta en paralelo —en varios núcleos o en varias máquinas— **sin que
> nosotros escribamos sockets ni comunicación de bajo nivel**. Esa es su diferencia con MPI,
> donde el paso de mensajes es explícito.
>
> El problema que resuelve es que Python, por el **GIL**, corre en un solo proceso y no
> aprovecha varios núcleos para cómputo puro. Ray nos deja **declarar tareas remotas** y él
> decide dónde corren y cómo mueve los datos."

**[MUESTRA]** Slide del modelo mental (driver / tasks / object refs / scheduler).

### 1.3 · El modelo mental y el patrón map-reduce (⏱ 1:00)

**[DICE]**
> "El modelo mental tiene pocas piezas: el **driver** orquesta; una **task** es una función
> con `@ray.remote` que corre en paralelo; un **object ref** es una promesa al resultado;
> `ray.put` publica un dato una vez para todos los workers, y `ray.get` espera y recolecta.
>
> Con eso, todo se reduce a un patrón **map-reduce** de cuatro pasos: publico los datos con
> `ray.put`, lanzo muchas tareas con `.remote()`, recolecto con `ray.get`, y agrego los
> resultados. **Es el mismo patrón del demo de primos del laboratorio** — nosotros solo
> cambiamos *qué* hace cada tarea."

**[MUESTRA]** El bloque de código map-reduce (sección C del material).
**[OJO con la granularidad]** (si hay tiempo): *"Si las tareas son muy chicas, Ray pierde
más tiempo coordinando que calculando; por eso cada tarea tiene que tener suficiente cómputo."*

### 1.4 · La tarea que trabajamos (⏱ 1:00)

**[DICE]**
> "Nuestra tarea inventada es **'el gato que aprende solo'**. El agente empieza jugando al
> azar y juega **miles de partidas contra sí mismo**. Cada jugada que termina en victoria se
> refuerza, la que termina en derrota se castiga; con eso va armando una **tabla** de qué tan
> buena es cada jugada en cada posición. Es **aprendizaje por refuerzo** con **Monte Carlo**.
>
> Y acá está la clave para el curso: **cada partida es independiente de las demás**. Eso lo
> hace *vergonzosamente paralelo* — podemos repartir las partidas entre varios trabajadores
> que juegan al mismo tiempo, y después juntar lo aprendido. Por eso es un caso ideal para Ray."

**[MUESTRA]** La curva de aprendizaje del HTML (botón *Animar aprendizaje*): el verde
(no-derrota) subiendo.

### 1.5 · Transición a Welinton (⏱ 0:15)

**[DICE]**
> "Entonces ya saben **qué es Ray** y **qué tarea resolvimos**. Ahora **Welinton** les va a
> mostrar **cómo lo distribuimos de verdad** —cómo montamos el clúster— y el demo funcionando."

---

# SECCIÓN 2 — WELINTON: El trabajo (implementación + clúster + demo) (⏱ ~3–4 min)

> Objetivo de Welinton: mostrar **cómo se distribuyó Ray** (la infraestructura que montamos),
> el **código** con el patrón, el **demo en vivo** y las **mediciones**. Apoyarse en G del
> material + Secciones 4–6 técnicas.

### 2.1 · Cómo montamos y distribuimos el clúster (⏱ 1:15)

**[DICE]**
> "Nosotros **no usamos una nube**: montamos el clúster con **máquinas virtuales QEMU con
> Debian**, cada una con Ray. Tenemos **ray0 como head** —que coordina y sirve el Dashboard—
> y **ray1 y ray2 como workers**. Cada VM aporta 2 CPUs, así que en multinodo el clúster
> tiene **3 nodos y 6 CPU**.
>
> El detalle interesante fue la **red**: la red por defecto de QEMU es NAT y **aísla las VMs
> entre sí**, y el multicast no funciona en Windows, así que las máquinas no se veían para
> formar el clúster. Lo resolvimos conectándole a cada VM una **segunda tarjeta de red a un
> hub Ethernet que corre en el host**, creando una **LAN interna 10.10.0.0/24**. Con esa red,
> ray0 levanta el head y ray1/ray2 se **unen** con `ray start --address`. Lo bonito es que
> **el código de entrenamiento no cambia nada**: usa `address=auto` y reparte solo."

**[MUESTRA]** Diagrama de la topología (ray0/ray1/ray2 + hub + LAN 10.10.0.0/24) **o** el
Dashboard mostrando **3 nodos / 6 CPU**.

### 2.2 · El código: el patrón de Ray en una generación (⏱ 0:45)

**[DICE]**
> "En el programa, cada **generación** de aprendizaje es el map-reduce que explicó Joaquín,
> en cuatro líneas: hago **`ray.put` de la política actual** para que todos los workers la
> reciban; lanzo **K tareas `rollout.remote(...)`**, donde cada una juega sus partidas de
> self-play; **`ray.get`** recolecta los resultados; y **fusiono** las estadísticas para armar
> la política mejorada. Repetimos eso varias generaciones. Cada tarea además reporta **en qué
> nodo se ejecutó**, así vemos la distribución real."

**[MUESTRA]** `gato_rl_ray.py`, el bloque del driver con las 4 líneas
`ray.put / .remote / ray.get / fusionar`.

### 2.3 · Demo en vivo (⏱ 1:15)

> **Plan A (con clúster):** entrenamiento real en las VMs. **Plan B (a prueba de fallos):**
> `gato.html` **ya generado**. *Recomendación: tener el Plan B siempre listo.*

**[DICE / PASOS]**
> "Veámoslo funcionando."
> 1. *(Plan A)* "Corro el entrenamiento en el clúster y, miren, **la columna de no-derrota
>    va subiendo** generación a generación, y la columna **nodos** muestra que las tareas se
>    reparten entre las máquinas."
> 2. "En el **Dashboard** se ven las tareas ejecutándose en paralelo y los nodos del clúster."
> 3. *(HTML)* "Y acá pueden **jugar contra la IA** —que casi siempre empata o gana, y nadie
>    le programó una estrategia, lo aprendió—; ven la **curva de aprendizaje**; y con el
>    **deslizador de replay**, cómo en la generación 0 juega torpe y al final juega como experto."

**[MUESTRA]** Terminal/TUI con el entrenamiento + Dashboard + `gato.html` (jugar, curva, replay).

### 2.4 · Medición: speedup, eficiencia y overhead (⏱ 0:30)

**[DICE]**
> "Como buen laboratorio de cómputo paralelo, **medimos, no solo ejecutamos**. Con
> `--benchmark` corremos el mismo total de partidas con **1 tarea** y con **K tareas**, y
> calculamos **Speedup = T1/Tp**, **Eficiencia = S/p** y **Overhead = p·Tp − T1**. Y se nota
> la **granularidad**: si subimos las partidas por tarea, cada tarea amortiza mejor el costo
> de coordinar y el speedup mejora."

**[MUESTRA]** Los números del `--benchmark` (o los chips de speedup del HTML).

### 2.5 · Cierre (⏱ 0:15)

**[DICE]**
> "En resumen: pasamos del demo que **cuenta** primos a uno que **aprende**, con el **mismo
> patrón distribuido**, montando el clúster Ray nosotros mismos sobre QEMU. Ray no reemplaza
> el razonamiento paralelo: lo hace **programable y observable** desde Python. ¡Gracias!"

---

# PREGUNTAS PROBABLES (para cualquiera de los dos)

**¿Por qué Monte Carlo y no una red neuronal (DQN)?**
> El gato es chico (~4.500 estados): una tabla basta y converge rápido. Una red necesitaría
> PyTorch/TensorFlow, que no están en la VM Debian mínima. Mantuvimos todo en librería
> estándar para que corra tal cual en el clúster.

**¿Dónde está el paralelismo exactamente?**
> En los *rollouts*: las K tareas `@ray.remote` que juegan partidas a la vez. La agregación
> (reduce) y la actualización de la política las hace el driver.

**¿Cómo lograron que las VMs se vieran si QEMU las aísla?**
> Con una **segunda NIC** por VM conectada a un **hub Ethernet en el host** → LAN interna
> `10.10.0.0/24`. Así ray1/ray2 se unen al head con `ray start --address=10.10.0.10:6379`.

**¿El código cambia entre 1 nodo y 3 nodos?**
> No. Usa `ray.init(address="auto")` y reporta hostnames; lo único que cambia es la
> infraestructura debajo. Por eso al pasar a 3 nodos las tareas se reparten solas.

**¿La IA juega perfecto?**
> Aprende a jugar muy bien por self-play (casi no pierde), pero no es minimax exhaustivo:
> optimiza contra su propia forma de jugar. Es la naturaleza de Monte Carlo: aprende de
> experiencia, no calcula todo el árbol.

**¿Por qué la curva a veces baja un poquito?**
> Es estocástico: la evaluación usa un rival aleatorio y un número finito de partidas; hay
> ruido. La tendencia general es lo que importa.

---

# CHECKLIST ANTES DE PRESENTAR

- [ ] `gato.html` **pre-generado** y abierto (Plan B garantizado).
- [ ] Clúster encendido (ray0, o ray0+ray1+ray2) y **Dashboard** abierto (Plan A).
- [ ] `gato_rl_ray.py` ya copiado en `~/ray-demo` (si va el Plan A real).
- [ ] Una partida de prueba jugada (que la IA responde).
- [ ] Slides a mano: modelo mental, map-reduce, topología del clúster y benchmark.
- [ ] **Reparto claro:** Joaquín 1.1→1.5 · Welinton 2.1→2.5 · cualquiera responde Q&A.
- [ ] Cronómetro: si van apretados, Welinton omite 2.4 (benchmark) y mantiene 2.1 y 2.3.
