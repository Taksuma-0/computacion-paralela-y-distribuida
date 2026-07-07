# Guión completo de presentación y estudio

## Detección distribuida de anomalías de comportamiento en trayectorias ADS-B

**Curso:** INF8090 · Computación Paralela y Distribuida — Ingeniería Civil en Ciencia de Datos (UTEM)
**Integrantes:** Joaquin Araya · Juan Toledo · Welinton Barrera
**Duración objetivo:** ~20 minutos · **11 diapositivas** (`presentacion_final.html`)

---

## Cómo usar este documento

Este archivo tiene cuatro partes:

1. **Parte A — Teoría que todos deben saber:** la materia de fondo. Léanla **completa** antes de presentar; de aquí salen casi todas las preguntas del profesor.
2. **Parte B — Guión hablado:** exactamente lo que dice cada uno, diapositiva por diapositiva.
3. **Parte C — Preguntas y respuestas:** simulacro de defensa.
4. **Parte D — Glosario:** definiciones cortas para repasar a último minuto.

**Regla de oro:** la diapositiva tiene poco texto a propósito; ustedes le ponen la voz. No lean la pantalla, **expliquen** y **señalen** lo que nombran.

---

## Reparto y tiempos

| Parte | Presenta | Diapositivas | Tiempo |
|---|---|---|---|
| 1. Apertura, problema y datos | **Joaquin** | 1 – 4 | ~6–7 min |
| 2. Diseño, implementación y resultados | **Juan** | 5 – 7 | ~7 min |
| 3. Calidad, análisis crítico y cierre | **Welinton** | 8 – 11 | ~6–7 min |

Números que **los tres** deben decir sin dudar: **636 vuelos reales**, **speedup 5,59×** con 8 nodos, **eficiencia 0,70**, **recall 1,0**.

---

# PARTE A — TEORÍA QUE TODOS DEBEN SABER

> Léanla antes de presentar. No hace falta memorizarla al pie de la letra, pero cada integrante debe poder **explicar con sus palabras** cualquiera de estos puntos.

## A.1 · El dominio: qué es ADS-B y qué buscamos

**ADS-B** (*Automatic Dependent Surveillance–Broadcast*) es un sistema por el que cada aeronave **transmite periódicamente su estado**: posición (latitud/longitud), altitud, velocidad y rumbo. Es "automático" (sin que el piloto intervenga) y "dependiente" (depende de los sensores de a bordo, como el GPS). Cualquiera con un receptor puede escucharlo; nosotros usamos los datos abiertos de **OpenSky Network**.

Dentro del tráfico **normal** hay vuelos cuyo comportamiento **se desvía del patrón esperado**. Nos interesan cuatro tipos:

- **Rodeo:** el avión toma una ruta mucho más larga que la recta origen–destino.
- **Holding:** patrón de espera, vueltas en círculo (típico antes de aterrizar).
- **Descenso anómalo:** pérdida de altitud brusca o impropia de la fase de vuelo.
- **Go-around:** aproximación interrumpida — desciende para aterrizar y vuelve a subir.

Detectarlos y **ordenarlos por rareza** (rankear) sirve para **seguridad operacional** y **auditoría de rutas**. Es un problema de **ciencia de datos**, no de ingeniería plana: hay que diseñar *features* de comportamiento y un método de *outlier scoring* robusto.

## A.2 · Paralelo vs. distribuido

- **Cómputo paralelo:** varias unidades de proceso trabajan a la vez sobre el **mismo problema**. Si comparten memoria (varios núcleos de un mismo PC) hablamos de **memoria compartida**.
- **Cómputo distribuido:** las unidades están en **máquinas separadas** que **no comparten memoria** y se coordinan **enviándose mensajes** por la red (**paso de mensajes**).

Nuestro proyecto cubre **ambos**: en modo *local* los agentes son **procesos** del mismo host, y en modo *clúster* son **máquinas virtuales QEMU** independientes a las que se llega por **SSH/TCP**. En los dos casos la coordinación es por **mensajes**, no por memoria compartida: es la aproximación distribuida.

## A.3 · Métricas de rendimiento (las que pregunta el profesor)

Sea `T1` el tiempo del programa **secuencial** (1 unidad) y `Tp` el tiempo con **p** unidades.

- **Speedup:** `Sp = T1 / Tp`. Cuántas veces más rápido. Ideal: `Sp = p` (lineal).
- **Eficiencia:** `Ep = Sp / p`. Qué fracción del ideal logramos (1,0 = perfecto). Casi siempre baja al crecer `p`.
- **Overhead:** el trabajo "extra" de coordinar/comunicar que no existía en secuencial. Lo estimamos como `o(p) = p·Tp − T1`.

**Ley de Amdahl:** si una fracción `f` del programa es **estrictamente secuencial** (no paralelizable), el speedup máximo es `1 / (f + (1−f)/p)`, que **nunca supera `1/f`** por más nodos que se agreguen. Moraleja: la parte serie limita.

**Ley de Gustafson:** en la práctica, al tener más nodos **agrandamos el problema**; entonces el speedup "escalado" crece casi lineal (`Sp ≈ p − f·(p−1)`). Moraleja: distribuir vale la pena cuando el trabajo **crece con la máquina**.

**Métrica de Karp–Flatt:** la fracción serie **empírica** se estima con `e = (1/Sp − 1/p) / (1 − 1/p)`. Es útil para **diagnosticar**: si `e` se mantiene constante al crecer `p`, la pérdida es por una región serie (Amdahl); si `e` **aumenta**, el problema es el **overhead de comunicación**; si `e` **baja**, el costo fijo se está **amortizando**. En nuestros datos `e` = 0,130 → 0,095 → 0,062: **baja**, señal de que escala con gracia.

## A.4 · Paralelismo de datos y "embarrassingly parallel"

Un problema es **embarrassingly parallel** ("vergonzosamente paralelo") cuando se parte en subtareas que **no dependen entre sí** y **casi no necesitan comunicarse**. Es el mejor caso para paralelizar. El nuestro lo es: el **puntaje de anomalía de un vuelo no depende de los otros**, así que podemos repartir los vuelos en trozos, procesarlos por separado y juntar los resultados al final. A esto se le llama **paralelismo de datos** (el mismo cálculo sobre distintos trozos de datos).

## A.5 · Granularidad (la idea central del proyecto)

La **granularidad** es la relación entre **cuánto se calcula** por trozo y **cuánto cuesta comunicarlo/coordinarlo**:

- **Grano grueso:** trozos grandes, mucho cómputo por trozo → poco overhead relativo → **acelera bien**.
- **Grano fino:** trozos pequeños → la comunicación/coordinación **domina** → puede **no acelerar** (o ir más lento).

**Regla:** distribuir solo conviene si cada trozo tiene **suficiente cómputo** para "pagar" el costo de repartirlo. Este es el aprendizaje que reportamos con honestidad: la carga densa acelera (grano grueso), pero los 636 vuelos reales son tan livianos (~0,07 s en total) que quedan **limitados por I/O** y **no aceleran**.

## A.6 · El GIL de Python (por qué procesos y no hilos)

Python (CPython) tiene el **GIL** (*Global Interpreter Lock*): un candado que permite que **solo un hilo ejecute bytecode Python a la vez**. Por eso, para trabajo **CPU-bound**, los **hilos no dan paralelismo real**. La solución es usar **procesos** separados: cada proceso tiene su **propio intérprete y su propio GIL**, así que corren de verdad en paralelo. Nuestros agentes son **procesos** (locales) o **VMs** (clúster), nunca hilos: por eso el cómputo escala.

## A.7 · Balanceo de carga (cola dinámica / work-stealing)

Si repartiéramos los trozos **de forma estática** (a cada nodo le toca un bloque fijo), un nodo lento retrasaría a todos. En su lugar usamos una **cola dinámica**: el coordinador tiene una fila de trozos y **cada agente que queda libre pide el siguiente**. Así los nodos rápidos hacen más trozos y los lentos menos, **balanceando** automáticamente. Es la idea de *work-stealing* (robo de trabajo).

## A.8 · Reducción (estilo map-reduce)

El patrón es **map → reduce**:

- **`split`** parte el problema en trozos.
- **`run`** procesa cada trozo (fase *map*, en paralelo).
- **`merge`** combina los resultados parciales en el resultado global (fase *reduce*).

En nuestro caso `merge` junta los "top locales" de cada agente y produce el **ranking global top-k** de vuelos más anómalos. La reducción es el **único punto de sincronización**: hasta ahí, todo es independiente.

## A.9 · Tolerancia a fallos

Un sistema distribuido debe **sobrevivir a que un nodo falle**. El nuestro:

1. Antes de trabajar, cada nodo pasa un **health-check** funcional (`self_test`: se compara su salida con la esperada).
2. Si un **trozo falla**, se **reintenta** o se **abandona** sin detener el trabajo.
3. Si un **nodo cae**, se **excluye** y los demás terminan su cola.

Lo demostramos: con un nodo caído, el trabajo igual completó **8/8** lotes.

## A.10 · Comunicación y serialización

Coordinador y agentes hablan por **TCP** (sockets). Los mensajes son **JSON delimitados por línea**: se serializa un objeto por línea y el receptor **acumula en un buffer de 64 KB** y separa por salto de línea, tolerando que un mensaje llegue partido en varios segmentos. Tipos de mensaje: `TASK` (coordinador→agente, un trozo), `RESULT` (agente→coordinador, un parcial), `SELF_TEST`/`HELLO` (salud) y `ERROR`/timeout (fallo → reintento/exclusión).

## A.11 · El modelo de detección (dominio)

De cada trayectoria (resampleada a **40 puntos** `[lat, lon, alt]`) extraemos tres **features**:

- **`len_ratio`:** largo real de la ruta (fórmula de **haversine**) dividido por la distancia directa → mide **desvío de ruta** (detecta rodeos).
- **`turn_sum`:** suma de los cambios de rumbo → mide **curvatura acumulada** (detecta holdings).
- **`vrate_max`:** tasa vertical máxima → detecta **descensos/ascensos anómalos** (go-arounds).

El **puntaje** es **z-robusto** con **MAD** (*Median Absolute Deviation* = mediana de las desviaciones respecto de la mediana). En vez de media y desviación estándar (sensibles a los propios outliers), usamos **mediana** y **MAD**, que son **robustas**:

```
z = max_f  |x_f − mediana_f| / max(1.4826 · MAD_f , piso_f)
un vuelo es anómalo si z ≥ σ (umbral)
```

El factor **1,4826** hace que la MAD sea comparable a una desviación estándar en datos normales. El **piso por feature** evita que un MAD ≈ 0 (vuelos casi rectos) dispare falsos positivos. Es simple, interpretable y robusto a lo heterogéneo de los datos reales.

## A.12 · Rigor experimental (por qué los números son creíbles)

- **Datos-por-semilla:** para medir escalabilidad, la partición lleva solo una **semilla**; el agente **regenera** sus trayectorias con `random.Random(semilla)`. Así la **transferencia por red es casi cero** y medimos **cómputo puro**, no red. Y es **reproducible**.
- **Semilla fija (7):** toda generación e inyección es determinista.
- **Repeticiones + calentamiento:** 3 repeticiones y una corrida de calentamiento descartada; reportamos **media, desviación y mejor de tres**.
- **Equivalencia baseline↔distribuido:** antes de reportar *speedup*, verificamos que el distribuido da **exactamente el mismo ranking y métricas** que la línea base secuencial. Comparar tiempos de dos programas que calculan cosas distintas sería trampa; por eso lo verificamos automáticamente.
- **Trazabilidad:** cada corrida deja un registro `results/<job-id>.json` (+ reporte `.html`); las tablas y gráficos se generan **solo** de esos registros, sin editar a mano.

---

# PARTE B — GUIÓN HABLADO (lo que dice cada uno)

> Está redactado para leerse casi tal cual, pero suena mejor si lo **ensayan** una vez y lo dicen con sus palabras. Entre `[ ]` van las **acciones** (qué señalar o hacer).

## PARTE 1 — JOAQUIN · Apertura, problema y datos (diapositivas 1–4)

### Diapositiva 1 — Portada

`[Radar animado en pantalla. Mirar al público, no a la pantalla.]`

"Buenas tardes. Somos Joaquin, Juan y Welinton, y les vamos a presentar nuestro proyecto de Computación Paralela y Distribuida: la **detección distribuida de anomalías de comportamiento en vuelos**, con datos reales de aviación.

La pregunta que guía todo el trabajo es concreta: dado un montón de trayectorias de vuelo, ¿podemos **detectar y ordenar los vuelos más raros** de forma **distribuida** —repartiendo el trabajo entre varios nodos— y que además eso **acelere** respecto de hacerlo en un solo proceso? Al final de la presentación vamos a haber respondido esa pregunta con **mediciones reales**."

### Diapositiva 2 — El problema

`[Señalar los cuatro mini-radares uno por uno.]`

"Primero, el problema. Los aviones transmiten constantemente su posición por un sistema que se llama **ADS-B**. Si uno mira ese flujo, la mayoría de los vuelos siguen su ruta con normalidad, pero **algunos se salen del patrón**. Nos enfocamos en cuatro tipos de anomalía de comportamiento:

- un **rodeo**, cuando el avión da una vuelta mucho más larga que la ruta directa `[señalar]`;
- un **holding**, que es un patrón de espera en círculos `[señalar]`;
- un **descenso anómalo**, una caída de altitud brusca `[señalar]`;
- y un **go-around**, que es una aproximación interrumpida: el avión baja para aterrizar y vuelve a subir `[señalar]`.

Detectar y **rankear** estos vuelos sirve para **seguridad operacional** y para **auditar rutas**. Y ojo: esto es un problema de **ciencia de datos**, no un cálculo trivial —hay que diseñar buenas *features* de comportamiento y un método robusto para puntuar qué tan raro es cada vuelo."

### Diapositiva 3 — ¿Por qué distribuir?

`[Señalar la animación partición → paralelo.]`

"¿Por qué distribuir esto y no simplemente correrlo en un PC? Porque el problema tiene una propiedad ideal: **el puntaje de cada vuelo es independiente del de los demás**. Una vez que extraemos las *features*, no hay ninguna dependencia entre un vuelo y otro. En la jerga del curso, es un problema **‘embarrassingly parallel’**: se puede partir en trozos, procesar cada trozo por separado y unir los resultados al final, casi sin comunicación.

Y hay una razón de escala: cuando el volumen de vuelos es grande, la versión **secuencial no termina** en un tiempo razonable. Ahí es donde repartir el trabajo entre varios nodos deja de ser un lujo y pasa a ser necesario. Eso sí —y esto lo va a retomar Welinton al final— **repartir solo acelera si cada trozo tiene suficiente trabajo**; a eso se le llama granularidad."

### Diapositiva 4 — Datos y línea base

`[Señalar el KPI de 636 vuelos.]`

"¿Con qué datos trabajamos? Con **636 vuelos reales** que bajamos de **OpenSky Network**, una red pública de datos ADS-B. Cada vuelo lo normalizamos a 40 puntos de latitud, longitud y altitud.

Para el estudio de velocidad usamos un truco importante que se llama **datos-por-semilla**: en vez de mandar los datos por la red, la partición lleva solo una **semilla**, y cada agente **regenera** sus propios datos a partir de ella. Así la **transferencia por red es casi cero** y medimos **cómputo puro**, sin que la red contamine la medición —y además es 100 % reproducible.

Y algo clave para poder hablar de *speedup* con seriedad: tenemos una **línea base secuencial**, el mismo programa en un solo proceso, que produce **exactamente el mismo resultado** que la versión distribuida. Verificamos esa **equivalencia** en cada corrida. Con eso listo, le paso la palabra a Juan, que les va a mostrar **cómo construimos el sistema** y qué medimos."

## PARTE 2 — JUAN · Diseño, implementación y resultados (diapositivas 5–7)

### Diapositiva 5 — Arquitectura

`[Dejar correr la animación; señalar los paquetes verdes bajando y los azules subiendo.]`

"Gracias, Joaquin. Esta es la **arquitectura**, y es probablemente lo más importante del diseño. Tenemos un **coordinador** —el cerebro, corre en el host— y varios **agentes**, que son los que hacen el trabajo pesado. Se comunican por **TCP**, mandándose mensajes en formato JSON.

El flujo es así: el coordinador tiene una **cola dinámica** de trozos de trabajo y los va **repartiendo** a los agentes —esos son los paquetes verdes que ven bajar `[señalar]`. Cada agente procesa su trozo **en paralelo** con los demás, y devuelve su resultado parcial —los paquetes azules que suben `[señalar]`. Finalmente, una operación que llamamos **`merge`** **reduce** todos los parciales en un **ranking global** de los vuelos más anómalos.

Dos propiedades importantes: la cola es **dinámica**, así que cada agente que queda libre pide el siguiente trozo —eso da **balanceo de carga** automático. Y el sistema es **tolerante a fallos**: si un nodo se cae, se **excluye** y el resto termina el trabajo. Lo probamos de verdad: con un nodo caído, el trabajo igual se completó entero."

### Diapositiva 6 — Implementación

`[Señalar el bloque de código con el contrato split/run/merge/self_test.]`

"¿Cómo está implementado? La gracia es que la **plataforma no sabe nada de aviones**. Toda la lógica del dominio vive en una **tarea enchufable** que implementa un **contrato mínimo** de cuatro funciones `[señalar]`: **`split`** parte el problema, **`run`** procesa un trozo en el agente, **`merge`** reduce los parciales, y **`self_test`** es una sonda de salud. Si mañana quisiéramos resolver otro problema distribuido, solo cambiaríamos esta tarea; el coordinador y los agentes siguen igual.

Hay tres **decisiones técnicas** que conviene destacar. Primero: usamos **procesos, no hilos**, para esquivar el **GIL** de Python —con hilos, el cómputo no correría en paralelo de verdad. Segundo: los **datos-por-semilla** que mencionó Joaquin, para medir cómputo y no red. Y tercero: el puntaje de anomalía es **z-robusto con MAD** —usamos mediana y desviación absoluta mediana en vez de media y desviación estándar, porque son **robustas a los propios outliers** que estamos buscando, con un piso por *feature* para que aguante datos reales heterogéneos."

### Diapositiva 7 — Evaluación experimental

`[Señalar la curva de speedup y luego la tabla.]`

"Ahora los resultados, que es donde se responde la pregunta inicial. El protocolo fue **riguroso**: probamos con **1, 2, 4 y 8 agentes**, con **3 repeticiones** cada uno más una corrida de calentamiento que descartamos, y semilla fija; reportamos media, desviación y el mejor de tres.

Miren la curva `[señalar]`: la línea verde es el **speedup medido** y la punteada es el ideal lineal. Con **8 nodos llegamos a un speedup de 5,59×** —es decir, casi seis veces más rápido. La curva sigue la tendencia ideal, con una separación que **crece** porque, al sumar nodos, el **overhead de coordinación** también crece. Eso se ve en la **eficiencia**, que baja a **0,70** `[señalar la tabla]`: seguimos aprovechando el 70 % del ideal con 8 nodos, lo cual para una coordinación centralizada es un muy buen número. Con esto sobre la mesa, Welinton cierra con la **calidad de la detección** y el **análisis crítico**."

## PARTE 3 — WELINTON · Calidad, análisis crítico y cierre (diapositivas 8–11)

### Diapositiva 8 — Calidad de la detección

`[Señalar los dos KPIs: recall 100 % y 8 hallazgos.]`

"Gracias, Juan. Que el sistema sea rápido no sirve de nada si **detecta mal**, así que medimos la calidad. Como el *ground truth* real es escaso, hicimos una **evaluación híbrida**: sobre los 636 vuelos reales **inyectamos 12 anomalías controladas** —perturbaciones que sabemos que son anómalas— para poder medir. El sistema las detectó **todas**: eso es un **recall de 1,0** `[señalar]`. Y además, entre los primeros del ranking, marcó **8 vuelos reales** genuinamente raros que nadie le había señalado `[señalar]`. Todo esto corrió en el **clúster QEMU real**, con dos nodos trabajando en paralelo."

### Diapositiva 9 — Análisis crítico

`[Ir señalando cada punto.]`

"Esta diapositiva es la más honesta de todas. Sí, el sistema **escala bien**, pero la eficiencia baja por el overhead de coordinación —lo diagnosticamos incluso con la métrica de **Karp–Flatt**, que muestra que ese costo se **amortiza** a medida que crece el trabajo `[señalar]`.

Y acá está el **aprendizaje central del proyecto**: la variable que decide todo es la **granularidad**. La carga densa acelera porque cada trozo tiene mucho cómputo; pero la misma arquitectura, corriendo sobre los **636 vuelos reales**, que son livianísimos, queda **limitada por I/O** y **no acelera** —su speedup es menor que 1 `[señalar]`. Y quiero ser claro: **esto no es un fracaso**. Es *la* lección de la materia —distribuir solo conviene si las particiones son suficientemente grandes— y la reportamos con total transparencia. Como cierre del análisis: también demostramos **tolerancia a fallos**, completando el trabajo con un nodo caído."

### Diapositiva 10 — El sistema, en vivo

`[Señalar la captura de la TUI a la izquierda y el gráfico a la derecha.]`

"Antes de concluir, queremos mostrarles que esto **funciona de verdad**, no es solo teoría. A la izquierda `[señalar]` está nuestra interfaz, diseñada como una **torre de control**: tiene un radar, los sectores de cada nodo del clúster y las alertas de anomalías en vivo. A la derecha `[señalar]` está el gráfico de *speedup* que **generó el propio benchmark**. Todo lo que ven en esta presentación es **evidencia real y trazable**: cada número sale de una corrida registrada. `[Opcional, si sobra tiempo:]` Si el profesor quiere, podemos hacer una **demostración en vivo** ahora mismo."

### Diapositiva 11 — Conclusiones

`[Última diapositiva. Bajar un poco el ritmo, mirar al público.]`

"Para cerrar. Cumplimos el objetivo: construimos un **orquestador distribuido propio** que detecta y rankea anomalías de vuelo, con **evidencia reproducible**. El **speedup de 5,59×** y la **equivalencia exacta** con la línea base justifican técnicamente la decisión de distribuir. El **recall de 1,0** confirma que la calidad se mantiene. Y el gran aprendizaje es que la **granularidad decide** si distribuir conviene: la misma arquitectura acelera con cómputo denso y no acelera con datos reales livianos.

Como **trabajo futuro**, la continuación natural es escalar a datos masivos con **Dask**, acelerar las *features* con *kernels* **OpenMP** y probar modelos como **Isolation Forest**. Con eso cerramos: muchas gracias, y quedamos atentos a sus preguntas."

---

# PARTE C — PREGUNTAS Y RESPUESTAS (simulacro de defensa)

> Repártanse quién responde qué, pero **todos** deben poder contestar cualquiera.

**¿Por qué usaron procesos y no hilos?**
Por el **GIL** de Python: solo un hilo ejecuta bytecode a la vez, así que para trabajo CPU-bound los hilos no dan paralelismo real. Cada **proceso** tiene su propio intérprete, entonces sí corren en paralelo de verdad.

**¿Por qué el speedup no es perfectamente lineal?**
Por el **overhead de coordinación y comunicación**, que crece con el número de nodos. Lo cuantificamos con **Karp–Flatt**: la fracción serie empírica va de 0,13 a 0,06 —**baja** con `p`, lo que indica que el costo fijo se **amortiza** y no hay una región puramente secuencial que nos limite.

**¿Por qué con los datos reales no acelera?**
Por **granularidad**: 636 vuelos son ~0,07 s de cómputo total, demasiado poco. El costo de repartir por la red **domina** al cómputo (*I/O-bound*), así que el speedup queda por debajo de 1. Con volumen masivo, el punto de equilibrio se movería y sí escalaría.

**¿Cómo garantizan que la versión distribuida da el mismo resultado que la secuencial?**
Verificamos la **equivalencia** en cada corrida: comparamos el **ranking top-k** y las **métricas** contra la línea base con la misma semilla. Si difirieran, **no reportamos** speedup. Así `T1` y `Tp` miden lo mismo.

**¿Esto es realmente distribuido o solo paralelo?**
Ambos. En local los agentes son **procesos**; en el clúster son **máquinas virtuales QEMU** independientes, con despliegue por **SSH** y comunicación por **TCP**. No comparten memoria: se coordinan por **mensajes**, que es la definición de distribuido.

**¿Qué es el scoring z-robusto con MAD y por qué no media/desviación estándar?**
Usamos **mediana** y **MAD** (desviación absoluta mediana) porque la media y la desviación estándar son **sensibles a los outliers** —y los outliers son justo lo que buscamos. Las métricas robustas no se "contaminan" con los vuelos raros.

**¿Qué pasa si un nodo se cae en plena ejecución?**
La **cola dinámica** reasigna su trozo a otro nodo; hay **reintentos** y, si el nodo no responde, se **excluye**. Lo demostramos: con un nodo caído, el trabajo terminó **8/8**.

**¿Por qué "datos-por-semilla"? ¿No es hacer trampa?**
No: es una técnica para **aislar el cómputo de la comunicación**. Al no transferir datos, medimos el escalado del **cálculo**, que es lo que queremos evaluar. Y como la semilla es fija, es **reproducible**. La variante con datos reales (transfiriendo el dataset) también la medimos y reportamos —de ahí sale la lección de granularidad.

**¿Qué es la ley de Amdahl y cómo se relaciona?**
Dice que si una fracción `f` del trabajo es serie, el speedup máximo es `1/f`, sin importar cuántos nodos agregues. En nuestro caso la fracción serie efectiva es pequeña y **decrece**, por eso escalamos bien hasta 8 nodos.

**¿Cuál es la limitación principal del sistema?**
La **coordinación centralizada**: a muchos nodos, el coordinador único se vuelve cuello de botella. La solución futura es una **coordinación jerárquica** (sub-coordinadores por grupo).

---

# PARTE D — GLOSARIO RÁPIDO

- **ADS-B:** sistema por el que los aviones transmiten su posición y estado.
- **Speedup (Sp):** T1/Tp, cuántas veces más rápido con p nodos.
- **Eficiencia (Ep):** Sp/p, fracción del ideal aprovechada.
- **Overhead:** trabajo extra de coordinación/comunicación (p·Tp − T1).
- **Amdahl:** la fracción serie limita el speedup máximo a 1/f.
- **Gustafson:** si el problema crece con la máquina, el speedup escala.
- **Karp–Flatt (e):** fracción serie empírica; diagnostica de dónde viene la pérdida.
- **Embarrassingly parallel:** subtareas sin dependencias ni comunicación.
- **Granularidad:** relación cómputo/comunicación por trozo; decide si acelera.
- **GIL:** candado de Python que impide paralelismo real con hilos.
- **Cola dinámica / work-stealing:** balanceo donde cada nodo libre pide el siguiente trozo.
- **map–reduce (split/run/merge):** partir, procesar en paralelo y reducir.
- **MAD:** mediana de las desviaciones absolutas; base del scoring robusto.
- **Datos-por-semilla:** mandar una semilla en vez de datos; el agente regenera.
- **Equivalencia:** el distribuido da el mismo resultado que el secuencial (verificado).
- **Tolerancia a fallos:** el sistema completa el trabajo aunque un nodo caiga.

---

## Manejo de la presentación

- Navegar: **`←` / `→`** (o barra espaciadora / clic). Pantalla completa: **`F`**. Volver al inicio: **`Home`**.
- Abrir `presentacion_final.html` **antes** de empezar (funciona offline, no necesita internet).
- Ensayar **una vez completa** cronometrando: el objetivo es **~20 minutos** repartidos como en la tabla.
