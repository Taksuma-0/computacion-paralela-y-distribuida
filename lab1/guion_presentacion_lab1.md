# Guion de Apoyo - Laboratorio 1

## Datos base

- Asignatura: INFB8090 - Computación Paralela y Distribuida
- Estudiante: Welinton Barrera Mondaca
- Sección: 412
- Profesor: Dr. Ing. Michael Miranda Sandoval
- Tema: Diagnóstico experimental de paralelismo

## Idea central que tengo que transmitir

La idea principal del laboratorio no fue paralelizar de verdad, sino aprender a medir, observar la estructura del problema y decidir si existe o no una oportunidad razonable de paralelización. En otras palabras: primero entender y medir, después pensar en optimizar.

## Guion oral de 5 a 8 minutos

### 1. Inicio

Hola profesor. En este laboratorio trabajé un diagnóstico experimental de paralelismo. El objetivo fue medir tiempos de ejecución en Python, distinguir entre tareas secuenciales y tareas con partes independientes, y reflexionar sobre cuándo el paralelismo realmente tiene sentido en problemas de ciencia de datos.

Lo que busqué demostrar en el notebook es que no basta con que un programa demore para concluir que hay que paralelizarlo. También importa mucho cómo está estructurado el trabajo.

### 2. Contexto y objetivo del notebook

Primero dejé una sección de contexto para explicar que este laboratorio es introductorio. No está pensado todavía para implementar concurrencia real, sino para construir una línea base secuencial, comparar variantes de procesamiento y justificar técnicamente una decisión.

## Explicación por secciones

### 3. Ejercicio 1: línea base secuencial

En el primer ejercicio trabajé con una suma acumulada de cuadrados. La función recorre una secuencia de enteros y va sumando los cuadrados uno por uno.

Los tiempos que obtuve fueron:

- `100.000` elementos: `0.005389 s`
- `500.000` elementos: `0.028212 s`
- `1.000.000` elementos: `0.051252 s`

Lo importante acá es que el tiempo aumenta al crecer el tamaño de entrada. En esta corrida, pasar de `100.000` a `500.000` multiplicó el tiempo aproximadamente por `5.24`, y pasar de `100.000` a `1.000.000` lo multiplicó por `9.51`.

Lo que yo explicaría acá es que esta versión funciona como una referencia secuencial base, porque todo ocurre en un solo flujo de ejecución. No hay división del trabajo ni procesos paralelos. Por eso sirve como punto de comparación para el resto del laboratorio.

### Qué decir en una frase

Este ejercicio me sirvió para construir una línea base secuencial y observar que el tiempo crece a medida que aumenta la carga de trabajo.

### 4. Ejercicio 2: secuencial vs procesamiento por bloques

En el segundo ejercicio comparé dos formas de procesar la misma lista de datos:

- una versión secuencial, elemento por elemento
- una versión por bloques

Los resultados fueron:

- procesamiento secuencial: `0.061631 s`
- procesamiento por bloques: `0.063590 s`
- diferencia: `0.001959 s`

En esta ejecución, la versión por bloques tardó un poco más. Acá es importante no confundirme: el punto del ejercicio no era demostrar que la versión por bloques necesariamente fuera más rápida, sino mostrar que la estructura del problema deja ver partes relativamente independientes.

Cada bloque puede procesarse con la misma lógica y luego combinarse al final mediante subtotales. Entonces, aunque acá no implementé paralelismo real, sí aparece una oportunidad razonable de paralelización futura.

### Qué decir en una frase

El valor de este ejercicio no está en que una variante gane por tiempo, sino en que la versión por bloques hace visible la independencia entre subconjuntos del problema.

### 5. Ejercicio 3: caso aplicado a ciencia de datos

En el tercer ejercicio simulé ocho lotes de datos independientes y calculé para cada lote una media, un mínimo y un máximo. El tiempo total de procesamiento fue:

- tiempo total: `0.038107 s`

La decisión que tomé fue que este problema se presta más a paralelismo en un mismo equipo que a computación distribuida.

La razón es que los lotes son independientes entre sí, así que existe una posibilidad clara de repartir el trabajo. Pero al mismo tiempo, el volumen del ejemplo sigue siendo manejable y no justifica agregar la complejidad de distribuir el cálculo entre varias máquinas.

### Qué decir en una frase

Como los lotes son independientes, hay potencial de paralelismo local; pero con este tamaño de problema no se justifica hablar todavía de computación distribuida.

### 6. Conclusión

Mi conclusión general es que el laboratorio me permitió distinguir entre una tarea claramente secuencial y tareas que tienen potencial de paralelización por su independencia interna. También confirmé que medir antes de optimizar es fundamental, porque si uno no observa tiempos ni estructura del problema, puede terminar proponiendo soluciones más complejas sin una necesidad real.

## Repaso rápido de materia

### Qué es una tarea secuencial

Es una tarea que se ejecuta paso a paso en un solo flujo. Cada instrucción avanza en orden y no se reparte el trabajo al mismo tiempo entre varias unidades.

### Qué es paralelismo

Es ejecutar varias partes de un problema al mismo tiempo, normalmente usando varios núcleos o varios procesos. El paralelismo tiene sentido cuando esas partes son lo bastante independientes y el costo de coordinarlas no supera la ganancia.

### Qué es computación distribuida

Es repartir el trabajo entre varios equipos o nodos conectados. Se usa cuando la carga o el volumen de datos ya supera lo razonable para un solo equipo, o cuando los datos están naturalmente repartidos en distintos lugares.

### Qué significa independencia de tareas

Significa que una parte del problema puede resolverse sin depender inmediatamente del resultado de otra. Mientras más independientes sean las subtareas, más sentido tiene pensar en paralelización.

### Qué es sobrecarga

Es el costo extra de coordinar procesos, sincronizar resultados, comunicar datos o repartir trabajo. Aunque algo sea paralelizable, la sobrecarga puede hacer que no convenga si el problema es pequeño.

### Qué es una línea base

Es una medición inicial de referencia, normalmente secuencial, que sirve para comparar después si una mejora realmente aporta algo.

## Cosas que conviene decir si te preguntan

### ¿Por qué no paralelizaste directamente?

Porque el laboratorio tiene un carácter diagnóstico. El objetivo era medir, comparar y justificar si existía o no una oportunidad real de paralelización antes de implementar algo más complejo.

### ¿Por qué no basta con que un programa sea lento?

Porque la lentitud por sí sola no dice si el problema tiene partes independientes ni si la sobrecarga de coordinar compensa. Primero hay que mirar la estructura del problema.

### ¿Qué condiciones hacen pertinente el paralelismo?

- independencia entre subtareas
- suficiente carga computacional por tarea
- poco acoplamiento entre partes
- bajo costo de combinación final

### ¿Cuándo usaría computación distribuida?

Cuando el volumen de datos o el tamaño del problema ya sea demasiado grande para un solo equipo, o cuando la información esté repartida en distintas máquinas.

### ¿Qué aprendiste en este laboratorio?

Aprendí que el paralelismo no es una solución universal. Es una decisión técnica que debe apoyarse en mediciones, análisis y comprensión de la estructura del problema.

## Cosas que no me conviene decir

- No decir: "la versión por bloques es mejor porque fue más rápida" o "porque fue más lenta".
- Sí decir: "la diferencia de tiempo puntual no es lo central; lo central es que por bloques revela independencia".

- No decir: "si algo demora, hay que paralelizarlo".
- Sí decir: "primero hay que medir y analizar si la estructura del problema lo permite".

- No decir: "distribuida y paralela son lo mismo".
- Sí decir: "paralelismo suele pensarse dentro de un equipo; distribuida implica varios equipos o nodos".

## Resumen ultra corto por si me piden hablar rápido

En este laboratorio medí una tarea secuencial, comparé una versión normal con una versión por bloques y analicé un caso con lotes independientes. Mi conclusión fue que no todo problema lento debe paralelizarse, y que la clave está en medir y en identificar si existen subtareas independientes. En el caso final, vi que hay potencial de paralelismo local, pero no una necesidad real de computación distribuida.
