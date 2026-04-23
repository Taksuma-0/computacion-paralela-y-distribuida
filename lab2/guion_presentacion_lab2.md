# Guia de Presentacion y Apoyo Tecnico - Laboratorio 2

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

Este archivo no esta pensado solo como libreto corto. Esta hecho para dos cosas:

- servir como guion base para una exposicion de 10 minutos o un poco mas;
- servir como apunte tecnico para estudiar antes de presentar.

La idea es que no solo sepan "que salio", sino tambien "por que salio" y "como defenderlo tecnicamente".

## Objetivo del laboratorio y mensaje central

El mensaje central del trabajo es este:

No repetimos los ejemplos exactos del PDF, pero si construimos ejercicios propios que demuestran los mismos aprendizajes del Laboratorio 2: medir tiempos de forma justa, calcular `speedup` y `eficiencia`, interpretar el comportamiento observado y finalmente justificar una decision tecnica sobre cuando conviene vectorizar, usar hilos, usar procesos o pensar en una estrategia distribuida.

La idea que conviene repetir varias veces durante la exposicion es:

**medir primero, comparar despues y concluir con base en evidencia, no por intuicion.**

## Apertura sugerida

Hola profesor. En este laboratorio, junto con Joaquin Araya, desarrollamos tres ejercicios originales para trabajar los mismos conceptos del Lab 02: modelos de computacion paralela, taxonomias vistas en clase y metricas de desempeno como speedup y eficiencia.

La decision que tomamos fue no copiar los ejemplos del PDF, sino construir problemas propios que respondieran al mismo objetivo. Por eso el notebook parte con una comparacion entre version escalar y vectorizada, sigue con dos escenarios de paralelismo practico, uno con hilos y otro con procesos, y termina con un ejercicio de decision tecnica sobre procesamiento por lotes independientes.

Lo importante es que en todos los casos partimos desde una linea base, medimos en condiciones comparables, calculamos metricas y despues interpretamos el resultado en terminos de overhead, tipo de carga y estructura del problema.

## Estructura recomendada para presentar el notebook

La exposicion se puede ordenar asi:

1. portada, contexto y metodologia;
2. ejercicio 1: vectorizacion;
3. ejercicio 2.a: hilos en una carga con latencia;
4. ejercicio 2.b: procesos en una carga CPU-bound;
5. ejercicio 3: decision estrategica sobre lotes;
6. cierre con conclusion global.

Si siguen este orden, la presentacion se siente como una historia tecnica y no como bloques desconectados.

## 1. Contexto y metodologia

### Que decir

Antes de entrar a los ejercicios, conviene explicar brevemente como se midio. En el notebook usamos `time.perf_counter()`, aplicamos un warm-up y despues hicimos cinco repeticiones por configuracion. Eso reduce el riesgo de sacar conclusiones desde una sola corrida anomala.

Tambien mostramos la maquina donde se hicieron los experimentos, porque las metricas de rendimiento dependen del entorno. Decir el hardware y la version de Python ayuda a que la medicion sea interpretable y reproducible.

### Puntos tecnicos que conviene remarcar

- las comparaciones usan la misma carga de trabajo;
- no se mezclan entradas distintas para calcular speedup;
- `speedup` y `eficiencia` se calculan sobre tiempos equivalentes;
- los resultados se interpretan con base en promedio, no en una sola muestra aislada.

### Frase util

Primero aseguramos comparaciones justas; despues interpretamos el rendimiento.

## 2. Ejercicio 1 - Vectorizacion de una senal sintetica

### Que hicimos

En el primer ejercicio aplicamos la misma transformacion numerica a una senal sintetica de dos maneras distintas:

- una version escalar, que recorre valor por valor en Python;
- una version vectorizada con NumPy.

La idea no era hacer paralelismo explicito, sino mostrar que una reformulacion del problema puede mejorar mucho el tiempo sin necesidad de usar hilos ni procesos.

### Resultados clave

- mejor speedup observado: **12.34x**
- ese mejor caso se dio en `n = 200.000`
- speedup promedio del ejercicio: **11.17x**

### Que decir al mostrar el grafico de tiempos

En el grafico de tiempos se observa que la version vectorizada queda consistentemente por debajo de la version escalar. Eso significa que, para la misma operacion matematica, NumPy resuelve el problema con mucho menos tiempo que un bucle Python tradicional.

### Que decir al mostrar el grafico de speedup

En el grafico de speedup se ve que la mejora no es un accidente puntual. Se mantiene alta en distintos tamanos de entrada, por lo que el patron es estable.

### Interpretacion tecnica

La interpretacion correcta es que el speedup viene de la vectorizacion. NumPy ejecuta operaciones en codigo optimizado, reduce el overhead del interprete y puede aprovechar paralelismo de datos a bajo nivel. Entonces aqui hay mejora real de rendimiento, pero no porque hayamos implementado un esquema MIMD con procesos independientes.

### Frase tecnica util

La mejora observada proviene de vectorizacion y de reduccion del overhead del interprete, no de paralelismo explicito con workers.

## 3. Ejercicio 2.a - Hilos sobre una carga con latencia

### Que hicimos

En este inciso simulamos un escenario parecido a leer metadatos o consultar informacion ligera: cada tarea tenia una espera artificial y una operacion pequena de validacion.

Lo ejecutamos:

- en serie;
- con `ThreadPoolExecutor` usando distintas cantidades de hilos.

### Resultados clave

- tiempo de referencia serial: **0.7112 s**
- mejor configuracion: **8 hilos**
- mejor tiempo medio: **0.1101 s**
- mejor speedup: **6.46x**
- mejor eficiencia: **80.8%**

### Interpretacion tecnica

Esta carga esta dominada por latencia, no por computo pesado. Por eso los hilos funcionan bien: mientras una tarea esta esperando, otra puede avanzar. El beneficio no viene de que cada hilo ejecute mas rapido, sino de que las esperas se solapan.

### Conexion con la teoria

Este caso se entiende como:

- paralelismo de tareas;
- memoria compartida;
- carga tipo `I/O-bound` o dominada por espera;
- overhead de coordinacion relativamente bajo.

### Frase tecnica util

En cargas dominadas por latencia, ThreadPoolExecutor permite ocultar tiempo de espera y mejorar el throughput sin necesidad de procesos separados.

## 4. Ejercicio 2.b - Procesos sobre una carga CPU-bound

### Que hicimos

En este inciso usamos una estimacion de PI por Monte Carlo, dividida en bloques independientes. Cada bloque genera puntos aleatorios y cuenta cuantos caen dentro del circulo unitario.

Eso representa una carga claramente CPU-bound, asi que la comparamos:

- en forma secuencial;
- con `ProcessPoolExecutor`.

### Resultados clave

- tiempo secuencial: **0.8183 s**
- PI estimado en la referencia: **3.14211**
- mejor configuracion: **8 procesos**
- mejor tiempo medio: **0.2841 s**
- mejor speedup: **2.88x**
- mejor eficiencia: **36.0%**

### Interpretacion tecnica

Aqui la carga consume computo real y no tiempo de espera. Por eso la herramienta correcta son los procesos y no los hilos. Cada proceso corre en su propio interprete, evita la restriccion del GIL y puede aprovechar mejor los nucleos disponibles.

El speedup es positivo, pero claramente sublineal. Eso no es un error: refleja el costo de crear procesos, repartir trabajo, serializar datos y coordinar la ejecucion.

### Conexion con la teoria

Este ejercicio conversa directamente con:

- CPU-bound;
- procesos;
- GIL;
- overhead;
- Ley de Amdahl.

### Frase tecnica util

Cuando la carga es CPU-bound y las tareas son independientes, los procesos superan a los hilos porque evitan el GIL, aunque el speedup real siga limitado por overhead.

## 5. Ejercicio 3 - Decision estrategica sobre lotes independientes

### Que hicimos

En el tercer ejercicio simulamos lotes independientes de datos y calculamos perfiles sinteticos por lote. El objetivo ya no era solo medir rendimiento, sino decidir cual era la estrategia mas razonable:

- quedarse secuencial;
- escalar verticalmente dentro del mismo equipo;
- o pensar en escalamiento horizontal/distribuido.

### Resultados clave

- tiempo secuencial: **0.7667 s**
- mejor configuracion local: **8 procesos**
- mejor tiempo medio: **0.3094 s**
- mejor speedup: **2.48x**
- mejor eficiencia: **31.0%**

### Conclusion tecnica

La recomendacion del notebook es **escalar verticalmente dentro del mismo equipo**.

### Como justificarla

- los lotes son independientes, por lo que existe paralelismo natural;
- la comunicacion es baja, porque cada worker solo retorna resultados agregados;
- el volumen actual cabe bien en una sola maquina;
- distribuir la carga ahora agregaria costo de comunicacion, orquestacion y complejidad sin una ganancia clara.

Entonces, no conviene quedarse secuencial, porque la mejora paralela ya es visible. Pero tampoco conviene pasar a distribuido, porque el tamano del problema todavia no lo exige.

### Frase tecnica util

Con la evidencia observada, el mejor compromiso entre rendimiento y complejidad es paralelismo local con procesos; el escalamiento horizontal todavia no esta justificado.

## Conceptos tecnicos que debemos saber si o si

Esta es la seccion mas importante para estudiar antes de presentar. Si el profesor hace preguntas mas tecnicas, estas definiciones y conexiones son las que deberian manejar con seguridad.

### T(1) y T(p)

`T(1)` es el tiempo de ejecucion con una sola unidad de procesamiento o con la version secuencial de referencia.

`T(p)` es el tiempo usando `p` workers, procesadores, hilos o procesos, segun el experimento.

En el notebook, por ejemplo:

- en el ejercicio 2.a, `T(1)` es la referencia serial y `T(p)` es el tiempo con `p` hilos;
- en el ejercicio 2.b, `T(1)` es el tiempo secuencial de Monte Carlo y `T(p)` es el tiempo con `p` procesos.

### Speedup

Se define como:

`S(p) = T(1) / T(p)`

Mide cuantas veces mas rapida es la version paralela o mejorada respecto de la referencia.

Interpretacion:

- si `S(p) > 1`, hubo mejora;
- si `S(p) = p`, seria speedup ideal o lineal;
- si `S(p) < p`, hay speedup sublineal;
- si `S(p) < 1`, la version nueva empeoro.

En el notebook:

- NumPy logro un speedup alto sin procesos;
- hilos dieron buen speedup en latencia;
- procesos dieron speedup moderado en CPU-bound.

### Eficiencia

Se define como:

`E(p) = S(p) / p`

Mide que tan bien se estan aprovechando los recursos paralelos.

Interpretacion:

- mientras mas cerca de 1, mejor uso teorico de los workers;
- cuando baja mucho, significa que el overhead esta pesando bastante.

En el notebook:

- 8 hilos en el ejercicio 2.a dieron **80.8%** de eficiencia;
- 8 procesos en el ejercicio 2.b dieron **36.0%**;
- 8 procesos en el ejercicio 3 dieron **31.0%**.

Eso muestra que mejorar tiempo total no implica automaticamente alta eficiencia.

### Overhead

Es el costo extra que aparece por paralelizar o coordinar:

- creacion de workers;
- sincronizacion;
- envio y recepcion de datos;
- serializacion;
- administracion del pool;
- combinacion final de resultados.

En el laboratorio, el overhead explica por que el speedup real no llega al ideal, especialmente en procesos.

### CPU-bound

Una tarea `CPU-bound` es una tarea cuyo cuello de botella esta en el computo. Mientras mas CPU tenga disponible, mejor puede escalar.

En el notebook, el ejercicio 2.b y el ejercicio 3 son CPU-bound.

### I/O-bound

Una tarea `I/O-bound` es una tarea cuyo cuello de botella esta en espera de datos, red, disco, latencia o eventos externos.

En el notebook, el ejercicio 2.a fue disenado para parecerse a una carga de ese tipo.

### GIL

El `Global Interpreter Lock` de CPython permite que un solo thread ejecute bytecode Python a la vez dentro de un mismo interprete.

Consecuencia:

- para tareas CPU-bound, los hilos no suelen escalar bien en Python puro;
- para tareas con espera o I/O, los hilos si pueden ser utiles porque las esperas se solapan.

Los procesos evitan este problema porque cada uno tiene su propio interprete.

### Vectorizacion

La vectorizacion consiste en expresar la operacion sobre colecciones completas de datos en vez de recorrer elemento por elemento en Python.

Ventajas:

- menos overhead del interprete;
- mejor uso de bibliotecas optimizadas;
- posible aprovechamiento de paralelismo de datos a bajo nivel.

En el notebook, esa fue la clave del ejercicio 1.

### Paralelismo de datos

Ocurre cuando la misma operacion se aplica sobre muchos datos independientes.

En el notebook, el ejercicio 1 se parece a este patron: una misma transformacion aplicada sobre toda la senal.

### Paralelismo de tareas

Ocurre cuando distintas unidades de trabajo pueden ejecutarse en paralelo porque son independientes o casi independientes.

En el notebook:

- ejercicio 2.a: consultas independientes;
- ejercicio 2.b: bloques independientes de simulacion;
- ejercicio 3: lotes independientes.

### Threads

Los threads comparten memoria dentro del mismo proceso.

Ventajas:

- bajo costo de creacion;
- facil compartir estado;
- utiles en latencia o I/O.

Limitaciones:

- en Python, el GIL reduce su utilidad para CPU-bound puro.

### Processes

Los procesos tienen memoria separada y cada uno ejecuta su propio interprete.

Ventajas:

- permiten aprovechar mejor multiples nucleos en CPU-bound;
- no comparten el mismo GIL.

Limitaciones:

- mayor overhead;
- mas costo para pasar datos;
- serializacion.

### Memoria compartida

Es un modelo donde varios workers acceden a una memoria comun.

En Python, los threads se asocian conceptualmente a este esquema.

### Memoria distribuida

Es un modelo donde cada unidad tiene su propia memoria y la comunicacion entre unidades es explicita.

En el laboratorio no implementamos un sistema distribuido real, pero el ejercicio 3 sirve para discutir cuando tendria sentido pasar a ese nivel.

### SIMD

`Single Instruction, Multiple Data`.

La misma instruccion opera sobre muchos datos.

Relacion con el notebook:

- ejercicio 1;
- vectorizacion;
- paralelismo de datos.

### MIMD

`Multiple Instruction, Multiple Data`.

Multiples unidades ejecutan instrucciones sobre datos distintos.

Relacion con el notebook:

- hilos y procesos ejecutando tareas separadas;
- ejercicio 2.a, 2.b y 3.

### Ley de Amdahl

Dice que el speedup total esta limitado por la parte secuencial y por el overhead. Aunque agregues mas workers, siempre existe un techo practico.

En el notebook se ve en los ejercicios con procesos: usar mas workers mejora, pero no entrega speedup lineal.

### Ley de Gustafson

Plantea que si el tamano del problema crece junto con el numero de workers, el paralelismo puede aprovecharse mejor.

Conexion con el notebook:

- hoy el ejercicio 3 no necesita distribuido;
- pero si aumentaran mucho los lotes o el volumen por lote, Gustafson ayuda a justificar una estrategia mas escalable.

### Escalamiento vertical

Es usar mas recursos dentro del mismo equipo: mas nucleos, mas RAM, mejor CPU.

En el ejercicio 3, esa fue la recomendacion final.

### Escalamiento horizontal

Es repartir el trabajo entre varias maquinas o nodos.

No fue la recomendacion del laboratorio porque el problema aun no tiene volumen suficiente para justificar esa complejidad.

### Granularidad

La granularidad describe el tamano de las unidades de trabajo.

- grano grueso: pocas tareas grandes;
- grano fino: muchas tareas pequenas.

Si la tarea es demasiado pequena, el overhead puede comerse la ganancia. Esto ayuda a explicar por que a veces agregar mas workers no conviene tanto como parece.

## Como conectar teoria y resultados

Esta seccion sirve para no perder el hilo teorico cuando esten mostrando el notebook.

### Ejercicio 1

- concepto principal: vectorizacion;
- taxonomia relacionada: SIMD o paralelismo de datos;
- idea central: puede haber gran mejora sin procesos ni hilos;
- conclusion: antes de paralelizar, conviene preguntar si el problema puede reescribirse de forma vectorizada.

### Ejercicio 2.a

- concepto principal: threads;
- modelo: memoria compartida;
- tipo de carga: I/O-bound o dominada por espera;
- idea central: los hilos solapan latencias y mejoran throughput;
- conclusion: los hilos tienen sentido cuando el cuello no esta en CPU.

### Ejercicio 2.b

- concepto principal: processes;
- tipo de carga: CPU-bound;
- idea central: los procesos vencen la limitacion del GIL;
- teoria asociada: overhead y Amdahl;
- conclusion: para computo pesado independiente, procesos es la opcion correcta.

### Ejercicio 3

- concepto principal: decision tecnica;
- idea central: no toda tarea paralelizable debe pasar inmediatamente a distribuido;
- factores claves: independencia, volumen, overhead, costo de coordinacion;
- conclusion: la evidencia favorece escalamiento vertical local.

## Frases tecnicas utiles para defender el trabajo

- La comparacion es valida porque `T(1)` y `T(p)` se midieron sobre la misma carga de trabajo.
- La mejora de NumPy proviene de vectorizacion y reduccion del overhead del interprete, no de MIMD explicito.
- En cargas dominadas por latencia, los hilos permiten solapar esperas y mejorar throughput.
- En cargas CPU-bound, los procesos son mas adecuados porque cada worker ejecuta en su propio interprete.
- El speedup observado es sublineal, lo que es coherente con costos de coordinacion y con la Ley de Amdahl.
- Mejorar tiempo total no implica automaticamente alta eficiencia; la eficiencia cae cuando el overhead crece.
- En el ejercicio 3, el problema es paralelizable, pero todavia no lo bastante grande como para justificar una arquitectura distribuida.
- La decision tecnica correcta depende del tipo de carga y de la estructura de dependencias, no solo del tiempo bruto.

## Preguntas probables con respuestas mas tecnicas

### Por que el resultado de NumPy cuenta como speedup si no usamos procesos?

Porque `speedup` solo compara tiempos entre una version base y una version mejorada. No exige que la mejora venga de procesos o hilos. En este caso, la mejora viene de vectorizacion, codigo compilado y menor overhead del interprete.

### Entonces vectorizacion y paralelismo son lo mismo?

No exactamente. La vectorizacion suele aprovechar paralelismo de datos a bajo nivel, pero para el programador no es lo mismo que coordinar procesos o hilos independientes. Son mecanismos distintos, aunque ambos puedan mejorar rendimiento.

### Por que no usar siempre procesos?

Porque los procesos tienen costo: creacion, coordinacion, serializacion y transferencia de datos. Si la carga esta dominada por espera o es demasiado ligera, ese overhead puede volverlos innecesarios o ineficientes.

### Por que 8 procesos no entregan speedup 8x?

Porque el ideal `S(p)=p` casi nunca se alcanza en sistemas reales. Siempre hay parte secuencial, ademas de costos de coordinacion, creacion de procesos, serializacion y balanceo imperfecto.

### Por que la eficiencia puede bajar aunque el tiempo total mejore?

Porque la eficiencia mide aprovechamiento relativo por worker. Si agregar workers reduce tiempo, pero el overhead crece mas rapido, la mejora marginal por worker disminuye y la eficiencia baja.

### Por que en el ejercicio 2.a hilos y no procesos?

Porque ahi la carga no era de computo pesado, sino de espera. Los hilos tienen menor costo y son suficientes para solapar latencias. Usar procesos habria agregado complejidad sin una necesidad clara.

### Por que en el ejercicio 2.b procesos y no hilos?

Porque la carga era CPU-bound. En Python, para ese tipo de problema, los hilos comparten el mismo GIL y no aprovechan igual los nucleos. Los procesos si pueden hacerlo mejor.

### Por que no recomendar distribuido en el ejercicio 3?

Porque el volumen actual cabe bien en una sola maquina, la memoria no es el problema y la coordinacion local es barata. Distribuir agregaria costo de comunicacion y orquestacion sin una ganancia proporcional.

### Que evidencia podria hacer cambiar la recomendacion del ejercicio 3?

Si creciera mucho el numero de lotes, el tamano por lote, la necesidad de memoria o si los datos ya estuvieran repartidos entre nodos. En ese escenario, el escalamiento horizontal empezaria a justificarse mejor.

### Como se conecta Amdahl con nuestros resultados?

Se conecta en que el speedup real fue sublineal. Eso refleja que, aunque gran parte del trabajo sea paralelizable, siempre existe una fraccion secuencial y un overhead que limita la aceleracion total.

### Como se conecta Gustafson con el laboratorio?

Gustafson es util para decir que, si el problema creciera con el numero de workers, el paralelismo podria justificarse aun mas. Eso sirve especialmente para discutir un futuro escenario distribuido en el ejercicio 3.

## Errores que no debemos cometer al explicar

- No decir que vectorizacion y paralelismo son exactamente lo mismo.
- No decir que mas workers siempre significa mejor rendimiento.
- No decir que un speedup alto implica automaticamente alta eficiencia.
- No confundir paralelismo local con computacion distribuida.
- No decir que el mejor tiempo define un modelo universal.
- No ignorar el overhead al interpretar resultados.
- No comparar tiempos de cargas distintas como si fueran equivalentes.
- No olvidar mencionar el hardware y la metodologia de medicion.

## Cierre general sugerido

Si tuviera que resumir todo el laboratorio en una sola idea, diria esto: el modelo correcto depende del tipo de carga y de la estructura del problema.

En el primer ejercicio vimos que una vectorizacion bien hecha puede entregar una mejora muy alta sin paralelismo explicito. En el segundo vimos que los hilos funcionan bien cuando la carga esta dominada por latencia, mientras que los procesos funcionan mejor cuando la carga es CPU-bound. Y en el tercer ejercicio usamos esas mediciones para justificar una decision tecnica mas realista sobre como escalar.

Por eso, `speedup` y `eficiencia` no deben leerse solos. Siempre hay que interpretarlos junto con overhead, independencia de tareas, comunicacion, granularidad y costo de coordinacion.

## Version corta de cierre

En este laboratorio construimos ejercicios propios para demostrar los mismos conceptos del Lab 02. Confirmamos que NumPy puede entregar speedup alto por vectorizacion, que los hilos funcionan mejor cuando domina la latencia, que los procesos son mas adecuados para CPU-bound y que, para lotes independientes de tamano moderado, la mejor recomendacion es paralelismo local y no computacion distribuida.

## Ultimo consejo para exponer

Cada vez que muestren una tabla o un grafico, digan siempre estas tres cosas:

1. que se estaba comparando;
2. que resultado salio;
3. que significa tecnicamente.

Si hacen eso en cada ejercicio, la presentacion se va a sentir mucho mas solida y se va a notar que no solo ejecutaron codigo, sino que entendieron el laboratorio.
