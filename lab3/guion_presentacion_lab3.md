# Guia de Presentacion y Apoyo Tecnico - Laboratorio 3

## Datos base

- Asignatura: INFB8090 - Computacion Paralela
- Integrantes: Welinton Barrera y Joaquin Araya
- Profesor: Dr. Ing. Michael Miranda Sandoval
- Seccion: 412
- Equipo usado: Windows-11-10.0.26200-SP0
- Python: 3.13.5
- CPU logicos visibles: 16
- RAM aproximada: 15.26 GB

## Como usar esta guia

Este archivo sirve para dos cosas:

- como recorrido oral del notebook;
- como apunte tecnico para estudiar antes de presentar.

La idea es que no solo sepan que salio, sino tambien por que salio y como defenderlo si el profesor pregunta mas tecnico.

## Mensaje central del laboratorio

El mensaje mas importante es que en Python no existe una estrategia concurrente universal. La herramienta correcta depende del tipo de carga, del GIL, del overhead, de la granularidad y del peso relativo entre espera y computo.

## Apertura sugerida

Hola profesor. En este laboratorio construimos tres desafios originales para trabajar concurrencia en Python con evidencia propia. El foco no fue solo programar hilos, procesos o asyncio, sino medirlos en escenarios distintos y justificar tecnicamente cuando cada estrategia conviene y cuando no.

## Recorrido recomendado del notebook

### 1. Metodologia

- Explicar que se uso `time.perf_counter()`.
- Decir que hubo 1 warm-up y 5 repeticiones por configuracion.
- Recordar que todas las comparaciones usan la misma carga por estrategia.
- Mencionar el hardware para dejar clara la reproducibilidad.

### 2. Desafio 1.a - CPU-bound con hilos

- Caso construido: digest sintetico de bloques de telemetria usando aritmetica modular en Python puro.
- Mejor speedup con hilos: **0.99x**.
- Speedup promedio del caso: **0.97x**.
- Lectura correcta: no hay mejora consistente, lo que es coherente con el GIL.
- Frase util: "En CPU-bound puro, ThreadPoolExecutor no entrega paralelismo efectivo de bytecode en CPython."

### 3. Desafio 1.b - I/O-bound con hilos

- Caso construido: manifiestos sinteticos con latencia controlada y validacion liviana.
- Mejor perfil: **36 manifiestos**.
- Mejor speedup con hilos: **7.10x**.
- Mejor eficiencia con hilos: **88.8%**.
- Lectura correcta: ahora los hilos si ayudan porque logran solapar la espera.

### 4. Desafio 2 - Benchmark comparativo secuencial vs hilos vs procesos

- Mejor configuracion global: **Mediano con 8 procesos**.
- Mejor tiempo con procesos: **0.2639 s**.
- Mejor speedup de procesos: **2.19x**.
- Mejor speedup de hilos: **0.98x**.
- Lectura correcta: los procesos ganan cuando la granularidad alcanza para amortizar el overhead; los hilos quedan cerca de la linea base por el GIL.

### 5. Desafio 3 - Escenario mixto con asyncio

- Mejor perfil para asyncio: **Dominado por espera**.
- Mejor tiempo con asyncio: **0.0565 s**.
- Mejor speedup de asyncio: **12.56x**.
- Mejor speedup de hilos en el caso mixto: **6.60x**.
- Punto tecnico clave: cuando domina la espera, asyncio brilla; cuando crece el postproceso local, la ventaja se estrecha.

## Conceptos tecnicos que deben saber si o si

### Concurrencia vs paralelismo

- Concurrencia significa que varias tareas progresan de forma intercalada.
- Paralelismo significa ejecucion simultanea real.
- En Python, no toda concurrencia implica paralelismo efectivo.

### GIL

- El `Global Interpreter Lock` permite que solo un hilo ejecute bytecode Python a la vez dentro de un proceso CPython.
- Consecuencia: los hilos no suelen acelerar CPU-bound puro.
- Pero en I/O-bound siguen siendo utiles porque las esperas se solapan.

### CPU-bound

- Es una carga dominada por computo.
- En este laboratorio: desafio 1.a y desafio 2.
- Herramienta tipica: procesos, no hilos.

### I/O-bound

- Es una carga dominada por espera, latencia o recursos externos.
- En este laboratorio: desafio 1.b.
- Herramienta tipica: hilos o asyncio.

### Asyncio

- Modelo asincrono basado en corrutinas y event loop.
- Muy fuerte cuando hay muchas esperas no bloqueantes.
- No convierte computo local en paralelismo real por si solo.

### Overhead

- Costo extra de crear workers, coordinar tareas, serializar datos o sincronizar resultados.
- Explica por que el speedup real no suele ser lineal.

### Speedup

- Formula: `S(p) = T(1) / T(p)`.
- Mide cuantas veces mas rapida es una variante respecto de la referencia.

### Eficiencia

- Formula: `E(p) = S(p) / p`.
- Mide que tan bien se aprovechan los workers.
- Puede bajar aunque el tiempo total mejore.

### Granularidad

- Tamano de cada unidad de trabajo.
- Si la tarea es demasiado pequena, el overhead domina.
- Esto explica por que multiprocessing no siempre gana en problemas chicos.

### Serializacion

- En procesos, los datos deben enviarse entre workers y proceso padre.
- Eso cuesta tiempo y memoria.
- Por eso la ventaja de procesos depende del tamano del trabajo.

## Como conectar teoria con cada desafio

### Desafio 1.a

- Concepto: el GIL limita a los hilos en CPU-bound.
- Evidencia: speedup maximo con hilos de solo **0.99x**.

### Desafio 1.b

- Concepto: hilos si ayudan cuando domina la espera.
- Evidencia: speedup maximo de **7.10x** en el caso I/O-bound.

### Desafio 2

- Concepto: processes permiten paralelismo real en CPU-bound.
- Evidencia: speedup de procesos de hasta **2.19x**.

### Desafio 3

- Concepto: asyncio es excelente para espera no bloqueante, pero su ventaja se reduce si crece el trabajo local.
- Evidencia: speedup de asyncio de **12.56x** cuando domina la espera y de **5.64x** cuando aumenta el postproceso.

## Frases tecnicas utiles para defender el trabajo

- "La comparacion es valida porque cada estrategia se midio sobre exactamente la misma carga."
- "El GIL limita el paralelismo efectivo de bytecode Python en threads para CPU-bound."
- "Los procesos evitan el GIL, pero pagan overhead de creacion y serializacion."
- "En I/O-bound, los hilos y asyncio pueden solapar espera y mejorar throughput."
- "Asyncio no acelera automaticamente la fase CPU; solo administra mejor la espera no bloqueante."
- "El speedup observado es sublineal porque existen costos fijos y partes no paralelizables."

## Preguntas probables con respuestas tecnicas

### Por que los hilos no mejoraron en CPU-bound?

Porque el trabajo ocurre en Python puro y los hilos comparten el mismo GIL. Aunque existan varios, solo uno ejecuta bytecode a la vez.

### Entonces los hilos no sirven?

Si sirven, pero para otro tipo de carga. En el caso I/O-bound del laboratorio lograron speedup de hasta **7.10x** porque la espera se pudo solapar.

### Por que procesos no dan speedup lineal?

Porque crear procesos, enviar tareas, serializar resultados y sincronizar tiene costo. Amdahl y el overhead explican ese limite.

### Por que asyncio no gano siempre por mucho?

Porque cuando crece la parte CPU local, el event loop ya no puede esconder tanto costo. La espera sigue optimizada, pero el computo no se vuelve paralelo.

### Cuando elegirias cada estrategia en un problema nuevo?

- Secuencial: problemas chicos o fuertemente acoplados.
- Hilos: I/O-bound con espera bloqueante o simple.
- Procesos: CPU-bound de granularidad suficiente.
- Asyncio: muchas operaciones de espera no bloqueante con poco trabajo local por tarea.

## Errores que no deben cometer al explicar

- No decir que concurrencia y paralelismo son exactamente lo mismo.
- No decir que mas workers siempre mejoran el rendimiento.
- No decir que threads "no sirven en Python" de forma absoluta.
- No olvidar mencionar overhead, granularidad y GIL.
- No presentar un benchmark como verdad universal sin hablar del tipo de carga.

## Cierre sugerido

La conclusion general del laboratorio es que la mejor estrategia en Python depende de la naturaleza de la carga y de la estructura del problema. Los hilos son utiles cuando domina la espera, los procesos son preferibles cuando domina el computo y `asyncio` destaca en espera no bloqueante de alta concurrencia. La decision correcta no sale de intuicion ni de moda tecnologica, sino de un benchmark bien disenado e interpretado con criterio.
