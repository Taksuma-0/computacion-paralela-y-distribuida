# Guia de Presentacion y Apoyo Tecnico - Laboratorio 4

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

Este archivo sirve como recorrido oral del notebook y como apunte tecnico para estudiar antes de presentar. La idea no es memorizar tablas, sino entender por que cada estrategia paralela se diseno asi.

## Mensaje central del laboratorio

El mensaje mas importante es que disenar un algoritmo paralelo no es lo mismo que agregar workers a un codigo existente. Primero hay que identificar unidades independientes, dependencias, particiones, variables locales, variables globales, reducciones, halos y costos de coordinacion.

## Apertura sugerida

Hola profesor. En este laboratorio construimos casos propios para trabajar el diseno de algoritmos paralelos antes de implementarlos con una libreria especifica. Nos enfocamos en descomposicion, particionamiento, dependencias, pseudocodigo paralelo y justificacion tecnica. La idea fue mostrar como se piensa el problema antes de programarlo.

## Recorrido recomendado del notebook

### 1. Metodologia

- Explicar que los datos son sinteticos y reproducibles.
- Mencionar que el foco del Lab 4 es el diseno, no medir speedup.
- Decir que la validacion en Python solo comprueba que las particiones conservan la correctitud.
- Mencionar el entorno para completar el registro minimo.

### 2. Desafio 1 - Analisis estructural y particionamiento

- Casos construidos: **Calibracion de sensores urbanos** y **Resumen de alertas por cuadrante**.
- El primer caso es patron `map`: cada salida depende de una entrada local.
- El segundo caso es patron `reduction`: los workers calculan parciales y luego se combinan.
- Mejor balance observado: **Adaptado por costo**.
- Desbalance maximo/promedio del mejor esquema: **1.008x**.
- Lectura correcta: la mejor particion depende del trade-off entre balance, locality y overhead.

### 3. Desafio 2.a - Reduccion por chunks

- Caso construido: promedio, varianza y maximo de severidad ambiental.
- Workers conceptuales: **8**.
- Variables locales: `n_local`, `suma_local`, `suma2_local`, `max_local`.
- Variables globales: `n_total`, `suma_total`, `suma2_total`, `max_global`.
- Error maximo contra la version secuencial: **0.00e+00**.
- Lectura correcta: la reduccion necesita una barrera logica antes de combinar parciales.

### 4. Desafio 2.b - Dependencia local con halos

- Caso construido: indice de salto termico sobre una serie temporal.
- Ancho de halo usado: **2**.
- Workers conceptuales: **4**.
- Error maximo de la version con halo: **0.00e+00**.
- Celdas internas que falla una particion ingenua sin halo: **12**.
- Lectura correcta: el pseudocodigo debe distinguir rango propio, rango leido y rango escrito.

### 5. Desafio 3 - Pipeline integrador

- Caso construido: pipeline de telemetria ambiental por lotes.
- Lotes procesados: **18**.
- Workers conceptuales: **4**.
- Desbalance final maximo/promedio: **1.06x**.
- Justificacion final: **433 palabras**.
- Lectura correcta: conviene procesar localmente y transferir parciales pequenos para reducir comunicacion.

### 6. Conclusion final comparativa

- Patrones comparados: **4**.
- Comparacion central: `map`, `reduction`, `stencil/halo` y `pipeline`.
- La tabla final permite defender que cada patron exige una coordinacion distinta.
- Frase util: "El diseno paralelo se decide por dependencias y coordinacion, no por elegir una libreria primero."

## Conceptos tecnicos que deben saber si o si

### Descomposicion por datos

Se divide el arreglo o coleccion de entrada en partes. Cada worker aplica la misma operacion sobre su tramo. Es adecuada para map, reducciones y muchos problemas sobre arreglos.

### Patron map

Cada salida depende de una entrada o de un elemento local. La coordinacion suele limitarse a ensamblar resultados en el orden correcto.

### Patron reduction

Cada worker calcula un resultado parcial y luego se combinan todos los parciales. Requiere una etapa global, normalmente despues de una barrera logica.

### Particionamiento

No es solo repartir cantidades iguales. Hay que considerar costo por dato, irregularidad, locality y overhead de planificacion.

### Locality

Acceso cercano o contiguo a datos. Los bloques contiguos suelen favorecerla, pero no siempre balancean bien cargas irregulares.

### Dependencia local

Una posicion depende de vecinos. Se puede paralelizar, pero el worker necesita halos o informacion de frontera.

### Halo

Datos extra que un worker lee fuera de su tramo propio para calcular correctamente los bordes de su particion.

### Barrera logica

Punto donde todos los workers deben terminar antes de continuar con una reduccion, ensamblaje o etapa global.

## Como conectar teoria con cada desafio

### Desafio 1

- Concepto: identificar el patron antes de particionar.
- Evidencia: map no requiere reduccion; reduction si necesita combinar parciales.

### Desafio 2.a

- Concepto: variables locales evitan conflictos.
- Evidencia: el resultado por chunks coincide con el secuencial con error maximo **0.00e+00**.

### Desafio 2.b

- Concepto: dependencias locales exigen halos.
- Evidencia: sin halo quedan **12** posiciones internas incompletas.

### Desafio 3

- Concepto: pipeline y reduccion final.
- Evidencia: se procesan lotes completos localmente y solo se transfieren parciales.

## Conclusion comparativa que deben defender

- `Map`: es el caso con menor coordinacion; cada salida depende de su entrada local y el riesgo principal es escribir dos veces el mismo indice.
- `Reduction`: permite trabajo local paralelo, pero exige barrera logica y combinacion global de parciales.
- `Stencil/halo`: no basta con repartir bloques; cada worker debe leer datos de frontera y escribir solo su rango valido.
- `Pipeline`: conviene procesar lotes completos localmente y transferir resumenes compactos, no todos los registros crudos.
- Idea global: ningun patron es universal; cada uno cambia el balance entre independencia, locality, comunicacion y sincronizacion.

## Frases tecnicas utiles para defender el trabajo

- "Antes de elegir hilos o procesos, identificamos que datos son independientes y donde aparece coordinacion."
- "En el patron map, la salida local no depende de otros workers."
- "En una reduction, el trabajo local es paralelo, pero la combinacion global introduce una etapa secuencial o coordinada."
- "El particionamiento por bloques favorece locality, pero puede desbalancearse si el costo por dato es irregular."
- "El halo separa lo que un worker lee de lo que realmente escribe."
- "Transferir parciales pequenos reduce costo de comunicacion frente a mover todos los registros crudos."

## Preguntas probables con respuestas tecnicas

### Por que no se uso simplemente el mismo numero de datos por worker?

Porque igual cantidad de datos no implica igual cantidad de trabajo. Si algunos datos requieren validacion extra, el costo real queda desbalanceado.

### Cual es la diferencia entre dependencia verdadera, anti-dependencia y output-dependencia?

Una dependencia verdadera aparece cuando una operacion necesita un dato producido por otra. Una anti-dependencia ocurre cuando una operacion escribe algo que otra todavia debe leer. Una output-dependencia aparece cuando dos operaciones intentan escribir el mismo resultado. En el notebook se evitan asignando rangos disjuntos y usando parciales locales.

### Por que la tabla de particionamiento no se decide solo por el mejor balance?

Porque una particion muy balanceada puede perder locality y aumentar overhead de planificacion. La decision debe mirar balance, acceso a memoria, costo irregular y coordinacion.

### Por que la reduccion necesita barrera?

Porque el resultado global depende de todos los parciales. Si se combina antes de que todos terminen, el promedio, varianza o maximo puede quedar incompleto.

### Que problema resuelve el halo?

Permite que cada worker calcule posiciones cercanas a sus fronteras usando vecinos que pertenecen a otra particion, sin escribir fuera de su tramo valido.

### Por que no conviene transferir todos los registros al final del pipeline?

Porque aumenta comunicacion y memoria. Es mejor calcular parciales locales y transferir solo resumenes compactos.

### Cual es la diferencia entre paralelizar codigo y disenar en paralelo?

Paralelizar codigo es repartir una implementacion existente. Disenar en paralelo es decidir desde la estructura del problema que se divide, que se coordina y que limites tendra la estrategia.

### Por que la conclusion no promete aceleracion universal?

Porque el laboratorio evalua diseno, no una herramienta concreta. Algunas partes son locales, otras requieren reduccion, halos o barreras, y esos costos pueden limitar el beneficio real.

## Errores que no deben cometer al explicar

- No decir que todo arreglo se paraleliza sin dependencias.
- No confundir map con reduction.
- No olvidar que los bordes de un stencil necesitan halos.
- No decir que el mejor balance siempre es la mejor opcion si destruye locality.
- No presentar pseudocodigo paralelo sin variables locales, reduccion o barreras cuando corresponda.

## Cierre sugerido

La conclusion general es que una buena estrategia paralela nace del analisis estructural. Primero se identifica si el problema es map, reduction, stencil o pipeline; despues se decide como particionar, que datos son locales, que informacion debe coordinarse y que overhead puede limitar el beneficio. En este laboratorio no prometimos aceleracion por simple reparto: mostramos donde existe paralelismo, bajo que restricciones y como escribir un pseudocodigo que lo haga defendible.
